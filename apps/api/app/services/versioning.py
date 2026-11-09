"""Model/prompt version manifests.

Every score and optimisation result records enough versions to explain which
deterministic rules, embedding model, reranker, taxonomy, structuring prompt,
and LLM/provider produced it. This is the replay contract; changing a manifest
is a scoring-version change.
"""

from __future__ import annotations

from app.core.config import settings
from app.schemas.jd import JDAnalysis
from app.schemas.resume import ResumeDocument
from app.services.scoring.embedding import active_embedding_model
from app.services.scoring.rerank import reranker_version
from app.taxonomy.skills import load_configured_taxonomies, taxonomy_version

SCORING_ENGINE_VERSION = "scoring-v2"


def scoring_model_versions(
    document: ResumeDocument,
    analysis: JDAnalysis,
    *,
    calibration: str | None = None,
) -> dict[str, str]:
    provider = settings.llm_provider
    return {
        "scoring": SCORING_ENGINE_VERSION,
        "embedding": active_embedding_model(),
        "reranker": reranker_version(),
        "taxonomy": taxonomy_version(),
        "structuring": document.structuring.model,
        "structuring_prompt": document.structuring.prompt_version,
        "jd_analyser": analysis.analyser_version,
        "prompt": settings.prompt_version if provider != "stub" else "n/a",
        "llm_provider": provider,
        "llm_model": settings.llm_model if provider != "stub" else "n/a",
        "fairness": (
            "redaction-v1" if settings.fairness_redaction_enabled else "disabled"
        ),
        "calibration": calibration or ("disabled" if not settings.calibration_enabled else "configured"),
        "bm25_weight": f"{settings.bm25_weight:.2f}",
        "reranker_weight": f"{settings.reranker_weight:.2f}",
    }


def optimiser_model_versions(
    *,
    provider_name: str,
    prompt_version: str,
    llm_model: str,
) -> dict[str, str]:
    load_configured_taxonomies()
    return {
        "scoring": SCORING_ENGINE_VERSION,
        "optimiser": "deterministic-optimiser-v1",
        "embedding": active_embedding_model(),
        "reranker": reranker_version(),
        "taxonomy": taxonomy_version(),
        "prompt": prompt_version if provider_name != "stub" else "n/a",
        "llm_provider": provider_name,
        "llm_model": llm_model if provider_name != "stub" else "n/a",
        "fairness": (
            "redaction-v1" if settings.fairness_redaction_enabled else "disabled"
        ),
    }


__all__ = ["SCORING_ENGINE_VERSION", "optimiser_model_versions", "scoring_model_versions"]
