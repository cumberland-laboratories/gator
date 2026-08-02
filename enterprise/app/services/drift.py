"""Drift evaluation service — compare observed state to policy expectations.

Separate from reporting: drift evaluation mutates evidence state (findings),
reporting only reads existing facts and findings.

Three supported checks (MVP):
- charter_required: at least one charter file in .gator/charters/
- status_json_required: .gator/status.json present
- trailers_required: governance trailers present in commit message
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.commit import Commit
from app.models.commit_observation import CommitObservation
from app.models.drift_finding import PolicyDriftFinding
from app.models.policy import Policy, PolicyVersion
from app.models.policy_target import PolicyTarget


SUPPORTED_CHECKS = {
    "charter_required",
    "status_json_required",
    "trailers_required",
}


def compare_policy(observation: CommitObservation, policy_version: PolicyVersion) -> list[dict]:
    """Compare an observation against a policy version's content.

    Returns a list of finding dicts (one per supported check in the policy).
    Only evaluates checks that are both (a) in the policy content and (b) in SUPPORTED_CHECKS.
    """
    content = policy_version.content or {}
    findings = []

    if content.get("charter_required"):
        charter_count = observation.charter_count or 0
        aligned = charter_count > 0
        findings.append({
            "check_name": "charter_required",
            "severity": "aligned" if aligned else "drift",
            "expected": {"charter_required": True},
            "observed": {"charter_count": charter_count},
            "detail": f"{'At least one charter found' if aligned else 'No charters found'} in .gator/charters/",
        })

    if content.get("status_json_required"):
        present = observation.status_json_present or False
        aligned = present
        findings.append({
            "check_name": "status_json_required",
            "severity": "aligned" if aligned else "drift",
            "expected": {"status_json_required": True},
            "observed": {"status_json_present": present},
            "detail": f".gator/status.json {'present' if present else 'not found'}",
        })

    if content.get("trailers_required"):
        trailers = observation.trailers or {}
        has_trailers = len(trailers) > 0
        findings.append({
            "check_name": "trailers_required",
            "severity": "aligned" if has_trailers else "drift",
            "expected": {"trailers_required": True},
            "observed": {"trailer_count": len(trailers), "trailer_keys": list(trailers.keys())},
            "detail": f"{'Governance trailers found' if has_trailers else 'No governance trailers found'} in commit message",
        })

    return findings


def evaluate_commit_drift(db: Session, commit: Commit, observation: CommitObservation):
    """Evaluate drift for a commit against all active policies targeting its repo.

    Upserts findings: unique on (policy_version_id, repository_id, commit_id, check_name).
    """
    # Get all active policies targeting this repo
    targets = db.execute(
        select(PolicyTarget).where(
            PolicyTarget.repository_id == observation.repository_id,
            PolicyTarget.active == True,
        )
    ).scalars().all()

    for target in targets:
        # Get the active version for this policy
        active_version = db.execute(
            select(PolicyVersion).where(
                PolicyVersion.policy_id == target.policy_id,
                PolicyVersion.is_active == True,
            )
        ).scalar_one_or_none()

        if active_version is None:
            continue  # Policy exists but has no active version

        policy = db.execute(
            select(Policy).where(Policy.id == target.policy_id)
        ).scalar_one()

        findings = compare_policy(observation, active_version)

        for f in findings:
            # Upsert: check for existing finding
            existing = db.execute(
                select(PolicyDriftFinding).where(
                    PolicyDriftFinding.policy_version_id == active_version.id,
                    PolicyDriftFinding.repository_id == observation.repository_id,
                    PolicyDriftFinding.commit_id == commit.id,
                    PolicyDriftFinding.check_name == f["check_name"],
                )
            ).scalar_one_or_none()

            if existing:
                existing.severity = f["severity"]
                existing.expected = f["expected"]
                existing.observed = f["observed"]
                existing.detail = f["detail"]
            else:
                db.add(PolicyDriftFinding(
                    organization_id=commit.organization_id,
                    policy_id=policy.id,
                    policy_version_id=active_version.id,
                    repository_id=observation.repository_id,
                    commit_id=commit.id,
                    check_name=f["check_name"],
                    severity=f["severity"],
                    expected=f["expected"],
                    observed=f["observed"],
                    detail=f["detail"],
                ))

    db.commit()
