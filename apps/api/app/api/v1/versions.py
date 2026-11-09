from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, Query, Response
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep, as_uuid
from app.core.config import settings
from app.core.errors import AppError, NotFoundError
from app.db.models import ResumeVersion
from app.schemas.jobs import ChangeDecisionRequest, ChangeDecisionResponse
from app.schemas.resume import ResumeVersionDetail, VersionDiffResponse
from app.services.export.docx import render_resume_docx
from app.services.latex.compiler import compile_source
from app.services.latex.patch import patch_source
from app.services.latex.project import decode_tex
from app.services.latex.render import render_resume_tex
from app.services.versions import (
    diff_resumes,
    load_version_document,
    load_version_for_user,
)
from app.storage.local import get_storage

router = APIRouter(prefix="/versions", tags=["versions"])


def _detail(version: ResumeVersion, document) -> ResumeVersionDetail:
    return ResumeVersionDetail(
        id=str(version.id),
        resume_id=str(version.resume_id),
        version=version.version,
        parent_version_id=str(version.parent_version_id) if version.parent_version_id else None,
        tex_url=version.tex_url,
        pdf_url=version.pdf_url,
        snapshot_url=version.snapshot_url,
        change_log=version.change_log_json or [],
        score_id=str(version.score_id) if version.score_id else None,
        document=document,
        created_at=version.created_at,
    )


@router.get("/{version_id}", response_model=ResumeVersionDetail)
async def get_version(
    version_id: str, session: SessionDep, user: CurrentUser
) -> ResumeVersionDetail:
    version, resume = await load_version_for_user(
        session, user.id, as_uuid(version_id, "version")
    )
    document = await load_version_document(version, resume)
    return _detail(version, document)


@router.get("/{version_id}/diff", response_model=VersionDiffResponse)
async def diff_version(
    version_id: str,
    session: SessionDep,
    user: CurrentUser,
    against: str | None = Query(default=None),
) -> VersionDiffResponse:
    version, resume = await load_version_for_user(
        session, user.id, as_uuid(version_id, "version")
    )
    current = await load_version_document(version, resume)

    against_version: ResumeVersion | None = None
    if against:
        against_version, against_resume = await load_version_for_user(
            session, user.id, as_uuid(against, "version")
        )
        if against_resume.id != resume.id:
            raise AppError(
                "version_mismatch",
                "Both versions must belong to the same resume.",
                status_code=400,
            )
    else:
        against_version = await session.scalar(
            select(ResumeVersion)
            .where(
                ResumeVersion.resume_id == resume.id,
                ResumeVersion.version < version.version,
            )
            .order_by(ResumeVersion.version.desc())
            .limit(1)
        )
        against = str(against_version.id) if against_version else None

    if against_version is None:
        return VersionDiffResponse(
            version_id=str(version.id),
            against_version_id=None,
            changed_fields=0,
            fields=[],
            note="This is the first version, so there is no earlier snapshot to diff.",
        )
    previous = await load_version_document(against_version, resume)
    return diff_resumes(
        previous.canonical,
        current.canonical,
        version_id=str(version.id),
        against_version_id=str(against_version.id),
    )


@router.get("/{version_id}/export")
async def export_version(
    version_id: str,
    session: SessionDep,
    user: CurrentUser,
    format: Literal["tex", "pdf", "docx", "json"] = Query(default="tex"),
    mode: Literal["canonical", "source"] = Query(default="canonical"),
) -> Response:
    version, resume = await load_version_for_user(
        session, user.id, as_uuid(version_id, "version")
    )
    document = await load_version_document(version, resume)
    stem = f"resume-v{version.version}"

    if mode == "source" and format != "tex":
        raise AppError(
            "source_mode_unsupported",
            "Source patching is only available with format=tex.",
            status_code=400,
        )

    if format == "tex":
        if mode == "source":
            if not version.tex_url or not version.tex_url.lower().endswith(".tex"):
                raise AppError(
                    "source_export_unavailable",
                    "This version has no single-file .tex source to patch. Export the "
                    "canonical TEX render instead.",
                    status_code=409,
                )
            raw = await get_storage().read(version.tex_url)
            effective: dict[str, tuple[str, str]] = {}
            for event in version.change_log_json or []:
                if not isinstance(event, dict) or event.get("type") != "change_decision":
                    continue
                change_id = str(event.get("change_id") or "")
                before = event.get("before_text") or event.get("original")
                after = event.get("after_text") or event.get("proposed")
                if event.get("status") == "accepted" and before and after and before != after:
                    effective[change_id] = (str(before), str(after))
                elif event.get("status") == "rejected":
                    effective.pop(change_id, None)
            patched = patch_source(decode_tex(raw), list(effective.values()))
            return Response(
                content=patched.source,
                media_type="application/x-tex",
                headers={
                    "content-disposition": f'attachment; filename="{stem}-patched.tex"',
                    "x-patch-applied": str(len(patched.applied)),
                    "x-patch-skipped": str(len(patched.skipped)),
                },
            )
        return Response(
            content=render_resume_tex(document),
            media_type="application/x-tex",
            headers={"content-disposition": f'attachment; filename="{stem}.tex"'},
        )
    if format == "json":
        return Response(
            content=document.model_dump_json(indent=2),
            media_type="application/json",
            headers={"content-disposition": f'attachment; filename="{stem}.json"'},
        )
    if format == "docx":
        return Response(
            content=render_resume_docx(document),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"content-disposition": f'attachment; filename="{stem}.docx"'},
        )

    if version.pdf_url:
        raw = await get_storage().read(version.pdf_url)
        return Response(
            content=raw,
            media_type="application/pdf",
            headers={"content-disposition": f'attachment; filename="{stem}.pdf"'},
        )

    if not settings.latex_compile_enabled:
        raise AppError(
            "pdf_export_unavailable",
            "PDF export requires the sandboxed LaTeX compiler. Enable "
            "ATS_LATEX_COMPILE_ENABLED and configure a worker, or export TEX/DOCX.",
            status_code=409,
        )
    compiled = await asyncio.to_thread(
        compile_source, render_resume_tex(document), "resume.tex"
    )
    if compiled.compiled and compiled.pdf:
        return Response(
            content=compiled.pdf,
            media_type="application/pdf",
            headers={"content-disposition": f'attachment; filename="{stem}.pdf"'},
        )
    raise AppError(
        "pdf_export_failed",
        "The sandboxed LaTeX compiler could not produce a PDF for this version.",
        status_code=409,
        details={"status": compiled.status, "reason": compiled.reason},
    )


@router.post(
    "/{version_id}/changes/{change_id}",
    response_model=ChangeDecisionResponse,
)
async def decide_version_change(
    version_id: str,
    change_id: str,
    payload: ChangeDecisionRequest,
    session: SessionDep,
    user: CurrentUser,
) -> ChangeDecisionResponse:
    """Doc-parity alias for accepting/rejecting a change by version id.

    The job remains the source of truth; this route finds the job that produced
    the version from its append-only change log and delegates to the canonical
    decision handler.
    """

    version, _resume = await load_version_for_user(
        session, user.id, as_uuid(version_id, "version")
    )
    job_id: str | None = None
    for event in reversed(version.change_log_json or []):
        if isinstance(event, dict) and event.get("change_id") == change_id:
            job_id = str(event.get("job_id") or "")
            break
    if not job_id:
        raise NotFoundError("change", change_id)

    from app.api.v1.jobs import decide_change

    return await decide_change(job_id, change_id, payload, session, user)


__all__ = ["router"]
