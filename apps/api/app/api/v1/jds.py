from __future__ import annotations

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, SessionDep, as_uuid, record_audit
from app.core.config import settings
from app.core.errors import AppError, NotFoundError
from app.db.models import JobDescription
from app.schemas.jd import JDAnalysis, JDAnalysisResponse, JDCreateRequest
from app.services.fetch import fetch_jd_from_url
from app.services.jd_cache import analyse_jd_cached
from app.services.scoring.embedding_store import store_jd_embedding

router = APIRouter(prefix="/jds", tags=["job descriptions"])


@router.post("", response_model=JDAnalysisResponse, status_code=status.HTTP_201_CREATED)
async def create_jd(
    payload: JDCreateRequest, session: SessionDep, user: CurrentUser
) -> JDAnalysisResponse:
    if payload.text and payload.url:
        raise AppError("jd_ambiguous", "Provide either text or url, not both.")
    if not payload.text and not payload.url:
        raise AppError("jd_missing", "Provide job description text or a URL.")

    source_url = str(payload.url) if payload.url else None
    raw_text = payload.text or ""
    warnings: list[str] = []

    if payload.url:
        raw_text = await fetch_jd_from_url(str(payload.url))
        warnings.append("Text was fetched from the URL. Verify that the relevant JD content was captured.")
    if len(raw_text) > settings.max_jd_chars:
        raise AppError(
            "jd_too_large",
            f"Job description exceeds the {settings.max_jd_chars} character limit.",
            status_code=413,
        )

    analysis, analysis_warnings, cache_hit = await analyse_jd_cached(
        raw_text, title=payload.title, company=payload.company
    )
    warnings.extend(analysis_warnings)
    if cache_hit:
        warnings.append("Served from the JD analysis cache.")

    row = JobDescription(
        user_id=user.id,
        source_url=source_url,
        raw_text=raw_text,
        analysis_json=analysis.model_dump(mode="json"),
    )
    session.add(row)
    await session.flush()
    await store_jd_embedding(session, row)
    await record_audit(
        session,
        user_id=user.id,
        action="jd.created",
        resource="jd",
        resource_id=str(row.id),
        meta={"source_url": source_url, "chars": len(raw_text)},
    )
    await session.commit()
    await session.refresh(row)
    return JDAnalysisResponse(
        id=str(row.id), analysis=analysis, warnings=warnings, created_at=row.created_at
    )


@router.get("/{jd_id}", response_model=JDAnalysisResponse)
async def get_jd(jd_id: str, session: SessionDep, user: CurrentUser) -> JDAnalysisResponse:
    row = await session.get(JobDescription, as_uuid(jd_id, "jd"))
    if not row or row.user_id != user.id:
        raise NotFoundError("jd", jd_id)
    return JDAnalysisResponse(
        id=str(row.id),
        analysis=JDAnalysis.model_validate(row.analysis_json),
        warnings=[],
        created_at=row.created_at,
    )


@router.get("", response_model=dict)
async def list_jds(
    session: SessionDep,
    user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    base = select(JobDescription).where(JobDescription.user_id == user.id)
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    rows = (
        await session.execute(
            base.order_by(JobDescription.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars()
    items = []
    for row in rows:
        analysis = row.analysis_json or {}
        items.append(
            {
                "id": str(row.id),
                "title": analysis.get("title"),
                "company": analysis.get("company"),
                "source_url": row.source_url,
                "created_at": row.created_at.isoformat(),
            }
        )
    return {"total": int(total or 0), "limit": limit, "offset": offset, "items": items}
