#!/usr/bin/env python3
"""
extract-codex-sessions.py — Session archaeology for OpenAI Codex CLI.

Reads Codex CLI's native session storage (~/.codex/sessions/),
extracts structured turn data, and produces standardized markdown
session logs matching the same format as extract-claude-sessions.py.

Storage layout:
  ~/.codex/sessions/YYYY/MM/DD/
    rollout-<timestamp>-<uuid>.jsonl
  ~/.codex/history.jsonl   — prompt history

JSONL turn format:
  timestamp: ISO string
  type: session_meta|response_item|event_msg|turn_context
  payload:
    session_meta: {id, cwd, cli_version, model_provider, git: {commit_hash, branch}}
    response_item: {type: message|function_call|function_call_output|reasoning,
                    role: user|developer|assistant, content: [{type, text}]}
    event_msg: {type: task_started|task_complete, turn_id}
    turn_context: {turn_id, cwd, model, approval_policy, sandbox_policy}

Role mapping:
  user/developer → Architect (both are human input)
  assistant → Agent
  function_call → Tool use
  function_call_output → Tool result
  reasoning → Agent thinking (internal)

Usage:
    python gator-command/scripts/extract-codex-sessions.py
    python gator-command/scripts/extract-codex-sessions.py --list
    python gator-command/scripts/extract-codex-sessions.py --date 2026-05-28
    python gator-command/scripts/extract-codex-sessions.py --latest 3 --summary
    python gator-command/scripts/extract-codex-sessions.py --json

@reads: ~/.codex/sessions/, ~/.codex/history.jsonl
@writes: stdout (or session log files when --output specified)
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

CODEX_DIR = Path.home() / ".codex"
SESSIONS_DIR = CODEX_DIR / "sessions"
HISTORY_FILE = CODEX_DIR / "history.jsonl"


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_sessions():
    """Find all Codex session JSONL files.

    Returns list of {uuid, path, date, lines, size, modified}
    organized by date.
    """
    if not SESSIONS_DIR.is_dir():
        return []

    sessions = []
    for jsonl in sorted(SESSIONS_DIR.rglob("rollout-*.jsonl")):
        try:
            line_count = sum(1 for _ in open(jsonl, encoding="utf-8", errors="replace"))
            size = jsonl.stat().st_size
            modified = datetime.fromtimestamp(jsonl.stat().st_mtime)

            # Extract UUID from filename: rollout-<timestamp>-<uuid>.jsonl
            name = jsonl.stem  # rollout-2026-05-28T08-33-48-<uuid>
            parts = name.split("-", 7)  # split on hyphens
            uuid = parts[-1] if len(parts) > 1 else name

            # Extract date from path: sessions/YYYY/MM/DD/
            rel = jsonl.relative_to(SESSIONS_DIR)
            date_parts = list(rel.parts[:-1])  # ['2026', '05', '28']
            date_str = "-".join(date_parts) if len(date_parts) >= 3 else ""

            sessions.append({
                "uuid": uuid,
                "path": jsonl,
                "date": date_str,
                "lines": line_count,
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
    """Extract structured turns from a Codex JSONL session file."""
    turns = []
    session_meta = {}

    with open(session_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type")
            timestamp = data.get("timestamp", "")
            payload = data.get("payload", {})

            if msg_type == "session_meta":
                session_meta = payload
                continue

            if msg_type == "turn_context":
                # Capture model info but don't emit as a turn
                session_meta["model"] = payload.get("model", "")
                session_meta["approval_policy"] = payload.get("approval_policy", "")
                continue

            if msg_type == "event_msg":
                # Skip task lifecycle events
                continue

            if msg_type == "response_item":
                role = payload.get("role", "")
                item_type = payload.get("type", "")

                # Extract text content
                text_content = ""
                tool_calls = []
                content = payload.get("content") or []

                if isinstance(content, list):
                    text_parts = []
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        btype = block.get("type", "")
                        if btype in ("input_text", "output_text", "text"):
                            text = block.get("text", "")
                            if text:
                                text_parts.append(text)
                    text_content = "\n".join(text_parts)
                elif isinstance(content, str):
                    text_content = content

                # Function calls
                if item_type == "function_call":
                    func_name = payload.get("name", "unknown")
                    func_args = payload.get("arguments", "")
                    tool_calls.append({
                        "tool": func_name,
                        "input_keys": _extract_arg_keys(func_args),
                    })
                    text_content = f"[calling {func_name}]"

                if item_type == "function_call_output":
                    output = payload.get("output", "")
                    if isinstance(output, str):
                        text_content = f"[tool result: {output[:200]}]"

                if item_type == "reasoning":
                    # Internal reasoning — include but mark
                    text_content = payload.get("summary", "")
                    if not text_content:
                        # Try content blocks
                        for block in (payload.get("content") or []):
                            if isinstance(block, dict) and block.get("text"):
                                text_content = block["text"]
                                break

                # Map roles
                if role in ("user", "developer"):
                    mapped_role = "user"
                elif role == "assistant":
                    mapped_role = "assistant"
                elif item_type == "function_call":
                    mapped_role = "assistant"
                elif item_type == "function_call_output":
                    mapped_role = "system"
                elif item_type == "reasoning":
                    mapped_role = "assistant"
                else:
                    mapped_role = role or "unknown"

                # Skip system/developer messages that are just instructions
                if mapped_role == "user" and text_content:
                    # Skip if it's the AGENTS.md injection or sandbox config
                    if text_content.startswith("# AGENTS.md") or \
                       text_content.startswith("<permissions") or \
                       text_content.startswith("<environment_context"):
                        continue

                turns.append({
                    "type": msg_type,
                    "role": mapped_role,
                    "timestamp": timestamp,
                    "content": text_content,
                    "tool_calls": tool_calls,
                    "item_type": item_type,
                })

    return turns, session_meta


def _extract_arg_keys(args_str):
    """Extract key names from a JSON arguments string."""
    if not args_str:
        return []
    try:
        args = json.loads(args_str)
        if isinstance(args, dict):
            return list(args.keys())
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def extract_session_metadata(turns, session_meta):
    """Extract session-level metadata."""
    if not turns:
        return {}

    timestamps = [t["timestamp"] for t in turns if t["timestamp"]]
    start = timestamps[0] if timestamps else ""
    end = timestamps[-1] if timestamps else ""

    user_count = sum(1 for t in turns if t["role"] == "user")
    assistant_count = sum(1 for t in turns if t["role"] == "assistant")

    all_tools = set()
    for t in turns:
        for tc in t.get("tool_calls", []):
            all_tools.add(tc["tool"])

    # Get repo from session_meta
    cwd = session_meta.get("cwd", "")
    repo = Path(cwd).name if cwd else ""
    branch = ""
    git_info = session_meta.get("git", {})
    if isinstance(git_info, dict):
        branch = git_info.get("branch", "")

    model = session_meta.get("model", "unknown")
    cli_version = session_meta.get("cli_version", "")

    return {
        "session_id": session_meta.get("id", ""),
        "vendor": "codex",
        "agent": f"Codex CLI ({model})",
        "architect": "AG",
        "start": start,
        "end": end,
        "repo": repo,
        "cwd": cwd,
        "branch": branch,
        "user_turns": user_count,
        "assistant_turns": assistant_count,
        "total_turns": len(turns),
        "tools_used": sorted(all_tools),
        "model": model,
        "cli_version": cli_version,
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
    lines.append(f"agent: Codex CLI ({metadata.get('model', 'unknown')})")
    lines.append(f"turns: {metadata.get('total_turns', 0)}")
    lines.append(f"tools: {', '.join(metadata.get('tools_used', []))}")
    lines.append("---")
    lines.append("")
    lines.append(f"# Session Log — {metadata.get('start', '')[:10]}")
    lines.append("")
    lines.append(f"**Repo**: {metadata.get('repo', 'unknown')}")
    lines.append(f"**Branch**: {metadata.get('branch', 'unknown')}")
    lines.append(f"**Model**: {metadata.get('model', 'unknown')}")
    lines.append(f"**Turns**: {metadata.get('user_turns', 0)} user, {metadata.get('assistant_turns', 0)} assistant")
    lines.append(f"**Tools**: {', '.join(metadata.get('tools_used', [])) or 'none'}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for t in turns:
        ts = t["timestamp"][:19] if t["timestamp"] else "?"
        role = t["role"]
        item_type = t.get("item_type", "")

        if role == "user":
            lines.append(f"### [{ts}] Architect")
        elif role == "assistant" and item_type == "reasoning":
            lines.append(f"### [{ts}] Agent (thinking)")
        elif role == "assistant":
            lines.append(f"### [{ts}] Agent")
        else:
            lines.append(f"### [{ts}] {role}")
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
    print("  Codex CLI sessions")
    print(f"  {len(sessions)} sessions found")
    print()

    by_date = {}
    for s in sessions:
        by_date.setdefault(s["date"], []).append(s)

    for date in sorted(by_date.keys()):
        items = by_date[date]
        print(f"  {date} ({len(items)} sessions)")
        for s in items:
            size_kb = s["size"] // 1024
            print(f"    {s['uuid'][:8]}...  {s['lines']:>4} lines  {size_kb:>4} KB  {s['modified']}")
        print()

    print(f"  total: {len(sessions)} sessions")
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
        description="Extract session logs from Codex CLI."
    )
    parser.add_argument("--list", "-l", action="store_true", help="List all sessions")
    parser.add_argument("--date", "-d", help="Filter by date (YYYY-MM-DD)")
    parser.add_argument("--session", "-s", help="Extract specific session (UUID partial match)")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    parser.add_argument("--latest", "-n", type=int, default=0, help="Extract N most recent")
    parser.add_argument("--summary", action="store_true", help="Compact summary for git")
    args = parser.parse_args()

    sessions = discover_sessions()
    if not sessions:
        print("  No Codex CLI sessions found.", file=sys.stderr)
        print(f"  Looked in: {SESSIONS_DIR}", file=sys.stderr)
        sys.exit(1)

    if args.list:
        print_session_list(sessions)
        return

    # Filter by date
    if args.date:
        sessions = [s for s in sessions if args.date in s["date"]]
        if not sessions:
            print(f"  No sessions found for date '{args.date}'.", file=sys.stderr)
            sys.exit(1)

    # Filter by UUID
    if args.session:
        sessions = [s for s in sessions if args.session.lower() in s["uuid"].lower()]
        if not sessions:
            print(f"  Session '{args.session}' not found.", file=sys.stderr)
            sys.exit(1)

    # Sort by modified (most recent first) and limit
    sessions.sort(key=lambda x: x["modified"], reverse=True)
    if args.latest > 0:
        sessions = sessions[:args.latest]

    # Extract
    results = []
    for s in sessions:
        turns, session_meta = extract_session(s["path"])
        if not turns:
            continue
        metadata = extract_session_metadata(turns, session_meta)

        summary = format_session_summary(turns, metadata)

        if args.json:
            result_item = {
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
