"""Bare clone cache for reading repo files.

Enterprise maintains a directory of bare clones, one per tracked repo.
Clones are created on first access and updated via git fetch on each
webhook event or reconciliation pass.

Auth is injected per-operation via git http.extraHeader — tokens are
never persisted in .git/config or on disk.
"""

import os
import subprocess
import threading
from pathlib import Path

from app.config import get_settings
from app.logging import get_logger

logger = get_logger("gator.enterprise.clone_cache")


class RepoCloneCache:
    """Bare clone cache keyed by canonical repo identifier."""

    def __init__(self, cache_dir: str | None = None):
        self.cache_dir = Path(cache_dir or get_settings().clone_cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _cache_path(self, canonical_identifier: str) -> Path:
        """Derive cache path from canonical identifier.

        e.g., github.com/company/core-api → <cache_dir>/github.com/company/core-api.git
        """
        return self.cache_dir / f"{canonical_identifier}.git"

    def _remote_url(self, canonical_identifier: str) -> str:
        """Unauthenticated HTTPS remote URL. No token in the URL.

        e.g., github.com/company/core-api → https://github.com/company/core-api.git
        """
        return f"https://{canonical_identifier}.git"

    def _get_auth_header(self, provider) -> str | None:
        """Generate a fresh auth header for this operation.

        For GitHub: obtains a new installation token via JWT exchange.
        The token is used for one git operation and never written to disk.
        """
        if provider is None:
            return None

        try:
            if provider.provider_type == "github":
                from app.providers.github import GitHubAdapter
                from app.config import get_settings
                settings = get_settings()
                config = provider.config or {}
                adapter = GitHubAdapter(
                    app_id=settings.github_app_id or config.get("app_id", ""),
                    private_key=settings.github_private_key or config.get("private_key", ""),
                    installation_id=str(config.get("installation_id", "")),
                )
                token = adapter._get_installation_token()
                return f"Authorization: Bearer {token}"
            return None
        except Exception as e:
            logger.warning("clone_cache.auth_failed", error=str(e), provider_type=provider.provider_type)
            return None

    def _git(self, *args, cwd=None, auth_header: str | None = None,
             capture_output=True) -> subprocess.CompletedProcess:
        """Run a git command with optional per-process auth header."""
        cmd = ["git"]
        if auth_header:
            cmd.extend(["-c", f"http.extraHeader={auth_header}"])
        cmd.extend(args)

        return subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=capture_output,
            text=True,
            timeout=120,
        )

    def ensure_clone(self, repo, provider=None) -> Path:
        """Clone or fetch a repo. Returns path to bare clone.

        Thread-safe. Auth injected per-operation, never persisted.
        """
        cache_path = self._cache_path(repo.canonical_identifier)
        auth_header = self._get_auth_header(provider)

        with self._lock:
            if not cache_path.exists():
                # First-time clone
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                result = self._git(
                    "clone", "--bare",
                    self._remote_url(repo.canonical_identifier),
                    str(cache_path),
                    auth_header=auth_header,
                )
                if result.returncode != 0:
                    logger.error("clone_cache.clone_failed",
                                 repo=repo.canonical_identifier,
                                 error=result.stderr.strip())
                    raise RuntimeError(f"git clone failed: {result.stderr.strip()}")
                logger.info("clone_cache.cloned", repo=repo.canonical_identifier)
            else:
                # Fetch latest
                result = self._git(
                    "fetch", "--all", "--prune",
                    cwd=str(cache_path),
                    auth_header=auth_header,
                )
                if result.returncode != 0:
                    logger.warning("clone_cache.fetch_failed",
                                   repo=repo.canonical_identifier,
                                   error=result.stderr.strip())
                    # Don't raise — stale clone is better than no clone

        return cache_path

    def resolve_ref(self, repo, branch: str) -> str:
        """Resolve a bare branch name to a git ref that works in this clone.

        Bare clones can store refs as refs/heads/<branch> or origin/<branch>
        depending on how they were created and fetched. This probes both.
        """
        cache_path = self._cache_path(repo.canonical_identifier)
        for candidate in [f"origin/{branch}", branch, f"refs/heads/{branch}"]:
            result = self._git(
                "rev-parse", "--verify", "--quiet", candidate,
                cwd=str(cache_path),
            )
            if result.returncode == 0:
                return candidate
        return branch  # fall back, let git show fail with a clear error

    def read_file(self, repo, path: str, branch: str = "main") -> bytes | None:
        """Read a file from the bare clone at a given branch.

        Runs: git show <resolved_ref>:<path>
        Returns file bytes or None if not found.
        No auth needed — reads from local bare clone.
        """
        cache_path = self._cache_path(repo.canonical_identifier)
        if not cache_path.exists():
            return None

        ref = self.resolve_ref(repo, branch)
        result = subprocess.run(
            ["git", "show", f"{ref}:{path}"],
            cwd=str(cache_path),
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        return result.stdout

    def list_directory(self, repo, path: str, branch: str = "main") -> list[str]:
        """List files in a directory at a given branch.

        Runs: git ls-tree --name-only <resolved_ref> <path>/
        Returns list of filenames (not full paths).
        """
        cache_path = self._cache_path(repo.canonical_identifier)
        if not cache_path.exists():
            return []

        ref = self.resolve_ref(repo, branch)
        # Ensure path ends with /
        tree_path = path.rstrip("/") + "/"
        result = self._git(
            "ls-tree", "--name-only", ref, tree_path,
            cwd=str(cache_path),
        )
        if result.returncode != 0:
            return []

        return [
            line.strip() for line in result.stdout.strip().split("\n")
            if line.strip()
        ]
