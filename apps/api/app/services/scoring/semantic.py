from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.jd import JDAnalysis
from app.schemas.resume import Resume, iter_evidence_bullets
from app.services.scoring.embedding import similarity

# Calibration for the hashed-ngram fallback. Trained embeddings use a 0.82
# threshold per the architecture doc; this fallback needs a lower band.
_LOW = 0.12
_HIGH = 0.42


@dataclass
class SemanticResult:
    score: float
    requirement_matches: list[dict[str, object]] = field(default_factory=list)
    unmatched_requirements: list[str] = field(default_factory=list)


def _scale(value: float) -> float:
    return max(0.0, min(100.0, (value - _LOW) / (_HIGH - _LOW) * 100))


def score_semantics(resume: Resume, analysis: JDAnalysis) -> tuple[SemanticResult, dict[str, object]]:
    requirements = list(analysis.responsibilities[:8])
    if not requirements:
        requirements = [
            f"{requirement.canonical} experience"
            for requirement in [*analysis.must_have, *analysis.nice_to_have][:10]
        ]

    bullets = iter_evidence_bullets(resume)
    if not requirements or not bullets:
        return SemanticResult(score=0.0), {
            "requirements": len(requirements),
            "bullets": len(bullets),
            "note": "No requirements or bullets to compare.",
        }

    result = SemanticResult(score=0.0)
    total = 0.0
    for requirement in requirements:
        best_similarity = 0.0
        best_text = ""
        best_id = ""
        for bullet in bullets:
            value = similarity(requirement, bullet.text)
            if value > best_similarity:
                best_similarity = value
                best_text = bullet.text
                best_id = bullet.id
        total += best_similarity
        scaled = _scale(best_similarity)
        entry = {
            "requirement": requirement[:240],
            "best_bullet": best_id,
            "similarity": round(best_similarity, 3),
            "scaled": round(scaled, 1),
            "evidence": best_text[:200],
        }
        result.requirement_matches.append(entry)
        if scaled < 35:
            result.unmatched_requirements.append(requirement[:160])

    mean_similarity = total / len(requirements)
    result.score = round(_scale(mean_similarity), 2)
    result.requirement_matches.sort(key=lambda item: float(item["similarity"]), reverse=True)
    return result, {
        "requirements": len(requirements),
        "bullets_compared": len(bullets),
        "mean_similarity": round(mean_similarity, 4),
        "calibration": {"low": _LOW, "high": _HIGH, "embedding": "hashed-ngram-v1"},
        "top_matches": result.requirement_matches[:5],
        "unmatched_requirements": result.unmatched_requirements[:8],
    }
