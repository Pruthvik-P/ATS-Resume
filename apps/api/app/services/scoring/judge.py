"""Optional constrained LLM judge for the hybrid score.

The deterministic score remains authoritative. The judge can only:
* return an advisory score in [0, 100];
* return an adjustment clamped to [-5, +5];
* explain strengths and gaps.

Nothing the model returns is trusted unchecked: ranges are clamped, text is
truncated, and the report records the exact provider/model/prompt version.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.schemas.jd import JDAnalysis
from app.schemas.resume import ResumeDocument
from app.schemas.score import ScoreReport
from app.services.llm.base import LLMProvider, get_llm_provider

JUDGE_PROMPT_VERSION = "judge-v1"

JUDGE_SYSTEM_PROMPT = """\
You are an ATS reviewer. Judge how well the resume demonstrates the job's
must-have requirements. Use only evidence present in the resume.
Return JSON:
{"score": 0-100, "confidence": 0-1, "adjustment": -5..5,
 "strengths": ["..."], "gaps": ["..."], "rationale": "one paragraph"}
Rules:
1. Missing must-have evidence is a gap; do not assume unstated skills.
2. Do not reward keyword stuffing, hidden text, or unsupported metrics.
3. `adjustment` is a small correction to the deterministic score, not a rewrite.
"""


def _clamp(value: Any, low: float, high: float, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, parsed))


def _string_list(value: Any, limit: int = 6) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item)[:300] for item in value if str(item).strip()][:limit]


async def run_llm_judge(
    document: ResumeDocument,
    analysis: JDAnalysis,
    report: ScoreReport,
    *,
    provider: LLMProvider | None = None,
) -> dict[str, Any] | None:
    if not settings.llm_judge_enabled:
        return None
    provider = provider or get_llm_provider()
    if provider.name == "stub":
        return None

    resume = document.canonical
    must = ", ".join(item.canonical for item in analysis.must_have[:20]) or "none detected"
    responsibilities = " | ".join(analysis.responsibilities[:8])
    bullets = [
        *[highlight for work in resume.work for highlight in work.highlights[:6]],
        *[highlight for project in resume.projects for highlight in project.highlights[:4]],
    ][:30]
    bullet_text = "\n".join(f"- {bullet}" for bullet in bullets)
    user_prompt = (
        f"<must_have>{must}</must_have>\n"
        f"<responsibilities>{responsibilities}</responsibilities>\n"
        f"<deterministic_score>{report.overall_score}</deterministic_score>\n"
        f"<resume_summary>{resume.basics.summary or ''}</resume_summary>\n"
        f"<bullets>{bullet_text}</bullets>"
    )
    result = await provider.complete_result(
        system=JUDGE_SYSTEM_PROMPT,
        user=user_prompt,
        schema_name="score_judge",
        prompt_version=JUDGE_PROMPT_VERSION,
    )
    if not result.data:
        return None

    data = result.data
    advisory = _clamp(data.get("score"), 0.0, 100.0, report.overall_score)
    adjustment = _clamp(data.get("adjustment"), -5.0, 5.0, 0.0)
    confidence = _clamp(data.get("confidence"), 0.0, 1.0, 0.5)
    return {
        "advisory_score": round(advisory, 1),
        "adjustment": round(adjustment, 1),
        "confidence": round(confidence, 2),
        "strengths": _string_list(data.get("strengths")),
        "gaps": _string_list(data.get("gaps")),
        "rationale": str(data.get("rationale") or "")[:1200],
        "provider": result.provider,
        "model": result.model,
        "prompt_version": JUDGE_PROMPT_VERSION,
        "usage": {
            "prompt_tokens": result.usage.prompt_tokens,
            "completion_tokens": result.usage.completion_tokens,
            "cost_usd": result.usage.cost_usd,
        },
    }


__all__ = ["JUDGE_PROMPT_VERSION", "JUDGE_SYSTEM_PROMPT", "run_llm_judge"]
