"""Policy-state routes — the policy channel's report + drift query surface.

Runtime-split Phase 5 (roadmap item 19, 2026-08-21). Machines report
which policy version they (and each governed repo on them) have applied;
the drift query answers "which machines/repos are on which policy
version, where is the drift" in one call — the Enterprise-as-query-
surface half of the pattern, with the committed repo-side policy pin as
the Git-side proof.

MVP scope guards (plan §8 risk 6): single-org, token-auth, report-based
drift only — a machine that has NEVER reported does not appear (missing-
coverage detection needs a machines-that-should-report set, e.g. the
machine_keys registry; deliberate follow-on, documented here so absence
of a row is never read as "in sync").
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_contract import ApiError
from app.auth import verify_token
from app.db import get_db
from app.models.api_token import ApiToken
from app.models.machine_policy_state import MachinePolicyState
from app.models.policy import Policy, PolicyVersion

router = APIRouter(prefix="/policy-state", tags=["policy_state"])


def _parse_dt(value, field):
    if value is None:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise ApiError(400, "bad_request", f"{field} is not an ISO timestamp")


def _active_version(db, policy):
    return db.execute(
        select(PolicyVersion).where(
            PolicyVersion.policy_id == policy.id,
            PolicyVersion.is_active == True,  # noqa: E712
        )
    ).scalar_one_or_none()


@router.post("/report")
def report_policy_state(
    body: dict,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Upsert the reporting machine's current policy state.

    Body: {"machine_id": str, "entries": [{"policy_slug": str,
           "content_hash": str, "repo_identifier": str (optional, "" =
           machine-level), "applied_at": ISO (optional)}],
           "replace_scopes": [str] (optional)}

    Per-entry outcomes, never a batch 500: unknown slug or a hash that
    matches no version of that policy yields status "error" for that
    entry while the rest land. Response includes `in_sync` per entry so
    the reporting client can surface drift immediately.

    `replace_scopes` gives the report FULL-STATE-PER-SCOPE semantics
    (whiteboard 2026-08-22 Finding 2 — without it, a policy retired
    org-side stayed drifted forever because reports could only upsert):
    for each named scope, the entries are the COMPLETE set — rows for
    that (machine, scope) whose policy is absent from the report are
    DELETED. Scopes not named are untouched, so partial reports stay
    safe. Empty entries are legal when replace_scopes is present (the
    all-retired convergence case).
    """
    machine_id = (body.get("machine_id") or "").strip()
    if not machine_id:
        raise ApiError(400, "bad_request", "machine_id is required")
    replace_scopes = body.get("replace_scopes") or []
    if not isinstance(replace_scopes, list) or \
            not all(isinstance(s, str) for s in replace_scopes):
        raise ApiError(400, "bad_request",
                       "replace_scopes must be a list of strings")
    entries = body.get("entries")
    if not isinstance(entries, list) or (not entries and not replace_scopes):
        raise ApiError(400, "bad_request",
                       "entries must be a non-empty list (empty is legal "
                       "only with replace_scopes)")

    now = datetime.now(timezone.utc)
    results = []
    # (scope → set of successfully-reported policy ids) for replace_scopes
    reported_by_scope = {s: set() for s in replace_scopes}
    for entry in entries:
        if not isinstance(entry, dict):
            results.append({"status": "error", "detail": "entry not an object"})
            continue
        slug = (entry.get("policy_slug") or "").strip()
        content_hash = (entry.get("content_hash") or "").strip()
        repo_identifier = (entry.get("repo_identifier") or "").strip()
        if not slug or not content_hash:
            results.append({"status": "error", "policy_slug": slug,
                            "detail": "policy_slug and content_hash required"})
            continue

        policy = db.execute(
            select(Policy).where(
                Policy.organization_id == token.organization_id,
                Policy.slug == slug,
            )
        ).scalar_one_or_none()
        if policy is None:
            results.append({"status": "error", "policy_slug": slug,
                            "detail": "unknown policy slug"})
            continue

        version = db.execute(
            select(PolicyVersion).where(
                PolicyVersion.policy_id == policy.id,
                PolicyVersion.content_hash == content_hash,
            )
        ).scalar_one_or_none()
        if version is None:
            results.append({"status": "error", "policy_slug": slug,
                            "detail": "content_hash matches no version of "
                                      "this policy"})
            continue

        applied_at = _parse_dt(entry.get("applied_at"), "applied_at")

        row = db.execute(
            select(MachinePolicyState).where(
                MachinePolicyState.organization_id == token.organization_id,
                MachinePolicyState.machine_id == machine_id,
                MachinePolicyState.repo_identifier == repo_identifier,
                MachinePolicyState.policy_id == policy.id,
            )
        ).scalar_one_or_none()
        if row is None:
            row = MachinePolicyState(
                organization_id=token.organization_id,
                machine_id=machine_id,
                repo_identifier=repo_identifier,
                policy_id=policy.id,
                policy_version_id=version.id,
                content_hash=content_hash,
                applied_at=applied_at,
                reported_at=now,
            )
            db.add(row)
            status = "created"
        else:
            row.policy_version_id = version.id
            row.content_hash = content_hash
            row.applied_at = applied_at
            row.reported_at = now
            status = "updated"

        if repo_identifier in reported_by_scope:
            reported_by_scope[repo_identifier].add(policy.id)

        active = _active_version(db, policy)
        results.append({
            "status": status,
            "policy_slug": slug,
            "repo_identifier": repo_identifier,
            "version_number": version.version_number,
            "in_sync": bool(active and active.id == version.id),
            "active_version_number": active.version_number if active else None,
        })

    # Full-state clearing for the named scopes (Finding 2).
    cleared = 0
    for scope, kept_ids in reported_by_scope.items():
        stale = db.execute(
            select(MachinePolicyState).where(
                MachinePolicyState.organization_id == token.organization_id,
                MachinePolicyState.machine_id == machine_id,
                MachinePolicyState.repo_identifier == scope,
            )
        ).scalars().all()
        for row in stale:
            if row.policy_id not in kept_ids:
                db.delete(row)
                cleared += 1

    db.commit()
    return {"machine_id": machine_id, "results": results, "cleared": cleared}


def _state_items(db, organization_id, machine_id=None, repo_identifier=None,
                 policy_slug=None):
    """Shared query: current states joined with policy + active version."""
    stmt = (
        select(MachinePolicyState, Policy)
        .join(Policy, Policy.id == MachinePolicyState.policy_id)
        .where(MachinePolicyState.organization_id == organization_id)
        .order_by(MachinePolicyState.machine_id,
                  MachinePolicyState.repo_identifier,
                  Policy.slug)
    )
    if machine_id:
        stmt = stmt.where(MachinePolicyState.machine_id == machine_id)
    if repo_identifier is not None:
        stmt = stmt.where(
            MachinePolicyState.repo_identifier == repo_identifier)
    if policy_slug:
        stmt = stmt.where(Policy.slug == policy_slug)

    items = []
    for row, policy in db.execute(stmt).all():
        active = _active_version(db, policy)
        applied = db.get(PolicyVersion, row.policy_version_id)
        items.append({
            "machine_id": row.machine_id,
            "repo_identifier": row.repo_identifier,
            "policy_slug": policy.slug,
            "applied_version_number": applied.version_number if applied else None,
            "applied_content_hash": row.content_hash,
            "active_version_number": active.version_number if active else None,
            "active_content_hash": active.content_hash if active else None,
            "in_sync": bool(active and active.content_hash == row.content_hash),
            "applied_at": row.applied_at.isoformat(),
            "reported_at": row.reported_at.isoformat(),
        })
    return items


@router.get("")
def list_policy_state(
    machine_id: str = None,
    repo: str = None,
    policy: str = None,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Current policy state across the fleet, with in_sync per row."""
    items = _state_items(db, token.organization_id, machine_id=machine_id,
                         repo_identifier=repo, policy_slug=policy)
    return {"items": items, "total": len(items)}


@router.get("/drift")
def policy_drift(
    machine_id: str = None,
    policy: str = None,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """The one-query drift answer: rows whose applied hash != the
    policy's active hash (includes policies with NO active version —
    an applied-but-retired policy is drift too). Report-based: machines
    that never reported are absent, not in-sync (see module docstring).
    """
    items = _state_items(db, token.organization_id, machine_id=machine_id,
                         policy_slug=policy)
    drifted = [i for i in items if not i["in_sync"]]
    return {"items": drifted, "total": len(drifted),
            "reported_total": len(items)}
