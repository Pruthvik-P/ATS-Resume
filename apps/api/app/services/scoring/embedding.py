from __future__ import annotations

import hashlib
import math
from functools import lru_cache

from app.core.config import settings
from app.services.text import content_tokens, stem


class HashedEmbedder:
    """Deterministic, dependency-free embedding fallback.

    Feature-hashes stemmed tokens and character trigrams into a fixed vector.
    It captures lexical overlap, not true semantics. Phase 2 swaps this for
    bge/e5 via sentence-transformers while keeping the same interface.
    """

    name = "hashed-ngram-v1"

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


@lru_cache(maxsize=2048)
def _cached_embed(text: str) -> tuple[float, ...]:
    return tuple(HashedEmbedder().embed(text))


def embed(text: str) -> list[float]:
    return list(_cached_embed(text))


def similarity(left: str, right: str) -> float:
    a, b = embed(left), embed(right)
    norm_a = math.sqrt(sum(value * value for value in a))
    norm_b = math.sqrt(sum(value * value for value in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=False)) / (norm_a * norm_b)


# Hashed features produce lower cosines than trained sentence embeddings.
# 0.34 is roughly the 90th percentile for unrelated resume/JD pairs in our
# test corpus; it is recorded in score details so calibration stays visible.
LEXICAL_FALLBACK_THRESHOLD = 0.34
