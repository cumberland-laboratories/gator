"""Request context middleware — request ID, timing, structured logging."""

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Generates/accepts X-Request-ID, times requests, emits structured log."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Accept or generate request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        # Initialize auth fields (populated by verify_token if authenticated)
        request.state.token_id = None
        request.state.organization_id = None

        start = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 1)

        # Add request ID to response
        response.headers["X-Request-ID"] = request_id

        # Structured request log
        from app.logging import get_logger
        logger = get_logger()
        logger.info(
            "http.request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
            request_id=request_id,
            org_id=str(request.state.organization_id) if request.state.organization_id else None,
            token_id=str(request.state.token_id) if request.state.token_id else None,
        )

        return response
