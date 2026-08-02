#!/usr/bin/env python3
"""
gator sessions — Audit infrastructure CLI for AI coding sessions.

Orchestrates the vendor-specific extraction scripts and presents
a unified automation surface for enterprise session management.

Commands:
    gator sessions index       — show all discoverable sessions across vendors
    gator sessions manifest    — emit JSON manifest for enterprise automation
    gator sessions export      — write normalized session files to spool dir
    gator sessions pending     — show sessions not yet exported

Gator does not own the audit backend. It produces a portable audit index
and normalized session evidence. Enterprise automation collects and stores
it wherever they already trust.

Usage:
    python gator-command/scripts/gator-sessions.py index
    python gator-command/scripts/gator-sessions.py manifest --since 24h --json
    python gator-command/scripts/gator-sessions.py export --pending
    python gator-command/scripts/gator-sessions.py pending

@reads: ~/.claude/, ~/.codex/, ~/.gemini/, ~/.gator/machine-id, spool state
@writes: ~/.gator/session-spool/ (normalized exports), stdout
"""

import argparse
import glob
import io
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add scripts dir to path for imports
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))


# ---------------------------------------------------------------------------
# Lazy vendor imports (only load what's available)
# ---------------------------------------------------------------------------

def _import_vendor(module_name):
    """Import a vendor extraction module by file name (with hyphens)."""
    try:
        import importlib.util
        # Files use hyphens: extract-claude-sessions.py
        script_path = SCRIPTS_DIR / f"{module_name}.py"
        if not script_path.exists():
            return None
        spec = importlib.util.spec_from_file_location(
            module_name.replace("-", "_"), script_path
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def _spool_slug(session_id, source_path=""):
    """Generate a filesystem-safe unique spool filename slug.

    Hashes session_id + source_path together. The source_path
    disambiguates when two different files share the same internal
    session ID (verified real case in Gemini storage).
    """
    import hashlib
    key = f"{session_id}|{source_path}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GATOR_USER_DIR = Path.home() / ".gator"
SPOOL_DIR = GATOR_USER_DIR / "session-spool"
SPOOL_STATE_FILE = SPOOL_DIR / ".exported.json"
MANIFEST_DIR = GATOR_USER_DIR / "turn-manifests"

STOPWORDS = {
    "the", "and", "this", "that", "with", "for", "are", "but", "not", "you",
    "all", "can", "had", "her", "was", "one", "our", "out", "has", "have",
    "from", "they", "been", "said", "each", "which", "their", "will", "way",
    "about", "many", "then", "them", "would", "like", "more", "some", "time",
    "very", "when", "come", "could", "made", "after", "also", "did", "just",
    "these", "than", "other", "into", "only", "new", "its", "what", "how",
    "who", "may", "any", "use", "here", "there", "where", "does", "should",
    "need", "please", "sure", "let", "now", "see", "get", "make", "know",
}


# ---------------------------------------------------------------------------
# Machine identity — delegated to shared module
# ---------------------------------------------------------------------------

def get_machine_identity():
    """Get stable machine identity (delegates to shared module)."""
    common = _import_vendor("gator-session-common")
    if common:
        return common.get_machine_identity()
    # Fallback if shared module unavailable
    import platform
    return {"id": "unknown", "hostname": platform.node(), "label": platform.node()}


# ---------------------------------------------------------------------------
# Unified session discovery
# ---------------------------------------------------------------------------

def discover_all_sessions():
    """Discover sessions across all installed vendors.

    Returns list of normalized session dicts with vendor, project,
    session_id, path, date, size, modified.
    """
    all_sessions = []

    # Claude Code
    claude_mod = _import_vendor("extract-claude-sessions")
    if claude_mod:
        try:
            projects = claude_mod.discover_projects()
            for p in projects:
                for s in p["sessions"]:
                    all_sessions.append({
                        "vendor": "claude",
                        "project": p["name"],
                        "session_id": s["uuid"],
                        "path": str(s["path"]),
                        "date": s.get("modified", "")[:10],
                        "size": s["path"].stat().st_size if s["path"].exists() else 0,
                        "modified": s["modified"],
                        "lines": s.get("lines", 0),
                    })
        except Exception as e:
            pass

    # Codex CLI
    codex_mod = _import_vendor("extract-codex-sessions")
    if codex_mod:
        try:
            sessions = codex_mod.discover_sessions()
            for s in sessions:
                # Enrich project from session_meta cwd (first line)
                project = ""
                try:
                    with open(s["path"], encoding="utf-8", errors="replace") as sf:
                        for line in sf:
                            data = json.loads(line.strip())
                            if data.get("type") == "session_meta":
                                cwd = data.get("payload", {}).get("cwd", "")
                                if cwd:
                                    project = Path(cwd).name
                                break
                except Exception:
                    pass
                all_sessions.append({
                    "vendor": "codex",
                    "project": project,
                    "session_id": s["uuid"],
                    "path": str(s["path"]),
                    "date": s.get("date", ""),
                    "size": s.get("size", 0),
                    "modified": s["modified"],
                    "lines": s.get("lines", 0),
                })
        except Exception:
            pass

    # Gemini CLI
    gemini_mod = _import_vendor("extract-gemini-sessions")
    if gemini_mod:
        try:
            sessions = gemini_mod.discover_sessions()
            for s in sessions:
                all_sessions.append({
                    "vendor": "gemini",
                    "project": s.get("project", ""),
                    "session_id": s["uuid"],
                    "path": str(s["path"]),
                    "date": s.get("date", ""),
                    "size": s.get("size", 0),
                    "modified": s["modified"],
                    "lines": s.get("lines", 0),
                })
        except Exception:
            pass

    # Sort by modified date (most recent first)
    all_sessions.sort(key=lambda x: x.get("modified", ""), reverse=True)
    return all_sessions


# ---------------------------------------------------------------------------
# Spool state management
# ---------------------------------------------------------------------------

def load_exported_state():
    """Load the set of session IDs already exported to spool."""
    if not SPOOL_STATE_FILE.exists():
        return set()
    try:
        data = json.loads(SPOOL_STATE_FILE.read_text(encoding="utf-8"))
        return set(data.get("exported", []))
    except (json.JSONDecodeError, OSError):
        return set()


def save_exported_state(exported_ids):
    """Save the set of exported session IDs."""
    SPOOL_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "exported": sorted(exported_ids),
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    SPOOL_STATE_FILE.write_text(
        json.dumps(data, indent=2) + "\n",
        encoding="utf-8",
    )


def get_pending_sessions(all_sessions):
    """Return sessions not yet exported to spool."""
    exported = load_exported_state()
    return [s for s in all_sessions if f"{s['vendor']}-{_spool_slug(s['session_id'], s.get('path', ''))}" not in exported]


# ---------------------------------------------------------------------------
# Time filter
# ---------------------------------------------------------------------------

def parse_since(since_str):
    """Parse a --since argument like '24h', '7d', '1w' into a datetime."""
    if not since_str:
        return None

    match = re.match(r'^(\d+)\s*([hdwm])$', since_str.lower())
    if not match:
        # Try ISO date
        try:
            return datetime.fromisoformat(since_str).replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    value = int(match.group(1))
    unit = match.group(2)
    now = datetime.now(timezone.utc)

    if unit == "h":
        return now - timedelta(hours=value)
    elif unit == "d":
        return now - timedelta(days=value)
    elif unit == "w":
        return now - timedelta(weeks=value)
    elif unit == "m":
        return now - timedelta(days=value * 30)
    return None


def filter_sessions_since(sessions, since_dt):
    """Filter sessions modified after the given datetime."""
    if not since_dt:
        return sessions

    since_str = since_dt.strftime("%Y-%m-%d %H:%M")
    return [s for s in sessions if s.get("modified", "") >= since_str]


# ---------------------------------------------------------------------------
# Turn manifest extraction helpers (pure functions)
# ---------------------------------------------------------------------------

def extract_turn_text(turn):
    """Coerce turn content to a flat string."""
    content = turn.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(item.get("text", ""))
        return " ".join(parts)
    return str(content)


def extract_tool_types(turn):
    """Return sorted unique tool names from tool_calls."""
    tool_calls = turn.get("tool_calls", [])
    names = set()
    for tc in tool_calls:
        name = tc.get("tool", "") or tc.get("name", "")
        if name:
            names.add(name)
    return sorted(names)


def _make_preview(text, max_len=180):
    """Collapse whitespace and truncate to max_len."""
    collapsed = re.sub(r'\s+', ' ', text).strip()
    if len(collapsed) <= max_len:
        return collapsed
    return collapsed[:max_len - 3] + "..."


def extract_mentions_files(text):
    """Extract file mentions from text. Returns deduplicated list, cap 20."""
    files = []
    seen = set()

    # Backtick-quoted paths and double-quoted paths with extensions
    for m in re.finditer(r'[`"]([a-zA-Z0-9_./-]+\.[a-zA-Z]{1,10})[`"]', text):
        f = m.group(1)
        if f not in seen and not f.startswith("http"):
            seen.add(f)
            files.append(f)

    # Bare paths with code extensions (word boundary)
    code_exts = r'\.(py|js|ts|tsx|jsx|rs|go|java|rb|sh|md|yaml|yml|json|toml|sql|css|html)'
    for m in re.finditer(r'(?<![`"\w])([a-zA-Z0-9_][\w./-]*' + code_exts + r')(?![`"\w])', text):
        f = m.group(1)
        if f not in seen:
            seen.add(f)
            files.append(f)

    return files[:20]


def extract_mentions_functions(text):
    """Extract function/method mentions. Returns bare names, cap 20."""
    funcs = []
    seen = set()

    # foo() or Class.method() → bare name without parens
    for m in re.finditer(r'(?<!\w)([a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)*)\s*\(', text):
        name = m.group(1)
        # Skip common non-function patterns
        if name.lower() in ('if', 'for', 'while', 'return', 'print', 'and', 'or', 'not',
                             'in', 'is', 'with', 'as', 'from', 'import', 'class', 'elif',
                             'http', 'https', 'e', 'f', 'str', 'int', 'list', 'dict',
                             'set', 'type', 'len', 'range', 'true', 'false', 'none'):
            continue
        if name not in seen:
            seen.add(name)
            funcs.append(name)

    # def foo( → foo
    for m in re.finditer(r'\bdef\s+([a-zA-Z_]\w*)\s*\(', text):
        name = m.group(1)
        if name not in seen:
            seen.add(name)
            funcs.append(name)

    return funcs[:20]


def extract_keywords(text, top_n=8):
    """Extract top-N keywords by frequency, excluding stopwords."""
    from collections import Counter
    # Tokenize: alphanumeric words, 3+ chars
    words = re.findall(r'[a-zA-Z]{3,}', text.lower())
    filtered = [w for w in words if w not in STOPWORDS]
    counts = Counter(filtered)
    return [word for word, _ in counts.most_common(top_n)]


# ---------------------------------------------------------------------------
# Turn manifest build functions
# ---------------------------------------------------------------------------

def build_turn_record(turn):
    """Build a single manifest turn entry from a spool turn."""
    text = extract_turn_text(turn)
    return {
        "seq": turn.get("seq", 0),
        "role": turn.get("role", ""),
        "vendor_type": turn.get("item_type", "") or turn.get("type", turn.get("role", "")),
        "timestamp": turn.get("timestamp", ""),
        "chars": len(text),
        "has_tool_calls": bool(turn.get("tool_calls")),
        "tool_types": extract_tool_types(turn),
        "mentions_files": extract_mentions_files(text),
        "mentions_functions": extract_mentions_functions(text),
        "keywords": extract_keywords(text),
        "preview": _make_preview(text),
    }


def build_turn_manifest(session_export):
    """Build a full manifest dict from a spool export dict."""
    metadata = session_export.get("metadata", {})
    session_id = metadata.get("session_id", "")
    source_path = metadata.get("source_path", "") or ""
    row_key = _spool_slug(session_id, source_path)

    turns_raw = session_export.get("turns", [])
    # Ensure each turn has a seq number
    manifest_turns = []
    for i, turn in enumerate(turns_raw):
        if "seq" not in turn:
            turn = dict(turn, seq=i + 1)
        manifest_turns.append(build_turn_record(turn))

    return {
        "schema": "gator-turn-manifest-v1",
        "row_key": row_key,
        "session_id": session_id,
        "vendor": session_export.get("vendor", ""),
        "repo": metadata.get("repo", "") or metadata.get("project", ""),
        "source_path": source_path,
        "spool_file": "",  # filled by caller
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "turn_count": len(manifest_turns),
        "turns": manifest_turns,
    }


def write_turn_manifest(manifest, out_path):
    """Write manifest JSON to disk, creating parent dirs."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(manifest, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Spool loading helper
# ---------------------------------------------------------------------------

def _load_spool_sessions():
    """Scan SPOOL_DIR for valid spool exports, return (row_key, filename, data) tuples.

    Computes canonical row_key from file content, not filename.
    Skips files that fail validation.
    """
    results = []
    if not SPOOL_DIR.is_dir():
        return results

    for p in sorted(SPOOL_DIR.glob("*.json")):
        if p.name == ".exported.json":
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        if data.get("schema") != "gator-session-export-v1":
            continue

        metadata = data.get("metadata", {})
        session_id = metadata.get("session_id")
        if not session_id:
            continue

        source_path = metadata.get("source_path", "") or ""
        row_key = _spool_slug(session_id, source_path)
        results.append((row_key, p.name, data))

    return results


# ---------------------------------------------------------------------------
# Command: turn-manifest
# ---------------------------------------------------------------------------

def cmd_turn_manifest(args):
    """Generate turn manifests for spool exports."""
    spool_sessions = _load_spool_sessions()

    if not spool_sessions:
        print("  No spool exports found.")
        return

    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    count = 0

    for row_key, spool_filename, data in spool_sessions:
        manifest_path = MANIFEST_DIR / f"{row_key}.turns.json"

        # Filter by row-key
        if args.row_key and row_key != args.row_key:
            continue

        # Skip already-generated unless --force
        if manifest_path.exists() and not args.force:
            continue

        manifest = build_turn_manifest(data)
        manifest["spool_file"] = spool_filename
        write_turn_manifest(manifest, manifest_path)
        count += 1
        print(f"  ✓ {row_key[:8]} ({manifest['turn_count']} turns) → {manifest_path.name}")

    print()
    print(f"  Generated {count} turn manifests in {MANIFEST_DIR}")
    print()


# ---------------------------------------------------------------------------
# Command: grep-turns
# ---------------------------------------------------------------------------

def cmd_grep_turns(args):
    """Search turn manifests by file, function, keyword, vendor, repo, role."""
    if not MANIFEST_DIR.is_dir():
        print("  No turn manifests found. Run 'turn-manifest' first.")
        return

    matches = []

    for p in sorted(MANIFEST_DIR.glob("*.turns.json")):
        try:
            manifest = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        # Session-level filters
        if args.vendor and manifest.get("vendor") != args.vendor:
            continue
        if args.repo and manifest.get("repo") != args.repo:
            continue

        row_key = manifest.get("row_key", "")

        for turn in manifest.get("turns", []):
            # Turn-level filters (all must match)
            if args.file:
                import fnmatch
                if not any(fnmatch.fnmatch(f, args.file) for f in turn.get("mentions_files", [])):
                    continue
            if args.function:
                if not any(args.function in fn for fn in turn.get("mentions_functions", [])):
                    continue
            if args.keyword:
                if args.keyword.lower() not in turn.get("keywords", []):
                    continue
            if args.role:
                if turn.get("role") != args.role:
                    continue

            matches.append({
                "row_key": row_key,
                "seq": turn.get("seq", 0),
                "role": turn.get("role", ""),
                "preview": turn.get("preview", ""),
                "vendor": manifest.get("vendor", ""),
                "repo": manifest.get("repo", ""),
            })

    if args.json:
        print(json.dumps({"matches": matches, "count": len(matches)}, indent=2))
        return

    if not matches:
        print("  No matching turns found.")
        return

    print()
    print(f"  {len(matches)} matching turns")
    print()
    for m in matches:
        preview = m["preview"][:80]
        print(f"  {m['row_key'][:8]}  seq={m['seq']:<3}  {m['role']:<10}  {preview}")
    print()


# ---------------------------------------------------------------------------
# Command: show-turns
# ---------------------------------------------------------------------------

def cmd_show_turns(args):
    """Show full turn content from a spool export by sequence number."""
    row_key = args.row_key

    # Try to find spool file via manifest first (fast path)
    spool_data = None
    manifest_path = MANIFEST_DIR / f"{row_key}.turns.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            spool_name = manifest.get("spool_file", "")
            if spool_name:
                spool_path = SPOOL_DIR / spool_name
                if spool_path.exists():
                    spool_data = json.loads(spool_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    # Fallback: scan spool dir
    if spool_data is None:
        for rk, fname, data in _load_spool_sessions():
            if rk == row_key:
                spool_data = data
                break

    if spool_data is None:
        print(f"  No spool export found for row_key {row_key}")
        return

    turns = spool_data.get("turns", [])
    # Parse --seq
    requested = set()
    for part in args.seq.split(","):
        part = part.strip()
        if part:
            try:
                requested.add(int(part))
            except ValueError:
                pass

    # Expand with --context
    context_n = args.context or 0
    expanded = set()
    for seq in requested:
        for offset in range(-context_n, context_n + 1):
            expanded.add(seq + offset)

    # Print matching turns
    for i, turn in enumerate(turns):
        seq = turn.get("seq", i + 1)
        if seq not in expanded:
            continue

        role = turn.get("role", "unknown")
        ts = turn.get("timestamp", "")
        text = extract_turn_text(turn)

        print()
        print(f"  ── turn {seq} ({role}) {ts} ──")
        print()
        # Indent content
        for line in text.splitlines():
            print(f"  {line}")
    print()


# ---------------------------------------------------------------------------
# Command: index
# ---------------------------------------------------------------------------

def cmd_index(args):
    """Show all discoverable sessions across vendors."""
    sessions = discover_all_sessions()

    if args.since:
        since_dt = parse_since(args.since)
        sessions = filter_sessions_since(sessions, since_dt)

    if args.json:
        machine = get_machine_identity()
        output = {
            "schema": "gator-session-index-v1",
            "machine": machine,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sessions": [
                {**s, "row_key": _spool_slug(s["session_id"], s.get("path", ""))}
                for s in sessions
            ],
            "summary": {
                "total": len(sessions),
                "by_vendor": {},
            },
        }
        for s in sessions:
            v = s["vendor"]
            output["summary"]["by_vendor"][v] = output["summary"]["by_vendor"].get(v, 0) + 1
        print(json.dumps(output, indent=2, default=str))
        return

    # Text output
    print()
    print("  gator sessions index")
    print(f"  {len(sessions)} sessions discovered")
    print()

    by_vendor = {}
    for s in sessions:
        by_vendor.setdefault(s["vendor"], []).append(s)

    for vendor in sorted(by_vendor.keys()):
        items = by_vendor[vendor]
        print(f"  {vendor} ({len(items)} sessions)")
        for s in items[:10]:  # Show latest 10 per vendor
            project = s["project"]
            size_kb = s["size"] // 1024
            proj_str = f" [{project}]" if project else ""
            print(f"    {s['session_id'][:8]}  {s['date']}  {size_kb:>4} KB{proj_str}  {s['modified']}")
        if len(items) > 10:
            print(f"    ... and {len(items) - 10} more")
        print()

    exported = load_exported_state()
    pending = len([s for s in sessions if f"{s['vendor']}-{_spool_slug(s['session_id'], s.get('path', ''))}" not in exported])
    print(f"  pending export: {pending} sessions")
    print()


# ---------------------------------------------------------------------------
# Command: manifest
# ---------------------------------------------------------------------------

def cmd_manifest(args):
    """Emit JSON manifest for enterprise automation."""
    sessions = discover_all_sessions()

    if args.since:
        since_dt = parse_since(args.since)
        sessions = filter_sessions_since(sessions, since_dt)

    if args.pending:
        sessions = get_pending_sessions(sessions)

    machine = get_machine_identity()

    manifest = {
        "schema": "gator-session-manifest-v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "machine": {
            "id": machine.get("id", ""),
            "hostname": machine.get("hostname", ""),
            "label": machine.get("label", ""),
        },
        "sessions": [],
    }

    for s in sessions:
        spool_path = SPOOL_DIR / f"{s['vendor']}-{_spool_slug(s['session_id'], s.get('path', ''))}.json"
        row_key = _spool_slug(s["session_id"], s.get("path", ""))
        manifest["sessions"].append({
            "row_key": row_key,
            "session_id": s["session_id"],
            "vendor": s["vendor"],
            "project": s["project"],
            "date": s["date"],
            "modified": s["modified"],
            "size": s["size"],
            "source_path": s["path"],
            "spool_path": str(spool_path) if spool_path.exists() else None,
            "status": "exported" if spool_path.exists() else "pending",
        })

    print(json.dumps(manifest, indent=2, default=str))


# ---------------------------------------------------------------------------
# Command: export
# ---------------------------------------------------------------------------

def cmd_export(args):
    """Write normalized session exports to spool directory."""
    sessions = discover_all_sessions()

    if args.since:
        since_dt = parse_since(args.since)
        sessions = filter_sessions_since(sessions, since_dt)

    if args.pending:
        sessions = get_pending_sessions(sessions)

    if not sessions:
        print("  No sessions to export.")
        return

    SPOOL_DIR.mkdir(parents=True, exist_ok=True)
    machine = get_machine_identity()
    exported = load_exported_state()
    count = 0

    for s in sessions:
        vendor = s["vendor"]
        session_id = s["session_id"]
        source_path = s.get("path", "")
        spool_file = SPOOL_DIR / f"{vendor}-{_spool_slug(session_id, source_path)}.json"

        # Extract using vendor-specific script
        turns = []
        metadata = {}
        summary = {}

        try:
            if vendor == "claude":
                mod = _import_vendor("extract-claude-sessions")
                if mod:
                    raw_turns = mod.extract_session(Path(s["path"]))
                    meta = mod.extract_session_metadata(raw_turns)
                    summ = mod.format_session_summary(raw_turns, meta)
                    turns = raw_turns
                    metadata = meta
                    summary = summ

            elif vendor == "codex":
                mod = _import_vendor("extract-codex-sessions")
                if mod:
                    raw_turns, session_meta = mod.extract_session(Path(s["path"]))
                    meta = mod.extract_session_metadata(raw_turns, session_meta)
                    summ = mod.format_session_summary(raw_turns, meta)
                    turns = raw_turns
                    metadata = meta
                    summary = summ

            elif vendor == "gemini":
                mod = _import_vendor("extract-gemini-sessions")
                if mod:
                    raw_turns, session_meta = mod.extract_session(Path(s["path"]))
                    meta = mod.extract_session_metadata(raw_turns, session_meta, s["project"])
                    summ = mod.format_session_summary(raw_turns, meta)
                    turns = raw_turns
                    metadata = meta
                    summary = summ

        except Exception as e:
            print(f"  ! Error extracting {vendor}/{session_id[:8]}: {e}")
            continue

        if not turns:
            continue

        # Inject source_path for row_key / transcript path generation
        metadata["source_path"] = source_path

        # Apply redaction
        try:
            common = _import_vendor("gator-session-common")
            if common:
                redacted_turns = []
                for t in turns:
                    t_copy = dict(t)
                    t_copy["content"] = common.redact(t_copy.get("content", ""))
                    redacted_turns.append(t_copy)
                turns = redacted_turns

                # Redact summary fields (goal, decision texts)
                if summary:
                    if "goal" in summary:
                        summary["goal"] = common.redact(summary["goal"], summary_mode=True)
                    if "decisions" in summary:
                        for d in summary["decisions"]:
                            if "text" in d:
                                d["text"] = common.redact(d["text"], summary_mode=True)
        except Exception:
            pass  # Proceed without redaction if module unavailable

        # Write normalized export
        export_data = {
            "schema": "gator-session-export-v1",
            "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "machine": {
                "id": machine.get("id", ""),
                "hostname": machine.get("hostname", ""),
                "label": machine.get("label", ""),
            },
            "vendor": vendor,
            "metadata": metadata,
            "summary": summary,
            "turns": turns,
        }

        spool_file.write_text(
            json.dumps(export_data, indent=2, default=str) + "\n",
            encoding="utf-8",
        )

        exported.add(f"{vendor}-{_spool_slug(session_id, source_path)}")
        count += 1
        print(f"  ✓ {vendor}/{session_id[:8]} → {spool_file.name}")

    save_exported_state(exported)
    print()
    print(f"  Exported {count} sessions to {SPOOL_DIR}")
    print()


# ---------------------------------------------------------------------------
# Command: pending
# ---------------------------------------------------------------------------

def cmd_pending(args):
    """Show sessions not yet exported to spool."""
    sessions = discover_all_sessions()
    pending = get_pending_sessions(sessions)

    if args.json:
        print(json.dumps({
            "pending": len(pending),
            "total": len(sessions),
            "sessions": pending,
        }, indent=2, default=str))
        return

    print()
    print(f"  gator sessions pending")
    print(f"  {len(pending)} of {len(sessions)} sessions not yet exported")
    print()

    for s in pending[:20]:
        proj_str = f" [{s['project']}]" if s["project"] else ""
        print(f"    {s['vendor']:<8} {s['session_id'][:8]}  {s['date']}{proj_str}")

    if len(pending) > 20:
        print(f"    ... and {len(pending) - 20} more")
    print()

    if pending:
        print(f"  Run 'gator sessions export --pending' to export them.")
        print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Command: commit-summaries
# ---------------------------------------------------------------------------

def cmd_commit_summaries(args):
    """Write git-tracked session summaries to .gator/sessions/.

    This is the committed summary layer — the durable, portable,
    signed audit trail. Unlike the spool (local, ephemeral), these
    summaries travel with the repo via git.

    The audit dashboard reads from these instead of raw vendor logs,
    making it work on any machine with the git repo.
    """
    # Find target directory
    if args.path:
        sessions_dir = Path(args.path)
    else:
        # Default: .gator/sessions/ in the current repo
        gator_dir = Path.cwd() / ".gator"
        if not gator_dir.is_dir():
            # Try command post
            for candidate in [Path.cwd(), Path.cwd().parent]:
                if (candidate / "gator-command").is_dir():
                    gator_dir = candidate / ".gator"
                    break
        sessions_dir = gator_dir / "sessions"

    sessions_dir.mkdir(parents=True, exist_ok=True)

    # Discover sessions
    all_sessions = discover_all_sessions()

    if args.since:
        since_dt = parse_since(args.since)
        all_sessions = filter_sessions_since(all_sessions, since_dt)

    if not all_sessions:
        print("  No sessions to commit.")
        return

    # Track what's already committed (by filename)
    existing = {f.name for f in sessions_dir.iterdir() if f.suffix == ".md"}

    common = _import_vendor("gator-session-common")
    if not common:
        print("  Error: gator-session-common.py not available.", file=sys.stderr)
        return

    written = 0
    skipped = 0

    for s in all_sessions:
        vendor = s["vendor"]
        session_id = s["session_id"]
        source_path = s.get("path", "")

        # Generate deterministic filename
        row_key = common.make_row_key({
            "session_id": session_id,
            "source_path": source_path,
        })
        date_str = s.get("date", "unknown")
        project = s.get("project", "unknown") or "unknown"
        filename = f"{date_str}-{project}-{vendor}-{row_key}.md"

        if filename in existing and not args.force:
            skipped += 1
            continue

        # Extract and format summary
        try:
            turns = []
            metadata = {}

            if vendor == "claude":
                mod = _import_vendor("extract-claude-sessions")
                if mod:
                    turns = mod.extract_session(Path(source_path))
                    metadata = mod.extract_session_metadata(turns)

            elif vendor == "codex":
                mod = _import_vendor("extract-codex-sessions")
                if mod:
                    turns, session_meta = mod.extract_session(Path(source_path))
                    metadata = mod.extract_session_metadata(turns, session_meta)

            elif vendor == "gemini":
                mod = _import_vendor("extract-gemini-sessions")
                if mod:
                    turns, session_meta = mod.extract_session(Path(source_path))
                    metadata = mod.extract_session_metadata(turns, session_meta, project)

            if not turns:
                continue

            # Inject source path for row_key generation
            metadata["source_path"] = source_path

            # Generate summary markdown using the canonical formatter
            summary_md = common.format_summary_markdown(turns, metadata)

            # Write to .gator/sessions/
            summary_file = sessions_dir / filename
            summary_file.write_text(summary_md, encoding="utf-8")
            written += 1

            if not args.quiet:
                print(f"  ✓ {filename}")

        except (OSError, KeyError, ValueError, UnicodeDecodeError) as e:
            print(f"  ! {vendor}/{session_id[:8]}: {type(e).__name__}: {e}")
            continue

    print()
    print(f"  Committed: {written} summaries to {sessions_dir}")
    if skipped:
        print(f"  Skipped:   {skipped} (already exist, use --force to overwrite)")
    print()


def parse_committed_summary(text, filename=""):
    """Parse a single committed summary markdown into a structured dict.

    Handles two schema types:
    - gator-session-summary-v1: from archaeology (gator sessions commit-summaries)
    - gator-commit-summary-v1: from pre-commit hook (structural, automatic)

    Returns a dict with: date, repo, vendor, decisions, goal, source_file, start.
    Returns None if the text has no parseable frontmatter.

    This is the canonical parser for committed summaries. Used by both
    the local read path (read_committed_summaries) and the remote read
    path (gator_remote + gator-audit.py). Do not duplicate this logic.
    """
    import re

    meta = {}
    decisions = []
    goal_lines = []
    in_frontmatter = False
    in_decisions = False
    in_goal = False

    for line in text.splitlines():
        stripped = line.strip()

        if stripped == "---":
            if not in_frontmatter:
                in_frontmatter = True
                continue
            else:
                in_frontmatter = False
                continue

        if in_frontmatter and ":" in stripped:
            key, _, value = stripped.partition(":")
            meta[key.strip()] = value.strip()
            continue

        if stripped == "## Goal":
            in_goal = True
            in_decisions = False
            continue
        elif stripped == "## Decisions":
            in_goal = False
            in_decisions = True
            continue
        elif stripped.startswith("## "):
            in_goal = False
            in_decisions = False
            continue

        if in_goal and stripped and stripped != "*No goal extracted*":
            goal_lines.append(stripped)

        if in_decisions and stripped.startswith("- "):
            # Parse decision: - [timestamp] text
            m = re.match(r'^- \[([^\]]*)\]\s*(.*)', stripped)
            if m:
                decisions.append({
                    "timestamp": m.group(1),
                    "text": m.group(2),
                })
            elif stripped != "- *No decisions extracted*":
                decisions.append({
                    "timestamp": meta.get("date", ""),
                    "text": stripped[2:],
                })

    if not meta:
        return None

    return {
        "date": meta.get("date", ""),
        "repo": meta.get("repo", ""),
        "vendor": meta.get("vendor", ""),
        "agent": meta.get("agent", ""),
        "goal": " ".join(goal_lines),
        "decisions": decisions,
        "source_file": filename,
        "start": meta.get("start", meta.get("timestamp", "")),
    }


def read_committed_summaries(sessions_dir, since_days=7):
    """Read committed summaries from .gator/sessions/.

    Returns a list of dicts with: date, repo, vendor, decisions, goal.
    This is the durable read path for gator audit — no vendor parsers,
    no local tool storage, just git-tracked markdown.
    """
    if not sessions_dir.is_dir():
        return []

    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%Y-%m-%d")

    summaries = []
    for f in sorted(sessions_dir.iterdir(), reverse=True):
        if not f.suffix == ".md":
            continue

        # Quick date filter from filename (YYYY-MM-DD-repo-vendor-hash.md)
        name = f.name
        if len(name) >= 10 and name[:10] < cutoff:
            continue

        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        result = parse_committed_summary(text, f.name)
        if result:
            summaries.append(result)

    return summaries


def main():
    if sys.stdout.encoding != "utf-8":
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )

    parser = argparse.ArgumentParser(
        description="Gator sessions — audit infrastructure for AI coding sessions."
    )
    sub = parser.add_subparsers(dest="command", help="Command")

    # index
    idx = sub.add_parser("index", help="Show all discoverable sessions")
    idx.add_argument("--json", "-j", action="store_true")
    idx.add_argument("--since", help="Filter by recency (e.g., 24h, 7d, 1w)")

    # manifest
    mfst = sub.add_parser("manifest", help="Emit JSON manifest for automation")
    mfst.add_argument("--since", help="Filter by recency")
    mfst.add_argument("--pending", action="store_true", help="Only pending sessions")

    # export
    exp = sub.add_parser("export", help="Export sessions to spool directory")
    exp.add_argument("--since", help="Filter by recency")
    exp.add_argument("--pending", action="store_true", help="Only pending sessions")

    # pending
    pnd = sub.add_parser("pending", help="Show sessions not yet exported")
    pnd.add_argument("--json", "-j", action="store_true")

    # commit-summaries
    cs = sub.add_parser("commit-summaries", help="Write git-tracked summaries to .gator/sessions/")
    cs.add_argument("--since", help="Filter by recency (e.g., 7d, 30d)")
    cs.add_argument("--path", help="Target directory (default: .gator/sessions/)")
    cs.add_argument("--force", action="store_true", help="Overwrite existing summaries")
    cs.add_argument("--quiet", "-q", action="store_true", help="Suppress per-file output")

    # turn-manifest
    tm = sub.add_parser("turn-manifest", help="Generate turn manifests from spool exports")
    tm.add_argument("--row-key", help="Generate for a specific row key")
    tm.add_argument("--force", action="store_true", help="Overwrite existing manifests")

    # grep-turns
    gt = sub.add_parser("grep-turns", help="Search turn manifests")
    gt.add_argument("--file", help="Match file mentions (fnmatch pattern)")
    gt.add_argument("--function", help="Match function mentions (substring)")
    gt.add_argument("--keyword", help="Match keywords (exact)")
    gt.add_argument("--vendor", help="Filter by vendor")
    gt.add_argument("--repo", help="Filter by repo")
    gt.add_argument("--role", help="Filter by role")
    gt.add_argument("--json", "-j", action="store_true", help="JSON output")

    # show-turns
    st = sub.add_parser("show-turns", help="Show full turn content from spool exports")
    st.add_argument("--row-key", required=True, help="Session row key")
    st.add_argument("--seq", required=True, help="Turn sequence numbers (comma-separated)")
    st.add_argument("--context", type=int, default=0, help="Number of surrounding turns to show")

    args = parser.parse_args()

    if args.command == "index":
        cmd_index(args)
    elif args.command == "manifest":
        cmd_manifest(args)
    elif args.command == "export":
        cmd_export(args)
    elif args.command == "pending":
        cmd_pending(args)
    elif args.command == "commit-summaries":
        cmd_commit_summaries(args)
    elif args.command == "turn-manifest":
        cmd_turn_manifest(args)
    elif args.command == "grep-turns":
        cmd_grep_turns(args)
    elif args.command == "show-turns":
        cmd_show_turns(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
