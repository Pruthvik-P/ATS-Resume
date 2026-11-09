from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Header, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, SessionDep, as_uuid, record_audit
from app.api.v1.helpers import load_inputs
from app.core.config import settings
from app.core.errors import AppError, NotFoundError
from app.core.ratelimit import enforce_rate_limit
from app.db.models import Fact, Job, Resume, ResumeVersion, ScoreReportRow
from app.db.session import SessionLocal
from app.schemas.jobs import (
    ChangeDecisionRequest,
    ChangeDecisionResponse,
    ChangeProposal,
    JobRead,
    OptimiseRequest,
    OptimiseResult,
    ProposalEditRequest,
)
from app.schemas.resume import ResumeDocument
from app.schemas.score import ScoreReport
from app.services.jobs import run_optimise_job
from app.services.latex.compiler import CompileResult, compile_source
from app.services.latex.render import render_resume_tex
from app.services.optimiser import apply_proposals
from app.services.scoring.embedding_store import store_bullet_embeddings
from app.services.scoring.engine import build_score_report
from app.services.verifier import verify_user_edit
from app.storage.local import get_storage

router = APIRouter(tags=["jobs"])

TERMINAL = {"succeeded", "failed", "cancelled"}
EDITABLE_KINDS = {"rewrite_bullet", "placeholder_metric"}


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


async def _load_job_for_update(session: AsyncSession, job_id: str, user: CurrentUser) -> Job:
    """Serialize decisions on the same job.

    PostgreSQL honours ``FOR UPDATE`` so concurrent accept/reject calls queue.
    SQLite ignores the clause but serializes writes anyway. This removes the
    read-modify-write race that could otherwise drop a decision.
    """

    result = await session.execute(
        select(Job).where(Job.id == as_uuid(job_id, "job")).with_for_update()
    )
    job = result.scalar_one_or_none()
    if not job or job.user_id != user.id:
        raise NotFoundError("job", job_id)
    if job.status != "succeeded" or not job.result:
        raise AppError(
            "job_not_ready",
            "The optimisation job has not produced proposals yet.",
            status_code=409,
        )
    return job


def _find_proposal(result: OptimiseResult, change_id: str) -> ChangeProposal:
    proposal = next((item for item in result.proposals if item.id == change_id), None)
    if proposal is None:
        raise NotFoundError("change", change_id)
    return proposal


async def _load_fact_texts(session: AsyncSession, user_id: UUID) -> list[str]:
    rows = (await session.execute(select(Fact).where(Fact.user_id == user_id))).scalars()
    return [row.fact_text for row in rows]


async def _record_edit_fact(
    *,
    session: AsyncSession,
    user_id: UUID,
    job_id: UUID,
    proposal: ChangeProposal,
) -> None:
    """A user-authored edit is a confirmed fact, not model output."""

    fact_text = proposal.proposed.strip()
    if not fact_text:
        return
    existing = await session.scalar(
        select(Fact).where(Fact.user_id == user_id, Fact.fact_text == fact_text)
    )
    if existing is not None:
        return
    session.add(
        Fact(
            user_id=user_id,
            fact_text=fact_text,
            source="user_edit",
            tags=["proposal_edit", f"job:{job_id}", f"change:{proposal.id}"],
            confirmed_at=datetime.now(UTC),
        )
    )
    await session.flush()


async def _apply_user_edit(
    *,
    session: AsyncSession,
    user_id: UUID,
    job_id: UUID,
    proposal: ChangeProposal,
    proposed: str,
) -> None:
    """Validate and persist a user edit, then re-run verification."""

    if proposal.kind not in EDITABLE_KINDS:
        raise AppError(
            "proposal_not_editable",
            "Only bullet rewrites and metric placeholders accept free-text edits.",
            status_code=409,
        )
    if proposal.status == "accepted":
        raise AppError(
            "change_already_accepted",
            "Reject the accepted change before editing it.",
            status_code=409,
        )
    cleaned = proposed.strip()
    if not cleaned:
        raise AppError("empty_edit", "The edited proposal cannot be empty.", status_code=422)

    facts = await _load_fact_texts(session, user_id)
    verification = verify_user_edit(proposal.original, cleaned, facts)
    proposal.proposed = cleaned
    proposal.edited_by_user = True
    proposal.truthfulness = "verified" if verification.verified else "needs_user_input"
    proposal.verification_notes = verification.reasons

    if verification.verified:
        await _record_edit_fact(
            session=session,
            user_id=user_id,
            job_id=job_id,
            proposal=proposal,
        )


async def _find_job_version(
    session: AsyncSession, resume_id: UUID, job_id: UUID
) -> ResumeVersion | None:
    """Return the version a job produced, if any.

    The job id is stamped into the append-only change log, so this works even
    after later versions for the same resume exist.
    """

    versions = list(
        (
            await session.execute(
                select(ResumeVersion)
                .where(ResumeVersion.resume_id == resume_id)
                .order_by(ResumeVersion.version.desc())
            )
        ).scalars()
    )
    return next(
        (
            version
            for version in versions
            if any(
                isinstance(entry, dict) and entry.get("job_id") == str(job_id)
                for entry in (version.change_log_json or [])
            )
        ),
        None,
    )


async def _load_job_base_document(
    session: AsyncSession, resume: Resume, job: Job
) -> ResumeDocument:
    """Load the document a job started from, not the current derived state.

    Reverting an accepted change must re-apply the remaining accepted proposals
    to the pre-job document. The parent version snapshot is that document.
    """

    job_version = await _find_job_version(session, resume.id, job.id)
    if job_version and job_version.parent_version_id:
        parent = await session.get(ResumeVersion, job_version.parent_version_id)
        if parent and parent.snapshot_url:
            raw = await get_storage().read(parent.snapshot_url)
            return ResumeDocument.model_validate_json(raw)
    return ResumeDocument.model_validate(resume.canonical_json)


async def _validate_document_compiles(
    document: ResumeDocument, *, strict: bool = True
) -> CompileResult | None:
    """Validate a candidate resume through the sandboxed compiler.

    Returning ``None`` means compilation is disabled. An ``unavailable``
    worker is not a candidate failure; only real compile errors block a strict
    decision. A successful compile supplies the PDF artifact stored with the
    derived version. The compile call is offloaded so it cannot block the
    event loop.
    """

    if not settings.latex_compile_enabled:
        return None
    result = await asyncio.to_thread(
        compile_source, render_resume_tex(document), "resume.tex"
    )
    if strict and result.status in {"failed", "timeout", "rejected"}:
        raise AppError(
            "compile_failed",
            "The updated resume does not compile in the sandboxed LaTeX worker.",
            status_code=409,
            details={
                "reason": result.reason,
                "engine": result.engine,
                "log": result.log[-4000:],
            },
        )
    return result


def _decision_event(
    *,
    job: Job,
    proposal: ChangeProposal,
    previous_status: str,
    note: str | None,
) -> dict[str, Any]:
    return {
        "type": "change_decision",
        "job_id": str(job.id),
        "change_id": proposal.id,
        "kind": proposal.kind,
        "status": proposal.status,
        "previous_status": previous_status,
        "reverted": previous_status == "accepted" and proposal.status == "rejected",
        "target": proposal.target_ref,
        "original": proposal.original,
        "proposed": proposal.proposed,
        "rationale": proposal.rationale,
        "edited_by_user": proposal.edited_by_user,
        "truthfulness": proposal.truthfulness,
        "verification_notes": proposal.verification_notes,
        "note": note,
        "at": datetime.now(UTC).isoformat(),
    }


async def _persist_accepted_changes(
    *,
    session: AsyncSession,
    job: Job,
    resume: Resume,
    jd_id: UUID,
    document: ResumeDocument,
    result: OptimiseResult,
    refreshed: ScoreReport,
    events: list[dict[str, Any]],
    compiled: CompileResult | None = None,
) -> ResumeVersion | None:
    """Persist accepted edits as a resume version and a real score report.

    A job owns at most one derived version. The change log is append-only: every
    decision, edit, revert, and snapshot is a new event, so the undo history is
    never overwritten.
    """

    accepted = any(proposal.status == "accepted" for proposal in result.proposals)

    versions = list(
        (
            await session.execute(
                select(ResumeVersion)
                .where(ResumeVersion.resume_id == resume.id)
                .order_by(ResumeVersion.version.desc())
            )
        ).scalars()
    )
    job_version = next(
        (
            version
            for version in versions
            if any(
                isinstance(entry, dict) and entry.get("job_id") == str(job.id)
                for entry in (version.change_log_json or [])
            )
        ),
        None,
    )
    if not accepted and job_version is None:
        return None

    if job_version is None:
        parent = versions[0] if versions else None
        job_version = ResumeVersion(
            resume_id=resume.id,
            version=(parent.version + 1) if parent else 1,
            parent_version_id=parent.id if parent else None,
            change_log_json=[],
        )
        session.add(job_version)
        await session.flush()

    resume.version = job_version.version
    resume.canonical_json = document.model_dump(mode="json")

    previous_log = list(job_version.change_log_json or [])
    revision = len(previous_log) + 1
    storage = get_storage()
    # Every decision writes a new immutable artifact. A revert therefore keeps
    # the previously accepted content addressable instead of overwriting it.
    snapshot_key = (
        f"resumes/{resume.id}/versions/{job_version.id}/rev-{job_version.version}"
        f"-{revision}.json"
    )
    snapshot_bytes = json.dumps(
        document.model_dump(mode="json"), indent=2, sort_keys=True, default=str
    ).encode("utf-8")
    await storage.save(snapshot_key, snapshot_bytes)
    job_version.snapshot_url = snapshot_key
    await store_bullet_embeddings(session, job_version.id, document.canonical)
    # Provenance: the original source artifact that this derived version came
    # from, plus the validation PDF when the sandboxed compiler is enabled.
    if resume.tex_url:
        job_version.tex_url = resume.tex_url

    pdf_key: str | None = None
    if compiled and compiled.pdf:
        pdf_key = (
            f"resumes/{resume.id}/versions/{job_version.id}/rev-{job_version.version}"
            f"-{revision}.pdf"
        )
        await storage.save(pdf_key, compiled.pdf)
        job_version.pdf_url = pdf_key

    score_row: ScoreReportRow | None = None
    if job_version.score_id is not None:
        score_row = await session.get(ScoreReportRow, job_version.score_id)
    if score_row is None:
        score_row = ScoreReportRow(
            resume_id=resume.id,
            jd_id=jd_id,
            resume_version_id=job_version.id,
            overall=refreshed.overall_score,
            raw_score=refreshed.raw_score,
            grade=refreshed.grade,
            breakdown=refreshed.breakdown.model_dump(mode="json"),
            report_json={},
            parse_fidelity_json=refreshed.parse_fidelity,
            model_versions=refreshed.model_versions,
        )
        session.add(score_row)
        await session.flush()
    else:
        score_row.overall = refreshed.overall_score
        score_row.raw_score = refreshed.raw_score
        score_row.grade = refreshed.grade
        score_row.breakdown = refreshed.breakdown.model_dump(mode="json")
        score_row.parse_fidelity_json = refreshed.parse_fidelity
        score_row.model_versions = refreshed.model_versions
        score_row.resume_version_id = job_version.id

    refreshed.id = str(score_row.id)
    score_row.report_json = refreshed.model_dump(mode="json")
    job_version.score_id = score_row.id
    result.score_after_accepted = refreshed.overall_score

    snapshot_event = {
        "type": "version_snapshot",
        "job_id": str(job.id),
        "version": job_version.version,
        "snapshot_url": snapshot_key,
        "pdf_url": pdf_key,
        "score_id": str(score_row.id),
        "source_artifact": resume.tex_url or resume.raw_file_url,
        "at": datetime.now(UTC).isoformat(),
    }
    job_version.change_log_json = previous_log + events + [snapshot_event]
    return job_version


@router.post("/optimise", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
async def create_optimise(
    payload: OptimiseRequest,
    background: BackgroundTasks,
    session: SessionDep,
    user: CurrentUser,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JobRead:
    if settings.rate_limit_optimise_jobs_per_hour:
        enforce_rate_limit(
            f"optimise:{user.id}",
            settings.rate_limit_optimise_jobs_per_hour,
            3600,
        )

    resume, jd, _document, _analysis = await load_inputs(
        session, user, payload.resume_id, payload.jd_id
    )
    options = payload.options
    target = payload.target_score or options.target_score
    request_payload = {
        "resume_id": str(resume.id),
        "jd_id": str(jd.id),
        "target_score": target,
        "options": options.model_dump(mode="json"),
    }

    key = (idempotency_key or "").strip() or None
    if key is not None and len(key) > 128:
        raise AppError(
            "invalid_idempotency_key",
            "Idempotency-Key must be 128 characters or fewer.",
            status_code=400,
        )

    if key is not None:
        existing = await session.scalar(
            select(Job).where(Job.user_id == user.id, Job.idempotency_key == key)
        )
        if existing is not None:
            if (existing.payload or {}) != request_payload:
                raise AppError(
                    "idempotency_key_reuse",
                    "This Idempotency-Key was already used for a different request.",
                    status_code=409,
                )
            return job_read(existing)

    job = Job(
        user_id=user.id,
        type="optimise",
        status="queued",
        progress=0,
        message="Queued",
        payload=request_payload,
        idempotency_key=key,
    )
    session.add(job)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        if key is not None:
            existing = await session.scalar(
                select(Job).where(Job.user_id == user.id, Job.idempotency_key == key)
            )
            if existing is not None:
                return job_read(existing)
        raise

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


@router.patch(
    "/jobs/{job_id}/changes/{change_id}",
    response_model=ChangeProposal,
)
async def edit_change(
    job_id: str,
    change_id: str,
    payload: ProposalEditRequest,
    session: SessionDep,
    user: CurrentUser,
) -> ChangeProposal:
    """Edit a proposal, re-run verification, and keep the job result in sync."""

    job = await _load_job_for_update(session, job_id, user)
    result = OptimiseResult.model_validate(job.result)
    proposal = _find_proposal(result, change_id)

    await _apply_user_edit(
        session=session,
        user_id=user.id,
        job_id=job.id,
        proposal=proposal,
        proposed=payload.proposed,
    )
    job.result = result.model_dump(mode="json")
    await record_audit(
        session,
        user_id=user.id,
        action="change.edited",
        resource="change",
        resource_id=change_id,
        meta={
            "job_id": str(job.id),
            "truthfulness": proposal.truthfulness,
            "verification_notes": proposal.verification_notes,
        },
    )
    await session.commit()
    return proposal


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
    job = await _load_job_for_update(session, job_id, user)
    result = OptimiseResult.model_validate(job.result)
    proposal = _find_proposal(result, change_id)
    previous_status = proposal.status

    edited = (
        payload.status == "accepted"
        and payload.proposed is not None
        and payload.proposed.strip() != proposal.proposed
    )
    if edited:
        await _apply_user_edit(
            session=session,
            user_id=user.id,
            job_id=job.id,
            proposal=proposal,
            proposed=payload.proposed or "",
        )

    # Idempotent replay: a retried decide call must not append a second event or
    # re-apply the same diff.
    if previous_status == payload.status and not edited:
        version = await _find_job_version(
            session, as_uuid(result.resume_id, "resume"), job.id
        )
        return ChangeDecisionResponse(
            job_id=str(job.id),
            change=proposal,
            score_after_accepted=result.score_after_accepted,
            version_id=str(version.id) if version else None,
            score_id=str(version.score_id) if version and version.score_id else None,
            snapshot_url=version.snapshot_url if version else None,
            pdf_url=str(version.pdf_url) if version and version.pdf_url else None,
            previous_status=previous_status,
            idempotent_replay=True,
        )

    if payload.status == "accepted" and proposal.truthfulness != "verified":
        raise AppError(
            "change_needs_input",
            "This change is not verified yet. Edit it or reject it.",
            status_code=409,
            details={"verification_notes": proposal.verification_notes},
        )

    proposal.status = payload.status
    events = [
        _decision_event(
            job=job,
            proposal=proposal,
            previous_status=previous_status,
            note=payload.note,
        )
    ]

    resume, jd, _document, analysis = await load_inputs(
        session, user, str(result.resume_id), str(result.jd_id)
    )
    base_document = await _load_job_base_document(session, resume, job)
    updated_document = apply_proposals(base_document, result.proposals, analysis)
    # A reject/revert must never be blocked by a compiler. Acceptances are
    # validated strictly; a revert recompiles best-effort so the stored PDF
    # matches the reverted snapshot when possible.
    if payload.status == "accepted":
        compiled = await _validate_document_compiles(updated_document, strict=True)
    elif payload.status == "rejected" and previous_status == "accepted":
        compiled = await _validate_document_compiles(updated_document, strict=False)
    else:
        compiled = None
    refreshed = build_score_report(
        resume_id=str(resume.id),
        jd_id=str(jd.id),
        document=updated_document,
        analysis=analysis,
    )
    result.score_after_accepted = refreshed.overall_score
    version = await _persist_accepted_changes(
        session=session,
        job=job,
        resume=resume,
        jd_id=jd.id,
        document=updated_document,
        result=result,
        refreshed=refreshed,
        events=events,
        compiled=compiled,
    )
    if (
        version is not None
        and payload.status == "rejected"
        and previous_status == "accepted"
        and not (compiled and compiled.pdf)
    ):
        # Do not leave a PDF from the previously accepted content attached to
        # a snapshot that now represents the reverted content.
        version.pdf_url = None
    job.result = result.model_dump(mode="json")

    action = "change.reverted" if events[0]["reverted"] else f"change.{payload.status}"
    await record_audit(
        session,
        user_id=user.id,
        action=action,
        resource="change",
        resource_id=change_id,
        meta={
            "job_id": str(job.id),
            "previous_status": previous_status,
            "edited_by_user": proposal.edited_by_user,
            "version_id": str(version.id) if version else None,
        },
    )
    await session.commit()
    return ChangeDecisionResponse(
        job_id=str(job.id),
        change=proposal,
        score_after_accepted=result.score_after_accepted,
        version_id=str(version.id) if version else None,
        score_id=str(version.score_id) if version and version.score_id else None,
        snapshot_url=version.snapshot_url if version else None,
        pdf_url=str(version.pdf_url) if version and version.pdf_url else None,
        previous_status=previous_status,
        idempotent_replay=False,
    )
