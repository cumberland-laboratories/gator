"""
CLI dispatcher for gator loop.

Owns: argparse subcommand routing for all loop commands. Each subcommand
delegates to the appropriate handler in host.py, submit.py, or session.py.

Subcommands:
  start         Initialize a loop and enter the watch loop
  status        Show role-scoped actionable state (read-only)
  submit-draft  Submit a plan draft (draftor)
  submit-review Submit review findings or approve (reviewer)
  escalate      Escalate to Architect from any active state
  unblock       Architect: resume a blocked loop
  extend        Architect: continue a loop that ended at its round limit
  tail          Follow events in real time
  list          List all loop sessions
"""

import argparse
import json
import sys
from pathlib import Path

_LOOP_DIR = str(Path(__file__).resolve().parent)
if _LOOP_DIR not in sys.path:
    sys.path.insert(0, _LOOP_DIR)


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def _cmd_start(args):
    from host import start_loop
    mode = getattr(args, "mode", "planning") or "planning"
    from_loop = getattr(args, "from_loop", None)
    if mode == "planning" and not args.sketch:
        print("  Error: a planning loop requires --sketch", file=sys.stderr)
        sys.exit(1)
    if mode == "coding" and not from_loop:
        print("  Error: a coding loop requires --from-loop <approved planning loop id>",
              file=sys.stderr)
        sys.exit(1)
    source_brief = getattr(args, "source_brief", None)
    if source_brief is not None and mode != "coding":
        print("  Error: --source-brief is only valid with --mode coding",
              file=sys.stderr)
        sys.exit(1)
    try:
        start_loop(
            feature=args.feature,
            sketch_path=args.sketch,
            max_rounds=args.max_rounds,
            turn_timeout=args.turn_timeout,
            mode=mode,
            from_loop=from_loop,
            brief_path=getattr(args, "brief", None),
            source_brief=source_brief,
        )
    except FileNotFoundError as e:
        print(f"  Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"  Error: {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"  Error: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_status(args):
    from session import resolve_token, load_session
    from state_machine import is_terminal, is_paused, is_active

    try:
        loop_id, role, loop_dir = resolve_token(args.token)
    except ValueError as e:
        print(f"  Error: {e}", file=sys.stderr)
        sys.exit(2)

    try:
        session = load_session(loop_dir)
    except FileNotFoundError:
        print(f"  Error: session not found for loop {loop_id}", file=sys.stderr)
        sys.exit(2)

    status = session["status"]
    stage = status["stage"]
    next_role = status.get("next_role")
    rnd = status.get("round", 0)
    max_rnd = status.get("max_rounds", 0)

    # Architect gets a supervisor view
    if role == "architect":
        _cmd_status_architect(args, session, loop_id, loop_dir)
        return

    # Model view
    my_turn = next_role == role

    if args.json:
        out = {
            "schema": "gator-loop-status-v1",
            "loop_id": loop_id,
            "loop_dir": str(loop_dir),
            "role": role,
            "your_turn": my_turn,
            "stage": stage,
            "round": rnd,
            "max_rounds": max_rnd,
            "blocked": status.get("blocked", False),
            "next_role": next_role,
            "architect_message": status.get("architect_message"),
            "architect_response_artifact": (
                str(loop_dir / status["architect_response_artifact"])
                if status.get("architect_response_artifact") else None
            ),
            "turn_timeout_seconds": status.get("turn_timeout_seconds"),
            "turn_deadline": status.get("turn_deadline"),
            "mode": _mode_of(session),
        }
        _strip_participant_time(session, out)
        out.update(_briefs_json(session, loop_dir))
        res = _approval_resolution(session, loop_dir)
        if res is not None:
            out["approval_resolution"] = res
        print(json.dumps(out, indent=2))
    else:
        print(f"  Loop: {loop_id}")
        print(f"  Dir: {loop_dir}")
        print(f"  Role: {role}")
        print(f"  Your turn: {'YES' if my_turn else 'NO'}")
        print(f"  Stage: {stage}")
        if _mode_of(session) == "coding":
            print("  Mode: coding")
        _print_briefs(session, loop_dir)

        if is_terminal(session):
            _print_terminal_reason(session, role)
            _print_approval_resolution(_approval_resolution(session, loop_dir))
            print("  Loop ended.")
        elif is_paused(session):
            print("  Blocked -- waiting for Architect")
        elif my_turn:
            architect_msg = status.get("architect_message")
            if architect_msg:
                print(f"  Architect message: {architect_msg}")
            response_artifact = status.get("architect_response_artifact")
            if response_artifact:
                print(f"  Architect response artifact: {loop_dir / response_artifact}")
            _print_turn_window(session)
            _print_action_prompt(session, role, loop_dir, args.token)
        else:
            print(f"  Waiting for: {next_role}")

        print(f"  Round: {rnd}/{max_rnd}")

    # Exit codes: 0 = your turn, 1 = not your turn, 2 = blocked/terminal
    if is_terminal(session) or is_paused(session):
        sys.exit(2)
    elif not my_turn:
        sys.exit(1)
    else:
        sys.exit(0)


def _cmd_status_architect(args, session, loop_id, loop_dir):
    """Architect supervisor view — always authorized to act on active loops."""
    from state_machine import is_terminal, is_paused, is_active

    status = session["status"]
    stage = status["stage"]
    rnd = status.get("round", 0)
    max_rnd = status.get("max_rounds", 0)
    roles = session.get("roles", {})

    decisions = session.get("decisions", [])
    pending = [d for d in decisions if d.get("response") is None]

    if args.json:
        out = {
            "schema": "gator-loop-status-v1",
            "loop_id": loop_id,
            "loop_dir": str(loop_dir),
            "role": "architect",
            "stage": stage,
            "round": rnd,
            "max_rounds": max_rnd,
            "blocked": status.get("blocked", False),
            "next_role": status.get("next_role"),
            "architect_message": status.get("architect_message"),
            "turn_timeout_seconds": status.get("turn_timeout_seconds"),
            "turn_deadline": status.get("turn_deadline"),
            "draftor_joined": roles.get("draftor", {}).get("joined", False),
            "reviewer_joined": roles.get("reviewer", {}).get("joined", False),
            "turns": session.get("turns", []),
            "decisions": decisions,
            "pending_decisions": pending,
            "mode": _mode_of(session),
        }
        attention = _attention_view(session)
        if attention is not None:
            out["attention"] = attention
        out.update(_briefs_json(session, loop_dir))
        res = _approval_resolution(session, loop_dir)
        if res is not None:
            out["approval_resolution"] = res
        print(json.dumps(out, indent=2))
    else:
        print(f"  Loop: {loop_id}")
        print(f"  Dir: {loop_dir}")
        print(f"  Role: architect (supervisor)")
        print(f"  Stage: {stage}")
        _print_briefs(session, loop_dir, architect=True)

        if is_active(session):
            print(f"  Active role: {status.get('next_role', '?')}")
            _print_attention_lines(session)
        elif is_paused(session):
            print(f"  Paused: {stage}")
        elif is_terminal(session):
            _print_terminal_reason(session, "architect")
            _print_approval_resolution(_approval_resolution(session, loop_dir),
                                       token=args.token)
            print("  Loop ended.")
            if stage == "max_rounds_exceeded":
                print()
                print("  Continue with more rounds (requires a reason):")
                print(f"    gator loop extend --token {args.token} --rounds <1-20> --message \"...\"")

        print(f"  Round: {rnd}/{max_rnd}")
        print(f"  Draftor: {'joined' if roles.get('draftor', {}).get('joined') else 'waiting'}")
        print(f"  Reviewer: {'joined' if roles.get('reviewer', {}).get('joined') else 'waiting'}")

        if is_active(session):
            print()
            print("  Commands:")
            print(f"    gator loop pause --token {args.token} --message \"...\"")
            print(f"    gator loop interject --token {args.token} --message \"...\"")
            print(f"    gator loop end --token {args.token} --reason \"...\"")
        elif is_paused(session):
            if pending:
                p = pending[-1]
                req = p.get("request", {})
                print(f"  Pending decision: {p['id']}")
                print(f"    Reason: {req.get('reason', '?')}")
                if req.get("artifact_path"):
                    print(f"    Request: {loop_dir / req['artifact_path']}")
            legacy_time = not _attention_on(session)
            if legacy_time:
                print(f"  Turn window: {status.get('turn_timeout_seconds')}s "
                      f"(change on unblock with --timeout <30-3600>)")
            else:
                print(f"  Attention interval: {_fmt_secs(status.get('turn_timeout_seconds'))} "
                      f"(Architect notice only)")
            timeout_hint = " [--timeout <s>]" if legacy_time else ""
            print()
            print("  Commands:")
            if pending:
                print("    Response required (message or --file) to resolve the pending decision:")
                print(f"    gator loop unblock --token {args.token} --message \"...\" [--file <response.md>]{timeout_hint}")
                print(f"    Exceptional: gator loop unblock --token {args.token} --no-response")
            else:
                print(f"    gator loop unblock --token {args.token} [--message \"...\"]{timeout_hint}")
            print(f"    gator loop end --token {args.token} --reason \"...\"")

    # Architect exit codes: 0 = active (can act), 2 = paused/terminal
    if is_terminal(session) or is_paused(session):
        sys.exit(2)
    else:
        sys.exit(0)


def _attention_on(session):
    from session import attention_mode
    return attention_mode(session)


def _fmt_secs(seconds):
    if isinstance(seconds, bool) or not isinstance(seconds, int):
        return "?"
    if seconds >= 60 and seconds % 60 == 0:
        return f"{seconds // 60} min"
    if seconds >= 60:
        return f"{seconds // 60}m {seconds % 60}s"
    return f"{seconds}s"


def _strip_participant_time(session, out):
    """#47: participant JSON never carries a time window for attention-mode
    loops (no deadline, no interval). Legacy loops are unchanged."""
    if _attention_on(session):
        out.pop("turn_timeout_seconds", None)
        out.pop("turn_deadline", None)


def _attention_view(session, now=None):
    """Architect-only attention projection for flagged loops, else None.

    ``due`` is informational (elapsed >= interval); ``notified`` reflects
    the durable marker for the current turn.
    """
    from datetime import datetime, timezone
    if not _attention_on(session):
        return None
    status = session.get("status", {})
    interval = status.get("turn_timeout_seconds")
    started = status.get("turn_started_at")
    notified_turn = status.get("attention_notified_turn")
    elapsed = None
    if isinstance(started, str):
        try:
            dt = datetime.fromisoformat(started)
            if dt.tzinfo is not None and dt.utcoffset() is not None:
                elapsed = max(0, int(((now or datetime.now(tz=timezone.utc)) - dt)
                                     .total_seconds()))
        except (ValueError, TypeError, OverflowError):
            elapsed = None
    valid_interval = isinstance(interval, int) and not isinstance(interval, bool)
    return {
        "interval_seconds": interval if valid_interval else None,
        "turn_started_at": started if isinstance(started, str) else None,
        "elapsed_seconds": elapsed,
        "notified_turn": notified_turn if isinstance(notified_turn, str) else None,
        "notified": isinstance(started, str) and notified_turn == started,
        "due": bool(valid_interval and elapsed is not None and elapsed >= interval),
    }


def _print_attention_lines(session):
    """Architect text view: interval, elapsed time, and notice state."""
    view = _attention_view(session)
    if view is None:
        return
    print(f"  Attention interval: {_fmt_secs(view['interval_seconds'])} "
          f"(Architect notice only)")
    if view["elapsed_seconds"] is not None:
        print(f"  Elapsed this turn: {_fmt_secs(view['elapsed_seconds'])}")
    if view["notified"]:
        print("  Attention: due (notice recorded). The loop is still running; "
              "no action is required.")
    elif view["due"]:
        print("  Attention: interval passed; no notice recorded yet "
              "(is a loop host running?)")


def _print_window_line(session):
    """Architect output after unblock/extend/reopen."""
    status = session["status"]
    if _attention_on(session):
        print(f"  Attention interval: {_fmt_secs(status.get('turn_timeout_seconds'))} "
              f"(Architect notice only)")
    else:
        print(f"  Turn window: {status.get('turn_timeout_seconds')}s")


def _host_duty(loop_dir):
    """Wording for what an attached host does for this loop (#47)."""
    from session import load_session
    try:
        flagged = _attention_on(load_session(loop_dir))
    except Exception:
        flagged = False
    if flagged:
        return {"does": "records attention notices",
                "not": "attention notices are NOT being recorded",
                "ctrl_c": "attention notices",
                "stopped": "Attention notices are no longer recorded for this loop."}
    return {"does": "enforces turn timeouts",
            "not": "turn timeouts are NOT being enforced",
            "ctrl_c": "turn-timeout enforcement",
            "stopped": "Turn timeouts are no longer enforced for this loop."}


def _print_turn_window(session):
    """Print the active turn window and deadline for the acting participant.

    #47: attention-mode loops show participants no time information.
    """
    if _attention_on(session):
        return
    status = session["status"]
    timeout = status.get("turn_timeout_seconds")
    deadline = status.get("turn_deadline")
    if timeout is None:
        return
    line = f"  Turn window: {timeout}s"
    if deadline:
        line += f" (deadline {deadline})"
    print(line)


def _mode_of(session):
    """Normalized loop mode for display; unknown modes show as-is."""
    from session import loop_mode
    try:
        return loop_mode(session)
    except ValueError:
        return str(session.get("mode"))


def _print_action_prompt(session, role, loop_dir, token):
    """Print the action hint and next-step command for the active role."""
    stage = session["status"]["stage"]

    if _mode_of(session) == "coding":
        _print_coding_action_prompt(session, role, loop_dir, token)
        return

    if role == "draftor":
        if stage == "plan_drafting":
            print("  Action: Draft the implementation plan based on the sketch.")
            print(f"  Sketch: {loop_dir / 'sketch.md'}")
        else:
            print("  Action: Revise the plan based on reviewer findings.")
            print(f"  Findings: {loop_dir / 'findings.current.md'}")
        print()
        print("  Next step:")
        print(f"    gator loop submit-draft --token {token} --file <your-plan.md>")
    elif role == "reviewer":
        print("  Action: Review the plan and submit findings or approve.")
        print(f"  Plan: {loop_dir / 'plan.current.md'}")
        print()
        print("  Next step:")
        print(f"    gator loop submit-review --token {token} --file <findings.md>")
        print(f"    gator loop submit-review --token {token} --file <review.md> --approve")


_STALE_REASONS = {
    "staged_tree_changed": "the staged tree changed after approval",
    "head_moved_tree_differs": ("HEAD moved and its tree is not the approved "
                                "tree (a different commit, or a hook changed "
                                "committed content)"),
    "detached_mismatch": "detached HEAD whose tree is not the approved tree",
}


_BRIEF_MARKERS = {
    "ok": "[OK]",
    "missing": "[!!] MISSING",
    "mismatch": "[!!] DIGEST MISMATCH",
    "unreadable": "[!!] UNREADABLE",
    "invalid_ref": "[!!] INVALID REFERENCE",
    "unsafe": "[!!] UNSAFE PATH",
}


def _brief_entries(session, loop_dir):
    """(label, path_or_None, check) for each brief position (#43).

    ``absent`` positions are omitted, so no-brief loops print nothing.
    Paths are the FIXED artifact names inside the loop dir, never a path
    taken from session data.
    """
    from session import verify_brief, BRIEF_FILENAME, SOURCE_BRIEF_FILENAME
    entries = []
    coding = session.get("coding") if isinstance(session.get("coding"), dict) else None
    label = ("Architect brief (this coding loop)" if coding is not None
             else "Architect brief")
    check = verify_brief(loop_dir, session.get("brief"), BRIEF_FILENAME)
    if check != "absent":
        entries.append((label, Path(loop_dir) / BRIEF_FILENAME, check))
    if coding is not None:
        check = verify_brief(loop_dir, coding.get("source_brief"),
                             SOURCE_BRIEF_FILENAME)
        if check != "absent":
            entries.append((
                f"Architect brief (from approved plan {coding.get('source_loop_id')})",
                Path(loop_dir) / SOURCE_BRIEF_FILENAME, check))
    return entries


def _print_briefs(session, loop_dir, architect=False):
    for label, path, check in _brief_entries(session, loop_dir):
        marker = _BRIEF_MARKERS.get(check, check)
        print(f"  {label}: {path} {marker}"
              + (" (required reading)" if check == "ok" else ""))
        if check != "ok":
            print("    This brief failed its integrity check; do not rely on it."
                  + ("" if architect else " Escalate to the Architect."))
    coding = session.get("coding") if isinstance(session.get("coding"), dict) else None
    if coding is not None and coding.get("source_brief_decision") == "dropped":
        print("  Planning brief: not carried forward (Architect's choice at coding start)")


def _briefs_json(session, loop_dir):
    out = {}
    for label, path, check in _brief_entries(session, loop_dir):
        key = "source_brief" if "approved plan" in label else "brief"
        out[key] = {"path": str(path), "check": check}
    coding = session.get("coding") if isinstance(session.get("coding"), dict) else None
    if coding is not None:
        out["source_brief_decision"] = coding.get("source_brief_decision")
    return out


def _approval_resolution(session, loop_dir):
    """Live approval resolution for an approved coding loop, else None."""
    if _mode_of(session) != "coding":
        return None
    if session["status"].get("stage") != "implementation_approved":
        return None
    import gitsnap
    from state_machine import resolve_approval
    coding = session.get("coding") or {}
    repo_root = Path(loop_dir).parent.parent.parent
    snap = gitsnap.snapshot(repo_root, coding.get("base_head"))
    return resolve_approval(coding.get("approval"), snap)


def _print_approval_resolution(res, token=None):
    """Text + marker lines (never meaning by color alone)."""
    if not res:
        return
    state = res["state"]
    tree = (res.get("approved_tree") or "")
    if state == "committed":
        print(f"  Approval: [OK] COMMITTED -- handoff complete (commit {res.get('commit')})")
    elif state == "pending":
        print("  Approval: [..] PENDING COMMIT -- return to the Draftor session for")
        print(f"            one normal commit of staged tree {tree}")
    elif state == "stale":
        why = _STALE_REASONS.get(res.get("reason"), res.get("reason"))
        print(f"  Approval: [!!] STALE -- {why}.")
        print("            The approved tree is no longer the candidate.")
    elif state == "unknown":
        print(f"  Approval: [??] UNKNOWN -- Git facts unavailable ({res.get('reason')});")
        print("            never treat this as approved.")
    if token and state in ("stale", "unknown"):
        print("  Return it to implementation review (requires a reason):")
        print(f"    gator loop reopen --token {token} --message \"...\"")


def _print_coding_action_prompt(session, role, loop_dir, token):
    """Coding-mode action hint (#41). The staged tree is the candidate."""
    stage = session["status"]["stage"]
    if role == "draftor":
        if stage == "implementation_drafting":
            print("  Action: Implement the approved plan, stage the intended change")
            print("          (code, charters, and commit_draft material), then submit.")
        else:
            print("  Action: Revise the staged implementation based on reviewer findings.")
            print(f"  Findings: {loop_dir / 'findings.current.md'}")
        print(f"  Approved plan: {loop_dir / 'approved-plan.md'}")
        print()
        print("  Next step:")
        print(f"    gator loop submit-implementation --token {token} --file <implementation.md>")
    elif role == "reviewer":
        print("  Action: Review the submitted candidate tree and the")
        print("          implementation artifact; submit findings or approve.")
        print(f"  Implementation: {loop_dir / 'implementation.current.md'}")
        gens = session.get("coding", {}).get("generations") or []
        if gens:
            snap = gens[-1]["snapshot"]
            print(f"  Candidate staged tree: {snap['staged_tree']} (round {gens[-1]['round']})")
            print(f"  Review exactly that candidate: git diff {snap['base_tree']} {snap['staged_tree']}")
        print()
        print("  Next step:")
        print(f"    gator loop submit-review --token {token} --file <findings.md>")
        print(f"    gator loop submit-review --token {token} --file <review.md> --approve")


def _print_terminal_reason(session, role):
    """Print why the loop ended."""
    stage = session["status"]["stage"]
    if stage == "implementation_approved":
        print("  Result: Implementation approved -- return to the Draftor session")
        print("          for one normal commit (existing hooks, Architect confirmation).")
    elif stage == "plan_approved":
        print("  Result: Plan approved")
    elif stage == "max_rounds_exceeded":
        max_r = session["status"].get("max_rounds", "?")
        print(f"  Result: Max rounds exceeded ({max_r})")
    elif stage == "turn_timed_out":
        print("  Result: Turn timed out")
    elif stage == "ended_by_architect":
        reason = session["status"].get("end_reason", "")
        if reason:
            print(f"  Result: Ended by Architect -- {reason}")
        else:
            print("  Result: Ended by Architect")


def _cmd_submit_implementation(args):
    """Coding (#41): submit the staged candidate + implementation artifact."""
    from submit import handle_submit_implementation, split_residue
    try:
        loop_id, role, loop_dir, gen = handle_submit_implementation(
            args.token, args.file)
    except PermissionError as e:
        print(f"  Rejected: {e}", file=sys.stderr)
        sys.exit(1)
    except (ValueError, FileNotFoundError) as e:
        print(f"  Error: {e}", file=sys.stderr)
        sys.exit(1)
    snap = gen["snapshot"]
    n_changed = len(snap["changed_paths"]) + snap.get("changed_truncated", 0)
    loop_res, other_res = split_residue(snap["unstaged_paths"])
    n_other = len(other_res) + snap.get("unstaged_truncated", 0)
    print(f"  Implementation submitted (round {gen['round']}). Advancing to implementation_review.")
    print(f"  Candidate staged tree: {snap['staged_tree']}")
    print(f"  Changed paths vs base: {n_changed}")
    if n_other:
        print(f"  WARNING: {n_other} unstaged/untracked path(s) are NOT part of the candidate.")
    if loop_res:
        print(f"  Loop residue under .gator/loops/: {len(loop_res)} path(s) (expected; not part of the candidate).")
    print(f"  Artifact: {loop_dir / 'implementation.current.md'}")
    print(f"  Loop: {loop_id}")


def _cmd_submit_draft(args):
    from submit import handle_submit_draft
    try:
        loop_id, role, loop_dir = handle_submit_draft(args.token, args.file)
        print(f"  Draft submitted. Advancing to plan_review.")
        print(f"  Loop: {loop_id}")
    except (FileNotFoundError, ValueError) as e:
        print(f"  Error: {e}", file=sys.stderr)
        sys.exit(1)
    except PermissionError as e:
        print(f"  Rejected: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_submit_review(args):
    from submit import handle_submit_review
    try:
        loop_id, role, loop_dir = handle_submit_review(
            args.token, args.file, approve=args.approve
        )
        from session import load_session
        session = load_session(loop_dir)
        if _mode_of(session) == "coding":
            gen = (session.get("coding", {}).get("generations") or [{}])[-1]
            review = gen.get("review") or {}
            if args.approve:
                print(f"  Implementation approved: staged tree {review.get('reviewed_tree')}.")
                print("  Return to the Draftor session for ONE normal commit (existing")
                print("  hooks, Architect confirmation). If the staged tree changes first,")
                print("  the approval becomes stale and the loop must be reopened.")
            else:
                print(f"  Review submitted for staged tree {review.get('reviewed_tree')}.")
                if review.get("candidate_changed"):
                    print("  Note: the live candidate changed after submission; the Draftor")
                    print("  must resubmit the current tree.")
                print(f"  Stage: {session['status']['stage']}")
        elif args.approve:
            print(f"  Plan approved. Loop complete.")
        else:
            print(f"  Review submitted. Revision requested.")
        print(f"  Loop: {loop_id}")
    except (FileNotFoundError, ValueError) as e:
        print(f"  Error: {e}", file=sys.stderr)
        sys.exit(1)
    except PermissionError as e:
        print(f"  Rejected: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_escalate(args):
    from submit import handle_escalate
    try:
        loop_id, role, loop_dir = handle_escalate(
            args.token, args.reason, file_path=getattr(args, "file", None)
        )
        print(f"  Escalated. Loop blocked -- waiting for Architect.")
        print(f"  Loop: {loop_id}")
    except (FileNotFoundError, ValueError) as e:
        print(f"  Error: {e}", file=sys.stderr)
        sys.exit(1)
    except PermissionError as e:
        print(f"  Rejected: {e}", file=sys.stderr)
        sys.exit(1)


def _turn_timeout_arg(value):
    """argparse type for unblock --timeout; delegates to the shared validator."""
    from session import validate_turn_timeout
    try:
        return validate_turn_timeout(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))


def _cmd_unblock(args):
    from submit import handle_unblock
    try:
        loop_id, loop_dir = handle_unblock(
            args.token, next_role=args.next_role, stage=args.stage,
            message=args.message, file_path=getattr(args, "file", None),
            turn_timeout=getattr(args, "timeout", None),
            no_response=getattr(args, "no_response", False),
        )
        from session import load_session
        session = load_session(loop_dir)
        stage = session["status"]["stage"]
        next_role = session["status"]["next_role"]
        print(f"  Unblocked. Resumed to {stage} (next: {next_role}).")
        _print_window_line(session)
        print(f"  Loop: {loop_id}")
    except (FileNotFoundError, ValueError) as e:
        print(f"  Error: {e}", file=sys.stderr)
        sys.exit(1)
    except PermissionError as e:
        print(f"  Rejected: {e}", file=sys.stderr)
        sys.exit(1)


def _round_count_arg(value):
    """argparse type for extend --rounds; delegates to the shared validator."""
    from session import validate_round_count
    try:
        return validate_round_count(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))


def _cmd_extend(args):
    """Architect: continue a loop that ended at its round limit (#39).

    Host contract (mirrors `gator loop start`): after a successful
    extension this command always attaches the foreground watcher, so the
    revived loop is never left live-but-unhosted by this command.
      - attached        -> watch in the foreground until terminal / Ctrl+C
      - already_hosted  -> another live process hosts it; exit 0
      - failed          -> extension is saved, timeouts NOT enforced; exit 1
    """
    import host as loop_host
    from session import load_session

    try:
        loop_id, loop_dir, previous, new = loop_host.extend_loop(
            args.token, args.rounds, args.message)
    except PermissionError as e:
        print(f"  Rejected: {e}", file=sys.stderr)
        sys.exit(1)
    except (RuntimeError, ValueError, FileNotFoundError) as e:
        print(f"  Error: {e}", file=sys.stderr)
        sys.exit(1)

    session = load_session(loop_dir)
    status = session["status"]
    print(f"  Extended: max rounds {previous} -> {new} (round {status.get('round', 0)}).")
    print(f"  Resumed to {status['stage']} (next: {status['next_role']}).")
    _print_window_line(session)
    print(f"  Loop: {loop_id}")
    print()
    print("  Participants must be re-engaged: give the Draftor and Reviewer fresh")
    print("  join prompts (Dashboard \"Copy prompt\", or their loop tokens).")
    print()

    _attach_foreground_watcher(loop_host, loop_dir, "extension")


def _attach_foreground_watcher(loop_host, loop_dir, what):
    """Host contract shared by extend (#39) and reopen (#41).

    attached -> watch in the foreground until terminal / Ctrl+C;
    already_hosted -> another live process enforces timeouts, exit 0;
    failed -> the revival is saved but timeouts are NOT enforced, exit 1.
    """
    duty = _host_duty(loop_dir)
    fd, state, detail = loop_host.acquire_host_lock_with_retry(loop_dir)
    if state == loop_host.HOST_ALREADY_HOSTED:
        print(f"  Host: already hosted ({detail}). That process {duty['does']}.")
        return
    if state != loop_host.HOST_ATTACHED:
        print(f"  Host: could not attach a watcher ({detail}).", file=sys.stderr)
        print(f"  The {what} is saved, but {duty['not']}.",
              file=sys.stderr)
        sys.exit(1)

    print(f"  Host: watching in the foreground (Ctrl+C stops {duty['ctrl_c']}).")
    print()
    sys.stdout.flush()
    try:
        loop_host.watch_loop(loop_dir, host_lock_fd=fd)
    except KeyboardInterrupt:
        print()
        print(f"  Host stopped. {duty['stopped']}")
    finally:
        loop_host.release_host_lock(fd)


def _cmd_reopen(args):
    """Architect: reopen an approved coding loop for revision (#41).

    Same host contract as `gator loop extend`: after a successful reopen
    this command always attaches the foreground watcher, so the revived
    loop is never left live-but-unhosted by this command.
    """
    import host as loop_host
    from session import load_session

    try:
        loop_id, loop_dir = loop_host.reopen_loop(args.token, args.message)
    except PermissionError as e:
        print(f"  Rejected: {e}", file=sys.stderr)
        sys.exit(1)
    except (RuntimeError, ValueError, FileNotFoundError) as e:
        print(f"  Error: {e}", file=sys.stderr)
        sys.exit(1)

    session = load_session(loop_dir)
    status = session["status"]
    print(f"  Reopened: {status['stage']} (next: {status['next_role']}, "
          f"round {status.get('round', 0)}).")
    print("  The previous approval is invalidated; the Draftor must resubmit.")
    _print_window_line(session)
    print(f"  Loop: {loop_id}")
    print()
    print("  Participants must be re-engaged: give the Draftor and Reviewer fresh")
    print("  join prompts (Dashboard \"Copy prompt\", or their loop tokens).")
    print()

    _attach_foreground_watcher(loop_host, loop_dir, "reopen")


def _cmd_pause(args):
    from submit import handle_pause
    try:
        loop_id, loop_dir = handle_pause(args.token, message=args.message)
        print(f"  Paused. Loop suspended -- waiting for unblock.")
        print(f"  Loop: {loop_id}")
    except (ValueError, PermissionError) as e:
        print(f"  Rejected: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_interject(args):
    from submit import handle_interject
    try:
        loop_id, loop_dir = handle_interject(args.token, args.message)
        print(f"  Interjection sent. Active model will see it on next status check.")
        print(f"  Loop: {loop_id}")
    except (ValueError, PermissionError) as e:
        print(f"  Rejected: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_end(args):
    from submit import handle_end
    try:
        loop_id, loop_dir = handle_end(args.token, reason=args.reason)
        print(f"  Loop ended by Architect.")
        print(f"  Loop: {loop_id}")
    except (ValueError, PermissionError) as e:
        print(f"  Rejected: {e}", file=sys.stderr)
        sys.exit(1)


WAIT_EXIT_STILL_WAITING = 3


def _positive_seconds(value):
    """argparse type for --max-seconds: a finite number greater than zero."""
    import math
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(f"must be a number of seconds, got {value!r}")
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError(f"must be greater than zero, got {value!r}")
    return seconds


def _cmd_wait(args):
    """Block until the loop becomes actionable for this role.

    With --max-seconds, return early (exit 3, wake_reason "still_waiting")
    when the deadline passes while another role still owns the turn.
    """
    import time as _time
    from session import resolve_token, load_session
    from state_machine import is_terminal, is_paused

    max_seconds = getattr(args, "max_seconds", None)
    if max_seconds is not None:
        try:
            max_seconds = _positive_seconds(max_seconds)
        except argparse.ArgumentTypeError as e:
            print(f"  Error: --max-seconds {e}", file=sys.stderr)
            sys.exit(2)

    try:
        loop_id, role, loop_dir = resolve_token(args.token)
    except ValueError as e:
        print(f"  Error: {e}", file=sys.stderr)
        sys.exit(2)

    if role == "architect":
        print("  Error: wait is for model roles only. Use status for the architect view.", file=sys.stderr)
        sys.exit(1)

    poll = getattr(args, "poll", 2.0)
    started = _time.monotonic()
    session, wake_reason = _wait_for_actionable(
        loop_dir, role, poll, load_session, is_terminal, is_paused,
        max_seconds=max_seconds,
    )
    waited_seconds = round(_time.monotonic() - started, 1)
    still_waiting = wake_reason == "still_waiting"
    reissue_cmd = f"gator loop wait --token {args.token}"
    if max_seconds is not None:
        reissue_cmd += f" --max-seconds {max_seconds:g}"

    # Render the same output as status
    status = session["status"]
    stage = status["stage"]
    next_role = status.get("next_role")
    my_turn = next_role == role
    rnd = status.get("round", 0)
    max_rnd = status.get("max_rounds", 0)

    if args.json:
        out = {
            "schema": "gator-loop-status-v1",
            "loop_id": loop_id,
            "loop_dir": str(loop_dir),
            "role": role,
            "your_turn": my_turn,
            "stage": stage,
            "round": rnd,
            "max_rounds": max_rnd,
            "blocked": status.get("blocked", False),
            "next_role": next_role,
            "architect_message": status.get("architect_message"),
            "architect_response_artifact": (
                str(loop_dir / status["architect_response_artifact"])
                if status.get("architect_response_artifact") else None
            ),
            "turn_timeout_seconds": status.get("turn_timeout_seconds"),
            "turn_deadline": status.get("turn_deadline"),
            "wake_reason": wake_reason,
            "max_seconds": max_seconds,
            "waited_seconds": waited_seconds,
            "reissue_command": reissue_cmd if still_waiting else None,
        }
        _strip_participant_time(session, out)
        print(json.dumps(out, indent=2))
    else:
        print(f"  Loop: {loop_id}")
        print(f"  Dir: {loop_dir}")
        print(f"  Role: {role}")
        print(f"  Your turn: {'YES' if my_turn else 'NO'}")
        print(f"  Stage: {stage}")

        if is_terminal(session):
            _print_terminal_reason(session, role)
            _print_approval_resolution(_approval_resolution(session, loop_dir))
            print("  Loop ended.")
        elif is_paused(session):
            print("  Blocked -- waiting for Architect")
        elif my_turn:
            architect_msg = status.get("architect_message")
            if architect_msg:
                print(f"  Architect message: {architect_msg}")
            response_artifact = status.get("architect_response_artifact")
            if response_artifact:
                print(f"  Architect response artifact: {loop_dir / response_artifact}")
            _print_turn_window(session)
            _print_action_prompt(session, role, loop_dir, args.token)
        elif still_waiting:
            print(f"  Still waiting -- another role owns the turn "
                  f"(waited {waited_seconds:g}s of {max_seconds:g}s).")
            print("  You are still a loop participant. Reissue the same command now:")
            print(f"    {reissue_cmd}")

        print(f"  Round: {rnd}/{max_rnd}")

    # Exit codes: 0 = your turn, 2 = paused/terminal, 3 = still waiting (bounded)
    if is_terminal(session) or is_paused(session):
        sys.exit(2)
    elif still_waiting:
        sys.exit(WAIT_EXIT_STILL_WAITING)
    else:
        sys.exit(0)


def _wait_for_actionable(loop_dir, role, poll_interval, load_session, is_terminal, is_paused,
                         max_seconds=None, clock=None, sleep=None):
    """Poll session.json until the loop becomes actionable for this role.

    Returns (session, wake_reason). Read-only — never writes any file.
    With max_seconds, returns (session, "still_waiting") once the monotonic
    deadline passes; each sleep is capped at the remaining time so the call
    never overruns its limit by a full poll interval. clock/sleep are test
    seams (default time.monotonic / time.sleep).
    """
    import time as _time
    clock = clock or _time.monotonic
    sleep = sleep or _time.sleep
    deadline = clock() + max_seconds if max_seconds is not None else None

    # Check immediately first
    session = load_session(loop_dir)
    if is_terminal(session):
        return session, "terminal"
    if is_paused(session):
        return session, "paused"
    if session["status"].get("next_role") == role:
        return session, "already_your_turn"

    # Poll
    while True:
        if deadline is None:
            sleep(poll_interval)
        else:
            remaining = deadline - clock()
            if remaining <= 0:
                return session, "still_waiting"
            sleep(min(poll_interval, remaining))
        try:
            session = load_session(loop_dir)
        except (FileNotFoundError, KeyError):
            continue
        if is_terminal(session):
            return session, "terminal"
        if is_paused(session):
            return session, "paused"
        if session["status"].get("next_role") == role:
            return session, "became_your_turn"


def _cmd_tail(args):
    from events import tail_events, format_event
    from session import find_gator_root

    repo_root = find_gator_root()
    loop_dir = repo_root / ".gator" / "loops" / args.loop

    if not loop_dir.is_dir():
        print(f"  Error: loop not found: {args.loop}", file=sys.stderr)
        sys.exit(1)

    print(f"  Tailing: {args.loop}")
    print()

    try:
        for event in tail_events(loop_dir):
            print(format_event(event))
            sys.stdout.flush()
            if event.get("event") in {"plan_approved", "max_rounds_exceeded", "turn_timed_out", "loop_ended_by_architect"}:
                print()
                print("  Loop ended.")
                return
    except KeyboardInterrupt:
        print()
        print("  Tail stopped.")


def _cmd_list(args):
    from session import find_gator_root, load_session

    repo_root = find_gator_root()
    loops_dir = repo_root / ".gator" / "loops"

    if not loops_dir.is_dir():
        print("  No loops found.")
        return

    loop_dirs = sorted(
        [d for d in loops_dir.iterdir() if d.is_dir() and not d.name.startswith(".")],
        key=lambda d: d.name,
    )

    if not loop_dirs:
        print("  No loops found.")
        return

    if args.json:
        entries = []
        for d in loop_dirs:
            try:
                s = load_session(d)
                entries.append({
                    "loop_id": s.get("loop_id", d.name),
                    "feature": s.get("feature", ""),
                    "stage": s["status"]["stage"],
                    "round": s["status"].get("round", 0),
                    "max_rounds": s["status"].get("max_rounds", 0),
                    "blocked": s["status"].get("blocked", False),
                })
            except (FileNotFoundError, KeyError, json.JSONDecodeError):
                entries.append({"loop_id": d.name, "error": "unreadable"})
        print(json.dumps({"schema": "gator-loop-list-v1", "loops": entries}, indent=2))
    else:
        print(f"  {'Loop ID':<50} {'Feature':<20} {'Stage':<25} {'Round'}")
        print(f"  {'---':<50} {'---':<20} {'---':<25} {'---'}")
        for d in loop_dirs:
            try:
                s = load_session(d)
                lid = s.get("loop_id", d.name)
                feat = s.get("feature", "")
                stage = s["status"]["stage"]
                blocked = " [BLOCKED]" if s["status"].get("blocked") else ""
                rnd = f"{s['status'].get('round', 0)}/{s['status'].get('max_rounds', 0)}"
                print(f"  {lid:<50} {feat:<20} {stage + blocked:<25} {rnd}")
            except (FileNotFoundError, KeyError, json.JSONDecodeError):
                print(f"  {d.name:<50} {'?':<20} {'unreadable':<25} {'?'}")


# ---------------------------------------------------------------------------
# Argparse
# ---------------------------------------------------------------------------

def _render_participant(payload, as_json):
    """One JSON line (adapter contract) or short human text. Never prints
    the token or registration_id — neither is ever in ``payload``."""
    if as_json:
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        sys.stdout.flush()
        return
    wake = payload.get("wake_reason")
    if wake == "error":
        print(f"  Error: {payload.get('error')}", file=sys.stderr)
        return
    print(f"  Loop: {payload.get('loop_id')}")
    print(f"  Role: {payload.get('role')}")
    messages = {
        "turn_ready": "Turn ready -- it is your turn now. Run: gator loop status --token <your-token>",
        "architect_block": "Loop paused or blocked on the Architect. Relaunch the watcher to wait for the unblock.",
        "terminal": "Loop ended. Stop; do not relaunch the watcher.",
        "still_waiting": "Still waiting -- another role owns the turn. Relaunch the same watch command.",
        "superseded": "Superseded -- a newer watcher owns this role. Stop.",
        "interrupted": "Watcher interrupted.",
    }
    print(f"  {messages.get(wake, wake)}")
    if payload.get("acked"):
        print("  (Acknowledged means this watcher received the notification -- "
              "not that any work was done.)")


def _cmd_participant_watch(args):
    """D2a receiver: register, heartbeat, deliver + ack one notification, exit.

    Exit: 0 turn_ready, 2 architect_block/terminal, 3 still_waiting,
    4 superseded, 1 error, 130 interrupted (SIGINT/SIGTERM).
    """
    import signal
    import liveness

    def _term(signum, frame):
        raise KeyboardInterrupt()
    try:
        signal.signal(signal.SIGTERM, _term)
    except (ValueError, OSError, AttributeError):
        pass  # not main thread / unsupported platform

    code, payload = liveness.run_watch(
        args.token, args.max_seconds, poll_seconds=args.poll_seconds,
        adapter_label=args.adapter_label)
    _render_participant(payload, args.json)
    sys.exit(code)


def _cmd_participant_status(args):
    """Own-role liveness summary. Read-only; never shows the other role."""
    import liveness
    try:
        out = liveness.own_status(args.token)
    except (ValueError, PermissionError) as e:
        payload = {"schema": liveness.PARTICIPANT_SCHEMA,
                   "wake_reason": "error", "error": liveness.redact(e)}
        _render_participant(payload, args.json)
        sys.exit(1)
    if args.json:
        print(json.dumps(out, sort_keys=True, separators=(",", ":")))
    else:
        print(f"  Loop: {out['loop_id']}")
        print(f"  Role: {out['role']}")
        print(f"  Watcher: {out['state']}")
        if out.get("available"):
            print(f"  Pending notifications: {out['pending']}")
            last = out.get("last_notification")
            if last:
                ack = last.get("acked_at") or "not acknowledged"
                print(f"  Last notification: {last['kind']} "
                      f"(created {last['created_at']}; acknowledged: {ack})")
    sys.exit(0)


def _cmd_participant(args):
    handlers = {"watch": _cmd_participant_watch,
                "status": _cmd_participant_status}
    handler = handlers.get(getattr(args, "participant_command", None))
    if handler is None:
        print("  Usage: gator loop participant {watch,status} --token <token>",
              file=sys.stderr)
        sys.exit(1)
    handler(args)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="gator loop",
        description="Governed planning loop between AI models",
    )
    sub = parser.add_subparsers(dest="subcommand")

    # start
    p_start = sub.add_parser("start", help="Initialize a new planning or coding loop")
    p_start.add_argument("--feature", required=True, help="Feature slug")
    p_start.add_argument("--sketch", default=None,
                         help="Path to sketch file (planning loops; required)")
    p_start.add_argument("--mode", choices=["planning", "coding"], default="planning",
                         help="Loop mode (default: planning). A coding loop is a "
                              "guarded successor of an approved planning loop")
    p_start.add_argument("--from-loop", dest="from_loop", default=None,
                         help="Approved planning loop id to implement (coding loops; required)")
    p_start.add_argument("--brief", default=None,
                         help="Optional Architect brief (Markdown, UTF-8, <= 32 KiB); "
                              "stored immutably as architect-brief.md (#43)")
    p_start.add_argument("--source-brief", dest="source_brief",
                         choices=["keep", "drop"], default=None,
                         help="Coding loops: carry the approved plan's Architect brief "
                              "forward (keep, default) or start without it (drop)")
    p_start.add_argument("--max-rounds", type=int, default=3, help="Max revision rounds (default: 3)")
    p_start.add_argument(
        "--attention-interval", "--turn-timeout", dest="turn_timeout",
        type=int, default=300,
        help="Architect attention interval in seconds (default: 300). After it "
             "passes, the Architect gets one notice per turn; participants never "
             "see it and the loop keeps running. --turn-timeout is an accepted alias")

    # status
    p_status = sub.add_parser("status", help="Show role-scoped loop status")
    p_status.add_argument("--token", required=True, help="Role token")
    p_status.add_argument("--json", action="store_true", help="JSON output")

    # submit-draft
    p_draft = sub.add_parser("submit-draft", help="Submit a plan draft")
    p_draft.add_argument("--token", required=True, help="Draftor role token")
    p_draft.add_argument("--file", required=True, help="Path to plan file")

    # submit-implementation (coding, #41)
    p_impl = sub.add_parser(
        "submit-implementation",
        help="Submit the staged candidate and implementation artifact (coding loops)")
    p_impl.add_argument("--token", required=True, help="Draftor token")
    p_impl.add_argument("--file", required=True, help="Path to the implementation artifact")

    # submit-review
    p_review = sub.add_parser("submit-review", help="Submit review findings or approve")
    p_review.add_argument("--token", required=True, help="Reviewer role token")
    p_review.add_argument("--file", required=True, help="Path to findings file")
    p_review.add_argument("--approve", action="store_true", help="Approve the plan (no findings)")

    # escalate
    p_esc = sub.add_parser("escalate", help="Escalate to Architect")
    p_esc.add_argument("--token", required=True, help="Role token")
    p_esc.add_argument("--reason", required=True, help="Escalation reason")
    p_esc.add_argument("--file", help="Path to decision-request document (optional)")

    # pause (Architect)
    p_pause = sub.add_parser("pause", help="Pause a running loop (Architect)")
    p_pause.add_argument("--token", required=True, help="Architect token")
    p_pause.add_argument("--message", help="Message to models (shown in their status)")

    # interject (Architect)
    p_interject = sub.add_parser("interject", help="Send guidance without pausing (Architect)")
    p_interject.add_argument("--token", required=True, help="Architect token")
    p_interject.add_argument("--message", required=True, help="Guidance message")

    # end (Architect)
    p_end = sub.add_parser("end", help="Terminate the loop (Architect)")
    p_end.add_argument("--token", required=True, help="Architect token")
    p_end.add_argument("--reason", help="Reason for ending")

    # unblock (Architect)
    p_unblock = sub.add_parser("unblock", help="Resume a paused loop (Architect)")
    p_unblock.add_argument("--token", required=True, help="Architect token")
    p_unblock.add_argument("--next-role", choices=["draftor", "reviewer"], help="Override resume role")
    p_unblock.add_argument("--stage", choices=["plan_drafting", "plan_review", "plan_revision"], help="Override resume stage")
    p_unblock.add_argument("--message", help="Message to the resuming model (shown in their status). "
                           "Required (or --file / --no-response) when resolving an escalation")
    p_unblock.add_argument("--file", help="Path to a decision-response artifact")
    p_unblock.add_argument(
        "--timeout", type=_turn_timeout_arg, default=None,
        help="Legacy loops only: new turn window in seconds (30-3600) for this "
             "and all later turns. Refused for attention-interval loops (#47)",
    )
    p_unblock.add_argument(
        "--no-response", action="store_true",
        help="Exceptional: resolve a pending escalation deliberately without a written "
             "response (recorded as a deliberate empty response). "
             "Mutually exclusive with --message and --file",
    )

    # extend (Architect, #39)
    p_extend = sub.add_parser(
        "extend", help="Continue a loop that ended at its round limit (Architect)")
    p_extend.add_argument("--token", required=True, help="Architect token")
    p_extend.add_argument(
        "--rounds", required=True, type=_round_count_arg,
        help="Additional rounds (1-20) added to the current ceiling; history is not renumbered")
    p_extend.add_argument(
        "--message", required=True,
        help="Required reason for continuing; shown to the resumed Draftor")

    # reopen (Architect, #41)
    p_reopen = sub.add_parser(
        "reopen", help="Reopen an approved coding loop for revision (Architect)")
    p_reopen.add_argument("--token", required=True, help="Architect token")
    p_reopen.add_argument(
        "--message", required=True,
        help="Required reason for reopening; shown to the resumed Draftor")

    # wait
    p_wait = sub.add_parser("wait", help="Block until it is your turn")
    p_wait.add_argument("--token", required=True, help="Role token")
    p_wait.add_argument("--poll", type=float, default=2.0, help="Poll interval in seconds (default: 2.0)")
    p_wait.add_argument(
        "--max-seconds", type=_positive_seconds, default=None,
        help="Return after this many seconds if still not your turn "
             "(exit 3, reissue the same command). Omit to wait indefinitely.",
    )
    p_wait.add_argument("--json", action="store_true", help="JSON output with wake_reason")

    # participant (liveness bridge, #36)
    p_part = sub.add_parser(
        "participant",
        help="Participant liveness: background watcher and own status")
    part_sub = p_part.add_subparsers(dest="participant_command")
    p_pwatch = part_sub.add_parser(
        "watch",
        help="Register a receiver and exit on the first notification "
             "(run under a background-process supervisor)")
    p_pwatch.add_argument("--token", required=True, help="Draftor or Reviewer token")
    p_pwatch.add_argument(
        "--max-seconds", type=_positive_seconds, required=True,
        help="Exit 3 (still waiting) after this many seconds; relaunch to keep waiting")
    p_pwatch.add_argument(
        "--poll-seconds", type=_positive_seconds, default=5.0,
        help="Poll/heartbeat interval in seconds (default: 5)")
    p_pwatch.add_argument("--adapter-label", default=None,
                          help="Optional short label shown to the Architect (max 40 chars)")
    p_pwatch.add_argument("--json", action="store_true",
                          help="Print exactly one JSON line (adapter contract)")
    p_pstatus = part_sub.add_parser("status", help="Show your own role's watcher status")
    p_pstatus.add_argument("--token", required=True, help="Draftor or Reviewer token")
    p_pstatus.add_argument("--json", action="store_true", help="JSON output")

    # tail
    p_tail = sub.add_parser("tail", help="Follow loop events in real time")
    p_tail.add_argument("--loop", required=True, help="Loop ID")

    # list
    p_list = sub.add_parser("list", help="List all loop sessions")
    p_list.add_argument("--json", action="store_true", help="JSON output")

    args = parser.parse_args(argv)

    if not args.subcommand:
        parser.print_help()
        sys.exit(0)

    dispatch = {
        "start": _cmd_start,
        "status": _cmd_status,
        "submit-draft": _cmd_submit_draft,
        "submit-implementation": _cmd_submit_implementation,
        "submit-review": _cmd_submit_review,
        "escalate": _cmd_escalate,
        "pause": _cmd_pause,
        "interject": _cmd_interject,
        "end": _cmd_end,
        "unblock": _cmd_unblock,
        "extend": _cmd_extend,
        "reopen": _cmd_reopen,
        "wait": _cmd_wait,
        "participant": _cmd_participant,
        "tail": _cmd_tail,
        "list": _cmd_list,
    }

    handler = dispatch.get(args.subcommand)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(1)
