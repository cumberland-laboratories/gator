"""Policy service — state transitions, rollout generation, targeting.

All policy business logic lives here. Routes are thin.

Invariants:
- Versions are immutable after creation
- At most one active version per policy (enforced by partial unique index)
- At most one non-terminal rollout per (policy_id, repository_id) (enforced in service layer)
- Activation is idempotent: re-activating same version is a no-op per repo
- Historical rollouts (applied, outdated, superseded, failed) are never modified
"""

import hashlib
import json
import uuid

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.audit_log import AdminAuditLog
from app.models.policy import Policy, PolicyVersion
from app.models.policy_rollout import PolicyRollout
from app.models.policy_target import PolicyTarget
from app.models.repository import Repository


from app.models.commit_observation import CommitObservation
from app.models.commit import Commit
from app.models.ingest_job import IngestJob

NON_TERMINAL_STATUSES = ("pending", "applied")
TERMINAL_STATUSES = ("superseded", "failed", "outdated")


def _canonical_hash(content: dict) -> str:
    """Compute SHA-256 of canonical JSON serialization."""
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _enqueue_drift_refresh_for_repos(db: Session, org_id: uuid.UUID, repo_ids: list[uuid.UUID]):
    """Enqueue evaluate_drift jobs for repos using their latest observed commit."""
    from sqlalchemy import desc

    for repo_id in repo_ids:
        # Find the latest observed observation for this repo
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
            continue  # No observation yet for this repo

        commit = result.Commit
        db.add(IngestJob(
            organization_id=org_id,
            job_type="evaluate_drift",
            payload={"commit_id": str(commit.id)},
            status="pending",
        ))
    db.flush()


def create_policy(
    db: Session, org_id: uuid.UUID, name: str, slug: str, description: str | None = None,
    actor_token_id: uuid.UUID | None = None,
) -> Policy:
    """Create a new policy in draft status."""
    policy = Policy(
        organization_id=org_id,
        name=name,
        slug=slug,
        description=description,
        status="draft",
    )
    db.add(policy)
    db.add(AdminAuditLog(
        organization_id=org_id,
        actor_token_id=actor_token_id,
        action="policy.create",
        detail={"name": name, "slug": slug},
    ))
    db.flush()
    return policy


def create_version(
    db: Session, policy: Policy, content: dict, notes: str | None = None,
    created_by_token_id: uuid.UUID | None = None,
) -> PolicyVersion:
    """Create a new immutable policy version."""
    # Auto-increment version number
    max_version = db.execute(
        select(func.max(PolicyVersion.version_number)).where(
            PolicyVersion.policy_id == policy.id
        )
    ).scalar()
    next_version = (max_version or 0) + 1

    version = PolicyVersion(
        policy_id=policy.id,
        version_number=next_version,
        content=content,
        content_hash=_canonical_hash(content),
        is_active=False,
        notes=notes,
        created_by_token_id=created_by_token_id,
    )
    db.add(version)
    db.add(AdminAuditLog(
        organization_id=policy.organization_id,
        actor_token_id=created_by_token_id,
        action="policy.version.create",
        detail={"policy_id": str(policy.id), "version_number": next_version},
    ))
    db.flush()
    return version


def activate_version(
    db: Session, policy: Policy, version: PolicyVersion,
    actor_token_id: uuid.UUID | None = None,
):
    """Activate a policy version, creating rollout records for all active targets.

    Idempotent: re-activating the same version is a no-op per repo.
    """
    # Deactivate current active version (if any)
    current_active = db.execute(
        select(PolicyVersion).where(
            PolicyVersion.policy_id == policy.id,
            PolicyVersion.is_active == True,
        )
    ).scalar_one_or_none()

    if current_active and current_active.id != version.id:
        current_active.is_active = False

    version.is_active = True
    policy.status = "active"

    # Get all active targets
    targets = db.execute(
        select(PolicyTarget).where(
            PolicyTarget.policy_id == policy.id,
            PolicyTarget.active == True,
        )
    ).scalars().all()

    for target in targets:
        _create_rollout_for_target(db, policy, version, target.repository_id, source="activation")

    db.add(AdminAuditLog(
        organization_id=policy.organization_id,
        actor_token_id=actor_token_id,
        action="policy.activate",
        detail={
            "policy_id": str(policy.id),
            "version_id": str(version.id),
            "version_number": version.version_number,
            "targets_count": len(targets),
        },
    ))

    # Enqueue drift re-evaluation for affected repos using their latest observed commit
    _enqueue_drift_refresh_for_repos(db, policy.organization_id, [t.repository_id for t in targets])

    db.commit()


def _create_rollout_for_target(
    db: Session, policy: Policy, version: PolicyVersion,
    repository_id: uuid.UUID, source: str,
):
    """Create a pending rollout for a target, handling idempotency and supersession."""
    # Check if a non-terminal rollout already exists for this version + repo
    existing = db.execute(
        select(PolicyRollout).where(
            PolicyRollout.policy_version_id == version.id,
            PolicyRollout.repository_id == repository_id,
            PolicyRollout.status.in_(NON_TERMINAL_STATUSES),
        )
    ).scalar_one_or_none()

    if existing is not None:
        # Idempotent: already pending or applied for this version
        return

    # Supersede existing pending rollouts for same policy + repo
    pending_rollouts = db.execute(
        select(PolicyRollout).where(
            PolicyRollout.policy_id == policy.id,
            PolicyRollout.repository_id == repository_id,
            PolicyRollout.status == "pending",
        )
    ).scalars().all()
    for r in pending_rollouts:
        r.status = "superseded"

    # Mark existing applied rollouts as outdated
    applied_rollouts = db.execute(
        select(PolicyRollout).where(
            PolicyRollout.policy_id == policy.id,
            PolicyRollout.repository_id == repository_id,
            PolicyRollout.status == "applied",
        )
    ).scalars().all()
    for r in applied_rollouts:
        r.status = "outdated"

    # Create new pending rollout
    db.add(PolicyRollout(
        organization_id=policy.organization_id,
        policy_id=policy.id,
        policy_version_id=version.id,
        repository_id=repository_id,
        status="pending",
        source=source,
    ))
    db.flush()


def add_targets(
    db: Session, policy: Policy, repo_ids: list[uuid.UUID],
    actor_token_id: uuid.UUID | None = None,
) -> list[uuid.UUID]:
    """Add or reactivate targets for a policy. Returns list of newly (re)activated repo IDs.

    Validates that all repositories belong to the same organization as the policy.
    """
    activated = []

    # Validate all repos belong to this org
    for repo_id in repo_ids:
        repo = db.execute(
            select(Repository).where(
                Repository.id == repo_id,
                Repository.organization_id == policy.organization_id,
            )
        ).scalar_one_or_none()
        if repo is None:
            raise ValueError(f"Repository {repo_id} not found in this organization")

    # Get active version if any
    active_version = db.execute(
        select(PolicyVersion).where(
            PolicyVersion.policy_id == policy.id,
            PolicyVersion.is_active == True,
        )
    ).scalar_one_or_none()

    for repo_id in repo_ids:
        existing = db.execute(
            select(PolicyTarget).where(
                PolicyTarget.policy_id == policy.id,
                PolicyTarget.repository_id == repo_id,
            )
        ).scalar_one_or_none()

        if existing is not None:
            if existing.active:
                continue  # Already active, skip
            existing.active = True
        else:
            db.add(PolicyTarget(
                policy_id=policy.id,
                repository_id=repo_id,
                active=True,
            ))

        activated.append(repo_id)

        # If policy has active version, create pending rollout for new target
        if active_version:
            _create_rollout_for_target(db, policy, active_version, repo_id, source="retarget")

    if activated:
        db.add(AdminAuditLog(
            organization_id=policy.organization_id,
            actor_token_id=actor_token_id,
            action="policy.target.add",
            detail={"policy_id": str(policy.id), "repo_ids": [str(r) for r in activated]},
        ))

        # Enqueue drift re-evaluation for newly targeted repos
        if active_version:
            _enqueue_drift_refresh_for_repos(db, policy.organization_id, activated)

    db.commit()
    return activated


def remove_target(
    db: Session, policy: Policy, repo_id: uuid.UUID,
    actor_token_id: uuid.UUID | None = None,
):
    """Remove a target. Deactivates target row, supersedes pending rollouts."""
    target = db.execute(
        select(PolicyTarget).where(
            PolicyTarget.policy_id == policy.id,
            PolicyTarget.repository_id == repo_id,
        )
    ).scalar_one_or_none()

    if target is None or not target.active:
        return

    target.active = False

    # Supersede any pending rollouts for this repo
    pending = db.execute(
        select(PolicyRollout).where(
            PolicyRollout.policy_id == policy.id,
            PolicyRollout.repository_id == repo_id,
            PolicyRollout.status == "pending",
        )
    ).scalars().all()
    for r in pending:
        r.status = "superseded"

    db.add(AdminAuditLog(
        organization_id=policy.organization_id,
        actor_token_id=actor_token_id,
        action="policy.target.remove",
        detail={"policy_id": str(policy.id), "repo_id": str(repo_id)},
    ))
    db.commit()


def get_rollout_summary(db: Session, policy: Policy) -> list[dict]:
    """Get rollout state for all targets of a policy."""
    rollouts = db.execute(
        select(PolicyRollout, Repository).join(
            Repository, PolicyRollout.repository_id == Repository.id
        ).where(
            PolicyRollout.policy_id == policy.id,
        ).order_by(PolicyRollout.created_at.desc())
    ).all()

    return [
        {
            "id": str(r.PolicyRollout.id),
            "repository_id": str(r.PolicyRollout.repository_id),
            "repository": r.Repository.canonical_identifier,
            "policy_version_id": str(r.PolicyRollout.policy_version_id),
            "status": r.PolicyRollout.status,
            "source": r.PolicyRollout.source,
            "applied_at": r.PolicyRollout.applied_at.isoformat() if r.PolicyRollout.applied_at else None,
            "created_at": r.PolicyRollout.created_at.isoformat(),
        }
        for r in rollouts
    ]


def get_repo_policies(db: Session, repo_id: uuid.UUID, org_id: uuid.UUID) -> list[dict]:
    """Get all policies targeting a repo with current rollout status."""
    targets = db.execute(
        select(PolicyTarget, Policy).join(
            Policy, PolicyTarget.policy_id == Policy.id
        ).where(
            PolicyTarget.repository_id == repo_id,
            PolicyTarget.active == True,
            Policy.organization_id == org_id,
        )
    ).all()

    result = []
    for row in targets:
        target, policy = row.PolicyTarget, row.Policy

        # Get current (non-terminal) rollout for this policy + repo
        current_rollout = db.execute(
            select(PolicyRollout).where(
                PolicyRollout.policy_id == policy.id,
                PolicyRollout.repository_id == repo_id,
                PolicyRollout.status.in_(NON_TERMINAL_STATUSES),
            )
        ).scalar_one_or_none()

        result.append({
            "policy_id": str(policy.id),
            "policy_name": policy.name,
            "policy_slug": policy.slug,
            "policy_status": policy.status,
            "rollout_status": current_rollout.status if current_rollout else None,
            "rollout_version_id": str(current_rollout.policy_version_id) if current_rollout else None,
        })

    return result
