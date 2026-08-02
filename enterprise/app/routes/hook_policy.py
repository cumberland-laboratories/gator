"""Hook policy + org policy routes — database-backed, persistent across restarts.

Hook policy controls what the pre-commit hook enforces per repo (stored on Repository.hook_mode).
Org policies are knowledge documents synced to developer machines (stored in org_policies table).
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_contract import ApiError, parse_uuid
from app.auth import verify_token
from app.db import get_db
from app.models.api_token import ApiToken
from app.models.org_policy import OrgPolicy
from app.models.repository import Repository

router = APIRouter(tags=["hook_policy"])

_VALID_MODES = {"strict", "warning", "evidence_only", "off"}


@router.get("/hook-policy")
def get_hook_policy(
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Get per-repo hook enforcement modes for this org."""
    repos = db.execute(
        select(Repository).where(
            Repository.organization_id == token.organization_id,
            Repository.active == True,
        )
    ).scalars().all()

    return {
        repo.canonical_identifier: {"mode": repo.hook_mode}
        for repo in repos
    }


@router.put("/hook-policy/{repo_id}")
def set_hook_policy(
    repo_id: str,
    body: dict,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Set hook enforcement mode for a specific repo."""
    rid = parse_uuid(repo_id, "repo_id")
    repo = db.execute(
        select(Repository).where(
            Repository.id == rid,
            Repository.organization_id == token.organization_id,
        )
    ).scalar_one_or_none()
    if repo is None:
        raise ApiError(404, "not_found", "Repository not found")

    mode = body.get("mode", "evidence_only")
    if mode not in _VALID_MODES:
        raise ApiError(400, "invalid_parameter", f"Invalid mode: {mode}")

    repo.hook_mode = mode
    db.commit()

    return {"status": "updated", "repo": repo.canonical_identifier, "mode": mode}


@router.get("/org-policies")
def list_org_policies(
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """List all org policy documents."""
    policies = db.execute(
        select(OrgPolicy).where(
            OrgPolicy.organization_id == token.organization_id
        ).order_by(OrgPolicy.slug)
    ).scalars().all()

    return {
        "policies": [
            {
                "slug": p.slug,
                "title": p.title,
                "content": p.content,
                "version": p.version,
            }
            for p in policies
        ]
    }


@router.post("/org-policies")
def create_org_policy(
    body: dict,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Create a new org policy document."""
    slug = body.get("slug", "")
    title = body.get("title", slug)
    content = body.get("content", "")

    if not slug:
        raise ApiError(400, "invalid_parameter", "slug is required")

    existing = db.execute(
        select(OrgPolicy).where(
            OrgPolicy.organization_id == token.organization_id,
            OrgPolicy.slug == slug,
        )
    ).scalar_one_or_none()

    if existing:
        raise ApiError(409, "conflict", f"Org policy '{slug}' already exists")

    policy = OrgPolicy(
        organization_id=token.organization_id,
        slug=slug,
        title=title,
        content=content,
    )
    db.add(policy)
    db.commit()

    return {"status": "created", "slug": slug}


@router.put("/org-policies/{slug}")
def update_org_policy(
    slug: str,
    body: dict,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Update an org policy document."""
    policy = db.execute(
        select(OrgPolicy).where(
            OrgPolicy.organization_id == token.organization_id,
            OrgPolicy.slug == slug,
        )
    ).scalar_one_or_none()

    if policy is None:
        raise ApiError(404, "not_found", f"Org policy '{slug}' not found")

    policy.content = body.get("content", policy.content)
    policy.title = body.get("title", policy.title)
    policy.version += 1
    db.commit()

    return {"status": "updated", "slug": slug, "version": policy.version}
