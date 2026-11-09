"""Optional cross-encoder reranker.

Embeddings retrieve candidates cheaply; a cross-encoder rescores the top
candidates with full query/document attention. The reranker is opt-in because
the model is large and must be downloaded. Loading failures disable it rather
than breaking scoring.
"""

from __future__ import annotations

import math
from typing import Protocol

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class Reranker(Protocol):
    name: str
    model_name: str

    def score(self, query: str, candidates: list[str]) -> list[float]: ...


class CrossEncoderReranker:
    name = "cross-encoder"

    def __init__(self, model_name: str | None = None) -> None:
        from sentence_transformers import CrossEncoder  # type: ignore[import-not-found]

        self.model_name = model_name or settings.reranker_model
        self._model = CrossEncoder(self.model_name)

    def score(self, query: str, candidates: list[str]) -> list[float]:
        if not candidates:
            return []
        raw = self._model.predict([(query, candidate) for candidate in candidates])
        # Cross-encoder outputs are logits; map them to (0, 1).
        return [1.0 / (1.0 + math.exp(-float(value))) for value in raw]


_ACTIVE: Reranker | None | object = None
_ACTIVE_KEY: tuple[bool, str] | None = None
_UNSET = object()


def get_reranker() -> Reranker | None:
    global _ACTIVE, _ACTIVE_KEY
    if not settings.reranker_enabled:
        return None
    key = (settings.reranker_enabled, settings.reranker_model)
    if _ACTIVE is _UNSET or key != _ACTIVE_KEY:
        try:
            _ACTIVE = CrossEncoderReranker(settings.reranker_model)
        except Exception as exc:
            logger.warning(
                "Cross-encoder unavailable; embedding similarity will be used",
                extra={"model": settings.reranker_model, "error": str(exc)},
            )
            _ACTIVE = None
        _ACTIVE_KEY = key
    return _ACTIVE if isinstance(_ACTIVE, CrossEncoderReranker) else None


def reset_reranker() -> None:
    global _ACTIVE, _ACTIVE_KEY
    _ACTIVE = None
    _ACTIVE_KEY = None


def reranker_version() -> str:
    """Return the configured model name without loading the model."""

    return settings.reranker_model if settings.reranker_enabled else "disabled"


def blend_rerank(
    embedding_scores: list[float],
    rerank_scores: list[float],
    weight: float,
) -> list[float]:
    weight = max(0.0, min(1.0, weight))
    if not rerank_scores:
        return embedding_scores
    return [
        (1 - weight) * embedding + weight * reranked
        for embedding, reranked in zip(embedding_scores, rerank_scores, strict=False)
    ]


__all__ = [
    "CrossEncoderReranker",
    "Reranker",
    "blend_rerank",
    "get_reranker",
    "reranker_version",
    "reset_reranker",
]
