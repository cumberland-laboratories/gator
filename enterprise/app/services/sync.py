"""Sync service — orchestration for webhook handling, reconciliation, and refresh.

All three sync triggers (webhook, scheduled reconciliation, manual refresh)
funnel through this service into register_commit_metadata jobs.

Deduplication is two-layer:
- Layer 1: check ingest_jobs before enqueueing (prevents queue amplification)
- Layer 2: register_commit_metadata handler is idempotent (no-op on existing commit)
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.commit import Commit
from app.models.git_provider import GitProvider
from app.models.ingest_job import IngestJob
from app.models.repository import Repository
from app.models.sync_run import ProviderSyncRun
from app.providers.base import CommitInfo, ProviderAdapter, RepoInfo
from app.providers.github import GitHubAdapter


def get_adapter_for_provider(provider: GitProvider) -> ProviderAdapter:
    """Instantiate the appropriate adapter for a provider record."""
    if provider.provider_type == "github":
        config = provider.config or {}
        from app.config import get_settings
        settings = get_settings()
        return GitHubAdapter(
            app_id=config.get("app_id", settings.github_app_id),
            private_key=settings.github_private_key,
            installation_id=config.get("installation_id", ""),
            webhook_secret=settings.github_webhook_secret,
        )
    raise ValueError(f"Unsupported provider type: {provider.provider_type}")


def _commit_already_pending(db: Session, org_id, repo_identifier: str, commit_sha: str) -> bool:
    """Layer 1 dedup: check if a pending/claimed job already exists for this commit."""
    from sqlalchemy.dialects.postgresql import JSONB
    existing = db.execute(
        select(IngestJob).where(
            IngestJob.organization_id == org_id,
            IngestJob.job_type == "register_commit_metadata",
            IngestJob.status.in_(["pending", "claimed"]),
            IngestJob.payload["commit_sha"].as_string() == commit_sha,
            IngestJob.payload["repo_identifier"].as_string() == repo_identifier,
        )
    ).scalar_one_or_none()
    return existing is not None


def _commit_already_exists(db: Session, org_id, repo_identifier: str, commit_sha: str) -> bool:
    """Check if commit is already in the commits table."""
    existing = db.execute(
        select(Commit).where(
            Commit.organization_id == org_id,
            Commit.repo_identifier == repo_identifier,
            Commit.commit_sha == commit_sha,
        )
    ).scalar_one_or_none()
    return existing is not None


def normalize_branch(webhook_ref: str | None) -> str | None:
    """Convert webhook ref to bare branch name.

    'refs/heads/feature-branch' → 'feature-branch'
    'refs/heads/main' → 'main'
    """
    if webhook_ref and webhook_ref.startswith("refs/heads/"):
        return webhook_ref.removeprefix("refs/heads/")
    if webhook_ref and webhook_ref.startswith("refs/tags/"):
        return webhook_ref.removeprefix("refs/tags/")
    return webhook_ref


def _enqueue_commit(db: Session, org_id, repo: Repository, commit: CommitInfo,
                    branch: str | None = None) -> bool:
    """Enqueue a register_commit_metadata job if not duplicate. Returns True if enqueued."""
    repo_identifier = repo.canonical_identifier

    # Layer 1: skip if already in commits table
    if _commit_already_exists(db, org_id, repo_identifier, commit.sha):
        return False

    # Layer 1b: skip if already pending in job queue
    if _commit_already_pending(db, org_id, repo_identifier, commit.sha):
        return False

    payload = {
        "commit_sha": commit.sha,
        "repo_identifier": repo_identifier,
        "author_identity": commit.author,
        "commit_message": commit.message,
        "committed_at": commit.timestamp.isoformat() if commit.timestamp else None,
        "model_identities": commit.model_identities,
        "branch": branch,
    }

    job = IngestJob(
        organization_id=org_id,
        job_type="register_commit_metadata",
        payload=payload,
        status="pending",
    )
    db.add(job)
    db.flush()  # Make visible to subsequent dedup checks in the same transaction
    return True


def handle_webhook_event(db: Session, provider: GitProvider, event_type: str, payload: dict):
    """Handle an incoming webhook event from a provider."""
    if event_type == "push":
        _handle_push_event(db, provider, payload)
    elif event_type in ("installation_repositories", "installation"):
        sync_repo_inventory(db, provider)


def _handle_push_event(db: Session, provider: GitProvider, payload: dict):
    """Process a push event: parse commits, dedupe, enqueue."""
    adapter = get_adapter_for_provider(provider)
    commits = adapter.parse_push_event(payload)

    # Find the repository
    repo_data = payload.get("repository", {})
    provider_repo_id = str(repo_data.get("id", ""))
    repo = db.execute(
        select(Repository).where(
            Repository.provider_id == provider.id,
            Repository.provider_repo_id == provider_repo_id,
        )
    ).scalar_one_or_none()

    if repo is None:
        # Unknown repo — may need inventory sync
        return

    now = datetime.now(timezone.utc)
    run = ProviderSyncRun(
        organization_id=provider.organization_id,
        provider_id=provider.id,
        run_type="webhook",
        scope=repo.canonical_identifier,
        status="started",
        started_at=now,
    )
    db.add(run)
    db.flush()

    # Extract branch from push event ref
    branch = normalize_branch(payload.get("ref"))

    jobs_created = 0
    for commit in commits:
        if _enqueue_commit(db, provider.organization_id, repo, commit, branch=branch):
            jobs_created += 1

    repo.last_webhook_at = now
    if commits:
        repo.last_commit_sha = commits[0].sha

    run.status = "completed"
    run.completed_at = datetime.now(timezone.utc)
    run.commits_found = len(commits)
    run.jobs_created = jobs_created
    db.commit()


def sync_repo_inventory(db: Session, provider: GitProvider, record_run: bool = True):
    """Sync repository inventory from the provider.

    Args:
        record_run: If False, suppresses ProviderSyncRun creation (used when
                    called from reconcile_provider which manages its own run record).
    """
    adapter = get_adapter_for_provider(provider)
    remote_repos = adapter.list_repositories()

    run = None
    if record_run:
        now = datetime.now(timezone.utc)
        run = ProviderSyncRun(
            organization_id=provider.organization_id,
            provider_id=provider.id,
            run_type="reconciliation",
            scope="inventory",
            status="started",
            started_at=now,
        )
        db.add(run)
        db.flush()

    remote_ids = set()
    for repo_info in remote_repos:
        remote_ids.add(repo_info.provider_repo_id)
        existing = db.execute(
            select(Repository).where(
                Repository.provider_id == provider.id,
                Repository.provider_repo_id == repo_info.provider_repo_id,
            )
        ).scalar_one_or_none()

        if existing:
            existing.name = repo_info.name
            existing.default_branch = repo_info.default_branch
            existing.canonical_identifier = f"github.com/{repo_info.full_name}"
            existing.active = True
        else:
            db.add(Repository(
                organization_id=provider.organization_id,
                provider_id=provider.id,
                provider_repo_id=repo_info.provider_repo_id,
                canonical_identifier=f"github.com/{repo_info.full_name}",
                name=repo_info.name,
                default_branch=repo_info.default_branch,
                active=True,
            ))

    # Deactivate repos no longer in the installation
    all_repos = db.execute(
        select(Repository).where(
            Repository.provider_id == provider.id,
            Repository.active == True,
        )
    ).scalars().all()
    for repo in all_repos:
        if repo.provider_repo_id not in remote_ids:
            repo.active = False

    if run:
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
    db.commit()


def sync_commits_for_repo(db: Session, repo: Repository, since: datetime | None = None) -> tuple[int, int]:
    """Fetch commits from provider and enqueue new ones. Returns (found, enqueued)."""
    provider = db.execute(
        select(GitProvider).where(GitProvider.id == repo.provider_id)
    ).scalar_one()
    adapter = get_adapter_for_provider(provider)

    # Extract owner/repo from canonical_identifier (github.com/owner/repo)
    parts = repo.canonical_identifier.split("/", 1)
    repo_full_name = parts[1] if len(parts) > 1 else repo.name

    commits = adapter.list_commits_since(repo_full_name, since)
    jobs_created = 0
    for commit in commits:
        if _enqueue_commit(db, repo.organization_id, repo, commit):
            jobs_created += 1

    now = datetime.now(timezone.utc)
    repo.last_reconciled_at = now
    if commits:
        repo.last_commit_sha = commits[0].sha

    db.commit()
    return len(commits), jobs_created


def reconcile_provider(db: Session, provider: GitProvider):
    """Full reconciliation: inventory sync + commit gap check for all active repos."""
    now = datetime.now(timezone.utc)
    run = ProviderSyncRun(
        organization_id=provider.organization_id,
        provider_id=provider.id,
        run_type="reconciliation",
        scope="all",
        status="started",
        started_at=now,
    )
    db.add(run)
    db.flush()

    try:
        sync_repo_inventory(db, provider, record_run=False)

        total_found = 0
        total_jobs = 0
        active_repos = db.execute(
            select(Repository).where(
                Repository.provider_id == provider.id,
                Repository.active == True,
            )
        ).scalars().all()

        for repo in active_repos:
            found, jobs = sync_commits_for_repo(db, repo, since=repo.last_reconciled_at)
            total_found += found
            total_jobs += jobs

        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.commits_found = total_found
        run.jobs_created = total_jobs
        db.commit()
    except Exception as e:
        db.rollback()
        run.status = "failed"
        run.completed_at = datetime.now(timezone.utc)
        run.error = {"message": str(e)}
        db.commit()
        raise


def refresh_repo(db: Session, repo: Repository):
    """Manual single-repo refresh. Full commit re-check."""
    provider = db.execute(
        select(GitProvider).where(GitProvider.id == repo.provider_id)
    ).scalar_one()

    now = datetime.now(timezone.utc)
    run = ProviderSyncRun(
        organization_id=provider.organization_id,
        provider_id=provider.id,
        run_type="manual",
        scope=repo.canonical_identifier,
        status="started",
        started_at=now,
    )
    db.add(run)
    db.flush()

    try:
        found, jobs = sync_commits_for_repo(db, repo, since=None)
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.commits_found = found
        run.jobs_created = jobs
        db.commit()
    except Exception as e:
        db.rollback()
        run.status = "failed"
        run.completed_at = datetime.now(timezone.utc)
        run.error = {"message": str(e)}
        db.commit()
        raise
