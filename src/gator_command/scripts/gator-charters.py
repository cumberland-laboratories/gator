#!/usr/bin/env python3
"""
gator charters — read-only charter health report.

Usage:
    gator charters report [--path <repo>]          human summary
    gator charters report --json [--path <repo>]   gator-charters-report-v1

The report reads charter files, source files and Git only. It never runs a
model, never runs the charter sync check, and never writes a file.

Exit codes: 0 when the report is `complete` or `partial`; 1 when it is
`unavailable` or `failed` (with `--json`, the JSON body is still printed).

@reads: charters, source files, git, the charter sync record (Git-private)
@writes: stdout only
"""

import argparse
import json
import sys

from gator_core import ensure_utf8_stdout, find_gator_root

import charter_report


def main():
    ensure_utf8_stdout()
    parser = argparse.ArgumentParser(
        prog="gator charters",
        description="Gator charters — read-only charter health report.",
    )
    # Flat optionals (no subparsers), so both `report --json` and
    # `--json report` parse; the Dashboard's run_json() passes --json first.
    parser.add_argument("action", choices=["report"], help="report: charter health")
    parser.add_argument("--json", "-j", action="store_true",
                        help="Output gator-charters-report-v1 JSON")
    parser.add_argument("--path", "-p",
                        help="Path to repo (default: current directory, walks up to find .gator/)")
    args = parser.parse_args()

    root = find_gator_root(args.path)
    if root is None:
        report = charter_report.unavailable_report(
            "No .gator/ found. Run from a gatorized repository.")
    else:
        try:
            report = charter_report.build_report(root)
        except Exception as exc:  # no traceback in machine output
            report = charter_report.failed_report(f"{type(exc).__name__}: {exc}")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(charter_report.render_text(report))
    sys.exit(0 if report.get("status") in ("complete", "partial") else 1)


if __name__ == "__main__":
    main()
