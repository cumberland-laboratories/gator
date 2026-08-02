"""Minimal in-process TTL cache for fleet summary and org overview only.

Narrow by design. Do not expand to other endpoints without explicit review.
For materialized data, use E4's report snapshot infrastructure instead.
"""

import threading
import time
from typing import Any


class TTLCache:
    """Thread-safe dict with per-key expiry."""

    def __init__(self, default_ttl: float = 10.0):
        self._store: dict[str, tuple[Any, float]] = {}  # key → (value, expires_at)
        self._ttl = default_ttl
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        """Get a value if it exists and hasn't expired."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """Set a value with TTL."""
        with self._lock:
            self._store[key] = (value, time.monotonic() + (ttl or self._ttl))

    def clear(self) -> None:
        """Clear all entries."""
        with self._lock:
            self._store.clear()


# Singleton cache instance — 10-second TTL
_views_cache = TTLCache(default_ttl=10.0)


def get_cached_or_compute(cache_key: str, compute_fn, ttl: float = 10.0):
    """Return cached value or compute and cache it."""
    result = _views_cache.get(cache_key)
    if result is not None:
        return result
    result = compute_fn()
    _views_cache.set(cache_key, result, ttl=ttl)
    return result
