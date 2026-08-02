#!/usr/bin/env python3
"""
gator repo-status — Per-repo governance status as structured JSON.

Provides a deep view of a single governed repo for the Gator Dashboard
Repo View: charter coverage (based on Covers: declarations), stale
charters, recent governed commits with full trailer data, override events,
and session summary count.

Charter coverage %:
    (git-tracked source files appearing in at least one charter's Covers:
    declaration) / (total git-tracked source files, excluding test and
    generated files) * 100

    Coverage is based on explicit Covers: declarations, not mere charter
    file presence. A charter file existing does not mean source files are
    covered — only files listed in Covers: count.

Charter staleness:
    A charter is stale if any source file in its Covers: declaration has a
    git commit timestamp newer than the charter file's own last git commit.

Usage:
    python gator-command/scripts/gator-repo-status.py
    python gator-command/scripts/gator-repo-status.py --repo dangerous-golf
    python gator-command/scripts/gator-repo-status.py --path /abs/path/to/repo
    python gator-command/scripts/gator-repo-status.py --json
    python gator-command/scripts/gator-repo-status.py --json --repo code-wizard

@reads: .gator/ state, git history, .gator/charters/, .gator/sessions/
@writes: stdout only
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from gator_core import (
    get_version, find_command_post, normalize_path, parse_registry,
    git, ensure_utf8_stdout,
)
from gator_layout import get_gator_paths

VERSION = get_version()

# Files excluded from the charter coverage denominator.
# Applied to paths as returned by git ls-files (relative to repo root).
_EXCLUDE_PATTERNS = [
    re.compile(r'(^|/)tests?/', re.I),
    re.compile(r'_test\.(py|js|ts|go|rb|java)$', re.I),
    re.compile(r'^test_.*\.(py|js|ts|go|rb|java)$', re.I),
    re.compile(r'(^|/)(dist|build|__pycache__|\.pytest_cache|node_modules)/', re.I),
    re.compile(r'\.(generated|gen)\.(py|js|ts|go)$', re.I),
]

# Charter filenames to skip when scanning .gator/charters/
_CHARTER_SKIP = {"_template.md", "README.md", "INDEX.md", ".gitkeep"}

# Number of recent governed commits to return in recent_trailers
_RECENT_LIMIT = 20

# Lookback window in days for trailer and override scanning
_LOOKBACK_DAYS = 30


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unix_to_utc(ts_str):
    """Convert a Unix timestamp string to UTC ISO 8601.

    Returns empty string on parse failure.

    Use %at in git log formats to get Unix timestamps — never %ai/%aI,
    which embed a local offset that str truncation would mislabel as UTC.
    """
    try:
        return datetime.fromtimestamp(
            int(ts_str.strip()), tz=timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, OSError):
        return ""


def _is_source_file(path_str):
    """Return True if path should count toward the charter coverage denominator."""
    for pattern in _EXCLUDE_PATTERNS:
        if pattern.search(path_str):
            return False
    return True


def _parse_covers(charter_text):
    """Extract file/directory paths from a charter's **Covers**: line.

    Handles the canonical format:
        **Covers**: `path/to/file.py`, `path/to/dir/`

    Returns a list of path strings (stripped of backticks).
    """
    for line in charter_text.splitlines():
        if re.match(r'^\*\*Covers\*\*:', line.strip()):
            return re.findall(r'`([^`]+)`', line)
    return []


def _file_last_commit_ts(repo_path, rel_path):
    """Return the Unix timestamp of the last commit touching rel_path.

    Returns None if git log fails or the file has no commits.
    """
    raw, ok = git("log", "-1", "--format=%at", "--", rel_path, cwd=repo_path)
    if not ok or not raw.strip():
        return None


def _hook_probe_dirs(repo_path):
    """Return hook directories to probe, preferring the managed strategy."""
    try:
        from gator_core import import_sibling
        update = import_sibling("gator-update")
        if update:
            return update.get_hook_probe_dirs(repo_path)
    except Exception:
        pass
    return [repo_path / ".git" / "hooks"]
    try:
        return int(raw.strip())
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Hook status
# ---------------------------------------------------------------------------

def get_hook_status(repo_path):
    """Return hook installation status for a governed repo.

    Returns:
        "present"     — hook sources or installed hook detected
        "missing"     — .gator/ exists but no hooks found
        "ungoverned"  — no .gator/ directory
    """
    paths = get_gator_paths(repo_path)
    if paths.layout == "invalid":
        return "ungoverned"

    hooks_src = paths.scripts_dir / "hooks"
    git_hooks = _hook_probe_dirs(repo_path)

    has_sources = hooks_src.is_dir() and any(hooks_src.iterdir())
    has_installed = any(
        hooks_dir.is_dir() and (
            (hooks_dir / "pre-commit").exists() or
            (hooks_dir / "commit-msg").exists()
        )
        for hooks_dir in git_hooks
    )

    return "present" if (has_sources or has_installed) else "missing"


# ---------------------------------------------------------------------------
# Charter coverage
# ---------------------------------------------------------------------------

def get_charter_coverage(repo_path):
    """Compute charter coverage % and identify stale charters.

    Coverage definition:
        (source files appearing in at least one charter's Covers: declaration)
        / (total git-tracked source files, excluding test/generated files) * 100

    Staleness definition:
        A charter is stale if any covered source file has a git commit
        timestamp newer than the charter file's own last git commit.

    Returns a dict:
        charter_count       — number of charter files (excluding templates)
        charter_coverage_pct — float (0–100), or None if no source files
        stale_charters      — list of stale charter dicts
        covered_files       — set of covered source file paths (internal use)
    """
    paths = get_gator_paths(repo_path)
    charters_dir = paths.charters_dir

    result = {
        "charter_count": 0,
        "charter_coverage_pct": None,
        "stale_charters": [],
    }

    # Get all git-tracked source files
    ls_out, ok = git("ls-files", cwd=repo_path)
    if not ok:
        return result

    all_source_files = set(
        p for p in ls_out.splitlines()
        if p.strip() and _is_source_file(p.strip())
    )
    if not all_source_files:
        result["charter_coverage_pct"] = 0.0
        return result

    if not charters_dir.is_dir():
        result["charter_coverage_pct"] = 0.0
        return result

    charter_files = [
        f for f in charters_dir.iterdir()
        if f.suffix == ".md" and f.name not in _CHARTER_SKIP
    ]
    result["charter_count"] = len(charter_files)

    if not charter_files:
        result["charter_coverage_pct"] = 0.0
        return result

    covered_files = set()
    stale_charters = []

    for charter_path in charter_files:
        try:
            text = charter_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        covers = _parse_covers(text)
        if not covers:
            continue

        # Resolve covered source files — each Covers: entry may be a file
        # path or a directory prefix. Match against git ls-files output.
        charter_covered = set()
        for cover in covers:
            cover = cover.rstrip("/")
            for sf in all_source_files:
                if sf == cover or sf.startswith(cover + "/"):
                    charter_covered.add(sf)

        covered_files |= charter_covered

        # Staleness check: compare charter's last commit vs each covered file
        charter_rel = str(charter_path.relative_to(repo_path)).replace("\\", "/")
        charter_ts = _file_last_commit_ts(repo_path, charter_rel)
        if charter_ts is None:
            # Charter has no commits yet — not stale (not yet in history)
            continue

        stale_covers = []
        latest_source_ts = None
        for sf in charter_covered:
            src_ts = _file_last_commit_ts(repo_path, sf)
            if src_ts is not None:
                if latest_source_ts is None or src_ts > latest_source_ts:
                    latest_source_ts = src_ts
                if src_ts > charter_ts:
                    stale_covers.append(sf)

        if stale_covers:
            stale_charters.append({
                "charter": charter_rel,
                "covers": list(charter_covered),
                "stale_sources": sorted(stale_covers),
                "charter_modified": _unix_to_utc(str(charter_ts)),
                "source_last_commit": _unix_to_utc(
                    str(latest_source_ts) if latest_source_ts else ""
                ),
            })

    pct = round(len(covered_files) / len(all_source_files) * 100, 1)
    result["charter_coverage_pct"] = pct
    result["stale_charters"] = stale_charters
    return result


# ---------------------------------------------------------------------------
# Trailer scanning
# ---------------------------------------------------------------------------

def get_trailer_data(repo_path, lookback_days=_LOOKBACK_DAYS, limit=_RECENT_LIMIT):
    """Scan git log for governed commits in the lookback window.

    Returns:
        last_governed_commit  — most recent commit with Gator-* trailers
        recent_trailers       — list of up to `limit` governed commits
        override_events       — commits with Gator-Override: trailer
    """
    since_str = f"{lookback_days} days ago"

    # TRIPWIRE: Use %at (Unix timestamp), not %ai or %aI.
    # %ai embeds a local timezone offset; truncating to 19 chars and
    # appending Z mislabels local time as UTC. %at is always UTC-unambiguous.
    #
    # TRIPWIRE: Do NOT call str.strip() on blocks before splitting on \x1f.
    # Python treats \x1f (chr(31), unit separator) as whitespace — strip()
    # removes the leading field separator and collapses 4 parts to 3.
    import subprocess as _sp
    try:
        proc = _sp.run(
            [
                "git", "log", f"--since={since_str}",
                "--format=COMMIT\x1f%H\x1f%at\x1f%(trailers:separator=\x1e)",
            ],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (_sp.TimeoutExpired, OSError):
        return None, [], []

    if proc.returncode != 0:
        return None, [], []

    last_governed = None
    recent_trailers = []
    override_events = []

    for block in proc.stdout.split("COMMIT"):
        # Do NOT strip block here — see TRIPWIRE above.
        if not block:
            continue
        parts = block.split("\x1f")
        if len(parts) < 4:
            continue

        commit_hash = parts[1].strip()
        commit_ts = _unix_to_utc(parts[2].strip())
        trailers_raw = parts[3]

        # Parse trailer lines
        trailer_dict = {}
        for line in (t.strip() for t in trailers_raw.split("\x1e") if t.strip()):
            if ":" in line:
                k, _, v = line.partition(":")
                trailer_dict[k.strip()] = v.strip()

        # Skip commits without Gator-* trailers
        if not any(k.startswith("Gator-") for k in trailer_dict):
            continue

        entry = {
            "hash": commit_hash[:7],
            "timestamp": commit_ts,
            "significance": trailer_dict.get("Gator-Significance", ""),
            "change_type": trailer_dict.get("Gator-Change-Type", ""),
            "charter_changed": trailer_dict.get("Gator-Charter-Changed", "") not in ("no", ""),
            "override": bool(trailer_dict.get("Gator-Override", "")),
            "agent": trailer_dict.get("Gator-Agent", ""),
            "architect": trailer_dict.get("Gator-Architect", trailer_dict.get("Gator-PI", "")),
        }

        # last_governed_commit — first one encountered (log is newest-first)
        if last_governed is None:
            last_governed = {
                "hash": entry["hash"],
                "timestamp": entry["timestamp"],
                "agent": entry["agent"],
                "architect": entry["architect"],
                "significance": entry["significance"],
                "change_type": entry["change_type"],
            }

        # recent_trailers — up to limit
        if len(recent_trailers) < limit:
            recent_trailers.append(entry)

        # Override events
        override_val = trailer_dict.get("Gator-Override", "")
        if override_val:
            override_events.append({
                "hash": commit_hash[:7],
                "timestamp": commit_ts,
                "override_type": override_val,
                # Approver is Gator-Override-Approved-By, not Gator-PI.
                # The hook writes this from .override-meta.json — it records
                # who ran gator-approve.py, which may differ from the session Architect.
                "approver": trailer_dict.get("Gator-Override-Approved-By", ""),
                "block_id": trailer_dict.get("Gator-Override-Block", ""),
            })

    return last_governed, recent_trailers, override_events


# ---------------------------------------------------------------------------
# Session summary count
# ---------------------------------------------------------------------------

def get_session_summaries(repo_path, limit=20):
    """Read committed session summaries via the canonical parser.

    Returns (total_count, recent_items) where total_count is the number
    of parseable summaries and recent_items is up to `limit` items
    (newest first) with metadata for dashboard display.

    Uses read_committed_summaries() from gator-sessions.py — the same
    parser used by gator-audit.py. This ensures the count and the panel
    are consistent: both reflect only files that pass the canonical parser.
    """
    sessions_dir = repo_path / ".gator" / "sessions"
    if not sessions_dir.is_dir():
        return 0, []

    try:
        from gator_core import import_sibling
        sessions_mod = import_sibling("gator-sessions")
    except (ImportError, Exception):
        return 0, []

    if sessions_mod is None:
        return 0, []

    # Read all summaries (since_days=9999 effectively means no time cutoff)
    summaries = sessions_mod.read_committed_summaries(sessions_dir, since_days=9999)

    items = []
    for s in summaries:
        items.append({
            "date": s.get("date", ""),
            "start": s.get("start", ""),
            "repo": s.get("repo", ""),
            "vendor": s.get("vendor", ""),
            "agent": s.get("agent", ""),
            "goal": s.get("goal", ""),
            "decisions_count": len(s.get("decisions", [])),
            "source_file": s.get("source_file", ""),
            "source_kind": "local-repo",
        })

    # Sort by (start, date, source_file) descending
    items.sort(
        key=lambda x: (x.get("start", "") or x.get("date", ""), x.get("source_file", "")),
        reverse=True,
    )
    return len(items), items[:limit]


# ---------------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------------

def scan_repo_status(repo_path, repo_name=None):
    """Assemble the full repo-status dict for a single governed repo.

    Returns a dict matching the gator-repo-status JSON schema.
    """
    repo_path = Path(repo_path).resolve()
    name = repo_name or repo_path.name

    data = {
        "schema": "gator-repo-status-v1",
        "repo": name,
        "path": str(repo_path),
        "accessible": repo_path.is_dir(),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    if not data["accessible"]:
        return data

    # Branch
    branch, ok = git("branch", "--show-current", cwd=repo_path)
    data["branch"] = branch if ok and branch else "unknown"

    # Hook status
    data["hook_status"] = get_hook_status(repo_path)

    # Charter coverage + staleness
    coverage = get_charter_coverage(repo_path)
    data["charter_count"] = coverage["charter_count"]
    data["charter_coverage_pct"] = coverage["charter_coverage_pct"]
    data["stale_charters"] = coverage["stale_charters"]

    # Trailer data: last governed commit, recent trailers, override events
    last_governed, recent_trailers, override_events = get_trailer_data(repo_path)
    data["last_governed_commit"] = last_governed
    data["recent_trailers"] = recent_trailers
    data["override_events"] = override_events

    # Session summary count + recent summaries (both from canonical parser)
    summary_count, recent_summaries = get_session_summaries(repo_path)
    data["session_summary_count"] = summary_count
    data["recent_session_summaries"] = recent_summaries

    # Enforcement config
    config_path = repo_path / ".gator" / "config.json"
    config = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    data["config"] = config

    # Topology
    try:
        from gator_core import get_repo_topology
        data["topology"] = get_repo_topology(repo_path / ".gator")
    except ImportError:
        data["topology"] = "unknown"

    # CLI version from .gator-version (tracks which gator version gatorized this repo)
    gator_version_file = repo_path / ".gator" / ".gator-version"
    if gator_version_file.exists():
        try:
            for line in gator_version_file.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("cli-version:"):
                    data["cli_version"] = line.split(":", 1)[1].strip()
                    break
        except OSError:
            pass

    return data


# ---------------------------------------------------------------------------
# Repo resolution
# ---------------------------------------------------------------------------

def resolve_repo(repo_name=None, repo_path_arg=None):
    """Find a repo path + name from --repo or --path argument.

    Resolution order:
    1. --path given → use directly, infer name from directory
    2. --repo given → look up in registry by name
    3. Neither → use current working directory
    """
    if repo_path_arg:
        p = Path(normalize_path(repo_path_arg)).resolve()
        return p, p.name

    if repo_name:
        cp = find_command_post()
        if cp:
            for entry in parse_registry(cp):
                if entry["name"] == repo_name:
                    return Path(normalize_path(entry["path"])).resolve(), entry["name"]
        print(f"  Error: repo '{repo_name}' not found in registry.", file=sys.stderr)
        sys.exit(1)

    # Default: current working directory
    cwd = Path.cwd().resolve()
    return cwd, cwd.name


# ---------------------------------------------------------------------------
# Text output
# ---------------------------------------------------------------------------

def render_text(data):
    """Render repo-status as human-readable terminal output."""
    lines = [""]

    accessible = data.get("accessible", False)
    name = data.get("repo", "?")
    path = data.get("path", "?")

    lines.append(f"  gator repo-status: {name}")
    lines.append(f"  {data.get('generated_at', '')}  |  {VERSION}")
    lines.append("")

    if not accessible:
        lines.append(f"  ✗ {path} — NOT ACCESSIBLE")
        lines.append("")
        return "\n".join(lines)

    # Overview
    branch = data.get("branch", "?")
    hook = data.get("hook_status", "?")
    hook_indicator = "✓" if hook == "present" else ("✗" if hook == "missing" else "·")
    lines.append(f"  Branch: {branch}   Hooks: {hook_indicator} {hook}")
    lines.append("")

    # Charter coverage
    pct = data.get("charter_coverage_pct")
    count = data.get("charter_count", 0)
    pct_str = f"{pct}%" if pct is not None else "n/a"
    stale = data.get("stale_charters", [])
    stale_indicator = f"  ⚠ {len(stale)} stale" if stale else ""
    lines.append(f"  CHARTERS: {count} charters  |  Coverage: {pct_str}{stale_indicator}")
    if stale:
        for s in stale:
            lines.append(f"    ⚠ {s['charter']}")
            for src in s.get("stale_sources", [])[:3]:
                lines.append(f"        source newer: {src}")
    lines.append("")

    # Last governed commit
    lgc = data.get("last_governed_commit")
    if lgc:
        lines.append(f"  LAST GOVERNED COMMIT: {lgc['hash']}  {lgc.get('timestamp', '')[:10]}")
        lines.append(f"    Agent: {lgc.get('agent', '?')}   Architect: {lgc.get('architect', '?')}")
        lines.append(f"    Significance: {lgc.get('significance', '?')}   Type: {lgc.get('change_type', '?')}")
    else:
        lines.append(f"  LAST GOVERNED COMMIT: none in last {_LOOKBACK_DAYS} days")
    lines.append("")

    # Recent trailers summary
    trailers = data.get("recent_trailers", [])
    if trailers:
        lines.append(f"  RECENT GOVERNED COMMITS ({len(trailers)} in last {_LOOKBACK_DAYS} days)")
        for t in trailers[:5]:
            override_flag = " [OVERRIDE]" if t.get("override") else ""
            charter_flag = " [charter]" if t.get("charter_changed") else ""
            lines.append(
                f"    {t['hash']}  {t.get('timestamp', '')[:10]}"
                f"  {t.get('significance', '?'):8}  {t.get('change_type', '?')}"
                f"{charter_flag}{override_flag}"
            )
        if len(trailers) > 5:
            lines.append(f"    ... and {len(trailers) - 5} more")
    else:
        lines.append(f"  RECENT GOVERNED COMMITS: none in last {_LOOKBACK_DAYS} days")
    lines.append("")

    # Overrides
    overrides = data.get("override_events", [])
    if overrides:
        lines.append(f"  OVERRIDE EVENTS ({len(overrides)})")
        for o in overrides:
            approver = f"  approver: {o['approver']}" if o.get("approver") else ""
            lines.append(f"    {o['hash']}  {o.get('timestamp', '')[:10]}  {o.get('override_type', '?')}{approver}")
        lines.append("")

    # Sessions
    session_count = data.get("session_summary_count", 0)
    lines.append(f"  SESSION SUMMARIES: {session_count}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    ensure_utf8_stdout()

    parser = argparse.ArgumentParser(
        description="Gator repo-status — per-repo governance status."
    )
    parser.add_argument(
        "--repo", "-r",
        help="Repo name from registry (e.g. dangerous-golf)",
    )
    parser.add_argument(
        "--path", "-p",
        help="Absolute path to repo (alternative to --repo)",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON",
    )
    args = parser.parse_args()

    repo_path, repo_name = resolve_repo(
        repo_name=args.repo,
        repo_path_arg=getattr(args, "path", None),
    )

    data = scan_repo_status(repo_path, repo_name)

    if args.json:
        print(json.dumps(data, indent=2, default=str))
    else:
        print(render_text(data))


if __name__ == "__main__":
    main()
