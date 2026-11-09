from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ScoringWeights(BaseModel):
    """Default weights from architecture doc §4.3. Must sum to 1.0."""

    keyword_match: float = 0.30
    semantic_relevance: float = 0.20
    experience_fit: float = 0.15
    parseability: float = 0.15
    impact: float = 0.10
    education: float = 0.05
    readability: float = 0.05

    def as_dict(self) -> dict[str, float]:
        return self.model_dump()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="ATS_",
        extra="ignore",
    )

    app_name: str = "ATS Engine API"
    app_version: str = "0.1.0"
    environment: Literal["local", "test", "staging", "production"] = "local"
    debug: bool = False
    api_v1_prefix: str = "/v1"

    # Auth is a single shared key in Phase 1. When unset, the API is open
    # (local development and tests only).
    api_key: str | None = None
    # Optional per-user API keys: "email=key,email2=key2". When provided, this
    # takes precedence over api_key and each key maps to its own user row.
    api_keys: str | None = None

    # Comma-separated list, e.g. "http://localhost:3000,https://app.example.com"
    allowed_origins: str = "http://localhost:3000"

    database_url: str = "sqlite+aiosqlite:///./ats.db"
    # Convenience for local dev. In production, run Alembic migrations instead.
    auto_create_tables: bool = True

    storage_backend: Literal["local"] = "local"
    storage_dir: Path = Path("./.data/uploads")
    max_upload_bytes: int = 10 * 1024 * 1024
    max_jd_chars: int = 60_000

    # LLM is pluggable. The default stub keeps the engine deterministic and
    # offline, which is what Phase 1 scoring and the verifier rely on.
    llm_provider: Literal["stub", "openai", "anthropic"] = "stub"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_timeout_seconds: float = 45.0

    # Deterministic hashing embedder dimension. Swap for bge/e5 in Phase 2.
    embedding_dim: int = 512

    scoring_weights: ScoringWeights = Field(default_factory=ScoringWeights)
    must_have_cap: float = 70.0
    parse_fidelity_cap: float = 60.0
    parse_fidelity_floor: float = 60.0
    keyword_stuffing_penalty: float = 12.0

    optimiser_max_iterations: int = 3
    optimiser_target_score: float = 85.0
    optimiser_max_changes: int = 25

    job_stale_after_seconds: int = 900

    # Retention is opt-in. `retention_days` is the default window used by
    # POST /v1/account/purge; a value of null means "keep until user deletes".
    retention_days: int | None = None

    # In-process abuse protection. These are per-identity, per-window limits.
    # 0 disables the corresponding limit.
    rate_limit_requests_per_minute: int = 180
    rate_limit_uploads_per_minute: int = 20
    rate_limit_optimise_jobs_per_hour: int = 30

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def user_api_keys(self) -> dict[str, str]:
        """Parse ``email=key,email2=key2`` into a lookup table."""

        if not self.api_keys:
            return {}
        mapping: dict[str, str] = {}
        for item in self.api_keys.split(","):
            email, separator, key = item.partition("=")
            if separator and email.strip() and key.strip():
                mapping[email.strip().lower()] = key.strip()
        return mapping

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
