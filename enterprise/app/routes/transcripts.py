"""Transcript read endpoints — list, detail, blob stream, per-commit links.

Complements ``routes/ingest.py`` which owns the write side. Design
reference: 2026-08-08 transcripts-first MVP plan §7.
"""

from __future__ import annotations

from typing import Iterator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
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
from app.config import get_settings
from app.db import get_db
from app.models.api_token import ApiToken
from app.models.commit import Commit
from app.models.commit_transcript_link import CommitTranscriptLink
from app.models.transcript_session import TranscriptSession
from app.services.blob_store import BlobNotFound
from app.services.blob_store_filesystem import FilesystemBlobStore

router = APIRouter(tags=["transcripts"])


# --- Chunk size for streaming blob response ---
# 64KB is a common streaming default; big enough to avoid syscall
# overhead per chunk, small enough that memory stays bounded for
# multi-MB transcripts.
_BLOB_STREAM_CHUNK = 64 * 1024


def _serialize_session(ts: TranscriptSession, linked_commit_count: int | None = None) -> dict:
    row = {
        "id": str(ts.id),
        "machine_id": ts.machine_id,
        "vendor": ts.vendor,
        "vendor_session_id": ts.vendor_session_id,
        "model": ts.model,
        "workspace_hint": ts.workspace_hint,
        "transcript_source_path": ts.transcript_source_path,
        "blob_key": ts.blob_key,
        "blob_size_bytes": ts.blob_size_bytes,
        "blob_sha256": ts.blob_sha256,
        "started_at": ts.started_at.isoformat() if ts.started_at else None,
        "ended_at": ts.ended_at.isoformat() if ts.ended_at else None,
        "last_seen_at": ts.last_seen_at.isoformat() if ts.last_seen_at else None,
        "ingested_at": ts.ingested_at.isoformat() if ts.ingested_at else None,
        "retention_class": ts.retention_class,
    }
    if linked_commit_count is not None:
        row["linked_commit_count"] = linked_commit_count
    return row


def _serialize_link(link: CommitTranscriptLink, commit: Commit) -> dict:
    return {
        "id": str(link.id),
        "commit_id": str(link.commit_id),
        "commit_sha": commit.commit_sha,
        "repo_identifier": commit.repo_identifier,
        "linkage_basis": link.linkage_basis,
        "linkage_confidence": link.linkage_confidence,
        "linkage_metadata": link.linkage_metadata,
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }


@router.get("/transcripts")
def list_transcripts(
    machine_id: str | None = Query(None),
    vendor: str | None = Query(None),
    since: str | None = Query(None, description="ISO 8601 lower bound on started_at"),
    until: str | None = Query(None, description="ISO 8601 upper bound on started_at"),
    unlinked: bool = Query(
        False,
        description=(
            "If true, return only transcript sessions with zero linked commits "
            "(the investigation queue for whoever runs audit). Server-side filter "
            "via HAVING count(...) = 0. Complements the `unlinked_recent_transcripts` "
            "Postgres view (Migration 010) which does the same query at the DB "
            "layer for direct-SQL callers."
        ),
    ),
    limit: int = Query(DEFAULT_LIMIT_LIST, ge=1, le=MAX_LIMIT_DEFAULT),
    offset: int = Query(0, ge=0),
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Paginated list of transcript sessions with linked-commit counts."""
    since_dt = parse_iso_datetime(since, "since")
    until_dt = parse_iso_datetime(until, "until")

    # Left-join to CommitTranscriptLink for per-session link count.
    stmt = (
        select(
            TranscriptSession,
            func.count(CommitTranscriptLink.id).label("link_count"),
        )
        .outerjoin(
            CommitTranscriptLink,
            CommitTranscriptLink.transcript_session_id == TranscriptSession.id,
        )
        .where(TranscriptSession.organization_id == token.organization_id)
        .group_by(TranscriptSession.id)
        .order_by(TranscriptSession.ingested_at.desc())
    )
    if machine_id:
        stmt = stmt.where(TranscriptSession.machine_id == machine_id)
    if vendor:
        stmt = stmt.where(TranscriptSession.vendor == vendor)
    if since_dt:
        stmt = stmt.where(TranscriptSession.started_at >= since_dt)
    if until_dt:
        stmt = stmt.where(TranscriptSession.started_at <= until_dt)
    if unlinked:
        # HAVING on the aggregate — this is why the outerjoin+group_by exist
        # above. Rows with zero matching CommitTranscriptLink survive.
        stmt = stmt.having(func.count(CommitTranscriptLink.id) == 0)

    # Grab one extra to compute has_more without a second query.
    rows = db.execute(stmt.offset(offset).limit(limit + 1)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    return {
        "items": [_serialize_session(ts, link_count) for ts, link_count in rows],
        "pagination": {
            "limit": limit,
            "offset": offset,
            "has_more": has_more,
        },
    }


@router.get("/transcripts/{transcript_id}")
def get_transcript(
    transcript_id: str,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Single transcript session with all its commit links inline."""
    tid = parse_uuid(transcript_id, "transcript_id")
    ts = db.execute(
        select(TranscriptSession).where(
            TranscriptSession.id == tid,
            TranscriptSession.organization_id == token.organization_id,
        )
    ).scalar_one_or_none()
    if ts is None:
        raise ApiError(404, "not_found", "Transcript session not found")

    link_rows = db.execute(
        select(CommitTranscriptLink, Commit)
        .join(Commit, CommitTranscriptLink.commit_id == Commit.id)
        .where(CommitTranscriptLink.transcript_session_id == tid)
        .order_by(CommitTranscriptLink.created_at.desc())
    ).all()

    payload = _serialize_session(ts, linked_commit_count=len(link_rows))
    payload["links"] = [_serialize_link(link, commit) for link, commit in link_rows]
    return payload


@router.get("/transcripts/{transcript_id}/blob")
def get_transcript_blob(
    transcript_id: str,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Stream the raw transcript body (may be many MB)."""
    tid = parse_uuid(transcript_id, "transcript_id")
    ts = db.execute(
        select(TranscriptSession).where(
            TranscriptSession.id == tid,
            TranscriptSession.organization_id == token.organization_id,
        )
    ).scalar_one_or_none()
    if ts is None:
        raise ApiError(404, "not_found", "Transcript session not found")

    settings = get_settings()
    store = FilesystemBlobStore(settings.blob_store_root)

    try:
        content = store.get(ts.blob_key)
    except BlobNotFound:
        raise ApiError(410, "blob_missing", f"Blob for {ts.id} is no longer available")

    # Stream in fixed-size chunks so the response object doesn't
    # buffer the whole transcript in memory even though the reference
    # BlobStore returns bytes.
    def _chunks() -> Iterator[bytes]:
        for i in range(0, len(content), _BLOB_STREAM_CHUNK):
            yield content[i : i + _BLOB_STREAM_CHUNK]

    headers = {
        "Content-Length": str(len(content)),
        "X-Blob-Sha256": ts.blob_sha256,
    }
    return StreamingResponse(
        _chunks(),
        media_type="application/x-ndjson",
        headers=headers,
    )


@router.get("/commits/{commit_sha}/transcripts")
def get_commit_transcripts(
    commit_sha: str,
    repo_canonical_id: str | None = Query(
        None,
        description=(
            "Optional repo scope. If omitted, all commits with this SHA "
            "in the caller's org are considered."
        ),
    ),
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """List all transcripts linked to the commit(s) matching the SHA."""
    if not commit_sha or len(commit_sha) < 7 or len(commit_sha) > 40:
        raise ApiError(400, "invalid_parameter", "commit_sha must be 7-40 hex chars")
    # Hex-only defense: SQLAlchemy parameterizes the LIKE pattern via
    # bind variable so injection isn't possible, but a `%` or `_` in
    # the input would silently widen the match to unintended commits.
    if not all(c in "0123456789abcdefABCDEF" for c in commit_sha):
        raise ApiError(400, "invalid_parameter", "commit_sha must be hex")

    commit_stmt = select(Commit).where(
        Commit.organization_id == token.organization_id,
        Commit.commit_sha.like(f"{commit_sha}%"),
    )
    if repo_canonical_id:
        commit_stmt = commit_stmt.where(Commit.repo_identifier == repo_canonical_id)
    commits = db.execute(commit_stmt).scalars().all()
    if not commits:
        raise ApiError(404, "not_found", f"No commits match sha prefix {commit_sha}")

    commit_ids = [c.id for c in commits]
    link_rows = db.execute(
        select(CommitTranscriptLink, TranscriptSession, Commit)
        .join(TranscriptSession, CommitTranscriptLink.transcript_session_id == TranscriptSession.id)
        .join(Commit, CommitTranscriptLink.commit_id == Commit.id)
        .where(CommitTranscriptLink.commit_id.in_(commit_ids))
        .order_by(CommitTranscriptLink.created_at.desc())
    ).all()

    return {
        "commits": [
            {
                "commit_id": str(c.id),
                "commit_sha": c.commit_sha,
                "repo_identifier": c.repo_identifier,
            }
            for c in commits
        ],
        "links": [
            {
                "commit_sha": commit.commit_sha,
                "transcript_session_id": str(ts.id),
                "vendor": ts.vendor,
                "vendor_session_id": ts.vendor_session_id,
                "model": ts.model,
                "linkage_basis": link.linkage_basis,
                "linkage_confidence": link.linkage_confidence,
                "linkage_metadata": link.linkage_metadata,
                "created_at": link.created_at.isoformat() if link.created_at else None,
            }
            for link, ts, commit in link_rows
        ],
    }
