from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from app.schemas.jd import JDAnalysis
from app.schemas.resume import Resume

_SENIORITY_RANK = {
    "intern": 0,
    "junior": 1,
    "mid": 2,
    "senior": 3,
    "lead": 4,
    "manager": 4,
    "principal": 5,
    "director": 5,
}

_TITLE_SENIORITY: tuple[tuple[str, str], ...] = (
    ("intern", "intern"),
    ("junior", "junior"),
    ("associate", "junior"),
    ("senior", "senior"),
    ("staff", "lead"),
    ("lead", "lead"),
    ("principal", "principal"),
    ("manager", "manager"),
    ("head", "director"),
    ("director", "director"),
    ("vp", "director"),
    ("chief", "director"),
)

_LEADERSHIP_RE = re.compile(
    r"\b(?:led|lead|managed|mentored|coached|owned|directed|supervised|"
    r"cross-functional|stakeholders|hired|grew the team)\b",
    re.IGNORECASE,
)

_MONTH_RE = re.compile(r"(\d{4})(?:-(\d{1,2}))?")


@dataclass
class ExperienceResult:
    score: float
    total_years: float = 0.0
    seniority: str | None = None
    last_role_end: str | None = None
    leadership_signals: int = 0
    notes: list[str] = field(default_factory=list)


def _month_index(value: str | None) -> int | None:
    if not value:
        return None
    lowered = value.strip().lower()
    if lowered in {"present", "current", "now"}:
        today = date.today()
        return today.year * 12 + today.month
    match = _MONTH_RE.search(value)
    if not match:
        return None
    year = int(match.group(1))
    month = int(match.group(2) or 1)
    if not 1 <= month <= 12:
        month = 1
    return year * 12 + month


def total_experience_months(resume: Resume) -> float:
    intervals: list[tuple[int, int]] = []
    for work in resume.work:
        start = _month_index(work.startDate)
        end = _month_index(work.endDate) or _month_index("present")
        if start is None:
            continue
        if end is None or end < start:
            end = start
        intervals.append((start, end))
    if not intervals:
        return 0.0
    intervals.sort()
    merged: list[list[int]] = [list(intervals[0])]
    for start, end in intervals[1:]:
        if start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return float(sum(end - start for start, end in merged))


def _resume_seniority(resume: Resume) -> str | None:
    best: str | None = None
    best_rank = -1
    for work in resume.work:
        title = (work.position or "").lower()
        for token, seniority in _TITLE_SENIORITY:
            if token in title and _SENIORITY_RANK[seniority] > best_rank:
                best = seniority
                best_rank = _SENIORITY_RANK[seniority]
    if best:
        return best
    if resume.work:
        return "mid"
    return None


def _last_end(resume: Resume) -> str | None:
    ends = [_month_index(work.endDate) for work in resume.work]
    known = [value for value in ends if value is not None]
    if not known:
        return None
    latest = max(known)
    if latest >= date.today().year * 12 + date.today().month:
        return "Present"
    return f"{latest // 12}-{latest % 12 or 12:02d}"


def score_experience(
    resume: Resume, analysis: JDAnalysis
) -> tuple[ExperienceResult, dict[str, object]]:
    months = total_experience_months(resume)
    years = round(months / 12, 1)
    detected_seniority = _resume_seniority(resume)
    last_end = _last_end(resume)

    if analysis.years_min:
        years_score = min(100.0, years / max(analysis.years_min, 1) * 100)
    else:
        years_score = min(100.0, 55 + years * 5)

    if analysis.seniority and detected_seniority:
        required_rank = _SENIORITY_RANK.get(analysis.seniority, 2)
        actual_rank = _SENIORITY_RANK.get(detected_seniority, 2)
        gap = actual_rank - required_rank
        if gap >= 0:
            seniority_score = 100.0 if gap == 0 else 88.0
        elif gap == -1:
            seniority_score = 72.0
        elif gap == -2:
            seniority_score = 48.0
        else:
            seniority_score = 30.0
    else:
        seniority_score = 75.0

    months_since_end: int | None = None
    if last_end == "Present":
        recency_score = 100.0
    elif last_end:
        year, month = last_end.split("-")
        months_since_end = (
            (date.today().year - int(year)) * 12 + (date.today().month - int(month))
        )
        if months_since_end <= 6:
            recency_score = 100.0
        elif months_since_end <= 18:
            recency_score = 85.0
        elif months_since_end <= 36:
            recency_score = 65.0
        else:
            recency_score = 45.0
    else:
        recency_score = 40.0

    bullets = [highlight for work in resume.work for highlight in work.highlights]
    leadership_signals = sum(1 for bullet in bullets if _LEADERSHIP_RE.search(bullet))
    needs_leadership = analysis.seniority in {"senior", "lead", "principal", "manager", "director"}
    if needs_leadership:
        leadership_score = min(100.0, 45 + leadership_signals * 18)
    else:
        leadership_score = min(100.0, 70 + leadership_signals * 5)

    score = (
        years_score * 0.45
        + seniority_score * 0.25
        + recency_score * 0.15
        + leadership_score * 0.15
    )
    result = ExperienceResult(
        score=round(score, 2),
        total_years=years,
        seniority=detected_seniority,
        last_role_end=last_end,
        leadership_signals=leadership_signals,
    )
    if analysis.years_min and years < analysis.years_min:
        result.notes.append(
            f"Detected about {years} years of experience against a {analysis.years_min}-year requirement."
        )
    if not resume.work:
        result.notes.append("No dated work history was parsed, so experience fit is a weak estimate.")

    return result, {
        "total_years": years,
        "required_years_min": analysis.years_min,
        "required_years_max": analysis.years_max,
        "roles": len(resume.work),
        "seniority_detected": detected_seniority,
        "seniority_required": analysis.seniority,
        "last_role_end": last_end,
        "months_since_last_role": months_since_end,
        "leadership_signals": leadership_signals,
        "subscores": {
            "years": round(years_score, 1),
            "seniority": round(seniority_score, 1),
            "recency": round(recency_score, 1),
            "leadership": round(leadership_score, 1),
        },
        "notes": result.notes,
    }
