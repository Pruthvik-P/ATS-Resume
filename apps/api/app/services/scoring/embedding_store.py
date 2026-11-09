"""Embedding persistence and similarity search.

JSON vectors are portable and work on SQLite. When the database is PostgreSQL,
`ATS_EMBEDDING_STORE_BACKEND=pgvector` adds a native `vector` column through the
Phase 2 migration and uses `<=>` cosine distance for search. Any pgvector
failure falls back to JSON cosine search.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import Bullet, JobDescription, Resume, ResumeVersion
from app.schemas.resume import Resume as ResumeModel
from app.schemas.resume import iter_evidence_bullets
from app.services.scoring.embedding import embed

logger = get_logger(__name__)

_PGVECTOR_DISABLED = False


@dataclass
class SimilarBullet:
    bullet_id: str
    resume_version_id: str
    section: str
    text: str
    similarity: float


def _is_postgres(session: AsyncSession) -> bool:
    try:
        return session.get_bind().dialect.name == "postgresql"
    except Exception:
        return False


def _use_pgvector(session: AsyncSession) -> bool:
    global _PGVECTOR_DISABLED
    return (
        not _PGVECTOR_DISABLED
        and settings.embedding_store_backend == "pgvector"
        and _is_postgres(session)
    )


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    norm_left = math.sqrt(sum(value * value for value in left))
    norm_right = math.sqrt(sum(value * value for value in right))
    if not norm_left or not norm_right:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=False)) / (
        norm_left * norm_right
    )


async def store_jd_embedding(session: AsyncSession, row: JobDescription) -> None:
    global _PGVECTOR_DISABLED
    if not settings.embedding_store_enabled:
        return
    vector = await asyncio.to_thread(embed, row.raw_text)
    row.embedding = vector
    if not _use_pgvector(session):
        return
    try:
        await session.execute(
            text(
                "UPDATE job_descriptions SET embedding_vector = CAST(:vector AS vector) "
                "WHERE id = :id"
            ),
            {"vector": _vector_literal(vector), "id": str(row.id)},
        )
    except Exception as exc:
        _PGVECTOR_DISABLED = True
        logger.warning("pgvector JD write failed; keeping JSON vectors", extra={"error": str(exc)})


async def store_bullet_embeddings(
    session: AsyncSession, resume_version_id: UUID, resume: ResumeModel
) -> int:
    global _PGVECTOR_DISABLED
    if not settings.embedding_store_enabled:
        return 0
    await session.execute(
        delete(Bullet).where(Bullet.resume_version_id == resume_version_id)
    )
    bullets = iter_evidence_bullets(resume)
    rows: list[Bullet] = []
    for evidence in bullets:
        vector = await asyncio.to_thread(embed, evidence.text)
        row = Bullet(
            resume_version_id=resume_version_id,
            section=evidence.section,
            text=evidence.text,
            embedding=vector,
            source_ref=(
                evidence.source_ref.model_dump(mode="json")
                if evidence.source_ref is not None
                else None
            ),
        )
        session.add(row)
        rows.append(row)
    await session.flush()
    if _use_pgvector(session):
        try:
            for row in rows:
                await session.execute(
                    text(
                        "UPDATE bullets SET embedding_vector = CAST(:vector AS vector) "
                        "WHERE id = :id"
                    ),
                    {"vector": _vector_literal(row.embedding or []), "id": str(row.id)},
                )
        except Exception as exc:
            _PGVECTOR_DISABLED = True
            logger.warning(
                "pgvector bullet write failed; keeping JSON vectors",
                extra={"error": str(exc)},
            )
    return len(rows)


async def similar_bullets(
    session: AsyncSession,
    *,
    user_id: UUID,
    query: str,
    resume_id: UUID | None = None,
    limit: int = 5,
) -> tuple[list[SimilarBullet], str]:
    query_vector = await asyncio.to_thread(embed, query)
    if _use_pgvector(session):
        try:
            params: dict[str, object] = {
                "vector": _vector_literal(query_vector),
                "user_id": str(user_id),
                "limit": limit,
            }
            clause = ""
            if resume_id is not None:
                clause = "AND r.id = :resume_id"
                params["resume_id"] = str(resume_id)
            rows = (
                await session.execute(
                    text(
                        "SELECT b.id, b.resume_version_id, b.section, b.text, "
                        "1 - (b.embedding_vector <=> CAST(:vector AS vector)) AS similarity "
                        "FROM bullets b "
                        "JOIN resume_versions v ON v.id = b.resume_version_id "
                        "JOIN resumes r ON r.id = v.resume_id "
                        "WHERE r.user_id = :user_id AND b.embedding_vector IS NOT NULL "
                        f"{clause} "
                        "ORDER BY b.embedding_vector <=> CAST(:vector AS vector) "
                        "LIMIT :limit"
                    ),
                    params,
                )
            ).all()
            return (
                [
                    SimilarBullet(
                        bullet_id=str(row.id),
                        resume_version_id=str(row.resume_version_id),
                        section=row.section,
                        text=row.text,
                        similarity=round(float(row.similarity), 4),
                    )
                    for row in rows
                ],
                "pgvector",
            )
        except Exception as exc:
            global _PGVECTOR_DISABLED
            _PGVECTOR_DISABLED = True
            logger.warning(
                "pgvector search failed; falling back to JSON cosine",
                extra={"error": str(exc)},
            )

    statement = (
        select(Bullet)
        .join(ResumeVersion, ResumeVersion.id == Bullet.resume_version_id)
        .join(Resume, Resume.id == ResumeVersion.resume_id)
        .where(Resume.user_id == user_id, Resume.deleted_at.is_(None))
    )
    if resume_id is not None:
        statement = statement.where(Resume.id == resume_id)
    rows = list((await session.execute(statement)).scalars())
    scored = [
        SimilarBullet(
            bullet_id=str(row.id),
            resume_version_id=str(row.resume_version_id),
            section=row.section,
            text=row.text,
            similarity=round(_cosine(query_vector, row.embedding or []), 4),
        )
        for row in rows
    ]
    scored.sort(key=lambda item: item.similarity, reverse=True)
    return scored[:limit], "json"


def reset_pgvector_state() -> None:
    global _PGVECTOR_DISABLED
    _PGVECTOR_DISABLED = False


__all__ = [
    "SimilarBullet",
    "reset_pgvector_state",
    "similar_bullets",
    "store_bullet_embeddings",
    "store_jd_embedding",
]
