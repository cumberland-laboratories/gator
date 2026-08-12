#!/usr/bin/env python3
"""
gator_session_reader.py — Committed-summary reader.

Importable library — no CLI, no main(). This is the surviving snippet-based
reader contract extracted from ``gator-sessions.py`` per the 2026-08-11
non-Enterprise session cleanup plan (Phase 2 split, deletion-free).

Consumers:
  - ``gator-audit.py``            — snippet-based decisions_source ("committed")
  - ``gator-repo-status.py``      — recent session summaries panel
  - ``tests/test_session_reader.py``  — reader-contract regression pins

Design notes:
  - Two functions, both verbatim from ``gator-sessions.py`` (parse_committed_summary
    at L1044, read_committed_summaries at L1128). Behavior is byte-identical to the
    original — this module IS the extraction, not a rewrite.
  - No dependency on ``gator-session-common.py`` or any other retirement candidate.
    The Phase-2 machine-identity wrapper (``gator-sessions.get_machine_identity``)
    is intentionally NOT ported — it has no surviving external callers (audit hits
    ``gator-session-common.get_machine_identity`` directly at gator-audit.py:272).

@reads: .gator/sessions/*.md (committed summaries)
@writes: none

See:
  - .gator/vault/artifacts/2026-08-11-non-enterprise-session-cleanup-plan.md
  - .gator/vault/artifacts/2026-08-11-session-cleanup-consumer-audit.md (r1)
"""

import re
from datetime import datetime, timedelta, timezone


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
