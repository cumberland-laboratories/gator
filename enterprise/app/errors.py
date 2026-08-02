"""Centralized error handlers — consistent JSON envelope for all API errors.

Every error response follows:
{
    "error": {"code": "...", "message": "..."},
    "request_id": "..."
}

Registered in main.py for: ApiError, starlette HTTPException,
RequestValidationError, and generic Exception.
"""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from app.api_contract import ApiError


def _get_request_id(request: Request) -> str:
    """Extract request_id from request state, or empty string if not set."""
    return getattr(request.state, "request_id", "")


# --- Status code to error code mapping for framework HTTPExceptions ---

_STATUS_CODE_MAP = {
    400: "invalid_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "invalid_request",
    429: "rate_limited",
}


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    """Handle ApiError raised by application code."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {"code": exc.code, "message": exc.message},
            "request_id": _get_request_id(request),
        },
        headers=exc.headers,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle framework-level HTTPExceptions (routing 404/405, auth, etc.)."""
    code = _STATUS_CODE_MAP.get(exc.status_code, "request_error")
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {"code": code, "message": message},
            "request_id": _get_request_id(request),
        },
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle Pydantic/FastAPI request validation errors."""
    errors = exc.errors()
    if errors:
        first = errors[0]
        loc = " → ".join(str(l) for l in first.get("loc", []))
        msg = first.get("msg", "Validation error")
        message = f"{loc}: {msg}" if loc else msg
    else:
        message = "Request validation failed"

    return JSONResponse(
        status_code=422,
        content={
            "error": {"code": "invalid_request", "message": message},
            "request_id": _get_request_id(request),
        },
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions. Never leak internals."""
    return JSONResponse(
        status_code=500,
        content={
            "error": {"code": "internal_error", "message": "Internal server error"},
            "request_id": _get_request_id(request),
        },
    )
