"""JD analysis cache.

The cache key includes the analyser version, text, title, and company. The
default backend is a bounded in-process TTL/LRU cache. When
`ATS_JD_CACHE_BACKEND=redis` and `ATS_REDIS_URL` are set, a Redis JSON entry is
used first; any Redis failure falls back to memory so scoring stays available.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.jd import JDAnalysis
from app.services.jd_analyser import analyse_jd

logger = get_logger(__name__)

_CACHE_VERSION = "jd-cache-v1"


@dataclass
class _Entry:
    analysis: JDAnalysis
    warnings: list[str]
    expires_at: float


_CACHE: OrderedDict[str, _Entry] = OrderedDict()


def _key(text: str, title: str | None, company: str | None) -> str:
    payload = json.dumps(
        {
            "version": _CACHE_VERSION,
            "text": text,
            "title": title,
            "company": company,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _get_memory(key: str) -> _Entry | None:
    entry = _CACHE.get(key)
    if entry is None:
        return None
    if entry.expires_at < time.monotonic():
        _CACHE.pop(key, None)
        return None
    _CACHE.move_to_end(key)
    return entry


def _set_memory(key: str, entry: _Entry) -> None:
    _CACHE[key] = entry
    _CACHE.move_to_end(key)
    while len(_CACHE) > max(1, settings.jd_cache_max_entries):
        _CACHE.popitem(last=False)


async def _get_redis(key: str) -> _Entry | None:
    try:
        import redis.asyncio as redis  # type: ignore[import-not-found]

        client = redis.from_url(settings.redis_url or "")
        try:
            raw = await client.get(f"ats:jd:{key}")
        finally:
            await client.aclose()
        if not raw:
            return None
        payload = json.loads(raw)
        analysis = JDAnalysis.model_validate(payload["analysis"])
        return _Entry(
            analysis=analysis,
            warnings=list(payload.get("warnings", [])),
            expires_at=time.monotonic() + settings.jd_cache_ttl_seconds,
        )
    except Exception as exc:
        logger.warning("Redis JD cache read failed; using memory", extra={"error": str(exc)})
        return None


async def _set_redis(key: str, entry: _Entry) -> None:
    try:
        import redis.asyncio as redis  # type: ignore[import-not-found]

        client = redis.from_url(settings.redis_url or "")
        try:
            await client.set(
                f"ats:jd:{key}",
                json.dumps(
                    {
                        "analysis": entry.analysis.model_dump(mode="json"),
                        "warnings": entry.warnings,
                    }
                ),
                ex=max(1, settings.jd_cache_ttl_seconds),
            )
        finally:
            await client.aclose()
    except Exception as exc:
        logger.warning("Redis JD cache write failed", extra={"error": str(exc)})


def reset_jd_cache() -> None:
    _CACHE.clear()


async def analyse_jd_cached(
    text: str,
    title: str | None = None,
    company: str | None = None,
) -> tuple[JDAnalysis, list[str], bool]:
    """Return ``(analysis, warnings, cache_hit)``."""

    key = _key(text, title, company)
    use_redis = (
        settings.jd_cache_backend == "redis" and bool(settings.redis_url)
    )
    if use_redis:
        cached = await _get_redis(key)
        if cached is not None:
            return cached.analysis, cached.warnings, True

    cached = _get_memory(key)
    if cached is not None:
        return cached.analysis, cached.warnings, True

    analysis, warnings = await asyncio.to_thread(analyse_jd, text, title, company)
    entry = _Entry(
        analysis=analysis,
        warnings=warnings,
        expires_at=time.monotonic() + settings.jd_cache_ttl_seconds,
    )
    _set_memory(key, entry)
    if use_redis:
        await _set_redis(key, entry)
    return analysis, warnings, False


def cache_size() -> int:
    return len(_CACHE)


__all__ = ["analyse_jd_cached", "cache_size", "reset_jd_cache"]
