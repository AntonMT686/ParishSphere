"""Fixed-window counters for brute-force protection (Redis when configured, else in-process)."""

from __future__ import annotations

import threading
import time
from typing import Any

import structlog

from app.core.config import get_settings

log = structlog.get_logger(__name__)


class Counter:
    def __init__(self) -> None:
        self._local: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()
        self._redis: Any = None
        url = get_settings().redis_url
        if url:
            try:
                import redis

                self._redis = redis.Redis.from_url(url, socket_timeout=0.5)
            except Exception:  # pragma: no cover
                log.warning("ratelimit_redis_unavailable")

    def hit(self, key: str, window_seconds: int) -> int:
        """Increment and return the count for ``key`` in the current window."""
        if self._redis is not None:
            try:
                pipe = self._redis.pipeline()
                pipe.incr(f"ps:rl:{key}")
                pipe.expire(f"ps:rl:{key}", window_seconds, nx=True)
                return int(pipe.execute()[0])
            except Exception:  # pragma: no cover - fall back to local
                log.warning("ratelimit_redis_failed")
        now = time.monotonic()
        with self._lock:
            expires, count = self._local.get(key, (0.0, 0))
            if expires <= now:
                expires, count = now + window_seconds, 0
            count += 1
            self._local[key] = (expires, count)
            return count

    def get(self, key: str) -> int:
        if self._redis is not None:
            try:
                return int(self._redis.get(f"ps:rl:{key}") or 0)
            except Exception:  # pragma: no cover
                log.warning("ratelimit_redis_failed")
        with self._lock:
            expires, count = self._local.get(key, (0.0, 0))
            return count if expires > time.monotonic() else 0

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._local.clear()
            else:
                self._local.pop(key, None)
        if self._redis is not None and key is not None:
            try:
                self._redis.delete(f"ps:rl:{key}")
            except Exception:  # pragma: no cover
                log.warning("ratelimit_redis_failed")


_counter: Counter | None = None


def counter() -> Counter:
    global _counter
    if _counter is None:
        _counter = Counter()
    return _counter
