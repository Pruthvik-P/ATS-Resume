from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep, as_uuid, record_audit
from app.api.v1.helpers import load_inputs
from app.core.config import settings
from app.core.errors import NotFoundError
from app.db.models import Resume, ResumeVersion, ScoreReportRow
from app.schemas.score import ScoreReport, ScoreRequest
from app.services.scoring.engine import build_score_report, grade_for
from app.services.scoring.judge import run_llm_judge

router = APIRouter(tags=["scoring"])


@router.post("/score", response_model=ScoreReport, status_code=status.HTTP_201_CREATED)
async def create_score(
    payload: ScoreRequest, session: SessionDep, user: CurrentUser
) -> ScoreReport:
    resume, jd, document, analysis = await load_inputs(
        session, user, payload.resume_id, payload.jd_id
    )
    report = build_score_report(
        resume_id=str(resume.id), jd_id=str(jd.id), document=document, analysis=analysis
    )
    judge = await run_llm_judge(document, analysis, report)
    if judge:
        report.judge = judge
        blend = max(0.0, min(1.0, settings.llm_judge_blend_weight))
        if blend:
            ceiling = min((cap.cap for cap in report.caps), default=100.0)
            adjusted = min(
                ceiling, report.overall_score + float(judge["adjustment"]) * blend
            )
            report.overall_score = round(max(0.0, adjusted), 1)
            report.grade = grade_for(report.overall_score)
        report.model_versions["judge"] = f"{judge['provider']}:{judge['model']}"
        report.model_versions["judge_prompt"] = str(judge["prompt_version"])

    latest_version = await session.scalar(
        select(ResumeVersion)
        .where(ResumeVersion.resume_id == resume.id)
        .order_by(ResumeVersion.version.desc())
        .limit(1)
    )

    row = ScoreReportRow(
        resume_id=resume.id,
        jd_id=jd.id,
        resume_version_id=latest_version.id if latest_version is not None else None,
        overall=report.overall_score,
        raw_score=report.raw_score,
        grade=report.grade,
        breakdown=report.breakdown.model_dump(mode="json"),
        report_json=report.model_dump(mode="json"),
        parse_fidelity_json=report.parse_fidelity,
        model_versions=report.model_versions,
    )
    session.add(row)
    await session.flush()
    report.id = str(row.id)
    row.report_json = report.model_dump(mode="json")

    if latest_version is not None:
        latest_version.score_id = row.id

    await record_audit(
        session,
        user_id=user.id,
        action="score.created",
        resource="score",
        resource_id=str(row.id),
        meta={"overall": report.overall_score, "resume_id": str(resume.id)},
    )
    await session.commit()
    return report


@router.get("/scores/{score_id}", response_model=ScoreReport)
async def get_score(score_id: str, session: SessionDep, user: CurrentUser) -> ScoreReport:
    row = await session.get(ScoreReportRow, as_uuid(score_id, "score"))
    if not row:
        raise NotFoundError("score", score_id)
    resume = await session.get(Resume, row.resume_id)
    if not resume or resume.user_id != user.id:
        raise NotFoundError("score", score_id)
    return ScoreReport.model_validate(row.report_json)


@router.get("/resumes/{resume_id}/scores", response_model=list[ScoreReport])
async def list_scores(
    resume_id: str, session: SessionDep, user: CurrentUser
) -> list[ScoreReport]:
    resume = await session.get(Resume, as_uuid(resume_id, "resume"))
    if not resume or resume.user_id != user.id or resume.deleted_at is not None:
        raise NotFoundError("resume", resume_id)
    rows = (
        await session.execute(
            select(ScoreReportRow)
            .where(ScoreReportRow.resume_id == resume.id)
            .order_by(ScoreReportRow.created_at.desc())
        )
    ).scalars()
    return [ScoreReport.model_validate(row.report_json) for row in rows]
