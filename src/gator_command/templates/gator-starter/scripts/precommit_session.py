"""Session ledger and commit summary for the gator pre-commit hook.

Handles session ledger parsing, commit entry building, ledger block
rendering, snippet generation, and commit summary writing.
Self-contained — no external imports beyond stdlib.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def _git(*args, cwd=None):
    """Run a git command, return stdout. Returns empty string on failure."""
    try:
        result = subprocess.run(
            ["git"] + list(args),
            capture_output=True, text=True, cwd=cwd,
            encoding="utf-8", errors="replace",
        )
        return (result.stdout or "").strip()
    except OSError:
        return ""


def _get_current_branch(repo_root):
    """Return current branch name."""
    return _git("branch", "--show-current", cwd=repo_root) or "unknown"


def normalize_agent_name(agent_value):
    """Normalize agent attribution to a filesystem-safe rolling-session key.

    Used for local ledger file naming and legacy session_id generation.
    Not the primary session grouping mechanism — that role belongs to
    vendor session identity (session_group_key) since Phase 4.
    """
    if not agent_value:
        return "unknown"
    agent = str(agent_value).split(",")[0].strip().lower()
    agent = re.sub(r"[^a-z0-9_-]+", "-", agent).strip("-")
    return agent or "unknown"


def _update_frontmatter(text, updates):
    """Update flat frontmatter keys in a markdown document."""
    if not text.startswith("---\n"):
        return text
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return text

    header_lines = parts[1].splitlines()
    seen = set()
    new_lines = []
    for line in header_lines:
        if ":" not in line:
            new_lines.append(line)
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key in updates:
            new_lines.append(f"{key}: {updates[key]}")
            seen.add(key)
        else:
            new_lines.append(line)

    for key, value in updates.items():
        if key not in seen:
            new_lines.append(f"{key}: {value}")

    return "---\n" + "\n".join(new_lines) + "\n---\n" + parts[2]


def _extract_note_lines(body, limit=8):
    """Extract concise note lines from commit_draft body text."""
    if not body:
        return []
    notes = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- "):
            line = line[2:].strip()
        notes.append(line)
        if len(notes) >= limit:
            break
    return notes


def _read_machine_id():
    """Read the stable machine UUID from ~/.gator/machine-id.

    The file has key: value lines (id, hostname, label, created).
    Returns just the id value, not the whole file.
    """
    machine_id_path = Path.home() / ".gator" / "machine-id"
    try:
        for line in machine_id_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("id:"):
                return line.partition(":")[2].strip()
        return ""
    except OSError:
        return ""


def _read_machine_label():
    """Read the human-friendly machine label from ~/.gator/machine-id."""
    machine_id_path = Path.home() / ".gator" / "machine-id"
    try:
        for line in machine_id_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("label:"):
                return line.partition(":")[2].strip()
        return ""
    except OSError:
        return ""


def _read_active_vendor_session(gator_dir):
    """Read .gator/active-vendor-session.json if valid, recent, and for this repo.

    Validates schema, cwd (must match repo root), and freshness (< 24 hours).
    Returns the parsed dict or None.
    """
    avs_path = gator_dir / "active-vendor-session.json"
    if not avs_path.exists():
        return None
    try:
        data = json.loads(avs_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        if data.get("schema") != "gator-active-vendor-session-v1":
            return None
        # Validate cwd matches this repo
        repo_root = gator_dir.parent
        file_cwd = (data.get("cwd") or "").replace("\\", "/").rstrip("/").lower()
        repo_cwd = str(repo_root).replace("\\", "/").rstrip("/").lower()
        if file_cwd and repo_cwd and file_cwd != repo_cwd:
            return None  # Wrong repo
        # Validate freshness
        import time
        mtime = avs_path.stat().st_mtime
        if (time.time() - mtime) > 86400:
            return None  # Stale
        return data
    except (json.JSONDecodeError, OSError):
        return None


def _read_vendor_session(gator_dir):
    """Read vendor session identity, returning {} on any failure.

    Thin wrapper over _read_active_vendor_session that also validates
    vendor_session_id is present and non-empty.
    """
    data = _read_active_vendor_session(gator_dir)
    if data is None:
        return {}
    if not isinstance(data, dict):
        return {}
    if not data.get("vendor_session_id"):
        return {}
    return data


def _derive_intent(entry):
    """Derive a human-readable intent from the commit entry.

    Derivation order:
    1. Cleaned commit subject: strip mechanical prefixes (Fix:, Deploy:, etc.)
    2. First substantive note if subject is empty or generic
    3. Raw subject as fallback
    """
    subject = entry.get("subject", "")
    # Strip mechanical prefixes that duplicate change_type
    cleaned = re.sub(
        r'^(Fix|Deploy|Blueprint|Docs|Refactor|Test|Plan):\s*',
        '', subject, flags=re.IGNORECASE,
    ).strip()
    if cleaned:
        return cleaned
    # Fallback to first note
    notes = entry.get("notes", [])
    return notes[0] if notes else subject


def parse_ledger(path):
    """Parse a session ledger file into structured data.

    Returns {"frontmatter": dict, "entries": list[dict], "raw_body": str}
    where raw_body is the text after frontmatter (for reassembly).
    """
    result = {"frontmatter": {}, "entries": [], "raw_body": ""}
    if not path or not path.exists():
        return result

    text = path.read_text(encoding="utf-8", errors="replace")
    # Normalize CRLF to LF — Windows write_text() produces CRLF,
    # but our delimiters and regexes assume LF.
    text = text.replace("\r\n", "\n")

    # Parse frontmatter
    if text.startswith("---\n"):
        parts = text.split("---\n", 2)
        if len(parts) >= 3:
            for line in parts[1].splitlines():
                if ":" in line:
                    key, _, value = line.partition(":")
                    result["frontmatter"][key.strip()] = value.strip()
            result["raw_body"] = parts[2]

    # Parse commit entry blocks from body
    body = result["raw_body"]
    heading_re = re.compile(r"^### (\S+) - (.+)$")
    kv_re = re.compile(r"^- ([a-z][a-z0-9-]*): (.+)$")
    section_re = re.compile(r"^([A-Z][a-zA-Z-]+):$")
    item_re = re.compile(r"^- (.+)$")

    current_entry = None
    current_section = None

    for line in body.splitlines():
        heading_match = heading_re.match(line)
        if heading_match:
            if current_entry:
                result["entries"].append(current_entry)
            current_entry = {
                "short_commit": heading_match.group(1),
                "subject": heading_match.group(2),
                "commit": "",
                "commit_index": 0,
                "timestamp": "",
                "previous_commit": None,
                "branch": "",
                "change_type": "",
                "significance": "",
                "decision_tags": [],
                "charter_changed": False,
                "files_touched": [],
                "files_touched_source": "",
                "snippet_id": "",
                "notes": [],
            }
            current_section = None
            continue

        if current_entry is None:
            continue

        section_match = section_re.match(line)
        if section_match:
            current_section = section_match.group(1)
            continue

        if current_section:
            item_match = item_re.match(line)
            if item_match:
                item_value = item_match.group(1)
                if current_section == "Files-Touched":
                    current_entry["files_touched"].append(item_value)
                elif current_section == "Notes":
                    current_entry["notes"].append(item_value)
                continue
            # Non-item line ends the section block
            if line.strip():
                current_section = None

        kv_match = kv_re.match(line)
        if kv_match:
            current_section = None  # key-value ends any active section
            key, value = kv_match.group(1), kv_match.group(2)
            if key == "commit":
                current_entry["commit"] = value
            elif key == "commit-index":
                try:
                    current_entry["commit_index"] = int(value)
                except ValueError:
                    pass
            elif key == "timestamp":
                current_entry["timestamp"] = value
            elif key == "previous-commit-in-session":
                current_entry["previous_commit"] = value if value != "~" else None
            elif key == "branch":
                current_entry["branch"] = value
            elif key == "change-type":
                current_entry["change_type"] = value
            elif key == "significance":
                current_entry["significance"] = value
            elif key == "decision-tags":
                current_entry["decision_tags"] = [t.strip() for t in value.split(",") if t.strip()]
            elif key == "charter-changed":
                current_entry["charter_changed"] = value.lower() in ("true", "yes")
            elif key == "files-touched-source":
                current_entry["files_touched_source"] = value
            elif key == "snippet-id":
                current_entry["snippet_id"] = value

    if current_entry:
        result["entries"].append(current_entry)

    return result


def build_commit_entry(gator_dir, status, session_meta, git_fn=None):
    """Build a canonical entry_record dict from status.json + git state + session_meta.

    session_meta is the parsed ledger frontmatter dict (or empty dict for new sessions).
    This function never reads the ledger file itself — the caller provides session_meta.
    This is the single source of truth for both ledger blocks and snippets.

    git_fn: optional callable for git commands (defaults to _git). Allows the
    hook script to inject its own git() for testability.
    """
    if git_fn is None:
        git_fn = _git
    repo_root = gator_dir.parent
    latest = git_fn("log", "-1", "--pretty=format:%H%n%h%n%s", cwd=repo_root).splitlines()
    if len(latest) < 3:
        return None
    commit_hash, short_hash, subject = latest[0], latest[1], latest[2]

    timestamp = status.get("timestamp") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    branch = status.get("branch") or (git_fn("branch", "--show-current", cwd=repo_root) or "unknown")
    architect = status.get("architect") or status.get("pi") or ""

    # previous_commit from ledger frontmatter (not body grep)
    previous_commit = session_meta.get("last-commit-hash") or None

    # commit_index from ledger frontmatter
    try:
        commit_count = int(session_meta.get("commits", 0))
    except (ValueError, TypeError):
        commit_count = 0
    commit_index = commit_count + 1

    # files_touched: prefer status.json, fall back to git diff-tree
    files_touched = status.get("files_touched") or []
    files_touched_source = "status-json"
    if not files_touched:
        try:
            dt_output = git_fn("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD", cwd=repo_root)
            files_touched = [f for f in dt_output.splitlines() if f.strip()]
            files_touched_source = "diff-tree"
        except Exception:
            files_touched = []
            files_touched_source = "unavailable"

    snippet_id = f"snippet-{commit_hash[:13]}"
    notes = _extract_note_lines(status.get("draft_body", ""))

    # Read vendor session identity from active-vendor-session.json
    vendor_session = _read_active_vendor_session(gator_dir)
    transcript_session_id = None
    vendor_inferred_from_session = None
    model_inferred_from_session = None
    if vendor_session:
        transcript_session_id = vendor_session.get("vendor_session_id")
        vendor_inferred_from_session = vendor_session.get("vendor")
        model_inferred_from_session = vendor_session.get("model")

    return {
        "commit": commit_hash,
        "short_commit": short_hash,
        "subject": subject,
        "timestamp": timestamp,
        "branch": branch,
        "architect": architect,
        "change_type": status.get("change_type") or "",
        "significance": status.get("significance") or "",
        "decision_tags": status.get("decision_tags") or [],
        "charter_changed": status.get("charter_changed", False),
        "commit_index": commit_index,
        "previous_commit": previous_commit,
        "files_touched": files_touched,
        "files_touched_source": files_touched_source,
        "snippet_id": snippet_id,
        "notes": notes,
        "transcript_session_id": transcript_session_id,
        "vendor_inferred_from_session": vendor_inferred_from_session,
        "model_inferred_from_session": model_inferred_from_session,
    }


def render_ledger_block(entry):
    """Render a ledger commit entry block from the canonical entry_record dict.

    Uses two element types:
    - Key-value lines: '- key: value' for scalar fields
    - Section blocks: 'Section-Name:' followed by '- item' lines for lists
    """
    prev = entry["previous_commit"] or "~"
    lines = [
        f"### {entry['short_commit']} - {entry['subject']}",
        f"- commit-index: {entry['commit_index']}",
        f"- timestamp: {entry['timestamp']}",
        f"- commit: {entry['commit']}",
        f"- previous-commit-in-session: {prev}",
        f"- branch: {entry['branch']}",
        f"- change-type: {entry['change_type']}",
        f"- significance: {entry['significance']}",
        f"- decision-tags: {','.join(entry['decision_tags'])}",
        f"- charter-changed: {entry['charter_changed']}",
        f"- files-touched-source: {entry['files_touched_source']}",
        f"- snippet-id: {entry['snippet_id']}",
    ]

    if entry["files_touched"]:
        lines.append("Files-Touched:")
        for f in entry["files_touched"]:
            lines.append(f"- {f}")

    if entry["notes"]:
        lines.append("Notes:")
        for note in entry["notes"]:
            lines.append(f"- {note}")

    lines.append("")
    lines.append("")
    return "\n".join(lines)


def _infer_vendor_from_agent(agent_key):
    """Best-effort vendor/model inference from the agent key.

    Returns (vendor, model) tuple.
    """
    key = (agent_key or "").lower()
    if "claude" in key:
        return "anthropic", agent_key
    if "codex" in key or "gpt" in key or "openai" in key or key == "o3" or key == "o4-mini":
        return "openai", agent_key
    if "gemini" in key:
        return "google", agent_key
    return "unknown", agent_key


def _reassemble_ledger(session_meta, raw_body, new_block, entry):
    """Reassemble a complete ledger file from updated frontmatter + existing body + new block.

    Returns the full file content as a string.
    """
    # Update frontmatter fields
    updated_meta = dict(session_meta)
    updated_meta["last-updated"] = entry["timestamp"]
    updated_meta["commits"] = str(entry["commit_index"])
    updated_meta["last-commit-hash"] = entry["commit"]
    updated_meta["architect"] = entry.get("architect", session_meta.get("architect", ""))
    updated_meta["branch"] = entry["branch"]

    # Render frontmatter
    fm_lines = ["---"]
    for key, value in updated_meta.items():
        fm_lines.append(f"{key}: {value}")
    fm_lines.append("---")

    return "\n".join(fm_lines) + "\n" + raw_body + new_block


def write_commit_summary(gator_dir, frontmatter, body, trailers, commit_msg_line):
    """Write a commit-level summary to .gator/sessions/.

    This is the structural audit trail — written automatically on every
    commit, no manual command needed. Each commit gets a small markdown
    file with the metadata from commit_draft.md and the trailer values.
    """
    sessions_dir = gator_dir / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    date_str = now.strftime("%Y-%m-%d")
    time_slug = now.strftime("%H%M%S")
    repo_name = gator_dir.parent.name

    filename = f"{date_str}-{repo_name}-commit-{time_slug}.md"
    summary_path = sessions_dir / filename

    # Build trailer dict for frontmatter
    trailer_dict = {}
    for t in trailers:
        if ": " in t:
            key, _, value = t.partition(": ")
            trailer_dict[key] = value

    # Extract decisions from body (same signals as extract_tags_from_body
    # but captures the full line for audit value)
    decisions = []
    if body:
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # Lines with decision tags or Architect attribution
            if "[#" in stripped or stripped.endswith(("— AG",)):
                decisions.append(stripped)
            # Lines starting with decision-like bullets
            elif stripped.startswith("- ") and len(stripped) > 20:
                decisions.append(stripped[2:])

    # Vendor attribution — the agent trailer carries the vendor identity
    agent = trailer_dict.get('Gator-Agent', frontmatter.get('agent', ''))
    vendor = agent.split(",")[0] if agent else ""  # "claude,codex" -> "claude"

    lines = [
        "---",
        "schema: gator-commit-summary-v1",
        f"type: commit",
        f"date: {date_str}",
        f"timestamp: {timestamp}",
        f"repo: {repo_name}",
        f"vendor: {vendor}",
        f"message: {frontmatter.get('message', commit_msg_line)!s}",
        f"change-type: {trailer_dict.get('Gator-Change-Type', '')}",
        f"significance: {trailer_dict.get('Gator-Significance', '')}",
        f"decision-tags: {trailer_dict.get('Gator-Decision-Tags', '')}",
        f"agent: {trailer_dict.get('Gator-Agent', '')}",
        f"architect: {trailer_dict.get('Gator-Architect', trailer_dict.get('Gator-PI', ''))}",
        f"charter-changed: {trailer_dict.get('Gator-Charter-Changed', '')}",
        "---",
        "",
    ]

    if decisions:
        lines.append("## Decisions")
        lines.append("")
        for d in decisions[:10]:
            lines.append(f"- {d}")
        lines.append("")

    if body and body.strip():
        lines.append("## Session Notes")
        lines.append("")
        # Include body but cap at 30 lines to keep summaries small
        body_lines = body.strip().splitlines()[:30]
        lines.extend(body_lines)
        if len(body.strip().splitlines()) > 30:
            lines.append("")
            lines.append(f"*({len(body.strip().splitlines()) - 30} more lines in commit_draft.md)*")
        lines.append("")

    try:
        summary_path.write_text("\n".join(lines), encoding="utf-8")
        # Stage it so it's included in this commit
        _git("add", str(summary_path), cwd=gator_dir.parent)
    except OSError:
        pass  # Non-fatal — don't block the commit for a summary write failure


def render_snippet_json(entry, session_meta, vendor_session=None):
    """Render a session snippet as a JSON string from canonical entry + session meta.

    This is the canonical snippet renderer. All snippet JSON emission should
    go through this function to maintain a single source of truth for snippet shape.

    Args:
        entry: dict from build_commit_entry()
        session_meta: dict from ledger frontmatter (for lineage fields)
        vendor_session: optional dict from _read_active_vendor_session() (for transcript_session_id)

    Returns: JSON string
    """
    machine_id = _read_machine_id()
    machine_label = _read_machine_label()

    # Agent/vendor inference
    agent = entry.get("agent", session_meta.get("agent", ""))
    vendor_inferred = entry.get("vendor_inferred_from_session") or ""
    model_inferred = entry.get("model_inferred_from_session") or ""
    if not vendor_inferred and agent:
        vendor_inferred, model_inferred = _infer_vendor_from_agent(agent)

    # Vendor session overlay
    transcript_session_id = entry.get("transcript_session_id")
    session_group_key = None
    group_vendor = vendor_inferred  # default: agent-inferred vendor
    if vendor_session:
        if vendor_session.get("vendor_session_id"):
            transcript_session_id = vendor_session["vendor_session_id"]
            # Group key vendor comes from vendor_session explicitly
            group_vendor = vendor_session.get("vendor") or "unknown"
        if vendor_session.get("vendor"):
            vendor_inferred = vendor_session["vendor"]
        if vendor_session.get("model"):
            model_inferred = vendor_session["model"]
    if transcript_session_id and group_vendor:
        session_group_key = f"{group_vendor}:{transcript_session_id}"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    snippet = {
        "schema": "gator-session-snippet-v2",
        "type": "session_snippet",
        "architect": entry.get("architect", ""),
        "agent": agent or None,
        "intent": _derive_intent(entry),
        "change_type": entry.get("change_type", ""),
        "significance": entry.get("significance", ""),
        "charter_changed": entry.get("charter_changed", False),
        "decision_tags": entry.get("decision_tags", []),
        "commit": entry["commit"],
        "short_commit": entry["short_commit"],
        "snippet_id": entry["snippet_id"],
        "session_group_key": session_group_key,
        "repo": entry.get("repo", ""),
        "branch": entry.get("branch", ""),
        "commit_index": entry.get("commit_index", 0),
        "previous_commit_in_session": entry.get("previous_commit"),
        # Three-tier fallback: vendor-reported start (most accurate) →
        # ledger's session-start (from frontmatter, seeded on first commit) →
        # now (last resort, should not fire for post-first-commit snippets).
        # A bare `now` was Codex-flagged as breaking the schema's
        # "when the session group began" contract for repos without an
        # active vendor session — every snippet in such a session would
        # otherwise carry the current commit's timestamp as `started_at`.
        "started_at": (
            (vendor_session or {}).get("started_at")
            or session_meta.get("started-at")
            or now
        ),
        "ended_at": now,
        "vendor_inferred": vendor_inferred,
        "model_inferred": model_inferred,
        "machine_id": machine_id,
        "machine_label": machine_label,
        "files_touched": entry.get("files_touched", []),
        "notes": entry.get("notes", []),
        "transcript_session_id": transcript_session_id,
        "transcript_ref": None,  # Never store local paths in committed snippets
    }

    return json.dumps(snippet, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Session timeout for ledger file reuse
# ---------------------------------------------------------------------------
SESSION_TIMEOUT_HOURS = 4


def record_commit_and_emit_snippet(gator_dir, status, git_fn=None):
    """Orchestrate session ledger append and snippet emission for a commit.

    Uses the canonical .gator/sessions/_active/ ledger surface.
    Idempotent: skips if HEAD matches the ledger's last-commit-hash.
    Ledger writes are atomic (temp-file-and-rename).
    Writes use newline="\\n" for consistent LF output across platforms.
    Snippet failure is non-blocking (warns on stderr, never raises).

    Args:
        gator_dir: Path to .gator/
        status: dict from status.json (agent, timestamp, branch, etc.)
        git_fn: optional callable for git commands (defaults to _git)

    Returns: (ledger_path, snippet_path) — either may be None
    """
    if git_fn is None:
        git_fn = _git
    repo_root = gator_dir.parent

    # Resolve agent and active-session ledger directory
    agent = status.get("agent", "")
    agent_normalized = normalize_agent_name(agent) if agent else "unknown"
    sessions_dir = gator_dir / "sessions" / "_active"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    ledger_path = None
    session_meta = {}
    raw_body = ""

    # Find existing ledger for this agent within timeout (most recent first)
    import time as _time
    for candidate in sorted(
        sessions_dir.glob(f"{repo_root.name}-{agent_normalized}-*.md"),
        key=lambda f: f.stat().st_mtime, reverse=True,
    ):
        age_hours = (_time.time() - candidate.stat().st_mtime) / 3600
        if age_hours > SESSION_TIMEOUT_HOURS:
            break  # Too old — start a new session
        parsed = parse_ledger(candidate)
        session_meta = parsed.get("frontmatter", {})
        raw_body = parsed.get("raw_body", "")
        ledger_path = candidate
        break

    # Build commit entry with lineage from ledger frontmatter
    entry = build_commit_entry(gator_dir, status, session_meta, git_fn=git_fn)
    if entry is None:
        return None, None

    # Idempotent: skip if HEAD is already recorded
    if session_meta.get("last-commit-hash") == entry["commit"]:
        return ledger_path, None

    entry["repo"] = repo_root.name
    entry["agent"] = agent_normalized

    # Update or create the session ledger
    new_block = render_ledger_block(entry)
    if ledger_path:
        updated_content = _reassemble_ledger(session_meta, raw_body, new_block, entry)
        _atomic_write(ledger_path, updated_content, sessions_dir)
        # Update session_meta to post-write state for the renderer
        session_meta = dict(session_meta)
        session_meta["last-updated"] = entry["timestamp"]
        session_meta["commits"] = str(entry["commit_index"])
        session_meta["last-commit-hash"] = entry["commit"]
        session_meta["architect"] = entry.get("architect", session_meta.get("architect", ""))
        session_meta["branch"] = entry["branch"]
    else:
        # Create new ledger
        now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        session_meta = {
            "schema": "gator-active-session-ledger-v1",
            "agent": agent_normalized,
            "started": now_ts,
            "last-updated": now_ts,
            "commits": "1",
            "last-commit-hash": entry["commit"],
            "branch": entry.get("branch", ""),
            "architect": entry.get("architect", ""),
        }
        fm_lines = ["---"]
        for key, value in session_meta.items():
            fm_lines.append(f"{key}: {value}")
        fm_lines.append("---")
        ledger_content = "\n".join(fm_lines) + "\n" + new_block
        now = datetime.now(timezone.utc)
        ts_slug = now.strftime("%Y%m%d-%H%M%S") + f"-{now.microsecond // 1000:03d}"
        ledger_filename = f"{repo_root.name}-{agent_normalized}-{ts_slug}.md"
        ledger_path = sessions_dir / ledger_filename
        _atomic_write(ledger_path, ledger_content, sessions_dir)

    # Read vendor session identity
    vendor_session = _read_active_vendor_session(gator_dir)

    # Render snippet through canonical renderer with current session_meta
    snippet_path = None
    try:
        snippet_json = render_snippet_json(entry, session_meta, vendor_session)

        snippets_dir = gator_dir / "session-snippets"
        snippets_dir.mkdir(exist_ok=True)
        date_str = entry["timestamp"][:10]
        snippet_filename = f"{date_str}-{repo_root.name}-{entry['commit'][:13]}.json"
        snippet_path = snippets_dir / snippet_filename

        if snippet_path.exists():
            existing = snippet_path.read_text(encoding="utf-8", errors="replace")
            if existing != snippet_json:
                print(
                    f"gator: snippet {snippet_path.name} already exists with different content — skipping",
                    file=sys.stderr,
                )
            snippet_path = None  # Signal collision — don't overwrite
        else:
            _atomic_write(snippet_path, snippet_json, snippets_dir)
            # Stage for next commit (staggered)
            git_fn("add", str(snippet_path), cwd=str(repo_root))
    except Exception as exc:
        print(f"gator: Snippet emission failed: {exc}", file=sys.stderr)
        snippet_path = None

    return ledger_path, snippet_path


def _atomic_write(target_path, content, parent_dir):
    """Write content to target_path atomically via temp-file-and-rename."""
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(parent_dir), suffix=".tmp", prefix=".gator-"
    )
    try:
        with open(tmp_fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        Path(tmp_path).replace(target_path)
    except Exception:
        try:
            Path(tmp_path).unlink()
        except OSError:
            pass
        raise
