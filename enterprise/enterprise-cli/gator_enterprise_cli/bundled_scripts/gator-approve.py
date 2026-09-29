#!/usr/bin/env python3
"""
gator-approve.py — Architect override approval for blocked commits (#34, #35).

Reached through the hook dispatcher:

    gator hook override status            show the last blocked attempt
    gator hook override approve [...]     approve its approvable findings
    gator hook override cancel            drop the block and any approval
    gator hook approve [...]              alias of `override approve`

Every blocked commit attempt records a block (see precommit_override.py) that
lists each failed rule with its resolution class. `approve` authorizes the
approvable rules for the EXACT staged change that was blocked; it never
approves fix-required findings, and a changed staging area needs a fresh
blocked attempt first. The approval is only consumed after a commit lands,
so a retry blocked for a different reason keeps it.

APPROVAL IS ARCHITECT-ONLY. The agent must NOT run `approve` — the
constitution forbids it; unauthorized self-approval is an auditable
governance violation. `status` and `cancel` are safe for anyone.
"""

import argparse
import io
import sys
from pathlib import Path

_script_dir = str(Path(__file__).resolve().parent)
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

import precommit_override as ovr  # noqa: E402


def _ensure_utf8_stdout():
    """Ensure stdout uses UTF-8 encoding (needed on Windows)."""
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )


def build_parser():
    parser = argparse.ArgumentParser(
        prog="gator hook override",
        description="Inspect, approve, or cancel a blocked commit (Architect).",
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("status", help="Show the last blocked commit attempt")
    p_approve = sub.add_parser(
        "approve", help="Approve the approvable findings of the blocked attempt (Architect only)")
    p_approve.add_argument("--reason", help="Why the override is justified (required)")
    p_approve.add_argument("--name", help="Architect name (required)")
    sub.add_parser("cancel", help="Drop the recorded block and any approval")
    return parser


def _normalize_argv(argv):
    """No subcommand -> approve (compatibility with the v1 script's bare flags)."""
    if not argv or argv[0].startswith("-") and argv[0] not in ("-h", "--help"):
        return ["approve"] + list(argv)
    return list(argv)


def _context():
    """(repo_root, state_dir, tree). Exits 1 with a message on failure."""
    try:
        root = ovr.resolve_repo_root()
        sdir = ovr.state_dir(root)
    except ovr.OverrideStateError as exc:
        print(f"  Error: {exc}", file=sys.stderr)
        sys.exit(1)
    try:
        tree = ovr.index_tree(root)
    except ovr.OverrideStateError as exc:
        print(f"  Error: {exc}", file=sys.stderr)
        sys.exit(1)
    return root, sdir, tree


def cmd_status(args):
    root, sdir, tree = _context()
    b_state, block = ovr.read_block(sdir)
    insp = ovr.inspect(sdir, tree)
    print()
    print("  gator override status")
    print()
    if b_state == "malformed":
        print("  The recorded block is unreadable. Run `gator hook override cancel`, "
              "then retry `git commit`.")
    else:
        for line in ovr.describe(block, insp["approval"], tree):
            print(line)
    if insp["state"] != "absent":
        print(f"    Approval state: {insp['state']} — {insp['detail']}")
    legacy = ovr.legacy_files_present(root / ".gator")
    if legacy:
        print(f"    Legacy v1 files present (ignored; retired on the next commit): "
              f"{', '.join(legacy)}")
    print()
    return 0


def cmd_cancel(args):
    root, sdir, _ = _context()
    removed = ovr.cancel(sdir)
    if removed:
        print(f"  Cancelled: removed {', '.join(removed)}.")
    else:
        print("  Nothing to cancel: no block or approval is recorded.")
    return 0


def _prompt(label):
    try:
        return input(label).strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  Cancelled.")
        sys.exit(1)


def cmd_approve(args):
    root, sdir, tree = _context()
    b_state, block = ovr.read_block(sdir)

    print()
    print("  gator override approval")
    print()

    if b_state == "absent":
        print("  No blocked commit attempt is recorded for this worktree.")
        print("  Retry `git commit`: if it is blocked, the attempt is recorded")
        print("  with each finding's resolution, and can then be reviewed here.")
        print()
        return 1
    if b_state == "malformed":
        print("  The recorded block is unreadable. Run `gator hook override cancel`,")
        print("  then retry `git commit` to record a fresh block.")
        print()
        return 1

    for line in ovr.describe(block, None, tree):
        print(line)
    print()

    if block.get("index_tree") != tree:
        print("  Refused: the staged changes differ from the blocked attempt.")
        print("  An approval covers one exact staged change. Retry `git commit` to")
        print("  record a fresh block for what is staged now, then approve that.")
        print()
        return 1
    now = ovr._now()
    if block.get("expires_epoch", 0) <= now:
        print("  Refused: this block has expired. Retry `git commit` to record a fresh one.")
        print()
        return 1

    rules = ovr.approvable_rules(block)
    fix_required = sorted({f["rule"] for f in block.get("failures", [])
                           if not ovr.is_approvable(f.get("resolution"))})
    if not rules:
        print("  Refused: nothing in this block can be approved.")
        print(f"  Fix these findings and retry the commit: {', '.join(fix_required)}")
        print()
        return 1

    wait = ovr.MIN_APPROVAL_DELAY_SECONDS - ovr.block_age_seconds(block, now)
    if wait > 0:
        print(f"  Refused: the block is too recent. Review the findings, then approve")
        print(f"  again in {int(wait) + 1}s (self-approval guard).")
        print()
        return 1

    print(f"  Approving for this exact staged change: {', '.join(rules)}")
    if fix_required:
        print(f"  Still fix-required (not approvable): {', '.join(fix_required)}")
    print()

    reason = (args.reason or "").strip() or _prompt("  Reason for override (required): ")
    if not reason:
        print("  Error: reason is required for override approval.")
        return 1
    name = (args.name or "").strip() or _prompt("  Your name (Architect): ")
    if not name:
        print("  Error: Architect name is required.")
        return 1

    try:
        approval = ovr.write_approval(sdir, block, name, reason, now=now)
    except (ValueError, OSError) as exc:
        print(f"  Error: {exc}")
        return 1

    print()
    print(f"  ✓ Override approved by {approval['approved_by']}")
    print(f"    Block ID:    {approval['block_id']}")
    print(f"    Approval ID: {approval['approval_id']}")
    print(f"    Rules:       {', '.join(approval['approved_rules'])}")
    print(f"    Reason:      {approval['reason']}")
    print(f"    Expires:     {approval['expires_at']}")
    print()
    if fix_required:
        print(f"  Fix the remaining findings ({', '.join(fix_required)}), then retry: git commit")
        print("  The approval is kept across retries while the staged change is unchanged.")
    else:
        print("  Now retry: git commit")
    print()
    return 0


def main(argv=None):
    _ensure_utf8_stdout()
    argv = _normalize_argv(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)
    handlers = {"status": cmd_status, "approve": cmd_approve, "cancel": cmd_cancel}
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
