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
    for _ in range(20):
        candidate = d / ".gator"
        if candidate.is_dir() and (d / ".git").exists():
            return candidate
        parent = d.parent
        if parent == d:
            break
        d = parent
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
    for candidate in (
        gator_dir / ".includes" / "scripts",
        gator_dir / "scripts",
    ):
        if candidate.is_dir():
            candidate_str = str(candidate)
            if candidate_str not in sys.path:
                sys.path.insert(0, candidate_str)
            break
    else:
        return 0

    from gator_layout import get_gator_paths
    from gator_core import import_sibling

    paths = get_gator_paths(repo_root)
    if paths.layout == "invalid":
        return 0

    gator_init = import_sibling("gator-init")
    # Capture the return so a future observability wire-up (B3) can route
    # non-happy-path statuses (degraded / unavailable / error) into a bounded
    # local diagnostic log. For now, discard: this commit is the layout fix
    # only; visibility is added in the B3 commit.
    _result = gator_init.ensure_git_hooks(repo_root, paths)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"gator-session-open: {e}", file=sys.stderr)
        sys.exit(0)
