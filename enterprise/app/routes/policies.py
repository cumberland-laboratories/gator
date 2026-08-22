"""Policy management routes — CRUD, versioning, targeting, activation, rollout inspection."""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api_contract import ApiError, parse_uuid
from app.auth import verify_token
from app.db import get_db
from app.models.api_token import ApiToken
from app.models.policy import Policy, PolicyVersion
from app.models.policy_target import PolicyTarget
from app.services import policy as policy_service

router = APIRouter(prefix="/policies", tags=["policies"])


# Request models

class CreatePolicyRequest(BaseModel):
    name: str
    slug: str
    description: str | None = None


class CreateVersionRequest(BaseModel):
    content: dict
    notes: str | None = None


class AddTargetsRequest(BaseModel):
    repository_ids: list[str]


# Routes

@router.post("")
def create_policy(
    body: CreatePolicyRequest,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Create a new policy."""
    try:
        policy = policy_service.create_policy(
            db, token.organization_id, body.name, body.slug, body.description,
            actor_token_id=token.id,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "conflict", f"Policy slug '{body.slug}' already exists")
    return _policy_response(db, policy)


@router.get("")
def list_policies(
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """List all policies."""
    policies = db.execute(
        select(Policy).where(
            Policy.organization_id == token.organization_id
        ).order_by(Policy.name)
    ).scalars().all()
    return [_policy_response(db, p) for p in policies]


@router.get("/active")
def active_policies(
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """All active-status policies with their active version INCLUDING
    content — the policy-channel pull payload (runtime-split Phase 5b).

    One call gives `gator-enterprise policies pull` everything it needs:
    slug, version number, content hash (for the state report + the
    repo-side policy pin) and the content itself (for
    ~/.gator/enterprise/org-policies.json).

    ROUTE-ORDER TRIPWIRE: declared BEFORE /{policy_id} — FastAPI matches
    in declaration order and parse_uuid would 400 on the literal
    "active" otherwise (pinned by test_active_route_not_shadowed).
    """
    policies = db.execute(
        select(Policy).where(
            Policy.organization_id == token.organization_id,
            Policy.status == "active",
        ).order_by(Policy.slug)
    ).scalars().all()

    items = []
    for policy in policies:
        version = db.execute(
            select(PolicyVersion).where(
                PolicyVersion.policy_id == policy.id,
                PolicyVersion.is_active == True,  # noqa: E712
            )
        ).scalar_one_or_none()
        if version is None:
            continue  # active policy without an activated version — nothing to pull
        items.append({
            "policy_id": str(policy.id),
            "slug": policy.slug,
            "name": policy.name,
            "version_number": version.version_number,
            "content_hash": version.content_hash,
            "content": version.content,
        })
    return {"items": items, "total": len(items)}


@router.get("/{policy_id}")
def get_policy(
    policy_id: str,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Get policy detail with active version info."""
    policy = _get_policy(db, policy_id, token.organization_id)
    return _policy_response(db, policy)


@router.post("/{policy_id}/versions")
def create_version(
    policy_id: str,
    body: CreateVersionRequest,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Create a new immutable policy version."""
    policy = _get_policy(db, policy_id, token.organization_id)
    version = policy_service.create_version(
        db, policy, body.content, body.notes,
        created_by_token_id=token.id,
    )
    db.commit()
    return _version_response(version)


@router.get("/{policy_id}/versions")
def list_versions(
    policy_id: str,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """List all versions of a policy."""
    policy = _get_policy(db, policy_id, token.organization_id)
    versions = db.execute(
        select(PolicyVersion).where(
            PolicyVersion.policy_id == policy.id
        ).order_by(PolicyVersion.version_number.desc())
    ).scalars().all()
    return [_version_response(v) for v in versions]


@router.post("/{policy_id}/activate/{version_id}")
def activate_version(
    policy_id: str,
    version_id: str,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Activate a policy version. Creates pending rollouts for all active targets."""
    policy = _get_policy(db, policy_id, token.organization_id)
    version = db.execute(
        select(PolicyVersion).where(
            PolicyVersion.id == parse_uuid(version_id, "version_id"),
            PolicyVersion.policy_id == policy.id,
        )
    ).scalar_one_or_none()

    if version is None:
        raise ApiError(404, "not_found", "Version not found")

    policy_service.activate_version(db, policy, version, actor_token_id=token.id)
    return {"status": "activated", "version_number": version.version_number}


@router.post("/{policy_id}/targets")
def add_targets(
    policy_id: str,
    body: AddTargetsRequest,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Add target repositories to a policy."""
    policy = _get_policy(db, policy_id, token.organization_id)
    repo_ids = [parse_uuid(rid, "repository_id") for rid in body.repository_ids]
    try:
        activated = policy_service.add_targets(db, policy, repo_ids, actor_token_id=token.id)
    except ValueError as e:
        raise ApiError(400, "invalid_parameter", str(e))
    return {"status": "targets_updated", "activated_count": len(activated)}


@router.delete("/{policy_id}/targets/{repo_id}")
def remove_target(
    policy_id: str,
    repo_id: str,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Remove a target repository from a policy."""
    policy = _get_policy(db, policy_id, token.organization_id)
    policy_service.remove_target(db, policy, parse_uuid(repo_id, "repo_id"), actor_token_id=token.id)
    return {"status": "target_removed"}


@router.get("/{policy_id}/targets")
def list_targets(
    policy_id: str,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """List target repositories for a policy."""
    policy = _get_policy(db, policy_id, token.organization_id)
    targets = db.execute(
        select(PolicyTarget).where(
            PolicyTarget.policy_id == policy.id,
            PolicyTarget.active == True,
        )
    ).scalars().all()
    return [
        {"repository_id": str(t.repository_id), "active": t.active}
        for t in targets
    ]


@router.get("/{policy_id}/rollouts")
def list_rollouts(
    policy_id: str,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """List rollout state for a policy."""
    policy = _get_policy(db, policy_id, token.organization_id)
    return policy_service.get_rollout_summary(db, policy)


# Helpers

def _get_policy(db: Session, policy_id: str, org_id: uuid.UUID) -> Policy:
    """Fetch a policy or raise 404."""
    policy = db.execute(
        select(Policy).where(
            Policy.id == parse_uuid(policy_id, "policy_id"),
            Policy.organization_id == org_id,
        )
    ).scalar_one_or_none()
    if policy is None:
        raise ApiError(404, "not_found", "Policy not found")
    return policy


def _policy_response(db: Session, policy: Policy) -> dict:
    """Serialize a policy with active version info."""
    active_version = db.execute(
        select(PolicyVersion).where(
            PolicyVersion.policy_id == policy.id,
            PolicyVersion.is_active == True,
        )
    ).scalar_one_or_none()

    version_count = db.execute(
        select(PolicyVersion).where(PolicyVersion.policy_id == policy.id)
    ).scalars().all()

    return {
        "id": str(policy.id),
        "name": policy.name,
        "slug": policy.slug,
        "description": policy.description,
        "status": policy.status,
        "active_version": _version_response(active_version) if active_version else None,
        "version_count": len(version_count),
        "created_at": policy.created_at.isoformat(),
    }


def _version_response(version: PolicyVersion) -> dict:
    """Serialize a policy version."""
    return {
        "id": str(version.id),
        "version_number": version.version_number,
        "content_hash": version.content_hash,
        "is_active": version.is_active,
        "notes": version.notes,
        "created_at": version.created_at.isoformat(),
    }
