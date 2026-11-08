from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.jd import JDAnalysis, SkillRequirement
from app.schemas.resume import Resume
from app.services.scoring.embedding import LEXICAL_FALLBACK_THRESHOLD, similarity
from app.services.text import contains_phrase
from app.taxonomy.skills import find_skills

EXACT_CREDIT = 1.0
ALIAS_CREDIT = 0.95
SEMANTIC_CREDIT = 0.60
SKILLS_ONLY_MULTIPLIER = 0.7


@dataclass
class SkillEvidence:
    skill: str
    credit: float
    location: str
    evidence: str


@dataclass
class KeywordResult:
    score: float
    matched: list[str] = field(default_factory=list)
    missing_must_have: list[str] = field(default_factory=list)
    missing_nice_to_have: list[str] = field(default_factory=list)
    evidence: list[SkillEvidence] = field(default_factory=list)
    semantic_fallback_used: bool = False


def _bullet_index(resume: Resume) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    if resume.basics.summary:
        items.append(("summary", resume.basics.summary))
    for work_index, work in enumerate(resume.work):
        for highlight_index, highlight in enumerate(work.highlights):
            items.append((f"work[{work_index}].highlights[{highlight_index}]", highlight))
    for project_index, project in enumerate(resume.projects):
        for highlight_index, highlight in enumerate(project.highlights):
            items.append(
                (f"projects[{project_index}].highlights[{highlight_index}]", highlight)
            )
    return items


def _skills_list_text(resume: Resume) -> str:
    return " ".join(
        f"{group.name or ''} {', '.join(group.keywords)}".strip() for group in resume.skills
    )


def _match_requirement(
    requirement: SkillRequirement,
    resume: Resume,
    bullets: list[tuple[str, str]],
    skills_text: str,
) -> SkillEvidence | None:
    canonical = requirement.canonical

    # 1. Evidence in experience/project bullets (highest credit).
    for location, text in bullets:
        matches = find_skills(text)
        for match in matches:
            if match.canonical != canonical:
                continue
            credit = EXACT_CREDIT if match.exact else ALIAS_CREDIT
            is_list_only = location == "skills"
            if is_list_only:
                credit *= SKILLS_ONLY_MULTIPLIER
            return SkillEvidence(
                skill=canonical,
                credit=round(credit, 3),
                location=location,
                evidence=text[:200],
            )

    # 2. Mentioned in the skills list only → discounted per doc §4.3.
    if contains_phrase(skills_text, canonical) or any(
        match.canonical == canonical for match in find_skills(skills_text)
    ):
        return SkillEvidence(
            skill=canonical,
            credit=round(EXACT_CREDIT * SKILLS_ONLY_MULTIPLIER, 3),
            location="skills_list",
            evidence="Listed in the skills section without supporting experience evidence.",
        )

    # 3. Semantic fallback for paraphrases ("container orchestration" → Kubernetes).
    best_similarity = 0.0
    best_text = ""
    for _location, text in bullets:
        value = similarity(text, canonical)
        if value > best_similarity:
            best_similarity = value
            best_text = text
    if best_similarity >= LEXICAL_FALLBACK_THRESHOLD:
        return SkillEvidence(
            skill=canonical,
            credit=round(SEMANTIC_CREDIT * best_similarity / max(LEXICAL_FALLBACK_THRESHOLD, 1e-6) / 2, 3),
            location="semantic_fallback",
            evidence=best_text[:200],
        )
    return None


def score_keywords(
    resume: Resume, analysis: JDAnalysis
) -> tuple[KeywordResult, dict[str, object]]:
    bullets = _bullet_index(resume)
    skills_text = _skills_list_text(resume)
    requirements = [*analysis.must_have, *analysis.nice_to_have]

    total_weight = 0.0
    earned = 0.0
    result = KeywordResult(score=0.0)

    for requirement in requirements:
        weight = 2.0 if requirement.importance == "must" else 1.0
        total_weight += weight
        evidence = _match_requirement(requirement, resume, bullets, skills_text)
        if evidence is None:
            if requirement.importance == "must":
                result.missing_must_have.append(requirement.canonical)
            else:
                result.missing_nice_to_have.append(requirement.canonical)
            continue
        earned += weight * evidence.credit
        result.matched.append(requirement.canonical)
        result.evidence.append(evidence)
        if evidence.location == "semantic_fallback":
            result.semantic_fallback_used = True

    result.score = round(100 * earned / total_weight, 2) if total_weight else 0.0
    details: dict[str, object] = {
        "matched": result.matched,
        "missing_must_have": result.missing_must_have,
        "missing_nice_to_have": result.missing_nice_to_have,
        "evidence": [
            {
                "skill": item.skill,
                "credit": item.credit,
                "location": item.location,
                "evidence": item.evidence,
            }
            for item in result.evidence
        ],
        "requirements_considered": len(requirements),
        "skills_list_only_multiplier": SKILLS_ONLY_MULTIPLIER,
        "semantic_fallback": result.semantic_fallback_used,
    }
    return result, details
