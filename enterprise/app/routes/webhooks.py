"""Webhook receiver — thin route that validates, resolves provider, and hands off.

No heavy processing here. Signature verification IS the auth.
"""

import json

from fastapi import APIRouter, Depends, Request

from app.api_contract import ApiError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models.git_provider import GitProvider
from app.providers.github import verify_github_signature
from app.services.sync import handle_webhook_event

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
settings = get_settings()


@router.post("/github")
async def github_webhook(request: Request, db: Session = Depends(get_db)):
    """Receive GitHub webhook events."""
    # Fail closed: reject all webhooks if secret is not configured
    if not settings.github_webhook_secret:
        raise ApiError(503, "service_unavailable", "Webhook integration not configured")

    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    event_type = request.headers.get("X-GitHub-Event", "")

    # Verify signature using app-level webhook secret
    if not verify_github_signature(body, signature, settings.github_webhook_secret):
        raise ApiError(401, "unauthorized", "Invalid webhook signature")

    payload = json.loads(body)

    # Resolve provider from webhook payload — installation.id maps to git_providers row
    installation_id = str(payload.get("installation", {}).get("id", ""))
    provider = db.execute(
        select(GitProvider).where(
            GitProvider.provider_type == "github",
            GitProvider.config["installation_id"].astext == installation_id,
        )
    ).scalar_one_or_none()

    if provider is None:
        # Webhook from unknown installation — accept but ignore (no retry storm)
        return {"status": "ignored", "reason": "unknown_installation"}

    handle_webhook_event(db, provider, event_type, payload)
    return {"status": "accepted"}
