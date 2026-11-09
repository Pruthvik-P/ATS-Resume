from __future__ import annotations

import math
import re
from collections import Counter
from difflib import SequenceMatcher

_WORD_RE = re.compile(r"[a-z0-9+#.]+", re.IGNORECASE)
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

STOPWORDS: frozenset[str] = frozenset(
    ["a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but", "by", "can", "could", "did", "do", "does", "doing", "down", "during", "each", "few", "for", "from", "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself", "him", "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just", "me", "more", "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on", "once", "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own", "same", "she", "should", "so", "some", "such", "than", "that", "the", "their", "theirs", "them", "themselves", "then", "there", "these", "they", "this", "those", "through", "to", "too", "under", "until", "up", "very", "was", "we", "were", "what", "when", "where", "which", "while", "who", "whom", "why", "will", "with", "would", "you", "your", "yours", "yourself", "yourselves", "will", "shall", "may", "might", "must", "able", "across", "also", "among", "around", "based", "etc", "via", "per", "within", "without", "new", "using", "use", "used", "strong", "excellent", "good", "great"]
)

ACTION_VERBS: frozenset[str] = frozenset(
    ["built", "build", "led", "lead", "designed", "design", "developed", "develop", "implemented", "implement", "shipped", "ship", "launched", "launch", "created", "create", "architected", "architect", "migrated", "migrate", "reduced", "reduce", "increased", "increase", "improved", "improve", "optimized", "optimised", "optimize", "automate", "automated", "scaled", "scale", "delivered", "deliver", "drove", "drive", "owned", "own", "established", "establish", "introduced", "introduce", "redesigned", "redesign", "refactored", "refactor", "streamlined", "streamline", "accelerated", "accelerate", "cut", "eliminate", "eliminated", "replaced", "replace", "unified", "consolidated", "negotiated", "negotiate", "mentored", "mentor", "coached", "coach", "trained", "train", "partnered", "partner", "coordinated", "coordinate", "analyzed", "analysed", "analyze", "evaluate", "evaluated", "diagnosed", "resolved", "resolve", "debugged", "debug", "instrumented", "instrument", "documented", "document"]
)

WEAK_PHRASES: tuple[str, ...] = (
    "responsible for",
    "worked on",
    "helped with",
    "helped to",
    "assisted with",
    "involved in",
    "participated in",
    "duties included",
    "tasked with",
    "various tasks",
    "team player",
    "hard worker",
)


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in _WORD_RE.findall(text)]


def content_tokens(text: str) -> list[str]:
    return [token for token in tokenize(text) if token not in STOPWORDS and len(token) > 1]


def stem(token: str) -> str:
    """Small, deterministic stemmer. Good enough for term matching, not NLP."""

    token = token.lower()
    if len(token) <= 3:
        return token
    for suffix, replacement in (
        ("ational", "ate"),
        ("ization", "ize"),
        ("isation", "ize"),
        ("iveness", "ive"),
        ("fulness", "ful"),
        ("ousness", "ous"),
        ("ization", "ize"),
        ("ities", "ity"),
        ("ements", "ement"),
        ("ement", ""),
        ("ments", ""),
        ("ment", ""),
        ("ingly", ""),
        ("edly", ""),
        ("ing", ""),
        ("ers", "er"),
        ("ies", "y"),
        ("ied", "y"),
        ("es", ""),
        ("ed", ""),
        ("ly", ""),
        ("s", ""),
    ):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            token = token[: -len(suffix)] + replacement
            break
    return token


def stem_set(text: str) -> set[str]:
    return {stem(token) for token in content_tokens(text)}


def split_sentences(text: str) -> list[str]:
    parts = _SENTENCE_RE.split(text.strip())
    return [part.strip() for part in parts if part.strip()]


def trigrams(text: str) -> Counter[str]:
    normalized = " ".join(tokenize(text))
    padded = f"  {normalized} "
    return Counter(padded[index : index + 3] for index in range(max(0, len(padded) - 2)))


def cosine_counters(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    common = set(left) & set(right)
    numerator = sum(left[key] * right[key] for key in common)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def contains_phrase(haystack: str, needle: str) -> bool:
    escaped = re.escape(needle.strip())
    return re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", haystack, re.IGNORECASE) is not None


def fuzzy_ratio(left: str, right: str) -> float:
    """Return a 0-100 similarity ratio, using rapidfuzz when installed."""

    try:
        from rapidfuzz.fuzz import ratio  # type: ignore[import-not-found]

        return float(ratio(left.lower(), right.lower()))
    except Exception:
        return SequenceMatcher(None, left.lower(), right.lower()).ratio() * 100


def fuzzy_contains(haystack: str, needle: str, threshold: int = 88) -> bool:
    """Typo-tolerant phrase matching over token windows."""

    needle_tokens = tokenize(needle)
    haystack_tokens = tokenize(haystack)
    if not needle_tokens or not haystack_tokens:
        return False
    width = max(1, len(needle_tokens))
    target = " ".join(needle_tokens)
    for index in range(max(1, len(haystack_tokens) - width + 1)):
        window = " ".join(haystack_tokens[index : index + width])
        if fuzzy_ratio(window, target) >= threshold:
            return True
    # Also compare against single tokens for one-word skills.
    if width == 1:
        return any(fuzzy_ratio(token, target) >= threshold for token in haystack_tokens)
    return False


_SPACY_NLP: object | None = None
_SPACY_LOADED = False


def _spacy_pipeline():
    global _SPACY_NLP, _SPACY_LOADED
    from app.core.config import settings

    if not settings.spacy_enabled:
        return None
    if _SPACY_LOADED:
        return _SPACY_NLP
    _SPACY_LOADED = True
    try:
        import spacy  # type: ignore[import-not-found]

        _SPACY_NLP = spacy.load(settings.spacy_model)
    except Exception:
        _SPACY_NLP = None
    return _SPACY_NLP


def reset_spacy() -> None:
    """Clear the optional spaCy model cache (used by tests)."""

    global _SPACY_NLP, _SPACY_LOADED
    _SPACY_NLP = None
    _SPACY_LOADED = False


def lemmatize(text: str) -> list[str]:
    """Lemmatize when spaCy is enabled, otherwise use the deterministic stemmer."""

    pipeline = _spacy_pipeline()
    if pipeline is not None:
        return [
            token.lemma_.lower()
            for token in pipeline(text)  # type: ignore[operator]
            if token.is_alpha and not token.is_stop and len(token.lemma_) > 1
        ]
    return [stem(token) for token in content_tokens(text)]


_NUMBER_RE = re.compile(r"\b\d[\d,.]*\s*(?:%|x|k|m|bn|b|million|billion|thousand)?\b", re.I)


def numbers_in(text: str) -> set[str]:
    return {match.group(0).lower().replace(",", "") for match in _NUMBER_RE.finditer(text)}


def flesch_reading_ease(text: str) -> float:
    words = tokenize(text)
    if not words:
        return 0.0
    sentences = max(1, len(split_sentences(text)))
    syllables = sum(_syllables(word) for word in words)
    return 206.835 - 1.015 * (len(words) / sentences) - 84.6 * (syllables / len(words))


def _syllables(word: str) -> int:
    word = re.sub(r"[^a-z]", "", word.lower())
    if not word:
        return 0
    vowels = "aeiouy"
    count = 0
    previous = False
    for char in word:
        is_vowel = char in vowels
        if is_vowel and not previous:
            count += 1
        previous = is_vowel
    if word.endswith("e") and count > 1:
        count -= 1
    return max(1, count)
