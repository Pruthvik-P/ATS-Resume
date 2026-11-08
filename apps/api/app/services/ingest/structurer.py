from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.schemas.common import ParseIssue, SourceRef
from app.schemas.resume import (
    Basics,
    CertificationItem,
    EducationItem,
    LanguageItem,
    ProjectItem,
    Resume,
    SkillGroup,
    StructuringMeta,
    WorkItem,
)

_MONTH = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
_DATE_TOKEN = rf"(?:{_MONTH}\.?\s*'?\d{{2,4}}|(?:0?[1-9]|1[0-2])/\d{{4}}|\d{{4}})"
_DATE_RANGE_RE = re.compile(
    rf"({_DATE_TOKEN})\s*(?:-|to|until)\s*({_DATE_TOKEN}|present|current|now)", re.IGNORECASE
)
_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w-]+")
_PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
_URL_RE = re.compile(r"https?://[^\s)\]>,]+|(?:www\.)[^\s)\]>,]+", re.IGNORECASE)
_BULLET_RE = re.compile(r"^\s*(?:[-*•·▪◦]|\d+[.)])\s+(?P<text>.+)$")

_ROLE_WORDS = frozenset(
    ["engineer", "developer", "manager", "analyst", "intern", "lead", "consultant", "designer", "scientist", "architect", "specialist", "director", "coordinator", "associate", "administrator", "technician", "researcher", "officer", "founder", "co-founder", "head", "president", "assistant", "strategist", "marketer", "writer", "editor", "professor"]
)

_DEGREE_RE = re.compile(
    r"\b(bachelor|master|b\.?\s?tech|m\.?\s?tech|b\.?\s?sc|m\.?\s?sc|b\.?\s?e\b|m\.?\s?e\b|"
    r"ph\.?\s?d|mba|associate(?:'s)?|diploma|high school|secondary school|b\.?\s?com|m\.?\s?com)\b",
    re.IGNORECASE,
)

_SECTION_ALIASES: dict[str, set[str]] = {
    "summary": {
        "summary",
        "professional summary",
        "profile",
        "about",
        "about me",
        "objective",
        "career objective",
        "professional profile",
    },
    "experience": {
        "experience",
        "work experience",
        "professional experience",
        "employment",
        "employment history",
        "relevant experience",
        "professional background",
        "work history",
    },
    "education": {"education", "academic background", "academics", "education & training"},
    "skills": {
        "skills",
        "technical skills",
        "core skills",
        "technologies",
        "technical proficiencies",
        "skill highlights",
        "skills & tools",
        "tools & technologies",
    },
    "projects": {"projects", "personal projects", "selected projects", "side projects"},
    "certifications": {
        "certifications",
        "certificates",
        "licenses & certifications",
        "licenses and certifications",
        "certifications & licenses",
    },
    "awards": {"awards", "honors", "honours", "achievements", "awards & honors"},
    "languages": {"languages", "language proficiency"},
}


@dataclass
class _Line:
    index: int
    text: str


@dataclass
class _Sectioned:
    preamble: list[_Line] = field(default_factory=list)
    sections: dict[str, list[_Line]] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)


def _clean_inline(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u00a0", " ")).strip(" \t|")


def _normalize_heading(text: str) -> str:
    value = text.strip()
    value = re.sub(r"^#+\s*", "", value).strip("*:-—– ")
    value = re.sub(r"\s+", " ", value).strip().lower()
    return value


def _heading_key(text: str) -> str | None:
    normalized = _normalize_heading(text)
    if not normalized or len(normalized) > 45:
        return None
    for key, aliases in _SECTION_ALIASES.items():
        if normalized in aliases:
            return key
    return None


def _bullet_text(text: str) -> str | None:
    match = _BULLET_RE.match(text)
    if match:
        return _clean_inline(match.group("text"))
    return None


def sectionize(text: str) -> _Sectioned:
    sectioned = _Sectioned()
    current: str | None = None
    for index, raw in enumerate(text.splitlines()):
        line = _Line(index=index, text=raw.rstrip())
        if not line.text.strip():
            continue
        key = _heading_key(line.text)
        if key:
            current = key
            sectioned.order.append(key)
            sectioned.sections.setdefault(key, [])
            continue
        if current is None:
            sectioned.preamble.append(line)
        else:
            sectioned.sections[current].append(line)
    return sectioned


def _normalize_date(token: str) -> str:
    token = token.strip().rstrip(".")
    lowered = token.lower()
    if lowered in {"present", "current", "now"}:
        return "Present"
    month_match = re.match(rf"({_MONTH})\.?\s*'?(\d{{2,4}})", token, re.IGNORECASE)
    if month_match:
        months = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        month = months[month_match.group(1)[:3].lower()]
        year = month_match.group(2)
        if len(year) == 2:
            year = f"20{year}" if int(year) < 70 else f"19{year}"
        return f"{year}-{month:02d}"
    numeric = re.match(r"(\d{1,2})/(\d{4})", token)
    if numeric:
        return f"{numeric.group(2)}-{int(numeric.group(1)):02d}"
    year_match = re.search(r"\d{4}", token)
    return year_match.group(0) if year_match else token


def _split_header(text: str) -> list[str]:
    cleaned = _clean_inline(text)
    for separator in (" | ", " — ", " – ", " - ", " at "):
        if separator in cleaned:
            parts = [_clean_inline(part) for part in cleaned.split(separator)]
            return [part for part in parts if part]
    return [part.strip() for part in cleaned.split(",") if part.strip()]


def _looks_like_role(value: str) -> bool:
    words = set(re.findall(r"[a-z]+", value.lower()))
    return bool(words & _ROLE_WORDS)


def _assign_position_company(
    parts: list[str], existing_position: str | None = None
) -> tuple[str | None, str | None]:
    if not parts:
        return None, None
    if existing_position:
        return existing_position, parts[0]
    if len(parts) == 1:
        return parts[0], None
    if _looks_like_role(parts[0]):
        return parts[0], parts[1]
    if _looks_like_role(parts[1]):
        return parts[1], parts[0]
    return parts[0], parts[1]


def _parse_work(lines: list[_Line]) -> tuple[list[WorkItem], list[int]]:
    entries: list[dict] = []
    current: dict | None = None
    used_lines: list[int] = []

    def flush() -> None:
        nonlocal current
        if current and (current.get("name") or current.get("position")):
            entries.append(current)
        current = None

    for line in lines:
        bullet = _bullet_text(line.text)
        if bullet is not None:
            if current is None:
                current = {"highlights": []}
            current.setdefault("highlights", []).append(bullet)
            used_lines.append(line.index)
            continue
        cleaned = _clean_inline(line.text)
        if not cleaned:
            continue
        date_match = _DATE_RANGE_RE.search(cleaned)
        if date_match and len(cleaned) <= 220:
            flush()
            remainder = _clean_inline(cleaned[: date_match.start()] + " " + cleaned[date_match.end() :])
            parts = _split_header(remainder)
            position, name = _assign_position_company(parts)
            current = {
                "position": position,
                "name": name,
                "startDate": _normalize_date(date_match.group(1)),
                "endDate": _normalize_date(date_match.group(2)),
                "highlights": [],
            }
            if len(parts) > 2:
                current["location"] = parts[2]
            used_lines.append(line.index)
            continue
        if current is None:
            continue
        if current.get("name") is None and not current.get("highlights"):
            current["name"] = cleaned
            used_lines.append(line.index)
        elif len(cleaned) <= 90 and not cleaned.endswith(".") and not current.get("highlights"):
            current["position"] = current.get("position") or cleaned
            used_lines.append(line.index)
        else:
            current.setdefault("highlights", []).append(cleaned)
            used_lines.append(line.index)
    flush()

    work: list[WorkItem] = []
    for entry in entries:
        highlights = [highlight for highlight in entry.get("highlights", []) if highlight]
        work.append(
            WorkItem(
                name=entry.get("name"),
                position=entry.get("position"),
                startDate=entry.get("startDate"),
                endDate=entry.get("endDate"),
                location=entry.get("location"),
                highlights=highlights,
            )
        )
    return work, used_lines


def _parse_education(lines: list[_Line]) -> list[EducationItem]:
    entries: list[EducationItem] = []
    for line in lines:
        cleaned = _clean_inline(line.text)
        if not cleaned:
            continue
        has_degree = bool(_DEGREE_RE.search(cleaned))
        has_institution = bool(
            re.search(r"university|college|institute|school|academy", cleaned, re.IGNORECASE)
        )
        if not has_degree and not has_institution:
            continue
        date_match = _DATE_RANGE_RE.search(cleaned)
        dates: tuple[str | None, str | None] = (None, None)
        if date_match:
            dates = (_normalize_date(date_match.group(1)), _normalize_date(date_match.group(2)))
            cleaned = _clean_inline(cleaned[: date_match.start()] + " " + cleaned[date_match.end() :])
        else:
            year = _YEAR_RE.search(cleaned)
            if year:
                dates = (None, year.group(1))
                cleaned = _clean_inline(cleaned.replace(year.group(0), "", 1))

        degree_match = _DEGREE_RE.search(cleaned)
        study_type = degree_match.group(0) if degree_match else None
        area = None
        area_match = re.search(r"\bin\s+([A-Za-z][A-Za-z &/-]{2,60})", cleaned)
        if area_match:
            area = _clean_inline(area_match.group(1)).strip(" ,.-")
            cleaned = _clean_inline(cleaned.replace(area_match.group(0), "", 1))
        institution = None
        for part in re.split(r"\s*\|\s*|\s+[-—–]\s+|,\s*", cleaned):
            candidate = _clean_inline(part)
            if not candidate:
                continue
            if re.search(
                r"university|college|institute|school|academy", candidate, re.IGNORECASE
            ):
                institution = candidate
                break
        if institution is None:
            parts = [part for part in re.split(r"\s*\|\s*|\s+[-—–]\s+", cleaned) if part.strip()]
            institution = _clean_inline(parts[-1]) if parts else None
        entries.append(
            EducationItem(
                institution=institution,
                studyType=study_type,
                area=area,
                startDate=dates[0],
                endDate=dates[1],
            )
        )
    return entries


def _parse_skills(lines: list[_Line]) -> list[SkillGroup]:
    groups: list[SkillGroup] = []
    loose: list[str] = []
    for line in lines:
        cleaned = _clean_inline(line.text)
        if not cleaned:
            continue
        if ":" in cleaned:
            name, _, values = cleaned.partition(":")
            keywords = [
                _clean_inline(value)
                for value in re.split(r"[,;|•·]", values)
                if _clean_inline(value)
            ]
            if keywords:
                groups.append(SkillGroup(name=_clean_inline(name) or "Skills", keywords=keywords))
                continue
        loose.extend(
            _clean_inline(value)
            for value in re.split(r"[,;|•·]", cleaned)
            if _clean_inline(value)
        )
    if loose:
        groups.append(SkillGroup(name="Skills", keywords=loose))
    return groups


def _parse_projects(lines: list[_Line]) -> list[ProjectItem]:
    projects: list[ProjectItem] = []
    current: ProjectItem | None = None
    for line in lines:
        bullet = _bullet_text(line.text)
        if bullet is not None:
            if current is None:
                current = ProjectItem(highlights=[])
            current.highlights.append(bullet)
            continue
        cleaned = _clean_inline(line.text)
        if not cleaned:
            continue
        if current and current.name and len(cleaned) > 90:
            current.description = (current.description + " " + cleaned).strip() if current.description else cleaned
        else:
            if current and current.name:
                projects.append(current)
            current = ProjectItem(name=cleaned, highlights=[])
    if current and current.name:
        projects.append(current)
    return projects


def _parse_certifications(lines: list[_Line]) -> list[CertificationItem]:
    items: list[CertificationItem] = []
    for line in lines:
        cleaned = _clean_inline(line.text)
        if not cleaned:
            continue
        year = _YEAR_RE.search(cleaned)
        date = year.group(1) if year else None
        name = _clean_inline(cleaned.replace(year.group(0), "", 1)) if year else cleaned
        items.append(CertificationItem(name=name.strip(" ,-|"), date=date))
    return items


def _parse_languages(lines: list[_Line]) -> list[LanguageItem]:
    items: list[LanguageItem] = []
    for line in lines:
        cleaned = _clean_inline(line.text)
        if not cleaned:
            continue
        match = re.match(r"([A-Za-z][A-Za-z ]+?)\s*[\(\-–—]\s*(.+?)\)?$", cleaned)
        if match:
            items.append(LanguageItem(language=match.group(1).strip(), fluency=match.group(2).strip()))
        else:
            items.append(LanguageItem(language=cleaned))
    return items


def _first_plausible_name(preamble: list[_Line]) -> tuple[str | None, int | None]:
    for line in preamble:
        cleaned = _clean_inline(line.text)
        if not cleaned or len(cleaned) > 60:
            continue
        if _EMAIL_RE.search(cleaned) or _URL_RE.search(cleaned):
            continue
        if sum(char.isdigit() for char in cleaned) > 0:
            continue
        if _heading_key(cleaned):
            continue
        words = cleaned.split()
        if 1 <= len(words) <= 6:
            return cleaned.strip("|, "), line.index
    return None, None


def structure_resume(text: str) -> tuple[Resume, dict[str, SourceRef], list[ParseIssue], StructuringMeta]:
    normalized_text = text.replace("–", "-").replace("—", "-")
    sectioned = sectionize(normalized_text)
    issues: list[ParseIssue] = []
    source_map: dict[str, SourceRef] = {}

    name, name_line = _first_plausible_name(sectioned.preamble)
    email_match = _EMAIL_RE.search(normalized_text)
    phone_match = _PHONE_RE.search(normalized_text)
    urls = _URL_RE.findall(normalized_text)

    if name:
        source_map["basics.name"] = SourceRef(
            kind="text_offset", line=name_line, quote=name, confidence=0.85
        )
    if email_match:
        source_map["basics.email"] = SourceRef(
            kind="text_offset", line=1, quote=email_match.group(0), confidence=0.97
        )
    if phone_match:
        source_map["basics.phone"] = SourceRef(
            kind="text_offset", line=1, quote=phone_match.group(0), confidence=0.9
        )

    basics = Basics(
        name=name,
        email=email_match.group(0) if email_match else None,
        phone=phone_match.group(0).strip() if phone_match else None,
        url=next((url for url in urls if "linkedin" not in url.lower()), None),
    )
    profiles = []
    for url in urls:
        lowered = url.lower()
        if "linkedin" in lowered:
            profiles.append({"network": "LinkedIn", "url": url})
        elif "github" in lowered:
            profiles.append({"network": "GitHub", "url": url})
    if profiles:
        from app.schemas.resume import Profile

        basics.profiles = [Profile(**profile) for profile in profiles]

    location_match = re.search(
        r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)?),\s*([A-Z]{2}|[A-Z][a-z]+)\b", normalized_text[:600]
    )
    if location_match:
        from app.schemas.resume import Location

        basics.location = Location(city=location_match.group(1), region=location_match.group(2))

    if "summary" in sectioned.sections:
        summary = " ".join(
            _clean_inline(line.text) for line in sectioned.sections["summary"]
        ).strip()
        if summary:
            basics.summary = summary
            source_map["basics.summary"] = SourceRef(
                kind="text_offset",
                line=sectioned.sections["summary"][0].index,
                quote=summary[:120],
                confidence=0.7,
            )

    work: list[WorkItem] = []
    work_lines: list[int] = []
    if "experience" in sectioned.sections:
        work, work_lines = _parse_work(sectioned.sections["experience"])
    education = _parse_education(sectioned.sections.get("education", []))
    skills = _parse_skills(sectioned.sections.get("skills", []))
    projects = _parse_projects(sectioned.sections.get("projects", []))
    certifications = _parse_certifications(sectioned.sections.get("certifications", []))

    resume = Resume(
        basics=basics,
        work=work,
        education=education,
        skills=skills,
        projects=projects,
        certifications=certifications,
    )

    for index, item in enumerate(work):
        if item.startDate or item.endDate:
            source_map[f"work[{index}]"] = SourceRef(
                kind="text_offset",
                line=work_lines[index] if index < len(work_lines) else None,
                quote=" | ".join(filter(None, [item.position, item.name])),
                confidence=0.6,
            )

    # --- Quality signals -------------------------------------------------
    if not basics.name:
        issues.append(
            ParseIssue(
                code="missing_name",
                severity="error",
                message="Could not identify a candidate name. ATS field extraction will fail.",
            )
        )
    if not basics.email:
        issues.append(
            ParseIssue(
                code="missing_email",
                severity="warning",
                message="No email address found in the resume text.",
            )
        )
    if not work:
        issues.append(
            ParseIssue(
                code="missing_experience",
                severity="warning",
                message="No work experience entries were detected. Check section headings and date formats.",
            )
        )
    if work and not any(entry.startDate or entry.endDate for entry in work):
        issues.append(
            ParseIssue(
                code="dates_not_parsed",
                severity="warning",
                message="Experience entries were found but no dates could be parsed.",
                auto_fixable=True,
            )
        )
    if not skills:
        issues.append(
            ParseIssue(
                code="missing_skills_section",
                severity="info",
                message="No skills section was detected.",
            )
        )

    words = len(normalized_text.split())
    if words < 120:
        issues.append(
            ParseIssue(
                code="resume_too_short",
                severity="warning",
                message=f"Only {words} words were extracted. The file may be incomplete or image-based.",
            )
        )

    confidence = 0.0
    confidence += 0.25 if basics.name else 0.0
    confidence += 0.2 if basics.email else 0.0
    confidence += 0.2 if work and any(entry.highlights for entry in work) else 0.0
    confidence += 0.1 if education else 0.0
    confidence += 0.1 if skills else 0.0
    confidence += 0.15 if work and any(entry.startDate for entry in work) else 0.0
    confidence = round(min(1.0, confidence), 2)

    if confidence < 0.6:
        issues.append(
            ParseIssue(
                code="low_structuring_confidence",
                severity="warning",
                message=(
                    f"Heuristic structuring confidence is {confidence:.0%}. "
                    "Review the parsed fields before scoring."
                ),
            )
        )

    structuring = StructuringMeta(
        method="heuristic",
        confidence=confidence,
        model="deterministic-heuristic-v1",
        prompt_version="n/a",
    )
    return resume, source_map, issues, structuring


def resume_stats(resume: Resume) -> tuple[int, int]:
    bullets = sum(len(work.highlights) for work in resume.work) + sum(
        len(project.highlights) for project in resume.projects
    )
    words = len(
        " ".join(
            filter(
                None,
                [
                    resume.basics.summary or "",
                    *[highlight for work in resume.work for highlight in work.highlights],
                ],
            )
        ).split()
    ) + sum(
        len(f"{work.position or ''} {work.name or ''}".split()) for work in resume.work
    )
    return bullets, words
