"""phase 2 embeddings: optional pgvector columns and cosine indexes

Revision ID: 7a3d9f2c1e44
Revises: 9c1f2e7a4b6d
Create Date: 2026-11-09 14:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.core.config import settings

revision: str = "7a3d9f2c1e44"
down_revision: str | None = "9c1f2e7a4b6d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _postgres():
        return
    dimension = max(1, settings.embedding_vector_dim)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        "ALTER TABLE job_descriptions ADD COLUMN IF NOT EXISTS "
        f"embedding_vector vector({dimension})"
    )
    op.execute(
        "ALTER TABLE bullets ADD COLUMN IF NOT EXISTS "
        f"embedding_vector vector({dimension})"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_job_descriptions_embedding_vector "
        "ON job_descriptions USING ivfflat (embedding_vector vector_cosine_ops) "
        "WITH (lists = 100)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_bullets_embedding_vector "
        "ON bullets USING ivfflat (embedding_vector vector_cosine_ops) "
        "WITH (lists = 100)"
    )


def downgrade() -> None:
    if not _postgres():
        return
    op.execute("DROP INDEX IF EXISTS ix_bullets_embedding_vector")
    op.execute("DROP INDEX IF EXISTS ix_job_descriptions_embedding_vector")
    op.execute("ALTER TABLE bullets DROP COLUMN IF EXISTS embedding_vector")
    op.execute("ALTER TABLE job_descriptions DROP COLUMN IF EXISTS embedding_vector")
