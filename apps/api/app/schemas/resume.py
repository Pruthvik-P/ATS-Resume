from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import ORMModel, ParseIssue, SourceFormat, SourceRef

StructuringMethod = Literal["heuristic", "llm"]


class Location(BaseModel):
    address: str | None = None
    postalCode: str | None = None
    city: str | None = None
    countryCode: str | None = None
    region: str | None = None


class Profile(BaseModel):
    network: str | None = None
    username: str | None = None
    url: str | None = None


class Basics(BaseModel):
    name: str | None = None
    label: str | None = None
    image: str | None = None
    email: str | None = None
    phone: str | None = None
    url: str | None = None
    summary: str | None = None
    location: Location | None = None
    profiles: list[Profile] = Field(default_factory=list)


class WorkItem(BaseModel):
    id: str | None = None
    name: str | None = None
    position: str | None = None
    url: str | None = None
    startDate: str | None = None
    endDate: str | None = None
    summary: str | None = None
    highlights: list[str] = Field(default_factory=list)
    location: str | None = None


class EducationItem(BaseModel):
    id: str | None = None
    institution: str | None = None
    url: str | None = None
    area: str | None = None
    studyType: str | None = None
    startDate: str | None = None
    endDate: str | None = None
    score: str | None = None
    courses: list[str] = Field(default_factory=list)


class SkillGroup(BaseModel):
    id: str | None = None
    name: str | None = None
    level: str | None = None
    keywords: list[str] = Field(default_factory=list)


class ProjectItem(BaseModel):
    id: str | None = None
    name: str | None = None
    description: str | None = None
    highlights: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    startDate: str | None = None
    endDate: str | None = None
    url: str | None = None


class CertificationItem(BaseModel):
    id: str | None = None
    name: str | None = None
    issuer: str | None = None
    date: str | None = None
    url: str | None = None


class LanguageItem(BaseModel):
    language: str | None = None
    fluency: str | None = None


class AwardItem(BaseModel):
    title: str | None = None
    date: str | None = None
    awarder: str | None = None
    summary: str | None = None


class ResumeMeta(BaseModel):
    canonical: str = "jsonresume-subset/v1"
    version: str = "v1"
    lastModified: str | None = None


class Resume(BaseModel):
    """A conservative subset of the JSON Resume schema."""

    basics: Basics = Field(default_factory=Basics)
    work: list[WorkItem] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)
    skills: list[SkillGroup] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)
    certifications: list[CertificationItem] = Field(default_factory=list)
    languages: list[LanguageItem] = Field(default_factory=list)
    awards: list[AwardItem] = Field(default_factory=list)
    meta: ResumeMeta = Field(default_factory=ResumeMeta)


class StructuringMeta(BaseModel):
    method: StructuringMethod = "heuristic"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    model: str = "deterministic-heuristic-v1"
    prompt_version: str = "n/a"


class EvidenceBullet(BaseModel):
    id: str
    section: Literal["summary", "work", "project", "other"] = "other"
    text: str
    source_ref: SourceRef | None = None


class ResumeDocument(BaseModel):
    format: SourceFormat
    canonical: Resume
    source_map: dict[str, SourceRef] = Field(default_factory=dict)
    issues: list[ParseIssue] = Field(default_factory=list)
    raw_text: str | None = None
    structuring: StructuringMeta = Field(default_factory=StructuringMeta)


class ResumeRead(ORMModel):
    id: str
    filename: str
    source_format: SourceFormat
    document: ResumeDocument
    created_at: datetime

    @classmethod
    def from_orm_row(cls, row: Any) -> ResumeRead:
        return cls(
            id=str(row.id),
            filename=row.filename,
            source_format=row.source_format,
            document=ResumeDocument.model_validate(row.canonical_json),
            created_at=row.created_at,
        )


class ResumeSummary(ORMModel):
    id: str
    filename: str
    source_format: SourceFormat
    name: str | None = None
    created_at: datetime
    overall_score: float | None = None


class ResumeVersionRead(ORMModel):
    id: str
    resume_id: str
    version: int
    parent_version_id: str | None = None
    change_log: list[dict[str, Any]] = Field(default_factory=list)
    score_id: str | None = None
    created_at: datetime


class ResumeStats(BaseModel):
    bullets: int
    words: int
    estimated_pages: float
    has_contact_block: bool
    sections: list[str]


def resume_word_count(resume: Resume) -> int:
    chunks: list[str] = []
    if resume.basics.summary:
        chunks.append(resume.basics.summary)
    for work in resume.work:
        chunks.append(" ".join(filter(None, [work.name, work.position, work.summary])))
        chunks.extend(work.highlights)
    for project in resume.projects:
        chunks.append(" ".join(filter(None, [project.name, project.description])))
        chunks.extend(project.highlights)
    for skill in resume.skills:
        chunks.append(" ".join(filter(None, [skill.name, *skill.keywords])))
    return len(" ".join(chunks).split())


def iter_evidence_bullets(resume: Resume) -> list[EvidenceBullet]:
    """Every piece of free text that can carry evidence for a JD requirement."""

    bullets: list[EvidenceBullet] = []
    if resume.basics.summary:
        bullets.append(EvidenceBullet(id="summary", section="summary", text=resume.basics.summary))
    for work_index, work in enumerate(resume.work):
        for highlight_index, highlight in enumerate(work.highlights):
            bullets.append(
                EvidenceBullet(
                    id=f"work[{work_index}].highlights[{highlight_index}]",
                    section="work",
                    text=highlight,
                )
            )
        if work.summary:
            bullets.append(
                EvidenceBullet(id=f"work[{work_index}].summary", section="work", text=work.summary)
            )
    for project_index, project in enumerate(resume.projects):
        for highlight_index, highlight in enumerate(project.highlights):
            bullets.append(
                EvidenceBullet(
                    id=f"projects[{project_index}].highlights[{highlight_index}]",
                    section="project",
                    text=highlight,
                )
            )
    return bullets


def resume_to_ats_text(resume: Resume) -> str:
    """Flatten the canonical resume the way a parser would present it."""

    lines: list[str] = []
    basics = resume.basics
    for value in (basics.name, basics.label, basics.email, basics.phone, basics.url):
        if value:
            lines.append(value)
    if basics.summary:
        lines.extend(["SUMMARY", basics.summary])
    if resume.work:
        lines.append("EXPERIENCE")
        for work in resume.work:
            header = " | ".join(filter(None, [work.position, work.name]))
            if header:
                lines.append(header)
            dates = " - ".join(filter(None, [work.startDate, work.endDate]))
            if dates:
                lines.append(dates)
            lines.extend(work.highlights)
    if resume.education:
        lines.append("EDUCATION")
        for education in resume.education:
            lines.append(
                " | ".join(
                    filter(
                        None,
                        [education.studyType, education.area, education.institution],
                    )
                )
            )
    if resume.skills:
        lines.append("SKILLS")
        for skill in resume.skills:
            lines.append(f"{skill.name or ''}: {', '.join(skill.keywords)}".strip(": "))
    if resume.projects:
        lines.append("PROJECTS")
        for project in resume.projects:
            if project.name:
                lines.append(project.name)
            lines.extend(project.highlights)
    if resume.certifications:
        lines.append("CERTIFICATIONS")
        lines.extend(
            filter(None, [certification.name for certification in resume.certifications])
        )
    return "\n".join(lines)


def today_iso() -> str:
    return date.today().isoformat()


def now_utc() -> datetime:
    return datetime.now(UTC)


class ResumeSearchQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    format: SourceFormat | None = None


__all__ = [
    "Basics",
    "CertificationItem",
    "EducationItem",
    "EvidenceBullet",
    "LanguageItem",
    "Location",
    "Profile",
    "ProjectItem",
    "Resume",
    "ResumeDocument",
    "ResumeRead",
    "ResumeSummary",
    "ResumeVersionRead",
    "SkillGroup",
    "WorkItem",
    "iter_evidence_bullets",
    "resume_to_ats_text",
    "resume_word_count",
]
