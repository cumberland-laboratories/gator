"""
gator_diagnostics.py — Bounded, machine-local log for session-hook events.

Vendor SessionStart hooks (Claude / Codex / Gemini) invoke `gator-session-open.py`
and `gator-session-start.py` under a design contract that forbids stdout output
and forces `sys.exit(0)` on every code path — so vendor sessions never block.
That contract also makes fleet-wide silent regressions undetectable: when a
session hook degrades or fails, the operator has no evidence to look at until
they manually invoke the script.

This module provides a single append-only log at `.gator/diagnostics/hooks.log`
for non-happy-path events, bounded to a fixed line count so it never grows
without limit. Every function is wrapped in a broad try/except — a log-write
failure MUST NOT change the caller's exit code or leak stdout.

The parent directory `.gator/diagnostics/` is gitignored by
`ensure_repo_gitignore()` in `gatorize.py`.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

# Bounded log: keep the most recent N lines. On write, if the file already
# holds >= MAX_LINES entries, drop the oldest ones so the new entry lands as
# entry MAX_LINES. Simple size cap; no timestamp-based rotation.
MAX_LINES = 200


def _iso_utc_now() -> str:
    """UTC timestamp in `YYYY-MM-DDTHH:MM:SSZ` form. Best-effort; no exceptions."""
    try:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return "unknown-time"


def log_hook_event(
    gator_dir: Path,
    script_name: str,
    status: str,
    detail: str = "",
) -> None:
    """Append one bounded line to `.gator/diagnostics/hooks.log`.

    Args:
        gator_dir: the repo's `.gator/` directory (Path).
        script_name: short identifier of the calling script (e.g. `gator-session-open`).
        status: uppercase status token (`FAIL`, `DEGRADED`, `UNAVAILABLE`, `ERROR`, `SKIP`).
        detail: free-text detail — kept on one line (embedded newlines are stripped).

    Guarantees:
        - Never raises. All errors swallowed.
        - Never writes to stdout. Never prints anything.
        - No-op if `gator_dir` is not a directory or the append fails.
        - Bounded: the log is truncated to the most recent MAX_LINES entries
          if the write would push it over the cap.
    """
    try:
        diag_dir = gator_dir / "diagnostics"
        diag_dir.mkdir(parents=True, exist_ok=True)
        log_path = diag_dir / "hooks.log"

        # Compose a single line. Strip newlines from `detail` so a
        # malformed detail can never break the one-line-per-event contract.
        one_line_detail = (
            (detail or "")
            .replace("\r", " ")
            .replace("\n", " ")
            .strip()
        )
        try:
            cwd = str(Path.cwd())
        except Exception:
            cwd = "unknown-cwd"
        line = (
            f"{_iso_utc_now()} {script_name} {status.upper()} "
            f"{one_line_detail} cwd={cwd}\n"
        )

        # Bound the file: if it already holds MAX_LINES or more, read what's
        # there, keep the tail (MAX_LINES - 1), append the new line, and
        # rewrite. This is O(N) per write but N is tiny (<= 200 lines), and
        # rotation runs only when the cap has been reached — cheap enough.
        existing = []
        if log_path.is_file():
            try:
                existing = log_path.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
            except Exception:
                existing = []

        if len(existing) >= MAX_LINES:
            keep = existing[-(MAX_LINES - 1):]
            try:
                log_path.write_text(
                    "\n".join(keep) + "\n" + line,
                    encoding="utf-8",
                )
                return
            except Exception:
                return

        # Under the cap — cheap append.
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            return
    except Exception:
        # Absolute belt-and-suspenders. Session hooks must always exit 0;
        # a diagnostic-log crash must not surface anywhere.
        return


# Statuses returned by `gator-init.ensure_git_hooks()` that DO warrant a log
# entry when session-open captures the return dict. Kept as a frozenset here
# so callers don't need to hardcode the vocabulary — if `ensure_git_hooks`
# grows a new non-happy-path status, add it here in the same commit.
NON_HAPPY_STATUSES = frozenset({"degraded", "unavailable", "error"})
