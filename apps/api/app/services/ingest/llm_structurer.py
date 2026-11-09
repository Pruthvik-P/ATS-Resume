"""Schema-constrained LLM structuring with a deterministic fallback.

The heuristic structurer always runs first. When `ATS_LLM_STRUCTURING_ENABLED`
is on and a real provider is configured, this module asks the model for a
JSON-Resume subset, validates every field with Pydantic, and merges non-empty
sections over the heuristic result. Invalid or empty output silently falls
back, with an audit issue explaining why.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.schemas.common import ParseIssue
from app.schemas.resume import Resume, ResumeDocument, StructuringMeta
from app.services.llm.base import LLMProvider, get_llm_provider

STRUCTURER_PROMPT_VERSION = "structurer-v1"

STRUCTURER_SYSTEM_PROMPT = """\
You extract a resume into a conservative JSON Resume subset.
RULES:
1. Use only text present in <resume_text>. Never invent employers, dates, titles,
   degrees, metrics, or skills.
2. Omit unknown fields instead of guessing. Preserve original wording for
   highlights and summaries.
3. Return one JSON object:
   {"resume": {"basics": {...}, "work": [...], "education": [...],
    "skills": [...], "projects": [...], "certifications": [...],
    "languages": [...], "awards": [...]},
    "confidence": 0.0}
4. Work entries: {"name", "position", "startDate", "endDate", "highlights"}.
5. Skills entries: {"name", "keywords"}.
"""


def _merge_basics(primary: Any, secondary: Any) -> Any:
    merged = secondary.model_copy(deep=True)
    for field in type(primary).model_fields:
        value = getattr(primary, field)
        if value:
            setattr(merged, field, value)
    return merged


def _merge_resume(fallback: Resume, candidate: Resume) -> Resume:
    """Keep heuristic fields the model omitted, prefer model fields it found."""

    merged = fallback.model_copy(deep=True)
    merged.basics = _merge_basics(candidate.basics, fallback.basics)
    for field in (
        "work",
        "education",
        "skills",
        "projects",
        "certifications",
        "languages",
        "awards",
    ):
        candidate_value = getattr(candidate, field)
        if candidate_value:
            setattr(merged, field, candidate_value)
    return merged


def _has_content(resume: Resume) -> bool:
    return bool(
        resume.basics.name
        or resume.basics.email
        or resume.work
        or resume.education
        or resume.skills
        or resume.projects
    )


async def apply_llm_structuring(
    document: ResumeDocument,
    raw_text: str,
    *,
    provider: LLMProvider | None = None,
) -> ResumeDocument:
    """Return a document with LLM-structured fields when enabled and valid."""

    if not settings.llm_structuring_enabled:
        return document
    provider = provider or get_llm_provider()
    if provider.name == "stub":
        return document

    prompt = f"<resume_text>\n{raw_text[:24_000]}\n</resume_text>"
    result = await provider.complete_result(
        system=STRUCTURER_SYSTEM_PROMPT,
        user=prompt,
        schema_name="resume_structuring",
        prompt_version=STRUCTURER_PROMPT_VERSION,
    )
    issues = list(document.issues)
    if not result.data:
        issues.append(
            ParseIssue(
                code="llm_structuring_failed",
                severity="info",
                message=(
                    "LLM structuring was requested but returned no usable JSON; "
                    "the deterministic heuristic result was kept."
                ),
            )
        )
        return document.model_copy(
            update={"issues": issues, "parse_fidelity": {**document.parse_fidelity, "llm_structuring": "failed"}}
        )

    payload = result.data.get("resume", result.data)
    if not isinstance(payload, dict):
        payload = {}
    try:
        candidate = Resume.model_validate(payload)
    except Exception as exc:
        issues.append(
            ParseIssue(
                code="llm_structuring_invalid",
                severity="info",
                message=(
                    "LLM structuring returned a schema-invalid resume; the heuristic "
                    f"result was kept ({type(exc).__name__})."
                ),
            )
        )
        return document.model_copy(
            update={"issues": issues, "parse_fidelity": {**document.parse_fidelity, "llm_structuring": "invalid"}}
        )

    if not _has_content(candidate):
        issues.append(
            ParseIssue(
                code="llm_structuring_empty",
                severity="info",
                message=(
                    "LLM structuring returned no usable fields; the heuristic result was kept."
                ),
            )
        )
        return document.model_copy(
            update={"issues": issues, "parse_fidelity": {**document.parse_fidelity, "llm_structuring": "empty"}}
        )

    merged = _merge_resume(document.canonical, candidate)
    confidence = result.data.get("confidence", 0.8)
    try:
        confidence = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        confidence = 0.8
    structuring = StructuringMeta(
        method="llm",
        confidence=round(confidence, 2),
        model=result.model,
        prompt_version=STRUCTURER_PROMPT_VERSION,
    )
    fidelity = {
        **document.parse_fidelity,
        "llm_structuring": "used",
        "llm_model": result.model,
        "llm_prompt_version": STRUCTURER_PROMPT_VERSION,
        "llm_usage": {
            "prompt_tokens": result.usage.prompt_tokens,
            "completion_tokens": result.usage.completion_tokens,
            "cost_usd": result.usage.cost_usd,
        },
    }
    issues.append(
        ParseIssue(
            code="llm_structuring_used",
            severity="info",
            message=(
                f"Structured with {result.model} ({STRUCTURER_PROMPT_VERSION}); "
                "every field was schema-validated against the source text."
            ),
        )
    )
    return document.model_copy(
        update={
            "canonical": merged,
            "issues": issues,
            "structuring": structuring,
            "parse_fidelity": fidelity,
        }
    )


__all__ = [
    "STRUCTURER_PROMPT_VERSION",
    "STRUCTURER_SYSTEM_PROMPT",
    "apply_llm_structuring",
]
