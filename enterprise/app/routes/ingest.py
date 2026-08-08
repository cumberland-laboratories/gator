"""Local-repo ingestion routes — commits + transcripts.

These are the entry points the `gator-enterprise transcripts pull` CLI
posts to. Both are batch- and idempotency-shaped so re-running the pull
is safe.

Design references:
- 2026-08-08 transcripts-first MVP plan §7 (endpoint contracts)
- 2026-08-08 ADR D11 (local commit ingest closes the FK gap for
  transcript ↔ commit linkage in the self-hosted MVP; unique key is
  ``(organization_id, repo_identifier, commit_sha)``)

The linkage algorithm (§8 of the plan) runs at the end of transcript
ingest, after the session row is written. MVP linkage bases implemented
here: ``exact_sha_in_transcript``, ``session_id_in_snippet``. The
``strong_machine_repo_time`` basis and ``orchestrator_declared`` link
endpoint land in Phase 3.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_contract import ApiError
from app.auth import verify_token
from app.config import get_settings
from app.db import get_db
from app.models.api_token import ApiToken
from app.models.commit import Commit
from app.models.commit_transcript_link import CommitTranscriptLink
from app.models.transcript_session import TranscriptSession
from app.services.blob_store import build_blob_key
from app.services.blob_store_filesystem import FilesystemBlobStore

router = APIRouter(tags=["ingest"])


# --- Request/response schemas ---


class CommitIngestItem(BaseModel):
    repo_canonical_id: str = Field(..., max_length=500)
    sha: str = Field(..., min_length=7, max_length=64)
    subject: str | None = None
    author: str | None = None
    committed_at: str | None = None  # ISO 8601
    branch: str | None = None
    gator_trailers: dict[str, Any] | None = None
    transcript_session_id: str | None = None  # from snippet, drives session_id_in_snippet linkage
    machine_id: str | None = None
    machine_label: str | None = None
    snippet_agent: str | None = None


class CommitIngestBody(BaseModel):
    machine_id: str | None = None  # optional per-batch default
    commits: list[CommitIngestItem]


class TranscriptIngestBody(BaseModel):
    machine_id: str
    vendor: str
    vendor_session_id: str
    model: str | None = None
    workspace_hint: str | None = None
    transcript_source_path: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    content_encoding: str = "raw"  # "raw" | "gzip"
    content: str  # base64-encoded blob body


# --- Helpers ---


_SHA_PATTERN = re.compile(rb"\b[0-9a-f]{7,40}\b")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # Accept trailing 'Z' for UTC — datetime.fromisoformat only
        # handles it on Python 3.11+, so normalize defensively.
        normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
        return datetime.fromisoformat(normalized)
    except (ValueError, TypeError):
        return None


def _dt_equal(a: datetime | None, b: datetime | None) -> bool:
    """Equality that tolerates naive-vs-aware differences.

    SQLite drops tzinfo on round-trip through `DateTime(timezone=True)`
    columns; Postgres preserves it. Compare as UTC-normalized values so
    an already-stored timestamp isn't spuriously re-detected as changed
    on the next ingest just because storage stripped its tzinfo.
    """
    if a is None or b is None:
        return a is None and b is None
    a_utc = a if a.tzinfo else a.replace(tzinfo=timezone.utc)
    b_utc = b if b.tzinfo else b.replace(tzinfo=timezone.utc)
    return a_utc == b_utc


def _decode_content(body: TranscriptIngestBody) -> bytes:
    try:
        raw = base64.b64decode(body.content, validate=True)
    except (ValueError, TypeError) as e:
        raise ApiError(400, "invalid_parameter", f"content is not valid base64: {e}")
    if body.content_encoding == "gzip":
        try:
            raw = gzip.decompress(raw)
        except OSError as e:
            raise ApiError(400, "invalid_parameter", f"gzip decompress failed: {e}")
    elif body.content_encoding != "raw":
        raise ApiError(
            400, "invalid_parameter",
            f"content_encoding must be 'raw' or 'gzip', got {body.content_encoding!r}",
        )
    return raw


def _get_blob_store() -> FilesystemBlobStore:
    settings = get_settings()
    return FilesystemBlobStore(settings.blob_store_root)


def _run_linkage(
    db: Session,
    *,
    organization_id: uuid.UUID,
    machine_id: str,
    vendor: str,
    vendor_session_id: str,
    transcript_row: TranscriptSession,
    content: bytes,
) -> list[dict[str, str]]:
    """Run MVP linkage bases against a freshly-written transcript.

    Returns the list of link summaries for the response body. Idempotent
    against the unique key ``(commit_id, transcript_session_id,
    linkage_basis)`` — pre-existing rows are skipped.
    """
    created: list[dict[str, str]] = []
    # Per-call dedup: full + prefix hits from the same transcript often
    # resolve to the same (commit, basis) pair (e.g. `955cb7823fb00` and
    # `955cb782` both match the same commit). We add rows to the session
    # without flushing between iterations, so the DB uniqueness check
    # can't see the just-queued row — this set fills that gap.
    seen_pairs: set[tuple[uuid.UUID, str]] = set()

    # --- Basis 1: exact SHA in transcript content ---
    # Cap scan to first 4MB for latency; commit SHAs written by the
    # session naturally cluster near the top of the transcript anyway
    # (they land in tool results after the commit tool call).
    scan_slice = content[: 4 * 1024 * 1024]
    seen_shas: set[str] = set()
    for match in _SHA_PATTERN.findall(scan_slice):
        try:
            candidate = match.decode("ascii")
        except UnicodeDecodeError:
            continue
        if candidate in seen_shas:
            continue
        seen_shas.add(candidate)
        # Look up commit by prefix within the same org
        commit = db.execute(
            select(Commit).where(
                Commit.organization_id == organization_id,
                Commit.commit_sha.like(f"{candidate}%"),
            ).limit(2)
        ).scalars().all()
        if len(commit) != 1:
            # 0 → no match; 2+ → ambiguous prefix, skip rather than
            # link to the wrong commit
            continue
        pair = (commit[0].id, "exact_sha_in_transcript")
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        link = _upsert_link(
            db,
            organization_id=organization_id,
            commit_id=commit[0].id,
            transcript_session_id=transcript_row.id,
            linkage_basis="exact_sha_in_transcript",
            linkage_confidence="high",
            linkage_metadata={"matched_sha": candidate, "commit_sha": commit[0].commit_sha},
        )
        if link:
            created.append({
                "commit_sha": commit[0].commit_sha,
                "linkage_basis": "exact_sha_in_transcript",
            })

    # --- Basis 2: session_id in commit's snippet ---
    # Commits pre-ingested by `transcripts pull` step 1 carry the
    # snippet's transcript_session_id (Migration 008 column, mapped on
    # the ORM in the same commit as this ingest route).
    session_matches = db.execute(
        select(Commit).where(
            Commit.organization_id == organization_id,
            Commit.transcript_session_id == vendor_session_id,
        )
    ).scalars().all()
    for commit_row in session_matches:
        pair = (commit_row.id, "session_id_in_snippet")
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        link = _upsert_link(
            db,
            organization_id=organization_id,
            commit_id=commit_row.id,
            transcript_session_id=transcript_row.id,
            linkage_basis="session_id_in_snippet",
            linkage_confidence="high",
            linkage_metadata={
                "matched_vendor_session_id": vendor_session_id,
                "commit_sha": commit_row.commit_sha,
            },
        )
        if link:
            created.append({
                "commit_sha": commit_row.commit_sha,
                "linkage_basis": "session_id_in_snippet",
            })

    return created


def _upsert_link(
    db: Session,
    *,
    organization_id: uuid.UUID,
    commit_id: uuid.UUID,
    transcript_session_id: uuid.UUID,
    linkage_basis: str,
    linkage_confidence: str,
    linkage_metadata: dict[str, Any],
) -> bool:
    """Insert a link row, silently no-op on unique violation. Returns
    True if a new row was inserted, False if the link already existed."""
    existing = db.execute(
        select(CommitTranscriptLink.id).where(
            CommitTranscriptLink.commit_id == commit_id,
            CommitTranscriptLink.transcript_session_id == transcript_session_id,
            CommitTranscriptLink.linkage_basis == linkage_basis,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return False
    db.add(CommitTranscriptLink(
        id=uuid.uuid4(),
        organization_id=organization_id,
        commit_id=commit_id,
        transcript_session_id=transcript_session_id,
        linkage_basis=linkage_basis,
        linkage_confidence=linkage_confidence,
        linkage_metadata=linkage_metadata,
        created_at=datetime.now(timezone.utc),
    ))
    return True


# --- Endpoints ---


@router.post("/commits/ingest")
def ingest_commits(
    body: CommitIngestBody,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Batch-upsert commits from local git activity.

    Called by `gator-enterprise transcripts pull` step 1 before
    transcripts are uploaded, so the FK targets exist for the linkage
    algorithm's `exact_sha_in_transcript` and `session_id_in_snippet`
    bases. Idempotent by
    ``(organization_id, repo_identifier, commit_sha)``.
    """
    if not body.commits:
        return {"commits_ingested": []}

    now = datetime.now(timezone.utc)
    results: list[dict[str, str]] = []

    for item in body.commits:
        machine_id = item.machine_id or body.machine_id
        existing = db.execute(
            select(Commit).where(
                Commit.organization_id == token.organization_id,
                Commit.repo_identifier == item.repo_canonical_id,
                Commit.commit_sha == item.sha,
            )
        ).scalar_one_or_none()

        committed_at = _parse_iso(item.committed_at)

        if existing is None:
            commit = Commit(
                id=uuid.uuid4(),
                organization_id=token.organization_id,
                repo_identifier=item.repo_canonical_id,
                commit_sha=item.sha,
                author_identity=item.author,
                commit_message=item.subject,
                committed_at=committed_at,
                ingested_at=now,
                machine_id=machine_id,
                machine_label=item.machine_label,
                snippet_agent=item.snippet_agent,
            )
            if item.transcript_session_id:
                commit.transcript_session_id = item.transcript_session_id
            db.add(commit)
            db.flush()
            status = "created"
            commit_id = commit.id
        else:
            status = "unchanged"
            # Refresh a small set of fields when the caller provides
            # richer data than what's stored. Never overwrite non-null
            # existing values with nulls — provider-sync ingest may have
            # populated a subset of these already.
            changed = False
            for attr, incoming in [
                ("author_identity", item.author),
                ("commit_message", item.subject),
                ("machine_id", machine_id),
                ("machine_label", item.machine_label),
                ("snippet_agent", item.snippet_agent),
                ("transcript_session_id", item.transcript_session_id),
            ]:
                if incoming and getattr(existing, attr) != incoming:
                    setattr(existing, attr, incoming)
                    changed = True
            if committed_at and not _dt_equal(existing.committed_at, committed_at):
                existing.committed_at = committed_at
                changed = True
            if changed:
                status = "updated"
            commit_id = existing.id

        results.append({
            "sha": item.sha,
            "commit_id": str(commit_id),
            "status": status,
        })

    db.commit()
    return {"commits_ingested": results}


@router.post("/transcripts/ingest")
def ingest_transcript(
    body: TranscriptIngestBody,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Upsert a transcript session and store its body in the blob store.

    Idempotent by ``(organization_id, machine_id, vendor,
    vendor_session_id)``. Re-ingesting the same session updates
    ``last_seen_at`` and rewrites the blob if the sha256 differs.
    """
    if not body.vendor or not body.vendor_session_id or not body.machine_id:
        raise ApiError(
            400, "invalid_parameter",
            "vendor, vendor_session_id, and machine_id are required",
        )

    raw = _decode_content(body)
    blob_sha256 = hashlib.sha256(raw).hexdigest()
    started_at = _parse_iso(body.started_at)
    ended_at = _parse_iso(body.ended_at)
    now = datetime.now(timezone.utc)

    blob_key = build_blob_key(
        org_uuid=str(token.organization_id),
        machine_id=body.machine_id,
        vendor=body.vendor,
        started_at_iso=body.started_at or now.isoformat(),
        vendor_session_id=body.vendor_session_id,
    )

    existing = db.execute(
        select(TranscriptSession).where(
            TranscriptSession.organization_id == token.organization_id,
            TranscriptSession.machine_id == body.machine_id,
            TranscriptSession.vendor == body.vendor,
            TranscriptSession.vendor_session_id == body.vendor_session_id,
        )
    ).scalar_one_or_none()

    blob_store = _get_blob_store()

    if existing is None:
        blob_store.put(blob_key, raw)
        ts_row = TranscriptSession(
            id=uuid.uuid4(),
            organization_id=token.organization_id,
            machine_id=body.machine_id,
            vendor=body.vendor,
            vendor_session_id=body.vendor_session_id,
            model=body.model,
            workspace_hint=body.workspace_hint,
            transcript_source_path=body.transcript_source_path,
            blob_key=blob_key,
            blob_size_bytes=len(raw),
            blob_sha256=blob_sha256,
            started_at=started_at,
            ended_at=ended_at,
            last_seen_at=now,
            ingested_at=now,
        )
        db.add(ts_row)
        db.flush()
        status = "created"
    else:
        ts_row = existing
        if existing.blob_sha256 != blob_sha256:
            blob_store.put(blob_key, raw)
            existing.blob_key = blob_key
            existing.blob_sha256 = blob_sha256
            existing.blob_size_bytes = len(raw)
        if body.model and existing.model != body.model:
            existing.model = body.model
        if body.workspace_hint and existing.workspace_hint != body.workspace_hint:
            existing.workspace_hint = body.workspace_hint
        if body.transcript_source_path and existing.transcript_source_path != body.transcript_source_path:
            existing.transcript_source_path = body.transcript_source_path
        if started_at and existing.started_at != started_at:
            existing.started_at = started_at
        if ended_at and existing.ended_at != ended_at:
            existing.ended_at = ended_at
        existing.last_seen_at = now
        status = "updated"

    links = _run_linkage(
        db,
        organization_id=token.organization_id,
        machine_id=body.machine_id,
        vendor=body.vendor,
        vendor_session_id=body.vendor_session_id,
        transcript_row=ts_row,
        content=raw,
    )

    db.commit()

    return {
        "transcript_session_id": str(ts_row.id),
        "blob_key": ts_row.blob_key,
        "blob_sha256": ts_row.blob_sha256,
        "blob_size_bytes": ts_row.blob_size_bytes,
        "status": status,
        "commits_linked": links,
    }
