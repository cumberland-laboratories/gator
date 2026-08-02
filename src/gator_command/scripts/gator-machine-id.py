#!/usr/bin/env python3
"""
gator-machine-id.py — Stable machine identity for session audit trails.

Generates and stores a persistent machine identifier at ~/.gator/machine-id.
The ID is a UUID generated once, persists across sessions and repos,
and is used in session summaries as the "where" pointer for audit trails.

Why not hostname?
  - Hostnames change (reimages, domain joins, laptop swaps)
  - Hostnames can be meaningless in enterprise (DESKTOP-NKSU8RO)
  - Hostnames can collide across machines

The machine-id file also stores a human-readable label that the PI
can set to make the audit trail legible:

  ~/.gator/machine-id:
    id: a1b2c3d4-5678-90ab-cdef-1234567890ab
    hostname: DESKTOP-NKSU8RO
    label: alan-home-desktop
    created: 2026-05-30

Usage:
    python gator-command/scripts/gator-machine-id.py           # show or create
    python gator-command/scripts/gator-machine-id.py --label "alan-home-desktop"
    python gator-command/scripts/gator-machine-id.py --json

As a module:
    from gator_machine_id import get_machine_id
    mid = get_machine_id()  # {"id": "...", "hostname": "...", "label": "..."}

@reads: ~/.gator/machine-id
@writes: ~/.gator/machine-id (on first run only, or --label update)
"""

import argparse
import json
import platform
import sys
import uuid
from datetime import date
from pathlib import Path


GATOR_USER_DIR = Path.home() / ".gator"
MACHINE_ID_FILE = GATOR_USER_DIR / "machine-id"


def get_machine_id():
    """Get or create the stable machine identity.

    Returns dict with id, hostname, label, created.
    Creates ~/.gator/machine-id on first call.
    """
    if MACHINE_ID_FILE.exists():
        return _read_machine_id()

    # First run — generate and store
    return _create_machine_id()


def _read_machine_id():
    """Read existing machine-id file."""
    data = {}
    try:
        for line in MACHINE_ID_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if ":" in line and not line.startswith("#"):
                key, _, value = line.partition(":")
                data[key.strip()] = value.strip()
    except OSError:
        return _create_machine_id()

    if "id" not in data:
        return _create_machine_id()

    return data


def _create_machine_id():
    """Generate a new machine-id and write to file."""
    GATOR_USER_DIR.mkdir(parents=True, exist_ok=True)

    data = {
        "id": str(uuid.uuid4()),
        "hostname": platform.node(),
        "label": platform.node(),  # default label = hostname, PI can change
        "created": str(date.today()),
    }

    lines = [
        f"id: {data['id']}",
        f"hostname: {data['hostname']}",
        f"label: {data['label']}",
        f"created: {data['created']}",
    ]
    MACHINE_ID_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return data


def set_label(new_label):
    """Update the human-readable label."""
    data = get_machine_id()
    data["label"] = new_label

    lines = [
        f"id: {data['id']}",
        f"hostname: {data.get('hostname', platform.node())}",
        f"label: {data['label']}",
        f"created: {data.get('created', str(date.today()))}",
    ]
    MACHINE_ID_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return data


def main():
    parser = argparse.ArgumentParser(
        description="Gator machine identity for session audit trails."
    )
    parser.add_argument(
        "--label", "-l",
        help="Set a human-readable label for this machine",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON",
    )
    args = parser.parse_args()

    if args.label:
        data = set_label(args.label)
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print(f"  Machine label set to: {data['label']}")
            print(f"  ID: {data['id']}")
    else:
        data = get_machine_id()
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print(f"  Machine ID: {data['id']}")
            print(f"  Hostname:   {data.get('hostname', '?')}")
            print(f"  Label:      {data.get('label', '?')}")
            print(f"  Created:    {data.get('created', '?')}")
            print(f"  Stored at:  {MACHINE_ID_FILE}")


if __name__ == "__main__":
    main()
