"""Vendor transcript discovery — MVP: Claude Code only.

Walks vendor transcript stores on the local machine and produces a
uniform ``DiscoveredTranscript`` record per session. The CLI ingest
command (``gator-enterprise transcripts pull``) consumes these to
upload transcripts to the Enterprise server.

Design reference: 2026-08-08 transcripts-first MVP plan §10 step 2.
Vendor-first target: Claude Code (per plan D6).

Claude Code transcript layout (verified 2026-08-08 on this machine):

    ~/.claude/projects/<project-hash>/<session-uuid>.jsonl

Each ``.jsonl`` is one session; ``<project-hash>`` is Claude's
mangled encoding of the workspace path (e.g.
``C--Users-curator-code2-gator`` for ``C:\\Users\\curator\\code2\\gator``).

The JSONL format is line-per-event, event types include:

  - ``mode`` / ``permission-mode`` — session-scoped metadata (bookkeeping)
  - ``user`` / ``assistant`` — turns, carry timestamp + cwd + gitBranch
                                + version; assistant carries model
  - ``system`` — synthesized notices (isMeta = true)
  - ``file-history-snapshot`` / ``file-history-delta`` — file state
  - ``attachment`` — user-attached files
  - ``ai-title`` / ``last-prompt`` — bookkeeping written at end

The parser only touches the fields needed for session identity and
linkage: ``sessionId``, ``timestamp``, ``cwd``, ``message.model``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


@dataclass
class DiscoveredTranscript:
    """One Claude Code / vendor transcript on disk, with parsed metadata."""

    vendor: str
    vendor_session_id: str
    source_path: str
    workspace_hint: str | None = None
    model: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    turn_count: int = 0
    file_size_bytes: int = 0
    project_hash: str | None = None
    parse_error: str | None = None
    # Populated at upload time — sha256 of raw content, chosen encoding.
    extras: dict = field(default_factory=dict)


def _default_claude_root() -> Path:
    """~/.claude/projects — override with $CLAUDE_TRANSCRIPTS_ROOT for tests."""
    override = os.environ.get("CLAUDE_TRANSCRIPTS_ROOT")
    if override:
        return Path(override)
    return Path(os.path.expanduser("~/.claude/projects"))


def _parse_iso_z(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
        dt = datetime.fromisoformat(normalized)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _parse_jsonl_metadata(path: Path) -> DiscoveredTranscript:
    """Read a Claude Code transcript file and extract session metadata.

    Reads line-by-line rather than loading the whole file — some
    sessions are hundreds of MB. Stops early once every field of
    interest is populated (session_id, model, started_at, workspace).
    Continues past that only to update ``ended_at`` + ``turn_count``.
    """
    result = DiscoveredTranscript(
        vendor="anthropic",
        vendor_session_id="",
        source_path=str(path),
        project_hash=path.parent.name,
    )
    try:
        result.file_size_bytes = path.stat().st_size
    except OSError:
        pass

    session_id: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    model: str | None = None
    workspace: str | None = None
    turn_count = 0

    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    event = json.loads(stripped)
                except (ValueError, json.JSONDecodeError):
                    # Malformed line — skip individually rather than
                    # abandon the whole file.
                    continue

                sid = event.get("sessionId")
                if sid and session_id is None:
                    session_id = sid

                ts = _parse_iso_z(event.get("timestamp"))
                if ts is not None:
                    if started_at is None or ts < started_at:
                        started_at = ts
                    if ended_at is None or ts > ended_at:
                        ended_at = ts

                if workspace is None:
                    cwd = event.get("cwd")
                    if isinstance(cwd, str) and cwd:
                        workspace = cwd

                if model is None:
                    msg = event.get("message")
                    if isinstance(msg, dict):
                        m = msg.get("model")
                        if isinstance(m, str) and m and m != "<synthetic>":
                            model = m

                event_type = event.get("type")
                if event_type in ("user", "assistant"):
                    turn_count += 1
    except OSError as e:
        result.parse_error = f"read failed: {e}"
        return result

    if session_id is None:
        # Fall back to the file basename (Claude uses session UUID
        # as filename) — but flag it so the caller knows this session
        # is degraded metadata.
        session_id = path.stem
        result.parse_error = "no sessionId in file; fell back to filename stem"

    result.vendor_session_id = session_id
    result.workspace_hint = workspace
    result.model = model
    result.started_at = started_at
    result.ended_at = ended_at
    result.turn_count = turn_count
    return result


def discover_claude_transcripts(
    root: Path | None = None,
    *,
    since: datetime | None = None,
    project_hash_filter: str | None = None,
) -> Iterator[DiscoveredTranscript]:
    """Yield every Claude Code transcript on the local machine.

    ``since`` filters by ``ended_at`` (or ``started_at`` if end is
    missing) — sessions entirely before ``since`` are skipped. Sessions
    with no parseable timestamps are ALWAYS yielded regardless of
    ``since`` (surfacing them lets the operator see parse failures).
    """
    root = root or _default_claude_root()
    if not root.exists() or not root.is_dir():
        return
    for project_dir in sorted(root.iterdir()):
        if not project_dir.is_dir():
            continue
        if project_hash_filter and project_dir.name != project_hash_filter:
            continue
        for entry in sorted(project_dir.iterdir()):
            if not entry.is_file() or entry.suffix != ".jsonl":
                continue
            record = _parse_jsonl_metadata(entry)
            if since:
                effective = record.ended_at or record.started_at
                if effective and effective < since:
                    continue
            yield record


# ------------------------------------------------------------------
# Vendor dispatch (post-MVP: codex, gemini)
# ------------------------------------------------------------------

_VENDOR_HANDLERS = {
    "claude": discover_claude_transcripts,
}

# Extra vendor slugs that map to the same handler (transcripts pull
# accepts both "claude" and "anthropic" as vendor filter; the stored
# vendor slug in Enterprise is "anthropic" per the transcripts_first
# plan §5).
_VENDOR_ALIASES = {
    "anthropic": "claude",
}


def discover(
    vendor: str,
    *,
    since: datetime | None = None,
    root: Path | None = None,
) -> Iterator[DiscoveredTranscript]:
    """Vendor-dispatching discovery. Raises ValueError for unknown vendors."""
    key = _VENDOR_ALIASES.get(vendor, vendor)
    handler = _VENDOR_HANDLERS.get(key)
    if handler is None:
        raise ValueError(
            f"Unsupported vendor: {vendor!r} "
            f"(supported: {sorted(set(_VENDOR_HANDLERS) | set(_VENDOR_ALIASES))})"
        )
    return handler(root=root, since=since)
