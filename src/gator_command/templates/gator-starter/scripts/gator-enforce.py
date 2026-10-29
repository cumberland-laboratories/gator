#!/usr/bin/env python3
"""
gator-enforce.py — Set this machine's commit policy for one Gator-governed clone.

Usage:
  python gator-enforce.py --level strict|warn [--repo /path/to/repo]

Levels:
  strict  — the default: missing charter updates block; dangerous patterns
            pause for an Architect decision
  warn    — every finding is advisory on this machine; commits record
            Gator-Commit-Policy: warn

The level is machine-local: it is written to
$(git rev-parse --git-path gator-commit-policy.json) in this clone, never to
the repository, so it never changes another engineer's checks. "strict"
removes the file. Enterprise-managed repositories are refused. The Dashboard's
Fleet Warn control writes the same file.
"""

import argparse
import sys
from pathlib import Path

# Submodules live alongside this script.
_script_dir = str(Path(__file__).resolve().parent)
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

import precommit_local_policy as local_policy  # noqa: E402

# The local subset of the hook-mode vocabulary (strict/warn/off); "off" is
# not a local level. Pinned by contracts/compatibility/test_hook_modes.py.
VALID_LEVELS = {"strict", "warn"}


def find_repo_root(repo_path=None):
    """Find repo root containing .gator/ from the given path or cwd."""
    start = Path(repo_path) if repo_path else Path.cwd()
    start = start.resolve()

    if (start / ".gator").is_dir():
        return start
    for parent in start.parents:
        if (parent / ".gator").is_dir():
            return parent
    return None


def main():
    parser = argparse.ArgumentParser(description="Set this machine's Gator commit policy")
    parser.add_argument("--level", required=True, choices=sorted(VALID_LEVELS),
                        help="Commit policy on this machine: strict or warn")
    parser.add_argument("--repo", default=None,
                        help="Path to the repo (default: current directory)")
    args = parser.parse_args()

    repo_root = find_repo_root(args.repo)
    if not repo_root:
        print("Error: No .gator/ directory found.", file=sys.stderr)
        print("Are you in a Gator-governed repo?", file=sys.stderr)
        sys.exit(1)

    old_level = local_policy.read_level(repo_root)
    try:
        local_policy.write_level(repo_root, args.level)
    except (local_policy.LocalPolicyError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if old_level == args.level:
        print(f"  Commit policy on this machine unchanged: {args.level}")
    else:
        print(f"  Commit policy on this machine: {old_level} -> {args.level}")

    if args.level == "strict":
        print("  Default checks: missing charter updates block; dangerous patterns pause.")
    else:
        print("  Findings are advisory on this machine only. Commits record "
              "Gator-Commit-Policy: warn.")


if __name__ == "__main__":
    main()
