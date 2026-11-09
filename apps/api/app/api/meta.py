from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings
from app.schemas.common import HealthResponse, MetaResponse
from app.services.scoring.embedding import active_embedding_model
from app.services.scoring.rerank import reranker_version
from app.taxonomy.skills import taxonomy_version

router = APIRouter(tags=["meta"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        version=settings.app_version,
        environment=settings.environment,
        llm_provider=settings.llm_provider,
    )


@router.get("/meta", response_model=MetaResponse)
async def meta() -> MetaResponse:
    return MetaResponse(
        scoring_weights=settings.scoring_weights.as_dict(),
        caps={
            "missing_must_have": settings.must_have_cap,
            "parse_fidelity_floor": settings.parse_fidelity_floor,
            "parse_fidelity": settings.parse_fidelity_cap,
            "keyword_stuffing": settings.keyword_stuffing_penalty,
        },
        match_tiers={"exact": 1.0, "alias": 0.95, "semantic": 0.6},
        embedding_model=active_embedding_model(),
        llm_provider=settings.llm_provider,
        latex_compile={
            "enabled": settings.latex_compile_enabled,
            "engine": settings.latex_compile_engine,
            "worker_configured": bool(settings.latex_worker_url),
            "ocr_enabled": settings.ocr_enabled,
        },
        ai={
            "llm_structuring_enabled": settings.llm_structuring_enabled,
            "llm_judge_enabled": settings.llm_judge_enabled,
            "embedding_provider": settings.embedding_provider,
            "embedding_store_backend": settings.embedding_store_backend,
            "reranker": reranker_version(),
            "bm25_weight": settings.bm25_weight,
            "fuzzy_matching": settings.fuzzy_matching_enabled,
            "spacy_enabled": settings.spacy_enabled,
            "taxonomy_version": taxonomy_version(),
            "jd_cache_backend": settings.jd_cache_backend,
            "calibration_enabled": settings.calibration_enabled,
            "fairness_redaction_enabled": settings.fairness_redaction_enabled,
        },
    )
