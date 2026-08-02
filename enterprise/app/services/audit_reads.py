"""Audit timeline read-model service — chronological governance event stream.

Uses cursor-based pagination with composite cursor (timestamp, source_type, id).
Each source fetches limit+1 rows (sentinel strategy). has_more is advisory:
false is authoritative; true means "likely more, fetch to confirm."
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import String, cast, desc, func, select
from sqlalchemy.orm import Session

from app.models.audit_log import AdminAuditLog
from app.models.commit import Commit
from app.models.commit_observation import CommitObservation
from app.models.drift_finding import PolicyDriftFinding
from app.models.policy import Policy
from app.models.report_run import ReportRun
from app.models.repository import Repository
from app.models.sync_run import ProviderSyncRun


def _parse_cursor(cursor: str | None) -> tuple[datetime, str, str] | None:
    """Parse composite cursor: 'ISO_TIMESTAMP|source_type|uuid'."""
    if not cursor:
        return None
    try:
        parts = cursor.split("|", 2)
        if len(parts) != 3:
            return None
        ts = datetime.fromisoformat(parts[0])
        return (ts, parts[1], parts[2])
    except (ValueError, IndexError):
        return None


def _make_cursor(timestamp: datetime, source_type: str, id: uuid.UUID) -> str:
    """Build composite cursor string."""
    return f"{timestamp.isoformat()}|{source_type}|{str(id)}"


def get_timeline(
    db: Session,
    org_id: uuid.UUID,
    repo_id: uuid.UUID | None = None,
    policy_id: uuid.UUID | None = None,
    event_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> dict:
    """Chronological governance event stream with cursor-based pagination."""
    now = datetime.now(timezone.utc)

    # Default since to 30 days if not provided
    if since is None and cursor is None:
        since = now - timedelta(days=30)

    parsed_cursor = _parse_cursor(cursor)
    fetch_limit = limit + 1  # Sentinel row strategy

    events: list[dict[str, Any]] = []

    # --- Source 1: Commits ---
    if event_type is None or event_type == "commit":
        events.extend(
            _fetch_commit_events(db, org_id, repo_id, since, until, parsed_cursor, fetch_limit)
        )

    # --- Source 2: Policy activations (from audit log) ---
    if event_type is None or event_type == "policy_activation":
        if not repo_id:  # Policy activations are org-level, not repo-scoped
            events.extend(
                _fetch_policy_activation_events(db, org_id, policy_id, since, until, parsed_cursor, fetch_limit)
            )

    # --- Source 3: Drift findings ---
    if event_type is None or event_type == "drift_detected":
        events.extend(
            _fetch_drift_events(db, org_id, repo_id, policy_id, since, until, parsed_cursor, fetch_limit)
        )

    # --- Source 4: Report runs ---
    if event_type is None or event_type == "report_completed":
        events.extend(
            _fetch_report_events(db, org_id, since, until, parsed_cursor, fetch_limit)
        )

    # --- Source 5: Provider sync runs ---
    if event_type is None or event_type == "provider_sync":
        if not repo_id and not policy_id:  # Syncs are provider-level
            events.extend(
                _fetch_sync_events(db, org_id, since, until, parsed_cursor, fetch_limit)
            )

    # Sort merged events by the same total ordering used by the cursor:
    # (timestamp DESC, type ASC, _id DESC). This ensures stable ordering
    # across pages — the cursor filter and the sort share the same key.
    events.sort(key=lambda e: (e["timestamp"], e["type"], e["_id"]), reverse=True)

    # Apply limit (take top N from merged candidates)
    has_more = len(events) > limit
    page = events[:limit]

    # Build next_cursor from last event on page
    next_cursor = None
    if has_more and page:
        last = page[-1]
        next_cursor = _make_cursor(
            datetime.fromisoformat(last["timestamp"]),
            last["type"],
            uuid.UUID(last["_id"]),
        )

    # Strip internal _id field from response
    for e in page:
        e.pop("_id", None)

    pagination = {
        "limit": limit,
        "has_more": has_more,
        "has_more_advisory": "has_more:false is authoritative; has_more:true means 'likely more, fetch to confirm'",
    }
    if next_cursor:
        pagination["next_cursor"] = next_cursor

    return {
        "events": page,
        "pagination": pagination,
        "generated_at": now.isoformat(),
    }


def _apply_cursor_filter(query, timestamp_col, id_col, source_type: str, parsed_cursor):
    """Apply cursor-based filtering to a query.

    The total ordering is (timestamp DESC, type DESC, id DESC). The cursor
    represents the last item on the previous page. We want rows that sort
    AFTER the cursor in this descending order:
      - timestamp < cursor_ts, OR
      - timestamp == cursor_ts AND source_type < cursor_source, OR
      - timestamp == cursor_ts AND source_type == cursor_source AND id < cursor_id

    Each per-source query knows its own source_type, so the middle condition
    collapses to a constant (this source sorts before/after cursor source).
    """
    if parsed_cursor:
        cursor_ts, cursor_source, cursor_id = parsed_cursor
        from sqlalchemy import or_, and_

        if source_type == cursor_source:
            # Same source: timestamp < OR (timestamp == AND id < cursor_id)
            query = query.where(
                or_(
                    timestamp_col < cursor_ts,
                    and_(
                        timestamp_col == cursor_ts,
                        cast(id_col, String) < cursor_id,
                    ),
                )
            )
        elif source_type < cursor_source:
            # This source type sorts after cursor in DESC order.
            # Include rows at timestamp <= cursor_ts (they all sort after cursor).
            query = query.where(timestamp_col <= cursor_ts)
        else:
            # This source type sorts before cursor in DESC order.
            # At the same timestamp, these would have appeared on the previous page.
            # Only include rows with timestamp strictly before cursor.
            query = query.where(timestamp_col < cursor_ts)
    return query


def _apply_date_range(query, timestamp_col, since, until):
    """Apply date range filters."""
    if since:
        query = query.where(timestamp_col >= since)
    if until:
        query = query.where(timestamp_col <= until)
    return query


def _fetch_commit_events(
    db: Session, org_id, repo_id, since, until, parsed_cursor, fetch_limit
) -> list[dict]:
    """Fetch commit events."""
    query = (
        select(Commit)
        .where(Commit.organization_id == org_id)
        .order_by(desc(Commit.committed_at), desc(cast(Commit.id, String)))
        .limit(fetch_limit)
    )

    if repo_id:
        # Need to resolve repo's canonical_identifier
        repo = db.execute(
            select(Repository.canonical_identifier).where(Repository.id == repo_id)
        ).scalar_one_or_none()
        if repo:
            query = query.where(Commit.repo_identifier == repo)

    query = _apply_cursor_filter(query, Commit.committed_at, Commit.id, "commit", parsed_cursor)
    query = _apply_date_range(query, Commit.committed_at, since, until)

    commits = db.execute(query).scalars().all()

    events = []
    for c in commits:
        if c.committed_at is None:
            continue

        # Get observation and drift count for this commit
        obs = db.execute(
            select(CommitObservation).where(
                CommitObservation.commit_id == c.id,
                CommitObservation.observation_status == "observed",
            )
        ).scalar_one_or_none()

        drift_count = 0
        if obs:
            drift_count = db.execute(
                select(func.count(PolicyDriftFinding.id)).where(
                    PolicyDriftFinding.commit_id == c.id,
                    PolicyDriftFinding.severity == "drift",
                )
            ).scalar_one()

        # Find repo name from identifier
        repo_row = db.execute(
            select(Repository.id, Repository.name).where(
                Repository.canonical_identifier == c.repo_identifier,
                Repository.organization_id == org_id,
            )
        ).first()

        msg_summary = (c.commit_message or "").split("\n")[0][:100]

        events.append({
            "type": "commit",
            "timestamp": c.committed_at.isoformat(),
            "_id": str(c.id),
            "repo": {"id": str(repo_row[0]), "name": repo_row[1]} if repo_row else None,
            "summary": msg_summary,
            "detail": {
                "commit_sha": c.commit_sha,
                "author": c.author_identity,
                "models": c.model_identities,
                "has_observation": obs is not None,
                "drift_count": drift_count,
            },
        })

    return events


def _fetch_policy_activation_events(
    db: Session, org_id, policy_id, since, until, parsed_cursor, fetch_limit
) -> list[dict]:
    """Fetch policy activation events from audit log."""
    query = (
        select(AdminAuditLog)
        .where(
            AdminAuditLog.organization_id == org_id,
            AdminAuditLog.action.like("policy.activate%"),
        )
        .order_by(desc(AdminAuditLog.created_at), desc(cast(AdminAuditLog.id, String)))
        .limit(fetch_limit)
    )

    if policy_id:
        # Filter by detail->'policy_id' if available
        query = query.where(
            AdminAuditLog.detail["policy_id"].astext == str(policy_id)
        )

    query = _apply_cursor_filter(query, AdminAuditLog.created_at, AdminAuditLog.id, "policy_activation", parsed_cursor)
    query = _apply_date_range(query, AdminAuditLog.created_at, since, until)

    logs = db.execute(query).scalars().all()

    events = []
    for log in logs:
        detail = log.detail or {}
        # Try to get policy name
        pid = detail.get("policy_id")
        policy_name = detail.get("policy_name", "Unknown")
        if pid and not detail.get("policy_name"):
            p = db.execute(
                select(Policy.name).where(Policy.id == uuid.UUID(pid))
            ).scalar_one_or_none()
            if p:
                policy_name = p

        events.append({
            "type": "policy_activation",
            "timestamp": log.created_at.isoformat(),
            "_id": str(log.id),
            "policy": {"id": pid, "name": policy_name},
            "summary": f"Version {detail.get('version_number', '?')} activated",
            "detail": {
                "version_number": detail.get("version_number"),
                "targets_affected": detail.get("targets_affected"),
                "rollouts_created": detail.get("rollouts_created"),
            },
        })

    return events


def _fetch_drift_events(
    db: Session, org_id, repo_id, policy_id, since, until, parsed_cursor, fetch_limit
) -> list[dict]:
    """Fetch drift detection events."""
    query = (
        select(PolicyDriftFinding)
        .where(
            PolicyDriftFinding.organization_id == org_id,
            PolicyDriftFinding.severity == "drift",
        )
        .order_by(desc(PolicyDriftFinding.created_at), desc(cast(PolicyDriftFinding.id, String)))
        .limit(fetch_limit)
    )

    if repo_id:
        query = query.where(PolicyDriftFinding.repository_id == repo_id)
    if policy_id:
        query = query.where(PolicyDriftFinding.policy_id == policy_id)

    query = _apply_cursor_filter(query, PolicyDriftFinding.created_at, PolicyDriftFinding.id, "drift_detected", parsed_cursor)
    query = _apply_date_range(query, PolicyDriftFinding.created_at, since, until)

    findings = db.execute(query).scalars().all()

    events = []
    for f in findings:
        # Resolve repo and policy names
        repo_row = db.execute(
            select(Repository.id, Repository.name).where(Repository.id == f.repository_id)
        ).first()
        policy_row = db.execute(
            select(Policy.id, Policy.name).where(Policy.id == f.policy_id)
        ).first()

        events.append({
            "type": "drift_detected",
            "timestamp": f.created_at.isoformat(),
            "_id": str(f.id),
            "repo": {"id": str(repo_row[0]), "name": repo_row[1]} if repo_row else None,
            "policy": {"id": str(policy_row[0]), "name": policy_row[1]} if policy_row else None,
            "summary": f"{f.check_name}: {f.severity}",
            "detail": {
                "check_name": f.check_name,
                "severity": f.severity,
            },
        })

    return events


def _fetch_report_events(
    db: Session, org_id, since, until, parsed_cursor, fetch_limit
) -> list[dict]:
    """Fetch report completion events."""
    query = (
        select(ReportRun)
        .where(
            ReportRun.organization_id == org_id,
            ReportRun.status == "completed",
        )
        .order_by(desc(ReportRun.completed_at), desc(cast(ReportRun.id, String)))
        .limit(fetch_limit)
    )

    query = _apply_cursor_filter(query, ReportRun.completed_at, ReportRun.id, "report_completed", parsed_cursor)
    query = _apply_date_range(query, ReportRun.completed_at, since, until)

    runs = db.execute(query).scalars().all()

    events = []
    for r in runs:
        if r.completed_at is None:
            continue
        events.append({
            "type": "report_completed",
            "timestamp": r.completed_at.isoformat(),
            "_id": str(r.id),
            "summary": f"{r.run_type.capitalize()} report: {r.scope or 'unknown'}",
            "detail": {
                "run_type": r.run_type,
                "scope": r.scope,
            },
        })

    return events


def _fetch_sync_events(
    db: Session, org_id, since, until, parsed_cursor, fetch_limit
) -> list[dict]:
    """Fetch provider sync events."""
    query = (
        select(ProviderSyncRun)
        .where(
            ProviderSyncRun.organization_id == org_id,
            ProviderSyncRun.status == "completed",
        )
        .order_by(desc(ProviderSyncRun.completed_at), desc(cast(ProviderSyncRun.id, String)))
        .limit(fetch_limit)
    )

    query = _apply_cursor_filter(query, ProviderSyncRun.completed_at, ProviderSyncRun.id, "provider_sync", parsed_cursor)
    query = _apply_date_range(query, ProviderSyncRun.completed_at, since, until)

    runs = db.execute(query).scalars().all()

    events = []
    for r in runs:
        if r.completed_at is None:
            continue
        events.append({
            "type": "provider_sync",
            "timestamp": r.completed_at.isoformat(),
            "_id": str(r.id),
            "summary": f"{r.run_type.capitalize()} sync completed",
            "detail": {
                "commits_found": r.commits_found,
                "jobs_created": r.jobs_created,
            },
        })

    return events
