from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep, as_uuid, record_audit
from app.api.v1.helpers import load_inputs
from app.core.errors import AppError, NotFoundError
from app.db.models import Job, ResumeVersion
from app.db.session import SessionLocal
from app.schemas.jobs import (
    ChangeDecisionRequest,
    ChangeDecisionResponse,
    JobRead,
    OptimiseRequest,
    OptimiseResult,
)
from app.services.jobs import run_optimise_job
from app.services.optimiser import apply_proposals
from app.services.scoring.engine import build_score_report

router = APIRouter(tags=["jobs"])

TERMINAL = {"succeeded", "failed", "cancelled"}


def job_read(job: Job) -> JobRead:
    return JobRead(
        id=str(job.id),
        type=job.type,  # type: ignore[arg-type]
        status=job.status,  # type: ignore[arg-type]
        progress=job.progress,
        message=job.message,
        result=job.result,
        error=job.error,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


@router.post("/optimise", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
async def create_optimise(
    payload: OptimiseRequest,
    background: BackgroundTasks,
    session: SessionDep,
    user: CurrentUser,
) -> JobRead:
    resume, jd, _document, _analysis = await load_inputs(
        session, user, payload.resume_id, payload.jd_id
    )
    options = payload.options
    target = payload.target_score or options.target_score

    job = Job(
        user_id=user.id,
        type="optimise",
        status="queued",
        progress=0,
        message="Queued",
        payload={
            "resume_id": str(resume.id),
            "jd_id": str(jd.id),
            "target_score": target,
            "options": options.model_dump(),
        },
    )
    session.add(job)
    await session.flush()
    await record_audit(
        session,
        user_id=user.id,
        action="optimise.queued",
        resource="job",
        resource_id=str(job.id),
        meta={"resume_id": str(resume.id), "jd_id": str(jd.id)},
    )
    await session.commit()
    await session.refresh(job)
    background.add_task(run_optimise_job, str(job.id))
    return job_read(job)


@router.get("/jobs/{job_id}", response_model=JobRead)
async def get_job(job_id: str, session: SessionDep, user: CurrentUser) -> JobRead:
    job = await session.get(Job, as_uuid(job_id, "job"))
    if not job or job.user_id != user.id:
        raise NotFoundError("job", job_id)
    return job_read(job)


@router.get("/jobs/{job_id}/events")
async def job_events(
    job_id: str, request: Request, session: SessionDep, user: CurrentUser
) -> StreamingResponse:
    job_uuid = as_uuid(job_id, "job")
    job = await session.get(Job, job_uuid)
    if not job or job.user_id != user.id:
        raise NotFoundError("job", job_id)

    async def stream():
        last_payload: str | None = None
        started = time.monotonic()
        while True:
            async with SessionLocal() as event_session:
                current = await event_session.get(Job, job_uuid)
                if current is None:
                    yield "event: error\ndata: {\"message\":\"job disappeared\"}\n\n"
                    return
                event_name = "progress" if current.status == "running" else (
                    "done" if current.status in TERMINAL else "status"
                )
                payload = json.dumps(
                    {
                        "job_id": str(current.id),
                        "status": current.status,
                        "progress": current.progress,
                        "message": current.message,
                        "error": current.error,
                        "result": current.result if current.status in TERMINAL else None,
                        "at": datetime.now(UTC).isoformat(),
                    },
                    default=str,
                )
                finished = current.status in TERMINAL
            if payload != last_payload:
                yield f"event: {event_name}\ndata: {payload}\n\n"
                last_payload = payload
            if finished:
                return
            if await request.is_disconnected():
                return
            if time.monotonic() - started > 300:
                yield "event: error\ndata: {\"message\":\"stream timeout\"}\n\n"
                return
            await asyncio.sleep(0.75)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/jobs/{job_id}/changes/{change_id}",
    response_model=ChangeDecisionResponse,
)
async def decide_change(
    job_id: str,
    change_id: str,
    payload: ChangeDecisionRequest,
    session: SessionDep,
    user: CurrentUser,
) -> ChangeDecisionResponse:
    job = await session.get(Job, as_uuid(job_id, "job"))
    if not job or job.user_id != user.id:
        raise NotFoundError("job", job_id)
    if job.status != "succeeded" or not job.result:
        raise AppError(
            "job_not_ready",
            "The optimisation job has not produced proposals yet.",
            status_code=409,
        )

    result = OptimiseResult.model_validate(job.result)
    proposal = next((item for item in result.proposals if item.id == change_id), None)
    if proposal is None:
        raise NotFoundError("change", change_id)
    proposal.status = payload.status

    resume, jd, document, analysis = await load_inputs(
        session, user, str(result.resume_id), str(result.jd_id)
    )
    updated_document = apply_proposals(document, result.proposals, analysis)
    refreshed = build_score_report(
        resume_id=str(resume.id),
        jd_id=str(jd.id),
        document=updated_document,
        analysis=analysis,
    )
    result.score_after_accepted = refreshed.overall_score
    job.result = result.model_dump(mode="json")

    if any(item.status == "accepted" for item in result.proposals):
        latest = await session.scalar(
            select(ResumeVersion)
            .where(ResumeVersion.resume_id == resume.id)
            .order_by(ResumeVersion.version.desc())
            .limit(1)
        )
        if latest is not None:
            latest.change_log_json = [
                {
                    "change_id": item.id,
                    "kind": item.kind,
                    "status": item.status,
                    "target": item.target_ref,
                }
                for item in result.proposals
                if item.status != "pending"
            ]

    await record_audit(
        session,
        user_id=user.id,
        action=f"change.{payload.status}",
        resource="change",
        resource_id=change_id,
        meta={"job_id": str(job.id)},
    )
    await session.commit()
    return ChangeDecisionResponse(
        job_id=str(job.id), change=proposal, score_after_accepted=result.score_after_accepted
    )
