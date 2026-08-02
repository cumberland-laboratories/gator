"""Token authentication for the Enterprise API."""

import hashlib
from datetime import datetime, timezone

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_contract import ApiError
from app.db import get_db
from app.models.api_token import ApiToken

bearer_scheme = HTTPBearer(auto_error=False)


def hash_token(raw: str) -> str:
    """Hash a raw token using SHA-256. Returns hex digest."""
    return hashlib.sha256(raw.encode()).hexdigest()


def verify_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> ApiToken:
    """FastAPI dependency — verifies Bearer token against the database.

    Returns the ApiToken record if valid; raises ApiError(401) otherwise.
    Stores token.id and organization_id on request.state for downstream use
    (rate limiter, structured logging).
    """
    if credentials is None:
        raise ApiError(401, "unauthorized", "Missing or malformed Authorization header")

    token_hash = hash_token(credentials.credentials)
    token = db.execute(
        select(ApiToken).where(ApiToken.token_hash == token_hash)
    ).scalar_one_or_none()

    if token is None:
        raise ApiError(401, "unauthorized", "Invalid or expired token")

    # Check expiry
    if token.expires_at and token.expires_at < datetime.now(timezone.utc):
        raise ApiError(401, "unauthorized", "Token expired")

    # Update last_used_at
    token.last_used_at = datetime.now(timezone.utc)
    db.commit()

    # Store on request state for middleware and rate limiter
    request.state.token_id = token.id
    request.state.organization_id = token.organization_id

    return token
