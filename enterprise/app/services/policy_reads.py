"""Policy compliance read-model service — per-policy target breakdown."""

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


def get_policy_compliance(
    db: Session, org_id: uuid.UUID, policy_id: uuid.UUID
) -> dict | None:
    """Per-repo compliance breakdown for a policy."""
    policy = db.execute(
        select(Policy).where(
            Policy.id == policy_id,
            Policy.organization_id == org_id,
        )
    ).scalar_one_or_none()

    if policy is None:
        return None

    # Active version
    active_version = db.execute(
        select(PolicyVersion).where(
            PolicyVersion.policy_id == policy.id,
            PolicyVersion.is_active == True,
        )
    ).scalar_one_or_none()

    # Version count
    version_count = db.execute(
        select(func.count(PolicyVersion.id)).where(
            PolicyVersion.policy_id == policy.id
        )
    ).scalar_one()

    # Active targets
    targets = db.execute(
        select(PolicyTarget, Repository)
        .join(Repository, PolicyTarget.repository_id == Repository.id)
        .where(
            PolicyTarget.policy_id == policy.id,
            PolicyTarget.active == True,
        )
    ).all()

    target_count = len(targets)

    # Per-repo compliance
    compliance_counts = {
        "aligned": 0, "drifting": 0, "pending": 0,
        "failed": 0, "unknown": 0,
    }
    repos_list = []

    for target, repo in targets:
        # Rollout status for this policy+repo
        latest_rollout = db.execute(
            select(PolicyRollout)
            .where(
                PolicyRollout.policy_id == policy.id,
                PolicyRollout.repository_id == repo.id,
                PolicyRollout.status.in_(["pending", "applied", "failed"]),
            )
            .order_by(desc(PolicyRollout.created_at))
            .limit(1)
        ).scalar_one_or_none()

        rollout_status = latest_rollout.status if latest_rollout else None

        # Determine compliance for this repo relative to this policy
        if rollout_status == "failed":
            repo_compliance = "failed"
        elif rollout_status == "pending":
            repo_compliance = "pending"
        else:
            # Rollout applied or no rollout — check observation + drift.
            # Only consider observations from commits AFTER this policy version's
            # rollout was applied. This prevents reporting compliance from
            # pre-rollout evidence.
            if latest_rollout is None or latest_rollout.applied_at is None:
                # No applied rollout for this policy+repo — cannot assess
                repo_compliance = "unknown"
                latest_obs = None
            else:
                obs_query = (
                    select(CommitObservation, Commit)
                    .join(Commit, CommitObservation.commit_id == Commit.id)
                    .where(
                        CommitObservation.repository_id == repo.id,
                        CommitObservation.organization_id == org_id,
                        CommitObservation.observation_status == "observed",
                        Commit.committed_at >= latest_rollout.applied_at,
                    )
                )

                latest_obs = db.execute(
                    obs_query.order_by(desc(Commit.committed_at)).limit(1)
                ).first()

                if latest_obs is None:
                    repo_compliance = "unknown"
                else:
                    # Check drift findings for this policy + latest commit
                    drift_findings_rows = db.execute(
                        select(PolicyDriftFinding).where(
                            PolicyDriftFinding.policy_id == policy.id,
                            PolicyDriftFinding.repository_id == repo.id,
                            PolicyDriftFinding.commit_id == latest_obs[0].commit_id,
                            PolicyDriftFinding.severity == "drift",
                        )
                    ).scalars().all()

                    if drift_findings_rows:
                        repo_compliance = "drifting"
                    else:
                        repo_compliance = "aligned"

        compliance_counts[repo_compliance] += 1

        # Build drift findings list
        drift_findings = []
        if repo_compliance == "drifting" and latest_obs:
            drift_findings = [
                {"check_name": f.check_name, "severity": f.severity, "detail": f.detail}
                for f in drift_findings_rows
            ]

        repos_list.append({
            "repository_id": str(repo.id),
            "canonical_identifier": repo.canonical_identifier,
            "name": repo.name,
            "compliance_status": repo_compliance,
            "rollout_status": rollout_status,
            "latest_commit_sha": latest_obs[1].commit_sha if latest_obs else None,
            "latest_observation_at": latest_obs[0].created_at.isoformat() if latest_obs else None,
            "drift_findings": drift_findings,
        })

    # Rollout progress (all rollouts, not just non-terminal)
    rollout_counts = db.execute(
        select(PolicyRollout.status, func.count(PolicyRollout.id))
        .where(PolicyRollout.policy_id == policy.id)
        .group_by(PolicyRollout.status)
    ).all()
    rollout_progress = {
        "pending": 0, "applied": 0, "failed": 0,
        "outdated": 0, "superseded": 0,
    }
    for status, count in rollout_counts:
        if status in rollout_progress:
            rollout_progress[status] = count

    return {
        "policy": {
            "id": str(policy.id),
            "name": policy.name,
            "slug": policy.slug,
            "status": policy.status,
            "active_version": {
                "version_number": active_version.version_number,
                "content_hash": active_version.content_hash,
                "created_at": active_version.created_at.isoformat(),
                "notes": active_version.notes,
            } if active_version else None,
            "version_count": version_count,
            "target_count": target_count,
        },
        "compliance": {
            **compliance_counts,
            "repos": repos_list,
        },
        "rollout_progress": rollout_progress,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
