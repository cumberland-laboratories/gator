"""Repository and provider management routes."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_contract import ApiError, parse_uuid
from app.auth import verify_token
from app.db import get_db
from app.models.api_token import ApiToken
from app.models.git_provider import GitProvider
from app.models.repository import Repository
from app.services.sync import reconcile_provider, refresh_repo
from app.services.policy import get_repo_policies

router = APIRouter(tags=["repos"])


@router.get("/repos")
def list_repos(
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """List all tracked repositories."""
    repos = db.execute(
        select(Repository).where(
            Repository.organization_id == token.organization_id
        ).order_by(Repository.canonical_identifier)
    ).scalars().all()

    return [
        {
            "id": str(r.id),
            "canonical_identifier": r.canonical_identifier,
            "name": r.name,
            "default_branch": r.default_branch,
            "active": r.active,
            "last_webhook_at": r.last_webhook_at.isoformat() if r.last_webhook_at else None,
            "last_reconciled_at": r.last_reconciled_at.isoformat() if r.last_reconciled_at else None,
            "last_commit_sha": r.last_commit_sha,
        }
        for r in repos
    ]


@router.post("/repos/{repo_id}/refresh")
def trigger_refresh(
    repo_id: str,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Trigger a manual refresh for a single repository."""
    rid = parse_uuid(repo_id, "repo_id")
    repo = db.execute(
        select(Repository).where(
            Repository.id == rid,
            Repository.organization_id == token.organization_id,
        )
    ).scalar_one_or_none()

    if repo is None:
        raise ApiError(404, "not_found", "Repository not found")

    refresh_repo(db, repo)
    return {"status": "refresh_started", "repo": repo.canonical_identifier}


@router.post("/providers/{provider_id}/reconcile")
def trigger_reconcile(
    provider_id: str,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Trigger full reconciliation for a provider."""
    pid = parse_uuid(provider_id, "provider_id")
    provider = db.execute(
        select(GitProvider).where(
            GitProvider.id == pid,
            GitProvider.organization_id == token.organization_id,
        )
    ).scalar_one_or_none()

    if provider is None:
        raise ApiError(404, "not_found", "Provider not found")

    reconcile_provider(db, provider)
    return {"status": "reconciliation_complete", "provider_id": str(provider.id)}


@router.get("/repos/{repo_id}/policies")
def repo_policies(
    repo_id: str,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """List all policies targeting a specific repository."""
    rid = parse_uuid(repo_id, "repo_id")
    repo = db.execute(
        select(Repository).where(
            Repository.id == rid,
            Repository.organization_id == token.organization_id,
        )
    ).scalar_one_or_none()

    if repo is None:
        raise ApiError(404, "not_found", "Repository not found")

    return get_repo_policies(db, repo.id, token.organization_id)
