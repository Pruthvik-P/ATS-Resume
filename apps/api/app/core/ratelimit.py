from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from app.core.errors import AppError

# Sliding-window limiter held in process memory. This protects a single API
# worker; a multi-worker deployment still needs Redis or the gateway's limiter.
_buckets: dict[str, deque[float]] = defaultdict(deque)
_lock = Lock()


def _now() -> float:
    return time.monotonic()


def check_rate_limit(key: str, limit: int, window_seconds: float) -> None:
    if limit <= 0:
        return
    now = _now()
    cutoff = now - window_seconds
    with _lock:
        bucket = _buckets[key]
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = max(1, int(window_seconds - (now - bucket[0])))
            raise AppError(
                "rate_limited",
                "Too many requests. Retry after the window resets.",
                status_code=429,
                details={"limit": limit, "window_seconds": int(window_seconds), "retry_after": retry_after},
            )
        bucket.append(now)


def enforce_rate_limit(key: str, limit: int, window_seconds: float) -> None:
    check_rate_limit(key, limit, window_seconds)


def reset_rate_limits() -> None:
    """Test hook: clear every counter."""

    with _lock:
        _buckets.clear()
