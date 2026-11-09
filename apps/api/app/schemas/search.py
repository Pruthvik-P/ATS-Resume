from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SimilarBulletsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=2, max_length=2000)
    resume_id: str | None = None
    limit: int = Field(default=5, ge=1, le=20)


class SimilarBulletItem(BaseModel):
    bullet_id: str
    resume_version_id: str
    section: str
    text: str
    similarity: float


class SimilarBulletsResponse(BaseModel):
    backend: str
    items: list[SimilarBulletItem] = Field(default_factory=list)


__all__ = [
    "SimilarBulletItem",
    "SimilarBulletsRequest",
    "SimilarBulletsResponse",
]
