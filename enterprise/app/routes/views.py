"""E5 views routes — read-model projections under /api/v1/views/.

All endpoints are GET, read-only, paginated where applicable.
This is the canonical read API consumed by both dashboard and CLI.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api_contract import ApiError, parse_enum, parse_iso_datetime, parse_uuid
from app.auth import verify_token
from app.cache import get_cached_or_compute
from app.db import get_db
from app.models.api_token import ApiToken
from app.services.fleet_reads import get_fleet_repos, get_fleet_summary, get_org_overview
from app.services.repo_reads import get_repo_detail
from app.services.policy_reads import get_policy_compliance
from app.services.activity_reads import get_repo_activity
from app.services.audit_reads import get_timeline

router = APIRouter(tags=["views"])

_COMPLIANCE_VALUES = {"aligned", "drifting", "pending", "failed", "unknown", "ungoverned"}
_SORT_VALUES = {"name", "last_commit_at", "drift_count"}
_EVENT_TYPES = {"commit", "policy_activation", "drift_detected", "report_completed", "provider_sync"}


@router.get("/views/fleet")
def fleet_summary(
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Fleet summary with six-state compliance breakdown."""
    cache_key = f"fleet_summary:{token.organization_id}"
    return get_cached_or_compute(cache_key, lambda: get_fleet_summary(db, token.organization_id))


@router.get("/views/fleet/repos")
def fleet_repos(
    compliance: str | None = Query(None, description="Filter: aligned, drifting, pending, failed, unknown, ungoverned"),
    sort: str = Query("name", description="Sort by: name, last_commit_at, drift_count"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Paginated fleet repo list with compliance status."""
    parse_enum(compliance, _COMPLIANCE_VALUES, "compliance")
    parse_enum(sort, _SORT_VALUES, "sort")

    return get_fleet_repos(
        db, token.organization_id,
        compliance_filter=compliance, sort_by=sort,
        limit=limit, offset=offset,
    )


@router.get("/views/repos/{repo_id}")
def repo_detail(
    repo_id: str,
    commits_limit: int = Query(20, ge=1, le=100),
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Single repo governance profile."""
    rid = parse_uuid(repo_id, "repo_id")
    result = get_repo_detail(db, token.organization_id, rid, commits_limit=commits_limit)
    if result is None:
        raise ApiError(404, "not_found", "Repository not found")
    return result


@router.get("/views/repos/{repo_id}/activity")
def repo_activity(
    repo_id: str,
    model: str | None = Query(None, description="Filter to commits involving this model"),
    since: str | None = Query(None, description="ISO 8601 start date"),
    until: str | None = Query(None, description="ISO 8601 end date"),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Model commit activity (heuristic, derived from commit metadata)."""
    rid = parse_uuid(repo_id, "repo_id")
    since_dt = parse_iso_datetime(since, "since")
    until_dt = parse_iso_datetime(until, "until")

    result = get_repo_activity(
        db, token.organization_id, rid,
        model_filter=model, since=since_dt, until=until_dt,
        limit=limit, offset=offset,
    )
    if result is None:
        raise ApiError(404, "not_found", "Repository not found")
    return result


@router.get("/views/policies/{policy_id}")
def policy_compliance(
    policy_id: str,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Policy compliance across target repos."""
    pid = parse_uuid(policy_id, "policy_id")
    result = get_policy_compliance(db, token.organization_id, pid)
    if result is None:
        raise ApiError(404, "not_found", "Policy not found")
    return result


@router.get("/views/timeline")
def timeline(
    repo_id: str | None = Query(None, description="Filter to single repo"),
    policy_id: str | None = Query(None, description="Filter to single policy"),
    event_type: str | None = Query(None, description="Filter: commit, policy_activation, drift_detected, report_completed, provider_sync"),
    since: str | None = Query(None, description="ISO 8601 start date (defaults to 30 days ago)"),
    until: str | None = Query(None, description="ISO 8601 end date"),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = Query(None, description="Opaque cursor for forward pagination"),
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Chronological audit event stream with cursor-based pagination."""
    parse_enum(event_type, _EVENT_TYPES, "event_type")
    rid = parse_uuid(repo_id, "repo_id") if repo_id else None
    pid = parse_uuid(policy_id, "policy_id") if policy_id else None
    since_dt = parse_iso_datetime(since, "since")
    until_dt = parse_iso_datetime(until, "until")

    return get_timeline(
        db, token.organization_id,
        repo_id=rid, policy_id=pid, event_type=event_type,
        since=since_dt, until=until_dt, limit=limit, cursor=cursor,
    )


@router.get("/views/org")
def org_overview(
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Org/tenant health overview."""
    cache_key = f"org_overview:{token.organization_id}"
    return get_cached_or_compute(cache_key, lambda: get_org_overview(db, token.organization_id))
