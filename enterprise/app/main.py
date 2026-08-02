"""Gator Enterprise API entrypoint."""

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import VERSION
from app.api_contract import ApiError
from app.config import get_settings
from app.logging import configure_logging
from app.errors import (
    api_error_handler,
    http_exception_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from app.middleware import RequestContextMiddleware
from app.rate_limit import check_rate_limit
from app.routes.health import router as health_router
from app.routes.tokens import router as tokens_router
from app.routes.webhooks import router as webhooks_router
from app.routes.repos import router as repos_router
from app.routes.policies import router as policies_router
from app.routes.reports import router as reports_router
from app.routes.views import router as views_router
from app.routes.session_blocks import router as session_blocks_router
from app.routes.hook_policy import router as hook_policy_router
from app.routes.crypto import router as crypto_router

settings = get_settings()
configure_logging(settings.app_env)

app = FastAPI(
    title="Gator Enterprise",
    version=VERSION,
    description="Git-commit-driven evidence and forensic reconstruction for AI-assisted software development.",
    docs_url="/docs" if settings.app_env == "dev" else None,
    redoc_url=None,
)

# --- Exception handlers (consistent error envelope) ---
app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)

# --- Middleware ---
app.add_middleware(RequestContextMiddleware)

# --- Routers ---
# Health and webhooks: no auth, no rate limiting
app.include_router(health_router)
app.include_router(webhooks_router, prefix="/api/v1")

# Authenticated routers: rate limiting applied at router level
_auth_deps = [Depends(check_rate_limit)]
app.include_router(tokens_router, prefix="/api/v1", dependencies=_auth_deps)
app.include_router(repos_router, prefix="/api/v1", dependencies=_auth_deps)
app.include_router(policies_router, prefix="/api/v1", dependencies=_auth_deps)
app.include_router(reports_router, prefix="/api/v1", dependencies=_auth_deps)
app.include_router(views_router, prefix="/api/v1", dependencies=_auth_deps)
app.include_router(session_blocks_router, prefix="/api/v1", dependencies=_auth_deps)
app.include_router(hook_policy_router, prefix="/api/v1", dependencies=_auth_deps)
app.include_router(crypto_router, prefix="/api/v1", dependencies=_auth_deps)
