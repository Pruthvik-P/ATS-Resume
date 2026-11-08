from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

Importance = Literal["must", "nice"]
Seniority = Literal["intern", "junior", "mid", "senior", "lead", "principal", "manager", "director"]


class SkillRequirement(BaseModel):
    skill: str
    canonical: str
    importance: Importance
    weight: float = 1.0
    category: str = "general"


class KnockoutCriterion(BaseModel):
    kind: Literal[
        "clearance",
        "work_authorization",
        "degree",
        "location",
        "experience",
        "certification",
        "other",
    ]
    text: str
    hard: bool = True


class JDAnalysis(BaseModel):
    title: str | None = None
    company: str | None = None
    seniority: Seniority | None = None
    years_min: int | None = None
    years_max: int | None = None
    must_have: list[SkillRequirement] = Field(default_factory=list)
    nice_to_have: list[SkillRequirement] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    domain_terms: list[str] = Field(default_factory=list)
    knockouts: list[KnockoutCriterion] = Field(default_factory=list)
    analyser_version: str = "deterministic-jd-v1"
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def all_skills(self) -> list[SkillRequirement]:
        return [*self.must_have, *self.nice_to_have]

    @property
    def must_have_skills(self) -> list[str]:
        return [item.canonical for item in self.must_have]


class JDAnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_url: str | None = None
    analysis: JDAnalysis
    created_at: datetime


class JDCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(default=None, max_length=60_000)
    url: HttpUrl | None = None
    title: str | None = Field(default=None, max_length=200)
    company: str | None = Field(default=None, max_length=200)


class JDAnalysisResponse(BaseModel):
    id: str
    analysis: JDAnalysis
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime
