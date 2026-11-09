"""LLM provider interface with retries, usage accounting, and tracing.

The default provider is still a deterministic stub. When a real provider is
configured, every call returns an :class:`LLMResult` carrying the model,
prompt version, token usage, cost estimate, retry count, latency, and error.
Callers keep using ``complete_json`` and validate the returned object with a
Pydantic schema, so a provider can never bypass the verifier or parser.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.services.llm.prompts import REWRITER_SYSTEM_PROMPT

logger = get_logger(__name__)

_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


@dataclass
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class LLMResult:
    data: dict[str, Any] | None = None
    provider: str = "stub"
    model: str = "stub"
    schema_name: str = ""
    prompt_version: str = ""
    usage: LLMUsage = field(default_factory=LLMUsage)
    attempts: int = 0
    latency_ms: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.data is not None and self.error is None


class LLMProvider(Protocol):
    name: str

    async def complete_json(
        self, *, system: str, user: str, schema_name: str
    ) -> dict[str, Any] | None: ...

    async def complete_result(
        self,
        *,
        system: str,
        user: str,
        schema_name: str,
        prompt_version: str = "",
    ) -> LLMResult: ...


class StubProvider:
    name = "stub"
    model = "stub"

    async def complete_json(
        self, *, system: str, user: str, schema_name: str
    ) -> dict[str, Any] | None:
        return None

    async def complete_result(
        self,
        *,
        system: str,
        user: str,
        schema_name: str,
        prompt_version: str = "",
    ) -> LLMResult:
        return LLMResult(
            provider=self.name,
            model=self.model,
            schema_name=schema_name,
            prompt_version=prompt_version,
            error="stub provider returns no data",
        )


def _estimate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    return round(
        prompt_tokens / 1_000_000 * settings.llm_input_cost_per_million
        + completion_tokens / 1_000_000 * settings.llm_output_cost_per_million,
        6,
    )


def _parse_json_object(content: Any) -> dict[str, Any] | None:
    if isinstance(content, dict):
        return content
    if not isinstance(content, str):
        return None
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


class _HTTPProvider:
    name = "http"
    default_base_url = ""

    def __init__(self) -> None:
        self.api_key = settings.llm_api_key
        self.base_url = (settings.llm_base_url or self.default_base_url).rstrip("/")
        self.model = settings.llm_model

    def _headers(self) -> dict[str, str]:
        raise NotImplementedError

    def _payload(self, system: str, user: str) -> dict[str, Any]:
        raise NotImplementedError

    def _endpoint(self) -> str:
        raise NotImplementedError

    def _content(self, body: dict[str, Any]) -> Any:
        raise NotImplementedError

    def _usage(self, body: dict[str, Any]) -> LLMUsage:
        usage = body.get("usage") or {}
        prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        completion = int(
            usage.get("completion_tokens") or usage.get("output_tokens") or 0
        )
        total = int(usage.get("total_tokens") or prompt + completion)
        return LLMUsage(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            cost_usd=_estimate_cost(prompt, completion),
        )

    async def complete_result(
        self,
        *,
        system: str,
        user: str,
        schema_name: str,
        prompt_version: str = "",
    ) -> LLMResult:
        started = time.monotonic()
        attempts = 0
        last_error: str | None = None
        if not self.api_key:
            return LLMResult(
                provider=self.name,
                model=self.model,
                schema_name=schema_name,
                prompt_version=prompt_version,
                error=f"ATS_LLM_API_KEY is not set for provider '{self.name}'",
            )

        for attempt in range(1, settings.llm_max_retries + 2):
            attempts = attempt
            try:
                async with httpx.AsyncClient(
                    timeout=settings.llm_timeout_seconds
                ) as client:
                    response = await client.post(
                        self._endpoint(),
                        headers=self._headers(),
                        json=self._payload(system, user),
                    )
                if response.status_code in _RETRYABLE_STATUS:
                    last_error = f"HTTP {response.status_code}"
                    if attempt <= settings.llm_max_retries:
                        await asyncio.sleep(
                            settings.llm_retry_backoff_seconds * (2 ** (attempt - 1))
                        )
                        continue
                    response.raise_for_status()
                response.raise_for_status()
                body = response.json()
                data = _parse_json_object(self._content(body))
                usage = self._usage(body)
                result = LLMResult(
                    data=data,
                    provider=self.name,
                    model=self.model,
                    schema_name=schema_name,
                    prompt_version=prompt_version,
                    usage=usage,
                    attempts=attempts,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    error=None if data is not None else "response was not a JSON object",
                )
                self._trace(result)
                return result
            except Exception as exc:  # network, HTTP, or JSON failure
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt <= settings.llm_max_retries:
                    await asyncio.sleep(
                        settings.llm_retry_backoff_seconds * (2 ** (attempt - 1))
                    )
                    continue

        result = LLMResult(
            provider=self.name,
            model=self.model,
            schema_name=schema_name,
            prompt_version=prompt_version,
            attempts=attempts,
            latency_ms=int((time.monotonic() - started) * 1000),
            error=last_error or "LLM request failed",
        )
        self._trace(result)
        return result

    async def complete_json(
        self, *, system: str, user: str, schema_name: str
    ) -> dict[str, Any] | None:
        result = await self.complete_result(
            system=system, user=user, schema_name=schema_name
        )
        return result.data

    def _trace(self, result: LLMResult) -> None:
        if not settings.llm_trace_enabled:
            return
        logger.info(
            "llm_call",
            extra={
                "llm_provider": result.provider,
                "llm_model": result.model,
                "llm_schema": result.schema_name,
                "llm_prompt_version": result.prompt_version,
                "llm_prompt_tokens": result.usage.prompt_tokens,
                "llm_completion_tokens": result.usage.completion_tokens,
                "llm_cost_usd": result.usage.cost_usd,
                "llm_attempts": result.attempts,
                "llm_latency_ms": result.latency_ms,
                "llm_error": result.error,
            },
        )


class OpenAIProvider(_HTTPProvider):
    name = "openai"
    default_base_url = "https://api.openai.com"

    def _endpoint(self) -> str:
        return f"{self.base_url}/v1/chat/completions"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def _payload(self, system: str, user: str) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
            "max_tokens": settings.llm_max_output_tokens,
        }

    def _content(self, body: dict[str, Any]) -> Any:
        return body["choices"][0]["message"]["content"]


class AnthropicProvider(_HTTPProvider):
    name = "anthropic"
    default_base_url = "https://api.anthropic.com"

    def _endpoint(self) -> str:
        return f"{self.base_url}/v1/messages"

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key or "",
            "anthropic-version": "2023-06-01",
        }

    def _payload(self, system: str, user: str) -> dict[str, Any]:
        return {
            "model": self.model,
            "max_tokens": settings.llm_max_output_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "temperature": 0.2,
        }

    def _content(self, body: dict[str, Any]) -> Any:
        blocks = body.get("content") or []
        return "".join(
            block.get("text", "") for block in blocks if isinstance(block, dict)
        )


def get_llm_provider() -> LLMProvider:
    if settings.llm_provider == "openai":
        return OpenAIProvider()
    if settings.llm_provider == "anthropic":
        return AnthropicProvider()
    return StubProvider()


__all__ = [
    "LLMProvider",
    "LLMResult",
    "LLMUsage",
    "REWRITER_SYSTEM_PROMPT",
    "get_llm_provider",
]
