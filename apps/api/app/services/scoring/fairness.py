"""Fairness controls for scoring.

Parseability must see the real name/contact block (that is a legitimate ATS
signal). Semantic/keyword/impact/readability scoring, however, should not see
protected identity signals. This module builds an anonymised scoring view and
records exactly what was removed for auditability.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.config import settings
from app.schemas.resume import Resume

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "gender_pronouns",
        re.compile(r"\b(?:he|she|him|her|his|hers|himself|herself)\b", re.IGNORECASE),
    ),
    (
        "age",
        re.compile(
            r"\b(?:age\s*[:\-]?\s*\d{1,3}|\d{1,2}\s*[- ]?(?:year|yr)s?\s*old|"
            r"date of birth|dob\s*[:\-]?\s*\d{1,4})\b",
            re.IGNORECASE,
        ),
    ),
    (
        "nationality_or_status",
        re.compile(
            r"\b(?:nationality|citizenship|visa status|race|ethnicity|religion|"
            r"marital status|gender|sex)\s*[:\-]\s*[^\n,.;]{1,60}",
            re.IGNORECASE,
        ),
    ),
    (
        "marital_status",
        re.compile(r"\b(?:married|divorced|widowed)\b", re.IGNORECASE),
    ),
    (
        "photo",
        re.compile(r"\b(?:photo|headshot|portrait|passport photo)\b", re.IGNORECASE),
    ),
    (
        "postal_address",
        re.compile(
            r"\b\d{1,6}\s+[A-Za-z][A-Za-z .'-]{1,40}\s+"
            r"(?:street|st\.?|avenue|ave\.?|road|rd\.?|boulevard|blvd\.?|lane|ln\.?)\b",
            re.IGNORECASE,
        ),
    ),
)

_REDACTED = "[redacted]"


@dataclass
class FairnessView:
    resume: Resume
    redactions: dict[str, int] = field(default_factory=dict)
    contact_removed: bool = False

    @property
    def audit(self) -> dict[str, object]:
        return {
            "enabled": True,
            "contact_removed": self.contact_removed,
            "redactions": self.redactions,
            "total_redactions": sum(self.redactions.values()),
            "note": (
                "Name, contact details, location, profiles, and protected-attribute "
                "phrases were removed from the scoring view. Parseability still uses "
                "the original document."
            ),
        }


def redact_text(text: str) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}
    redacted = text
    for label, pattern in _PATTERNS:
        matches = pattern.findall(redacted)
        if matches:
            counts[label] = counts.get(label, 0) + len(matches)
            redacted = pattern.sub(_REDACTED, redacted)
    return redacted, counts


def anonymise_resume(resume: Resume) -> FairnessView:
    copy = resume.model_copy(deep=True)
    redactions: dict[str, int] = {}

    if copy.basics.summary:
        copy.basics.summary, counts = redact_text(copy.basics.summary)
        _merge_counts(redactions, counts)
    for work in copy.work:
        if work.summary:
            work.summary, counts = redact_text(work.summary)
            _merge_counts(redactions, counts)
        work.highlights = [
            _redact_into(highlight, redactions) for highlight in work.highlights
        ]
    for project in copy.projects:
        if project.description:
            project.description, counts = redact_text(project.description)
            _merge_counts(redactions, counts)
        project.highlights = [
            _redact_into(highlight, redactions) for highlight in project.highlights
        ]
    for award in copy.awards:
        if award.summary:
            award.summary, counts = redact_text(award.summary)
            _merge_counts(redactions, counts)

    contact_removed = bool(
        copy.basics.name
        or copy.basics.email
        or copy.basics.phone
        or copy.basics.url
        or copy.basics.image
        or copy.basics.profiles
        or copy.basics.location
    )
    copy.basics.name = None
    copy.basics.email = None
    copy.basics.phone = None
    copy.basics.url = None
    copy.basics.image = None
    copy.basics.profiles = []
    copy.basics.location = None
    return FairnessView(
        resume=copy, redactions=redactions, contact_removed=contact_removed
    )


def _redact_into(text: str, counts: dict[str, int]) -> str:
    redacted, new_counts = redact_text(text)
    _merge_counts(counts, new_counts)
    return redacted


def _merge_counts(target: dict[str, int], source: dict[str, int]) -> None:
    for key, value in source.items():
        target[key] = target.get(key, 0) + value


def scoring_view(resume: Resume) -> FairnessView:
    if not settings.fairness_redaction_enabled:
        return FairnessView(resume=resume)
    return anonymise_resume(resume)


__all__ = ["FairnessView", "anonymise_resume", "redact_text", "scoring_view"]
