#!/usr/bin/env python3
"""
gator-session-open.py — Silent self-heal at session start.

Called by vendor SessionStart hooks (Claude Code, Codex CLI, Gemini CLI).
Ensures git hooks are correct without requiring the user to type `gator init`.

This script MUST:
- Always exit 0 (never block the vendor session)
- Never write to stdout (vendors may interpret stdout as hook output)
- Be safe to run even if .gator/ or .git/ is missing

@reads: .gator/.includes/scripts/gator-init.py (ensure_git_hooks) on v2 layout;
        .gator/scripts/gator-init.py on v1 (during a v1→v2 update straddle).
@writes: .git/hooks/ (only when hooks are missing or stale)
"""

import sys
from pathlib import Path


def find_gator_dir():
    """Walk up from cwd to find a repo-level .gator/ directory.

    Only returns a .gator/ that sits inside a git repo (sibling .git/).
    This prevents the machine-local ~/.gator config directory from being
    mistaken for a governed checkout.
    """
    d = Path.cwd().resolve()
    # Uncapped walk (2026-08-22 — same class as the policies.py 10-hop
    # finding: arbitrary depth caps silently fail on deep working dirs).
    if (d / ".gator").is_dir() and (d / ".git").exists():
        return d / ".gator"
    for parent in d.parents:
        if (parent / ".gator").is_dir() and (parent / ".git").exists():
            return parent / ".gator"
    return None


def main():
    gator_dir = find_gator_dir()
    if not gator_dir:
        return 0

    repo_root = gator_dir.parent

    # Bootstrap sys.path from the layout-resolved scripts directory. Probe v2
    # first (.includes/scripts/), then v1 (scripts/) so this script works
    # during a v1→v2 update straddle and on legacy fleet repos that have not
    # migrated yet. Without this, the previous v1-only path (gator_dir /
    # "scripts") silently no-ops on every v2 repo.
    # Runtime-split Phase 4/5 fix (2026-08-22): post-Phase-4 pinned repos
    # carry NO repo-resident scripts — when this copy runs from the wheel
    # (via the gator-hook dispatcher), its siblings live in its OWN
    # directory. The old repo-dirs-only probe made session-open a silent
    # no-op on every pinned repo (hook self-heal lost; only `gator init`
    # healed). Own-dir fallback restores it.
    for candidate in (
        gator_dir / ".includes" / "scripts",
        gator_dir / "scripts",
        Path(__file__).resolve().parent,
    ):
        if candidate.is_dir() and (candidate / "gator_core.py").is_file():
            candidate_str = str(candidate)
            if candidate_str not in sys.path:
                sys.path.insert(0, candidate_str)
            break
    else:
        return 0

    from gator_layout import get_gator_paths
    from gator_core import import_sibling
    try:
        from gator_diagnostics import log_hook_event, NON_HAPPY_STATUSES
    except ImportError:
        # Diagnostics module unavailable — degrade silently to the pre-B3
        # behavior (still exit 0, still no stdout). This should only happen
        # if the module wasn't shipped by an old template; keep session-open
        # forward-compatible.
        log_hook_event = None
        NON_HAPPY_STATUSES = frozenset()

    paths = get_gator_paths(repo_root)
    if paths.layout == "invalid":
        if log_hook_event:
            log_hook_event(gator_dir, "gator-session-open", "SKIP",
                           f"layout={paths.layout}")
        return 0

    gator_init = import_sibling("gator-init")
    # Capture ensure_git_hooks's return dict so non-happy-path statuses
    # (degraded / unavailable / error) get an entry in the bounded diagnostic
    # log — the "silent hook" contract keeps stdout empty, but the maintainer
    # still needs evidence when self-heal degrades.
    result = gator_init.ensure_git_hooks(repo_root, paths) or {}
    status = str(result.get("status", "")).lower()
    if status in NON_HAPPY_STATUSES and log_hook_event:
        log_hook_event(
            gator_dir,
            "gator-session-open",
            status,
            str(result.get("detail", "")),
        )

    # Org-policy staleness nudge (runtime-split D6 decision (c),
    # Architect-ratified 2026-08-22). STDERR only — this script's
    # contract forbids stdout (vendors treat it as hook output/context).
    # Purely local mtime check, Enterprise-active repos only; the
    # agent-facing copy of the nudge lives in the `gator init` banner.
    try:
        from gator_core import policy_staleness_nudge
        _nudge = policy_staleness_nudge(gator_dir)
        if _nudge:
            print(f"gator: {_nudge}", file=sys.stderr)
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"gator-session-open: {e}", file=sys.stderr)
        sys.exit(0)
