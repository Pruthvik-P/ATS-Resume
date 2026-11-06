from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Priority = Literal["high", "medium", "low"]
ScoreKey = Literal[
    "keyword_match",
    "semantic_relevance",
    "experience_fit",
    "parseability",
    "impact",
    "education",
    "readability",
]


class ComponentScore(BaseModel):
    """One weighted scoring component. Extra keys carry explainability detail."""

    model_config = ConfigDict(extra="allow")

    score: float = Field(ge=0.0, le=100.0)
    weight: float = Field(ge=0.0, le=1.0)


class ScoreBreakdown(BaseModel):
    keyword_match: ComponentScore
    semantic_relevance: ComponentScore
    experience_fit: ComponentScore
    parseability: ComponentScore
    impact: ComponentScore
    education: ComponentScore
    readability: ComponentScore


class CapApplied(BaseModel):
    code: str
    reason: str
    cap: float


class PenaltyApplied(BaseModel):
    code: str
    reason: str
    points: float


class Recommendation(BaseModel):
    priority: Priority
    type: str
    text: str
    evidence: list[str] = Field(default_factory=list)
    component: ScoreKey | None = None


class ScoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resume_id: str
    jd_id: str


class ScoreReport(BaseModel):
    id: str | None = None
    resume_id: str
    jd_id: str
    overall_score: float = Field(ge=0.0, le=100.0)
    raw_score: float = Field(ge=0.0, le=100.0)
    grade: str
    breakdown: ScoreBreakdown
    knockouts: list[str] = Field(default_factory=list)
    caps: list[CapApplied] = Field(default_factory=list)
    penalties: list[PenaltyApplied] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    parse_fidelity: dict[str, Any] = Field(default_factory=dict)
    weights: dict[str, float] = Field(default_factory=dict)
    model_versions: dict[str, str] = Field(default_factory=dict)
    scoring_version: str = "scoring-v1"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ScoreReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    resume_id: str
    jd_id: str
    overall: float
    grade: str
    breakdown: dict[str, Any]
    report: ScoreReport
    created_at: datetime
