from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.db.models import AuditLog, User
from app.db.session import get_session

DEFAULT_USER_EMAIL = "local@ats-engine.local"

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _default_user(session: AsyncSession) -> User:
    result = await session.execute(select(User).where(User.email == DEFAULT_USER_EMAIL))
    user = result.scalar_one_or_none()
    if user:
        return user
    user = User(email=DEFAULT_USER_EMAIL, plan="local")
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        result = await session.execute(select(User).where(User.email == DEFAULT_USER_EMAIL))
        existing = result.scalar_one()
        return existing
    await session.refresh(user)
    return user


async def get_current_user(
    request: Request,
    session: SessionDep,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> User:
    if settings.api_key:
        provided = x_api_key or request.query_params.get("api_key") or ""
        if not secrets.compare_digest(provided, settings.api_key):
            raise AppError(
                "unauthorized",
                "A valid API key is required.",
                status_code=401,
            )
    return await _default_user(session)


CurrentUser = Annotated[User, Depends(get_current_user)]


def as_uuid(value: str, resource: str) -> UUID:
    try:
        return UUID(value)
    except (ValueError, TypeError) as exc:
        raise AppError(
            "invalid_id",
            f"'{value}' is not a valid {resource} id.",
            status_code=400,
        ) from exc


async def record_audit(
    session: AsyncSession,
    *,
    user_id: UUID | None,
    action: str,
    resource: str | None = None,
    resource_id: str | None = None,
    meta: dict | None = None,
) -> None:
    session.add(
        AuditLog(
            user_id=user_id,
            action=action,
            resource=resource,
            resource_id=resource_id,
            meta=meta or {},
        )
    )


def utcnow() -> datetime:
    return datetime.now(UTC)
