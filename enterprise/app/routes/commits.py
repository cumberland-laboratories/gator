"""Commit read endpoints — provenance, reverse lookups.

Companion to ``routes/ingest.py`` (write side) and ``routes/transcripts.py``
(which houses the ``/commits/{sha}/transcripts`` reverse-lookup for
historical co-location with the transcript-list surface).

This module owns the commit-side reads that DON'T return transcripts:

- ``GET /api/v1/commits/{sha}/provenance`` — Q4 from the 2026-08-14
  audit-question-surface artifact ("Which machine produced commit
  ``<sha>``?"). Returns commit-side provenance fields populated during
  commit reconciliation from the snippet: machine_id, machine_label,
  snippet_agent, transcript_session_id, committed_at, author_identity,
  repo_identifier. Ratified as `commits provenance <sha>` CLI verb via
  R3 = (i) at Phase 1 exit.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_contract import ApiError
from app.auth import verify_token
from app.db import get_db
from app.models.api_token import ApiToken
from app.models.commit import Commit

router = APIRouter(tags=["commits"])


@router.get("/commits/{commit_sha}/provenance")
def get_commit_provenance(
    commit_sha: str,
    repo_canonical_id: str | None = Query(
        None,
        description=(
            "Optional repo scope. If omitted, all commits with this SHA "
            "in the caller's org are considered — matching how "
            "`/commits/{sha}/transcripts` scopes."
        ),
    ),
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Return commit provenance fields — Q4 from audit-question-surface artifact.

    Populated during commit reconciliation from the snippet's `machine_id`,
    `machine_label`, `snippet_agent`, `transcript_session_id` fields
    (Migration 008). Commit rows without a snippet have these fields null
    (human-authored commits, or commits from machines that never ran a
    gator-governed session).

    SHA prefix matching (7-40 hex chars) mirrors `/commits/{sha}/transcripts`.
    When more than one commit matches the SHA in the caller's org, ALL
    matching commit rows are returned in the `commits` array — caller
    disambiguates by `repo_identifier` or supplies `repo_canonical_id` up
    front to narrow the match.
    """
    if not commit_sha or len(commit_sha) < 7 or len(commit_sha) > 40:
        raise ApiError(400, "invalid_parameter", "commit_sha must be 7-40 hex chars")

    stmt = select(Commit).where(
        Commit.organization_id == token.organization_id,
        Commit.commit_sha.like(f"{commit_sha}%"),
    )
    if repo_canonical_id:
        stmt = stmt.where(Commit.repo_identifier == repo_canonical_id)
    stmt = stmt.order_by(Commit.committed_at.desc())

    commit_rows = db.execute(stmt).scalars().all()

    return {
        "commits": [
            {
                "commit_sha": c.commit_sha,
                "repo_identifier": c.repo_identifier,
                "author_identity": c.author_identity,
                "committed_at": c.committed_at.isoformat() if c.committed_at else None,
                "machine_id": c.machine_id,
                "machine_label": c.machine_label,
                "snippet_agent": c.snippet_agent,
                "transcript_session_id": c.transcript_session_id,
            }
            for c in commit_rows
        ],
    }
