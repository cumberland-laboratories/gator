"""In-process rate limiting — token bucket per (token_id, route_bucket).

Implemented as a FastAPI dependency (not middleware) because middleware
runs before dependency injection and cannot access the authenticated token.

Coverage: added as a router-level dependency on all authenticated routers,
so every authenticated endpoint inherits rate limiting automatically.
"""

import time
import threading
from dataclasses import dataclass, field

from fastapi import Depends, Request

from app.api_contract import RateLimitError
from app.auth import verify_token
from app.models.api_token import ApiToken


# --- Token bucket ---

@dataclass
class TokenBucket:
    """Simple token bucket with monotonic clock."""
    capacity: float
    refill_rate: float  # tokens per second
    tokens: float = field(init=False)
    last_refill: float = field(init=False)

    def __post_init__(self):
        self.tokens = self.capacity
        self.last_refill = time.monotonic()

    def try_consume(self) -> tuple[bool, float]:
        """Try to consume one token. Returns (allowed, retry_after_secs)."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True, 0.0
        else:
            retry_after = (1.0 - self.tokens) / self.refill_rate
            return False, retry_after


# --- Rate limiter ---

# Bucket configs: (capacity, window_seconds)
# capacity = max requests in window; refill_rate = capacity / window
BUCKET_CONFIGS = {
    "views.timeline": (30, 60),    # 30 requests per 60 seconds
    "views.default":  (120, 60),   # 120 requests per 60 seconds
    "writes.default": (60, 60),    # 60 requests per 60 seconds
}


def classify_route(method: str, path: str) -> str:
    """Classify a route into a rate-limit bucket."""
    if method in ("POST", "PUT", "PATCH", "DELETE"):
        return "writes.default"
    if "/views/timeline" in path:
        return "views.timeline"
    return "views.default"


class RateLimiter:
    """In-process rate limiter keyed by (token_id, bucket_name).

    Thread-safe. Per-app-instance (not distributed).
    """

    def __init__(self):
        self._buckets: dict[tuple[str, str], TokenBucket] = {}
        self._lock = threading.Lock()

    def check(self, token_id: str, bucket_name: str) -> tuple[bool, float]:
        """Check rate limit. Returns (allowed, retry_after_secs)."""
        key = (token_id, bucket_name)
        with self._lock:
            if key not in self._buckets:
                capacity, window = BUCKET_CONFIGS.get(bucket_name, (120, 60))
                self._buckets[key] = TokenBucket(
                    capacity=capacity,
                    refill_rate=capacity / window,
                )
            return self._buckets[key].try_consume()


# Singleton limiter
_limiter = RateLimiter()


# --- FastAPI dependency ---

def check_rate_limit(
    request: Request,
    token: ApiToken = Depends(verify_token),
):
    """FastAPI dependency — checks rate limit after authentication.

    Runs after verify_token (which stores token.id on request.state).
    Raises RateLimitError(429) with Retry-After header on breach.
    """
    bucket = classify_route(request.method, request.url.path)
    allowed, retry_after = _limiter.check(str(token.id), bucket)
    if not allowed:
        raise RateLimitError(retry_after=retry_after, bucket=bucket)
