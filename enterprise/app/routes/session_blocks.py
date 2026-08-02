"""E7 session block routes — transcript views, machine identity, pending evidence."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, distinct, func, select
from sqlalchemy.orm import Session

from app.api_contract import ApiError, parse_uuid
from app.auth import verify_token
from app.db import get_db
from app.models.api_token import ApiToken
from app.models.commit import Commit
from app.models.evidence_block import CommitEvidenceBlock
from app.models.repository import Repository
from app.services.session_blocks import (
    get_block_for_commit,
    get_pending_blocks_by_machine,
    get_session_reconstruction,
)

router = APIRouter(tags=["session_blocks"])


@router.get("/views/repos/{repo_id}/blocks")
def list_repo_blocks(
    repo_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """List indexed session blocks for a repo (metadata only, not transcripts)."""
    rid = parse_uuid(repo_id, "repo_id")
    repo = db.execute(
        select(Repository).where(
            Repository.id == rid,
            Repository.organization_id == token.organization_id,
        )
    ).scalar_one_or_none()
    if repo is None:
        raise ApiError(404, "not_found", "Repository not found")

    blocks = db.execute(
        select(CommitEvidenceBlock, Commit)
        .join(Commit, CommitEvidenceBlock.commit_id == Commit.id)
        .where(
            Commit.repo_identifier == repo.canonical_identifier,
            Commit.organization_id == token.organization_id,
            CommitEvidenceBlock.block_type == "session_block",
        )
        .order_by(desc(Commit.committed_at))
        .offset(offset)
        .limit(limit)
    ).all()

    total = db.execute(
        select(func.count(CommitEvidenceBlock.id))
        .join(Commit, CommitEvidenceBlock.commit_id == Commit.id)
        .where(
            Commit.repo_identifier == repo.canonical_identifier,
            Commit.organization_id == token.organization_id,
            CommitEvidenceBlock.block_type == "session_block",
        )
    ).scalar_one()

    return {
        "blocks": [
            {
                "id": str(b.CommitEvidenceBlock.id),
                "commit_sha": b.Commit.commit_sha,
                "committed_at": b.Commit.committed_at.isoformat() if b.Commit.committed_at else None,
                "vendor": b.CommitEvidenceBlock.vendor,
                "turn_count": b.CommitEvidenceBlock.turn_count,
                "capture_quality": b.CommitEvidenceBlock.capture_quality,
                "machine_id": b.Commit.machine_id,
                "machine_label": b.Commit.machine_label,
                "artifact_path": b.CommitEvidenceBlock.artifact_path,
                "indexed_from_ref": b.CommitEvidenceBlock.indexed_from_ref,
            }
            for b in blocks
        ],
        "pagination": {"offset": offset, "limit": limit, "total": total},
    }


@router.get("/views/commits/{commit_id}/transcript")
def get_transcript(
    commit_id: str,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Fetch the full transcript slice for a specific commit."""
    cid = parse_uuid(commit_id, "commit_id")

    # Verify org scoping
    commit = db.execute(
        select(Commit).where(
            Commit.id == cid,
            Commit.organization_id == token.organization_id,
        )
    ).scalar_one_or_none()
    if commit is None:
        raise ApiError(404, "not_found", "Commit not found")

    block = get_block_for_commit(db, cid)
    if block is None:
        raise ApiError(404, "not_found", "No session block for this commit")

    return {
        "commit_sha": commit.commit_sha,
        "vendor": block.get("vendor"),
        "capture_quality": block.get("capture_quality"),
        "turn_count": block.get("turn_count"),
        "interval": block.get("interval"),
        "turns": block.get("turns", []),
        "content_sha256": block.get("content_sha256"),
    }


@router.get("/views/machines")
def list_machines(
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """List all known machines across the org."""
    machines = db.execute(
        select(
            Commit.machine_id,
            Commit.machine_label,
            func.count(distinct(Commit.repo_identifier)).label("repo_count"),
            func.count(Commit.id).label("commit_count"),
            func.max(Commit.committed_at).label("last_seen"),
        )
        .where(
            Commit.organization_id == token.organization_id,
            Commit.machine_id.isnot(None),
        )
        .group_by(Commit.machine_id, Commit.machine_label)
        .order_by(func.max(Commit.committed_at).desc())
    ).all()

    return {
        "machines": [
            {
                "machine_id": m.machine_id,
                "machine_label": m.machine_label,
                "repo_count": m.repo_count,
                "commit_count": m.commit_count,
                "last_seen": m.last_seen.isoformat() if m.last_seen else None,
            }
            for m in machines
        ],
    }


@router.get("/views/machines/pending")
def list_pending_blocks(
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """List AI-assisted commits with no session block (pending evidence).

    Excludes human-only commits (snippet_agent null).
    """
    pending = get_pending_blocks_by_machine(db, token.organization_id)
    return {"pending": pending}
