"""p0 integrity: version snapshots, idempotency keys, explicit provenance

Revision ID: 9c1f2e7a4b6d
Revises: 8b4692701773
Create Date: 2026-11-09 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9c1f2e7a4b6d"
down_revision: str | None = "8b4692701773"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "resume_versions",
        sa.Column("snapshot_url", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_jobs_user_idempotency",
        "jobs",
        ["user_id", "idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_user_idempotency", table_name="jobs")
    op.drop_column("jobs", "idempotency_key")
    op.drop_column("resume_versions", "snapshot_url")
