"""Database models are defined here so Alembic autogenerate can import one module."""

from app.db.models import (
    AuditLog,
    Base,
    Bullet,
    Fact,
    Job,
    JobDescription,
    Resume,
    ResumeVersion,
    ScoreReportRow,
    User,
)

__all__ = [
    "AuditLog",
    "Base",
    "Bullet",
    "Fact",
    "Job",
    "JobDescription",
    "Resume",
    "ResumeVersion",
    "ScoreReportRow",
    "User",
]
