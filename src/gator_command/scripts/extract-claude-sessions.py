#!/usr/bin/env python3
"""
extract-claude-sessions.py — Session archaeology for Claude Code.

Reads Claude Code's native session storage (~/.claude/projects/),
extracts structured turn data, and produces standardized markdown
session logs. This is the first cross-vendor archaeology script —
nobody else produces clean audit records from AI coding sessions.

Storage layout:
  ~/.claude/projects/<project-slug>/
    <session-uuid>.jsonl    — conversation turns (user, assistant, system, progress)
    <session-uuid>/         — file history snapshots (not used here)
  ~/.claude/history.jsonl   — prompt history (initial messages)

JSONL turn format:
  type: user|assistant|system|progress|file-history-snapshot
  message: {role, content}    — content is string (user) or list of blocks (assistant)
  timestamp: ISO string
  cwd: working directory
  gitBranch: current branch
  sessionId: UUID

Usage:
    python gator-command/scripts/extract-claude-sessions.py
    python gator-command/scripts/extract-claude-sessions.py --project gator-command
    python gator-command/scripts/extract-claude-sessions.py --session <uuid>
    python gator-command/scripts/extract-claude-sessions.py --json
    python gator-command/scripts/extract-claude-sessions.py --list

@reads: ~/.claude/projects/, ~/.claude/history.jsonl
@writes: stdout (or session log files when --output specified)
"""

import argparse
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

CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"
HISTORY_FILE = CLAUDE_DIR / "history.jsonl"

# Turn types to extract (skip file-history-snapshot and progress)
EXTRACT_TYPES = {"user", "assistant", "system"}


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_projects():
    """Find all projects with session data.

    Returns list of {name, path, sessions: [{uuid, path, lines, modified}]}
    """
    if not PROJECTS_DIR.is_dir():
        return []

    projects = []
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue

        # Find JSONL session files
        sessions = []
        for f in sorted(project_dir.iterdir()):
            if f.suffix == ".jsonl" and f.stem != "memory":
                try:
                    line_count = sum(1 for _ in open(f, encoding="utf-8", errors="replace"))
                    modified = datetime.fromtimestamp(f.stat().st_mtime)
                    sessions.append({
                        "uuid": f.stem,
                        "path": f,
                        "lines": line_count,
                        "modified": modified.strftime("%Y-%m-%d %H:%M"),
                    })
                except OSError:
                    continue

        if sessions:
            # Get repo name from the first session's cwd (most reliable)
            readable = project_dir.name  # fallback
            for s in sessions:
                try:
                    with open(s["path"], encoding="utf-8", errors="replace") as sf:
                        for line in sf:
                            data = json.loads(line.strip())
                            cwd = data.get("cwd", "")
                            if cwd:
                                readable = Path(cwd).name
                                break
                        break
                except Exception:
                    continue

            projects.append({
                "name": readable,
                "slug": project_dir.name,
                "path": project_dir,
                "sessions": sessions,
            })

    return projects


def find_project(projects, name):
    """Find a project by name (partial match)."""
    for p in projects:
        if name.lower() in p["name"].lower() or name.lower() in p["slug"].lower():
            return p
    return None


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extract_session(session_path):
    """Extract structured turns from a Claude Code JSONL session file.

    Returns list of turn dicts with: type, timestamp, role, content,
    tool_calls, cwd, branch, session_id.
    """
    turns = []

    with open(session_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            turn_type = data.get("type")
            if turn_type not in EXTRACT_TYPES:
                continue

            msg = data.get("message", {})
            if not isinstance(msg, dict):
                continue

            role = msg.get("role", turn_type)
            content = msg.get("content", "")

            # Parse content — string for user, list of blocks for assistant
            text_content = ""
            tool_calls = []

            if isinstance(content, str):
                text_content = content
            elif isinstance(content, list):
                text_parts = []
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        tool_calls.append({
                            "tool": block.get("name", "unknown"),
                            "input_keys": list(block.get("input", {}).keys()),
                        })
                    elif block.get("type") == "tool_result":
                        # Tool results contain the output
                        result_content = block.get("content", "")
                        if isinstance(result_content, str) and result_content:
                            text_parts.append(f"[tool result: {result_content[:200]}]")
                        elif isinstance(result_content, list):
                            for rc in result_content:
                                if isinstance(rc, dict) and rc.get("text"):
                                    text_parts.append(f"[tool result: {rc['text'][:200]}]")
                text_content = "\n".join(text_parts)

            # Parse timestamp
            ts_raw = data.get("timestamp", "")
            if isinstance(ts_raw, str) and ts_raw:
                timestamp = ts_raw
            elif isinstance(ts_raw, (int, float)):
                timestamp = datetime.fromtimestamp(
                    ts_raw / 1000, tz=timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%SZ")
            else:
                timestamp = ""

            turns.append({
                "type": turn_type,
                "role": role,
                "timestamp": timestamp,
                "content": text_content,
                "tool_calls": tool_calls,
                "cwd": data.get("cwd", ""),
                "branch": data.get("gitBranch", ""),
                "session_id": data.get("sessionId", ""),
            })

    return turns


def extract_session_metadata(turns):
    """Extract session-level metadata from turns."""
    if not turns:
        return {}

    # First and last timestamps
    timestamps = [t["timestamp"] for t in turns if t["timestamp"]]
    start = timestamps[0] if timestamps else ""
    end = timestamps[-1] if timestamps else ""

    # Working directory and branch
    cwds = set(t["cwd"] for t in turns if t["cwd"])
    branches = set(t["branch"] for t in turns if t["branch"])

    # Count by role
    user_count = sum(1 for t in turns if t["role"] == "user")
    assistant_count = sum(1 for t in turns if t["role"] == "assistant")

    # Tools used
    all_tools = set()
    for t in turns:
        for tc in t.get("tool_calls", []):
            all_tools.add(tc["tool"])

    # Session ID
    session_ids = set(t["session_id"] for t in turns if t["session_id"])

    # Extract repo name from cwd
    repo = ""
    if cwds:
        cwd = list(cwds)[0]
        repo = Path(cwd).name

    return {
        "session_id": list(session_ids)[0] if session_ids else "",
        "vendor": "claude",
        "agent": "Claude Code",
        "architect": "AG",
        "start": start,
        "end": end,
        "repo": repo,
        "branch": sorted(branches)[0] if branches else "",
        "cwds": sorted(cwds),
        "branches": sorted(branches),
        "user_turns": user_count,
        "assistant_turns": assistant_count,
        "total_turns": len(turns),
        "tools_used": sorted(all_tools),
    }


# ---------------------------------------------------------------------------
# Output: Markdown
# ---------------------------------------------------------------------------

def format_session_markdown(turns, metadata):
    """Format a session as a standardized markdown log."""
    lines = []

    # Frontmatter
    lines.append("---")
    lines.append(f"session-id: {metadata.get('session_id', '')}")
    lines.append(f"date: {metadata.get('start', '')[:10]}")
    lines.append(f"start: {metadata.get('start', '')}")
    lines.append(f"end: {metadata.get('end', '')}")
    lines.append(f"repo: {metadata.get('repo', '')}")
    lines.append(f"agent: Claude Code")
    lines.append(f"turns: {metadata.get('total_turns', 0)}")
    lines.append(f"tools: {', '.join(metadata.get('tools_used', []))}")
    lines.append("---")
    lines.append("")
    lines.append(f"# Session Log — {metadata.get('start', '')[:10]}")
    lines.append("")
    lines.append(f"**Repo**: {metadata.get('repo', 'unknown')}")
    lines.append(f"**Branch**: {', '.join(metadata.get('branches', ['unknown']))}")
    lines.append(f"**Turns**: {metadata.get('user_turns', 0)} user, {metadata.get('assistant_turns', 0)} assistant")
    lines.append(f"**Tools**: {', '.join(metadata.get('tools_used', [])) or 'none'}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Turns
    for t in turns:
        ts = t["timestamp"][:19] if t["timestamp"] else "?"
        role = t["role"].upper()

        # Role prefix
        if role == "USER":
            lines.append(f"### [{ts}] Architect")
        elif role == "ASSISTANT":
            lines.append(f"### [{ts}] Agent")
        else:
            lines.append(f"### [{ts}] {role}")
        lines.append("")

        # Content (truncate very long content)
        content = t["content"].strip()
        if content:
            if len(content) > 2000:
                content = content[:2000] + "\n\n*[truncated]*"
            lines.append(content)
            lines.append("")

        # Tool calls
        if t["tool_calls"]:
            for tc in t["tool_calls"]:
                lines.append(f"**Tool**: `{tc['tool']}` ({', '.join(tc['input_keys'])})")
            lines.append("")

    return "\n".join(lines)


def format_session_summary(turns, metadata):
    """Structured summary — delegates to shared canonical formatter."""
    common = _get_common()
    return common.format_session_summary_dict(turns, metadata)


def format_summary_markdown(turns, metadata):
    """Compact summary — delegates to shared canonical formatter."""
    common = _get_common()
    return common.format_summary_markdown(turns, metadata)


# ---------------------------------------------------------------------------
# Output: List
# ---------------------------------------------------------------------------

def print_session_list(projects):
    """Print a summary of all discoverable sessions."""
    print()
    print("  Claude Code sessions")
    print(f"  {len(projects)} projects found")
    print()

    total_sessions = 0
    for p in projects:
        print(f"  {p['name']} ({len(p['sessions'])} sessions)")
        for s in p["sessions"]:
            print(f"    {s['uuid'][:8]}...  {s['lines']:>5} lines  {s['modified']}")
            total_sessions += 1
        print()

    print(f"  total: {total_sessions} sessions across {len(projects)} projects")
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
        description="Extract session logs from Claude Code."
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List all discoverable sessions",
    )
    parser.add_argument(
        "--project", "-p",
        help="Filter by project name (partial match)",
    )
    parser.add_argument(
        "--session", "-s",
        help="Extract a specific session by UUID (partial match)",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON instead of markdown",
    )
    parser.add_argument(
        "--latest", "-n",
        type=int,
        default=0,
        help="Extract only the N most recent sessions",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Extract compact summaries (for git) instead of full transcripts",
    )
    args = parser.parse_args()

    # Discover
    projects = discover_projects()
    if not projects:
        print("  No Claude Code sessions found.", file=sys.stderr)
        print(f"  Looked in: {PROJECTS_DIR}", file=sys.stderr)
        sys.exit(1)

    # List mode
    if args.list:
        print_session_list(projects)
        return

    # Filter by project
    if args.project:
        p = find_project(projects, args.project)
        if not p:
            print(f"  Project '{args.project}' not found.", file=sys.stderr)
            print(f"  Available: {', '.join(p['name'] for p in projects)}", file=sys.stderr)
            sys.exit(1)
        projects = [p]

    # Collect all sessions to extract
    all_sessions = []
    for p in projects:
        for s in p["sessions"]:
            all_sessions.append((p, s))

    # Filter by session UUID
    if args.session:
        all_sessions = [
            (p, s) for p, s in all_sessions
            if args.session.lower() in s["uuid"].lower()
        ]
        if not all_sessions:
            print(f"  Session '{args.session}' not found.", file=sys.stderr)
            sys.exit(1)

    # Sort by modified date (most recent first) and limit
    all_sessions.sort(key=lambda x: x[1]["modified"], reverse=True)
    if args.latest > 0:
        all_sessions = all_sessions[:args.latest]

    # Extract
    results = []
    for p, s in all_sessions:
        turns = extract_session(s["path"])
        if not turns:
            continue
        metadata = extract_session_metadata(turns)
        metadata["project"] = p["name"]

        summary = format_session_summary(turns, metadata)

        if args.json:
            result_item = {
                "project": p["name"],
                "metadata": metadata,
                "summary": summary,
            }
            if not args.summary:
                result_item["turns"] = turns
            results.append(result_item)
        elif args.summary:
            md = format_summary_markdown(turns, metadata)
            print(md)
            print("\n" + "=" * 60 + "\n")
        else:
            md = format_session_markdown(turns, metadata)
            print(md)
            print("\n" + "=" * 60 + "\n")

    if args.json:
        print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
