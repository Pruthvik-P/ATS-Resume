"""LLM provider interface.

Phase 1 is deliberately deterministic: the shipped provider is a stub that
returns no candidates, so every score and proposal is reproducible offline.
Configure `ATS_LLM_PROVIDER=openai|anthropic` plus a key to enable rewriting.
The verifier still validates every candidate before it reaches a user.
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.services.llm.prompts import REWRITER_SYSTEM_PROMPT

logger = get_logger(__name__)


class LLMProvider(Protocol):
    name: str

    async def complete_json(
        self, *, system: str, user: str, schema_name: str
    ) -> dict[str, Any] | None: ...


class StubProvider:
    name = "stub"

    async def complete_json(
        self, *, system: str, user: str, schema_name: str
    ) -> dict[str, Any] | None:
        return None


class OpenAIProvider:
    name = "openai"

    def __init__(self) -> None:
        self.api_key = settings.llm_api_key
        self.base_url = (settings.llm_base_url or "https://api.openai.com").rstrip("/")
        self.model = settings.llm_model

    async def complete_json(
        self, *, system: str, user: str, schema_name: str
    ) -> dict[str, Any] | None:
        if not self.api_key:
            logger.warning("LLM provider is openai but ATS_LLM_API_KEY is unset")
            return None
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }
        try:
            async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
            import json

            return json.loads(content)
        except Exception:
            logger.exception("OpenAI completion failed")
            return None


class AnthropicProvider:
    name = "anthropic"

    def __init__(self) -> None:
        self.api_key = settings.llm_api_key
        self.base_url = (settings.llm_base_url or "https://api.anthropic.com").rstrip("/")
        self.model = settings.llm_model

    async def complete_json(
        self, *, system: str, user: str, schema_name: str
    ) -> dict[str, Any] | None:
        if not self.api_key:
            logger.warning("LLM provider is anthropic but ATS_LLM_API_KEY is unset")
            return None
        payload = {
            "model": self.model,
            "max_tokens": 2000,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        try:
            async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/v1/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                    },
                    json=payload,
                )
                response.raise_for_status()
                content = response.json()["content"][0]["text"]
            import json

            return json.loads(content)
        except Exception:
            logger.exception("Anthropic completion failed")
            return None


def get_llm_provider() -> LLMProvider:
    if settings.llm_provider == "openai":
        return OpenAIProvider()
    if settings.llm_provider == "anthropic":
        return AnthropicProvider()
    return StubProvider()


__all__ = ["LLMProvider", "REWRITER_SYSTEM_PROMPT", "get_llm_provider"]
