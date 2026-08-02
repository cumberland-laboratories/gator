"""Provider protocol — operations-only interface for Git provider adapters.

Auth plumbing (tokens, JWTs, keys) is internal to each adapter.
The protocol consumer only sees business operations.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass
class CommitInfo:
    """Normalized commit metadata from a provider."""

    sha: str
    author: str | None = None
    message: str | None = None
    timestamp: datetime | None = None
    model_identities: dict | None = None


@dataclass
class RepoInfo:
    """Normalized repository metadata from a provider."""

    provider_repo_id: str
    name: str
    full_name: str  # e.g. "cumberland-laboratories/test-repo"
    default_branch: str = "main"


class ProviderAdapter(Protocol):
    """Interface for Git provider integrations.

    Each adapter handles its own auth internally.
    Protocol consumers call operations, never touch tokens.
    """

    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        """Verify webhook signature authenticity."""
        ...

    def parse_push_event(self, payload: dict) -> list[CommitInfo]:
        """Extract commit info from a push event payload."""
        ...

    def list_repositories(self) -> list[RepoInfo]:
        """List all repositories accessible to this integration."""
        ...

    def list_commits_since(self, repo_full_name: str, since: datetime | None) -> list[CommitInfo]:
        """List commits on default branch since a given time."""
        ...

    def get_file_at_commit(self, repo_full_name: str, path: str, ref: str) -> bytes | None:
        """Get file content at a specific commit. Returns None if not found."""
        ...

    def list_directory_at_commit(self, repo_full_name: str, path: str, ref: str) -> list[str] | None:
        """List filenames in a directory at a specific commit. Returns None if not found."""
        ...
