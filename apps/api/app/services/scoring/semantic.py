from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import settings
from app.schemas.jd import JDAnalysis
from app.schemas.resume import Resume, iter_evidence_bullets
from app.services.scoring.bm25 import BM25
from app.services.scoring.embedding import embedding_bands, similarity
from app.services.scoring.rerank import Reranker, blend_rerank, get_reranker

# Calibration is supplied by the active embedder. Trained models use a higher
# band than the hashed-ngram fallback.
_LOW = 0.12
_HIGH = 0.42


@dataclass
class SemanticResult:
    score: float
    requirement_matches: list[dict[str, object]] = field(default_factory=list)
    unmatched_requirements: list[str] = field(default_factory=list)


def _scale(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return max(0.0, min(100.0, (value - low) / (high - low) * 100))


def _rerank_candidates(
    reranker: Reranker,
    requirement: str,
    bullets: list,
    embedding_scores: list[float],
    weight: float,
) -> tuple[list[float], list[float]]:
    order = sorted(
        range(len(bullets)), key=lambda index: embedding_scores[index], reverse=True
    )[:8]
    raw = reranker.score(requirement, [bullets[index].text for index in order])
    combined = list(embedding_scores)
    blended = blend_rerank([embedding_scores[index] for index in order], raw, weight)
    for index, value in zip(order, blended, strict=False):
        combined[index] = value
    return combined, raw


def score_semantics(
    resume: Resume,
    analysis: JDAnalysis,
    *,
    reranker: Reranker | None = None,
) -> tuple[SemanticResult, dict[str, object]]:
    low, high, embedding_name = embedding_bands()
    active_reranker = reranker if reranker is not None else get_reranker()
    rerank_weight = max(0.0, min(1.0, settings.reranker_weight))
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
            "calibration": {"low": low, "high": high, "embedding": embedding_name},
        }

    bm25_weight = max(0.0, min(1.0, settings.bm25_weight))
    bm25_index = (
        BM25([bullet.text for bullet in bullets]) if bm25_weight > 0 else None
    )
    result = SemanticResult(score=0.0)
    total = 0.0
    for requirement in requirements:
        bm25_scores = (
            bm25_index.normalized_scores(requirement) if bm25_index else []
        )
        embedding_scores = [similarity(requirement, bullet.text) for bullet in bullets]
        candidate_scores = embedding_scores
        rerank_scores: list[float] = []
        if active_reranker is not None:
            candidate_scores, rerank_scores = _rerank_candidates(
                active_reranker,
                requirement,
                bullets,
                embedding_scores,
                rerank_weight,
            )
        best_similarity = 0.0
        best_text = ""
        best_id = ""
        for index, bullet in enumerate(bullets):
            value = candidate_scores[index]
            if bm25_scores:
                value = (1 - bm25_weight) * value + bm25_weight * bm25_scores[index]
            if value > best_similarity:
                best_similarity = value
                best_text = bullet.text
                best_id = bullet.id
        total += best_similarity
        scaled = _scale(best_similarity, low, high)
        entry = {
            "requirement": requirement[:240],
            "best_bullet": best_id,
            "similarity": round(best_similarity, 3),
            "scaled": round(scaled, 1),
            "evidence": best_text[:200],
        }
        if rerank_scores:
            entry["rerank_score"] = round(max(rerank_scores), 3)
        result.requirement_matches.append(entry)
        if scaled < 35:
            result.unmatched_requirements.append(requirement[:160])

    mean_similarity = total / len(requirements)
    result.score = round(_scale(mean_similarity, low, high), 2)
    result.requirement_matches.sort(key=lambda item: float(item["similarity"]), reverse=True)
    return result, {
        "requirements": len(requirements),
        "bullets_compared": len(bullets),
        "mean_similarity": round(mean_similarity, 4),
        "calibration": {"low": low, "high": high, "embedding": embedding_name},
        "bm25_weight": bm25_weight,
        "reranker": active_reranker.name if active_reranker is not None else None,
        "reranker_model": (
            active_reranker.model_name if active_reranker is not None else None
        ),
        "reranker_weight": rerank_weight,
        "top_matches": result.requirement_matches[:5],
        "unmatched_requirements": result.unmatched_requirements[:8],
    }
