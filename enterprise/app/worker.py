"""Gator Enterprise worker process.

Standalone process that claims and processes ingest jobs.
Also runs periodic reconciliation on a timer.

Usage:
    python -m app.worker

Invariant: register_commit_metadata must remain idempotent —
duplicate jobs resolve as successful no-ops, not failures.
"""

import signal
import sys
import time
from datetime import datetime, timezone
from dateutil.parser import isoparse

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.logging import configure_logging, get_logger
from app.models.commit import Commit
from app.models.git_provider import GitProvider
from app.models.ingest_job import IngestJob

settings = get_settings()
configure_logging(settings.app_env)
logger = get_logger("gator.enterprise.worker")

running = True


def handle_shutdown(signum, frame):
    global running
    logger.info("worker.shutdown_signal", signal=signum)
    running = False


signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)


def claim_job(db) -> IngestJob | None:
    """Claim the next pending job using SELECT FOR UPDATE SKIP LOCKED."""
    result = db.execute(
        select(IngestJob)
        .where(IngestJob.status == "pending")
        .order_by(IngestJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = result.scalar_one_or_none()
    if job:
        job.status = "claimed"
        job.claimed_at = datetime.now(timezone.utc)
        db.commit()
    return job


def process_register_commit_metadata(db, job: IngestJob):
    """Process a register_commit_metadata job.

    Idempotent: if commit already exists, completes as a no-op.
    This is load-bearing for the two-layer dedup design.
    """
    payload = job.payload or {}
    commit_sha = payload.get("commit_sha")
    repo_identifier = payload.get("repo_identifier")

    if not commit_sha or not repo_identifier:
        raise ValueError("payload must include commit_sha and repo_identifier")

    # Check if commit already exists (idempotent — no-op on duplicate)
    existing = db.execute(
        select(Commit).where(
            Commit.organization_id == job.organization_id,
            Commit.repo_identifier == repo_identifier,
            Commit.commit_sha == commit_sha,
        )
    ).scalar_one_or_none()

    if existing is None:
        committed_at_raw = payload.get("committed_at")
        committed_at = None
        if committed_at_raw:
            committed_at = isoparse(committed_at_raw) if isinstance(committed_at_raw, str) else committed_at_raw

        commit = Commit(
            organization_id=job.organization_id,
            repo_identifier=repo_identifier,
            commit_sha=commit_sha,
            author_identity=payload.get("author_identity"),
            model_identities=payload.get("model_identities"),
            commit_message=payload.get("commit_message"),
            committed_at=committed_at,
            ingested_at=datetime.now(timezone.utc),
        )
        db.add(commit)
        db.flush()
        logger.info("worker.commit_registered", commit_sha=commit_sha[:8], repo=repo_identifier)

        # Auto-enqueue observation extraction (carry branch through chain)
        db.add(IngestJob(
            organization_id=job.organization_id,
            job_type="extract_commit_observation",
            payload={
                "commit_id": str(commit.id),
                "repo_identifier": repo_identifier,
                "branch": payload.get("branch"),
            },
            status="pending",
        ))
        db.flush()
    else:
        logger.debug("worker.commit_exists", commit_sha=commit_sha[:8], repo=repo_identifier)


def process_sync_repo_inventory(db, job: IngestJob):
    """Process a sync_repo_inventory job."""
    from app.services.sync import sync_repo_inventory

    provider = db.execute(
        select(GitProvider).where(GitProvider.id == job.payload.get("provider_id"))
    ).scalar_one_or_none()

    if provider is None:
        raise ValueError(f"Provider not found: {job.payload.get('provider_id')}")

    sync_repo_inventory(db, provider)


def process_extract_commit_observation(db, job: IngestJob):
    """Extract governance observation for a commit, then auto-enqueue drift evaluation."""
    import uuid as uuid_mod
    from app.services.evidence import extract_observation

    payload = job.payload or {}
    commit_id = payload.get("commit_id")
    if not commit_id:
        raise ValueError("payload must include commit_id")

    commit = db.execute(
        select(Commit).where(Commit.id == uuid_mod.UUID(commit_id))
    ).scalar_one_or_none()
    if commit is None:
        raise ValueError(f"Commit not found: {commit_id}")

    from app.models.repository import Repository
    repo = db.execute(
        select(Repository).where(
            Repository.canonical_identifier == commit.repo_identifier,
            Repository.organization_id == commit.organization_id,
        )
    ).scalar_one_or_none()
    if repo is None:
        logger.warning("worker.no_repository", repo_identifier=commit.repo_identifier)
        return

    observation = extract_observation(db, commit, repo)

    branch = payload.get("branch")

    if observation and observation.observation_status == "observed":
        # Auto-enqueue drift evaluation
        db.add(IngestJob(
            organization_id=job.organization_id,
            job_type="evaluate_drift",
            payload={"commit_id": str(commit.id), "branch": branch},
            status="pending",
        ))

        # Auto-enqueue session block reconciliation (dedup by repo_id + branch)
        if repo and branch:
            existing_reconcile = db.execute(
                select(IngestJob.id).where(
                    IngestJob.job_type == "reconcile_session_blocks",
                    IngestJob.status.in_(["pending", "claimed"]),
                    IngestJob.payload["repo_id"].astext == str(repo.id),
                    IngestJob.payload["branch"].astext == branch,
                ).limit(1)
            ).scalar_one_or_none()

            if existing_reconcile is None:
                db.add(IngestJob(
                    organization_id=job.organization_id,
                    job_type="reconcile_session_blocks",
                    payload={"repo_id": str(repo.id), "branch": branch},
                    status="pending",
                ))

        db.flush()
        logger.info("worker.observation_extracted", commit_sha=commit.commit_sha[:8], drift_enqueued=True)


def process_evaluate_drift(db, job: IngestJob):
    """Evaluate drift for a commit against active policies."""
    import uuid as uuid_mod
    from app.services.drift import evaluate_commit_drift
    from app.models.commit_observation import CommitObservation

    payload = job.payload or {}
    commit_id = payload.get("commit_id")
    if not commit_id:
        raise ValueError("payload must include commit_id")

    commit = db.execute(
        select(Commit).where(Commit.id == uuid_mod.UUID(commit_id))
    ).scalar_one_or_none()
    if commit is None:
        raise ValueError(f"Commit not found: {commit_id}")

    observation = db.execute(
        select(CommitObservation).where(
            CommitObservation.commit_id == commit.id,
            CommitObservation.observation_status == "observed",
        )
    ).scalar_one_or_none()
    if observation is None:
        logger.warning("worker.no_observation", commit_sha=commit.commit_sha[:8])
        return

    evaluate_commit_drift(db, commit, observation)
    logger.info("worker.drift_evaluated", commit_sha=commit.commit_sha[:8])


def process_generate_report(db, job: IngestJob):
    """Generate a report snapshot."""
    import uuid as uuid_mod
    from app.models.repository import Repository
    from app.models.policy import Policy

    payload = job.payload or {}
    report_type = payload.get("report_type")

    if report_type == "repo":
        from app.services.reporting import generate_repo_report
        repo = db.execute(
            select(Repository).where(Repository.id == uuid_mod.UUID(payload["target_id"]))
        ).scalar_one()
        generate_repo_report(db, repo)
    elif report_type == "policy":
        from app.services.reporting import generate_policy_report
        policy = db.execute(
            select(Policy).where(Policy.id == uuid_mod.UUID(payload["target_id"]))
        ).scalar_one()
        generate_policy_report(db, policy)
    else:
        raise ValueError(f"Unknown report type: {report_type}")

    logger.info("worker.report_generated", report_type=report_type, target_id=payload.get("target_id"))


def process_reconcile_session_blocks(db, job: IngestJob):
    """Reconcile session blocks for a repo at a branch."""
    import uuid as uuid_mod
    from app.models.repository import Repository
    from app.services.session_blocks import reconcile_session_blocks

    payload = job.payload or {}
    repo_id = payload.get("repo_id")
    branch = payload.get("branch")

    if not repo_id:
        raise ValueError("payload must include repo_id")

    repo = db.execute(
        select(Repository).where(Repository.id == uuid_mod.UUID(repo_id))
    ).scalar_one_or_none()

    if repo is None:
        raise ValueError(f"Repository not found: {repo_id}")

    blocks = reconcile_session_blocks(db, repo, branch=branch)
    logger.info("worker.session_blocks_reconciled",
                repo=repo.canonical_identifier, branch=branch,
                blocks_indexed=len(blocks))


def process_job(db, job: IngestJob):
    """Route job to appropriate handler based on job_type."""
    handlers = {
        "register_commit_metadata": process_register_commit_metadata,
        "sync_repo_inventory": process_sync_repo_inventory,
        "extract_commit_observation": process_extract_commit_observation,
        "evaluate_drift": process_evaluate_drift,
        "generate_report": process_generate_report,
        "reconcile_session_blocks": process_reconcile_session_blocks,
    }

    handler = handlers.get(job.job_type)
    if handler is None:
        raise ValueError(f"Unknown job type: {job.job_type}")

    handler(db, job)


def run_reconciliation():
    """Run reconciliation for all active providers."""
    from app.services.sync import reconcile_provider

    db = SessionLocal()
    try:
        providers = db.execute(
            select(GitProvider).where(GitProvider.status == "active")
        ).scalars().all()

        if not providers:
            return

        logger.info("worker.reconciliation_start", provider_count=len(providers))
        for provider in providers:
            try:
                reconcile_provider(db, provider)
                logger.info("worker.reconciliation_complete", provider_id=str(provider.id))
            except Exception as e:
                logger.error("worker.reconciliation_failed", provider_id=str(provider.id), error=str(e), error_type=type(e).__name__)

        # Session block reconciliation — enqueue for all active repos
        from app.models.repository import Repository
        all_repos = db.execute(
            select(Repository).where(Repository.active == True)
        ).scalars().all()

        for repo in all_repos:
            branch = repo.default_branch
            existing = db.execute(
                select(IngestJob.id).where(
                    IngestJob.job_type == "reconcile_session_blocks",
                    IngestJob.status.in_(["pending", "claimed"]),
                    IngestJob.payload["repo_id"].astext == str(repo.id),
                    IngestJob.payload["branch"].astext == branch,
                ).limit(1)
            ).scalar_one_or_none()

            if existing is None:
                db.add(IngestJob(
                    organization_id=repo.organization_id,
                    job_type="reconcile_session_blocks",
                    payload={"repo_id": str(repo.id), "branch": branch},
                    status="pending",
                ))
        db.commit()
        logger.info("worker.session_block_reconciliation_enqueued", repo_count=len(all_repos))
    finally:
        db.close()


def run():
    """Main worker loop with periodic reconciliation."""
    logger.info("worker.start", poll_interval=settings.worker_poll_interval, reconciliation_interval=settings.reconciliation_interval)

    last_reconciliation: datetime | None = None  # None = never run, trigger on first cycle

    while running:
        # Check if reconciliation is due
        now = datetime.now(timezone.utc)
        if last_reconciliation is None or (now - last_reconciliation).total_seconds() >= settings.reconciliation_interval:
            run_reconciliation()
            last_reconciliation = datetime.now(timezone.utc)

        # Process jobs
        db = SessionLocal()
        try:
            job = claim_job(db)
            if job is None:
                db.close()
                time.sleep(settings.worker_poll_interval)
                continue

            start = time.monotonic()
            logger.info("worker.job_start", job_id=str(job.id), job_type=job.job_type, org_id=str(job.organization_id))
            try:
                process_job(db, job)
                job.status = "completed"
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
                duration_ms = round((time.monotonic() - start) * 1000, 1)
                logger.info("worker.job_completed", job_id=str(job.id), job_type=job.job_type, org_id=str(job.organization_id), duration_ms=duration_ms)
            except Exception as e:
                db.rollback()
                duration_ms = round((time.monotonic() - start) * 1000, 1)
                try:
                    job.status = "failed"
                    job.completed_at = datetime.now(timezone.utc)
                    job.error = {"message": str(e), "type": type(e).__name__}
                    db.commit()
                except Exception as inner:
                    db.rollback()
                    logger.error("worker.job_failure_record_failed", job_id=str(job.id), error=str(inner))
                logger.error("worker.job_failed", job_id=str(job.id), job_type=job.job_type, org_id=str(job.organization_id), duration_ms=duration_ms, error=str(e), error_type=type(e).__name__)

        finally:
            db.close()

    logger.info("worker.shutdown_complete")


if __name__ == "__main__":
    run()
