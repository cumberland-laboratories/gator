#!/usr/bin/env python3
"""
extract-gemini-sessions.py — Session archaeology for Gemini CLI.

Reads Gemini CLI's native session storage (~/.gemini/tmp/<project>/chats/),
extracts structured turn data, and produces standardized markdown
session logs matching the same format as the Claude and Codex scripts.

Storage layout:
  ~/.gemini/tmp/<project>/chats/
    session-<timestamp>-<uuid>.json   — single JSON file per session
  ~/.gemini/projects.json             — maps cwd paths to project slugs

Session JSON format:
  {sessionId, projectHash, startTime, lastUpdated, messages: [...], kind}

Message format:
  type: user|gemini|info|error
  content: [{type, text}]           — text blocks
  toolCalls: [{name, args}]         — gemini tool invocations
  model: string                     — gemini messages only
  tokens: {input, output}           — gemini messages only

Usage:
    python gator-command/scripts/extract-gemini-sessions.py --list
    python gator-command/scripts/extract-gemini-sessions.py --project learnhub
    python gator-command/scripts/extract-gemini-sessions.py --latest 3 --summary
    python gator-command/scripts/extract-gemini-sessions.py --json

@reads: ~/.gemini/tmp/*/chats/, ~/.gemini/projects.json
@writes: stdout
"""

import argparse
import glob
import io
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Shared session utilities — use gator_core.import_sibling for clean imports
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gator_core import import_sibling

_COMMON = None
def _get_common():
    global _COMMON
    if _COMMON is None:
        _COMMON = import_sibling("gator-session-common")
    return _COMMON


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GEMINI_DIR = Path.home() / ".gemini"
TMP_DIR = GEMINI_DIR / "tmp"
PROJECTS_FILE = GEMINI_DIR / "projects.json"


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def load_project_map():
    """Load project path → slug mapping from projects.json."""
    if not PROJECTS_FILE.exists():
        return {}
    try:
        data = json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
        return data.get("projects", {})
    except (json.JSONDecodeError, OSError):
        return {}


def discover_sessions():
    """Find all Gemini session JSON files.

    Returns list of {uuid, project, path, date, messages, size, modified}
    """
    if not TMP_DIR.is_dir():
        return []

    sessions = []
    pattern = str(TMP_DIR / "*" / "chats" / "session-*.json")

    for filepath in sorted(glob.glob(pattern)):
        filepath = Path(filepath)
        try:
            size = filepath.stat().st_size
            modified = datetime.fromtimestamp(filepath.stat().st_mtime)
            project = filepath.parent.parent.name

            # Read internal sessionId from JSON payload (canonical identity)
            # Falls back to filename stem if JSON can't be read
            source_file = filepath.stem
            uuid = source_file  # fallback
            try:
                with open(filepath, encoding="utf-8", errors="replace") as sf:
                    data = json.load(sf)
                    if isinstance(data, dict) and data.get("sessionId"):
                        uuid = data["sessionId"]
            except Exception:
                pass

            # Extract date from filename
            # session-2026-03-17T21-35-... → 2026-03-17
            parts = filepath.stem.split("-")
            date_str = ""
            if len(parts) >= 4:
                date_str = f"{parts[1]}-{parts[2]}-{parts[3][:2]}"

            sessions.append({
                "uuid": uuid,
                "source_file": source_file,
                "project": project,
                "path": filepath,
                "date": date_str,
                "size": size,
                "modified": modified.strftime("%Y-%m-%d %H:%M"),
            })
        except OSError:
            continue

    return sessions


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extract_session(session_path):
    """Extract structured turns from a Gemini session JSON file."""
    with open(session_path, encoding="utf-8", errors="replace") as f:
        data = json.load(f)

    session_meta = {
        "session_id": data.get("sessionId", ""),
        "start": data.get("startTime", ""),
        "end": data.get("lastUpdated", ""),
        "kind": data.get("kind", ""),
    }

    turns = []
    messages = data.get("messages", [])

    for msg in messages:
        msg_type = msg.get("type", "")
        timestamp = msg.get("timestamp", "")
        content_blocks = msg.get("content") or []

        # Extract text content
        text_parts = []
        for block in content_blocks:
            if isinstance(block, dict):
                text = block.get("text", "")
                if text:
                    text_parts.append(text)
        text_content = "\n".join(text_parts)

        # Extract tool calls
        tool_calls = []
        for tc in (msg.get("toolCalls") or []):
            if isinstance(tc, dict):
                tool_calls.append({
                    "tool": tc.get("name", "unknown"),
                    "input_keys": list(tc.get("args", {}).keys()),
                })

        # Map roles
        if msg_type == "user":
            role = "user"
        elif msg_type == "gemini":
            role = "assistant"
        elif msg_type in ("info", "error"):
            role = "system"
        else:
            role = msg_type or "unknown"

        # Skip empty messages
        if not text_content and not tool_calls:
            continue

        turn = {
            "type": msg_type,
            "role": role,
            "timestamp": timestamp,
            "content": text_content,
            "tool_calls": tool_calls,
        }

        # Gemini-specific metadata
        if msg_type == "gemini":
            turn["model"] = msg.get("model", "")
            turn["tokens"] = msg.get("tokens", {})

        turns.append(turn)

    return turns, session_meta


def extract_session_metadata(turns, session_meta, project_name):
    """Extract session-level metadata."""
    if not turns:
        return {}

    timestamps = [t["timestamp"] for t in turns if t["timestamp"]]
    start = session_meta.get("start", timestamps[0] if timestamps else "")
    end = session_meta.get("end", timestamps[-1] if timestamps else "")

    user_count = sum(1 for t in turns if t["role"] == "user")
    assistant_count = sum(1 for t in turns if t["role"] == "assistant")

    all_tools = set()
    for t in turns:
        for tc in t.get("tool_calls", []):
            all_tools.add(tc["tool"])

    # Get model from first gemini message
    model = ""
    for t in turns:
        if t.get("model"):
            model = t["model"]
            break

    return {
        "session_id": session_meta.get("session_id", ""),
        "vendor": "gemini",
        "agent": f"Gemini CLI ({model})" if model else "Gemini CLI",
        "architect": "AG",
        "start": start,
        "end": end,
        "repo": project_name,
        "user_turns": user_count,
        "assistant_turns": assistant_count,
        "total_turns": len(turns),
        "tools_used": sorted(all_tools),
        "model": model,
    }


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def format_session_markdown(turns, metadata):
    """Full transcript as markdown."""
    lines = []
    lines.append("---")
    lines.append(f"session-id: {metadata.get('session_id', '')}")
    lines.append(f"date: {metadata.get('start', '')[:10]}")
    lines.append(f"start: {metadata.get('start', '')}")
    lines.append(f"end: {metadata.get('end', '')}")
    lines.append(f"repo: {metadata.get('repo', '')}")
    lines.append(f"agent: Gemini CLI ({metadata.get('model', 'unknown')})")
    lines.append(f"turns: {metadata.get('total_turns', 0)}")
    lines.append(f"tools: {', '.join(metadata.get('tools_used', []))}")
    lines.append("---")
    lines.append("")
    lines.append(f"# Session Log — {metadata.get('start', '')[:10]}")
    lines.append("")
    lines.append(f"**Repo**: {metadata.get('repo', 'unknown')}")
    lines.append(f"**Model**: {metadata.get('model', 'unknown')}")
    lines.append(f"**Turns**: {metadata.get('user_turns', 0)} user, {metadata.get('assistant_turns', 0)} assistant")
    lines.append(f"**Tools**: {', '.join(metadata.get('tools_used', [])) or 'none'}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for t in turns:
        ts = t["timestamp"][:19] if t["timestamp"] else "?"
        if t["role"] == "user":
            lines.append(f"### [{ts}] Architect")
        elif t["role"] == "assistant":
            lines.append(f"### [{ts}] Agent")
        else:
            lines.append(f"### [{ts}] {t['role']}")
        lines.append("")

        content = t["content"].strip()
        if content:
            if len(content) > 2000:
                content = content[:2000] + "\n\n*[content truncated]*"
            lines.append(content)
            lines.append("")

        if t["tool_calls"]:
            for tc in t["tool_calls"]:
                lines.append(f"**Tool**: `{tc['tool']}` ({', '.join(tc['input_keys'])})")
            lines.append("")

    return "\n".join(lines)


def format_summary_markdown(turns, metadata):
    """Compact summary — delegates to shared canonical formatter."""
    common = _get_common()
    return common.format_summary_markdown(turns, metadata)


def format_session_summary(turns, metadata):
    """Structured summary — delegates to shared canonical formatter."""
    common = _get_common()
    return common.format_session_summary_dict(turns, metadata)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

def print_session_list(sessions):
    """Print summary of all discoverable sessions."""
    print()
    print("  Gemini CLI sessions")
    print(f"  {len(sessions)} sessions found")
    print()

    by_project = {}
    for s in sessions:
        by_project.setdefault(s["project"], []).append(s)

    for project in sorted(by_project.keys()):
        items = by_project[project]
        print(f"  {project} ({len(items)} sessions)")
        for s in items:
            size_kb = s["size"] // 1024
            print(f"    {s['uuid'][:8]}  {s['date']}  {size_kb:>4} KB  {s['modified']}")
        print()

    print(f"  total: {len(sessions)} sessions across {len(by_project)} projects")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    if sys.stdout.encoding != "utf-8":
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )

    parser = argparse.ArgumentParser(
        description="Extract session logs from Gemini CLI."
    )
    parser.add_argument("--list", "-l", action="store_true", help="List all sessions")
    parser.add_argument("--project", "-p", help="Filter by project name")
    parser.add_argument("--session", "-s", help="Extract specific session (UUID partial match)")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    parser.add_argument("--latest", "-n", type=int, default=0, help="Extract N most recent")
    parser.add_argument("--summary", action="store_true", help="Compact summary for git")
    args = parser.parse_args()

    sessions = discover_sessions()
    if not sessions:
        print("  No Gemini CLI sessions found.", file=sys.stderr)
        print(f"  Looked in: {TMP_DIR}", file=sys.stderr)
        sys.exit(1)

    if args.list:
        print_session_list(sessions)
        return

    if args.project:
        sessions = [s for s in sessions if args.project.lower() in s["project"].lower()]
        if not sessions:
            print(f"  Project '{args.project}' not found.", file=sys.stderr)
            sys.exit(1)

    if args.session:
        sessions = [s for s in sessions if args.session.lower() in s["uuid"].lower()]
        if not sessions:
            print(f"  Session '{args.session}' not found.", file=sys.stderr)
            sys.exit(1)

    sessions.sort(key=lambda x: x["modified"], reverse=True)
    if args.latest > 0:
        sessions = sessions[:args.latest]

    results = []
    for s in sessions:
        turns, session_meta = extract_session(s["path"])
        if not turns:
            continue
        metadata = extract_session_metadata(turns, session_meta, s["project"])
        summary = format_session_summary(turns, metadata)

        if args.json:
            result_item = {"metadata": metadata, "summary": summary}
            if not args.summary:
                result_item["turns"] = turns
            results.append(result_item)
        elif args.summary:
            print(format_summary_markdown(turns, metadata))
            print("\n" + "=" * 60 + "\n")
        else:
            print(format_session_markdown(turns, metadata))
            print("\n" + "=" * 60 + "\n")

    if args.json:
        print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
