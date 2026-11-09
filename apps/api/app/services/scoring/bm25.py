"""Dependency-free BM25 baseline.

The architecture doc calls for a BM25/TF-IDF retrieval baseline alongside
embeddings. This implementation is pure Python so it runs without scikit-learn
or rank_bm25; the optional `nlp` extra can still be used elsewhere.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

from app.services.text import lemmatize


def _terms(text: str) -> list[str]:
    return [term for term in lemmatize(text) if len(term) > 1]


@dataclass
class BM25:
    documents: list[str]
    k1: float = 1.5
    b: float = 0.75
    _tokens: list[list[str]] = field(init=False, repr=False)
    _doc_freq: Counter[str] = field(init=False, repr=False)
    _avg_len: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._tokens = [_terms(document) for document in self.documents]
        self._doc_freq = Counter(
            term for tokens in self._tokens for term in set(tokens)
        )
        lengths = [len(tokens) for tokens in self._tokens]
        self._avg_len = (sum(lengths) / len(lengths)) if lengths else 0.0

    def _idf(self, term: str) -> float:
        total = len(self._tokens)
        frequency = self._doc_freq.get(term, 0)
        return math.log(1 + (total - frequency + 0.5) / (frequency + 0.5))

    def scores(self, query: str) -> list[float]:
        query_terms = _terms(query)
        if not query_terms or not self._tokens:
            return [0.0 for _ in self._tokens]
        results: list[float] = []
        for tokens in self._tokens:
            counts = Counter(tokens)
            length = len(tokens) or 1
            score = 0.0
            for term in query_terms:
                freq = counts.get(term, 0)
                if not freq:
                    continue
                denominator = freq + self.k1 * (
                    1 - self.b + self.b * length / (self._avg_len or 1.0)
                )
                score += self._idf(term) * freq * (self.k1 + 1) / denominator
            results.append(score)
        return results

    def normalized_scores(self, query: str) -> list[float]:
        raw = self.scores(query)
        peak = max(raw, default=0.0)
        if peak <= 0:
            return [0.0 for _ in raw]
        return [round(value / peak, 4) for value in raw]


def bm25_similarity(query: str, document: str) -> float:
    """Pairwise BM25 score normalized into [0, 1] for a single document."""

    index = BM25([document])
    raw = index.scores(query)[0]
    return round(raw / (raw + 1.0), 4) if raw else 0.0


__all__ = ["BM25", "bm25_similarity"]
