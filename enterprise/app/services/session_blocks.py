"""Session block indexing, machine identity, pending detection, and reconstruction.

Reconciles session blocks and snippets from bare clones into the Enterprise
index. Handles machine identity population, AI vs human-only classification,
and pending evidence detection.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, select, func
from sqlalchemy.orm import Session

from app.logging import get_logger
from app.models.commit import Commit
from app.models.evidence_block import CommitEvidenceBlock
from app.models.repository import Repository
from app.services.artifact_reader import ArtifactReader
from app.services.repo_clone import RepoCloneCache

logger = get_logger("gator.enterprise.session_blocks")


def reconcile_session_blocks(
    db: Session,
    repo: Repository,
    branch: str | None = None,
    clone_cache: RepoCloneCache | None = None,
) -> list[CommitEvidenceBlock]:
    """Reconcile session blocks AND snippet metadata for a repo against a branch.

    1. Ensure clone is current
    2. Index snippets — machine identity + AI attribution
    3. Index session blocks — metadata only, content stays in Git
    4. Return newly indexed blocks
    """
    if clone_cache is None:
        clone_cache = RepoCloneCache()

    branch = branch or repo.default_branch
    reader = ArtifactReader(clone_cache)

    # Fetch latest
    from app.models.git_provider import GitProvider
    provider = db.execute(
        select(GitProvider).where(GitProvider.id == repo.provider_id)
    ).scalar_one_or_none()

    clone_cache.ensure_clone(repo, provider)

    newly_indexed = []

    # --- Index snippets (machine identity + AI attribution) ---
    snippet_files = reader.list_snippets(repo, branch=branch)
    for snippet_file in snippet_files:
        snippet_path = f".gator/session-snippets/{snippet_file}"
        snippet = reader.get_snippet(repo, snippet_path, branch=branch)
        if snippet is None:
            continue

        # Match to commit by SHA
        commit_sha = snippet.get("commit")
        if not commit_sha:
            continue

        commit = db.execute(
            select(Commit).where(
                Commit.organization_id == repo.organization_id,
                Commit.repo_identifier == repo.canonical_identifier,
                Commit.commit_sha == commit_sha,
            )
        ).scalar_one_or_none()

        if commit is None:
            continue

        # Populate machine identity and agent if not already set
        updated = False
        if commit.machine_id is None and snippet.get("machine_id"):
            commit.machine_id = snippet["machine_id"]
            updated = True
        if commit.machine_label is None and snippet.get("machine_label"):
            commit.machine_label = snippet["machine_label"]
            updated = True
        if commit.snippet_agent is None:
            commit.snippet_agent = snippet.get("agent")  # may be None for human-only
            updated = True

        if updated:
            db.flush()

    # --- Index session blocks ---
    block_files = reader.list_session_blocks(repo, branch=branch)
    for block_file in block_files:
        block_path = f".gator/session-blocks/{block_file}"

        # Read metadata only — no decryption needed for indexing.
        # For v2 plaintext: decompress and parse.
        # For v3 encrypted: read cleartext envelope fields.
        block = reader.get_session_block_metadata(repo, block_path, branch=branch)
        if block is None:
            continue

        content_hash = block.get("content_sha256", "")
        target_sha = block.get("target_commit", "")

        # Check if already indexed
        existing = db.execute(
            select(CommitEvidenceBlock).where(
                CommitEvidenceBlock.artifact_path == block_path,
                CommitEvidenceBlock.content_hash == content_hash,
            )
        ).scalar_one_or_none()

        if existing is not None:
            # Already indexed — check for ref durability promotion
            if (existing.indexed_from_ref != repo.default_branch
                    and branch == repo.default_branch):
                existing.indexed_from_ref = repo.default_branch
                db.flush()
                logger.info("session_blocks.ref_promoted",
                            block=block_path, old_ref=existing.indexed_from_ref,
                            new_ref=repo.default_branch)
            continue

        # Match to commit record
        commit = db.execute(
            select(Commit).where(
                Commit.organization_id == repo.organization_id,
                Commit.repo_identifier == repo.canonical_identifier,
                Commit.commit_sha == target_sha,
            )
        ).scalar_one_or_none()

        if commit is None:
            logger.warning("session_blocks.commit_not_found",
                           target_commit=target_sha[:8], block=block_path)
            continue

        # Create index entry
        raw_bytes = clone_cache.read_file(repo, block_path, branch=branch)
        is_encrypted = block.get("_encrypted", False)
        plaintext_size = None
        if not is_encrypted and raw_bytes:
            plaintext_size = len(gzip_decompress_bytes(raw_bytes))

        # Extract encryption metadata from recipients
        org_key_id = None
        origin_machine_key_id = None
        if is_encrypted:
            for r in block.get("recipients", []):
                if r.get("kind") == "org":
                    org_key_id = r.get("key_id")
                elif r.get("kind") == "machine":
                    origin_machine_key_id = r.get("key_id")

        evidence = CommitEvidenceBlock(
            commit_id=commit.id,
            block_type="session_block",
            artifact_path=block_path,
            indexed_from_ref=branch,
            target_commit_sha=target_sha,
            content_hash=content_hash,
            capture_quality=block.get("capture_quality"),
            vendor=block.get("vendor"),
            turn_count=block.get("turn_count"),
            indexed_at=datetime.now(timezone.utc),
            plaintext_size_bytes=plaintext_size,
            size_bytes=len(raw_bytes) if raw_bytes else None,
            encryption_mode="aes-256-gcm" if is_encrypted else "plaintext",
            org_key_id=org_key_id,
            origin_machine_key_id=origin_machine_key_id,
        )
        db.add(evidence)
        db.flush()
        newly_indexed.append(evidence)

        logger.info("session_blocks.indexed",
                     block=block_path, commit=target_sha[:8],
                     vendor=block.get("vendor"), turns=block.get("turn_count"))

    db.commit()
    return newly_indexed


def gzip_decompress_bytes(data: bytes) -> bytes:
    """Decompress gzip data, returning empty bytes on failure."""
    import gzip
    try:
        return gzip.decompress(data)
    except Exception:
        return b""


def get_block_for_commit(
    db: Session, commit_id: uuid.UUID,
    clone_cache: RepoCloneCache | None = None,
) -> dict | None:
    """Fetch the session block content for a specific commit.

    Reads from bare clone on demand — content not stored in DB.
    """
    evidence = db.execute(
        select(CommitEvidenceBlock).where(
            CommitEvidenceBlock.commit_id == commit_id,
            CommitEvidenceBlock.block_type == "session_block",
        )
    ).scalar_one_or_none()

    if evidence is None:
        return None

    # Get the repo
    commit = db.execute(select(Commit).where(Commit.id == commit_id)).scalar_one()
    repo = db.execute(
        select(Repository).where(
            Repository.canonical_identifier == commit.repo_identifier,
            Repository.organization_id == commit.organization_id,
        )
    ).scalar_one_or_none()

    if repo is None:
        return None

    if clone_cache is None:
        clone_cache = RepoCloneCache()

    # Load org private key for decryption if block is encrypted
    org_private_key_pem = None
    if evidence.encryption_mode and evidence.encryption_mode != "plaintext":
        org_private_key_pem = _get_org_private_key(db, commit.organization_id, evidence.org_key_id)

    reader = ArtifactReader(clone_cache)
    branch = evidence.indexed_from_ref or repo.default_branch
    return reader.get_session_block(repo, evidence.artifact_path, branch=branch,
                                    org_private_key_pem=org_private_key_pem)


def _get_org_private_key(db: Session, org_id: uuid.UUID, key_id: str | None) -> str | None:
    """Load org private key for decryption. Looks up by key_id or falls back to active key."""
    from app.models.org_encryption_key import OrgEncryptionKey

    if key_id:
        key = db.execute(
            select(OrgEncryptionKey).where(
                OrgEncryptionKey.organization_id == org_id,
                OrgEncryptionKey.key_id == key_id,
            )
        ).scalar_one_or_none()
    else:
        key = db.execute(
            select(OrgEncryptionKey).where(
                OrgEncryptionKey.organization_id == org_id,
                OrgEncryptionKey.active == True,
            )
        ).scalar_one_or_none()

    return key.private_key_pem if key else None


def get_session_reconstruction(
    db: Session, repo_id: uuid.UUID, commit_shas: list[str],
    clone_cache: RepoCloneCache | None = None,
) -> list[dict]:
    """Reconstruct a session from multiple commits.

    Returns ordered turns with gap markers where blocks are missing.
    """
    repo = db.execute(select(Repository).where(Repository.id == repo_id)).scalar_one_or_none()
    if repo is None:
        return []

    if clone_cache is None:
        clone_cache = RepoCloneCache()

    reader = ArtifactReader(clone_cache)
    result = []

    for sha in commit_shas:
        commit = db.execute(
            select(Commit).where(
                Commit.organization_id == repo.organization_id,
                Commit.repo_identifier == repo.canonical_identifier,
                Commit.commit_sha == sha,
            )
        ).scalar_one_or_none()

        if commit is None:
            result.append({"type": "gap", "commit_sha": sha, "reason": "commit_not_found"})
            continue

        evidence = db.execute(
            select(CommitEvidenceBlock).where(
                CommitEvidenceBlock.commit_id == commit.id,
                CommitEvidenceBlock.block_type == "session_block",
            )
        ).scalar_one_or_none()

        if evidence is None:
            result.append({
                "type": "gap",
                "commit_sha": sha,
                "reason": "no_session_block",
                "is_ai_assisted": commit.snippet_agent is not None,
            })
            continue

        # Load org private key if encrypted
        org_private_key_pem = None
        if evidence.encryption_mode and evidence.encryption_mode != "plaintext":
            org_private_key_pem = _get_org_private_key(db, repo.organization_id, evidence.org_key_id)

        branch = evidence.indexed_from_ref or repo.default_branch
        block = reader.get_session_block(repo, evidence.artifact_path, branch=branch,
                                         org_private_key_pem=org_private_key_pem)
        if block is None:
            result.append({"type": "gap", "commit_sha": sha, "reason": "block_read_failed"})
            continue

        result.append({
            "type": "transcript",
            "commit_sha": sha,
            "vendor": block.get("vendor"),
            "turn_count": block.get("turn_count"),
            "turns": block.get("turns", []),
        })

    return result


def get_pending_blocks_by_machine(db: Session, org_id: uuid.UUID) -> list[dict]:
    """Find AI-assisted commits that have snippets but no session block.

    Only counts commits where snippet_agent is non-null (AI-assisted).
    Human-only commits (snippet_agent=null) are excluded.
    """
    # Subquery: commit_ids that have session blocks
    has_block = select(CommitEvidenceBlock.commit_id).where(
        CommitEvidenceBlock.block_type == "session_block"
    ).scalar_subquery()

    pending = db.execute(
        select(Commit).where(
            Commit.organization_id == org_id,
            Commit.snippet_agent.isnot(None),  # AI-assisted only
            Commit.machine_id.isnot(None),      # has machine identity
            ~Commit.id.in_(has_block),           # no session block indexed
        )
        .order_by(Commit.committed_at.desc())
        .limit(100)
    ).scalars().all()

    now = datetime.now(timezone.utc)
    return [
        {
            "machine_id": c.machine_id,
            "machine_label": c.machine_label,
            "repo": c.repo_identifier,
            "commit_sha": c.commit_sha,
            "committed_at": c.committed_at.isoformat() if c.committed_at else None,
            "hours_pending": round((now - c.committed_at).total_seconds() / 3600, 1) if c.committed_at else None,
            "agent": c.snippet_agent,
        }
        for c in pending
    ]
