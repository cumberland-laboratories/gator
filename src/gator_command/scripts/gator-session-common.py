#!/usr/bin/env python3
"""
gator-session-common.py — Shared utilities for session archaeology scripts.

Contains the machine identity resolver, redaction engine, and
intelligence extraction logic used by all vendor-specific extraction
scripts (Claude, Codex, Gemini, Cursor, future).

This module is the foundation of the Gator Session Schema — the
normalized format all vendors map to.

Import:
    from gator_session_common import get_machine_identity, redact, extract_intelligence

@reads: ~/.gator/machine-id
@does-not-own: vendor-specific extraction (each script handles its own format)
"""

import os
import platform
import re
from pathlib import Path


# ---------------------------------------------------------------------------
# Machine Identity
# ---------------------------------------------------------------------------

GATOR_USER_DIR = Path.home() / ".gator"
MACHINE_ID_FILE = GATOR_USER_DIR / "machine-id"


def get_machine_identity():
    """Get stable machine identity for session summaries.

    Returns dict with id, hostname, label. Creates machine-id file
    on first call if it doesn't exist.

    Uses gator-machine-id.py's storage format for compatibility.
    """
    if MACHINE_ID_FILE.exists():
        data = {}
        try:
            for line in MACHINE_ID_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if ":" in line and not line.startswith("#"):
                    key, _, value = line.partition(":")
                    data[key.strip()] = value.strip()
        except OSError:
            pass

        if "id" in data:
            return {
                "id": data["id"],
                "hostname": data.get("hostname", platform.node()),
                "label": data.get("label", data.get("hostname", platform.node())),
            }

    # No machine-id file — create one
    import uuid
    from datetime import date

    GATOR_USER_DIR.mkdir(parents=True, exist_ok=True)
    mid = str(uuid.uuid4())
    hostname = platform.node()

    lines = [
        f"id: {mid}",
        f"hostname: {hostname}",
        f"label: {hostname}",
        f"created: {date.today()}",
    ]
    MACHINE_ID_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {"id": mid, "hostname": hostname, "label": hostname}


# ---------------------------------------------------------------------------
# Redaction Engine
# ---------------------------------------------------------------------------

# Patterns applied to ALL content (summaries and transcripts)
REDACT_ALWAYS = [
    # API keys
    (r'sk-[A-Za-z0-9]{20,}', '[REDACTED-API-KEY]'),
    (r'AKIA[A-Z0-9]{16}', '[REDACTED-AWS-KEY]'),
    # Passwords in assignments
    (r'(?i)(password|passwd|pwd)\s*=\s*["\'][^"\']+["\']',
     r'\1 = "[REDACTED]"'),
    # API key/secret assignments
    (r'(?i)(api[_-]?key|secret[_-]?key|access[_-]?token)\s*=\s*["\'][A-Za-z0-9+/=_-]{16,}["\']',
     r'\1 = "[REDACTED]"'),
    # Private key blocks
    (r'-----BEGIN[A-Z ]*PRIVATE KEY-----[\s\S]*?-----END[A-Z ]*PRIVATE KEY-----',
     '[REDACTED-PRIVATE-KEY]'),
    # Bearer tokens
    (r'(?i)Bearer\s+[A-Za-z0-9_.-]{20,}',
     'Bearer [REDACTED-TOKEN]'),
    # Connection strings with embedded passwords
    (r'(?i)(mysql|postgres|mongodb|redis)://[^:]+:[^@]+@',
     r'\1://[REDACTED]@'),
]

# Patterns applied only to SUMMARIES (transcripts keep the original)
REDACT_SUMMARY = [
    # Full user paths → relative
    (r'[A-Z]:\\Users\\[^\\]+\\', '~/'),
    (r'/home/[^/]+/', '~/'),
    (r'/Users/[^/]+/', '~/'),
]


def redact(text, summary_mode=False):
    """Apply redaction patterns to text.

    Args:
        text: Content to redact
        summary_mode: If True, also apply summary-only redactions
                      (path anonymization)

    Always redacts: API keys, passwords, private keys, tokens,
    connection strings.

    Summary-only redacts: full user paths → ~/
    """
    if not text:
        return text

    # Always redact secrets
    for pattern, replacement in REDACT_ALWAYS:
        text = re.sub(pattern, replacement, text)

    # Summary-only redactions
    if summary_mode:
        for pattern, replacement in REDACT_SUMMARY:
            text = re.sub(pattern, replacement, text)

    return text


# ---------------------------------------------------------------------------
# Intelligence Extraction (shared across vendors)
# ---------------------------------------------------------------------------

# Decision-language signals in Architect messages
DECISION_SIGNALS = [
    "let's ", "let us ", "we should ", "go with ",
    "approved", "yes, ", "do it", "proceed",
    "i want ", "i think ", "i'd like ",
    "decision:", "decided:",
]


def extract_intelligence(turns):
    """Extract decisions, files changed, charters updated, and session goal.

    Works with the normalized turn format (role, content, tool_calls).
    Vendor-agnostic — all extraction scripts produce turns in this shape.

    Args:
        turns: list of dicts with role, content, tool_calls, timestamp

    Returns dict with goal, decisions, files_changed, charters_updated.
    """
    files_changed = set()
    charters_updated = set()
    decisions = []
    goal = ""

    for t in turns:
        raw_content = t.get("content", "")
        content = raw_content.strip() if isinstance(raw_content, str) else ""
        role = t.get("role", "")

        # Goal = first substantive Architect message
        if role == "user" and content and not goal and len(content) > 10:
            goal = redact(content[:200], summary_mode=True)

        # Files from content (backtick-quoted or double-quoted paths)
        if content:
            for match in re.finditer(r'[`"]([a-zA-Z0-9_./-]+\.[a-zA-Z]{1,10})[`"]', content):
                filepath = match.group(1)
                if ".gator/charters/" in filepath:
                    charters_updated.add(filepath.split("/")[-1])
                elif not filepath.startswith("http"):
                    files_changed.add(filepath)

        # Files from tool calls
        for tc in t.get("tool_calls", []):
            tool = tc.get("tool", "")
            if tool:
                files_changed.add(f"[{tool} operation]")

        # Decisions from Architect messages
        if role == "user" and content:
            lower = content.lower()
            if any(sig in lower for sig in DECISION_SIGNALS):
                decisions.append({
                    "timestamp": t.get("timestamp", ""),
                    "text": redact(content[:120], summary_mode=True),
                })

    return {
        "goal": goal,
        "files_changed": sorted(files_changed)[:20],
        "charters_updated": sorted(charters_updated),
        "decisions": decisions[:10],
    }


# ---------------------------------------------------------------------------
# Session Identity (composite key, no collisions)
# ---------------------------------------------------------------------------

def make_row_key(metadata):
    """Generate the canonical unique row key for a session.

    Hashes session_id + source_path to handle the real case where
    two different files share the same internal session ID (Gemini).
    This key is used everywhere: transcript paths, spool filenames,
    export state, manifest rows.
    """
    import hashlib
    session_id = metadata.get("session_id", "unknown")
    source_path = metadata.get("source_path", "")
    key = f"{session_id}|{source_path}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def make_transcript_path(metadata):
    """Generate a collision-free transcript path.

    Uses the row_key (hash of session_id + source_path) to guarantee
    uniqueness even for Gemini's genuine duplicate session IDs.
    Format: <date>-<repo>-<vendor>-<row_key>.md
    """
    date = metadata.get("start", "")[:10]
    repo = metadata.get("repo", "unknown")
    vendor = metadata.get("vendor", "unknown")
    rk = make_row_key(metadata)
    transcript_dir = GATOR_USER_DIR / "session-transcripts"
    return transcript_dir / f"{date}-{repo}-{vendor}-{rk}.md"


# ---------------------------------------------------------------------------
# Summary Formatting (shared across vendors — canonical implementation)
# ---------------------------------------------------------------------------

def format_summary_frontmatter(metadata, machine):
    """Generate standardized YAML frontmatter for session summaries.

    This is the ONLY implementation. Vendor extractors must call this,
    not hand-roll their own frontmatter.
    """
    transcript_path = make_transcript_path(metadata)

    return [
        f"schema: gator-session-summary-v1",
        f"session-id: {metadata.get('session_id', '')}",
        f"date: {metadata.get('start', '')[:10]}",
        f"start: {metadata.get('start', '')}",
        f"end: {metadata.get('end', '')}",
        f"repo: {metadata.get('repo', 'unknown')}",
        f"architect: {metadata.get('architect', metadata.get('pi', 'unknown'))}",
        f"agent: {metadata.get('agent', 'unknown')}",
        f"vendor: {metadata.get('vendor', 'unknown')}",
        f"machine-id: {machine.get('id', '')}",
        f"machine-label: {machine.get('label', '')}",
        f"transcript: {transcript_path}",
        f"turns: {metadata.get('user_turns', 0)} user, {metadata.get('assistant_turns', 0)} assistant",
        f"tools: {', '.join(metadata.get('tools_used', []))}",
        f"branch: {metadata.get('branch', 'unknown')}",
    ]


def format_summary_markdown(turns, metadata):
    """Generate complete summary markdown (frontmatter + body).

    This is the canonical summary formatter. All vendor extractors
    should call this instead of implementing their own.
    """
    machine = get_machine_identity()
    intelligence = extract_intelligence(turns)
    transcript_path = make_transcript_path(metadata)

    lines = []

    # Frontmatter
    lines.append("---")
    lines.extend(format_summary_frontmatter(metadata, machine))
    lines.append("---")
    lines.append("")

    # Body
    lines.append(f"# Session Summary — {metadata.get('start', '')[:10]} {metadata.get('repo', 'unknown')} ({metadata.get('agent', metadata.get('vendor', ''))})")
    lines.append("")

    lines.append("## Goal")
    lines.append("")
    lines.append(intelligence["goal"] or "*No goal extracted*")
    lines.append("")

    lines.append("## Decisions")
    lines.append("")
    if intelligence["decisions"]:
        for d in intelligence["decisions"]:
            ts = d["timestamp"][:19] if d["timestamp"] else "?"
            lines.append(f"- [{ts}] {d['text']}")
    else:
        lines.append("*No decisions extracted*")
    lines.append("")

    lines.append("## Files Changed")
    lines.append("")
    if intelligence["files_changed"]:
        for f in intelligence["files_changed"]:
            lines.append(f"- {f}")
    else:
        lines.append("*No file changes extracted*")
    lines.append("")

    if intelligence["charters_updated"]:
        lines.append("## Charters Updated")
        lines.append("")
        for c in intelligence["charters_updated"]:
            lines.append(f"- {c}")
        lines.append("")

    lines.append("## Evidence Location")
    lines.append("")
    lines.append(f"- **Machine**: {machine.get('label', '?')} (`{machine.get('id', '?')}`)")
    lines.append(f"- **Transcript**: `{transcript_path}`")
    lines.append(f"- **Raw source**: vendor-specific local storage")
    lines.append("")

    return "\n".join(lines)


def format_session_summary_dict(turns, metadata):
    """Generate structured summary dict for JSON output.

    Canonical implementation — all vendors use this.
    """
    machine = get_machine_identity()
    intelligence = extract_intelligence(turns)
    transcript_path = make_transcript_path(metadata)

    return {
        "schema": "gator-session-summary-v1",
        "session_id": metadata.get("session_id", ""),
        "row_key": make_row_key(metadata),
        "date": metadata.get("start", "")[:10],
        "start": metadata.get("start", ""),
        "end": metadata.get("end", ""),
        "repo": metadata.get("repo", "unknown"),
        "architect": metadata.get("architect", metadata.get("pi", "unknown")),
        "agent": metadata.get("agent", "unknown"),
        "vendor": metadata.get("vendor", "unknown"),
        "machine_id": machine.get("id", ""),
        "machine_label": machine.get("label", ""),
        "transcript": str(transcript_path),
        "turns": metadata.get("total_turns", 0),
        "user_turns": metadata.get("user_turns", 0),
        "assistant_turns": metadata.get("assistant_turns", 0),
        "tools": metadata.get("tools_used", []),
        "branches": metadata.get("branches", [metadata.get("branch", "")]),
        "model": metadata.get("model", ""),
        "goal": intelligence["goal"],
        "decisions": intelligence["decisions"],
        "files_changed": intelligence["files_changed"],
        "charters_updated": intelligence["charters_updated"],
    }
