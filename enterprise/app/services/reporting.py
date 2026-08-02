"""Reporting service — read-only materialization of existing evidence and findings.

Reports NEVER mutate evidence state. They only read observations and drift
findings that were produced by the evidence extraction and drift evaluation
layers, then assemble materialized snapshots.

"Current" definition:
- Latest observed commit per repo (most recent committed_at with observation_status=observed)
- Currently active policy version only
- Only policies that currently target this repo (active policy_target row)
"""

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.models.commit import Commit
from app.models.commit_observation import CommitObservation
from app.models.drift_finding import PolicyDriftFinding
from app.models.policy import Policy, PolicyVersion
from app.models.policy_target import PolicyTarget
from app.models.report_run import ReportRun
from app.models.report_snapshot import ReportSnapshot
from app.models.repository import Repository


def _canonical_hash(content: dict) -> str:
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _get_latest_observation(db: Session, repo_id) -> tuple[CommitObservation | None, Commit | None]:
    """Get the latest observation for a repo (most recent committed_at with observed status)."""
    result = db.execute(
        select(CommitObservation, Commit)
        .join(Commit, CommitObservation.commit_id == Commit.id)
        .where(
            CommitObservation.repository_id == repo_id,
            CommitObservation.observation_status == "observed",
        )
        .order_by(desc(Commit.committed_at))
        .limit(1)
    ).first()

    if result is None:
        return None, None
    return result.CommitObservation, result.Commit


def generate_repo_report(db: Session, repo: Repository) -> ReportSnapshot | None:
    """Generate a repo governance report from existing observations and findings."""
    now = datetime.now(timezone.utc)
    run = ReportRun(
        organization_id=repo.organization_id,
        run_type="repo",
        scope=repo.canonical_identifier,
        status="started",
        started_at=now,
    )
    db.add(run)
    db.flush()

    try:
        observation, commit = _get_latest_observation(db, repo.id)

        # Get currently targeted active policies
        targeted_policies = db.execute(
            select(Policy, PolicyVersion)
            .join(PolicyTarget, PolicyTarget.policy_id == Policy.id)
            .join(PolicyVersion, (PolicyVersion.policy_id == Policy.id) & (PolicyVersion.is_active == True))
            .where(
                PolicyTarget.repository_id == repo.id,
                PolicyTarget.active == True,
                Policy.organization_id == repo.organization_id,
            )
        ).all()

        # Build compliance summary
        policy_results = []
        for row in targeted_policies:
            policy, version = row.Policy, row.PolicyVersion

            findings = []
            if observation and commit:
                findings_rows = db.execute(
                    select(PolicyDriftFinding).where(
                        PolicyDriftFinding.policy_version_id == version.id,
                        PolicyDriftFinding.repository_id == repo.id,
                        PolicyDriftFinding.commit_id == commit.id,
                    )
                ).scalars().all()
                findings = [
                    {
                        "check_name": f.check_name,
                        "severity": f.severity,
                        "expected": f.expected,
                        "observed": f.observed,
                        "detail": f.detail,
                    }
                    for f in findings_rows
                ]

            has_drift = any(f["severity"] == "drift" for f in findings)
            if not observation:
                compliance = "no_observation"
            elif not findings:
                compliance = "no_findings"
            elif has_drift:
                compliance = "drift"
            else:
                compliance = "aligned"

            policy_results.append({
                "policy_id": str(policy.id),
                "policy_name": policy.name,
                "policy_version_number": version.version_number,
                "compliance": compliance,
                "findings": findings,
            })

        # Overall: drift if any drifting, unknown if any missing evidence, aligned only if all aligned
        if any(p["compliance"] == "drift" for p in policy_results):
            overall = "drift"
        elif any(p["compliance"] in ("no_observation", "no_findings") for p in policy_results):
            overall = "unknown"
        elif policy_results:
            overall = "aligned"
        else:
            overall = "no_policies"

        content = {
            "repository": repo.canonical_identifier,
            "repository_id": str(repo.id),
            "observation_commit": str(commit.commit_sha) if commit else None,
            "observation_at": commit.committed_at.isoformat() if commit and commit.committed_at else None,
            "observation": {
                "status_json_present": observation.status_json_present if observation else None,
                "charter_count": observation.charter_count if observation else None,
                "constitution_present": observation.constitution_present if observation else None,
                "trailers": observation.trailers if observation else None,
            } if observation else None,
            "policies": policy_results,
            "overall_compliance": overall,
            "generated_at": now.isoformat(),
        }

        snapshot = ReportSnapshot(
            organization_id=repo.organization_id,
            report_run_id=run.id,
            snapshot_type="repo_governance",
            scope=repo.canonical_identifier,
            content=content,
            content_hash=_canonical_hash(content),
        )
        db.add(snapshot)

        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        return snapshot

    except Exception as e:
        db.rollback()
        run.status = "failed"
        run.completed_at = datetime.now(timezone.utc)
        run.error = {"message": str(e)}
        db.add(run)
        db.commit()
        raise


def generate_policy_report(db: Session, policy: Policy) -> ReportSnapshot | None:
    """Generate a policy compliance report across all targeted repos."""
    now = datetime.now(timezone.utc)
    run = ReportRun(
        organization_id=policy.organization_id,
        run_type="policy",
        scope=policy.slug,
        status="started",
        started_at=now,
    )
    db.add(run)
    db.flush()

    try:
        # Get active version
        active_version = db.execute(
            select(PolicyVersion).where(
                PolicyVersion.policy_id == policy.id,
                PolicyVersion.is_active == True,
            )
        ).scalar_one_or_none()

        # Get all active targets
        targets = db.execute(
            select(PolicyTarget, Repository)
            .join(Repository, PolicyTarget.repository_id == Repository.id)
            .where(
                PolicyTarget.policy_id == policy.id,
                PolicyTarget.active == True,
            )
        ).all()

        repo_results = []
        for row in targets:
            target, repo = row.PolicyTarget, row.Repository
            observation, commit = _get_latest_observation(db, repo.id)

            findings = []
            if observation and commit and active_version:
                findings_rows = db.execute(
                    select(PolicyDriftFinding).where(
                        PolicyDriftFinding.policy_version_id == active_version.id,
                        PolicyDriftFinding.repository_id == repo.id,
                        PolicyDriftFinding.commit_id == commit.id,
                    )
                ).scalars().all()
                findings = [
                    {
                        "check_name": f.check_name,
                        "severity": f.severity,
                        "detail": f.detail,
                    }
                    for f in findings_rows
                ]

            has_drift = any(f["severity"] == "drift" for f in findings)
            if not observation:
                compliance = "no_observation"
            elif not findings:
                compliance = "no_findings"
            elif has_drift:
                compliance = "drift"
            else:
                compliance = "aligned"

            repo_results.append({
                "repository": repo.canonical_identifier,
                "repository_id": str(repo.id),
                "latest_commit": commit.commit_sha if commit else None,
                "compliance": compliance,
                "findings": findings,
            })

        aligned_count = sum(1 for r in repo_results if r["compliance"] == "aligned")
        drift_count = sum(1 for r in repo_results if r["compliance"] == "drift")

        content = {
            "policy_name": policy.name,
            "policy_slug": policy.slug,
            "policy_id": str(policy.id),
            "active_version": active_version.version_number if active_version else None,
            "targeted_repos": len(repo_results),
            "aligned": aligned_count,
            "drifting": drift_count,
            "repos": repo_results,
            "generated_at": now.isoformat(),
        }

        snapshot = ReportSnapshot(
            organization_id=policy.organization_id,
            report_run_id=run.id,
            snapshot_type="policy_compliance",
            scope=policy.slug,
            content=content,
            content_hash=_canonical_hash(content),
        )
        db.add(snapshot)

        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        return snapshot

    except Exception as e:
        db.rollback()
        run.status = "failed"
        run.completed_at = datetime.now(timezone.utc)
        run.error = {"message": str(e)}
        db.add(run)
        db.commit()
        raise
