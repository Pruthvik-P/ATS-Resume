from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PurgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Overrides the configured retention window for this purge call.
    older_than_days: int | None = Field(default=None, ge=1, le=3650)


class PurgeResponse(BaseModel):
    resumes_deleted: int = 0
    versions_deleted: int = 0
    scores_deleted: int = 0
    facts_deleted: int = 0
    jobs_deleted: int = 0
    jds_deleted: int = 0
    audit_rows_deleted: int = 0
    storage_objects_deleted: int = 0


class DeleteAllResponse(BaseModel):
    deleted: PurgeResponse
    audit_retained: bool = True
