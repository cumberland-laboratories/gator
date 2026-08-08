"""Filesystem-backed BlobStore reference implementation.

Suitable for single-node Enterprise deployments. Backing directory
is configured via the ``BLOB_STORE_ROOT`` env var (see
``app.config.Settings.blob_store_root``); default is
``/var/lib/gator-enterprise/blobs``.

Concurrency safety: put uses temp-file + atomic ``os.replace``;
delete uses ``os.remove`` with FileNotFound tolerance; list walks
the directory tree without a lock. Multiple concurrent workers
uploading the same key race is resolved by last-writer-wins via
``os.replace`` (idempotent when content is identical).
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

from app.services.blob_store import BlobNotFound


# Windows can raise PermissionError from os.replace when the target is
# briefly opened by another handle (antivirus scan, another writer racing
# on the same key). Retry with light backoff. POSIX doesn't need this,
# but the retry is harmless there — it only fires on failure.
_REPLACE_RETRY_ATTEMPTS = 6
_REPLACE_RETRY_INITIAL_SLEEP_SEC = 0.005


class FilesystemBlobStore:
    """Local-filesystem backend for the :class:`BlobStore` protocol.

    Attributes:
        root: Base directory for all blob storage; created lazily
              on first ``put``.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def put(self, key: str, content: bytes) -> str:
        target = self._path_for(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: temp-file in the same directory, then replace.
        # Same-directory is required so os.replace stays atomic on POSIX
        # (no cross-filesystem move); using tempfile.mkstemp with dir=
        # ensures that.
        fd, tmp_path = tempfile.mkstemp(
            dir=str(target.parent), prefix=".blob-", suffix=".tmp"
        )
        closed = False
        try:
            os.write(fd, content)
            os.close(fd)
            closed = True
            self._replace_with_retry(tmp_path, str(target))
        except Exception:
            if not closed:
                try:
                    os.close(fd)
                except OSError:
                    pass
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        return key

    @staticmethod
    def _replace_with_retry(src: str, dst: str) -> None:
        """os.replace with Windows-safe retry loop.

        On Windows, os.replace can raise PermissionError when the target
        is briefly held by another handle (antivirus scan, concurrent
        writer race). Retry with exponential backoff a few times before
        giving up. POSIX won't hit the retry path in practice."""
        sleep_sec = _REPLACE_RETRY_INITIAL_SLEEP_SEC
        last_error: Exception | None = None
        for _ in range(_REPLACE_RETRY_ATTEMPTS):
            try:
                os.replace(src, dst)
                return
            except PermissionError as e:
                last_error = e
                time.sleep(sleep_sec)
                sleep_sec *= 2
        # Give up — surface the original error type
        raise last_error if last_error else RuntimeError("replace failed")

    def get(self, key: str) -> bytes:
        target = self._path_for(key)
        if not target.exists():
            raise BlobNotFound(key)
        return target.read_bytes()

    def exists(self, key: str) -> bool:
        return self._path_for(key).exists()

    def delete(self, key: str) -> None:
        target = self._path_for(key)
        try:
            target.unlink()
        except FileNotFoundError:
            pass

    def list(self, prefix: str = "") -> list[str]:
        # Walk under the prefix's directory-shaped subtree and return
        # keys relative to the root. Non-existent prefix -> empty list
        # rather than error (matches the "list is safe on any input"
        # convention).
        prefix_norm = prefix.strip("/")
        start = self.root if not prefix_norm else self.root / prefix_norm
        if not start.exists():
            return []
        results: list[str] = []
        # If the prefix is a file itself, treat it as a single-key match
        if start.is_file():
            results.append(str(start.relative_to(self.root)).replace(os.sep, "/"))
            return results
        for path in start.rglob("*"):
            if path.is_file() and not path.name.startswith(".blob-"):
                rel = path.relative_to(self.root)
                results.append(str(rel).replace(os.sep, "/"))
        return results

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _path_for(self, key: str) -> Path:
        # Reject absolute paths and traversal — keys are relative,
        # forward-slash-only, and must stay under root.
        if not key:
            raise ValueError("blob key must be non-empty")
        # Normalize backslashes just in case caller passed a Windows path
        normalized = key.replace("\\", "/").lstrip("/")
        parts = [p for p in normalized.split("/") if p]
        if any(p == ".." for p in parts):
            raise ValueError(f"blob key cannot contain '..' segments: {key!r}")
        return self.root.joinpath(*parts)
