"""Token info route — proves auth works end-to-end."""

from fastapi import APIRouter, Depends

from app.auth import verify_token
from app.models.api_token import ApiToken

router = APIRouter(prefix="/tokens", tags=["tokens"])


@router.get("/me")
def token_info(token: ApiToken = Depends(verify_token)):
    """Return metadata about the current token. Proves auth works."""
    return {
        "id": str(token.id),
        "label": token.label,
        "scopes": token.scopes,
        "last_used_at": token.last_used_at.isoformat() if token.last_used_at else None,
        "expires_at": token.expires_at.isoformat() if token.expires_at else None,
        "created_at": token.created_at.isoformat() if token.created_at else None,
    }
