from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from app.schemas.jd import JDAnalysis, KnockoutCriterion, SkillRequirement
from app.services.text import content_tokens
from app.taxonomy.skills import category_for, find_skills

_MUST_CUES = (
    "must have",
    "must-have",
    "required",
    "requirements",
    "qualifications",
    "what you'll need",
    "what you need",
    "basic qualifications",
    "minimum qualifications",
    "skills and experience",
    "who you are",
)
_NICE_CUES = (
    "nice to have",
    "nice-to-have",
    "preferred",
    "bonus",
    "good to have",
    "desired",
    "plus",
)
_RESPONSIBILITY_CUES = (
    "responsibilities",
    "what you'll do",
    "what you will do",
    "the role",
    "about the role",
    "day to day",
    "day-to-day",
    "key duties",
    "you will",
)

_SENIORITY_PATTERNS: tuple[tuple[str, str], ...] = (
    ("intern", "intern"),
    ("internship", "intern"),
    ("junior", "junior"),
    ("entry level", "junior"),
    ("entry-level", "junior"),
    ("new grad", "junior"),
    ("mid level", "mid"),
    ("mid-level", "mid"),
    ("senior", "senior"),
    ("sr.", "senior"),
    ("staff", "lead"),
    ("principal", "principal"),
    ("lead", "lead"),
    ("head of", "director"),
    ("director", "director"),
    ("manager", "manager"),
)

_YEARS_RANGE_RE = re.compile(
    r"(\d{1,2})\s*(?:\+|plus)?\s*(?:-|to)\s*(\d{1,2})\s*\+?\s*(?:years|yrs)", re.IGNORECASE
)
_YEARS_SINGLE_RE = re.compile(r"(\d{1,2})\s*\+?\s*(?:years|yrs)", re.IGNORECASE)

_KNOCKOUT_PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("clearance", r"(?:security clearance|top secret|ts/sci|public trust|secret clearance)", "clearance"),
    (
        "work_authorization",
        r"(?:authori[sz]ed to work|work authori[sz]ation|no (?:visa )?sponsorship|"
        r"unable to sponsor|must be a (?:us|u\.s\.) citizen|right to work|eligible to work)",
        "work_authorization",
    ),
    (
        "degree",
        r"(?:bachelor'?s? degree|master'?s? degree|bs/ba|b\.s\.|m\.s\.|ph\.?d|"
        r"degree in [a-z ]{3,30} required|4-year degree)",
        "degree",
    ),
    (
        "location",
        r"(?:on-?site|hybrid|must (?:reside|live) in|relocation required|in-office)",
        "location",
    ),
    (
        "certification",
        r"(?:certification required|certified in|pmp|aws certified|security\+|cissp)",
        "certification",
    ),
)

_BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-*•·▪◦]|\d+[.)])\s+")


@dataclass
class _LineInfo:
    index: int
    text: str
    importance: str | None = None
    kind: str = "other"
    start: int = 0
    end: int = 0


def _classify_lines(text: str) -> tuple[list[_LineInfo], bool, bool]:
    lines: list[_LineInfo] = []
    current_importance: str | None = None
    current_kind = "other"
    saw_must_section = False
    saw_nice_section = False

    offset = 0
    for index, raw in enumerate(text.split("\n")):
        line_start = offset
        offset += len(raw) + 1
        stripped = raw.strip()
        if not stripped:
            continue
        start = line_start + raw.find(stripped)
        end = start + len(stripped)
        lowered = stripped.lower().strip(":#* ")
        if len(lowered) <= 80:
            if any(cue in lowered for cue in _RESPONSIBILITY_CUES):
                current_kind = "responsibilities"
                current_importance = None
                lines.append(_LineInfo(index, stripped, None, "heading", start, end))
                continue
            if any(cue in lowered for cue in _MUST_CUES):
                current_importance = "must"
                current_kind = "requirements"
                saw_must_section = True
                lines.append(_LineInfo(index, stripped, "must", "heading", start, end))
                continue
            if any(cue in lowered for cue in _NICE_CUES):
                current_importance = "nice"
                current_kind = "requirements"
                saw_nice_section = True
                lines.append(_LineInfo(index, stripped, "nice", "heading", start, end))
                continue
        lines.append(_LineInfo(index, stripped, current_importance, current_kind, start, end))

    return lines, saw_must_section, saw_nice_section


def _detect_seniority(text: str, title: str | None) -> str | None:
    haystack = f"{title or ''} {text[:4000]}".lower()
    for pattern, seniority in _SENIORITY_PATTERNS:
        if pattern in haystack:
            return seniority
    return None


def _detect_years(text: str) -> tuple[int | None, int | None]:
    range_match = _YEARS_RANGE_RE.search(text)
    if range_match:
        low, high = int(range_match.group(1)), int(range_match.group(2))
        return min(low, high), max(low, high)
    single = _YEARS_SINGLE_RE.search(text)
    if single:
        value = int(single.group(1))
        if 0 < value <= 30:
            return value, None
    return None, None


def _detect_knockouts(text: str) -> list[KnockoutCriterion]:
    knockouts: list[KnockoutCriterion] = []
    seen: set[str] = set()
    lowered = text.lower()
    for kind, pattern, _label in _KNOCKOUT_PATTERNS:
        match = re.search(pattern, lowered)
        if not match:
            continue
        if kind in seen:
            continue
        seen.add(kind)
        start = max(0, match.start() - 60)
        end = min(len(text), match.end() + 60)
        sentence = text[start:end].split("\n")[0].strip()
        hard = "preferred" not in lowered[start:end] and "nice to have" not in lowered[start:end]
        knockouts.append(KnockoutCriterion(kind=kind, text=sentence[:240], hard=hard))
    return knockouts


def analyse_jd(text: str, title: str | None = None, company: str | None = None) -> tuple[JDAnalysis, list[str]]:
    warnings: list[str] = []
    normalized = re.sub(r"[ \t]+", " ", text.replace("\r\n", "\n")).strip()
    if len(normalized) < 40:
        warnings.append("The job description is very short; analysis confidence is limited.")

    lines, saw_must, saw_nice = _classify_lines(normalized)
    line_bounds: list[tuple[int, int, str | None]] = [
        (info.start, info.end, info.importance) for info in lines
    ]

    matches = find_skills(normalized)

    def importance_at(position: int) -> str | None:
        for start, end, importance in line_bounds:
            if start <= position <= end:
                return importance
        return None

    by_skill: dict[str, str] = {}
    for match in matches:
        importance = importance_at(match.start)
        existing = by_skill.get(match.canonical)
        if existing == "must":
            continue
        if importance == "must" or existing is None:
            by_skill[match.canonical] = importance or "nice"
        if importance is None and existing is None:
            by_skill[match.canonical] = "nice"

    # Nothing landed in a requirements section: promote clearly demanded skills.
    if not any(value == "must" for value in by_skill.values()):
        demand_cues = (
            "required",
            "must",
            "proficien",
            "experience with",
            "knowledge of",
            "familiar with",
            "hands-on",
            "strong ",
        )
        for match in matches:
            window = normalized[max(0, match.start - 120) : match.start].lower()
            if any(cue in window for cue in demand_cues):
                by_skill[match.canonical] = "must"

    if not any(value == "must" for value in by_skill.values()) and by_skill:
        counts = Counter(match.canonical for match in matches)
        for canonical, _ in counts.most_common(8):
            by_skill[canonical] = "must"

    if not saw_must:
        warnings.append(
            "No explicit requirements section detected; must-have skills were inferred from wording."
        )
    if not saw_nice:
        warnings.append("No nice-to-have section detected.")

    must: list[SkillRequirement] = []
    nice: list[SkillRequirement] = []
    for canonical, importance in sorted(by_skill.items()):
        requirement = SkillRequirement(
            skill=canonical,
            canonical=canonical,
            importance=importance,  # type: ignore[arg-type]
            weight=2.0 if importance == "must" else 1.0,
            category=category_for(canonical),
        )
        if importance == "must":
            must.append(requirement)
        else:
            nice.append(requirement)

    if not must and not nice:
        warnings.append(
            "No known skills were detected. The score will rely on semantic overlap only."
        )

    responsibilities = [
        _BULLET_PREFIX_RE.sub("", info.text).strip()
        for info in lines
        if info.kind == "responsibilities"
        and info.kind != "heading"
        and len(info.text) > 25
        and not info.text.endswith(":")
    ]
    if not responsibilities:
        responsibilities = [
            _BULLET_PREFIX_RE.sub("", info.text).strip()
            for info in lines
            if _BULLET_PREFIX_RE.match(info.text) and len(info.text) > 30
        ][:12]

    counts = Counter(content_tokens(normalized))
    skill_tokens = {canonical.lower() for canonical in by_skill}
    keywords = [
        token
        for token, _ in counts.most_common(40)
        if len(token) >= 3 and token not in skill_tokens
    ][:25]
    domain_terms = [
        token
        for token, count in counts.most_common(80)
        if count >= 2 and len(token) >= 4 and token not in skill_tokens
    ][:15]

    years_min, years_max = _detect_years(normalized)
    detected_title = title
    if not detected_title:
        for info in lines[:3]:
            candidate = info.text.strip(" -|")
            if 2 <= len(candidate.split()) <= 8 and not candidate.endswith("."):
                detected_title = candidate
                break

    analysis = JDAnalysis(
        title=detected_title,
        company=company,
        seniority=_detect_seniority(normalized, detected_title),  # type: ignore[arg-type]
        years_min=years_min,
        years_max=years_max,
        must_have=must,
        nice_to_have=nice,
        responsibilities=responsibilities[:15],
        keywords=keywords,
        domain_terms=domain_terms,
        knockouts=_detect_knockouts(normalized),
    )
    return analysis, warnings
