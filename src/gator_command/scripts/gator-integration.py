#!/usr/bin/env python3
"""
gator-integration.py — `gator integration status|remove|dismiss-codex-reminder`.

Shows or removes Gator's connection to the AI tools on this machine (the
SessionStart hooks in each vendor's user-level settings). Every ordinary
`gator` command connects them automatically; this verb never does, so
`remove` stays removed until the next ordinary command (or for good with
GATOR_NO_VENDOR_INTEGRATION=1).

Exit codes: 0 success; 1 unreadable state file (status, dismiss) or a
vendor file Gator could not read (remove); 2 usage error.

@reads/@writes: see machine_integration.py
"""

import argparse
import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from gator_core import ensure_utf8_stdout  # noqa: E402
import machine_integration as mi  # noqa: E402


def _vendor_line(info):
    if info["problem"]:
        state = "Problem: Gator could not read this settings file"
    elif info["connected"]:
        state = "Connected"
    elif info["present"]:
        state = "Not connected (run any gator command)"
    else:
        state = "Not installed"
    return f"  {info['display']:<12} {state}\n               {info['config_path']}"


def cmd_status(args):
    report = mi.status()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print()
        print("  Gator's connection to AI tools on this machine")
        print()
        for info in report["vendors"].values():
            print(_vendor_line(info))
        print()
        state_text = {"ok": "ok", "missing": "not created yet",
                      "unreadable": "UNREADABLE — reset with: gator integration remove"}
        print(f"  State file   {state_text[report['state']]}")
        print(f"               {report['state_path']}")
        if report["codex_reminder_due"]:
            print()
            print("  In Codex, approve Gator's hook once: /hooks.")
            print("  Then run: gator integration dismiss-codex-reminder")
        print()
    return 1 if report["state"] == "unreadable" else 0


def cmd_remove(args):
    actions = mi.remove()
    print()
    if not actions:
        print("  Nothing to remove: no Gator hooks or state on this machine.")
    for action in actions:
        verb = {"deleted": "Deleted", "stripped": "Removed Gator's hooks from",
                "malformed": "Left unchanged (could not read)"}[action["action"]]
        print(f"  {verb} {action['path']}")
    print()
    print("  The next ordinary gator command connects the AI tools again.")
    print("  To keep them disconnected, set GATOR_NO_VENDOR_INTEGRATION=1.")
    print("  Other machines are not affected.")
    print()
    return 1 if any(a["action"] == "malformed" for a in actions) else 0


def cmd_dismiss(args):
    if mi.dismiss_codex_reminder():
        print("  Codex reminder dismissed.")
        return 0
    print("  Gator has no readable connection record on this machine; nothing "
          "to dismiss.", file=sys.stderr)
    return 1


def main(argv=None):
    ensure_utf8_stdout()
    parser = argparse.ArgumentParser(
        prog="gator integration",
        description="Show or remove Gator's connection to the AI tools on this machine.")
    sub = parser.add_subparsers(dest="action", required=True)
    p_status = sub.add_parser("status", help="show which AI tools Gator is connected to")
    p_status.add_argument("--json", action="store_true", help="output JSON")
    p_status.set_defaults(func=cmd_status)
    sub.add_parser("remove", help="remove Gator's hooks from every AI tool on this machine"
                   ).set_defaults(func=cmd_remove)
    sub.add_parser("dismiss-codex-reminder",
                   help="record that you approved Gator's hook in Codex (/hooks)"
                   ).set_defaults(func=cmd_dismiss)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
