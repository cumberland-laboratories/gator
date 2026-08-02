#!/usr/bin/env python3
"""
gator-pulse.py — Generate a strategic operations brief for a governed repo.

Reads the .gator/ knowledge layer (roadmap, issues, inbox, mission,
sessions) and git history, writes a structured summary to .gator/pulse.md.

Sections: Top 5 Next Steps, Roadmap Check, Top 5 Priorities,
Issues & Blockers, Recent Activity.

Usage:
    python gator-pulse.py [--path /repo] [--days 7] [--dry-run]

@reads: git log, .gator/roadmap.md, .gator/issues.md, .gator/inbox.md,
        .gator/mission.md, .gator/sessions/
@writes: .gator/pulse.md
"""

import argparse
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from gator_core import find_gator_root, ensure_utf8_stdout  # noqa: E402
from gator_layout import get_gator_paths  # noqa: E402


def git(*args, cwd=None):
    """Run a git command, return (stdout, ok)."""
    try:
        result = subprocess.run(
            ["git"] + list(args),
            capture_output=True, text=True, timeout=30, cwd=cwd,
        )
        return result.stdout.strip(), result.returncode == 0
    except Exception:
        return "", False


# ── evidence gathering ─────────────────────────────────────────────────────

def read_file(path, max_lines=200):
    """Read a file, return content or empty string."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        return "\n".join(lines[:max_lines])
    except (OSError, UnicodeDecodeError):
        return ""


def get_recent_commits(repo_path, days=7, limit=30):
    """Get recent commits."""
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    out, ok = git(
        "log", f"--since={since}", "--format=%h|%s|%ai",
        f"-{limit}", cwd=str(repo_path),
    )
    if not ok or not out:
        return []
    commits = []
    for line in out.splitlines():
        parts = line.split("|", 2)
        if len(parts) >= 3:
            commits.append({
                "hash": parts[0],
                "message": parts[1],
                "date": parts[2][:10],
            })
    return commits


def get_branch(repo_path):
    """Get current branch."""
    out, ok = git("branch", "--show-current", cwd=str(repo_path))
    return out if ok else "unknown"


def get_latest_assessment(artifacts_dir):
    """Find and read the most recent project-assessment artifact.

    Looks for files matching *project-assessment*.md in .gator/artifacts/,
    sorted by filename (date-prefixed) descending. Returns dict with
    content, model, and date, or None if no assessment exists.
    """
    if not artifacts_dir.is_dir():
        return None
    assessments = sorted(
        [f for f in artifacts_dir.glob("*project-assessment*.md") if f.is_file()],
        reverse=True,
    )
    if not assessments:
        return None
    latest = assessments[0]
    try:
        text = latest.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    # Parse frontmatter for model and date
    model = ""
    date = ""
    body_lines = []
    in_frontmatter = False
    past_frontmatter = False
    for line in text.splitlines():
        if line.strip() == "---" and not past_frontmatter:
            if in_frontmatter:
                past_frontmatter = True
            else:
                in_frontmatter = True
            continue
        if in_frontmatter and not past_frontmatter:
            if line.startswith("model:"):
                model = line.split(":", 1)[1].strip()
            elif line.startswith("date:"):
                date = line.split(":", 1)[1].strip()
            continue
        if past_frontmatter:
            body_lines.append(line)

    # Extract just the assessment body (skip the ## heading if present)
    content_lines = []
    for line in body_lines:
        if line.startswith("## Project Assessment"):
            continue
        if line.startswith("# "):
            continue
        content_lines.append(line)

    content = "\n".join(content_lines).strip()
    if not content:
        return None

    return {
        "content": content,
        "model": model,
        "date": date,
        "file": latest.name,
    }


def extract_roadmap_table(roadmap_text):
    """Extract the first markdown table from the roadmap, preserving all columns."""
    table_lines = []
    in_table = False
    for line in roadmap_text.splitlines():
        if line.startswith("|"):
            in_table = True
            table_lines.append(line)
        elif in_table:
            # End of table — stop at first non-table line after table started
            break
    return table_lines if len(table_lines) >= 3 else []  # header + separator + at least 1 row


def parse_roadmap_items(roadmap_text):
    """Extract roadmap items with status from markdown tables."""
    items = []
    for line in roadmap_text.splitlines():
        if not line.startswith("|"):
            continue
        if line.startswith("|---") or line.startswith("| #") or line.startswith("| Priority"):
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) < 3:
            continue
        # Try to find status cell — look for Done/Building/Designed/etc
        for i, cell in enumerate(cells):
            if any(s in cell for s in ("Done", "Building", "Working", "Designed", "Considering", "Deferred", "Open")):
                name = cells[i - 1] if i > 0 else cells[0]
                # Clean up bold markers
                name = re.sub(r'\*\*([^*]+)\*\*', r'\1', name).strip()
                # Shorten long names
                if len(name) > 80:
                    name = name[:80] + "..."
                items.append({"name": name, "status": cell.strip()})
                break
    return items


def parse_issues(issues_text):
    """Extract issues with status."""
    issues = []
    current = None
    for line in issues_text.splitlines():
        if line.startswith("### "):
            if current:
                issues.append(current)
            current = {"title": line[4:].strip(), "status": "Open"}
        elif current and line.startswith("**Status**:"):
            current["status"] = line.split(":", 1)[1].strip()
    if current:
        issues.append(current)
    return issues


def parse_inbox_items(inbox_text):
    """Extract inbox bullet items."""
    items = []
    for line in inbox_text.splitlines():
        line = line.strip()
        if line.startswith("- ") and len(line) > 10:
            text = line[2:].strip()
            if len(text) > 100:
                text = text[:100] + "..."
            items.append(text)
    return items


def get_session_decisions(sessions_dir, days=7):
    """Extract recent decisions from committed session summaries."""
    decisions = []
    if not sessions_dir.is_dir():
        return decisions
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    for f in sorted(sessions_dir.glob("*.md"), reverse=True):
        if f.name.startswith("_"):
            continue
        # Quick date check from filename
        if f.name[:10] < cutoff:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
            in_decisions = False
            for line in text.splitlines():
                if line.startswith("## Decisions") or line.startswith("## decisions"):
                    in_decisions = True
                    continue
                if in_decisions and line.startswith("## "):
                    break
                if in_decisions and line.startswith("- "):
                    dec = line[2:].strip()
                    # Strip timestamp prefix if present
                    dec = re.sub(r'^\[\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}\]\s*', '', dec)
                    if len(dec) > 10:
                        decisions.append(dec)
        except (OSError, UnicodeDecodeError):
            continue
    return decisions[:10]


# ── pulse generation ───────────────────────────────────────────────────────

def build_pulse(repo_path, days=7):
    """Build the pulse.md content from repo evidence."""
    today = datetime.now().strftime("%Y-%m-%d")
    branch = get_branch(repo_path)
    paths = get_gator_paths(repo_path)

    # Gather evidence (using layout-resolved paths)
    roadmap_text = read_file(paths.roadmap)
    issues_text = read_file(paths.issues)
    inbox_text = read_file(paths.inbox)
    mission_text = read_file(paths.mission, max_lines=10)
    commits = get_recent_commits(repo_path, days)
    roadmap_items = parse_roadmap_items(roadmap_text)
    issues = parse_issues(issues_text)
    inbox_items = parse_inbox_items(inbox_text)
    sessions_dir = paths.gator_root / "sessions"
    decisions = get_session_decisions(sessions_dir, days)
    assessment = get_latest_assessment(paths.artifacts_dir)

    # Classify roadmap items
    done = [i for i in roadmap_items if "Done" in i["status"]]
    building = [i for i in roadmap_items if any(s in i["status"] for s in ("Building", "Working"))]
    designed = [i for i in roadmap_items if "Designed" in i["status"]]
    other = [i for i in roadmap_items if i not in done and i not in building and i not in designed]

    # Classify issues
    open_issues = [i for i in issues if "Open" in i["status"] or "Working" in i["status"]]
    resolved_issues = [i for i in issues if "Resolved" in i["status"]]

    lines = []

    # ── Header
    lines.append("# Pulse")
    lines.append("")
    lines.append(f"*{today} | branch: {branch} | {len(commits)} commits in {days}d*")
    lines.append("")

    # ── Top 5 Next Steps
    lines.append("## Top 5 Next Steps")
    lines.append("")
    next_steps = []
    # Building items are the most actionable
    for item in building[:3]:
        next_steps.append(f"Continue: {item['name']}")
    # Designed items are next in line
    for item in designed:
        if len(next_steps) >= 5:
            break
        next_steps.append(f"Build: {item['name']}")
    # Open issues are actionable
    for issue in open_issues:
        if len(next_steps) >= 5:
            break
        next_steps.append(f"Fix: {issue['title']}")
    # Inbox items might contain action items
    for item in inbox_items:
        if len(next_steps) >= 5:
            break
        if any(kw in item.upper() for kw in ("TODO", "NEED", "SHOULD", "MUST", "FIX", "BUG")):
            next_steps.append(f"Triage: {item}")

    if next_steps:
        for i, step in enumerate(next_steps[:5], 1):
            lines.append(f"{i}. {step}")
    else:
        lines.append("No actionable items identified from roadmap or issues.")
    lines.append("")

    # ── Project Assessment
    if assessment:
        lines.append("## Project Assessment")
        lines.append("")
        lines.append(assessment["content"])
        lines.append("")
        sig = assessment["model"] or "unknown model"
        date = assessment["date"] or "undated"
        lines.append(f"*-- {sig}, {date}*")
        lines.append("")
    else:
        lines.append("## Project Assessment")
        lines.append("")
        lines.append("*No assessment yet. Ask the AI agent to generate one:*")
        lines.append('*"Write a project assessment artifact"*')
        lines.append("")

    # ── Roadmap Check
    lines.append("## Roadmap Check")
    lines.append("")
    if roadmap_items:
        # Pass through the original roadmap table from the source file
        roadmap_table = extract_roadmap_table(roadmap_text)
        if roadmap_table:
            for row in roadmap_table:
                lines.append(row)
        else:
            # Fallback: build a simple table from parsed items
            lines.append("| Item | Status |")
            lines.append("|------|--------|")
            for item in roadmap_items:
                lines.append(f"| {item['name']} | {item['status']} |")
        lines.append("")

        # In progress detail below the table
        if building:
            lines.append("**In progress:**")
            lines.append("")
            for item in building:
                lines.append(f"- {item['name']}")
            lines.append("")
    else:
        lines.append("No roadmap items found.")
        lines.append("")

    # ── Top 5 Priorities
    lines.append("## Top 5 Priorities")
    lines.append("")
    priorities = []
    # Open issues are priorities
    for issue in open_issues[:3]:
        priorities.append(f"**Issue**: {issue['title']}")
    # Inbox items with urgency signals
    for item in inbox_items:
        if len(priorities) >= 5:
            break
        priorities.append(f"**Inbox**: {item}")
    # Decisions that need follow-up
    for dec in decisions:
        if len(priorities) >= 5:
            break
        if any(kw in dec.lower() for kw in ("need", "should", "todo", "defer", "block")):
            priorities.append(f"**Decision follow-up**: {dec}")

    if priorities:
        for i, p in enumerate(priorities[:5], 1):
            lines.append(f"{i}. {p}")
    else:
        lines.append("No urgent priorities identified.")
    lines.append("")

    # ── Issues & Blockers
    lines.append("## Issues & Blockers")
    lines.append("")
    if open_issues:
        for issue in open_issues:
            status_tag = "Working" if "Working" in issue["status"] else "Open"
            lines.append(f"- **{status_tag}**: {issue['title']}")
    else:
        lines.append("No open issues.")
    if resolved_issues:
        lines.append("")
        lines.append(f"*{len(resolved_issues)} resolved issue{'s' if len(resolved_issues) > 1 else ''}*")
    lines.append("")

    # ── Recent Activity
    lines.append("## Recent Activity")
    lines.append("")
    if commits:
        lines.append(f"{len(commits)} commits in the last {days} days.")
        lines.append("")
        for c in commits[:10]:
            lines.append(f"- `{c['hash']}` {c['message']} ({c['date']})")
        if len(commits) > 10:
            lines.append(f"- *...and {len(commits) - 10} more*")
    else:
        lines.append("No commits in this window.")

    if decisions:
        lines.append("")
        lines.append("**Recent decisions:**")
        for dec in decisions[:5]:
            lines.append(f"- {dec}")
    lines.append("")

    # ── Footer
    lines.append("---")
    lines.append(f"*Generated by gator-pulse.py on {today}*")
    lines.append("")

    return "\n".join(lines)


def main():
    ensure_utf8_stdout()

    parser = argparse.ArgumentParser(
        description="Generate repo pulse — strategic operations brief"
    )
    parser.add_argument("--path", "-p", help="Path to repo (default: cwd)")
    parser.add_argument("--days", "-d", type=int, default=7,
                        help="Lookback window in days (default: 7)")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Print to stdout instead of writing file")
    args = parser.parse_args()

    repo_root = find_gator_root(args.path)
    if not repo_root:
        print("Error: no .gator/ found.", file=sys.stderr)
        sys.exit(1)

    content = build_pulse(repo_root, args.days)

    if args.dry_run:
        print(content)
        return

    paths = get_gator_paths(repo_root)
    pulse_file = paths.pulse
    pulse_file.write_text(content, encoding="utf-8")
    print(f"  Wrote {pulse_file}")


if __name__ == "__main__":
    main()
