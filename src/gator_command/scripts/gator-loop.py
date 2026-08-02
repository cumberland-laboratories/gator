#!/usr/bin/env python3
"""
gator loop — governed planning debate between AI models.

Thin entry script that delegates to the loop package's CLI module.
Follows the same pattern as other gator-*.py scripts: standalone
invocable via subprocess from cli.py's _run_script().
"""

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(SCRIPTS_DIR / "loop"))

from gator_core import ensure_utf8_stdout


def main():
    ensure_utf8_stdout()
    from loop.cli import main as loop_main
    loop_main(sys.argv[1:])


if __name__ == "__main__":
    main()
