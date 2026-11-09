from __future__ import annotations

import httpx
import pytest

from app.core.config import settings
from app.services.ingest.llm_structurer import (
    STRUCTURER_PROMPT_VERSION,
    apply_llm_structuring,
)
from app.services.ingest.pipeline import ingest_bytes
from app.services.jd_analyser import analyse_jd
from app.services.llm.base import LLMResult, LLMUsage, OpenAIProvider, StubProvider
from app.services.scoring.engine import build_score_report
from app.services.scoring.judge import run_llm_judge
from tests.conftest import SAMPLE_JD, SAMPLE_TEX


class _FakeResponse:
    def __init__(self, status_code: int, body: dict) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> dict:
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPError("error")


class _FakeClient:
    responses: list[_FakeResponse] = []
    calls = 0

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(self, *args: object, **kwargs: object) -> _FakeResponse:
        _FakeClient.calls += 1
        return _FakeClient.responses.pop(0)


def _openai_body(content: str, prompt: int = 100, completion: int = 20) -> dict:
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
        },
    }


async def test_stub_provider_returns_no_data():
    result = await StubProvider().complete_result(
        system="s", user="u", schema_name="x", prompt_version="v1"
    )
    assert result.data is None
    assert result.provider == "stub"
    assert result.error


async def test_openai_provider_retries_and_accounts_usage(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_max_retries", 1)
    monkeypatch.setattr(settings, "llm_retry_backoff_seconds", 0.0)
    monkeypatch.setattr(settings, "llm_input_cost_per_million", 2.0)
    monkeypatch.setattr(settings, "llm_output_cost_per_million", 4.0)
    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

    _FakeClient.responses = [
        _FakeResponse(429, {}),
        _FakeResponse(200, _openai_body('{"proposals": []}')),
    ]
    _FakeClient.calls = 0

    result = await OpenAIProvider().complete_result(
        system="s", user="u", schema_name="rewrite", prompt_version="rewriter-v1"
    )
    assert result.ok is True
    assert result.data == {"proposals": []}
    assert result.attempts == 2
    assert result.usage.prompt_tokens == 100
    assert result.usage.completion_tokens == 20
    assert result.usage.cost_usd == pytest.approx(0.00028)
    assert result.prompt_version == "rewriter-v1"
    assert _FakeClient.calls == 2


async def test_openai_provider_rejects_non_json(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_max_retries", 0)
    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    _FakeClient.responses = [_FakeResponse(200, _openai_body("not json at all"))]

    result = await OpenAIProvider().complete_result(
        system="s", user="u", schema_name="rewrite"
    )
    assert result.data is None
    assert "JSON" in (result.error or "")


class _FakeProvider:
    name = "openai"

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    async def complete_result(self, **kwargs: object) -> LLMResult:
        self.calls += 1
        return LLMResult(
            data=self.payload,
            provider=self.name,
            model="fake-model",
            schema_name="resume_structuring",
            prompt_version=STRUCTURER_PROMPT_VERSION,
            usage=LLMUsage(prompt_tokens=10, completion_tokens=5, cost_usd=0.001),
        )

    async def complete_json(self, **kwargs: object) -> dict | None:
        return self.payload


def _fallback_document():
    return ingest_bytes("jane.tex", None, SAMPLE_TEX.encode("utf-8")).document


async def test_llm_structuring_merges_valid_fields(monkeypatch):
    monkeypatch.setattr(settings, "llm_structuring_enabled", True)
    provider = _FakeProvider(
        {
            "resume": {
                "basics": {
                    "name": "Jane Doe",
                    "email": "jane.doe@example.com",
                    "label": "Backend Engineer",
                },
                "skills": [{"name": "Cloud", "keywords": ["AWS", "Docker"]}],
            },
            "confidence": 0.91,
        }
    )
    original = _fallback_document()
    updated = await apply_llm_structuring(original, SAMPLE_TEX, provider=provider)

    assert updated.structuring.method == "llm"
    assert updated.structuring.model == "fake-model"
    assert updated.structuring.prompt_version == STRUCTURER_PROMPT_VERSION
    assert updated.structuring.confidence == 0.91
    assert updated.canonical.basics.label == "Backend Engineer"
    # Sections the model omitted are retained from the heuristic result.
    assert updated.canonical.work
    assert any(skill.name == "Cloud" for skill in updated.canonical.skills)
    assert updated.parse_fidelity["llm_structuring"] == "used"
    assert any(issue.code == "llm_structuring_used" for issue in updated.issues)


async def test_llm_structuring_falls_back_on_invalid_schema(monkeypatch):
    monkeypatch.setattr(settings, "llm_structuring_enabled", True)
    provider = _FakeProvider({"resume": {"work": "not-a-list"}, "confidence": 0.5})
    original = _fallback_document()
    updated = await apply_llm_structuring(original, SAMPLE_TEX, provider=provider)

    assert updated.structuring.method == "heuristic"
    assert updated.canonical.model_dump() == original.canonical.model_dump()
    assert any(issue.code == "llm_structuring_invalid" for issue in updated.issues)


async def test_llm_structuring_disabled_keeps_document(monkeypatch):
    monkeypatch.setattr(settings, "llm_structuring_enabled", False)
    provider = _FakeProvider({"resume": {"basics": {"name": "Ignored"}}})
    original = _fallback_document()
    updated = await apply_llm_structuring(original, SAMPLE_TEX, provider=provider)

    assert updated is original
    assert provider.calls == 0


async def test_llm_judge_clamps_and_attributes(monkeypatch):
    monkeypatch.setattr(settings, "llm_judge_enabled", True)
    document = _fallback_document()
    analysis, _ = analyse_jd(SAMPLE_JD, title="Senior Backend Engineer")
    report = build_score_report(
        resume_id="resume-1",
        jd_id="jd-1",
        document=document,
        analysis=analysis,
    )
    provider = _FakeProvider(
        {
            "score": 130,
            "confidence": 2,
            "adjustment": 99,
            "strengths": ["FastAPI evidence", "Production API scale"],
            "gaps": ["Terraform not evidenced"],
            "rationale": "Strong backend match with one must-have gap.",
        }
    )
    judge = await run_llm_judge(document, analysis, report, provider=provider)

    assert judge is not None
    assert judge["advisory_score"] == 100.0
    assert judge["adjustment"] == 5.0
    assert judge["confidence"] == 1.0
    assert judge["provider"] == "openai"
    assert judge["prompt_version"] == "judge-v1"
    assert judge["strengths"]
    assert judge["gaps"]


async def test_llm_judge_disabled_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "llm_judge_enabled", False)
    document = _fallback_document()
    analysis, _ = analyse_jd(SAMPLE_JD)
    report = build_score_report(
        resume_id="resume-1",
        jd_id="jd-1",
        document=document,
        analysis=analysis,
    )
    provider = _FakeProvider({"score": 99, "adjustment": 5})
    assert await run_llm_judge(document, analysis, report, provider=provider) is None
    assert provider.calls == 0
