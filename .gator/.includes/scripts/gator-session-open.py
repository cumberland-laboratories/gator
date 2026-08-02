#!/usr/bin/env python3
"""
gator-session-open.py — Silent self-heal at session start.

Called by vendor SessionStart hooks (Claude Code, Codex CLI, Gemini CLI).
Ensures git hooks are correct without requiring the user to type `gator init`.

This script MUST:
- Always exit 0 (never block the vendor session)
- Never write to stdout (vendors may interpret stdout as hook output)
- Be safe to run even if .gator/ or .git/ is missing

@reads: .gator/scripts/gator-init.py (ensure_git_hooks)
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

    # Bootstrap: add scripts/ to sys.path for gator_core imports
    scripts_dir = str(gator_dir / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    from gator_core import import_sibling

    gator_init = import_sibling("gator-init")
    gator_init.ensure_git_hooks(repo_root, gator_dir)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"gator-session-open: {e}", file=sys.stderr)
        sys.exit(0)
