#!/usr/bin/env python3
"""
gator-version.py — Git-native version resolution for Gator Command.

The version IS the git state. Tagged releases (v0.1.0, v1.0.0) are the
anchors. Between tags, git describe gives the full picture:
  v0.1.0-14-g8ea4749 = 14 commits after v0.1.0, at commit 8ea4749.

Usage as a module:
    from gator_core import get_version
    version = get_version()  # "v0.1.0-14-g8ea4749" or "v0.1.0" or "dev"

Usage as a script:
    python gator-command/scripts/gator-version.py
    python gator-command/scripts/gator-version.py --short

No hardcoded version strings. The repo is the source of truth.
"""

import argparse
import sys

from gator_core import get_version, get_version_short


def main():
    parser = argparse.ArgumentParser(description="Gator version from git tags")
    parser.add_argument("--short", action="store_true", help="Tag only, no commit count")
    args = parser.parse_args()

    if args.short:
        print(get_version_short())
    else:
        print(get_version())


if __name__ == "__main__":
    main()
