"""Embedding providers with a deterministic fallback.

`HashedEmbedder` is dependency-free and remains the default. When
`ATS_EMBEDDING_PROVIDER=sentence-transformers` is configured and the optional
`embeddings` extra is installed, a trained model (bge/e5/gte) is used instead.
A load failure falls back to the hashed embedder and records that fact, so a
missing model never breaks scoring.
"""

from __future__ import annotations

import hashlib
import math
from collections import OrderedDict
from typing import Protocol

from app.core.config import settings
from app.core.logging import get_logger
from app.services.text import content_tokens, stem

logger = get_logger(__name__)


class Embedder(Protocol):
    name: str
    model_name: str
    dim: int

    def embed(self, text: str) -> list[float]: ...


class HashedEmbedder:
    """Deterministic feature-hashing embedder.

    Hashes stemmed tokens, character trigrams, and token bigrams into a fixed
    vector. It captures lexical overlap, not true semantics.
    """

    name = "hashed-ngram-v1"
    model_name = "hashed-ngram-v1"

    def __init__(self, dim: int | None = None) -> None:
        self.dim = dim or settings.embedding_dim

    def _bucket(self, feature: str) -> tuple[int, float]:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        return value % self.dim, 1.0 if (value >> 63) & 1 else -1.0

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        tokens = content_tokens(text)
        features: list[str] = []
        for token in tokens:
            features.append(f"w:{stem(token)}")
            padded = f"#{token}#"
            for index in range(max(0, len(padded) - 2)):
                features.append(f"c:{padded[index : index + 3]}")
        for left, right in zip(tokens, tokens[1:], strict=False):
            features.append(f"b:{stem(left)}_{stem(right)}")
        for feature in features:
            bucket, sign = self._bucket(feature)
            vector[bucket] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    def similarity(self, left: str, right: str) -> float:
        return self.cosine(self.embed(left), self.embed(right))

    @staticmethod
    def cosine(left: list[float], right: list[float]) -> float:
        if not left or not right:
            return 0.0
        return sum(a * b for a, b in zip(left, right, strict=False))


class SentenceTransformerEmbedder:
    """Optional trained embedding model (bge/e5/gte) via sentence-transformers."""

    name = "sentence-transformers"

    def __init__(self, model_name: str | None = None) -> None:
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]

        self.model_name = model_name or settings.embedding_model
        self._model = SentenceTransformer(self.model_name)
        self.dim = int(
            self._model.get_sentence_embedding_dimension() or settings.embedding_dim
        )

    def embed(self, text: str) -> list[float]:
        vector = self._model.encode(text, normalize_embeddings=True)
        return [float(value) for value in vector]


class _FallbackEmbedder:
    """Wrap the hashed fallback with the model name that was requested."""

    def __init__(self, requested: str) -> None:
        self._inner = HashedEmbedder()
        self.name = HashedEmbedder.name
        self.model_name = f"{HashedEmbedder.name} (fallback for {requested})"
        self.dim = self._inner.dim

    def embed(self, text: str) -> list[float]:
        return self._inner.embed(text)


_ACTIVE: Embedder | None = None
_ACTIVE_KEY: tuple[str, str, int] | None = None
_CACHE: OrderedDict[str, tuple[float, ...]] = OrderedDict()
_CACHE_MODEL: str | None = None


def _build_embedder() -> Embedder:
    if settings.embedding_provider == "sentence-transformers":
        try:
            return SentenceTransformerEmbedder(settings.embedding_model)
        except Exception as exc:
            logger.warning(
                "Trained embedding model unavailable; using hashed fallback",
                extra={"model": settings.embedding_model, "error": str(exc)},
            )
            return _FallbackEmbedder(settings.embedding_model)
    return HashedEmbedder()


def get_embedder() -> Embedder:
    global _ACTIVE, _ACTIVE_KEY
    key = (settings.embedding_provider, settings.embedding_model, settings.embedding_dim)
    if _ACTIVE is None or key != _ACTIVE_KEY:
        _ACTIVE = _build_embedder()
        _ACTIVE_KEY = key
    return _ACTIVE


def active_embedding_model() -> str:
    return get_embedder().model_name


def reset_embedder() -> None:
    """Clear the provider and text cache (used by tests and config changes)."""

    global _ACTIVE, _ACTIVE_KEY, _CACHE_MODEL
    _ACTIVE = None
    _ACTIVE_KEY = None
    _CACHE.clear()
    _CACHE_MODEL = None


def embed(text: str) -> list[float]:
    global _CACHE_MODEL
    model = active_embedding_model()
    if model != _CACHE_MODEL:
        _CACHE.clear()
        _CACHE_MODEL = model
    cached = _CACHE.get(text)
    if cached is not None:
        _CACHE.move_to_end(text)
        return list(cached)
    vector = tuple(get_embedder().embed(text))
    _CACHE[text] = vector
    while len(_CACHE) > max(1, settings.embedding_cache_size):
        _CACHE.popitem(last=False)
    return list(vector)


def similarity(left: str, right: str) -> float:
    a, b = embed(left), embed(right)
    norm_a = math.sqrt(sum(value * value for value in a))
    norm_b = math.sqrt(sum(value * value for value in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=False)) / (norm_a * norm_b)


# Kept for callers that imported the constant directly. New code should use
# `semantic_fallback_threshold()` so the threshold follows the active model.
LEXICAL_FALLBACK_THRESHOLD = 0.34


def embedding_bands() -> tuple[float, float, str]:
    """Return (low, high, model_name) for the active embedder."""

    model = active_embedding_model()
    if settings.semantic_low is not None and settings.semantic_high is not None:
        return settings.semantic_low, settings.semantic_high, model
    if get_embedder().name == "sentence-transformers":
        return 0.55, 0.82, model
    return 0.12, 0.42, model


def semantic_fallback_threshold() -> float:
    low, high, _ = embedding_bands()
    if low >= 0.5:
        return round(low + (high - low) * 0.25, 3)
    return LEXICAL_FALLBACK_THRESHOLD


__all__ = [
    "Embedder",
    "HashedEmbedder",
    "LEGACY_EMBEDDER_NAME",
    "SentenceTransformerEmbedder",
    "active_embedding_model",
    "embed",
    "embedding_bands",
    "get_embedder",
    "reset_embedder",
    "semantic_fallback_threshold",
    "similarity",
]

# Backwards-compatible alias used by older documentation/tests.
LEGACY_EMBEDDER_NAME = HashedEmbedder.name
