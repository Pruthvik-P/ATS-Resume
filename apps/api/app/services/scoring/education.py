from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.jd import JDAnalysis
from app.schemas.resume import Resume

_DEGREE_RANK: tuple[tuple[str, int], ...] = (
    ("phd", 5),
    ("doctor", 5),
    ("master", 4),
    ("mba", 4),
    ("m.tech", 4),
    ("m.sc", 4),
    ("m.s", 4),
    ("bachelor", 3),
    ("b.tech", 3),
    ("b.sc", 3),
    ("b.s", 3),
    ("b.e", 3),
    ("associate", 2),
    ("diploma", 2),
    ("high school", 1),
)


@dataclass
class EducationResult:
    score: float
    degree_level: int = 0
    required_level: int | None = None
    certifications: int = 0
    notes: list[str] = field(default_factory=list)


def _degree_level(value: str | None) -> int:
    if not value:
        return 0
    lowered = value.lower()
    best = 0
    for token, rank in _DEGREE_RANK:
        if token in lowered:
            best = max(best, rank)
    return best


def _required_level(analysis: JDAnalysis) -> int | None:
    for knockout in analysis.knockouts:
        if knockout.kind != "degree":
            continue
        text = knockout.text.lower()
        for token, rank in _DEGREE_RANK:
            if token in text:
                return rank
        return 3
    return None


def score_education(
    resume: Resume, analysis: JDAnalysis
) -> tuple[EducationResult, dict[str, object]]:
    levels = [_degree_level(education.studyType) for education in resume.education]
    levels.extend(_degree_level(education.area) for education in resume.education)
    degree_level = max(levels, default=0)
    required = _required_level(analysis)
    certifications = len(resume.certifications)

    result = EducationResult(
        score=100.0,
        degree_level=degree_level,
        required_level=required,
        certifications=certifications,
    )

    if required is None:
        score = 100.0
        result.notes.append("The job description does not state a hard degree requirement.")
    elif degree_level >= required:
        score = 100.0
    elif degree_level and required - degree_level == 1:
        score = 70.0
        result.notes.append("Education is one level below the stated requirement.")
    elif degree_level:
        score = 45.0
        result.notes.append("Education is materially below the stated requirement.")
    else:
        score = 25.0
        result.notes.append("No degree was detected, but the job description asks for one.")

    result.score = round(score, 2)
    return result, {
        "degree_level": degree_level,
        "required_level": required,
        "certifications": certifications,
        "education_entries": len(resume.education),
        "notes": result.notes,
        "note": "Degree level is inferred from degree keywords; verify manually.",
    }
