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
from app.core.ratelimit import enforce_rate_limit
from app.db.models import AuditLog, User
from app.db.session import get_session

DEFAULT_USER_EMAIL = "local@ats-engine.local"

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _get_or_create_user(
    session: AsyncSession, email: str, *, plan: str = "local"
) -> User:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user:
        return user
    user = User(email=email, plan=plan)
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        result = await session.execute(select(User).where(User.email == email))
        return result.scalar_one()
    await session.refresh(user)
    return user


async def _default_user(session: AsyncSession) -> User:
    return await _get_or_create_user(session, DEFAULT_USER_EMAIL, plan="local")


def _resolve_per_user_key(provided: str) -> str | None:
    for email, key in settings.user_api_keys.items():
        if secrets.compare_digest(provided, key):
            return email
    return None


async def get_current_user(
    request: Request,
    session: SessionDep,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> User:
    provided = x_api_key or request.query_params.get("api_key") or ""

    per_user_keys = settings.user_api_keys
    if per_user_keys:
        email = _resolve_per_user_key(provided)
        if email is None:
            raise AppError(
                "unauthorized",
                "A valid per-user API key is required.",
                status_code=401,
            )
        user = await _get_or_create_user(session, email, plan="free")
    elif settings.api_key:
        if not secrets.compare_digest(provided, settings.api_key):
            raise AppError(
                "unauthorized",
                "A valid API key is required.",
                status_code=401,
            )
        user = await _default_user(session)
    else:
        # Open mode is for local development and tests only.
        user = await _default_user(session)

    if settings.rate_limit_requests_per_minute:
        enforce_rate_limit(
            f"request:{user.id}",
            settings.rate_limit_requests_per_minute,
            60,
        )
    return user


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
