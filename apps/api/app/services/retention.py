from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Bullet, Resume, ResumeVersion, ScoreReportRow
from app.schemas.account import PurgeResponse
from app.storage.local import get_storage


async def delete_resumes(
    session: AsyncSession, rows: list[Resume]
) -> PurgeResponse:
    """Explicitly delete every row and file a resume owns.

    SQLite does not enforce foreign keys by default, so relying on ``ON DELETE
    CASCADE`` would leave orphan versions and scores behind. The deletes are
    ordered from leaves to roots and work identically on SQLite and Postgres.
    """

    if not rows:
        return PurgeResponse()

    resume_ids = [row.id for row in rows]
    versions = list(
        (
            await session.execute(
                select(ResumeVersion).where(ResumeVersion.resume_id.in_(resume_ids))
            )
        ).scalars()
    )
    version_ids = [version.id for version in versions]

    keys: set[str] = set()
    for row in rows:
        keys.update(key for key in (row.raw_file_url, row.tex_url) if key)
    for version in versions:
        keys.update(
            key for key in (version.tex_url, version.pdf_url, version.snapshot_url) if key
        )

    if version_ids:
        await session.execute(
            delete(Bullet).where(Bullet.resume_version_id.in_(version_ids))
        )
    scores = await session.execute(
        delete(ScoreReportRow).where(ScoreReportRow.resume_id.in_(resume_ids))
    )
    if version_ids:
        await session.execute(
            delete(ResumeVersion).where(ResumeVersion.id.in_(version_ids))
        )
    resumes = await session.execute(delete(Resume).where(Resume.id.in_(resume_ids)))

    storage = get_storage()
    for key in keys:
        await storage.delete(key)

    return PurgeResponse(
        resumes_deleted=resumes.rowcount or 0,
        versions_deleted=len(version_ids),
        scores_deleted=scores.rowcount or 0,
        storage_objects_deleted=len(keys),
    )
