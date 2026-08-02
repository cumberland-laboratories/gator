"""Tests for rate limiting — token bucket math and route classification."""

import time

import pytest

from app.rate_limit import RateLimiter, TokenBucket, classify_route


class TestTokenBucket:
    def test_initial_capacity(self):
        bucket = TokenBucket(capacity=5, refill_rate=1.0)
        for _ in range(5):
            allowed, _ = bucket.try_consume()
            assert allowed is True

    def test_exhaustion(self):
        bucket = TokenBucket(capacity=2, refill_rate=1.0)
        bucket.try_consume()
        bucket.try_consume()
        allowed, retry_after = bucket.try_consume()
        assert allowed is False
        assert retry_after > 0

    def test_refill(self):
        bucket = TokenBucket(capacity=1, refill_rate=100.0)  # Fast refill
        bucket.try_consume()
        allowed, _ = bucket.try_consume()
        assert allowed is False

        time.sleep(0.02)  # Wait for refill
        allowed, _ = bucket.try_consume()
        assert allowed is True


class TestClassifyRoute:
    def test_timeline(self):
        assert classify_route("GET", "/api/v1/views/timeline") == "views.timeline"

    def test_views_default(self):
        assert classify_route("GET", "/api/v1/views/fleet") == "views.default"
        assert classify_route("GET", "/api/v1/repos") == "views.default"
        assert classify_route("GET", "/api/v1/policies") == "views.default"

    def test_writes(self):
        assert classify_route("POST", "/api/v1/repos/123/refresh") == "writes.default"
        assert classify_route("DELETE", "/api/v1/policies/123/targets/456") == "writes.default"
        assert classify_route("POST", "/api/v1/policies") == "writes.default"


class TestRateLimiter:
    def test_different_tokens_independent(self):
        limiter = RateLimiter()
        # Exhaust token A
        for _ in range(120):
            limiter.check("token-a", "views.default")
        allowed_a, _ = limiter.check("token-a", "views.default")
        assert allowed_a is False

        # Token B should still be allowed
        allowed_b, _ = limiter.check("token-b", "views.default")
        assert allowed_b is True

    def test_different_buckets_independent(self):
        limiter = RateLimiter()
        # Exhaust timeline bucket
        for _ in range(30):
            limiter.check("token-x", "views.timeline")
        allowed_tl, _ = limiter.check("token-x", "views.timeline")
        assert allowed_tl is False

        # Default views bucket should still be allowed
        allowed_dv, _ = limiter.check("token-x", "views.default")
        assert allowed_dv is True
