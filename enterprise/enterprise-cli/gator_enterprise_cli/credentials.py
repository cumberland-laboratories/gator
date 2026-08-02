"""Enterprise credentials store — MACHINE-scoped, per-user.

Persists the Enterprise API key at `~/.gator/enterprise/credentials.json`
so `sync`/`audit` (Phase 4c-C-2 and beyond) can authenticate against
the Enterprise server without prompting on every invocation. Written by
`gator enterprise setup` since Phase 4c-C-1 (2026-08-02); previously
setup accepted `--api-key` and discarded the value.

**Scope**: MACHINE-scoped, one credentials file per user per machine.
Distinct from repo-scoped `.gator/enterprise.json` (the marker), which
records that a specific repo participates in Enterprise; the credentials
file authorizes that participation. See
`gator-command/charters/scripts-enterprise.md` for the full scope model.

**Fail-closed reads**: `read_credentials` returns `None` on missing
file, unreadable file, malformed JSON, or non-object JSON root. Never
raises for expected error modes — callers can trust the return value.

**Filesystem permissions**: on POSIX systems, `write_credentials` sets
mode `0o600` (owner read+write only) — best practice for files
containing bearer tokens. Skipped on Windows (different ACL model —
NTFS defaults to per-user profile isolation which is a reasonable
baseline; a hardened Windows story is a future concern if needed).

**Testability**: every function accepts an optional `home` parameter
(defaults to `Path.home()`) so tests can supply `tmp_path` as a fake
home without monkeypatching. Same structural convention as
`enterprise_vendor_hooks.py`.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional


CREDENTIALS_SUBPATH = Path(".gator") / "enterprise" / "credentials.json"


def credentials_path(home: Optional[Path] = None) -> Path:
    """Return the canonical path to the machine-scoped credentials file."""
    home_dir = Path(home) if home is not None else Path.home()
    return home_dir / CREDENTIALS_SUBPATH


def write_credentials(api_key: str, home: Optional[Path] = None) -> Path:
    """Persist the Enterprise API key at machine scope.

    Creates parent directories if missing. On POSIX, sets mode 0o600.
    Overwrites any existing credentials file — callers should
    consider whether that's the desired behavior for their flow
    (setup: yes, overwrite; other cases would need their own guard).

    Args:
        api_key: The bearer token to persist. Non-empty string.
        home: If provided, treat as the user's home directory (tests
            supply `tmp_path` here). Defaults to `Path.home()`.

    Returns:
        The path the credentials were written to.
    """
    if not isinstance(api_key, str) or not api_key:
        raise ValueError("api_key must be a non-empty string")

    path = credentials_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {"api_key": api_key}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    # POSIX: owner-only permissions for a file holding a bearer token.
    # Skipped on Windows because chmod semantics differ (Windows uses
    # ACLs; NTFS's default per-user profile isolation is our baseline).
    if sys.platform != "win32":
        os.chmod(path, 0o600)

    return path


def read_credentials(home: Optional[Path] = None) -> Optional[dict]:
    """Read the machine-scoped credentials file.

    Fail-closed on any error: missing file, unreadable file, malformed
    JSON, non-object JSON root all return None. Never raises for
    expected error modes.

    Returns:
        The parsed credentials dict on success (currently
        `{"api_key": "..."}`), or None on any failure mode. Callers
        check for None + use `.get("api_key")` for the token.
    """
    path = credentials_path(home)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def remove_credentials(home: Optional[Path] = None) -> bool:
    """Delete the machine-scoped credentials file if present.

    Returns:
        True if a file was actually deleted; False if the file was
        already absent (no-op). Does NOT delete the parent directory
        even if it becomes empty — that could hold other Enterprise
        machine-scoped state in future.
    """
    path = credentials_path(home)
    if not path.exists():
        return False
    path.unlink()
    return True
