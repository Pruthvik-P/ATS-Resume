from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SourceFormat = Literal["pdf", "docx", "tex", "zip", "txt"]
Severity = Literal["info", "warning", "error"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SourceRef(BaseModel):
    """Points a canonical field back at where it came from in the source."""

    kind: Literal["latex_line", "pdf_bbox", "text_offset", "unknown"] = "unknown"
    line: int | None = None
    page: int | None = None
    bbox: list[float] | None = None
    start: int | None = None
    end: int | None = None
    quote: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ParseIssue(BaseModel):
    code: str
    severity: Severity = "warning"
    message: str
    source_ref: SourceRef | None = None
    auto_fixable: bool = False


class ParseIssueList(BaseModel):
    issues: list[ParseIssue] = Field(default_factory=list)

    def add(self, issue: ParseIssue) -> None:
        self.issues.append(issue)

    @property
    def errors(self) -> list[ParseIssue]:
        return [issue for issue in self.issues if issue.severity == "error"]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    environment: str
    llm_provider: str
    time: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MetaResponse(BaseModel):
    scoring_weights: dict[str, float]
    caps: dict[str, float]
    must_have_multiplier: float = 2.0
    skills_only_multiplier: float = 0.7
    match_tiers: dict[str, float]
    embedding_model: str
    llm_provider: str
    latex_compile: dict[str, Any] = Field(default_factory=dict)
    phase: str = "1"


class Paginated(BaseModel):
    total: int
    limit: int
    offset: int


class AnyDict(BaseModel):
    data: dict[str, Any]
