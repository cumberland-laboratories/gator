#!/usr/bin/env python3
"""
gator-session-block.py — Session-block companion capture.

Extracts exact, compressed transcript slices for each commit interval.
Session blocks are local-only by default (gitignored). This is a CLI-first,
on-demand capture tool — no hook integration for MVP.

Same-machine, recent-session best effort. Requires the vendor transcript
to still exist on this machine.

Usage:
    gator session-blocks generate --commit <commit-ish>

@reads: .gator/session-snippets/, vendor transcript files
@writes: .gator/session-blocks/<stem>.json.gz
"""

import argparse
import gzip
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class SnippetNotFound(Exception):
    pass

class SnippetInvariantViolation(Exception):
    pass

class TranscriptNotFound(Exception):
    pass

class MultipleTranscriptsFound(Exception):
    def __init__(self, candidates):
        self.candidates = candidates
        super().__init__(f"Multiple transcript candidates: {candidates}")

class AnchorNotFound(Exception):
    pass


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _git(*args, cwd=None):
    """Run a git command. Returns (stdout, ok)."""
    try:
        result = subprocess.run(
            ["git"] + list(args),
            capture_output=True, text=True, cwd=cwd, timeout=10,
        )
        return result.stdout.strip(), result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return "", False


def resolve_full_hash(commit_ish, cwd=None):
    """Resolve any commit-ish to a full 40-char hash."""
    out, ok = _git("rev-parse", commit_ish, cwd=cwd)
    if not ok or not out:
        return None
    return out.strip().split("\n")[0]


def resolve_short_hash(full_hash, cwd=None):
    """Resolve a full hash to its short form."""
    out, ok = _git("rev-parse", "--short", full_hash, cwd=cwd)
    if not ok or not out:
        return full_hash[:7]
    return out.strip()


# ---------------------------------------------------------------------------
# Snippet resolution
# ---------------------------------------------------------------------------

def find_gator_dir(start=None):
    """Walk up to find .gator/ directory."""
    path = Path(start or os.getcwd()).resolve()
    for _ in range(10):
        if (path / ".gator").is_dir():
            return path / ".gator"
        if path.parent == path:
            break
        path = path.parent
    return None


def resolve_snippet(gator_dir, full_commit_hash):
    """Find exactly one snippet for a commit hash.

    Raises SnippetNotFound if zero, SnippetInvariantViolation if multiple.
    """
    snippets_dir = gator_dir / "session-snippets"
    if not snippets_dir.is_dir():
        raise SnippetNotFound(f"No snippet found for commit {full_commit_hash}")

    matches = []
    for f in snippets_dir.iterdir():
        if not f.suffix == ".json":
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("commit") == full_commit_hash:
            matches.append((f, data))

    if len(matches) == 0:
        raise SnippetNotFound(f"No snippet found for commit {full_commit_hash}")
    if len(matches) > 1:
        raise SnippetInvariantViolation(
            f"Multiple snippets for commit {full_commit_hash} — invariant violation"
        )

    return matches[0][1], matches[0][0]


# ---------------------------------------------------------------------------
# Transcript discovery
# ---------------------------------------------------------------------------

def discover_transcript(vendor, transcript_session_id):
    """Find a vendor transcript file by session ID.

    This is a provisional local-machine best-effort discovery layer.
    Vendor log directory layouts are not stable APIs and may change.

    Raises TranscriptNotFound if zero matches.
    Raises MultipleTranscriptsFound (with candidate paths) if ambiguous.
    """
    home = Path.home()
    candidates = []

    # Canonical vendor_inferred values from gator-session-start.py:
    #   anthropic, openai, google, unknown
    if vendor in ("anthropic", "claude", "unknown"):
        # Claude Code: ~/.claude/projects/*/<session_id>.jsonl
        claude_projects = home / ".claude" / "projects"
        if claude_projects.is_dir():
            for project_dir in claude_projects.iterdir():
                if not project_dir.is_dir():
                    continue
                candidate = project_dir / f"{transcript_session_id}.jsonl"
                if candidate.is_file():
                    candidates.append(candidate)

    if vendor in ("openai", "codex", "unknown"):
        # Codex CLI: ~/.codex/sessions/*/*/rollout-*-<session_id>.jsonl
        codex_sessions = home / ".codex" / "sessions"
        if codex_sessions.is_dir():
            for date_dir in codex_sessions.iterdir():
                if not date_dir.is_dir():
                    continue
                for sub in date_dir.iterdir():
                    if not sub.is_dir():
                        continue
                    for f in sub.iterdir():
                        if (f.suffix == ".jsonl"
                                and transcript_session_id in f.name
                                and f.name.startswith("rollout-")):
                            candidates.append(f)

    if vendor in ("google", "gemini", "unknown"):
        # Gemini CLI: ~/.gemini/tmp/*/chats/session-*-<session_id>.json
        gemini_tmp = home / ".gemini" / "tmp"
        if gemini_tmp.is_dir():
            for proj_dir in gemini_tmp.iterdir():
                if not proj_dir.is_dir():
                    continue
                chats_dir = proj_dir / "chats"
                if not chats_dir.is_dir():
                    continue
                for f in chats_dir.iterdir():
                    if (f.suffix == ".json"
                            and transcript_session_id in f.name
                            and f.name.startswith("session-")):
                        candidates.append(f)

    if len(candidates) == 0:
        raise TranscriptNotFound(
            f"Transcript file not found for session {transcript_session_id} "
            f"(vendor: {vendor})"
        )
    if len(candidates) > 1:
        raise MultipleTranscriptsFound(candidates)

    return candidates[0]


# ---------------------------------------------------------------------------
# Transcript parsing
# ---------------------------------------------------------------------------

def parse_claude_transcript(transcript_path):
    """Parse Claude Code JSONL transcript.

    Returns list of raw turn dicts with full, untruncated content.
    Unlike extract-claude-sessions.py, tool results are NOT truncated.
    """
    turns = []
    with open(transcript_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            turn_type = data.get("type")
            if turn_type not in ("user", "assistant", "system"):
                continue

            msg = data.get("message", {})
            if not isinstance(msg, dict):
                continue

            role = msg.get("role", turn_type)
            content = msg.get("content", "")

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

            # Parse content — string for user, list of blocks for assistant
            text_content = ""
            tool_calls = []
            is_tool_output = False

            if isinstance(content, str):
                text_content = content
            elif isinstance(content, list):
                text_parts = []
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type", "")
                    if btype == "text":
                        text_parts.append(block.get("text", ""))
                    elif btype == "tool_use":
                        tool_calls.append({
                            "tool": block.get("name", "unknown"),
                            "input_keys": list(block.get("input", {}).keys()),
                        })
                    elif btype == "tool_result":
                        is_tool_output = True
                        result_content = block.get("content", "")
                        if isinstance(result_content, str) and result_content:
                            text_parts.append(result_content)
                        elif isinstance(result_content, list):
                            for rc in result_content:
                                if isinstance(rc, dict) and rc.get("text"):
                                    text_parts.append(rc["text"])
                text_content = "\n".join(text_parts)

            turns.append({
                "type": turn_type,
                "role": role,
                "timestamp": timestamp,
                "content": text_content,
                "tool_calls": tool_calls,
                "is_tool_output": is_tool_output,
            })

    return turns


def parse_codex_transcript(transcript_path):
    """Parse Codex CLI JSONL transcript. Same contract as Claude parser."""
    turns = []
    with open(transcript_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            role = data.get("role", "")
            if role not in ("user", "assistant", "system"):
                continue

            content = data.get("content", "")
            text_content = content if isinstance(content, str) else ""
            is_tool_output = data.get("type") == "tool_result"

            ts_raw = data.get("timestamp", "")
            timestamp = ts_raw if isinstance(ts_raw, str) else ""

            tool_calls = []
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif block.get("type") == "tool_use":
                            tool_calls.append({
                                "tool": block.get("name", "unknown"),
                                "input_keys": list(block.get("input", {}).keys()),
                            })
                        elif block.get("type") == "tool_result":
                            is_tool_output = True
                            rc = block.get("content", "")
                            if isinstance(rc, str):
                                text_parts.append(rc)
                text_content = "\n".join(text_parts)

            turns.append({
                "type": data.get("type", role),
                "role": role,
                "timestamp": timestamp,
                "content": text_content,
                "tool_calls": tool_calls,
                "is_tool_output": is_tool_output,
            })

    return turns


def parse_gemini_transcript(transcript_path):
    """Parse Gemini CLI JSON transcript. Same contract as Claude parser."""
    turns = []
    try:
        data = json.loads(
            Path(transcript_path).read_text(encoding="utf-8", errors="replace")
        )
    except (json.JSONDecodeError, OSError):
        return turns

    messages = data if isinstance(data, list) else data.get("messages", [])
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role", "")
        if role not in ("user", "model", "assistant", "system"):
            continue

        content = msg.get("content", "")
        text_content = content if isinstance(content, str) else ""
        is_tool_output = msg.get("type") == "tool_result"

        ts_raw = msg.get("timestamp", "")
        timestamp = ts_raw if isinstance(ts_raw, str) else ""

        tool_calls = []
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_result":
                        is_tool_output = True
                        rc = block.get("content", "")
                        if isinstance(rc, str):
                            text_parts.append(rc)
            text_content = "\n".join(text_parts)

        mapped_role = "assistant" if role == "model" else role
        turns.append({
            "type": msg.get("type", role),
            "role": mapped_role,
            "timestamp": timestamp,
            "content": text_content,
            "tool_calls": tool_calls,
            "is_tool_output": is_tool_output,
        })

    return turns


# ---------------------------------------------------------------------------
# Anchor detection
# ---------------------------------------------------------------------------

# Git commit output pattern: [branch abc1234]
_GIT_COMMIT_RE = re.compile(r"\[[\w./-]+ ([a-f0-9]{7,})\]")


def find_commit_anchors(raw_turns, start_short_hash, end_short_hash):
    """Scan tool output turns for commit hash anchors.

    Only scans turns with is_tool_output == True.
    Returns (start_index, end_index, start_found) where start_found indicates
    whether the start anchor was actually located in the transcript.
    Raises AnchorNotFound if end hash cannot be found.
    """
    start_index = 0
    start_found = False
    end_index = None

    for i, turn in enumerate(raw_turns):
        if not turn.get("is_tool_output"):
            continue

        matches = _GIT_COMMIT_RE.findall(turn.get("content", ""))
        for match in matches:
            if start_short_hash and match.startswith(start_short_hash):
                start_index = i
                start_found = True
            if match.startswith(end_short_hash):
                end_index = i

    if end_index is None:
        raise AnchorNotFound(
            f"End anchor {end_short_hash} not found in any tool output"
        )

    if start_short_hash and not start_found:
        raise AnchorNotFound(
            f"Start anchor {start_short_hash} not found in any tool output"
        )

    return start_index, end_index, start_found


# ---------------------------------------------------------------------------
# Normalization and rendering
# ---------------------------------------------------------------------------

_ROLE_MAP = {
    "user": "human",
    "assistant": "assistant",
    "system": "system",
    "model": "assistant",
}


def normalize_turns(raw_turns, start_idx, end_idx):
    """Slice and normalize turns to canonical schema."""
    sliced = raw_turns[start_idx:end_idx + 1]
    normalized = []
    for i, turn in enumerate(sliced, 1):
        role = turn.get("role", "")
        if turn.get("is_tool_output"):
            mapped_role = "tool_result"
        else:
            mapped_role = _ROLE_MAP.get(role, role)

        normalized.append({
            "seq": i,
            "role": mapped_role,
            "ts": turn.get("timestamp") or None,
            "content": turn.get("content", ""),
            "tool_calls": turn.get("tool_calls", []),
        })
    return normalized


def extract_interval(transcript_path, vendor, start_short_hash, end_short_hash):
    """Parse transcript, find anchors, normalize turns.

    Returns (turns, capture_quality, capture_method).
    """
    # Select parser — canonical vendor_inferred values: anthropic, openai, google, unknown
    if vendor in ("openai", "codex"):
        raw_turns = parse_codex_transcript(transcript_path)
    elif vendor in ("google", "gemini"):
        raw_turns = parse_gemini_transcript(transcript_path)
    else:
        # anthropic, claude, unknown, or unrecognized → Claude parser
        raw_turns = parse_claude_transcript(transcript_path)

    start_idx, end_idx, start_found = find_commit_anchors(
        raw_turns, start_short_hash, end_short_hash
    )

    turns = normalize_turns(raw_turns, start_idx, end_idx)

    if start_short_hash and start_found:
        quality = "exact"
    else:
        quality = "bounded"

    return turns, quality, "commit-hash-anchors"


def render_session_block(turns, capture_quality, capture_method, snippet):
    """Build gator-session-block-v1 dict from turns + snippet metadata."""
    human_count = sum(1 for t in turns if t["role"] == "human")
    assistant_count = sum(1 for t in turns if t["role"] == "assistant")
    tool_count = sum(1 for t in turns if t["role"] == "tool_result")

    return {
        "schema": "gator-session-block-v1",
        "type": "session_block",
        "target_commit": snippet.get("commit"),
        "short_commit": snippet.get("short_commit"),
        "snippet_id": snippet.get("snippet_id"),
        "session_id": snippet.get("session_id"),
        "session_group_key": snippet.get("session_group_key"),
        "transcript_session_id": snippet.get("transcript_session_id"),
        "repo": snippet.get("repo"),
        "branch": snippet.get("branch"),
        "commit_index": snippet.get("commit_index"),
        "previous_commit_in_session": snippet.get("previous_commit_in_session"),
        "started_at": snippet.get("started_at"),
        "ended_at": snippet.get("ended_at"),
        "capture_status": "captured",
        "capture_quality": capture_quality,
        "capture_method": capture_method,
        "content_policy": "raw",
        "binary_content": "excluded",
        "vendor": snippet.get("vendor_inferred"),
        "model": snippet.get("model_inferred"),
        "turn_count": len(turns),
        "turns": turns,
        "metrics": {
            "human_turns": human_count,
            "assistant_turns": assistant_count,
            "tool_result_turns": tool_count,
        },
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def emit_session_block(gator_dir, block_data, snippet_filename_stem):
    """Gzip-compress block JSON and write to .gator/session-blocks/.

    Idempotent: no-op if identical content exists.
    Returns the output path.
    """
    blocks_dir = gator_dir / "session-blocks"
    blocks_dir.mkdir(exist_ok=True)

    out_path = blocks_dir / f"{snippet_filename_stem}.json.gz"
    compressed = gzip.compress(
        json.dumps(block_data, indent=2, ensure_ascii=False).encode("utf-8")
    )

    if out_path.exists():
        existing = out_path.read_bytes()
        if existing == compressed:
            return out_path

    out_path.write_bytes(compressed)
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def generate(commit_ish, repo_cwd=None):
    """Main generation flow. Returns (output_path, block_data) on success."""
    cwd = repo_cwd or os.getcwd()

    # 1. Find .gator/
    gator_dir = find_gator_dir(cwd)
    if not gator_dir:
        print("Error: .gator/ directory not found", file=sys.stderr)
        sys.exit(1)

    # 2. Resolve to full commit hash
    full_hash = resolve_full_hash(commit_ish, cwd=cwd)
    if not full_hash:
        print(f"Error: Cannot resolve commit '{commit_ish}'", file=sys.stderr)
        sys.exit(1)

    # 3. Find snippet
    try:
        snippet, snippet_path = resolve_snippet(gator_dir, full_hash)
    except SnippetNotFound as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except SnippetInvariantViolation as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # 4. Check transcript_session_id
    transcript_session_id = snippet.get("transcript_session_id")
    if not transcript_session_id:
        print(
            "Error: Snippet has no transcript_session_id — block generation "
            "requires the session-identity pipeline (v1.3.0+)",
            file=sys.stderr,
        )
        sys.exit(1)

    vendor = snippet.get("vendor_inferred", "unknown")

    # 5. Discover transcript
    try:
        transcript_path = discover_transcript(vendor, transcript_session_id)
    except TranscriptNotFound as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except MultipleTranscriptsFound as e:
        print(
            f"Error: Multiple transcript candidates found for session "
            f"{transcript_session_id}:",
            file=sys.stderr,
        )
        for c in e.candidates:
            print(f"  {c}", file=sys.stderr)
        sys.exit(1)

    # 6. Resolve anchor hashes
    end_short_hash = snippet.get("short_commit", "")
    start_short_hash = None

    prev_commit = snippet.get("previous_commit_in_session")
    if prev_commit:
        # Prefer previous snippet's short_commit field
        try:
            prev_snippet, _ = resolve_snippet(gator_dir, prev_commit)
            start_short_hash = prev_snippet.get("short_commit")
        except (SnippetNotFound, SnippetInvariantViolation):
            # Fallback to git rev-parse --short
            start_short_hash = resolve_short_hash(prev_commit, cwd=cwd)

    # 7. Extract interval
    try:
        turns, quality, method = extract_interval(
            transcript_path, vendor, start_short_hash, end_short_hash
        )
    except AnchorNotFound as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # 8. Render and emit
    block_data = render_session_block(turns, quality, method, snippet)
    snippet_stem = snippet_path.stem  # filename without .json
    out_path = emit_session_block(gator_dir, block_data, snippet_stem)

    print(out_path)
    return out_path, block_data


def main():
    parser = argparse.ArgumentParser(
        prog="gator session-blocks",
        description=(
            "Generate session-block companions from vendor transcripts. "
            "Same-machine, recent-session best effort. Requires the vendor "
            "transcript to still exist on this machine."
        ),
    )
    sub = parser.add_subparsers(dest="action")
    gen = sub.add_parser("generate", help="Generate a session block for a commit")
    gen.add_argument(
        "--commit", required=True,
        help="Commit-ish to generate block for (short hash, full hash, HEAD, branch)",
    )

    args = parser.parse_args()
    if args.action != "generate":
        parser.print_help()
        sys.exit(1)

    generate(args.commit)


if __name__ == "__main__":
    main()
