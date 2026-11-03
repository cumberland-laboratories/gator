#!/usr/bin/env python3
"""
gator-approve.py — Architect override approval for blocked commits (#34, #35).

Reached through the hook dispatcher:

    gator hook override status            show the last blocked attempt
    gator hook override approve [...]     approve its approvable findings
    gator hook override cancel            drop the block and any approval
    gator hook override acknowledge [...] record the Architect's decision to
                                          keep the current paused findings
    gator hook approve [...]              alias of `override approve`

Every blocked commit attempt records a block (see precommit_override.py) that
lists each failed rule with its resolution class. `approve` authorizes the
approvable rules for the EXACT staged change that was blocked; it never
approves fix-required findings, and a changed staging area needs a fresh
blocked attempt first. The approval is only consumed after a commit lands,
so a retry blocked for a different reason keeps it.

Machine-readable mode (#76, for the Dashboard Commits view): `--json` on
each subcommand prints one JSON object (gator-override-status-v1,
gator-override-approve-v1, gator-override-cancel-v1) and never prompts.
`--expect-block` / `--expect-revision` on approve and cancel refuse any
state the caller did not see; the revision covers the findings and any
approval, not only the block ID, and is defined for unreadable records.

APPROVAL IS ARCHITECT-ONLY. The agent must NOT run `approve` — the
constitution forbids it; unauthorized self-approval is an auditable
governance violation. `status` and `cancel` are safe for anyone.

`acknowledge` (#102) writes the Architect's keep decision for a
dangerous-pattern pause into commit_draft.md, for every current paused
finding at once. It is not an override and touches no override state. The
Dashboard runs it after the Architect confirms; an agent runs it only
after the Architect's explicit reply to the enumerated finding set (see
procedures/dangerous-pattern-warnings.md).
"""

import argparse
import hashlib
import io
import json
import math
import sys
from pathlib import Path

_script_dir = str(Path(__file__).resolve().parent)
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

import precommit_override as ovr  # noqa: E402
import precommit_lint as lint  # noqa: E402
import precommit_policy as policy  # noqa: E402

STATUS_SCHEMA = "gator-override-status-v1"
ACK_SCHEMA = "gator-override-acknowledge-v1"
NOTE_MAX = 500
APPROVE_SCHEMA = "gator-override-approve-v1"
CANCEL_SCHEMA = "gator-override-cancel-v1"
REVISION_LENGTH = 16
KNOWN_RESOLUTIONS = (ovr.EXTERNAL_APPROVAL, ovr.PAUSE, ovr.FIX_REQUIRED)


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
    p_status = sub.add_parser("status", help="Show the last blocked commit attempt")
    p_status.add_argument("--json", action="store_true",
                          help="Print gator-override-status-v1 JSON")
    p_approve = sub.add_parser(
        "approve", help="Approve the approvable findings of the blocked attempt (Architect only)")
    p_approve.add_argument("--reason", help="Why the override is justified (required)")
    p_approve.add_argument("--name", help="Architect name (required)")
    p_cancel = sub.add_parser("cancel", help="Drop the recorded block and any approval")
    p_ack = sub.add_parser(
        "acknowledge",
        help="Record the Architect's decision to keep every current paused finding")
    which = p_ack.add_mutually_exclusive_group(required=True)
    which.add_argument("--all-current", action="store_true",
                       help="Acknowledge exactly the findings that pause the commit now")
    which.add_argument("--keys", nargs="+", metavar="KEY",
                       help="The complete current set of paused finding keys (RULE@path:line)")
    p_ack.add_argument("--architect", help="Architect name, when the draft names none")
    p_ack.add_argument("--note", help="Optional shared note for the whole set")
    p_ack.add_argument("--surface", choices=sorted(policy.ACK_SURFACES), default="agent",
                       help="Where the Architect decided (bullet text)")
    p_ack.add_argument("--json", action="store_true",
                       help="Print gator-override-acknowledge-v1 JSON")
    p_ack.add_argument("--expect-block", metavar="BLOCK_ID",
                       help="Refuse unless this is the recorded block")
    for p in (p_approve, p_cancel):
        p.add_argument("--json", action="store_true",
                       help="Print a JSON result and never prompt")
        p.add_argument("--expect-block", metavar="BLOCK_ID",
                       help="Refuse unless this is the recorded block")
        p.add_argument("--expect-revision", metavar="REVISION",
                       help="Refuse unless the recorded state is unchanged (status --json revision)")
    return parser


def _normalize_argv(argv):
    """No subcommand -> approve (compatibility with the v1 script's bare flags)."""
    if not argv or argv[0].startswith("-") and argv[0] not in ("-h", "--help"):
        return ["approve"] + list(argv)
    return list(argv)


def _emit(obj):
    print(json.dumps(obj, ensure_ascii=False))


def _context(schema=None):
    """(repo_root, state_dir, tree). Exits 1 with a message on failure.

    With ``schema`` (JSON mode) the failure is one JSON object on stdout:
    status reports ``state: unavailable``, approve/cancel a refusal.
    """
    try:
        root = ovr.resolve_repo_root()
        sdir = ovr.state_dir(root)
        tree = ovr.index_tree(root)
    except ovr.OverrideStateError as exc:
        if schema == STATUS_SCHEMA:
            _emit({"schema": schema, "state": "unavailable", "message": str(exc)})
        elif schema:
            _emit({"schema": schema, "ok": False, "refusal": "unavailable",
                   "message": str(exc)})
        else:
            print(f"  Error: {exc}", file=sys.stderr)
        sys.exit(1)
    return root, sdir, tree


# ---------------------------------------------------------------------------
# Revision fingerprint (#76)
# ---------------------------------------------------------------------------

class _Unreadable(Exception):
    """A state file exists but its bytes cannot be read."""


def _raw_digest(path):
    """sha256 hex of a state file's bytes; None when absent.

    Raises _Unreadable when the file exists but cannot be read, so callers
    fail safe: no revision, so no guarded action can match it.
    """
    try:
        data = Path(path).read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise _Unreadable(str(exc))
    return hashlib.sha256(data).hexdigest()


def _record_part(sdir, filename, state, value):
    if state == "ok":
        return value
    if state == "malformed":
        digest = _raw_digest(Path(sdir) / filename)
        return None if digest is None else ["malformed", digest]
    return None


def _revision(block_part, approval_part):
    """16-hex fingerprint of the recorded state the caller is looking at."""
    text = json.dumps([block_part, approval_part], separators=(",", ":"),
                      ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:REVISION_LENGTH]


def _snapshot(sdir):
    """Read block + approval once. Returns a dict with the parsed records,
    their states, and ``revision``: None when nothing is recorded, or when a
    record exists but cannot be read (``unreadable`` True)."""
    b_state, block = ovr.read_block(sdir)
    a_state, approval = ovr.read_approval(sdir)
    snap = {"b_state": b_state, "block": block, "a_state": a_state,
            "approval": approval, "revision": None, "unreadable": False}
    block_value = None
    if b_state == "ok":
        block_value = [block["block_id"], block["index_tree"],
                       [[f["rule"], f["resolution"], f.get("message", "")]
                        for f in block["failures"]]]
    approval_value = approval["approval_id"] if a_state == "ok" else None
    try:
        bp = _record_part(sdir, ovr.BLOCK_FILE, b_state, block_value)
        ap = _record_part(sdir, ovr.APPROVAL_FILE, a_state, approval_value)
    except _Unreadable:
        snap["unreadable"] = True
        return snap
    if bp is not None or ap is not None:
        snap["revision"] = _revision(bp, ap)
    return snap


def _guard_refusal(snap, expect_block, expect_revision):
    """(code, lines) when the caller's expectation no longer holds, else None."""
    block = snap["block"] if snap["b_state"] == "ok" else None
    if expect_block is not None and (block is None or block["block_id"] != expect_block):
        return ("block-changed", [
            "  Refused: the blocked commit attempt changed since it was shown.",
            "  Review it again (`gator hook override status`) before acting."])
    if expect_revision is not None and snap["revision"] != expect_revision:
        if snap["unreadable"]:
            return ("unavailable", [
                "  Refused: the recorded override state cannot be read. Run",
                "  `gator hook override cancel` in a terminal, then retry `git commit`."])
        return ("findings-changed", [
            "  Refused: the findings or approval changed since they were shown.",
            "  Review them again (`gator hook override status`) before acting."])
    return None


# ---------------------------------------------------------------------------
# The single approval refusal sequence (human and JSON paths)
# ---------------------------------------------------------------------------

def _failure_rules(block, resolution):
    return sorted({f["rule"] for f in block.get("failures", [])
                   if f.get("resolution") == resolution})


def _approval_refusal(snap, tree, now, expect_block=None, expect_revision=None):
    """None when ``approve`` may write an approval, else (code, lines, extra).

    Codes, in order: no-block, malformed, block-changed, findings-changed
    (or unavailable), tree-changed, expired, legacy, nothing-approvable,
    too-recent. ``lines`` is the human text; JSON joins it into ``message``.
    """
    b_state, block = snap["b_state"], snap["block"]
    if b_state == "absent":
        return ("no-block", [
            "  No blocked commit attempt is recorded for this worktree.",
            "  Retry `git commit`: if it is blocked, the attempt is recorded",
            "  with each finding's resolution, and can then be reviewed here."], {})
    if b_state == "malformed":
        return ("malformed", [
            "  The recorded block is unreadable. Run `gator hook override cancel`,",
            "  then retry `git commit` to record a fresh block."], {})
    guard = _guard_refusal(snap, expect_block, expect_revision)
    if guard:
        return guard + ({},)
    if block.get("index_tree") != tree:
        return ("tree-changed", [
            "  Refused: the staged changes differ from the blocked attempt.",
            "  An approval covers one exact staged change. Retry `git commit` to",
            "  record a fresh block for what is staged now, then approve that."], {})
    if block.get("expires_epoch", 0) <= now:
        return ("expired", [
            "  Refused: this block has expired. Retry `git commit` to record a fresh one."], {})
    legacy = ovr.legacy_rules(block)
    if legacy:
        return ("legacy", [
            f"  Refused: {', '.join(legacy)} was recorded by an earlier Gator runtime.",
            "  Gator no longer evaluates it. Run `gator hook override cancel` and",
            "  retry the commit; the retry uses the current policy."], {})
    if not ovr.approvable_rules(block):
        fix_required = _failure_rules(block, ovr.FIX_REQUIRED)
        paused = _failure_rules(block, ovr.PAUSE)
        lines = ["  Refused: nothing in this block can be approved."]
        if fix_required:
            lines.append(f"  Fix these findings and retry the commit: {', '.join(fix_required)}")
        if paused:
            lines.append("  A dangerous-pattern pause is resolved by recording the Architect's")
            lines.append("  decision in commit_draft.md, never by this command. The Dashboard")
            lines.append("  records it, or `gator hook override acknowledge` after the")
            lines.append("  Architect's explicit reply.")
        return ("nothing-approvable", lines, {})
    wait = ovr.MIN_APPROVAL_DELAY_SECONDS - ovr.block_age_seconds(block, now)
    if wait > 0:
        return ("too-recent", [
            "  Refused: the block is too recent. Review the findings, then approve",
            f"  again in {int(wait) + 1}s (self-approval guard)."],
            {"retry_after_seconds": int(wait) + 1})
    return None


def _message(lines):
    return " ".join(line.strip() for line in lines)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

def _architect_default(root):
    try:
        r = ovr._git(["config", "user.name"], root)
    except OSError:
        return None
    name = (r.stdout or "").strip() if r.returncode == 0 else ""
    return name or None


def _status_record(root, sdir, tree, now):
    """gator-override-status-v1 for the current worktree. Read-only."""
    snap = _snapshot(sdir)
    insp = ovr.inspect(sdir, tree, now)
    b_state, block = snap["b_state"], snap["block"]
    malformed = [name for name, state in (("block", b_state), ("approval", snap["a_state"]))
                 if state == "malformed"]

    findings = []
    if b_state == "ok":
        for f in block["failures"]:
            recorded = f["resolution"]
            rec = {"rule": f["rule"],
                   "resolution": recorded if recorded in KNOWN_RESOLUTIONS else ovr.FIX_REQUIRED,
                   "message": f.get("message", ""), "covered": False}
            if recorded in ovr.LEGACY_RESOLUTIONS:
                rec["legacy"] = True
            findings.append(rec)
    external = {f["rule"] for f in findings if f["resolution"] == ovr.EXTERNAL_APPROVAL}
    covered = set()
    if insp["state"] == "valid":
        covered = ovr.approval_coverage(
            insp["approval"], [(f["rule"], f["resolution"]) for f in findings])
    for f in findings:
        f["covered"] = f["rule"] in covered
    uncovered = sorted(external - covered)

    if malformed or snap["unreadable"]:
        state = "malformed"
    elif b_state == "absent":
        state = "none"
    elif block["expires_epoch"] <= now:
        state = "expired"
    elif block["index_tree"] != tree:
        state = "stale"
    elif ovr.legacy_rules(block):
        state = "legacy"
    elif covered and not uncovered:
        state = "approved"
    else:
        state = "blocked"

    refusal = _approval_refusal(snap, tree, now)
    wait = 0
    block_view = None
    if b_state == "ok":
        age = ovr.block_age_seconds(block, now)
        wait = max(0, math.ceil(ovr.MIN_APPROVAL_DELAY_SECONDS - age))
        block_view = {
            "block_id": block["block_id"],
            "created_at": block.get("created_at"),
            "created_epoch": block["created_epoch"],
            "expires_at": block.get("expires_at"),
            "expires_epoch": block["expires_epoch"],
            "age_seconds": int(age),
            "tree_matches": block["index_tree"] == tree,
            "files": list(block["files"]),
        }
    approval_view = {"state": insp["state"], "detail": insp["detail"]}
    approval = insp.get("approval")
    if approval:
        approval_view.update({
            "approval_id": approval["approval_id"],
            "approved_by": approval["approved_by"],
            "approved_at": approval.get("approved_at"),
            "approved_rules": list(approval["approved_rules"]),
        })
    return {
        "schema": STATUS_SCHEMA,
        "state": state,
        "revision": snap["revision"],
        "malformed": malformed,
        "block": block_view,
        "findings": findings,
        "approval": approval_view,
        "approvable_rules": ovr.approvable_rules(block) if b_state == "ok" else [],
        "covered_rules": sorted(covered),
        "uncovered_external_rules": uncovered,
        "can_approve": refusal is None and bool(uncovered),
        "approve_refusal": refusal[0] if refusal else None,
        "approve_wait_seconds": wait,
        "min_approval_delay_seconds": ovr.MIN_APPROVAL_DELAY_SECONDS,
        "architect_default": _architect_default(root),
        # #102 (additive): the findings a pause still waits on (never the
        # matched source text), and the Architect the draft already names.
        "pause_findings": _pause_findings(root, block, tree) if b_state == "ok" else [],
        "draft_architect": _draft_architect(root),
    }


def cmd_status(args):
    if args.json:
        root, sdir, tree = _context(STATUS_SCHEMA)
        _emit(_status_record(root, sdir, tree, ovr._now()))
        return 0
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


# ---------------------------------------------------------------------------
# cancel
# ---------------------------------------------------------------------------

def cmd_cancel(args):
    root, sdir, _ = _context(CANCEL_SCHEMA if args.json else None)
    if args.expect_block is not None or args.expect_revision is not None:
        guard = _guard_refusal(_snapshot(sdir), args.expect_block, args.expect_revision)
        if guard:
            code, lines = guard
            if args.json:
                _emit({"schema": CANCEL_SCHEMA, "ok": False, "refusal": code,
                       "message": _message(lines), "removed": []})
            else:
                for line in lines:
                    print(line)
            return 1
    removed = ovr.cancel(sdir)
    if args.json:
        _emit({"schema": CANCEL_SCHEMA, "ok": True, "refusal": None,
               "message": (f"Cancelled: removed {', '.join(removed)}." if removed
                           else "Nothing to cancel: no block or approval is recorded."),
               "removed": removed})
        return 0
    if removed:
        print(f"  Cancelled: removed {', '.join(removed)}.")
    else:
        print("  Nothing to cancel: no block or approval is recorded.")
    return 0


# ---------------------------------------------------------------------------
# approve
# ---------------------------------------------------------------------------

def _prompt(label):
    try:
        return input(label).strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  Cancelled.")
        sys.exit(1)


def _approve_json(snap, tree, now, sdir, args):
    def refuse(code, message, extra=None, block=None):
        out = {"schema": APPROVE_SCHEMA, "ok": False, "refusal": code,
               "message": message, "retry_after_seconds": None, "approval": None,
               "remaining": {"fix_required": [], "paused": []}}
        if block is not None:
            out["remaining"] = {"fix_required": _failure_rules(block, ovr.FIX_REQUIRED),
                                "paused": _failure_rules(block, ovr.PAUSE)}
        out.update(extra or {})
        _emit(out)
        return 1

    refusal = _approval_refusal(snap, tree, now, args.expect_block, args.expect_revision)
    block = snap["block"] if snap["b_state"] == "ok" else None
    if refusal:
        code, lines, extra = refusal
        return refuse(code, _message(lines), extra, block)
    name = (args.name or "").strip()
    reason = (args.reason or "").strip()
    if not name or not reason:
        return refuse("invalid-input", "An Architect name and a reason are required.",
                      block=block)
    if (len(name) > ovr.TRAILER_MAX["approved_by"]
            or len(reason) > ovr.TRAILER_MAX["reason"]):
        return refuse("invalid-input",
                      f"The name is limited to {ovr.TRAILER_MAX['approved_by']} characters "
                      f"and the reason to {ovr.TRAILER_MAX['reason']}.", block=block)
    try:
        approval = ovr.write_approval(sdir, block, name, reason, now=now)
    except (ValueError, OSError) as exc:
        return refuse("write-failed", str(exc), block=block)
    _emit({
        "schema": APPROVE_SCHEMA, "ok": True, "refusal": None,
        "message": f"Override approved by {approval['approved_by']}.",
        "retry_after_seconds": None,
        "approval": {k: approval[k] for k in ("approval_id", "block_id", "approved_rules",
                                              "approved_by", "expires_at")},
        "remaining": {"fix_required": _failure_rules(block, ovr.FIX_REQUIRED),
                      "paused": _failure_rules(block, ovr.PAUSE)},
    })
    return 0


def cmd_approve(args):
    root, sdir, tree = _context(APPROVE_SCHEMA if args.json else None)
    now = ovr._now()
    snap = _snapshot(sdir)
    if args.json:
        return _approve_json(snap, tree, now, sdir, args)

    print()
    print("  gator override approval")
    print()

    refusal = _approval_refusal(snap, tree, now, args.expect_block, args.expect_revision)
    if refusal and refusal[0] in ("no-block", "malformed"):
        for line in refusal[1]:
            print(line)
        print()
        return 1

    block = snap["block"]
    for line in ovr.describe(block, None, tree):
        print(line)
    print()

    if refusal:
        for line in refusal[1]:
            print(line)
        print()
        return 1

    rules = ovr.approvable_rules(block)
    fix_required = _failure_rules(block, ovr.FIX_REQUIRED)
    paused = _failure_rules(block, ovr.PAUSE)
    print(f"  Approving for this exact staged change: {', '.join(rules)}")
    if fix_required:
        print(f"  Still fix-required (not approvable): {', '.join(fix_required)}")
    if paused:
        print(f"  Still paused (record the Architect's decision in commit_draft.md): "
              f"{', '.join(paused)}")
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


# ---------------------------------------------------------------------------
# acknowledge (#102): one scoped Architect decision for a pause
# ---------------------------------------------------------------------------

def _draft_path(root):
    return Path(root) / ".gator" / "commit_draft.md"


def _read_draft(root):
    """(text, frontmatter, body, error); text None when the draft is absent."""
    path = _draft_path(root)
    if not path.is_file():
        return None, {}, "", None
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        text = f.read()
    _, frontmatter, body, error = policy.split_draft(text)
    return text, frontmatter, body, error


def _draft_architect(root):
    try:
        _, frontmatter, _, error = _read_draft(root)
    except OSError:
        return None
    value = " ".join(str(frontmatter.get("architect") or "").split()) if not error else ""
    return value or None


def _current_dangerous(root):
    """The live HIGH/CRITICAL warning findings of the staged change, read
    exactly as the hook reads them (Layer 1 lint, strict split)."""
    r = ovr._git(["diff", "--cached", "--name-only"], root)
    if r.returncode != 0:
        raise ovr.OverrideStateError("cannot read the staged files")
    staged = [line for line in (r.stdout or "").splitlines() if line.strip()]
    dangerous, _, _ = policy.split_lint(lint.run_layer1_lint(staged, root), "strict")
    return dangerous


def _unresolved(dangerous, frontmatter, body):
    """(unresolved findings, acknowledged keys, problems) against the draft."""
    ack, ack_problems = policy.validate_acknowledgements(frontmatter, body, dangerous)
    skip, skip_problems = policy.validate_skips(frontmatter, dangerous, ack)
    decided = set(ack) | set(skip)
    pending = [f for f in dangerous if policy.finding_key(f) not in decided]
    return pending, list(ack), ack_problems + skip_problems


def _finding_view(f):
    return {"key": policy.finding_key(f), "rule": f.get("rule"), "file": f.get("file"),
            "line": f.get("line"), "severity": f.get("severity"),
            "message": f.get("message", "")}


def _pause_findings(root, block, tree):
    """Status view: the paused findings, only while the recorded block is a
    pause for this exact staged change. Never raises."""
    try:
        if block.get("index_tree") != tree or not _failure_rules(block, ovr.PAUSE):
            return []
        _, frontmatter, body, error = _read_draft(root)
        if error:
            frontmatter, body = {}, ""
        pending, _, _ = _unresolved(_current_dangerous(root), frontmatter, body)
        return [_finding_view(f) for f in pending]
    except Exception:  # noqa: BLE001 — status stays readable
        return []


def _ack_refusal(code, lines, args, extra=None):
    if args.json:
        out = {"schema": ACK_SCHEMA, "ok": False, "refusal": code, "message": _message(lines)}
        out.update(extra or {})
        _emit(out)
    else:
        print()
        for line in lines:
            print(line)
        print()
    return 1


def _write_atomic(path, text):
    import os
    import tempfile
    fd, tmp = tempfile.mkstemp(prefix=".commit_draft.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def cmd_acknowledge(args):
    root, sdir, tree = _context(ACK_SCHEMA if args.json else None)
    snap = _snapshot(sdir)
    if snap["b_state"] != "ok":
        return _ack_refusal("no-block", [
            "  No readable blocked commit attempt is recorded for this worktree.",
            "  Retry `git commit`: a dangerous-pattern pause is recorded, then decided."], args)
    block = snap["block"]
    guard = _guard_refusal(snap, args.expect_block, None)
    if guard:
        return _ack_refusal(guard[0], guard[1], args)
    if not _failure_rules(block, ovr.PAUSE):
        return _ack_refusal("no-pause", [
            "  The recorded attempt is not paused on a dangerous pattern."], args)
    if block.get("index_tree") != tree:
        return _ack_refusal("tree-changed", [
            "  Refused: the staged changes differ from the paused attempt, so the",
            "  findings may have moved. Retry `git commit` and decide on the new pause."], args)
    try:
        text, frontmatter, body, error = _read_draft(root)
    except OSError as exc:
        return _ack_refusal("unavailable", [f"  Refused: cannot read commit_draft.md: {exc}"], args)
    if text is None or error or not text.startswith("---"):
        return _ack_refusal("draft-unstructured", [
            "  Refused: commit_draft.md has no readable frontmatter block. Fix the",
            "  draft (see /commit), then record the decision."], args)
    try:
        dangerous = _current_dangerous(root)
    except ovr.OverrideStateError as exc:
        return _ack_refusal("unavailable", [f"  Refused: {exc}"], args)
    pending, ack_keys, problems = _unresolved(dangerous, frontmatter, body)
    if problems:
        return _ack_refusal("existing-evidence-invalid", [
            "  Refused: commit_draft.md already holds dangerous-pattern evidence that",
            "  does not match the staged change: " + "; ".join(problems)], args)
    current = [policy.finding_key(f) for f in pending]
    if not current:
        return _ack_refusal("no-pause", [
            "  Every current dangerous-pattern finding already has a recorded decision.",
            "  Retry the commit."], args)
    requested = current if args.all_current else list(args.keys)
    if len(set(requested)) != len(requested) or set(requested) != set(current):
        return _ack_refusal("findings-changed", [
            "  Refused: the decision must cover exactly the current paused findings:",
            "  " + ", ".join(current) + ". Show them to the Architect again."],
            args, {"current_keys": current})

    supplied = " ".join(str(args.architect or "").split())
    note = " ".join(str(args.note or "").split())
    if len(supplied) > ovr.TRAILER_MAX["approved_by"] or len(note) > NOTE_MAX:
        return _ack_refusal("invalid-input", [
            f"  Refused: the Architect name is limited to {ovr.TRAILER_MAX['approved_by']}"
            f" characters and the note to {NOTE_MAX}."], args)
    named = " ".join(str(frontmatter.get("architect") or "").split())
    if named and supplied and supplied != named:
        return _ack_refusal("architect-mismatch", [
            f"  Refused: commit_draft.md names the Architect as {named!r}, not {supplied!r}."],
            args, {"draft_architect": named})
    architect = named or supplied
    if not architect:
        return _ack_refusal("architect-required", [
            "  Refused: name the Architect who decided (--architect); commit_draft.md",
            "  names none."], args)

    try:
        new_text = policy.render_acknowledgement(text, current, architect,
                                                 note=note, surface=args.surface)
    except ValueError as exc:
        return _ack_refusal("write-failed", [f"  Refused: {exc}. Nothing was written."], args)
    _, fm2, body2, err2 = policy.split_draft(new_text)
    keys2, problems2 = ([], [err2]) if err2 else policy.validate_acknowledgements(
        fm2, body2, dangerous)
    if problems2 or set(keys2) != set(ack_keys) | set(current):
        return _ack_refusal("write-failed", [
            "  Refused: the recorded decision would not validate ("
            + "; ".join(problems2 or ["unexpected key set"]) + "). Nothing was written."], args)
    try:
        _write_atomic(_draft_path(root), new_text)
    except OSError as exc:
        return _ack_refusal("write-failed", [f"  Refused: cannot write commit_draft.md: {exc}"], args)

    if args.json:
        _emit({"schema": ACK_SCHEMA, "ok": True, "outcome": "retry-commit",
               "acknowledged": current, "all_acknowledged": sorted(keys2),
               "architect": architect, "block_id": block["block_id"]})
    else:
        print()
        print(f"  Decision recorded for {len(current)} finding(s), kept on the direction of {architect}:")
        for key in current:
            print(f"    - {key}")
        print("  Retry the commit: git commit")
        print()
    return 0


def main(argv=None):
    _ensure_utf8_stdout()
    argv = _normalize_argv(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)
    handlers = {"status": cmd_status, "approve": cmd_approve, "cancel": cmd_cancel,
                "acknowledge": cmd_acknowledge}
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
