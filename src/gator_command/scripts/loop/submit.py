"""
Submit handlers for gator loop.

Owns: submit-draft, submit-review, escalate, and unblock command logic.
Each handler resolves context, acquires the session lock, validates,
mutates state, copies artifacts, and emits events — all inside the lock.

These are the canonical writers of session.json and events.jsonl during
normal operation. The only other writer is the host's timeout enforcer.
"""

import shutil
import sys
from pathlib import Path

_LOOP_DIR = str(Path(__file__).resolve().parent)
if _LOOP_DIR not in sys.path:
    sys.path.insert(0, _LOOP_DIR)

from session import (
    attention_mode,
    resolve_token, with_session_lock, append_turn,
    find_gator_root, _make_writable, _make_readonly,
    validate_turn_timeout, validate_round_count, loop_mode,
)
from state_machine import (
    validate_action, validate_unblock,
    advance_draft_submitted, advance_review_submitted,
    advance_escalated, advance_unblocked, advance_extended,
    advance_reopened, advance_implementation_submitted,
    advance_implementation_reviewed,
    advance_paused_by_architect, advance_interjected,
    advance_ended_by_architect,
)


# ---------------------------------------------------------------------------
# Artifact copying
# ---------------------------------------------------------------------------

def _copy_artifact(source_path, loop_dir, target_name):
    """Copy a submission file into the loop directory.

    Sets read-only after copy on POSIX. Returns the target path.
    """
    source = Path(source_path)
    target = Path(loop_dir) / target_name
    _make_writable(target)
    shutil.copy2(str(source), str(target))
    _make_readonly(target)
    return target_name


# ---------------------------------------------------------------------------
# Coding-mode implementation artifact (#41)
# ---------------------------------------------------------------------------

IMPLEMENTATION_HEADINGS = (
    "Executive Summary",
    "Implementation Summary",
    "Charter Updates",
    "Verification",
    "Commit State",
)

_H2 = __import__("re").compile(r"^##[ \t]+(.+?)[ \t]*#*[ \t]*$")


def _h2_title(line):
    m = _H2.match(line.rstrip("\r\n"))
    if not m or line.startswith("###"):
        return None
    return m.group(1).strip()


def _h2_titles(text):
    """Lower-cased level-2 heading titles outside fenced code, in order."""
    titles = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        title = _h2_title(line)
        if title:
            titles.append(title.lower())
    return titles


def missing_implementation_headings(text):
    """Required ``## `` headings absent from an implementation artifact.

    Matching is case-insensitive on the exact heading text, level 2 only,
    and ignores headings inside fenced code blocks.
    """
    seen = set(_h2_titles(text))
    return [h for h in IMPLEMENTATION_HEADINGS if h.lower() not in seen]


CONTEXT_CHECKED_HEADING = "Context Checked"
_PLACEHOLDER_BODIES = frozenset({"", "none", "na", "nothing", "tbd", "todo"})


def _section_body(text, title):
    """Body lines of the first level-2 section named ``title`` (case-
    insensitive), up to the next unfenced level-2 heading or EOF."""
    lines = text.splitlines()
    in_fence = False
    body = None
    for line in lines:
        stripped = line.lstrip()
        is_fence = stripped.startswith("```") or stripped.startswith("~~~")
        if body is not None:
            if is_fence:
                in_fence = not in_fence
            elif not in_fence and _h2_title(line) is not None:
                break
            body.append(line)
            continue
        if is_fence:
            in_fence = not in_fence
            continue
        if not in_fence:
            h = _h2_title(line)
            if h is not None and h.lower() == title.lower():
                body = []
    return body


def context_checked_problems(text):
    """Structural problems with a plan's ``## Context Checked`` (#46).

    Exactly one level-2 heading outside fences; a non-empty body once HTML
    comments and blank lines are removed; and not merely a placeholder
    (none / n/a / nothing / tbd / '-'). "None — <reason>" is accepted:
    "None" needs a short reason. Adequacy is the Reviewer's judgment, never
    checked here. Returns a list of human-readable problems ([] = ok).
    """
    import re as _re
    count = _h2_titles(text).count(CONTEXT_CHECKED_HEADING.lower())
    if count == 0:
        return ["missing a '## Context Checked' section (list the charters, "
                "code/source artifacts, and Architect brief you consulted, or "
                "'None — <reason>')"]
    if count > 1:
        return ["more than one '## Context Checked' section; keep exactly one"]
    body = "\n".join(_section_body(text, CONTEXT_CHECKED_HEADING) or [])
    body = _re.sub(r"<!--.*?-->", "", body, flags=_re.S)
    meaningful = [l.strip() for l in body.splitlines() if l.strip()]
    if not meaningful:
        return ["'## Context Checked' is empty"]
    normalized = _re.sub(r"[^a-z0-9]+", "", " ".join(meaningful).lower())
    if normalized in _PLACEHOLDER_BODIES:
        return ["'## Context Checked' is only a placeholder; list what you "
                "checked, or write 'None — <reason>'"]
    return []


def commit_state_heading_count(text):
    """How many level-2 ``Commit State`` headings (outside fences) exist.

    The CLI owns exactly one Commit State section, so a valid artifact has
    exactly one; duplicates would leave an author-controlled competing
    state block next to the captured one.
    """
    return _h2_titles(text).count("commit state")


def _display_path(path):
    # Raw facts are persisted unchanged; this only keeps one path per line
    # in the rendered artifact (a newline in a filename is shown escaped).
    return path.replace("\r", "\\r").replace("\n", "\\n")


LOOP_RESIDUE_PREFIX = ".gator/loops/"


def split_residue(paths):
    """Display-only classification of RAW residue paths (never filtering).

    Loop residue (the loop's own audit files under ``.gator/loops/``) is
    always untracked and keeps changing while a loop runs, so it is shown
    separately as expected; everything else is "other" residue the
    Reviewer should notice. The persisted snapshot keeps the raw list.
    Returns (loop_paths, other_paths).
    """
    loop, other = [], []
    for p in paths:
        (loop if p.startswith(LOOP_RESIDUE_PREFIX) else other).append(p)
    return loop, other


def _change_counts(changed):
    counts = {}
    for c in changed or []:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    return counts


def coding_status_view(coding, loop_dir=None):
    """Slim, allowlisted projection of ``session["coding"]`` for the
    Dashboard status poll (#41). Never ships raw path lists (up to
    MAX_PATHS per generation) on every poll: identifiers, counts, review
    verdicts, and the approval binding only. The raw facts stay on disk.
    """
    if not isinstance(coding, dict):
        return None
    gens = []
    for g in coding.get("generations") or []:
        snap = g.get("snapshot") or {}
        loop_res, other_res = split_residue(snap.get("unstaged_paths") or [])
        review = g.get("review") or None
        gens.append({
            "round": g.get("round"),
            "submitted_at": g.get("submitted_at"),
            "artifact_path": g.get("artifact_path"),
            "staged_tree": snap.get("staged_tree"),
            "current_head": snap.get("current_head"),
            "branch": snap.get("branch"),
            "detached": snap.get("detached"),
            "changed_count": (len(snap.get("changed_paths") or [])
                              + (snap.get("changed_truncated") or 0)),
            "changed_by_status": _change_counts(snap.get("changed_paths")),
            "residue_other_count": (len(other_res)
                                    + (snap.get("unstaged_truncated") or 0)),
            "residue_loop_count": len(loop_res),
            "review": ({
                "verdict": review.get("verdict"),
                "reviewed_tree": review.get("reviewed_tree"),
                "reviewed_head": review.get("reviewed_head"),
                "candidate_changed": review.get("candidate_changed"),
                "reviewed_at": review.get("reviewed_at"),
            } if isinstance(review, dict) else None),
        })
    approval = coding.get("approval")
    # #43: strict, positionally bound source-brief metadata + integrity.
    from session import (brief_status_view, verify_brief,
                         SOURCE_BRIEF_FILENAME, SOURCE_BRIEF_DECISIONS)
    src_ref = coding.get("source_brief")
    decision = coding.get("source_brief_decision")
    if decision not in SOURCE_BRIEF_DECISIONS:
        decision = None
    return {
        "source_brief": brief_status_view(src_ref, SOURCE_BRIEF_FILENAME),
        "source_brief_check": (
            verify_brief(loop_dir, src_ref, SOURCE_BRIEF_FILENAME)
            if loop_dir is not None else
            ("absent" if src_ref is None else "unknown")),
        "source_brief_decision": decision,
        "source_loop_id": coding.get("source_loop_id"),
        "plan_sha256": coding.get("plan_sha256"),
        "base_head": coding.get("base_head"),
        "base_tree": coding.get("base_tree"),
        "generations": gens,
        "approval": ({k: approval.get(k) for k in
                      ("tree", "head", "round", "ts", "invalidated_at")}
                     if isinstance(approval, dict) else None),
    }


def render_commit_state(snap):
    """CLI-owned ``## Commit State`` section built from the raw snapshot.

    The facts here are authoritative; the author's text in this section is
    always replaced. Path lists are shown inside ``text`` fences so no
    filename can inject Markdown.
    """
    changed = snap.get("changed_paths") or []
    unstaged = snap.get("unstaged_paths") or []
    loop_residue, other_residue = split_residue(unstaged)
    counts = {}
    for c in changed:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    summary = ", ".join(f"{k} {counts[k]}" for k in sorted(counts)) or "none"
    head_ref = ("detached HEAD" if snap.get("detached")
                else (snap.get("branch") or "").replace("refs/heads/", ""))
    lines = [
        "## Commit State",
        "",
        "<!-- Captured by the gator loop CLI at submission. Authoritative:",
        "     author text in this section is replaced. The reviewed candidate",
        "     is the staged tree below, not this artifact's prose. -->",
        "",
        "| Fact | Value |",
        "|---|---|",
        f"| Base HEAD | `{snap.get('base_head')}` |",
        f"| Base tree | `{snap.get('base_tree')}` |",
        f"| Current HEAD | `{snap.get('current_head')}` ({head_ref}) |",
        f"| Staged tree (candidate) | `{snap.get('staged_tree')}` |",
        f"| Changed paths vs base | {len(changed) + snap.get('changed_truncated', 0)} ({summary}) |",
        f"| Unstaged / untracked residue | {len(other_residue)} other + {len(loop_residue)} loop residue under `.gator/loops/`"
        + (f" + {snap['unstaged_truncated']} truncated" if snap.get("unstaged_truncated") else "")
        + " (none of it is part of the candidate) |",
        "",
        "Review exactly this candidate with:",
        "",
        "```text",
        f"git diff {snap.get('base_tree')} {snap.get('staged_tree')}",
        "```",
        "",
        "Changed paths (status, path):",
        "",
        "```text",
    ]
    for c in changed:
        if "old_path" in c:
            lines.append(f"{c['status']} {_display_path(c['old_path'])} -> "
                         f"{_display_path(c['path'])}")
        else:
            lines.append(f"{c['status']} {_display_path(c['path'])}")
    if not changed:
        lines.append("(none)")
    if snap.get("changed_truncated"):
        lines.append(f"... {snap['changed_truncated']} more (truncated)")
    lines += ["```", ""]
    if other_residue or snap.get("unstaged_truncated"):
        lines += ["Unstaged / untracked residue (disclosed; NOT part of the "
                  "candidate):", "", "```text"]
        lines += [_display_path(u) for u in other_residue]
        if snap.get("unstaged_truncated"):
            lines.append(f"... {snap['unstaged_truncated']} more (truncated)")
        lines += ["```", ""]
    else:
        lines += ["Unstaged / untracked residue outside the loop directory: "
                  "none.", ""]
    if loop_residue:
        lines += [f"Loop residue: {len(loop_residue)} path(s) under "
                  "`.gator/loops/` (this loop's own audit files; expected, "
                  "not part of the candidate).", ""]
    return "\n".join(lines)


def replace_commit_state(text, block):
    """Replace the ``## Commit State`` section (to the next level-2 heading
    outside a fence, or EOF) with ``block``. Exactly one such heading must
    exist; duplicates are refused so no competing state block survives."""
    if commit_state_heading_count(text) > 1:
        raise ValueError(
            "Implementation artifact has more than one '## Commit State' "
            "section; keep exactly one (the CLI replaces its contents)")
    lines = text.splitlines()
    out = []
    i = 0
    in_fence = False
    replaced = False
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
        title = None if in_fence else _h2_title(line)
        if (not replaced and title is not None
                and title.lower() == "commit state"):
            out.extend(block.rstrip("\n").split("\n"))
            i += 1
            sec_fence = False
            while i < len(lines):
                s = lines[i].lstrip()
                if s.startswith("```") or s.startswith("~~~"):
                    sec_fence = not sec_fence
                elif not sec_fence and _h2_title(lines[i]) is not None:
                    break
                i += 1
            out.append("")
            replaced = True
            continue
        out.append(line)
        i += 1
    if not replaced:
        raise ValueError("Implementation artifact has no '## Commit State' section")
    return "\n".join(out).rstrip("\n") + "\n"


def _write_artifact_text(loop_dir, target_name, text):
    target = Path(loop_dir) / target_name
    _make_writable(target)
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    _make_readonly(target)
    return target_name


# ---------------------------------------------------------------------------
# Submit handlers
# ---------------------------------------------------------------------------

def _context_evidence_required(session):
    """#46 migration boundary: only sessions created with the contract flag
    (planning loops created after the release) are validated."""
    contract = session.get("contract") if isinstance(session, dict) else None
    if not isinstance(contract, dict):
        return False
    level = contract.get("context_evidence")
    return isinstance(level, int) and not isinstance(level, bool) and level >= 1


def _check_context_evidence(data):
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("Plan draft must be UTF-8 text")
    problems = context_checked_problems(text)
    if problems:
        raise ValueError("Plan draft rejected: " + "; ".join(problems))


def _write_artifact_bytes(loop_dir, target_name, data):
    target = Path(loop_dir) / target_name
    _make_writable(target)
    with open(target, "wb") as f:
        f.write(data)
    _make_readonly(target)
    return target_name


def handle_submit_draft(token, file_path):
    """Process a draftor plan submission.

    Resolves token, validates role and turn, copies plan to
    plan.current.md, advances state to plan_review.
    """
    # Fail fast: check source file before acquiring lock
    source = Path(file_path)
    if not source.exists():
        raise FileNotFoundError(f"Draft file not found: {file_path}")
    if source.stat().st_size == 0:
        raise ValueError(f"Draft file is empty: {file_path}")

    loop_id, role, loop_dir = resolve_token(token)

    # #46: read the draft ONCE. For new-contract sessions the exact
    # captured bytes are validated inside the lock and persisted — no
    # second read and no path copy — so a file swapped after validation can
    # never be persisted unchecked. A preflight check gives a friendly early
    # error; the in-lock check is authoritative.
    captured = source.read_bytes()
    try:
        from session import load_session as _peek
        preflight_session = _peek(loop_dir)
    except Exception:
        preflight_session = None  # the locked transaction reports problems
    if _context_evidence_required(preflight_session):
        _check_context_evidence(captured)

    def _submit(session):
        # Validate inside lock (session may have changed)
        allowed, reason = validate_action(session, role, "submit_draft")
        if not allowed:
            raise PermissionError(reason)

        # Copy artifact — round-versioned first, then current
        round_num = session["status"]["round"]
        versioned_name = f"plan.round-{round_num}.md"
        if _context_evidence_required(session):
            _check_context_evidence(captured)
            _write_artifact_bytes(loop_dir, versioned_name, captured)
            _write_artifact_bytes(loop_dir, "plan.current.md", captured)
        else:
            # Legacy (pre-#46) sessions: unchanged behavior.
            _copy_artifact(source, loop_dir, versioned_name)
            _copy_artifact(source, loop_dir, "plan.current.md")

        # Mark role as joined
        session["roles"]["draftor"]["joined"] = True

        # Track turn — artifact_path points to versioned file (audit trail)
        turn = append_turn(
            session, role, "plan_draft",
            "Plan draft submitted", versioned_name
        )

        # Current reference points to *.current.md (model consumption)
        session["current"]["draft"] = {
            "turn_id": turn["turn_id"],
            "summary": turn["summary"],
            "artifact_path": "plan.current.md",
        }

        # Advance state
        timeout = session["status"]["turn_timeout_seconds"]
        advance_draft_submitted(session, timeout)

        # Determine round for event
        round_num = session["status"]["round"]
        # After draft submission we're still in the same round
        # (round increments on review with findings)
        event = {
            "event": "draft_submitted",
            "role": role,
            "round": round_num,
            "artifact_path": versioned_name,
            "detail": f"Plan draft submitted, advancing to plan_review",
        }
        return session, event

    with_session_lock(loop_dir, _submit)

    return loop_id, role, loop_dir


def handle_submit_review(token, file_path, approve=False, loop_dir=None):
    """Process a reviewer submission (findings or approval).

    Resolves token, validates role and turn, copies findings to
    findings.current.md, advances state based on --approve flag.

    Coding loops (#41) take the tree-bound path in ``_coding_review()``
    under the same lock: the review is recorded against the submitted
    candidate generation, and APPROVE additionally requires the live staged
    tree and HEAD to still equal that candidate.
    """
    source = Path(file_path)
    if not source.exists():
        raise FileNotFoundError(f"Review file not found: {file_path}")
    if source.stat().st_size == 0:
        raise ValueError(f"Review file is empty: {file_path}")

    # Pre-read for ESCALATE verdict detection (safe, before lock)
    import re
    _has_escalate_verdict = False
    if not approve:
        try:
            head = source.read_bytes()[:500].decode("utf-8", errors="replace")
            _has_escalate_verdict = bool(
                re.search(r"##\s*Verdict[^\n]*\n\s*ESCALATE", head, re.IGNORECASE))
        except OSError:
            pass

    loop_id, role, loop_dir = resolve_token(token, loop_dir=loop_dir)

    def _submit(session):
        allowed, reason = validate_action(session, role, "submit_review")
        if not allowed:
            raise PermissionError(reason)

        if loop_mode(session) == "coding":
            return _coding_review(session, role, loop_dir, source, approve)

        # Copy artifact — round-versioned first, then current
        # Capture round BEFORE advance (advance increments on findings)
        round_num = session["status"]["round"]
        versioned_name = f"findings.round-{round_num}.md"
        _copy_artifact(source, loop_dir, versioned_name)
        _copy_artifact(source, loop_dir, "findings.current.md")

        # Mark role as joined
        session["roles"]["reviewer"]["joined"] = True

        # Track turn — artifact_path points to versioned file (audit trail)
        summary = "Plan approved" if approve else "Review findings submitted"
        turn = append_turn(
            session, role, "plan_review",
            summary, versioned_name
        )

        # Current reference points to *.current.md (model consumption)
        session["current"]["findings"] = {
            "turn_id": turn["turn_id"],
            "summary": turn["summary"],
            "artifact_path": "findings.current.md",
        }

        # Advance state
        timeout = session["status"]["turn_timeout_seconds"]
        # findings_count is not parsed from file — explicit via --approve flag
        findings_count = 0 if approve else 1
        advance_review_submitted(session, approve, findings_count, timeout)

        # Build event
        if approve:
            event = {
                "event": "plan_approved",
                "role": role,
                "round": session["status"]["round"],
                "artifact_path": versioned_name,
                "detail": "Reviewer approved the plan",
            }
        elif session["status"]["stage"] == "max_rounds_exceeded":
            event = {
                "event": "max_rounds_exceeded",
                "role": role,
                "round": session["status"]["round"],
                "artifact_path": versioned_name,
                "detail": f"Round limit reached ({session['status']['max_rounds']})",
            }
        else:
            event = {
                "event": "revision_requested",
                "role": role,
                "round": session["status"]["round"],
                "artifact_path": versioned_name,
                "detail": "Findings submitted, revision requested",
            }
        return session, event

    with_session_lock(loop_dir, _submit)

    if _has_escalate_verdict:
        print(
            "Warning: findings contain an ESCALATE verdict but were "
            "submitted via submit-review, not escalate. The loop entered "
            "revision, not blocked state. If you intended to escalate, "
            "run `gator loop escalate` instead.",
            file=sys.stderr,
        )

    return loop_id, role, loop_dir


REVIEWED_CANDIDATE_HEADING = "Reviewed Candidate"


def render_reviewed_candidate(review):
    """CLI-owned ``## Reviewed Candidate`` section appended to a coding
    review artifact: which exact tree the verdict is about."""
    verdict = "APPROVE" if review["verdict"] == "approve" else "REVISE"
    lines = [
        "## Reviewed Candidate",
        "",
        "<!-- Captured by the gator loop CLI at review submission. -->",
        "",
        "| Fact | Value |",
        "|---|---|",
        f"| Verdict | {verdict} |",
        f"| Reviewed staged tree | `{review['reviewed_tree']}` |",
        f"| Reviewed HEAD | `{review['reviewed_head']}` |",
        f"| Candidate round | {review['round']} |",
        f"| Live candidate unchanged at review | "
        f"{'no — the index or HEAD moved after submission' if review['candidate_changed'] else 'yes'} |",
        "",
    ]
    return "\n".join(lines)


def _coding_review(session, role, loop_dir, source, approve):
    """Coding review transaction (#41); runs inside the session lock.

    - The review binds to the LATEST generation's submitted candidate
      (``reviewed_tree`` / ``reviewed_head``). Reviewers inspect it with
      ``git diff <base_tree> <staged_tree>``, which is immutable, so
      findings remain valid even if the live index later moves.
    - A fresh snapshot is taken. APPROVE is rejected unless the live staged
      tree AND HEAD still equal the submitted candidate (the approval
      authorizes exactly that tree for the one normal commit). Findings are
      always accepted and flagged ``candidate_changed`` when it moved.
    - The artifact must be UTF-8 and must not author its own
      ``## Reviewed Candidate`` section; the CLI appends that section.
    """
    import gitsnap
    from datetime import datetime, timezone

    try:
        text = source.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise ValueError("Review file must be UTF-8 text")
    if REVIEWED_CANDIDATE_HEADING.lower() in _h2_titles(text):
        raise ValueError(
            "Review artifact must not include a '## Reviewed Candidate' "
            "section; the CLI appends it")

    coding = session["coding"]
    gens = coding.get("generations") or []
    if not gens:
        raise ValueError("No implementation candidate has been submitted")
    gen = gens[-1]
    submitted = gen["snapshot"]

    repo_root = Path(loop_dir).parent.parent.parent
    snap = gitsnap.snapshot(repo_root, coding["base_head"])
    live_ok = bool(snap.get("ok"))
    changed = (not live_ok
               or snap["staged_tree"] != submitted["staged_tree"]
               or snap["current_head"] != submitted["current_head"])
    if approve and changed:
        if not live_ok:
            raise ValueError(
                "Cannot verify the live candidate before approval: "
                f"{snap.get('error')} ({snap.get('detail', '')})")
        raise ValueError(
            "The candidate changed since submission (staged tree or HEAD "
            "differs); approval is blocked. Submit findings so the Draftor "
            "resubmits the current tree.")

    round_num = session["status"]["round"]
    now = datetime.now(tz=timezone.utc).isoformat()
    versioned_name = f"findings.round-{round_num}.md"
    review = {
        "verdict": "approve" if approve else "revise",
        "round": gen["round"],
        "reviewed_tree": submitted["staged_tree"],
        "reviewed_head": submitted["current_head"],
        "candidate_changed": changed,
        "live_snapshot_ok": live_ok,
        "artifact_path": versioned_name,
        "reviewed_at": now,
    }
    rendered = (text.rstrip("\n") + "\n\n" + render_reviewed_candidate(review)
                ).rstrip("\n") + "\n"
    _write_artifact_text(loop_dir, versioned_name, rendered)
    _write_artifact_text(loop_dir, "findings.current.md", rendered)
    gen["review"] = review

    session["roles"]["reviewer"]["joined"] = True
    summary = ("Implementation approved" if approve
               else "Implementation review findings submitted")
    turn = append_turn(session, role, "implementation_review", summary,
                       versioned_name)
    session["current"]["findings"] = {
        "turn_id": turn["turn_id"],
        "summary": turn["summary"],
        "artifact_path": "findings.current.md",
    }

    timeout = session["status"]["turn_timeout_seconds"]
    approval = None
    if approve:
        approval = {"tree": review["reviewed_tree"],
                    "head": review["reviewed_head"],
                    "round": gen["round"], "ts": now}
    advance_implementation_reviewed(session, approve, timeout,
                                    approval=approval)

    status = session["status"]
    base_event = {"role": role, "round": status["round"],
                  "artifact_path": versioned_name,
                  "reviewed_tree": review["reviewed_tree"],
                  "candidate_changed": changed}
    if approve:
        event = dict(base_event, event="implementation_approved",
                     detail=(f"Reviewer approved staged tree "
                             f"{review['reviewed_tree'][:12]} -- return to "
                             "the Draftor session for one normal commit"))
    elif status["stage"] == "max_rounds_exceeded":
        event = dict(base_event, event="max_rounds_exceeded",
                     detail=f"Round limit reached ({status['max_rounds']})")
    else:
        event = dict(base_event, event="revision_requested",
                     detail=("Findings on staged tree "
                             f"{review['reviewed_tree'][:12]}, revision requested"
                             + (" (candidate changed since submission)"
                                if changed else "")))
    return session, event


def handle_escalate(token, reason, file_path=None):
    """Escalate to blocked_on_architect from any active state.

    Either model role may escalate from any active stage, including when
    it is not its turn. Optional file_path attaches a structured
    decision-request artifact.
    """
    if not reason or not reason.strip():
        raise ValueError("Escalation reason is required")

    artifact_name = None
    if file_path is not None:
        source = Path(file_path)
        if not source.exists():
            raise FileNotFoundError(f"Decision-request file not found: {file_path}")
        if source.stat().st_size == 0:
            raise ValueError(f"Decision-request file is empty: {file_path}")

    loop_id, role, loop_dir = resolve_token(token)

    def _escalate(session):
        nonlocal artifact_name
        allowed, msg = validate_action(session, role, "escalate")
        if not allowed:
            raise PermissionError(msg)

        round_num = session["status"]["round"]

        decision_seq = len(session.get("decisions", [])) + 1
        if file_path is not None:
            artifact_name = f"decision-request.decision-{decision_seq}.round-{round_num}.md"
            _copy_artifact(file_path, loop_dir, artifact_name)

        # Track turn
        append_turn(
            session, role, "escalation",
            f"Escalated: {reason}"
        )

        # Advance state
        advance_escalated(session, reason)

        # Record structured decision request
        from datetime import datetime, timezone
        decision_id = f"decision-{decision_seq}"
        decision_entry = {
            "id": decision_id,
            "request": {
                "reason": reason,
                "artifact_path": artifact_name,
                "round": round_num,
                "role": role,
                "ts": datetime.now(tz=timezone.utc).isoformat(),
            },
            "response": None,
        }
        if "decisions" not in session:
            session["decisions"] = []
        session["decisions"].append(decision_entry)

        event = {
            "event": "escalated",
            "role": role,
            "round": session["status"]["round"],
            "detail": reason,
        }
        if artifact_name:
            event["decision_request"] = artifact_name
        return session, event

    with_session_lock(loop_dir, _escalate)

    return loop_id, role, loop_dir


ARTIFACT_ONLY_RESPONSE_SUMMARY = "See decision-response artifact."
DELIBERATE_EMPTY_RESPONSE_SUMMARY = (
    "Architect resolved the escalation deliberately without a written response.")


ATTENTION_TIMEOUT_REFUSAL = (
    "This loop uses an Architect attention interval (set at start); there is "
    "no participant time window to change. Unblock without --timeout.")


def handle_unblock(token, next_role=None, stage=None, message=None,
                   file_path=None, loop_dir=None, turn_timeout=None,
                   no_response=False):
    """Architect command: unblock a paused loop.

    Requires architect token. Both next_role and stage are optional;
    defaults come from the resume state saved at escalation/pause time.
    Optional message is stored in session and shown in the resuming
    model's status output. Optional file_path attaches a durable
    decision-response artifact.

    Response contract: when the unblock resolves a pending decision
    (an escalation), a non-empty message, a response file, or the
    explicit no_response opt-in is required — a blank unblock is
    rejected before any state change. An ordinary Architect pause has
    no pending decision and may be unblocked with no response.

    Optional turn_timeout (validated 30..3600 s) replaces the loop's
    stored window before the new deadline is computed; omitted keeps
    the current window.
    """
    if message is not None and not message.strip():
        message = None
    if no_response and (message is not None or file_path is not None):
        raise ValueError(
            "no-response is mutually exclusive with a message or response file")
    if turn_timeout is not None:
        turn_timeout = validate_turn_timeout(turn_timeout)

    if file_path is not None:
        source = Path(file_path)
        if not source.exists():
            raise FileNotFoundError(
                f"Decision-response file not found: {file_path}")
        if source.stat().st_size == 0:
            raise ValueError(
                f"Decision-response file is empty: {file_path}")

    loop_id, role, loop_dir = resolve_token(token, loop_dir=loop_dir)
    if role != "architect":
        raise PermissionError("Unblock requires the architect token")

    def _unblock(session):
        allowed, reason = validate_unblock(session)
        if not allowed:
            raise PermissionError(reason)

        # Check pending decisions before advancing state
        from datetime import datetime, timezone
        decisions = session.get("decisions", [])
        pending = [d for d in decisions if d.get("response") is None]

        if file_path is not None and not pending:
            raise ValueError(
                "--file requires a pending decision request to attach to; "
                "no outstanding decisions exist")
        if no_response and not pending:
            raise ValueError(
                "no-response applies only when resolving a pending decision; "
                "no outstanding decisions exist")
        if pending and message is None and file_path is None and not no_response:
            raise ValueError(
                f"Unblocking resolves pending decision {pending[-1]['id']}; "
                "a response is required: provide a message, a response file, "
                "or explicitly choose no response")

        # Response classification (only meaningful when resolving a decision)
        if no_response:
            response_kind = "deliberate_empty"
            status_message = DELIBERATE_EMPTY_RESPONSE_SUMMARY
        elif message is not None and file_path is not None:
            response_kind = "message_and_artifact"
            status_message = message
        elif file_path is not None:
            response_kind = "artifact"
            status_message = ARTIFACT_ONLY_RESPONSE_SUMMARY
        else:
            response_kind = "message" if message is not None else None
            status_message = message

        if turn_timeout is not None and attention_mode(session):
            # #47: no participant time window exists to change. Raised before
            # any mutation, inside the lock (authoritative, race-free).
            raise ValueError(ATTENTION_TIMEOUT_REFUSAL)
        previous_timeout = session["status"]["turn_timeout_seconds"]
        if turn_timeout is not None:
            session["status"]["turn_timeout_seconds"] = turn_timeout
        timeout = session["status"]["turn_timeout_seconds"]
        advance_unblocked(session, stage=stage, next_role=next_role,
                          turn_timeout=timeout, message=status_message)

        # Resolve the most recent pending decision, if any
        resolved_id = None
        artifact_name = None
        if pending:
            decision = pending[-1]
            resolved_id = decision["id"]
            if file_path is not None:
                artifact_name = f"decision-response.{resolved_id}.md"
                _copy_artifact(file_path, loop_dir, artifact_name)
            decision["response"] = {
                "message": message,
                "artifact_path": artifact_name,
                "kind": response_kind,
                "ts": datetime.now(tz=timezone.utc).isoformat(),
            }

        # Surface response artifact in model-facing status (cleared on next submit)
        # Store relative name only — cli resolves against loop_dir at render time
        session["status"]["architect_response_artifact"] = artifact_name

        # Record architect turn
        append_turn(session, "architect", "unblock",
                    status_message or "Loop unblocked")

        detail = (f"Resumed to {session['status']['stage']} "
                  f"(next: {session['status']['next_role']})")
        if status_message:
            detail += f" -- Architect: {status_message}"
        if timeout != previous_timeout:
            detail += f" -- turn window {previous_timeout}s -> {timeout}s"
        event = {
            "event": "loop_unblocked",
            "role": "architect",
            "round": session["status"]["round"],
            "detail": detail,
            "turn_timeout_seconds": timeout,
        }
        if timeout != previous_timeout:
            event["previous_turn_timeout_seconds"] = previous_timeout
        if resolved_id:
            event["decision_id"] = resolved_id
            event["response_kind"] = response_kind
        return session, event

    with_session_lock(loop_dir, _unblock)

    return loop_id, loop_dir


def handle_extend(token, rounds, message, loop_dir=None):
    """Architect command: continue a loop that ended at its round limit (#39).

    Raises the round ceiling by ``rounds`` (validated 1..20) and resumes the
    loop at plan_revision for the Draftor, with a fresh deadline from the
    loop's stored turn window. ``message`` is required: it is the durable
    reason for continuing and is shown to the resumed Draftor.

    All input and identity validation runs before the session lock; stage
    validation runs inside it before any mutation, so a rejected extension
    leaves session.json and events.jsonl untouched.

    This handler is the session transaction only. The single-active-loop
    guard (start.lock + scan) and watcher attachment are the caller's
    responsibility — see host.extend_loop().

    Returns (loop_id, loop_dir, previous_max_rounds, new_max_rounds).
    """
    if message is None or not str(message).strip():
        raise ValueError("A reason (--message) is required to extend a loop")
    message = str(message).strip()
    rounds = validate_round_count(rounds)

    loop_id, role, loop_dir = resolve_token(token, loop_dir=loop_dir)
    if role != "architect":
        raise PermissionError("Extend requires the architect token")

    result = {}

    def _extend(session):
        allowed, reason = validate_action(session, "architect", "extend")
        if not allowed:
            raise PermissionError(reason)

        timeout = session["status"]["turn_timeout_seconds"]
        previous, new = advance_extended(
            session, rounds, turn_timeout=timeout, message=message)
        result["previous"], result["new"] = previous, new

        append_turn(session, "architect", "extend", message)

        status = session["status"]
        event = {
            "event": "loop_extended",
            "role": "architect",
            "round": status["round"],
            "rounds_added": rounds,
            "previous_max_rounds": previous,
            "max_rounds": new,
            "stage": status["stage"],
            "next_role": status["next_role"],
            "reason": message,
            "detail": (f"Extended by {rounds} round(s): {previous} -> {new}"
                       f" -- Architect: {message}"),
        }
        return session, event

    with_session_lock(loop_dir, _extend)

    return loop_id, loop_dir, result["previous"], result["new"]


def handle_submit_implementation(token, file_path, loop_dir=None):
    """Coding (#41): Draftor submits the staged candidate for review.

    Before the lock: the artifact must exist, be UTF-8, non-empty, and carry
    the required headings (Executive Summary, Implementation Summary,
    Charter Updates, Verification, Commit State).

    Under the session lock: role/stage/turn validation, then a raw Git
    snapshot against the loop's captured ``base_head``. It must be ok and
    must stage something (``staged_tree != base_tree``). Unstaged residue
    is disclosed, never blocking. The CLI replaces the artifact's Commit
    State section with the captured facts, writes
    ``implementation.round-N.md`` + ``implementation.current.md``, appends
    the generation ``{round, submitted_at, artifact_path, snapshot}`` (the
    raw snapshot, unfiltered), and advances to implementation_review.

    Returns (loop_id, role, loop_dir, generation).
    """
    import gitsnap
    from datetime import datetime, timezone

    source = Path(file_path)
    if not source.is_file():
        raise FileNotFoundError(f"Implementation file not found: {file_path}")
    try:
        text = source.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise ValueError("Implementation file must be UTF-8 text")
    if not text.strip():
        raise ValueError(f"Implementation file is empty: {file_path}")
    missing = missing_implementation_headings(text)
    if missing:
        raise ValueError(
            "Implementation artifact is missing required section(s): "
            + ", ".join(f"## {h}" for h in missing))
    if commit_state_heading_count(text) != 1:
        raise ValueError(
            "Implementation artifact has more than one '## Commit State' "
            "section; keep exactly one (the CLI replaces its contents)")

    loop_id, role, loop_dir = resolve_token(token, loop_dir=loop_dir)
    repo_root = Path(loop_dir).parent.parent.parent
    result = {}

    def _submit(session):
        allowed, reason = validate_action(session, role, "submit_implementation")
        if not allowed:
            raise PermissionError(reason)

        coding = session["coding"]
        snap = gitsnap.snapshot(repo_root, coding["base_head"])
        if not snap.get("ok"):
            raise ValueError(
                "Cannot capture the staged candidate: "
                f"{snap.get('error')} ({snap.get('detail', '')})")
        if snap["staged_tree"] == snap["base_tree"]:
            raise ValueError(
                "Nothing is staged relative to the loop's base commit; "
                "stage the intended change (git add) before submitting")

        rendered = replace_commit_state(text, render_commit_state(snap))
        round_num = session["status"]["round"]
        versioned_name = f"implementation.round-{round_num}.md"
        _write_artifact_text(loop_dir, versioned_name, rendered)
        _write_artifact_text(loop_dir, "implementation.current.md", rendered)

        session["roles"]["draftor"]["joined"] = True
        turn = append_turn(session, role, "implementation",
                           "Implementation submitted", versioned_name)
        session["current"]["implementation"] = {
            "turn_id": turn["turn_id"],
            "summary": turn["summary"],
            "artifact_path": "implementation.current.md",
        }

        generation = {
            "round": round_num,
            "submitted_at": datetime.now(tz=timezone.utc).isoformat(),
            "artifact_path": versioned_name,
            "snapshot": snap,
        }
        coding.setdefault("generations", []).append(generation)
        result["generation"] = generation

        advance_implementation_submitted(
            session, session["status"]["turn_timeout_seconds"])

        n_changed = len(snap["changed_paths"]) + snap.get("changed_truncated", 0)
        n_unstaged = (len(snap["unstaged_paths"])
                      + snap.get("unstaged_truncated", 0))
        loop_res, other_res = split_residue(snap["unstaged_paths"])
        event = {
            "event": "implementation_submitted",
            "role": role,
            "round": round_num,
            "artifact_path": versioned_name,
            "staged_tree": snap["staged_tree"],
            "current_head": snap["current_head"],
            "changed_count": n_changed,
            "unstaged_count": n_unstaged,
            "residue_other_count": (len(other_res)
                                    + snap.get("unstaged_truncated", 0)),
            "residue_loop_count": len(loop_res),
            "detail": (f"Implementation submitted: staged tree "
                       f"{snap['staged_tree'][:12]}, {n_changed} changed "
                       f"path(s), {len(other_res)} other unstaged/untracked"),
        }
        return session, event

    with_session_lock(loop_dir, _submit)
    return loop_id, role, loop_dir, result["generation"]


def handle_reopen(token, message, loop_dir=None):
    """Architect command: reopen an approved coding loop for revision (#41).

    implementation_approved -> implementation_revision for the Draftor with
    a fresh deadline from the loop's stored turn window; the round counter
    is kept and the prior approval is marked invalidated. ``message`` is
    required: the durable reason, shown to the resumed Draftor.

    Input/identity validation runs before the session lock; stage/mode
    validation runs inside it before any mutation, so a rejected reopen
    leaves session.json and events.jsonl untouched.

    Session transaction only — the single-active guard (start.lock + scan)
    and watcher attachment belong to host.reopen_loop() and its callers.
    Returns (loop_id, loop_dir).
    """
    if message is None or not str(message).strip():
        raise ValueError("A reason (--message) is required to reopen a loop")
    message = str(message).strip()

    loop_id, role, loop_dir = resolve_token(token, loop_dir=loop_dir)
    if role != "architect":
        raise PermissionError("Reopen requires the architect token")

    def _reopen(session):
        allowed, reason = validate_action(session, "architect", "reopen")
        if not allowed:
            raise PermissionError(reason)

        timeout = session["status"]["turn_timeout_seconds"]
        advance_reopened(session, turn_timeout=timeout, message=message)
        append_turn(session, "architect", "reopen", message)

        status = session["status"]
        event = {
            "event": "loop_reopened",
            "role": "architect",
            "round": status["round"],
            "stage": status["stage"],
            "next_role": status["next_role"],
            "reason": message,
            "detail": f"Reopened for revision -- Architect: {message}",
        }
        return session, event

    with_session_lock(loop_dir, _reopen)
    return loop_id, loop_dir


def handle_pause(token, message=None, loop_dir=None):
    """Architect command: pause a running loop.

    Requires architect token. Transitions to paused_by_architect.
    """
    loop_id, role, loop_dir = resolve_token(token, loop_dir=loop_dir)
    if role != "architect":
        raise PermissionError("Pause requires the architect token")

    def _pause(session):
        allowed, reason = validate_action(session, role, "pause")
        if not allowed:
            raise PermissionError(reason)

        advance_paused_by_architect(session, message=message)

        append_turn(session, "architect", "pause",
                    message or "Loop paused by Architect")

        detail = "Loop paused by Architect"
        if message:
            detail += f" -- {message}"
        event = {
            "event": "loop_paused",
            "role": "architect",
            "round": session["status"]["round"],
            "detail": detail,
        }
        return session, event

    with_session_lock(loop_dir, _pause)

    return loop_id, loop_dir


def handle_interject(token, message, loop_dir=None):
    """Architect command: inject guidance without pausing.

    Requires architect token. Stores message in session, emits event,
    but does not change stage or deadline.
    """
    if not message or not message.strip():
        raise ValueError("Interjection message is required")

    loop_id, role, loop_dir = resolve_token(token, loop_dir=loop_dir)
    if role != "architect":
        raise PermissionError("Interject requires the architect token")

    def _interject(session):
        allowed, reason = validate_action(session, role, "interject")
        if not allowed:
            raise PermissionError(reason)

        advance_interjected(session, message)

        append_turn(session, "architect", "interjection", message)

        event = {
            "event": "architect_interjection",
            "role": "architect",
            "round": session["status"]["round"],
            "detail": message,
        }
        return session, event

    with_session_lock(loop_dir, _interject)

    return loop_id, loop_dir


def handle_end(token, reason=None, loop_dir=None):
    """Architect command: terminate the loop prematurely.

    Requires architect token. Transitions to ended_by_architect.
    """
    loop_id, role, loop_dir = resolve_token(token, loop_dir=loop_dir)
    if role != "architect":
        raise PermissionError("End requires the architect token")

    def _end(session):
        allowed, msg = validate_action(session, role, "end")
        if not allowed:
            raise PermissionError(msg)

        advance_ended_by_architect(session, reason=reason)

        append_turn(session, "architect", "end",
                    reason or "Loop ended by Architect")

        detail = "Loop ended by Architect"
        if reason:
            detail += f" -- {reason}"
        event = {
            "event": "loop_ended_by_architect",
            "role": "architect",
            "round": session["status"]["round"],
            "detail": detail,
        }
        return session, event

    with_session_lock(loop_dir, _end)

    return loop_id, loop_dir
