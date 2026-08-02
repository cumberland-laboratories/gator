#!/usr/bin/env python3
"""
gator-session-start.py — Capture vendor session identity at session start.

Called by vendor SessionStart hooks (Claude Code, Codex CLI, Gemini CLI).
All three vendors pass JSON on stdin with session metadata including a
vendor session ID. This script reads that payload and writes
.gator/active-vendor-session.json — a local-only file that the post-commit
hook reads to populate transcript_session_id in snippets.

This script MUST:
- Always exit 0 (never block the vendor session)
- Never write to stdout (vendors may interpret stdout as hook output)
- Be safe to run even if stdin is empty or malformed

@reads: stdin (JSON from vendor SessionStart hook)
@writes: .gator/active-vendor-session.json (gitignored, machine-local)
"""

import io
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def _ensure_utf8_stdio():
    """Ensure stdio uses UTF-8 encoding (needed on Windows)."""
    if sys.stdin.encoding and sys.stdin.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdin = io.TextIOWrapper(
            sys.stdin.buffer, encoding="utf-8", errors="replace"
        )
    if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace"
        )


def find_gator_dir():
    """Walk up from cwd to find .gator/."""
    d = Path.cwd().resolve()
    for _ in range(20):
        candidate = d / ".gator"
        if candidate.is_dir():
            return candidate
        parent = d.parent
        if parent == d:
            break
        d = parent
    return None


# --- Vendor detection and field extraction ---

VENDOR_HINTS = {
    "anthropic": ["claude", "anthropic"],
    "openai": ["codex", "openai", "gpt"],
    "google": ["gemini", "google"],
}


VENDOR_CANONICAL = {
    "anthropic": "anthropic",
    "claude": "anthropic",
    "openai": "openai",
    "codex": "openai",
    "google": "google",
    "gemini": "google",
}


def detect_vendor(payload):
    """Detect vendor from payload fields. Returns canonical vendor name.

    Canonical names: 'anthropic', 'openai', 'google', 'unknown'.
    Normalizes common aliases (e.g., 'claude' -> 'anthropic').
    """
    # Check for explicit vendor field (flat or nested)
    raw_vendor = _get_str(payload, "vendor", "provider")
    if raw_vendor:
        canonical = VENDOR_CANONICAL.get(raw_vendor.lower())
        if canonical:
            return canonical
        return raw_vendor.lower()

    # Infer from model name (flat or nested)
    model = (_get_str(payload, "model", "model_name") or "").lower()
    for vendor, hints in VENDOR_HINTS.items():
        for hint in hints:
            if hint in model:
                return vendor

    # Env var hint (Gemini exposes GEMINI_SESSION_ID)
    if os.environ.get("GEMINI_SESSION_ID"):
        return "google"

    return "unknown"


def _get_str(payload, *keys):
    """Get first non-empty string value from payload by trying multiple keys.

    Handles both flat payloads and one level of nesting (checks top-level
    and common nested containers like 'data', 'payload', 'metadata').
    """
    containers = [payload]
    for nested_key in ("data", "payload", "metadata", "hookSpecificOutput"):
        nested = payload.get(nested_key)
        if isinstance(nested, dict):
            containers.append(nested)

    for container in containers:
        for key in keys:
            val = container.get(key)
            if val is not None and str(val).strip() and str(val).strip().lower() != "null":
                return str(val).strip()
    return None


def extract_vendor_session_id(payload):
    """Extract vendor session ID. Returns string or None.

    Verified field locations (2026-06-21 research):
    - Claude Code: top-level 'session_id' (stdin JSON schema)
    - Codex CLI: top-level 'session_id' (codex-rs/hooks/schema/generated/session-start.command.input.schema.json)
    - Gemini CLI: top-level 'session_id' (stdin JSON) + GEMINI_SESSION_ID env var

    Payload always wins over env vars. Env vars can be stale from a
    previous session or a different vendor tool.
    """
    # Payload is the authoritative source
    sid = _get_str(payload, "session_id", "sessionId", "id")
    if sid:
        return sid

    # Env var fallback only when payload has nothing
    env_sid = os.environ.get("GEMINI_SESSION_ID") or os.environ.get("CLAUDE_SESSION_ID")
    if env_sid and env_sid.strip():
        return env_sid.strip()

    return None


def extract_model(payload):
    """Extract precise model name. Returns string or None.

    Codex provides 'model' at top level. Claude and Gemini may not include
    it in the SessionStart payload (model is known from config, not hook input).
    """
    return _get_str(payload, "model", "model_name")


def extract_transcript_path(payload):
    """Extract transcript file path. Returns string or None.

    All three vendors provide 'transcript_path' at top level when available.
    """
    return _get_str(payload, "transcript_path", "transcriptPath", "session_path")


def extract_cwd(payload):
    """Extract working directory. Returns string or None."""
    return _get_str(payload, "cwd", "working_directory", "workingDirectory")


def extract_started_at(payload):
    """Extract or generate start timestamp. Returns ISO string."""
    val = _get_str(payload, "started_at", "timestamp", "start_time", "startedAt")
    if val:
        return val
    # Default to current UTC time
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_session_file(payload):
    """Build the active-vendor-session.json content from payload.

    Returns dict if a valid session can be built, None otherwise.
    """
    vendor_session_id = extract_vendor_session_id(payload)
    if not vendor_session_id:
        return None

    return {
        "schema": "gator-active-vendor-session-v1",
        "vendor": detect_vendor(payload),
        "vendor_session_id": vendor_session_id,
        "model": extract_model(payload),
        "transcript_path": extract_transcript_path(payload),
        "started_at": extract_started_at(payload),
        "cwd": extract_cwd(payload),
        "source": "session-start-hook",
    }


def write_session_file(gator_dir, data):
    """Atomic write of active-vendor-session.json."""
    target = gator_dir / "active-vendor-session.json"
    content = json.dumps(data, indent=2) + "\n"

    # Atomic: write to temp, then replace
    fd, tmp_path = tempfile.mkstemp(
        dir=str(gator_dir), prefix=".avs-", suffix=".tmp"
    )
    closed = False
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        closed = True
        # os.replace is atomic on both Unix and Windows (same filesystem)
        os.replace(tmp_path, str(target))
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


def main():
    _ensure_utf8_stdio()

    # Read stdin (vendor hook payload)
    try:
        raw = sys.stdin.read()
    except Exception:
        # stdin not available or broken pipe — exit cleanly
        return 0

    if not raw or not raw.strip():
        return 0

    # Parse JSON defensively
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        print("gator-session-start: invalid JSON on stdin", file=sys.stderr)
        return 0

    if not isinstance(payload, dict):
        return 0

    # Build session data
    data = build_session_file(payload)
    if not data:
        # No usable session ID — exit silently
        return 0

    # Find .gator/ directory
    gator_dir = find_gator_dir()
    if not gator_dir:
        print("gator-session-start: no .gator/ found", file=sys.stderr)
        return 0

    # Write the file
    try:
        write_session_file(gator_dir, data)
    except Exception as e:
        print(f"gator-session-start: write failed: {e}", file=sys.stderr)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
