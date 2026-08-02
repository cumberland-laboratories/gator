#!/usr/bin/env python3
"""
gator fleet-intel — generate per-repo intelligence summaries for the command post.

Reads fleet state (git history, .gator/ files, committed summaries, trailers)
and produces structured intelligence profiles in gator-command/threads/.

Usage:
    python gator-fleet-intel.py                 # update all repo profiles
    python gator-fleet-intel.py --repo NAME     # update one repo
    python gator-fleet-intel.py --json          # JSON output instead of files
    python gator-fleet-intel.py --dry-run       # show what would be written

This script synthesizes, it does not invent. Every field is derived from
observable git/file state — no LLM inference, no fabrication.

**Limitation**: currently requires local repo checkouts. Remote-only repos
(accessible via thin-fetch / bare cache) are skipped. Future: add remote
profiling via gator_remote.py to match fleet-report's remote capability.

@reads: gator-command/registry.md, .gator/ in each repo, git history,
        .gator/sessions/*.md (committed summaries)
@writes: gator-command/threads/repo-*.md
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from gator_core import (
    get_version, find_command_post, normalize_path, parse_registry,
    git, ensure_utf8_stdout,
)
from gator_layout import get_gator_paths

VERSION = get_version()


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def get_recent_commits(repo_path, days=30, limit=20):
    """Get recent commit messages with dates and trailers."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    log, ok = git(
        "log", "--format=%H|%s|%ci|%(trailers:key=Gator-Change-Type,valueonly)",
        f"--since={since}", f"-{limit}", "dev",
        cwd=repo_path,
    )
    if not ok:
        log, ok = git(
            "log", "--format=%H|%s|%ci|%(trailers:key=Gator-Change-Type,valueonly)",
            f"--since={since}", f"-{limit}",
            cwd=repo_path,
        )
    if not ok:
        return []

    commits = []
    for line in log.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("|", 3)
        if len(parts) >= 3:
            commits.append({
                "hash": parts[0][:8],
                "message": parts[1].strip(),
                "date": parts[2].strip()[:10],
                "change_type": parts[3].strip() if len(parts) > 3 else "",
            })
    return commits


def get_commit_frequency(repo_path):
    """Compute commit frequency stats."""
    counts = {}
    for days_label, days in [("7d", 7), ("30d", 30)]:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        out, ok = git("rev-list", "--count", f"--since={since}", "HEAD", cwd=repo_path)
        counts[days_label] = int(out.strip()) if ok and out.strip().isdigit() else 0
    return counts


def get_change_type_distribution(commits):
    """Count change types from trailer data."""
    types = {}
    for c in commits:
        ct = c.get("change_type", "").strip()
        if ct:
            types[ct] = types.get(ct, 0) + 1
    return types


def read_mission(repo_path):
    """Read mission summary from mission.md (resolved by layout)."""
    paths = get_gator_paths(repo_path)
    for candidate in [
        paths.mission,
        repo_path / "gator-command" / "mission.md",
    ]:
        if candidate.exists():
            text = candidate.read_text(encoding="utf-8", errors="replace")
            lines = []
            for line in text.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and not stripped.startswith("["):
                    lines.append(stripped)
                    if len(lines) >= 3:
                        break
            return " ".join(lines)[:300] if lines else ""
    return ""


def read_charter_names(repo_path):
    """Read charter file names (minus templates/index)."""
    paths = get_gator_paths(repo_path)
    charters_dir = paths.charters_dir
    if not charters_dir.is_dir():
        return []
    skip = {"_template.md", "README.md", "INDEX.md"}
    return sorted(f.stem for f in charters_dir.glob("*.md") if f.name not in skip)


def read_active_threads(repo_path):
    """Read active thread names from active-threads/ (resolved by layout)."""
    paths = get_gator_paths(repo_path)
    threads_dir = paths.active_threads_dir
    if not threads_dir.is_dir():
        return []
    return sorted(f.stem for f in threads_dir.glob("*.md"))


def read_issues_count(repo_path):
    """Count open issues from issues.md (resolved by layout)."""
    paths = get_gator_paths(repo_path)
    issues_file = paths.issues
    if not issues_file.exists():
        return 0
    text = issues_file.read_text(encoding="utf-8", errors="replace")
    return text.lower().count("**status**: open")


def read_committed_decisions(repo_path, days=30):
    """Read decisions from committed session summaries."""
    paths = get_gator_paths(repo_path)
    sessions_dir = paths.gator_root / "sessions"
    if not sessions_dir.is_dir():
        return []

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    decisions = []

    for f in sorted(sessions_dir.glob("*.md"), reverse=True):
        if f.name.startswith("_"):
            continue
        if len(f.name) >= 10 and f.name[:10] < cutoff:
            continue

        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        in_decisions = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped == "## Decisions":
                in_decisions = True
                continue
            if stripped.startswith("## ") and in_decisions:
                break
            if in_decisions and stripped.startswith("- "):
                # Strip timestamp prefix
                m = re.match(r'^- \[([^\]]*)\]\s*(.*)', stripped)
                text_part = m.group(2) if m else stripped[2:]
                if text_part and text_part != "*No decisions extracted*":
                    decisions.append(text_part)

    return decisions[:20]  # cap at 20 most recent


def read_outbox(repo_path):
    """Read outbox items (cross-repo observations)."""
    outbox = repo_path / ".gator" / "outbox.md"
    if not outbox.exists():
        return []
    text = outbox.read_text(encoding="utf-8", errors="replace")
    items = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") and stripped != "- *(empty)*":
            items.append(stripped[2:])
    return items


# ---------------------------------------------------------------------------
# Profile generation
# ---------------------------------------------------------------------------

def build_profile(name, repo_path):
    """Build a complete intelligence profile for a repo."""
    path = Path(normalize_path(str(repo_path)))

    if not path.is_dir():
        return {
            "name": name,
            "accessible": False,
            "path": str(repo_path),
        }

    commits = get_recent_commits(path)
    freq = get_commit_frequency(path)
    change_types = get_change_type_distribution(commits)
    mission = read_mission(path)
    charters = read_charter_names(path)
    threads = read_active_threads(path)
    open_issues = read_issues_count(path)
    decisions = read_committed_decisions(path)
    outbox = read_outbox(path)

    # Derive activity level
    c7 = freq.get("7d", 0)
    if c7 >= 10:
        activity = "high"
    elif c7 >= 3:
        activity = "moderate"
    elif c7 >= 1:
        activity = "low"
    else:
        activity = "dormant"

    # Recent commit themes — group by message prefix patterns
    themes = {}
    for c in commits[:15]:
        msg = c["message"]
        # Extract first word/prefix as rough theme
        prefix = msg.split(":")[0].split("(")[0].strip() if ":" in msg or "(" in msg else msg.split()[0] if msg else ""
        prefix = prefix.lower()
        if prefix and len(prefix) < 30:
            themes[prefix] = themes.get(prefix, 0) + 1

    # Top themes by frequency
    top_themes = sorted(themes.items(), key=lambda x: -x[1])[:5]

    return {
        "name": name,
        "accessible": True,
        "path": str(path),
        "mission": mission,
        "activity": activity,
        "commits_7d": freq.get("7d", 0),
        "commits_30d": freq.get("30d", 0),
        "charters": charters,
        "threads": threads,
        "open_issues": open_issues,
        "change_types": change_types,
        "commit_themes": top_themes,
        "recent_commits": [
            {"hash": c["hash"], "message": c["message"], "date": c["date"]}
            for c in commits[:10]
        ],
        "decisions": decisions[:10],
        "outbox": outbox,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ---------------------------------------------------------------------------
# Output: markdown thread
# ---------------------------------------------------------------------------

def render_thread(profile):
    """Render a per-repo intelligence profile as markdown thread."""
    name = profile["name"]
    lines = []

    lines.append("---")
    lines.append(f"title: \"{name}\"")
    lines.append("category: repo-profile")
    lines.append(f"generated: {profile.get('generated_at', '')[:10]}")
    lines.append(f"repo-path: {profile.get('path', '')}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {name}")
    lines.append("")

    # What it is
    lines.append("## What It Is")
    lines.append("")
    mission = profile.get("mission", "")
    lines.append(mission if mission else "*No mission.md found*")
    lines.append("")

    # Current state
    lines.append("## Current State")
    lines.append("")
    activity = profile.get("activity", "unknown")
    c7 = profile.get("commits_7d", 0)
    c30 = profile.get("commits_30d", 0)
    lines.append(f"**Activity**: {activity} ({c7} commits in 7d, {c30} in 30d)")
    lines.append("")

    if profile.get("open_issues"):
        lines.append(f"**Open issues**: {profile['open_issues']}")
        lines.append("")

    # Charter coverage
    charters = profile.get("charters", [])
    if charters:
        lines.append(f"**Charters**: {', '.join(charters)}")
        lines.append("")

    threads = profile.get("threads", [])
    if threads:
        lines.append(f"**Active threads**: {', '.join(threads)}")
        lines.append("")

    # What changed recently
    lines.append("## Recent Activity")
    lines.append("")

    change_types = profile.get("change_types", {})
    if change_types:
        ct_parts = [f"{k} ({v})" for k, v in sorted(change_types.items(), key=lambda x: -x[1])]
        lines.append(f"**Change types**: {', '.join(ct_parts)}")
        lines.append("")

    commit_themes = profile.get("commit_themes", [])
    if commit_themes:
        theme_parts = [f"{t[0]} ({t[1]})" for t in commit_themes]
        lines.append(f"**Commit themes**: {', '.join(theme_parts)}")
        lines.append("")

    recent = profile.get("recent_commits", [])
    if recent:
        for c in recent[:7]:
            lines.append(f"- `{c['hash']}` {c['date']} — {c['message']}")
        if len(recent) > 7:
            lines.append(f"- ... and {len(recent) - 7} more")
        lines.append("")

    # Decisions
    decisions = profile.get("decisions", [])
    if decisions:
        lines.append("## Recent Decisions")
        lines.append("")
        for d in decisions[:7]:
            lines.append(f"- {d}")
        if len(decisions) > 7:
            lines.append(f"- ... and {len(decisions) - 7} more")
        lines.append("")

    # Outbox
    outbox = profile.get("outbox", [])
    if outbox:
        lines.append("## Outbox Items")
        lines.append("")
        for item in outbox:
            lines.append(f"- {item}")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append(f"*Generated by gator fleet-intel {VERSION} on {profile.get('generated_at', '')[:10]}. "
                 f"Do not edit manually — regenerated on each run.*")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ensure_utf8_stdout()

    parser = argparse.ArgumentParser(
        description="Generate per-repo intelligence summaries for the command post."
    )
    parser.add_argument("--repo", metavar="NAME", help="Update one repo only")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output to stdout")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be written")

    args = parser.parse_args()

    # Find command post
    cp = find_command_post()
    if not cp:
        print("  ! Could not find gator-command/ directory")
        sys.exit(1)

    gc_dir = cp / "gator-command"
    registry = parse_registry(cp)

    if not registry:
        print("  No repos in registry.")
        return

    # Filter to single repo if requested
    if args.repo:
        registry = [r for r in registry if r["name"] == args.repo]
        if not registry:
            print(f"  ! Repo '{args.repo}' not found in registry")
            sys.exit(1)

    # In JSON mode, status goes to stderr
    log = (lambda msg: print(msg, file=sys.stderr)) if args.json else print

    log("")
    log(f"  fleet-intel: profiling {len(registry)} repos")
    log("")

    profiles = []
    for entry in registry:
        name = entry["name"]
        repo_path = entry["path"]
        log(f"  scanning {name} ...")
        profile = build_profile(name, repo_path)
        profiles.append(profile)

    log("")

    if args.json:
        print(json.dumps(profiles, indent=2, default=str))
        return

    # Write thread files
    threads_dir = gc_dir / "threads"
    threads_dir.mkdir(exist_ok=True)

    written = 0
    for profile in profiles:
        if not profile.get("accessible"):
            print(f"  ! {profile['name']}: inaccessible, skipped")
            continue

        filename = f"repo-{profile['name']}.md"
        filepath = threads_dir / filename
        content = render_thread(profile)

        if args.dry_run:
            print(f"  would write: {filepath}")
            print(f"    {len(content)} chars, {content.count(chr(10))} lines")
        else:
            filepath.write_text(content, encoding="utf-8")
            print(f"  ✓ {filename}")
            written += 1

    print()
    if not args.dry_run:
        print(f"  Written: {written} repo profiles to {threads_dir}")
    print()


if __name__ == "__main__":
    main()
