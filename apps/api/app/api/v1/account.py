from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, status
from sqlalchemy import delete, or_, select

from app.api.deps import CurrentUser, SessionDep, record_audit
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import AuditLog, Fact, Job, JobDescription, Resume, ScoreReportRow
from app.schemas.account import DeleteAllResponse, PurgeRequest, PurgeResponse
from app.services.retention import delete_resumes

router = APIRouter(prefix="/account", tags=["account"])


@router.delete("", response_model=DeleteAllResponse, status_code=status.HTTP_200_OK)
async def delete_all(
    session: SessionDep, user: CurrentUser
) -> DeleteAllResponse:
    """Delete all resumes, JDs, scores, facts, jobs, and stored files for a user."""

    resumes = list(
        (await session.execute(select(Resume).where(Resume.user_id == user.id))).scalars()
    )
    resume_ids = [row.id for row in resumes]
    deleted = await delete_resumes(session, resumes)

    jd_ids = list(
        (
            await session.execute(
                select(JobDescription.id).where(JobDescription.user_id == user.id)
            )
        ).scalars()
    )
    if jd_ids:
        # Catch orphan scores that reference a JD but not a live resume row.
        scores = await session.execute(
            delete(ScoreReportRow).where(
                or_(
                    ScoreReportRow.jd_id.in_(jd_ids),
                    ScoreReportRow.resume_id.in_(resume_ids),
                )
            )
        )
        deleted.scores_deleted += scores.rowcount or 0
        jds = await session.execute(
            delete(JobDescription).where(JobDescription.id.in_(jd_ids))
        )
        deleted.jds_deleted = jds.rowcount or 0

    facts = await session.execute(delete(Fact).where(Fact.user_id == user.id))
    deleted.facts_deleted = facts.rowcount or 0
    jobs = await session.execute(delete(Job).where(Job.user_id == user.id))
    deleted.jobs_deleted = jobs.rowcount or 0
    audits = await session.execute(delete(AuditLog).where(AuditLog.user_id == user.id))
    deleted.audit_rows_deleted = audits.rowcount or 0

    # Keep one tombstone audit row so the deletion itself is accountable.
    await record_audit(
        session,
        user_id=user.id,
        action="account.deleted",
        resource="user",
        resource_id=str(user.id),
        meta={"counts": deleted.model_dump()},
    )
    await session.commit()
    return DeleteAllResponse(deleted=deleted, audit_retained=True)


@router.post("/purge", response_model=PurgeResponse)
async def purge(
    payload: PurgeRequest, session: SessionDep, user: CurrentUser
) -> PurgeResponse:
    """Apply the retention window. A null window means keep until asked."""

    days = payload.older_than_days or settings.retention_days
    if not days:
        raise AppError(
            "retention_not_configured",
            "Set ATS_RETENTION_DAYS or provide older_than_days to purge.",
            status_code=400,
        )

    cutoff = datetime.now(UTC) - timedelta(days=days)
    rows = list(
        (
            await session.execute(
                select(Resume).where(
                    Resume.user_id == user.id,
                    Resume.created_at < cutoff,
                )
            )
        ).scalars()
    )
    deleted = await delete_resumes(session, rows)

    jobs = await session.execute(
        delete(Job).where(Job.user_id == user.id, Job.created_at < cutoff)
    )
    deleted.jobs_deleted = jobs.rowcount or 0

    await record_audit(
        session,
        user_id=user.id,
        action="account.purged",
        resource="user",
        resource_id=str(user.id),
        meta={"older_than_days": days, "counts": deleted.model_dump()},
    )
    await session.commit()
    return deleted
