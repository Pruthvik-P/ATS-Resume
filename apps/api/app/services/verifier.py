from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.text import ACTION_VERBS, STOPWORDS, content_tokens, numbers_in


@dataclass
class VerificationResult:
    verified: bool
    reasons: list[str] = field(default_factory=list)


_CAPITALIZED_RE = re.compile(r"\b[A-Z][A-Za-z0-9+#.&-]{1,}\b")


def _proper_nouns(text: str) -> set[str]:
    nouns: set[str] = set()
    for match in _CAPITALIZED_RE.finditer(text):
        prefix = text[: match.start()].rstrip()
        if not prefix or prefix.endswith((".", "!", "?", "\n")):
            # Sentence-initial capitals are usually ordinary words, not names.
            continue
        token = match.group(0)
        if token.lower() in ACTION_VERBS or token.lower() in STOPWORDS:
            continue
        nouns.add(token.lower())
    return nouns


def _facts_blob(facts: list[str]) -> str:
    return " \n ".join(facts)


def verify_rewrite(original: str, proposed: str, facts: list[str]) -> VerificationResult:
    """Fail closed: a rewrite may only reuse facts present in the source or Facts Bank."""

    reasons: list[str] = []
    fact_text = _facts_blob(facts)

    original_numbers = numbers_in(original) | numbers_in(fact_text)
    proposed_numbers = numbers_in(proposed)
    invented_numbers = proposed_numbers - original_numbers
    if invented_numbers:
        reasons.append(
            "Invented numeric claim(s): " + ", ".join(sorted(invented_numbers))
        )

    original_nouns = _proper_nouns(original) | _proper_nouns(fact_text)
    proposed_nouns = _proper_nouns(proposed)
    invented_nouns = proposed_nouns - original_nouns
    if invented_nouns:
        reasons.append(
            "New proper noun(s) not present in the source: " + ", ".join(sorted(invented_nouns))
        )

    original_tokens = set(content_tokens(original)) | set(content_tokens(fact_text))
    allowed_new = set(ACTION_VERBS) | STOPWORDS
    new_tokens = {
        token
        for token in content_tokens(proposed)
        if token not in original_tokens and token not in allowed_new
    }
    if len(new_tokens) > 2:
        reasons.append(
            "Rewrite introduces unsupported content: " + ", ".join(sorted(new_tokens)[:6])
        )

    return VerificationResult(verified=not reasons, reasons=reasons)


def verify_skill_reorder(original_skills: list[str], proposed_skills: list[str]) -> VerificationResult:
    original_set = {value.strip().lower() for value in original_skills}
    proposed_set = {value.strip().lower() for value in proposed_skills}
    added = proposed_set - original_set
    removed = original_set - proposed_set
    reasons: list[str] = []
    if added:
        reasons.append("Reorder adds skills that were not in the source: " + ", ".join(sorted(added)))
    if removed:
        reasons.append("Reorder drops skills: " + ", ".join(sorted(removed)))
    return VerificationResult(verified=not reasons, reasons=reasons)
