from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, File, Query, UploadFile, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, SessionDep, as_uuid, record_audit
from app.core.config import settings
from app.core.errors import NotFoundError, UploadTooLargeError
from app.core.ratelimit import enforce_rate_limit
from app.db.models import Resume, ResumeVersion
from app.schemas.resume import ResumeRead, ResumeSummary, ResumeVersionRead
from app.services.ingest.llm_structurer import apply_llm_structuring
from app.services.ingest.pipeline import ingest_bytes
from app.services.retention import delete_resumes
from app.services.scoring.embedding_store import store_bullet_embeddings
from app.storage.local import get_storage

router = APIRouter(prefix="/resumes", tags=["resumes"])


def _safe_name(filename: str) -> str:
    name = Path(filename).name
    cleaned = "".join(char if char.isalnum() or char in "._-" else "_" for char in name)
    return cleaned[-120:] or "resume"


@router.post("", response_model=ResumeRead, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    session: SessionDep,
    user: CurrentUser,
    file: UploadFile = File(...),
) -> ResumeRead:
    if settings.rate_limit_uploads_per_minute:
        enforce_rate_limit(
            f"upload:{user.id}",
            settings.rate_limit_uploads_per_minute,
            60,
        )

    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise UploadTooLargeError(settings.max_upload_bytes)
    if not data:
        from app.core.errors import AppError

        raise AppError("empty_upload", "The uploaded file is empty.")

    filename = file.filename or "resume"
    result = await asyncio.to_thread(ingest_bytes, filename, file.content_type, data)
    result.document = await apply_llm_structuring(result.document, result.raw_text)

    resume = Resume(
        user_id=user.id,
        filename=filename,
        source_format=result.document.format,
        canonical_json=result.document.model_dump(mode="json"),
        version=1,
    )
    session.add(resume)
    await session.flush()

    storage = get_storage()
    key = f"resumes/{resume.id}/{_safe_name(filename)}"
    await storage.save(key, data)
    resume.raw_file_url = key
    if result.document.format in {"tex", "zip"}:
        resume.tex_url = key

    version = ResumeVersion(
        resume_id=resume.id,
        version=1,
        tex_url=resume.tex_url,
        change_log_json=[
            {
                "type": "upload",
                "format": result.document.format,
                "source_artifact": key,
                "at": datetime.now(UTC).isoformat(),
            }
        ],
    )
    session.add(version)
    await session.flush()
    await store_bullet_embeddings(session, version.id, result.document.canonical)

    snapshot_key = f"resumes/{resume.id}/versions/{version.id}/rev-1.json"
    snapshot_bytes = json.dumps(
        result.document.model_dump(mode="json"), indent=2, sort_keys=True, default=str
    ).encode("utf-8")
    await storage.save(snapshot_key, snapshot_bytes)
    version.snapshot_url = snapshot_key

    await record_audit(
        session,
        user_id=user.id,
        action="resume.uploaded",
        resource="resume",
        resource_id=str(resume.id),
        meta={"format": result.document.format, "bytes": len(data)},
    )
    await session.commit()
    await session.refresh(resume)
    return ResumeRead.from_orm_row(resume)


@router.get("", response_model=dict)
async def list_resumes(
    session: SessionDep,
    user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    base = select(Resume).where(Resume.user_id == user.id, Resume.deleted_at.is_(None))
    total = await session.scalar(
        select(func.count()).select_from(base.subquery())
    )
    rows = (
        await session.execute(
            base.order_by(Resume.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars()
    items = []
    for row in rows:
        canonical = (row.canonical_json or {}).get("canonical", {})
        name = (canonical.get("basics") or {}).get("name")
        items.append(
            ResumeSummary(
                id=str(row.id),
                filename=row.filename,
                source_format=row.source_format,  # type: ignore[arg-type]
                name=name,
                created_at=row.created_at,
            ).model_dump(mode="json")
        )
    return {"total": int(total or 0), "limit": limit, "offset": offset, "items": items}


@router.get("/{resume_id}", response_model=ResumeRead)
async def get_resume(resume_id: str, session: SessionDep, user: CurrentUser) -> ResumeRead:
    row = await session.get(Resume, as_uuid(resume_id, "resume"))
    if not row or row.user_id != user.id or row.deleted_at is not None:
        raise NotFoundError("resume", resume_id)
    return ResumeRead.from_orm_row(row)


@router.get("/{resume_id}/versions", response_model=list[ResumeVersionRead])
async def list_versions(
    resume_id: str, session: SessionDep, user: CurrentUser
) -> list[ResumeVersionRead]:
    row = await session.get(Resume, as_uuid(resume_id, "resume"))
    if not row or row.user_id != user.id or row.deleted_at is not None:
        raise NotFoundError("resume", resume_id)
    versions = (
        await session.execute(
            select(ResumeVersion)
            .where(ResumeVersion.resume_id == row.id)
            .order_by(ResumeVersion.version.desc())
        )
    ).scalars()
    return [
        ResumeVersionRead(
            id=str(version.id),
            resume_id=str(version.resume_id),
            version=version.version,
            parent_version_id=str(version.parent_version_id) if version.parent_version_id else None,
            tex_url=version.tex_url,
            pdf_url=version.pdf_url,
            snapshot_url=version.snapshot_url,
            change_log=version.change_log_json or [],
            score_id=str(version.score_id) if version.score_id else None,
            created_at=version.created_at,
        )
        for version in versions
    ]


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume(resume_id: str, session: SessionDep, user: CurrentUser) -> None:
    row = await session.get(Resume, as_uuid(resume_id, "resume"))
    if not row or row.user_id != user.id or row.deleted_at is not None:
        raise NotFoundError("resume", resume_id)

    await delete_resumes(session, [row])
    await record_audit(
        session,
        user_id=user.id,
        action="resume.deleted",
        resource="resume",
        resource_id=str(row.id),
    )
    await session.commit()
