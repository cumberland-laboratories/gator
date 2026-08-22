#!/usr/bin/env python3
"""
gator-approve.py — Architect-only override approval for blocked commits.

When the pre-commit hook blocks a commit, it writes an override request
to .gator/override-request.json with a unique block ID. The Architect reviews
the findings, then runs this script to approve the override.

The agent must NOT run this script. The constitution forbids it.
Unauthorized self-approval is an auditable governance violation.

Usage:
    python .gator/scripts/gator-approve.py
    python .gator/scripts/gator-approve.py --reason "trivial whitespace change"
    python .gator/scripts/gator-approve.py --reason "bug fix" --name "Architect"

The script reads the pending override request, confirms with the Architect,
and writes .gator/override-approved.json. The next git commit attempt
will accept the override if the block IDs match and the approval is
newer than the request.
"""

import io
import json
import sys
import time
from pathlib import Path


def _ensure_utf8_stdout():
    """Ensure stdout uses UTF-8 encoding (needed on Windows)."""
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )


def find_gator_dir():
    """Walk up from cwd to find .gator/."""
    d = Path.cwd().resolve()
    # Uncapped walk (2026-08-22 — same class as the policies.py finding:
    # a 10-hop cap silently fails on deeply nested working dirs).
    if (d / ".gator").is_dir():
        return d / ".gator"
    for parent in d.parents:
        if (parent / ".gator").is_dir():
            return parent / ".gator"
    return None


def main():
    _ensure_utf8_stdout()

    gator_dir = find_gator_dir()
    if not gator_dir:
        print("  Error: no .gator/ found.", file=sys.stderr)
        sys.exit(1)

    request_file = gator_dir / "override-request.json"
    if not request_file.exists():
        print("  No pending override request.")
        print("  Override requests are created when the pre-commit hook blocks a commit.")
        sys.exit(1)

    request = json.loads(request_file.read_text(encoding="utf-8"))
    block_id = request.get("block_id", "unknown")
    failure_type = request.get("failure_type", "unknown")
    files = request.get("files", [])
    override_type = request.get("override_type", "charter-skip")
    timestamp = request.get("timestamp", "unknown")

    print()
    print("  gator override approval")
    print()
    print(f"    Block ID:     {block_id}")
    print(f"    Failure:      {failure_type}")
    print(f"    Override:     {override_type}")
    print(f"    Blocked at:   {timestamp}")
    if files:
        print(f"    Files:        {', '.join(files[:5])}")
    print()

    # Parse --reason and --name from args
    reason = ""
    pi_name = ""
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--reason" and i + 1 < len(args):
            reason = args[i + 1]
        elif arg == "--name" and i + 1 < len(args):
            pi_name = args[i + 1]

    # Prompt for missing values
    if not reason:
        try:
            reason = input("  Reason for override (required): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.")
            sys.exit(1)

    if not reason:
        print("  Error: reason is required for override approval.")
        sys.exit(1)

    if not pi_name:
        try:
            pi_name = input("  Your name (Architect): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.")
            sys.exit(1)

    if not pi_name:
        print("  Error: Architect name is required.")
        sys.exit(1)

    # Write approval
    approval = {
        "block_id": block_id,
        "override_type": override_type,
        "approved_by": pi_name,
        "reason": reason,
        "approved_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "request_timestamp": timestamp,
    }

    approved_file = gator_dir / "override-approved.json"
    approved_file.write_text(
        json.dumps(approval, indent=2) + "\n",
        encoding="utf-8",
    )

    print()
    print(f"  \u2713 Override approved by {pi_name}")
    print(f"    Block ID: {block_id}")
    print(f"    Reason: {reason}")
    print()
    print("  Now retry: git commit")
    print()


if __name__ == "__main__":
    main()
