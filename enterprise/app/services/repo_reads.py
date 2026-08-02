"""Repo detail read-model service — single-repo governance profile."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.commit import Commit
from app.models.commit_observation import CommitObservation
from app.models.drift_finding import PolicyDriftFinding
from app.models.policy import Policy, PolicyVersion
from app.models.policy_rollout import PolicyRollout
from app.models.policy_target import PolicyTarget
from app.models.repository import Repository
from app.services.fleet_reads import compute_repo_compliance


def get_repo_detail(
    db: Session, org_id: uuid.UUID, repo_id: uuid.UUID, commits_limit: int = 20
) -> dict | None:
    """Full governance profile for a single repo."""
    repo = db.execute(
        select(Repository).where(
            Repository.id == repo_id,
            Repository.organization_id == org_id,
        )
    ).scalar_one_or_none()

    if repo is None:
        return None

    compliance_status = compute_repo_compliance(db, org_id, repo_id)

    # Latest observation
    latest_obs_row = db.execute(
        select(CommitObservation, Commit)
        .join(Commit, CommitObservation.commit_id == Commit.id)
        .where(
            CommitObservation.repository_id == repo_id,
            CommitObservation.organization_id == org_id,
            CommitObservation.observation_status == "observed",
        )
        .order_by(desc(Commit.committed_at))
        .limit(1)
    ).first()

    latest_observation = None
    if latest_obs_row:
        obs, commit = latest_obs_row
        latest_observation = {
            "commit_sha": commit.commit_sha,
            "committed_at": commit.committed_at.isoformat() if commit.committed_at else None,
            "status_json_present": obs.status_json_present,
            "constitution_present": obs.constitution_present,
            "charter_count": obs.charter_count,
            "charter_names": obs.charter_names,
            "trailers": obs.trailers,
        }

    # Per-policy governance state
    targets = db.execute(
        select(PolicyTarget, Policy)
        .join(Policy, PolicyTarget.policy_id == Policy.id)
        .where(
            PolicyTarget.repository_id == repo_id,
            PolicyTarget.active == True,
        )
    ).all()

    policies_list = []
    for target, policy in targets:
        # Active version
        active_version = db.execute(
            select(PolicyVersion).where(
                PolicyVersion.policy_id == policy.id,
                PolicyVersion.is_active == True,
            )
        ).scalar_one_or_none()

        # Latest rollout for this repo+policy
        latest_rollout = db.execute(
            select(PolicyRollout)
            .where(
                PolicyRollout.policy_id == policy.id,
                PolicyRollout.repository_id == repo_id,
                PolicyRollout.status.in_(["pending", "applied", "failed"]),
            )
            .order_by(desc(PolicyRollout.created_at))
            .limit(1)
        ).scalar_one_or_none()

        # Drift findings for latest commit (if we have an observation)
        drift_findings = []
        if latest_obs_row:
            findings = db.execute(
                select(PolicyDriftFinding).where(
                    PolicyDriftFinding.policy_id == policy.id,
                    PolicyDriftFinding.repository_id == repo_id,
                    PolicyDriftFinding.commit_id == latest_obs_row[0].commit_id,
                    PolicyDriftFinding.severity == "drift",
                )
            ).scalars().all()
            drift_findings = [
                {"check_name": f.check_name, "severity": f.severity, "detail": f.detail}
                for f in findings
            ]

        # Determine drift_status with correct precedence
        if latest_rollout and latest_rollout.status in ("pending", "failed"):
            drift_status = latest_rollout.status
        elif not latest_obs_row:
            drift_status = "unknown"
        elif drift_findings:
            drift_status = "drifting"
        else:
            drift_status = "aligned"

        policies_list.append({
            "policy_id": str(policy.id),
            "name": policy.name,
            "slug": policy.slug,
            "active_version": active_version.version_number if active_version else None,
            "rollout_status": latest_rollout.status if latest_rollout else None,
            "drift_status": drift_status,
            "drift_findings": drift_findings,
        })

    # Recent commits
    commits = db.execute(
        select(Commit)
        .where(
            Commit.organization_id == org_id,
            Commit.repo_identifier == repo.canonical_identifier,
        )
        .order_by(desc(Commit.committed_at))
        .limit(commits_limit)
    ).scalars().all()

    recent_commits = []
    for c in commits:
        obs = db.execute(
            select(CommitObservation).where(
                CommitObservation.commit_id == c.id,
                CommitObservation.observation_status == "observed",
            )
        ).scalar_one_or_none()

        drift_count = db.execute(
            select(func.count(PolicyDriftFinding.id)).where(
                PolicyDriftFinding.commit_id == c.id,
                PolicyDriftFinding.severity == "drift",
            )
        ).scalar_one()

        # First line of commit message only
        msg = c.commit_message or ""
        msg_summary = msg.split("\n")[0][:100]

        recent_commits.append({
            "commit_sha": c.commit_sha,
            "author_identity": c.author_identity,
            "model_identities": c.model_identities,
            "committed_at": c.committed_at.isoformat() if c.committed_at else None,
            "message_summary": msg_summary,
            "has_observation": obs is not None,
            "drift_count": drift_count,
        })

    return {
        "repo": {
            "id": str(repo.id),
            "canonical_identifier": repo.canonical_identifier,
            "name": repo.name,
            "default_branch": repo.default_branch,
            "active": repo.active,
            "last_commit_sha": repo.last_commit_sha,
            "last_webhook_at": repo.last_webhook_at.isoformat() if repo.last_webhook_at else None,
            "last_reconciled_at": repo.last_reconciled_at.isoformat() if repo.last_reconciled_at else None,
        },
        "governance": {
            "compliance_status": compliance_status,
            "latest_observation": latest_observation,
            "policies": policies_list,
        },
        "recent_commits": recent_commits,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
