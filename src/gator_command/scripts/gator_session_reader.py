#!/usr/bin/env python3
"""
gator_session_reader.py — Committed-summary reader + machine identity.

Importable library — no CLI, no main(). Post-Phase-3 (2026-08-13) this module
owns the entire surviving reader-side contract:

  - parse_committed_summary(text, filename)     — extracted from gator-sessions.py:1044 in Phase 2A
  - read_committed_summaries(sessions_dir, ...) — extracted from gator-sessions.py:1128 in Phase 2A
  - get_machine_identity()                      — folded from gator-session-common.py:33 in Phase 3F

Consumers:
  - ``gator-audit.py``               — snippet-based decisions_source + data["machine"]
  - ``gator-repo-status.py``         — recent session summaries panel
  - ``tests/test_session_reader.py`` — reader-contract regression pins

Design notes:
  - All three functions are byte-identical copies of their originals — this
    module IS the consolidation, not a rewrite.
  - No dependency on any retirement candidate. `gator-session-common.py` is
    retired 2026-08-13 in this commit; `gator-sessions.py` retired 2026-08-13
    in Commit E.

@reads: .gator/sessions/*.md (committed summaries), ~/.gator/machine-id
@writes: ~/.gator/machine-id (first-call creation)

See:
  - .gator/vault/artifacts/2026-08-11-non-enterprise-session-cleanup-plan.md
  - .gator/vault/artifacts/2026-08-11-session-cleanup-consumer-audit.md (r2)
"""

import platform
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Machine identity (folded from gator-session-common.py in Phase 3F, 2026-08-13)
# ---------------------------------------------------------------------------

GATOR_USER_DIR = Path.home() / ".gator"
MACHINE_ID_FILE = GATOR_USER_DIR / "machine-id"


def get_machine_identity():
    """Get stable machine identity for session summaries.

    Returns dict with id, hostname, label. Creates machine-id file
    on first call if it doesn't exist.

    Uses gator-machine-id.py's storage format for compatibility.
    """
    if MACHINE_ID_FILE.exists():
        data = {}
        try:
            for line in MACHINE_ID_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if ":" in line and not line.startswith("#"):
                    key, _, value = line.partition(":")
                    data[key.strip()] = value.strip()
        except OSError:
            pass

        if "id" in data:
            return {
                "id": data["id"],
                "hostname": data.get("hostname", platform.node()),
                "label": data.get("label", data.get("hostname", platform.node())),
            }

    # No machine-id file — create one
    import uuid
    from datetime import date

    GATOR_USER_DIR.mkdir(parents=True, exist_ok=True)
    mid = str(uuid.uuid4())
    hostname = platform.node()

    lines = [
        f"id: {mid}",
        f"hostname: {hostname}",
        f"label: {hostname}",
        f"created: {date.today()}",
    ]
    MACHINE_ID_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {"id": mid, "hostname": hostname, "label": hostname}


# ---------------------------------------------------------------------------
# Committed-summary parser + reader (extracted from gator-sessions.py in
# Phase 2A, 2026-08-12)
# ---------------------------------------------------------------------------


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
