from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.schemas.resume import Resume
from app.services.text import ACTION_VERBS, WEAK_PHRASES

_METRIC_RE = re.compile(
    r"(?:\b\d[\d,.]*\s*(?:%|percent|x|k|m|bn|million|billion|users|customers|requests|"
    r"ms|seconds|minutes|hours|days|weeks|months|people|engineers|services|teams)\b)"
    r"|(?:\$\s?\d)"
    r"|(?:\b\d[\d,.]*\b)",
    re.IGNORECASE,
)


@dataclass
class BulletAssessment:
    index: int
    text: str
    points: int
    has_action_verb: bool
    has_metric: bool
    good_length: bool
    has_weak_phrase: bool

    @property
    def issues(self) -> list[str]:
        problems: list[str] = []
        if not self.has_action_verb:
            problems.append("does not start with a strong action verb")
        if not self.has_metric:
            problems.append("has no measurable result")
        if not self.good_length:
            problems.append("length is outside the 40-220 character range")
        if self.has_weak_phrase:
            problems.append("uses a weak phrase")
        return problems


@dataclass
class ImpactResult:
    score: float
    bullets: list[BulletAssessment] = field(default_factory=list)
    weak_bullet_indexes: list[int] = field(default_factory=list)
    quantification_ratio: float = 0.0


def score_impact(resume: Resume) -> tuple[ImpactResult, dict[str, object]]:
    texts = [
        highlight
        for work in resume.work
        for highlight in work.highlights
        if highlight.strip()
    ] + [
        highlight
        for project in resume.projects
        for highlight in project.highlights
        if highlight.strip()
    ]

    result = ImpactResult(score=0.0)
    if not texts:
        return result, {
            "bullets": 0,
            "weak_bullets": [],
            "quantification_ratio": 0.0,
            "note": "No experience bullets were found to assess.",
        }

    for index, text in enumerate(texts, start=1):
        lowered = text.lower()
        words = re.findall(r"[a-z]+", lowered)
        first_word = words[0] if words else ""
        has_action_verb = first_word in ACTION_VERBS
        has_metric = bool(_METRIC_RE.search(text))
        good_length = 40 <= len(text) <= 220
        has_weak_phrase = any(phrase in lowered for phrase in WEAK_PHRASES)
        points = sum([has_action_verb, has_metric, good_length, not has_weak_phrase])
        assessment = BulletAssessment(
            index=index,
            text=text,
            points=points,
            has_action_verb=has_action_verb,
            has_metric=has_metric,
            good_length=good_length,
            has_weak_phrase=has_weak_phrase,
        )
        result.bullets.append(assessment)
        if points <= 2:
            result.weak_bullet_indexes.append(index)

    result.quantification_ratio = round(
        sum(1 for bullet in result.bullets if bullet.has_metric) / len(result.bullets), 2
    )
    result.score = round(
        100 * sum(bullet.points for bullet in result.bullets) / (4 * len(result.bullets)), 2
    )
    details: dict[str, object] = {
        "bullets": len(result.bullets),
        "weak_bullets": result.weak_bullet_indexes,
        "quantification_ratio": result.quantification_ratio,
        "action_verb_ratio": round(
            sum(1 for bullet in result.bullets if bullet.has_action_verb) / len(result.bullets), 2
        ),
        "assessments": [
            {
                "index": bullet.index,
                "points": bullet.points,
                "issues": bullet.issues,
                "excerpt": bullet.text[:160],
            }
            for bullet in result.bullets
        ],
    }
    return result, details
