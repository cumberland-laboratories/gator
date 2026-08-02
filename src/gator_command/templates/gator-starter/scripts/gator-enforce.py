#!/usr/bin/env python3
"""
gator-enforce.py — Set the enforcement level for a Gator-governed repo.

Usage:
  python gator-enforce.py --level strict|warn|off [--repo /path/to/repo]

Levels:
  strict  — CRITICAL/HIGH findings block commits (default)
  warn    — all findings reported but nothing blocks
  off     — governance checks skipped, trailers still written

Writes to .gator/config.json in the target repo.
"""

import argparse
import json
import sys
from pathlib import Path

VALID_LEVELS = {"strict", "warn", "off"}


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
    from gator_layout import get_gator_paths

    parser = argparse.ArgumentParser(description="Set Gator enforcement level")
    parser.add_argument("--level", required=True, choices=sorted(VALID_LEVELS),
                        help="Enforcement level: strict, warn, or off")
    parser.add_argument("--repo", default=None,
                        help="Path to the repo (default: current directory)")
    args = parser.parse_args()

    repo_root = find_repo_root(args.repo)
    if not repo_root:
        print("Error: No .gator/ directory found.", file=sys.stderr)
        print("Are you in a Gator-governed repo?", file=sys.stderr)
        sys.exit(1)

    paths = get_gator_paths(repo_root)
    config_path = paths.config_json

    # Read existing config or start fresh
    config = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            config = {}

    old_level = config.get("enforcement_level", "strict")
    config["enforcement_level"] = args.level

    config_path.write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )

    if old_level == args.level:
        print(f"  Enforcement level unchanged: {args.level}")
    else:
        print(f"  Enforcement level: {old_level} -> {args.level}")

    if args.level == "strict":
        print("  CRITICAL/HIGH findings will block commits.")
    elif args.level == "warn":
        print("  Findings will be reported but commits will not be blocked.")
    else:
        print("  Governance checks disabled. Trailers still written.")


if __name__ == "__main__":
    main()
