"""Vendor transcript discovery — Claude Code + Codex CLI + Gemini CLI.

Walks vendor transcript stores on the local machine and produces a
uniform ``DiscoveredTranscript`` record per session. The CLI ingest
command (``gator-enterprise transcripts pull``) consumes these to
upload transcripts to the Enterprise server.

Design reference: 2026-08-08 transcripts-first MVP plan §10 step 2
(Claude-first per plan D6); Codex adapter added in audit-surface
Phase 3 (2026-08-15); Gemini adapter added in audit-surface Phase 4
(2026-08-15) with the Migration 011 ``session_qualifier`` contract for
Gemini's duplicate-raw-ID-across-files pathology.

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

import hashlib
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
    # Fatal-parse marker (Phase 2 hardening, 2026-08-14): True when the
    # file itself is unreadable (OSError) — record propagates the error
    # so the CLI can skip-with-diagnostic instead of attempting to upload
    # a file it never actually read. Non-fatal parse issues (e.g. missing
    # sessionId, fell back to filename stem) keep unreadable=False because
    # the file is still usable evidence.
    unreadable: bool = False
    # Duplicate-raw-ID disambiguator (Migration 011, Phase 4 Gemini
    # adapter): 16-hex SHA-256 of the source path for Gemini records,
    # "" for every other vendor. Flows into the ingest payload's
    # session_qualifier field so duplicate-raw-ID transcripts coexist
    # as distinct rows + distinct blob keys server-side.
    session_qualifier: str = ""
    # Populated at upload time — sha256 of raw content, chosen encoding.
    extras: dict = field(default_factory=dict)


def _default_claude_root() -> Path:
    """~/.claude/projects — override with $CLAUDE_TRANSCRIPTS_ROOT for tests."""
    override = os.environ.get("CLAUDE_TRANSCRIPTS_ROOT")
    if override:
        return Path(override)
    return Path(os.path.expanduser("~/.claude/projects"))


def _default_codex_root() -> Path:
    """~/.codex/sessions — override with $CODEX_TRANSCRIPTS_ROOT for tests.

    Codex CLI (OpenAI) stores rollout JSONL files under a
    ``YYYY/MM/DD/rollout-<timestamp>-<uuid>.jsonl`` tree — a per-day
    directory hierarchy, unlike Claude's flat ``projects/<hash>/`` layout.
    """
    override = os.environ.get("CODEX_TRANSCRIPTS_ROOT")
    if override:
        return Path(override)
    return Path(os.path.expanduser("~/.codex/sessions"))


def claude_root_path() -> Path:
    """Public accessor for the Claude discovery root (Phase 2 hardening).

    CLI callers use this to check root existence before running discovery,
    so a missing `~/.claude/projects/` surfaces as an informative operator
    message instead of a silent zero-transcripts-discovered pull.
    """
    return _default_claude_root()


def codex_root_path() -> Path:
    """Public accessor for the Codex discovery root (Phase 3 addition).

    Parallel to ``claude_root_path()`` — CLI's Codex-root-missing warning
    at `_handle_pull` reaches for this so the warned path matches the path
    discovery will actually walk.
    """
    return _default_codex_root()


def _default_gemini_root() -> Path:
    """~/.gemini/tmp — override with $GEMINI_TRANSCRIPTS_ROOT for tests.

    Gemini CLI stores one JSON file per session (NOT JSONL) under a
    per-project tree: ``tmp/<project>/chats/session-<timestamp>-<uuid>.json``.
    The sibling ``~/.gemini/projects.json`` maps workspace paths to
    project slugs — read via ``_gemini_projects_file()`` for workspace
    hints.
    """
    override = os.environ.get("GEMINI_TRANSCRIPTS_ROOT")
    if override:
        return Path(override)
    return Path(os.path.expanduser("~/.gemini/tmp"))


def gemini_root_path() -> Path:
    """Public accessor for the Gemini discovery root (Phase 4 addition).

    Parallel to ``claude_root_path()`` / ``codex_root_path()``.
    """
    return _default_gemini_root()


def _gemini_projects_file(root: Path) -> Path:
    """Path of Gemini's ``projects.json`` for a given discovery root.

    Lives NEXT TO the ``tmp/`` root (``~/.gemini/projects.json`` in the
    default layout), so a ``GEMINI_TRANSCRIPTS_ROOT`` override keeps the
    pair co-located: ``<override>/../projects.json``.
    """
    return root.parent / "projects.json"


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
        result.unreadable = True
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
# Codex CLI (OpenAI) — Phase 3 (2026-08-15)
# ------------------------------------------------------------------
#
# Format reference (from the retired base-Gator extract-codex-sessions.py
# module, deleted 2026-08-13 in Commit E `d54d899` per non-Enterprise
# session cleanup plan; git-show'd from history at Phase 3 draft time):
#
#     ~/.codex/sessions/YYYY/MM/DD/rollout-<ts>-<uuid>.jsonl
#
# JSONL event types:
#   session_meta   — first event; payload has {id, cwd, cli_version,
#                    model_provider, git: {commit_hash, branch}}
#   turn_context   — mid-session; payload has {turn_id, cwd, model,
#                    approval_policy, sandbox_policy}
#   response_item  — user/assistant/tool turns; payload has {role, type,
#                    content: [{type, text}]}
#   event_msg      — task lifecycle {type: task_started|task_complete}
#
# Metadata extraction: session_id from session_meta.payload.id (first-
# available wins, exactly like Claude's sessionId); workspace_hint from
# session_meta.payload.cwd; model from turn_context.payload.model;
# started_at/ended_at from min/max of top-level `timestamp` across all
# events; turn_count = count of response_item events with role in
# (user, assistant).


def _parse_codex_jsonl_metadata(path: Path) -> DiscoveredTranscript:
    """Read a Codex CLI transcript file and extract session metadata.

    Parallel to `_parse_jsonl_metadata` (the Claude parser) but uses
    Codex's session_meta/turn_context/response_item event shape rather
    than Claude's flat per-event fields. Streams line-by-line — Codex
    sessions can be many MB. Stops early once every field of interest
    is populated (session_id, model, started_at, workspace); continues
    only to update ended_at + turn_count.
    """
    result = DiscoveredTranscript(
        vendor="openai",
        vendor_session_id="",
        source_path=str(path),
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
                    # abandon the whole file. Matches Claude parser.
                    continue

                # Timestamp: top-level field on every event.
                ts = _parse_iso_z(event.get("timestamp"))
                if ts is not None:
                    if started_at is None or ts < started_at:
                        started_at = ts
                    if ended_at is None or ts > ended_at:
                        ended_at = ts

                msg_type = event.get("type")
                payload = event.get("payload") or {}
                if not isinstance(payload, dict):
                    payload = {}

                if msg_type == "session_meta":
                    if session_id is None:
                        sid = payload.get("id")
                        if isinstance(sid, str) and sid:
                            session_id = sid
                    if workspace is None:
                        cwd = payload.get("cwd")
                        if isinstance(cwd, str) and cwd:
                            workspace = cwd
                    continue

                if msg_type == "turn_context":
                    if model is None:
                        m = payload.get("model")
                        if isinstance(m, str) and m:
                            model = m
                    # cwd on turn_context can override initial session_meta
                    # cwd if the operator cd'd mid-session — take the
                    # session_meta value as authoritative (initial workspace)
                    # unless still None.
                    if workspace is None:
                        cwd = payload.get("cwd")
                        if isinstance(cwd, str) and cwd:
                            workspace = cwd
                    continue

                if msg_type == "response_item":
                    role = payload.get("role")
                    if role in ("user", "assistant"):
                        turn_count += 1
                    continue

                # event_msg + any unknown type: ignore for metadata
                # extraction (they don't carry session identity).
    except OSError as e:
        result.parse_error = f"read failed: {e}"
        result.unreadable = True
        return result

    if session_id is None:
        # Fall back to the UUID chunk of the filename. Codex filenames
        # are `rollout-<ISO-timestamp>-<uuid>.jsonl` — last hyphen-
        # separated segment before `.jsonl` is the UUID.
        stem = path.stem  # e.g. "rollout-2026-05-28T08-33-48-abc123-uuid"
        parts = stem.split("-")
        session_id = parts[-1] if len(parts) > 1 else stem
        result.parse_error = "no session_meta.id in file; fell back to filename UUID"

    result.vendor_session_id = session_id
    result.workspace_hint = workspace
    result.model = model
    result.started_at = started_at
    result.ended_at = ended_at
    result.turn_count = turn_count
    return result


def discover_codex_transcripts(
    root: Path | None = None,
    *,
    since: datetime | None = None,
) -> Iterator[DiscoveredTranscript]:
    """Yield every Codex CLI transcript on the local machine.

    Recursively walks ``~/.codex/sessions/YYYY/MM/DD/`` for files matching
    ``rollout-*.jsonl``. Sorted by path (which orders by date + timestamp
    naturally because Codex filenames start with the ISO timestamp).

    ``since`` filters by ``ended_at`` (or ``started_at`` if end is missing)
    — sessions entirely before ``since`` are skipped. Sessions with no
    parseable timestamps are ALWAYS yielded regardless of ``since``,
    matching Claude's behavior (surfaces parse failures to the operator).
    """
    root = root or _default_codex_root()
    if not root.exists() or not root.is_dir():
        return
    for entry in sorted(root.rglob("rollout-*.jsonl")):
        if not entry.is_file():
            continue
        record = _parse_codex_jsonl_metadata(entry)
        if since:
            effective = record.ended_at or record.started_at
            if effective and effective < since:
                continue
        yield record


def _gemini_session_qualifier(path: Path) -> str:
    """16-hex SHA-256 of the source path — the duplicate-raw-ID key.

    Gemini is the only known vendor whose transcript storage can put
    the same internal ``sessionId`` in two DIFFERENT files. Base
    Gator's retired archaeology handled this in
    ``gator-session-common.py::make_row_key`` by hashing
    ``session_id|source_path``; here the session id is already its own
    column server-side (Migration 011 widened uniqueness), so the
    qualifier hashes the source path alone.
    """
    return hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]


def _parse_gemini_json_metadata(
    path: Path,
    projects_map: dict[str, str] | None = None,
) -> DiscoveredTranscript:
    """Read a Gemini CLI session file and extract session metadata.

    Unlike Claude/Codex (JSONL, streamed line-by-line), a Gemini
    session is ONE JSON document:

        {sessionId, projectHash, startTime, lastUpdated,
         messages: [{type: user|gemini|info|error, content, model,
                     tokens, ...}], kind}

    so the whole file is parsed in one ``json.load``. Session identity
    is the internal ``sessionId`` (canonical — the filename UUID can
    differ); fallback to the filename stem with a ``parse_error`` note,
    matching the Claude/Codex degraded-parse contract. A whole-file
    JSON parse failure is likewise degraded-parse (the raw bytes are
    still evidence), NOT ``unreadable`` — only an OSError sets that.

    ``projects_map`` is the parsed ``projects.json`` mapping
    ``{workspace_path: project_slug}``; the workspace hint is the
    reverse lookup of the session's project directory name, falling
    back to the directory name itself (basename-compatible with the
    server's `strong_machine_repo_time` matcher either way).
    """
    result = DiscoveredTranscript(
        vendor="google",
        vendor_session_id="",
        source_path=str(path),
        session_qualifier=_gemini_session_qualifier(path),
    )
    try:
        result.file_size_bytes = path.stat().st_size
    except OSError:
        pass

    project_dirname = path.parent.parent.name
    workspace: str | None = None
    for ws_path, slug in (projects_map or {}).items():
        if slug == project_dirname:
            workspace = ws_path
            break
    result.workspace_hint = workspace or project_dirname

    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
    except OSError as e:
        result.parse_error = f"read failed: {e}"
        result.unreadable = True
        return result
    except (ValueError, json.JSONDecodeError):
        result.vendor_session_id = path.stem
        result.parse_error = "malformed JSON; fell back to filename stem"
        return result

    if not isinstance(data, dict):
        result.vendor_session_id = path.stem
        result.parse_error = "non-object JSON root; fell back to filename stem"
        return result

    session_id = data.get("sessionId")
    if isinstance(session_id, str) and session_id:
        result.vendor_session_id = session_id
    else:
        result.vendor_session_id = path.stem
        result.parse_error = "no sessionId in file; fell back to filename stem"

    result.started_at = _parse_iso_z(data.get("startTime"))
    result.ended_at = _parse_iso_z(data.get("lastUpdated"))

    turn_count = 0
    model: str | None = None
    messages = data.get("messages")
    if isinstance(messages, list):
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            if msg.get("type") in ("user", "gemini"):
                turn_count += 1
            if model is None and msg.get("type") == "gemini":
                m = msg.get("model")
                if isinstance(m, str) and m:
                    model = m
    result.turn_count = turn_count
    result.model = model
    return result


def discover_gemini_transcripts(
    root: Path | None = None,
    *,
    since: datetime | None = None,
) -> Iterator[DiscoveredTranscript]:
    """Yield every Gemini CLI transcript on the local machine.

    Walks ``<root>/<project>/chats/session-*.json`` (default root
    ``~/.gemini/tmp/``), sorted by path for deterministic ordering.

    ``since`` filters by ``ended_at`` (or ``started_at`` if end is
    missing) — sessions entirely before ``since`` are skipped. Sessions
    with no parseable timestamps are ALWAYS yielded, matching
    Claude/Codex behavior (surfaces parse failures to the operator).
    """
    root = root or _default_gemini_root()
    if not root.exists() or not root.is_dir():
        return
    projects_map: dict[str, str] = {}
    projects_file = _gemini_projects_file(root)
    try:
        raw_map = json.loads(projects_file.read_text(encoding="utf-8"))
        candidate = raw_map.get("projects", {})
        if isinstance(candidate, dict):
            projects_map = {
                k: v for k, v in candidate.items() if isinstance(v, str)
            }
    except (OSError, ValueError, json.JSONDecodeError):
        pass  # hints degrade to project dir names; not an error
    for entry in sorted(root.glob("*/chats/session-*.json")):
        if not entry.is_file():
            continue
        record = _parse_gemini_json_metadata(entry, projects_map)
        if since:
            effective = record.ended_at or record.started_at
            if effective and effective < since:
                continue
        yield record


# ------------------------------------------------------------------
# Vendor dispatch
# ------------------------------------------------------------------

_VENDOR_HANDLERS = {
    "claude": discover_claude_transcripts,
    "codex": discover_codex_transcripts,
    "gemini": discover_gemini_transcripts,
}

# Extra vendor slugs that map to the same handler. `transcripts pull`
# accepts both the vendor's product name (claude, codex, gemini) and
# the canonical Enterprise vendor slug (anthropic, openai, google) as
# inputs. The stored vendor slug on `transcript_sessions.vendor` is the
# canonical form (anthropic for Claude, openai for Codex, google for
# Gemini) — see the Enterprise TranscriptSession model docstring.
_VENDOR_ALIASES = {
    "anthropic": "claude",
    "openai": "codex",
    "google": "gemini",
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
