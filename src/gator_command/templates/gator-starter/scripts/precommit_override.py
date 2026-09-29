#!/usr/bin/env python3
"""
precommit_override.py — tree-bound pre-commit override state (#34, #35).

The single interpreter for the pre-commit block/approval envelope, shared by
gator-pre-commit.py (validate / trailers / cleanup) and gator-approve.py
(status / approve / cancel). Nothing else reads or writes these files.

State lives per worktree under ``$(git rev-parse --git-path gator-override)/``
(e.g. ``.git/gator-override/`` or ``.git/worktrees/<wt>/gator-override/``):
Git can never stage it, the Dashboard cannot serve it, and each linked
worktree (with its own index) has its own state.

  block.json     every blocked attempt: the staged-change identity
                 (index_tree(): a digest of `git ls-files --stage` minus
                 hook-managed .gator files), every failed rule
                 and its resolution class. block_id is stable for the life
                 of one index tree and does not depend on the failure set.
  approval.json  immutable Architect snapshot bound to one exact tree and a
                 set of approved rules. Validate never rewrites it.
  handoff.json   written by validate on a pass that used an approval; read
                 by commit-msg for trailers. Not consumed until post-commit.

Lifecycle: an approval is consumed only by ``retire()`` in post-commit, after
the commit exists. A retry blocked for another reason keeps the approval.
A tree change, expiry, or ``cancel()`` retires it.

@reads/@writes: <git-path>/gator-override/{block,approval,handoff}.json
@does-not-own: rule evaluation (gator-pre-commit.py), the interactive
               approval UX (gator-approve.py)
"""

import hashlib
import json
import os
import secrets
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = "gator-override-v2"
EXPIRY_HOURS = 24
# Anti-self-approval friction carried over from the v1 flow: an approval
# must be written at least this long after the block it approves.
MIN_APPROVAL_DELAY_SECONDS = 10

STATE_DIRNAME = "gator-override"
BLOCK_FILE = "block.json"
APPROVAL_FILE = "approval.json"
HANDOFF_FILE = "handoff.json"

# Resolution classes for failed rules.
APPROVABLE = "approvable"      # Architect may authorize this exact tree
LINT = "lint"                  # HIGH/CRITICAL Layer 1 lint; approvable via the envelope
FIX_REQUIRED = "fix-required"  # correctness failures; never approvable

APPROVABLE_RULES = frozenset({
    "charter-alongside-code",
    "cross-cutting-missing",
    "charter-index-gap",
})
FIX_REQUIRED_RULES = frozenset({
    "frontmatter-parse",
    "invalid-change-type",
    "invalid-significance",
    "empty-commit-draft",
    "missing-message",
    "legacy-override-file",
    "unmerged-index",
})
CHARTER_OVERRIDE_RULES = APPROVABLE_RULES

# Legacy v1 files in .gator/ — detected and retired, never interpreted.
LEGACY_FILES = (
    "override-request.json",
    "override-approved.json",
    ".override-meta.json",
    ".override",
)

TRAILER_MAX = {"approved_by": 80, "reason": 200}


class OverrideStateError(Exception):
    """Environment problem (not a git repo, unmerged index, ...)."""


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------

def _git(args, cwd):
    return subprocess.run(
        ["git"] + list(args), cwd=str(cwd), capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )


def resolve_repo_root(cwd=None):
    """Git worktree top level for ``cwd`` that contains ``.gator/``.

    Raises OverrideStateError outside a git worktree or a governed repo.
    """
    cwd = Path(cwd or Path.cwd())
    try:
        r = _git(["rev-parse", "--show-toplevel"], cwd)
    except OSError as exc:
        raise OverrideStateError(f"git is not available: {exc}")
    top = (r.stdout or "").strip()
    if r.returncode != 0 or not top:
        raise OverrideStateError(
            f"not inside a git worktree: {cwd}")
    root = Path(top)
    if not (root / ".gator").is_dir():
        raise OverrideStateError(
            f"not a Gator-governed repo (no .gator/ at {root})")
    return root


def state_dir(repo_root):
    """Per-worktree state directory (not created)."""
    repo_root = Path(repo_root)
    r = _git(["rev-parse", "--git-path", STATE_DIRNAME], repo_root)
    out = (r.stdout or "").strip()
    if r.returncode != 0 or not out:
        raise OverrideStateError(f"cannot resolve git path in {repo_root}")
    p = Path(out)
    return p if p.is_absolute() else (repo_root / p)


# Files the hooks themselves write/stage during a commit attempt (or that
# carry the commit message being fixed). They must not count toward the
# staged-change identity, or every attempt would look like a different
# change: validate stages status.json / whiteboard.md / commit_issues.md
# with fresh timestamps, the pass path restages lint-allow.json, and fixing
# a fix-required finding means editing commit_draft.md.
HOOK_MANAGED_PATHS = frozenset({
    ".gator/status.json",
    ".gator/whiteboard.md",
    ".gator/commit_issues.md",
    ".gator/lint-allow.json",
    ".gator/commit_draft.md",
})


def index_tree(repo_root):
    """Deterministic identity of the staged change (the approval binding).

    SHA-256 over every ``git ls-files --stage`` entry (mode, blob OID, path)
    except ``HOOK_MANAGED_PATHS``. Any staged add, delete, rename, mode or
    content change, or restage of different content changes it. This is the
    plan's "equivalently complete deterministic digest" of ``git write-tree``.

    Fails closed with OverrideStateError when the index has unmerged
    entries or cannot be read.
    """
    r = subprocess.run(
        ["git", "ls-files", "--stage", "-z"], cwd=str(repo_root),
        capture_output=True,
    )
    if r.returncode != 0:
        raise OverrideStateError(
            "cannot read the staged index: "
            + r.stderr.decode("utf-8", "replace").strip())
    digest = hashlib.sha256()
    for entry in r.stdout.split(b"\0"):
        if not entry:
            continue
        meta, _, path = entry.partition(b"\t")
        parts = meta.split()
        if len(parts) != 3:
            raise OverrideStateError("unexpected `git ls-files --stage` output")
        mode, oid, stage = parts
        if stage != b"0":
            raise OverrideStateError(
                "the index has unmerged entries (resolve merge conflicts first)")
        if path.decode("utf-8", "replace").replace("\\", "/") in HOOK_MANAGED_PATHS:
            continue
        digest.update(mode + b" " + oid + b" " + path + b"\0")
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Classification + sanitization
# ---------------------------------------------------------------------------

def classify(rule, lint_rules=()):
    """Resolution class for a failed rule. Unknown rules fail closed."""
    if rule in APPROVABLE_RULES:
        return APPROVABLE
    if rule in lint_rules:
        return LINT
    return FIX_REQUIRED


def is_approvable(resolution):
    return resolution in (APPROVABLE, LINT)


def sanitize_trailer_value(value, max_len):
    """Single-line, bounded, trailer-safe text (no CR/LF injection)."""
    text = " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text


# ---------------------------------------------------------------------------
# Atomic JSON I/O
# ---------------------------------------------------------------------------

def _now():
    return time.time()


def _iso(epoch):
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.stem + "-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_json(path):
    """(state, data): ('absent', None) | ('malformed', None) | ('ok', dict)."""
    path = Path(path)
    if not path.exists():
        return "absent", None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "malformed", None
    if not isinstance(data, dict):
        return "malformed", None
    return "ok", data


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_str(v, allow_empty=False):
    return isinstance(v, str) and (allow_empty or bool(v))


def _is_str_list(v):
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


# Required envelope fields and their type checks. A record that is valid
# JSON with the right schema string but missing or mistyped fields is
# `malformed` — it must fail closed, never raise inside a hook.
_BLOCK_FIELDS = {
    "block_id": _is_str,
    "index_tree": _is_str,
    "created_epoch": _is_num,
    "expires_epoch": _is_num,
    "files": _is_str_list,
}
_APPROVAL_FIELDS = {
    "approval_id": _is_str,
    "block_id": _is_str,
    "index_tree": _is_str,
    "approved_rules": _is_str_list,
    "approved_by": _is_str,
    "reason": _is_str,
    "approved_epoch": _is_num,
    "expires_epoch": _is_num,
}
_HANDOFF_FIELDS = {
    "block_id": _is_str,
    "approval_id": _is_str,
    "index_tree": _is_str,
    "overridden_rules": _is_str_list,
    "approved_by": lambda v: _is_str(v, allow_empty=True),
    "reason": lambda v: _is_str(v, allow_empty=True),
}


def _valid_envelope(data, fields):
    if data.get("schema") != SCHEMA:
        return False
    return all(name in data and check(data[name]) for name, check in fields.items())


def _valid_failures(value):
    return isinstance(value, list) and all(
        isinstance(f, dict) and _is_str(f.get("rule")) and _is_str(f.get("resolution"))
        and _is_str(f.get("message", ""), allow_empty=True)
        for f in value)


def _remove(path):
    try:
        Path(path).unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Block
# ---------------------------------------------------------------------------

def read_block(sdir):
    state, data = _read_json(Path(sdir) / BLOCK_FILE)
    if state == "ok" and not (_valid_envelope(data, _BLOCK_FIELDS)
                              and _valid_failures(data.get("failures"))):
        return "malformed", None
    return state, data


def write_block(sdir, tree, failures, files, lint_rules=(), now=None):
    """Write or refresh block.json for this attempt.

    ``failures`` is a list of (rule, message). block_id is kept while the
    tree is unchanged (and the block unexpired); a new tree gets a new id.
    Returns the written block dict.
    """
    now = _now() if now is None else now
    state, existing = read_block(sdir)
    if (state == "ok" and existing.get("index_tree") == tree
            and existing.get("expires_epoch", 0) > now):
        block_id = existing["block_id"]
        created = existing["created_epoch"]
    else:
        block_id = secrets.token_hex(4)
        created = now
    expires = created + EXPIRY_HOURS * 3600
    seen = set()
    records = []
    for rule, message in failures:
        records.append({
            "rule": rule,
            "resolution": classify(rule, lint_rules),
            "message": message,
        })
        seen.add(rule)
    block = {
        "schema": SCHEMA,
        "block_id": block_id,
        "created_epoch": created,
        "created_at": _iso(created),
        "updated_at": _iso(now),
        "expires_epoch": expires,
        "expires_at": _iso(expires),
        "index_tree": tree,
        "failures": records,
        "files": sorted(set(files)),
    }
    _write_json(Path(sdir) / BLOCK_FILE, block)
    return block


def approvable_rules(block):
    return sorted({f["rule"] for f in block.get("failures", [])
                   if is_approvable(f.get("resolution"))})


# ---------------------------------------------------------------------------
# Approval
# ---------------------------------------------------------------------------

def read_approval(sdir):
    state, data = _read_json(Path(sdir) / APPROVAL_FILE)
    if state == "ok" and not _valid_envelope(data, _APPROVAL_FIELDS):
        return "malformed", None
    return state, data


def write_approval(sdir, block, approved_by, reason, now=None):
    """Write an immutable approval snapshot for ``block``'s approvable rules.

    Caller (gator-approve.py) validates that the block still matches the
    current tree and is old enough. Raises ValueError on an empty name or
    reason, or when the block has nothing approvable.
    """
    now = _now() if now is None else now
    approved_by = str(approved_by or "").strip()
    reason = str(reason or "").strip()
    if not approved_by:
        raise ValueError("Architect name is required")
    if not reason:
        raise ValueError("a reason is required")
    rules = approvable_rules(block)
    if not rules:
        raise ValueError("this block has no approvable rules")
    approval = {
        "schema": SCHEMA,
        "approval_id": secrets.token_hex(4),
        "block_id": block["block_id"],
        "index_tree": block["index_tree"],
        "approved_rules": rules,
        "approved_by": approved_by,
        "reason": reason,
        "approved_epoch": now,
        "approved_at": _iso(now),
        "expires_epoch": block["expires_epoch"],
        "expires_at": block["expires_at"],
    }
    _write_json(Path(sdir) / APPROVAL_FILE, approval)
    return approval


def inspect(sdir, tree, now=None):
    """Classify the approval against the current tree. Read-only.

    Returns {"state": absent|malformed|expired|mismatch|premature|valid,
             "approval": dict|None, "block": dict|None, "detail": str}
    Only "valid" authorizes anything; every other state fails closed.
    """
    now = _now() if now is None else now
    b_state, block = read_block(sdir)
    a_state, approval = read_approval(sdir)
    result = {"approval": approval, "block": block if b_state == "ok" else None}
    if a_state == "absent":
        return dict(result, state="absent", detail="no approval recorded")
    if a_state == "malformed":
        return dict(result, state="malformed",
                    detail="approval.json is unreadable or not a gator-override-v2 record")
    if approval["expires_epoch"] <= now:
        return dict(result, state="expired",
                    detail=f"approval {approval['approval_id']} expired at {approval.get('expires_at')}")
    if approval["index_tree"] != tree:
        return dict(result, state="mismatch",
                    detail=(f"approval {approval['approval_id']} was for a different staged tree; "
                            "the staged changes changed after approval"))
    if (block is not None and block.get("index_tree") == tree
            and approval["approved_epoch"] < block["created_epoch"] + MIN_APPROVAL_DELAY_SECONDS):
        return dict(result, state="premature",
                    detail=(f"approval was written less than {MIN_APPROVAL_DELAY_SECONDS}s "
                            "after the block (self-approval guard)"))
    return dict(result, state="valid", detail=f"approval {approval['approval_id']} is valid for this tree")


def retire_approval(sdir):
    return _remove(Path(sdir) / APPROVAL_FILE)


# ---------------------------------------------------------------------------
# Handoff (validate -> commit-msg)
# ---------------------------------------------------------------------------

def write_handoff(sdir, approval, overridden_rules, now=None):
    now = _now() if now is None else now
    rules = sorted(set(overridden_rules))
    handoff = {
        "schema": SCHEMA,
        "block_id": approval["block_id"],
        "approval_id": approval["approval_id"],
        "index_tree": approval["index_tree"],
        "overridden_rules": rules,
        "charter_override": any(r in CHARTER_OVERRIDE_RULES for r in rules),
        "approved_by": sanitize_trailer_value(approval["approved_by"], TRAILER_MAX["approved_by"]),
        "reason": sanitize_trailer_value(approval["reason"], TRAILER_MAX["reason"]),
        "written_at": _iso(now),
    }
    _write_json(Path(sdir) / HANDOFF_FILE, handoff)
    return handoff


def read_handoff(sdir, tree=None):
    """The handoff if present, well-formed, and (when given) for ``tree``."""
    state, data = _read_json(Path(sdir) / HANDOFF_FILE)
    if state != "ok" or not _valid_envelope(data, _HANDOFF_FIELDS):
        return None
    if tree is not None and data.get("index_tree") != tree:
        return None
    return data


def clear_handoff(sdir):
    return _remove(Path(sdir) / HANDOFF_FILE)


def override_trailers(handoff):
    """Sanitized Gator-Override-* trailer lines for a handoff."""
    if not handoff:
        return []
    lines = []
    by = sanitize_trailer_value(handoff.get("approved_by"), TRAILER_MAX["approved_by"])
    if by:
        lines.append(f"Gator-Override-Approved-By: {by}")
    if handoff.get("block_id"):
        lines.append(f"Gator-Override-Block: {sanitize_trailer_value(handoff['block_id'], 40)}")
    reason = sanitize_trailer_value(handoff.get("reason"), TRAILER_MAX["reason"])
    if reason:
        lines.append(f"Gator-Override-Reason: {reason}")
    rules = handoff.get("overridden_rules") or []
    if rules:
        lines.append("Gator-Override-Rules: "
                     + sanitize_trailer_value(",".join(rules), 200))
    return lines


# ---------------------------------------------------------------------------
# Retirement
# ---------------------------------------------------------------------------

def legacy_files_present(gator_dir):
    gator_dir = Path(gator_dir)
    return [name for name in LEGACY_FILES if (gator_dir / name).exists()]


def retire(sdir, gator_dir=None):
    """Idempotently remove all transient override state (post-commit).

    Removes block, approval, and handoff, plus legacy v1 files in
    ``gator_dir``. Returns the list of removed names.
    """
    removed = []
    for name in (BLOCK_FILE, APPROVAL_FILE, HANDOFF_FILE):
        if _remove(Path(sdir) / name):
            removed.append(name)
    if gator_dir is not None:
        for name in LEGACY_FILES:
            if _remove(Path(gator_dir) / name):
                removed.append(f".gator/{name}")
    return removed


def cancel(sdir):
    """Architect/agent-safe cancellation: drop block, approval, and handoff."""
    return retire(sdir)


def block_age_seconds(block, now=None):
    now = _now() if now is None else now
    return max(0.0, now - block.get("created_epoch", now))


def apply_approval(sdir, tree, failures, lint_rules=()):
    """Apply a stored approval to this attempt's failures. The one approval
    decision shared by every validate path (strict and Enterprise
    evidence_only), so they cannot diverge.

    ``failures`` is a list of (rule, message). Clears any stale handoff,
    retires an approval that is expired / mismatched / malformed /
    premature, and removes only failures whose rule the valid approval
    names AND that classify approvable or lint. Writes the handoff when an
    approval clears every remaining failure. Never deletes a valid approval.

    Returns (remaining_failures, handoff_or_None, notes).
    """
    notes = []
    if sdir is None or tree is None:
        return list(failures), None, notes
    clear_handoff(sdir)
    insp = inspect(sdir, tree)
    if insp["state"] in ("expired", "mismatch", "malformed", "premature"):
        retire_approval(sdir)
        notes.append(f"Previous approval retired: {insp['detail']}.")
        return list(failures), None, notes
    if insp["state"] != "valid":
        return list(failures), None, notes
    approval = insp["approval"]
    approved = set(approval["approved_rules"])
    covered_rules = {r for r, _ in failures
                     if r in approved and is_approvable(classify(r, lint_rules))}
    if not covered_rules:
        return list(failures), None, notes
    remaining = [(r, m) for r, m in failures if r not in covered_rules]
    if not remaining:
        return remaining, write_handoff(sdir, approval, covered_rules), notes
    notes.append(
        f"Approval {approval['approval_id']} ({approval['approved_by']}) "
        f"covers {', '.join(sorted(covered_rules))} for this exact staged "
        "change and is kept for the retry; resolve the remaining findings below.")
    return remaining, None, notes


def render_block_report(header, failures, warnings, lint_rules, notes, block,
                        info_lines=()):
    """Lines for a blocked attempt: tagged failures, warnings, notes, a
    fix-required vs approvable resolution summary, the Architect STOP box
    (only when something is approvable), and the block id pointer."""
    def res(rule):
        return classify(rule, lint_rules)

    out = ["", f"  {header}", ""]
    for rule, msg in failures:
        out.append(f"  ✗ {rule} [{res(rule)}]: {msg}")
    if warnings:
        out.append("")
        for rule, msg in warnings:
            out.append(f"  ⚠ {rule}: {msg}")
    out.append("")
    for note in notes:
        out.append(f"  • {note}")
    if notes:
        out.append("")
    out.extend(info_lines)

    needs_approval = sorted({r for r, _ in failures if is_approvable(res(r))})
    fix_required = sorted({r for r, _ in failures if not is_approvable(res(r))})
    out += ["", "  Resolution:"]
    if fix_required:
        out.append(f"    fix-required (fix and retry; cannot be approved): "
                   f"{', '.join(fix_required)}")
    if needs_approval:
        out.append(f"    approvable (fix, or the Architect may approve this exact "
                   f"staged change): {', '.join(needs_approval)}")
    if needs_approval:
        out += [
            "",
            "  ┌─────────────────────────────────────────────────────────┐",
            "  │ STOP. Do not override this yourself.                   │",
            "  │                                                        │",
            "  │ Present these findings to the Architect, who decides:  │",
            "  │   1. Fix the findings and retry the commit, or         │",
            "  │   2. Approve the approvable findings:                  │",
            "  │        gator hook approve                              │",
            "  │                                                        │",
            "  │ You may NOT run gator hook approve yourself.           │",
            "  │ Unauthorized self-approval is a governance violation.  │",
            "  └─────────────────────────────────────────────────────────┘",
        ]
        if fix_required:
            out.append("  The fix-required findings must be fixed either way.")
    if block is not None:
        out += ["", f"  Block ID: {block['block_id']}   "
                    "(details: gator hook override status)"]
    out.append("")
    return out


def describe(block, approval, tree, now=None):
    """Human-readable status lines shared by status/approve output."""
    now = _now() if now is None else now
    lines = []
    if block is None:
        lines.append("  No blocked commit attempt is recorded for this worktree.")
        return lines
    age = int(block_age_seconds(block, now))
    matches = block.get("index_tree") == tree
    lines.append(f"    Block ID:     {block['block_id']}")
    lines.append(f"    Blocked at:   {block.get('created_at')}  ({age}s ago)")
    lines.append(f"    Expires at:   {block.get('expires_at')}")
    lines.append(f"    Staged tree:  {'matches the current index' if matches else 'CHANGED since the block — retry the commit to refresh it'}")
    lines.append("    Failures:")
    for f in block.get("failures", []):
        lines.append(f"      - {f['rule']} ({f['resolution']})")
    files = block.get("files", [])
    if files:
        shown = ", ".join(files[:8])
        more = f" (+{len(files) - 8} more)" if len(files) > 8 else ""
        lines.append(f"    Files:        {shown}{more}")
    if approval:
        lines.append(f"    Approval:     {approval.get('approval_id')} by {approval.get('approved_by')} "
                     f"for {', '.join(approval.get('approved_rules', []))}")
    return lines
