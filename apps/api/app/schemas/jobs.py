from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
JobType = Literal["optimise", "score", "ingest"]
ChangeKind = Literal[
    "rewrite_bullet",
    "reorder_skills",
    "reorder_bullets",
    "condense_bullets",
    "placeholder_metric",
    "missing_skill_question",
    "parse_fix",
    "summary_tailor",
]
ChangeStatus = Literal["pending", "accepted", "rejected"]


class ChangeProposal(BaseModel):
    id: str
    kind: ChangeKind
    section: str
    target_ref: str | None = None
    original: str
    proposed: str
    rationale: str
    evidence_spans: list[str] = Field(default_factory=list)
    jd_keywords_used: list[str] = Field(default_factory=list)
    risk: Literal["low", "medium", "high"] = "low"
    status: ChangeStatus = "pending"
    truthfulness: Literal["verified", "needs_user_input", "rejected"] = "verified"
    # True when a human supplied or rewrote `proposed`. Such text is treated as
    # a user-confirmed fact and recorded in the Facts Bank.
    edited_by_user: bool = False
    # Verifier feedback from the latest user edit. Empty for generated prose.
    verification_notes: list[str] = Field(default_factory=list)


class VerifierSummary(BaseModel):
    checked: int = 0
    rejected: int = 0
    needs_user_input: int = 0
    reasons: list[str] = Field(default_factory=list)


class OptimiseOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_iterations: int = Field(default=3, ge=1, le=5)
    target_score: float = Field(default=85.0, ge=0.0, le=100.0)
    reorder_skills: bool = True
    reorder_bullets: bool = True
    tailor_summary: bool = True
    suggest_metrics: bool = True
    max_pages: float = Field(default=1.0, ge=0.5, le=5.0)
    max_changes: int = Field(default=25, ge=1, le=100)
    tone: Literal["concise", "balanced", "detailed"] = "concise"


class OptimiseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resume_id: str
    jd_id: str
    target_score: float | None = Field(default=None, ge=0.0, le=100.0)
    options: OptimiseOptions = Field(default_factory=OptimiseOptions)


class IterationRecord(BaseModel):
    iteration: int
    baseline_score: float
    candidate_score: float
    score_delta: float
    compile_status: str = "disabled"
    parse_fidelity_before: dict[str, Any] = Field(default_factory=dict)
    parse_fidelity_after: dict[str, Any] = Field(default_factory=dict)
    rolled_back: bool = False
    reason: str | None = None


class OptimiseResult(BaseModel):
    job_id: str
    resume_id: str
    jd_id: str
    baseline_score: float
    target_score: float
    score_after_accepted: float
    estimated_pages_before: float = 0.0
    estimated_pages_after: float = 0.0
    iterations: int
    stopped_reason: Literal[
        "target_reached",
        "no_further_gains",
        "max_iterations",
        "failed",
    ] = "max_iterations"
    proposals: list[ChangeProposal] = Field(default_factory=list)
    verifier: VerifierSummary = Field(default_factory=VerifierSummary)
    notes: list[str] = Field(default_factory=list)
    iteration_history: list[IterationRecord] = Field(default_factory=list)
    model_versions: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: JobType
    status: JobStatus
    progress: int = Field(default=0, ge=0, le=100)
    message: str | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ProposalEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposed: str = Field(min_length=1, max_length=4000)
    note: str | None = Field(default=None, max_length=500)


class ChangeDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted", "rejected"]
    note: str | None = Field(default=None, max_length=500)
    # Optional last-minute edit. When present it is verified and persisted
    # before the decision is applied, so the user never has to accept stale text.
    proposed: str | None = Field(default=None, min_length=1, max_length=4000)


class ChangeDecisionResponse(BaseModel):
    job_id: str
    change: ChangeProposal
    score_after_accepted: float
    version_id: str | None = None
    score_id: str | None = None
    snapshot_url: str | None = None
    pdf_url: str | None = None
    previous_status: ChangeStatus | None = None
    idempotent_replay: bool = False


class JobEvent(BaseModel):
    event: Literal["status", "progress", "done", "error"]
    job_id: str
    status: JobStatus
    progress: int = 0
    message: str | None = None
    data: dict[str, Any] | None = None
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))
