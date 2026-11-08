from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings
from app.schemas.common import HealthResponse, MetaResponse

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
        embedding_model="hashed-ngram-v1",
        llm_provider=settings.llm_provider,
    )
