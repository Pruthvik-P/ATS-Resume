"""Version loading and canonical field-level diffing."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.db.models import Resume, ResumeVersion
from app.schemas.resume import (
    FieldDiff,
    ResumeDocument,
    VersionDiffResponse,
)
from app.schemas.resume import Resume as ResumeModel
from app.storage.local import get_storage


async def load_version_for_user(
    session: AsyncSession, user_id: UUID, version_id: UUID
) -> tuple[ResumeVersion, Resume]:
    version = await session.get(ResumeVersion, version_id)
    if version is None:
        raise NotFoundError("version", str(version_id))
    resume = await session.get(Resume, version.resume_id)
    if resume is None or resume.user_id != user_id or resume.deleted_at is not None:
        raise NotFoundError("version", str(version_id))
    return version, resume


async def load_version_document(
    version: ResumeVersion, resume: Resume
) -> ResumeDocument:
    if version.snapshot_url:
        raw = await get_storage().read(version.snapshot_url)
        return ResumeDocument.model_validate_json(raw)
    return ResumeDocument.model_validate(resume.canonical_json)


def _flatten(value: Any, prefix: str, output: dict[str, str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _flatten(item, f"{prefix}.{key}" if prefix else key, output)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _flatten(item, f"{prefix}[{index}]", output)
    elif value is not None and value != "":
        output[prefix] = str(value)


def flatten_resume(resume: ResumeModel) -> dict[str, str]:
    output: dict[str, str] = {}
    _flatten(resume.model_dump(exclude={"meta"}), "", output)
    return output


def diff_resumes(
    before: ResumeModel,
    after: ResumeModel,
    *,
    version_id: str,
    against_version_id: str | None,
) -> VersionDiffResponse:
    left = flatten_resume(before)
    right = flatten_resume(after)
    fields: list[FieldDiff] = []
    for path in sorted(set(left) | set(right)):
        old = left.get(path)
        new = right.get(path)
        if old == new:
            continue
        if old is None:
            change = "added"
        elif new is None:
            change = "removed"
        else:
            change = "changed"
        fields.append(
            FieldDiff(path=path, change=change, before=old, after=new)  # type: ignore[arg-type]
        )
    return VersionDiffResponse(
        version_id=version_id,
        against_version_id=against_version_id,
        changed_fields=len(fields),
        fields=fields[:250],
    )


__all__ = [
    "diff_resumes",
    "flatten_resume",
    "load_version_document",
    "load_version_for_user",
]
