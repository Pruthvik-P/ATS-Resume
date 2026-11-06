from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.schemas.resume import Resume
from app.services.text import ACTION_VERBS, flesch_reading_ease, split_sentences, tokenize

_PASSIVE_RE = re.compile(r"\b(?:was|were|been|being|is|are)\s+\w+ed\b", re.IGNORECASE)


@dataclass
class ReadabilityResult:
    score: float
    flesch: float = 0.0
    avg_words_per_sentence: float = 0.0
    action_start_ratio: float = 0.0
    passive_ratio: float = 0.0
    notes: list[str] = field(default_factory=list)


def _flesch_score(value: float) -> float:
    """45-75 is a comfortable resume band; penalise both extremes."""

    if 45 <= value <= 75:
        return 100.0
    if value < 45:
        return max(0.0, 100 - (45 - value) * 2.2)
    return max(0.0, 100 - (value - 75) * 2.0)


def score_readability(resume: Resume) -> tuple[ReadabilityResult, dict[str, object]]:
    bullets = [highlight for work in resume.work for highlight in work.highlights]
    body = " ".join(filter(None, [resume.basics.summary or "", *bullets])).strip()
    if not body:
        return ReadabilityResult(score=0.0), {
            "note": "No summary or bullets to assess.",
            "flesch": 0.0,
        }

    sentences = split_sentences(body)
    words = tokenize(body)
    avg_words = len(words) / max(1, len(sentences))
    flesch = flesch_reading_ease(body)

    if 10 <= avg_words <= 24:
        length_score = 100.0
    elif avg_words < 10:
        length_score = 80.0
    else:
        length_score = max(0.0, 100 - (avg_words - 24) * 4)

    action_starts = 0
    for bullet in bullets:
        match = re.match(r"\s*([A-Za-z]+)", bullet)
        if match and match.group(1).lower() in ACTION_VERBS:
            action_starts += 1
    action_ratio = action_starts / len(bullets) if bullets else 0.0

    passive = len(_PASSIVE_RE.findall(body))
    passive_ratio = passive / max(1, len(sentences))

    result = ReadabilityResult(
        score=0.0,
        flesch=round(flesch, 1),
        avg_words_per_sentence=round(avg_words, 1),
        action_start_ratio=round(action_ratio, 2),
        passive_ratio=round(passive_ratio, 2),
    )
    if avg_words > 30:
        result.notes.append("Sentences are long; split dense bullets for easier scanning.")
    if action_ratio < 0.5:
        result.notes.append("Fewer than half of bullets start with an action verb.")
    if passive_ratio > 0.3:
        result.notes.append("Frequent passive voice detected.")

    score = (
        _flesch_score(flesch) * 0.35
        + length_score * 0.25
        + action_ratio * 100 * 0.25
        + max(0.0, 100 - passive_ratio * 150) * 0.15
    )
    result.score = round(max(0.0, min(100.0, score)), 2)
    return result, {
        "flesch_reading_ease": result.flesch,
        "avg_words_per_sentence": result.avg_words_per_sentence,
        "action_start_ratio": result.action_start_ratio,
        "passive_ratio": result.passive_ratio,
        "sentences": len(sentences),
        "words": len(words),
        "notes": result.notes,
    }
