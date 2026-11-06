from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FactCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_text: str = Field(min_length=3, max_length=2000)
    source: str = Field(default="user", max_length=200)
    tags: list[str] = Field(default_factory=list)


class FactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    fact_text: str
    source: str
    tags: list[str]
    confirmed_at: datetime | None = None
    created_at: datetime


class FactList(BaseModel):
    total: int
    items: list[FactRead]
