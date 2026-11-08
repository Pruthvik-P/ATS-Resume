from __future__ import annotations

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, SessionDep, as_uuid, record_audit
from app.core.errors import NotFoundError
from app.db.models import Fact
from app.schemas.facts import FactCreate, FactList, FactRead

router = APIRouter(prefix="/facts", tags=["facts bank"])


@router.post("", response_model=FactRead, status_code=status.HTTP_201_CREATED)
async def create_fact(payload: FactCreate, session: SessionDep, user: CurrentUser) -> FactRead:
    fact = Fact(
        user_id=user.id,
        fact_text=payload.fact_text.strip(),
        source=payload.source,
        tags=payload.tags,
    )
    session.add(fact)
    await session.flush()
    await record_audit(
        session,
        user_id=user.id,
        action="fact.created",
        resource="fact",
        resource_id=str(fact.id),
    )
    await session.commit()
    await session.refresh(fact)
    return FactRead(
        id=str(fact.id),
        fact_text=fact.fact_text,
        source=fact.source,
        tags=fact.tags or [],
        confirmed_at=fact.confirmed_at,
        created_at=fact.created_at,
    )


@router.get("", response_model=FactList)
async def list_facts(
    session: SessionDep,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> FactList:
    base = select(Fact).where(Fact.user_id == user.id)
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    rows = (
        await session.execute(
            base.order_by(Fact.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars()
    items = [
        FactRead(
            id=str(row.id),
            fact_text=row.fact_text,
            source=row.source,
            tags=row.tags or [],
            confirmed_at=row.confirmed_at,
            created_at=row.created_at,
        )
        for row in rows
    ]
    return FactList(total=int(total or 0), items=items)


@router.delete("/{fact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fact(fact_id: str, session: SessionDep, user: CurrentUser) -> None:
    fact = await session.get(Fact, as_uuid(fact_id, "fact"))
    if not fact or fact.user_id != user.id:
        raise NotFoundError("fact", fact_id)
    await session.delete(fact)
    await session.commit()
