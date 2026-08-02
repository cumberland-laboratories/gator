"""Fleet read-model service — compliance bucketing, fleet summary, org overview.

This is E5's core service. The six-state compliance bucketing logic is defined
here once and reused by fleet summary, fleet repo list, repo detail, and policy
compliance endpoints.

Compliance states (evaluation precedence: failed > pending > drifting > aligned > unknown > ungoverned):
  - aligned: active targets, all rollouts applied, observation exists, zero drift findings
  - drifting: active targets, rollout applied, observation exists, drift findings present
  - pending: active targets, at least one rollout in pending state
  - failed: active targets, at least one rollout in failed state
  - unknown: active targets, all rollouts applied, but no observation yet
  - ungoverned: no active policy targets
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, distinct, exists, func, select
from sqlalchemy.orm import Session

from app.models.api_token import ApiToken
from app.models.commit import Commit
from app.models.commit_observation import CommitObservation
from app.models.evidence_block import CommitEvidenceBlock
from app.models.drift_finding import PolicyDriftFinding
from app.models.git_provider import GitProvider
from app.models.ingest_job import IngestJob
from app.models.organization import Organization
from app.models.policy import Policy
from app.models.policy_rollout import PolicyRollout
from app.models.policy_target import PolicyTarget
from app.models.repository import Repository


def compute_repo_compliance(
    db: Session, org_id: uuid.UUID, repo_id: uuid.UUID
) -> str:
    """Compute the compliance status for a single repo.

    Returns one of: aligned, drifting, pending, failed, unknown, ungoverned.
    """
    # Check if repo has any active policy targets
    has_targets = db.execute(
        select(func.count(PolicyTarget.id)).where(
            PolicyTarget.repository_id == repo_id,
            PolicyTarget.active == True,
        )
    ).scalar_one()

    if has_targets == 0:
        return "ungoverned"

    # Check rollout states — failed takes precedence over pending
    rollout_states = db.execute(
        select(PolicyRollout.status, func.count(PolicyRollout.id))
        .where(
            PolicyRollout.repository_id == repo_id,
            PolicyRollout.organization_id == org_id,
            PolicyRollout.status.in_(["pending", "failed", "applied"]),
        )
        .group_by(PolicyRollout.status)
    ).all()

    state_counts = {row[0]: row[1] for row in rollout_states}

    if state_counts.get("failed", 0) > 0:
        return "failed"
    if state_counts.get("pending", 0) > 0:
        return "pending"

    # All rollouts are applied (or no non-terminal rollouts exist).
    # Find the LATEST applied_at among current rollouts — observations must be
    # after ALL policies are applied to count. Using max ensures we don't evaluate
    # against evidence from between two rollout applications.
    latest_applied = db.execute(
        select(func.max(PolicyRollout.applied_at)).where(
            PolicyRollout.repository_id == repo_id,
            PolicyRollout.organization_id == org_id,
            PolicyRollout.status == "applied",
        )
    ).scalar_one()

    # Check for observations after the most recent rollout was applied
    obs_query = (
        select(CommitObservation)
        .join(Commit, CommitObservation.commit_id == Commit.id)
        .where(
            CommitObservation.repository_id == repo_id,
            CommitObservation.organization_id == org_id,
            CommitObservation.observation_status == "observed",
        )
    )
    if latest_applied:
        obs_query = obs_query.where(Commit.committed_at >= latest_applied)

    latest_observation = db.execute(
        obs_query.order_by(Commit.committed_at.desc()).limit(1)
    ).scalar_one_or_none()

    if latest_observation is None:
        return "unknown"

    # Check drift findings against latest observed commit
    drift_count = db.execute(
        select(func.count(PolicyDriftFinding.id)).where(
            PolicyDriftFinding.repository_id == repo_id,
            PolicyDriftFinding.organization_id == org_id,
            PolicyDriftFinding.commit_id == latest_observation.commit_id,
            PolicyDriftFinding.severity == "drift",
        )
    ).scalar_one()

    if drift_count > 0:
        return "drifting"

    return "aligned"


def compute_fleet_compliance(
    db: Session, org_id: uuid.UUID
) -> dict[str, list[uuid.UUID]]:
    """Compute compliance status for all active repos in the org.

    Returns a dict mapping compliance status to list of repo IDs.
    Avoids N+1 by batching where possible, but calls per-repo logic
    for correctness (compliance bucketing involves multiple tables
    and state precedence that's hard to express in a single query).
    """
    repos = db.execute(
        select(Repository.id).where(
            Repository.organization_id == org_id,
            Repository.active == True,
        )
    ).scalars().all()

    buckets: dict[str, list[uuid.UUID]] = {
        "aligned": [],
        "drifting": [],
        "pending": [],
        "failed": [],
        "unknown": [],
        "ungoverned": [],
    }

    for repo_id in repos:
        status = compute_repo_compliance(db, org_id, repo_id)
        buckets[status].append(repo_id)

    return buckets


def get_fleet_summary(db: Session, org_id: uuid.UUID) -> dict:
    """Full fleet summary for the org."""
    # Org metadata
    org = db.execute(
        select(Organization).where(Organization.id == org_id)
    ).scalar_one()

    # Repo counts
    total_repos = db.execute(
        select(func.count(Repository.id)).where(
            Repository.organization_id == org_id
        )
    ).scalar_one()
    active_repos = db.execute(
        select(func.count(Repository.id)).where(
            Repository.organization_id == org_id,
            Repository.active == True,
        )
    ).scalar_one()

    # Compliance bucketing
    buckets = compute_fleet_compliance(db, org_id)
    by_compliance = {k: len(v) for k, v in buckets.items()}

    # Policy counts
    total_policies = db.execute(
        select(func.count(Policy.id)).where(
            Policy.organization_id == org_id
        )
    ).scalar_one()
    active_policies = db.execute(
        select(func.count(Policy.id)).where(
            Policy.organization_id == org_id,
            Policy.status == "active",
        )
    ).scalar_one()

    # Drift findings
    total_drift = db.execute(
        select(func.count(PolicyDriftFinding.id)).where(
            PolicyDriftFinding.organization_id == org_id,
        )
    ).scalar_one()
    drift_severity_count = db.execute(
        select(func.count(PolicyDriftFinding.id)).where(
            PolicyDriftFinding.organization_id == org_id,
            PolicyDriftFinding.severity == "drift",
        )
    ).scalar_one()
    repos_with_drift = db.execute(
        select(func.count(distinct(PolicyDriftFinding.repository_id))).where(
            PolicyDriftFinding.organization_id == org_id,
            PolicyDriftFinding.severity == "drift",
        )
    ).scalar_one()

    # Ingest health
    now = datetime.now(timezone.utc)
    commits_24h = db.execute(
        select(func.count(Commit.id)).where(
            Commit.organization_id == org_id,
            Commit.ingested_at >= now - timedelta(hours=24),
        )
    ).scalar_one()
    commits_7d = db.execute(
        select(func.count(Commit.id)).where(
            Commit.organization_id == org_id,
            Commit.ingested_at >= now - timedelta(days=7),
        )
    ).scalar_one()
    pending_jobs = db.execute(
        select(func.count(IngestJob.id)).where(
            IngestJob.organization_id == org_id,
            IngestJob.status == "pending",
        )
    ).scalar_one()
    failed_jobs_24h = db.execute(
        select(func.count(IngestJob.id)).where(
            IngestJob.organization_id == org_id,
            IngestJob.status == "failed",
            IngestJob.completed_at >= now - timedelta(hours=24),
        )
    ).scalar_one()

    # Providers
    providers = db.execute(
        select(GitProvider).where(
            GitProvider.organization_id == org_id
        )
    ).scalars().all()

    provider_list = []
    for p in providers:
        repo_count = db.execute(
            select(func.count(Repository.id)).where(
                Repository.provider_id == p.id,
                Repository.active == True,
            )
        ).scalar_one()
        provider_list.append({
            "id": str(p.id),
            "type": p.provider_type,
            "status": p.status,
            "repos_tracked": repo_count,
        })

    # Session block coverage
    total_blocks = db.execute(
        select(func.count(CommitEvidenceBlock.id))
        .join(Commit, CommitEvidenceBlock.commit_id == Commit.id)
        .where(
            Commit.organization_id == org_id,
            CommitEvidenceBlock.block_type == "session_block",
        )
    ).scalar_one()
    total_turns = db.execute(
        select(func.coalesce(func.sum(CommitEvidenceBlock.turn_count), 0))
        .join(Commit, CommitEvidenceBlock.commit_id == Commit.id)
        .where(
            Commit.organization_id == org_id,
            CommitEvidenceBlock.block_type == "session_block",
        )
    ).scalar_one()
    # Pending: AI-assisted commits with no session block
    has_block = select(CommitEvidenceBlock.commit_id).where(
        CommitEvidenceBlock.block_type == "session_block"
    ).scalar_subquery()
    pending_on_machines = db.execute(
        select(func.count(Commit.id)).where(
            Commit.organization_id == org_id,
            Commit.snippet_agent.isnot(None),
            Commit.machine_id.isnot(None),
            ~Commit.id.in_(has_block),
        )
    ).scalar_one()

    return {
        "organization": {"id": str(org.id), "name": org.name, "slug": org.slug},
        "repos": {
            "total": total_repos,
            "active": active_repos,
            "inactive": total_repos - active_repos,
            "by_compliance": by_compliance,
        },
        "policies": {
            "total": total_policies,
            "active": active_policies,
            "draft": total_policies - active_policies,
        },
        "drift": {
            "total_findings": total_drift,
            "open_findings": drift_severity_count,
            "repos_with_drift": repos_with_drift,
        },
        "session_blocks": {
            "total_blocks": total_blocks,
            "total_turns": total_turns,
            "pending_on_machines": pending_on_machines,
        },
        "ingest": {
            "commits_last_24h": commits_24h,
            "commits_last_7d": commits_7d,
            "pending_jobs": pending_jobs,
            "failed_jobs_last_24h": failed_jobs_24h,
        },
        "providers": provider_list,
        "generated_at": now.isoformat(),
    }


def get_fleet_repos(
    db: Session,
    org_id: uuid.UUID,
    compliance_filter: str | None = None,
    sort_by: str = "name",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Paginated fleet repo list with compliance status."""
    buckets = compute_fleet_compliance(db, org_id)

    # Build flat list with compliance status
    repo_ids_with_status: list[tuple[uuid.UUID, str]] = []
    for status, ids in buckets.items():
        if compliance_filter and status != compliance_filter:
            continue
        for rid in ids:
            repo_ids_with_status.append((rid, status))

    total = len(repo_ids_with_status)

    # Fetch repo details for the page
    # First get all repo IDs we need
    all_ids = [r[0] for r in repo_ids_with_status]
    if not all_ids:
        return {"repos": [], "pagination": {"offset": offset, "limit": limit, "total": 0}}

    repos_by_id = {}
    repos = db.execute(
        select(Repository).where(Repository.id.in_(all_ids))
    ).scalars().all()
    for r in repos:
        repos_by_id[r.id] = r

    # Build result rows
    rows = []
    for repo_id, compliance_status in repo_ids_with_status:
        repo = repos_by_id.get(repo_id)
        if not repo:
            continue

        # Get latest observation for charter_count and last_observation_at
        obs = db.execute(
            select(CommitObservation, Commit)
            .join(Commit, CommitObservation.commit_id == Commit.id)
            .where(
                CommitObservation.repository_id == repo_id,
                CommitObservation.organization_id == org_id,
                CommitObservation.observation_status == "observed",
            )
            .order_by(Commit.committed_at.desc())
            .limit(1)
        ).first()

        # Drift count for this repo
        drift_count = db.execute(
            select(func.count(PolicyDriftFinding.id)).where(
                PolicyDriftFinding.repository_id == repo_id,
                PolicyDriftFinding.organization_id == org_id,
                PolicyDriftFinding.severity == "drift",
            )
        ).scalar_one()

        # Policy count
        policy_count = db.execute(
            select(func.count(PolicyTarget.id)).where(
                PolicyTarget.repository_id == repo_id,
                PolicyTarget.active == True,
            )
        ).scalar_one()

        rows.append({
            "id": str(repo.id),
            "canonical_identifier": repo.canonical_identifier,
            "name": repo.name,
            "active": repo.active,
            "compliance_status": compliance_status,
            "policy_count": policy_count,
            "drift_count": drift_count,
            "last_commit_at": obs[1].committed_at.isoformat() if obs else None,
            "last_observation_at": obs[0].created_at.isoformat() if obs else None,
            "charter_count": obs[0].charter_count if obs else None,
        })

    # Sort
    sort_key = {
        "name": lambda r: (r["name"] or "").lower(),
        "last_commit_at": lambda r: r["last_commit_at"] or "",
        "drift_count": lambda r: -r["drift_count"],
    }.get(sort_by, lambda r: (r["name"] or "").lower())

    rows.sort(key=sort_key)

    # Paginate
    page = rows[offset:offset + limit]

    return {
        "repos": page,
        "pagination": {"offset": offset, "limit": limit, "total": total},
    }


def get_org_overview(db: Session, org_id: uuid.UUID) -> dict:
    """Org/tenant health overview."""
    now = datetime.now(timezone.utc)

    org = db.execute(
        select(Organization).where(Organization.id == org_id)
    ).scalar_one()

    # Providers with repo counts and last sync
    from app.models.sync_run import ProviderSyncRun

    providers = db.execute(
        select(GitProvider).where(GitProvider.organization_id == org_id)
    ).scalars().all()

    provider_list = []
    for p in providers:
        repo_count = db.execute(
            select(func.count(Repository.id)).where(
                Repository.provider_id == p.id,
                Repository.active == True,
            )
        ).scalar_one()
        last_sync = db.execute(
            select(ProviderSyncRun)
            .where(ProviderSyncRun.provider_id == p.id)
            .order_by(ProviderSyncRun.started_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        provider_list.append({
            "id": str(p.id),
            "type": p.provider_type,
            "status": p.status,
            "repos_tracked": repo_count,
            "last_sync": last_sync.started_at.isoformat() if last_sync else None,
            "last_sync_status": last_sync.status if last_sync else None,
        })

    # Tokens — only what the model supports
    total_tokens = db.execute(
        select(func.count(ApiToken.id)).where(
            ApiToken.organization_id == org_id
        )
    ).scalar_one()
    expired_tokens = db.execute(
        select(func.count(ApiToken.id)).where(
            ApiToken.organization_id == org_id,
            ApiToken.expires_at < now,
        )
    ).scalar_one()
    most_recent_use = db.execute(
        select(func.max(ApiToken.last_used_at)).where(
            ApiToken.organization_id == org_id
        )
    ).scalar_one()

    # Job queue health
    pending_jobs = db.execute(
        select(func.count(IngestJob.id)).where(
            IngestJob.organization_id == org_id,
            IngestJob.status == "pending",
        )
    ).scalar_one()
    failed_24h = db.execute(
        select(func.count(IngestJob.id)).where(
            IngestJob.organization_id == org_id,
            IngestJob.status == "failed",
            IngestJob.completed_at >= now - timedelta(hours=24),
        )
    ).scalar_one()
    completed_24h = db.execute(
        select(func.count(IngestJob.id)).where(
            IngestJob.organization_id == org_id,
            IngestJob.status == "completed",
            IngestJob.completed_at >= now - timedelta(hours=24),
        )
    ).scalar_one()
    oldest_pending = db.execute(
        select(func.min(IngestJob.created_at)).where(
            IngestJob.organization_id == org_id,
            IngestJob.status == "pending",
        )
    ).scalar_one()

    return {
        "organization": {"id": str(org.id), "name": org.name, "slug": org.slug},
        "providers": provider_list,
        "tokens": {
            "total": total_tokens,
            "expired": expired_tokens,
            "most_recent_use": most_recent_use.isoformat() if most_recent_use else None,
        },
        "jobs": {
            "pending": pending_jobs,
            "failed_last_24h": failed_24h,
            "completed_last_24h": completed_24h,
            "oldest_pending": oldest_pending.isoformat() if oldest_pending else None,
        },
        "generated_at": now.isoformat(),
    }
