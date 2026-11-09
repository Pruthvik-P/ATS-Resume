from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep, as_uuid
from app.core.config import settings
from app.core.errors import AppError, NotFoundError
from app.db.models import JobDescription, Resume
from app.schemas.jd import JDAnalysis
from app.schemas.resume import ResumeDocument
from app.schemas.tailor import TailorRequest, TailorResponse
from app.services.tailoring import TailorInput, tailor_preview

router = APIRouter(tags=["tailoring"])


@router.post("/resumes/{resume_id}/tailor", response_model=TailorResponse)
async def tailor_resume(
    resume_id: str,
    payload: TailorRequest,
    session: SessionDep,
    user: CurrentUser,
) -> TailorResponse:
    resume = await session.get(Resume, as_uuid(resume_id, "resume"))
    if not resume or resume.user_id != user.id or resume.deleted_at is not None:
        raise NotFoundError("resume", resume_id)

    unique_ids = list(dict.fromkeys(payload.jd_ids))
    if len(unique_ids) > settings.multi_jd_max_targets:
        raise AppError(
            "too_many_targets",
            f"At most {settings.multi_jd_max_targets} JDs can be previewed per request.",
            status_code=400,
        )

    targets: list[TailorInput] = []
    for jd_id in unique_ids:
        jd = await session.get(JobDescription, as_uuid(jd_id, "jd"))
        if not jd or jd.user_id != user.id:
            raise NotFoundError("jd", jd_id)
        analysis = JDAnalysis.model_validate(jd.analysis_json)
        targets.append(TailorInput(jd_id=str(jd.id), title=analysis.title, analysis=analysis))

    document = ResumeDocument.model_validate(resume.canonical_json)
    results = await tailor_preview(document, targets, payload.options)
    return TailorResponse(resume_id=str(resume.id), targets=results)


__all__ = ["router"]
