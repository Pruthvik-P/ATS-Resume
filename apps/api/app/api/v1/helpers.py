from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import as_uuid
from app.core.errors import NotFoundError
from app.db.models import JobDescription, Resume, User
from app.schemas.jd import JDAnalysis
from app.schemas.resume import ResumeDocument


async def load_inputs(
    session: AsyncSession, user: User, resume_id: str, jd_id: str
) -> tuple[Resume, JobDescription, ResumeDocument, JDAnalysis]:
    resume = await session.get(Resume, as_uuid(resume_id, "resume"))
    if not resume or resume.user_id != user.id or resume.deleted_at is not None:
        raise NotFoundError("resume", resume_id)
    jd = await session.get(JobDescription, as_uuid(jd_id, "jd"))
    if not jd or jd.user_id != user.id:
        raise NotFoundError("jd", jd_id)
    document = ResumeDocument.model_validate(resume.canonical_json)
    analysis = JDAnalysis.model_validate(jd.analysis_json)
    return resume, jd, document, analysis


__all__ = ["HTTPException", "load_inputs"]
