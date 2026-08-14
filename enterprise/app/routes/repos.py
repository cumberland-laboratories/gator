"""Repository and provider management routes.

Also owns repo-scoped audit-question surfaces (2026-08-14 audit-question
artifact §3):

- ``GET /api/v1/repos/{repo_canonical_id}/commits`` — Q2 ("Which recent
  commits in repo <repo> have transcript coverage?") — ratified as
  CLI verb ``commits list --repo <id>`` via R4 = (a) at Phase 1 exit.
- ``GET /api/v1/repos/{repo_canonical_id}/transcripts`` — Q5 ("Which
  model/vendor sessions touched repo <repo> over time?") — ratified as
  CLI verb ``repos transcripts <id>`` via R5 = (b) at Phase 1 exit.

Both use canonical repo identifier (`local/<name>` on this machine) as
the path segment — same shape ingest side uses for `Commit.repo_identifier`.
Q5 for Gemini has an answer-completeness caveat pre-Migration-011 per Q5
Notes column in the Phase 1 artifact; Phase 2's Q5 surface still ships
and returns honest partial data for Gemini until Phase 4 lands.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api_contract import (
    ApiError,
    DEFAULT_LIMIT_LIST,
    MAX_LIMIT_DEFAULT,
    parse_iso_datetime,
    parse_uuid,
)
from app.auth import verify_token
from app.db import get_db
from app.models.api_token import ApiToken
from app.models.commit import Commit
from app.models.commit_transcript_link import CommitTranscriptLink
from app.models.git_provider import GitProvider
from app.models.repository import Repository
from app.models.transcript_session import TranscriptSession
from app.services.sync import reconcile_provider, refresh_repo
from app.services.policy import get_repo_policies

router = APIRouter(tags=["repos"])


@router.get("/repos")
def list_repos(
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """List all tracked repositories."""
    repos = db.execute(
        select(Repository).where(
            Repository.organization_id == token.organization_id
        ).order_by(Repository.canonical_identifier)
    ).scalars().all()

    return [
        {
            "id": str(r.id),
            "canonical_identifier": r.canonical_identifier,
            "name": r.name,
            "default_branch": r.default_branch,
            "active": r.active,
            "last_webhook_at": r.last_webhook_at.isoformat() if r.last_webhook_at else None,
            "last_reconciled_at": r.last_reconciled_at.isoformat() if r.last_reconciled_at else None,
            "last_commit_sha": r.last_commit_sha,
        }
        for r in repos
    ]


@router.post("/repos/{repo_id}/refresh")
def trigger_refresh(
    repo_id: str,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Trigger a manual refresh for a single repository."""
    rid = parse_uuid(repo_id, "repo_id")
    repo = db.execute(
        select(Repository).where(
            Repository.id == rid,
            Repository.organization_id == token.organization_id,
        )
    ).scalar_one_or_none()

    if repo is None:
        raise ApiError(404, "not_found", "Repository not found")

    refresh_repo(db, repo)
    return {"status": "refresh_started", "repo": repo.canonical_identifier}


@router.post("/providers/{provider_id}/reconcile")
def trigger_reconcile(
    provider_id: str,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Trigger full reconciliation for a provider."""
    pid = parse_uuid(provider_id, "provider_id")
    provider = db.execute(
        select(GitProvider).where(
            GitProvider.id == pid,
            GitProvider.organization_id == token.organization_id,
        )
    ).scalar_one_or_none()

    if provider is None:
        raise ApiError(404, "not_found", "Provider not found")

    reconcile_provider(db, provider)
    return {"status": "reconciliation_complete", "provider_id": str(provider.id)}


@router.get("/repos/{repo_id}/policies")
def repo_policies(
    repo_id: str,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """List all policies targeting a specific repository."""
    rid = parse_uuid(repo_id, "repo_id")
    repo = db.execute(
        select(Repository).where(
            Repository.id == rid,
            Repository.organization_id == token.organization_id,
        )
    ).scalar_one_or_none()

    if repo is None:
        raise ApiError(404, "not_found", "Repository not found")

    return get_repo_policies(db, repo.id, token.organization_id)


# ----------------------------------------------------------------------
# Audit-question surfaces (Phase 2 Commit J, 2026-08-14)
# ----------------------------------------------------------------------


# Ranked linkage-basis mapping — kept in sync with Migration 010's
# `commits_with_transcript_coverage` view (same numeric ordering + same
# human-readable prefix strings). Extracted as a module constant so future
# additions to the linkage vocabulary land in one place.
_LINKAGE_BASIS_RANK = {
    "exact_sha_in_transcript":  (1, "1_exact_sha_in_transcript"),
    "session_id_in_snippet":    (2, "2_session_id_in_snippet"),
    "strong_machine_repo_time": (3, "3_strong_machine_repo_time"),
    "orchestrator_declared":    (4, "4_orchestrator_declared"),
}


def _best_linkage_basis(link_bases: list[str | None]) -> tuple[int, str | None]:
    """Return (rank, human_basis) for the strongest basis in a list.

    Unranked bases sort to rank 99 with a None human label. Empty input
    (i.e. commit with zero links) returns (99, None) so the caller can
    surface it as "unlinked".
    """
    best_rank = 99
    best_basis = None
    for basis in link_bases:
        if not basis:
            continue
        rank, human = _LINKAGE_BASIS_RANK.get(basis, (99, None))
        if rank < best_rank:
            best_rank = rank
            best_basis = human
    return best_rank, best_basis


@router.get("/repos/{repo_canonical_id:path}/commits")
def list_repo_commits(
    repo_canonical_id: str,
    limit: int = Query(DEFAULT_LIMIT_LIST, ge=1, le=MAX_LIMIT_DEFAULT),
    offset: int = Query(0, ge=0),
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Q2 — recent commits in the repo with transcript-coverage summary.

    Returns per-commit rows shaped like Migration 010's
    ``commits_with_transcript_coverage`` view: commit metadata + linked
    transcript count + best (strongest) linkage basis observed. Ordered
    by ``committed_at DESC`` (recent first) — matches the audit-question
    intent "which RECENT commits in repo <repo> have transcript coverage".

    Implemented as a route-level composition of the same join the view
    exposes (rather than a direct ``SELECT ... FROM commits_with_transcript_coverage``)
    so the SQLite in-memory test harness works without recreating the view
    at ``Base.metadata.create_all`` time.
    """
    stmt = (
        select(Commit, CommitTranscriptLink.linkage_basis)
        .outerjoin(
            CommitTranscriptLink,
            CommitTranscriptLink.commit_id == Commit.id,
        )
        .where(
            Commit.organization_id == token.organization_id,
            Commit.repo_identifier == repo_canonical_id,
        )
        .order_by(Commit.committed_at.desc().nulls_last(), Commit.commit_sha)
    )

    rows = db.execute(stmt).all()

    # Group by commit_id — one row per commit, plus a list of the linkage
    # bases from each link. Python-side grouping keeps the SQL simple and
    # portable across Postgres / SQLite; the row count is bounded by
    # `limit` after grouping (see below).
    grouped: dict[str, tuple[Commit, list[str | None]]] = {}
    for commit, basis in rows:
        key = str(commit.id)
        if key not in grouped:
            grouped[key] = (commit, [])
        if basis is not None:
            grouped[key][1].append(basis)

    ordered = list(grouped.values())
    # Preserve the SQL-order (committed_at desc) — dict insertion order
    # holds, but re-sort defensively in case SQLAlchemy reorders.
    ordered.sort(
        key=lambda pair: (
            pair[0].committed_at is None,
            -(pair[0].committed_at.timestamp() if pair[0].committed_at else 0),
            pair[0].commit_sha,
        )
    )

    total = len(ordered)
    page = ordered[offset : offset + limit + 1]
    has_more = len(page) > limit
    page = page[:limit]

    items = []
    for commit, bases in page:
        best_rank, best_basis = _best_linkage_basis(bases)
        items.append({
            "commit_sha": commit.commit_sha,
            "repo_identifier": commit.repo_identifier,
            "author_identity": commit.author_identity,
            "committed_at": commit.committed_at.isoformat() if commit.committed_at else None,
            "machine_id": commit.machine_id,
            "snippet_agent": commit.snippet_agent,
            "linked_transcript_count": len(bases),
            "best_linkage_rank": best_rank,
            "best_linkage_basis_ranked": best_basis,
        })

    return {
        "items": items,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "has_more": has_more,
            "total_matched": total,
        },
    }


@router.get("/repos/{repo_canonical_id:path}/transcripts")
def list_repo_transcripts(
    repo_canonical_id: str,
    vendor: str | None = Query(None),
    since: str | None = Query(None, description="ISO 8601 lower bound on started_at"),
    limit: int = Query(DEFAULT_LIMIT_LIST, ge=1, le=MAX_LIMIT_DEFAULT),
    offset: int = Query(0, ge=0),
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Q5 — transcript sessions that touched this repo, ordered by recency.

    Three-way join: TranscriptSession ⨝ CommitTranscriptLink ⨝ Commit
    WHERE Commit.repo_identifier = repo_canonical_id AND org matches.
    Deduplicated per transcript session (one session may link to many
    commits in the same repo). Ordered by ``started_at DESC``.

    **Gemini answer-completeness caveat** (per Phase 1 artifact §3 Q5
    Notes): pre-Migration-011, two Gemini transcript files with the
    same raw ``vendor_session_id`` on the same machine collide at ingest
    — second-file uploads overwrite the first. This surface returns
    honest partial data for Gemini until Phase 4 lands (§10 item 6 =
    (b) Migration 011); no re-classification of Q5's status bucket.
    """
    since_dt = parse_iso_datetime(since, "since")

    stmt = (
        select(TranscriptSession)
        .distinct()
        .join(
            CommitTranscriptLink,
            CommitTranscriptLink.transcript_session_id == TranscriptSession.id,
        )
        .join(
            Commit,
            CommitTranscriptLink.commit_id == Commit.id,
        )
        .where(
            Commit.organization_id == token.organization_id,
            Commit.repo_identifier == repo_canonical_id,
            TranscriptSession.organization_id == token.organization_id,
        )
        .order_by(TranscriptSession.started_at.desc().nulls_last())
    )
    if vendor:
        stmt = stmt.where(TranscriptSession.vendor == vendor)
    if since_dt:
        stmt = stmt.where(TranscriptSession.started_at >= since_dt)

    rows = db.execute(stmt.offset(offset).limit(limit + 1)).scalars().all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    items = [
        {
            "id": str(ts.id),
            "vendor": ts.vendor,
            "vendor_session_id": ts.vendor_session_id,
            "model": ts.model,
            "machine_id": ts.machine_id,
            "workspace_hint": ts.workspace_hint,
            "started_at": ts.started_at.isoformat() if ts.started_at else None,
            "ended_at": ts.ended_at.isoformat() if ts.ended_at else None,
            "ingested_at": ts.ingested_at.isoformat() if ts.ingested_at else None,
            "blob_size_bytes": ts.blob_size_bytes,
        }
        for ts in rows
    ]

    return {
        "items": items,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "has_more": has_more,
        },
    }
