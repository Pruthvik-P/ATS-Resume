from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep, as_uuid
from app.core.errors import NotFoundError
from app.db.models import Resume
from app.schemas.search import (
    SimilarBulletItem,
    SimilarBulletsRequest,
    SimilarBulletsResponse,
)
from app.services.scoring.embedding_store import similar_bullets

router = APIRouter(prefix="/search", tags=["search"])


@router.post("/similar-bullets", response_model=SimilarBulletsResponse)
async def search_similar_bullets(
    payload: SimilarBulletsRequest,
    session: SessionDep,
    user: CurrentUser,
) -> SimilarBulletsResponse:
    resume_id = None
    if payload.resume_id:
        resume_id = as_uuid(payload.resume_id, "resume")
        resume = await session.get(Resume, resume_id)
        if not resume or resume.user_id != user.id or resume.deleted_at is not None:
            raise NotFoundError("resume", payload.resume_id)

    items, backend = await similar_bullets(
        session,
        user_id=user.id,
        query=payload.query,
        resume_id=resume_id,
        limit=payload.limit,
    )
    return SimilarBulletsResponse(
        backend=backend,
        items=[
            SimilarBulletItem(
                bullet_id=item.bullet_id,
                resume_version_id=item.resume_version_id,
                section=item.section,
                text=item.text,
                similarity=item.similarity,
            )
            for item in items
        ],
    )


__all__ = ["router"]
