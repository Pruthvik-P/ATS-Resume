from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.schemas.resume import ResumeDocument

_HEADING_GROUPS = {
    "experience": ("experience", "work experience", "employment", "professional experience"),
    "education": ("education", "academic"),
    "skills": ("skills", "technical skills", "technologies"),
    "projects": ("projects", "selected projects"),
}

_SEVERITY_PENALTY = {"error": 14.0, "warning": 5.0, "info": 1.0}


@dataclass
class ParseabilityResult:
    score: float
    field_recall: float = 0.0
    missing_fields: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    headings_found: list[str] = field(default_factory=list)


def _tokens_present(text: str, value: str) -> bool:
    tokens = [token for token in re.findall(r"[A-Za-z0-9+#.]{2,}", value.lower())]
    if not tokens:
        return False
    return all(token in text for token in tokens)


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def score_parseability(document: ResumeDocument) -> tuple[ParseabilityResult, dict[str, object]]:
    resume = document.canonical
    raw = document.raw_text or ""
    lowered = raw.lower()
    checks: list[tuple[str, bool, float]] = []

    if resume.basics.name:
        checks.append(("name", _tokens_present(lowered, resume.basics.name), 1.5))
    if resume.basics.email:
        checks.append(("email", resume.basics.email.lower() in lowered, 1.5))
    if resume.basics.phone:
        phone_digits = _digits(resume.basics.phone)
        checks.append(("phone", phone_digits[-7:] in _digits(raw) if phone_digits else False, 1.0))
    if resume.basics.url:
        checks.append(("website", resume.basics.url.lower() in lowered, 0.5))

    for index, work in enumerate(resume.work):
        if work.position:
            checks.append((f"work[{index}].position", _tokens_present(lowered, work.position), 0.8))
        if work.name:
            checks.append((f"work[{index}].company", _tokens_present(lowered, work.name), 0.8))
        if work.startDate:
            year = re.search(r"\d{4}", work.startDate)
            if year:
                checks.append((f"work[{index}].start_date", year.group(0) in raw, 0.4))

    for index, education in enumerate(resume.education):
        if education.institution:
            checks.append(
                (f"education[{index}].institution", _tokens_present(lowered, education.institution), 0.6)
            )
        if education.studyType:
            checks.append(
                (f"education[{index}].study_type", _tokens_present(lowered, education.studyType), 0.4)
            )

    skill_keywords = [keyword for group in resume.skills for keyword in group.keywords]
    if skill_keywords:
        present = sum(1 for keyword in skill_keywords if keyword.lower() in lowered)
        ratio = present / len(skill_keywords)
        checks.append(("skills_list", ratio >= 0.6, 0.8))

    total_weight = sum(weight for _, _, weight in checks)
    earned = sum(weight for _, present, weight in checks if present)
    field_recall = 100 * earned / total_weight if total_weight else 0.0
    missing_fields = [name for name, present, _ in checks if not present]

    headings_found = [
        key
        for key, aliases in _HEADING_GROUPS.items()
        if any(alias in lowered for alias in aliases)
    ]
    expected_headings = [key for key, present in (
        ("experience", bool(resume.work)),
        ("education", bool(resume.education)),
        ("skills", bool(resume.skills)),
        ("projects", bool(resume.projects)),
    ) if present]
    heading_ratio = (
        len([key for key in headings_found if key in expected_headings]) / len(expected_headings)
        if expected_headings
        else 0.5
    )

    contact_block = raw[:600].lower()
    contact_in_header = bool(
        (resume.basics.email and resume.basics.email.lower() in contact_block)
        or (resume.basics.phone and _digits(resume.basics.phone)[-7:] in _digits(contact_block))
    )
    layout_score = (heading_ratio * 60) + (40 if contact_in_header else 0)

    issues = [issue for issue in document.issues if issue.severity in _SEVERITY_PENALTY]
    penalty = sum(_SEVERITY_PENALTY[issue.severity] for issue in issues)
    issue_quality = max(0.0, 100.0 - penalty)

    score = field_recall * 0.55 + layout_score * 0.25 + issue_quality * 0.20

    # A missing name or email means several ATS vendors drop the record entirely.
    if resume.basics.name is None or resume.basics.email is None:
        score = min(score, 55.0)

    result = ParseabilityResult(
        score=round(max(0.0, min(100.0, score)), 2),
        field_recall=round(field_recall, 1),
        missing_fields=missing_fields,
        issues=[f"{issue.severity}: {issue.message}" for issue in issues][:12],
        headings_found=headings_found,
    )
    return result, {
        "field_recall": round(field_recall, 1),
        "missing_fields": missing_fields,
        "headings_found": headings_found,
        "contact_in_header": contact_in_header,
        "issue_penalty": round(penalty, 1),
        "issues": result.issues,
        "extractor_note": (
            "Parse fidelity is measured against the text this engine extracted. "
            "Different ATS vendors may extract differently."
        ),
    }
