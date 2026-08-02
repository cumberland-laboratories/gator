"""Evidence extraction service — commit observation from governance artifacts.

Extracts structured governance facts from a commit's repo state:
- Commit trailers (Gator-* keys)
- .gator/status.json presence and hash
- .gator/charters/ file listing
- .gator/constitution.md presence

Observations are extracted facts, not raw blobs. Git remains authoritative.
"""

import hashlib
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.commit import Commit
from app.models.commit_observation import CommitObservation
from app.models.git_provider import GitProvider
from app.models.repository import Repository
from app.services.sync import get_adapter_for_provider


def parse_trailers(message: str | None) -> dict:
    """Extract governance trailers from a commit message.

    Looks for Gator-*: Key: Value patterns. Handles both:
    - properly formatted trailer blocks (separated by blank line)
    - single-line messages where trailers appear inline (e.g., from
      webhook payloads that strip newlines)
    """
    if not message:
        return {}

    trailers = {}

    # First try: split on blank lines, scan the last block for trailer lines
    blocks = re.split(r'\n\s*\n', message.strip())
    if blocks:
        last_block = blocks[-1]
        for line in last_block.strip().split('\n'):
            line = line.strip()
            match = re.match(r'^(Gator-[\w-]+):\s*(.+?)(?:\s+Gator-|\s*$)', line)
            if match:
                trailers[match.group(1)] = match.group(2).strip()

    # Fallback: scan entire message for Gator-Key: Value patterns
    # This handles messages where newlines were lost or trailers are inline
    if not trailers:
        for match in re.finditer(r'(Gator-[\w-]+):\s*([^\s](?:.*?)(?=\s+Gator-[\w-]+:|$))', message):
            trailers[match.group(1)] = match.group(2).strip()

    return trailers


def extract_observation(db: Session, commit: Commit, repo: Repository):
    """Extract governance observation for a commit.

    Retry semantics:
    - If observation exists with status=observed, skip (idempotent)
    - If observation exists with status=failed, delete and re-extract (retry)
    """
    # Check for existing observation
    existing = db.execute(
        select(CommitObservation).where(
            CommitObservation.commit_id == commit.id
        )
    ).scalar_one_or_none()

    if existing is not None:
        if existing.observation_status == "observed":
            return existing  # Already done, idempotent skip
        # Failed observation — reuse the existing row for retry
        observation = existing
        observation.observation_status = "pending"
        observation.error = None
    else:
        observation = CommitObservation(
            organization_id=commit.organization_id,
            commit_id=commit.id,
            repository_id=repo.id,
            observation_status="pending",
        )
        db.add(observation)

    db.flush()

    # Get provider adapter
    provider = db.execute(
        select(GitProvider).where(GitProvider.id == repo.provider_id)
    ).scalar_one()
    adapter = get_adapter_for_provider(provider)

    # Extract repo full name from canonical_identifier
    parts = repo.canonical_identifier.split("/", 1)
    repo_full_name = parts[1] if len(parts) > 1 else repo.name

    try:
        # Parse trailers from commit message
        trailers = parse_trailers(commit.commit_message)
        observation.trailers = trailers

        # Check .gator/status.json
        status_json = adapter.get_file_at_commit(repo_full_name, ".gator/status.json", commit.commit_sha)
        observation.status_json_present = status_json is not None
        if status_json is not None:
            observation.status_json_hash = hashlib.sha256(status_json).hexdigest()

        # Check .gator/charters/
        charter_files = adapter.list_directory_at_commit(repo_full_name, ".gator/charters", commit.commit_sha)
        if charter_files is not None:
            charter_files = [f for f in charter_files if f.endswith(".md")]
            observation.charter_count = len(charter_files)
            observation.charter_names = charter_files
        else:
            observation.charter_count = 0
            observation.charter_names = []

        # Check .gator/constitution.md
        constitution = adapter.get_file_at_commit(repo_full_name, ".gator/constitution.md", commit.commit_sha)
        observation.constitution_present = constitution is not None

        observation.observation_status = "observed"
        db.commit()
        return observation

    except Exception as e:
        db.rollback()
        # Re-query or create the failed observation record
        observation = db.execute(
            select(CommitObservation).where(CommitObservation.commit_id == commit.id)
        ).scalar_one_or_none()
        if observation:
            observation.observation_status = "failed"
            observation.error = {"message": str(e)}
        else:
            # First-attempt failure: row was rolled back, create a fresh failed record
            db.add(CommitObservation(
                organization_id=commit.organization_id,
                commit_id=commit.id,
                repository_id=repo.id,
                observation_status="failed",
                error={"message": str(e)},
            ))
        db.commit()
        raise
