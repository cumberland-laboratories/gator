"""Centralized API contract — parsers, limits, and error types.

Single source of truth for request parsing, pagination limits, and
the ApiError exception used by all routes and handlers.
"""

import uuid
from datetime import datetime


# --- Pagination limits ---

MAX_LIMIT_DEFAULT = 200
MAX_LIMIT_TIMELINE = 200
MAX_LIMIT_ACTIVITY = 100
MAX_LIMIT_OBSERVATIONS = 50
DEFAULT_LIMIT_LIST = 50
DEFAULT_LIMIT_TIMELINE = 50
DEFAULT_LIMIT_ACTIVITY = 30


# --- Error types ---

class ApiError(Exception):
    """Structured API error. Caught by the error handler in errors.py.

    Attributes:
        status_code: HTTP status code.
        code: Machine-readable error code (e.g., "invalid_parameter").
        message: Human-readable error message.
        headers: Optional response headers (e.g., {"Retry-After": "5"}).
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        headers: dict[str, str] | None = None,
    ):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers
        super().__init__(message)


class RateLimitError(ApiError):
    """Rate limit exceeded. Carries Retry-After header."""

    def __init__(self, retry_after: float, bucket: str = ""):
        msg = f"Rate limit exceeded for {bucket}" if bucket else "Rate limit exceeded"
        super().__init__(
            status_code=429,
            code="rate_limited",
            message=msg,
            headers={"Retry-After": str(int(retry_after))},
        )
        self.retry_after = retry_after


# --- Parsers ---

def parse_uuid(value: str, label: str = "ID") -> uuid.UUID:
    """Parse a string as UUID. Raises ApiError(400) on failure."""
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        raise ApiError(400, "invalid_parameter", f"Invalid {label}: {value}")


def parse_iso_datetime(value: str | None, label: str = "date") -> datetime | None:
    """Parse an ISO 8601 datetime string. Returns None if value is None."""
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        raise ApiError(400, "invalid_parameter", f"Invalid {label}: {value} (use ISO 8601)")


def parse_enum(value: str | None, valid: set[str], label: str = "value") -> str | None:
    """Validate a string against a set of allowed values. Returns None if value is None."""
    if value is None:
        return None
    if value not in valid:
        raise ApiError(400, "invalid_parameter", f"Invalid {label}: {value} (allowed: {', '.join(sorted(valid))})")
    return value
