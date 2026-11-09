from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.jobs import OptimiseOptions


class TailorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jd_ids: list[str] = Field(min_length=1, max_length=20)
    options: OptimiseOptions = Field(default_factory=OptimiseOptions)


class TailorProposalPreview(BaseModel):
    id: str
    kind: str
    original: str
    proposed: str
    rationale: str
    truthfulness: str


class TailorTarget(BaseModel):
    jd_id: str
    jd_title: str | None = None
    baseline_score: float
    proposed_score: float
    proposal_count: int = 0
    verified_count: int = 0
    top_proposals: list[TailorProposalPreview] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class TailorResponse(BaseModel):
    resume_id: str
    targets: list[TailorTarget] = Field(default_factory=list)
    note: str = (
        "Preview only: proposals are not persisted. Accept changes through an optimise "
        "job to create a versioned, auditable resume."
    )


__all__ = [
    "TailorProposalPreview",
    "TailorRequest",
    "TailorResponse",
    "TailorTarget",
]
