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
    try:
        start_loop(
            feature=args.feature,
            sketch_path=args.sketch,
            max_rounds=args.max_rounds,
            turn_timeout=args.turn_timeout,
        )
    except FileNotFoundError as e:
        print(f"  Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
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
        }
        print(json.dumps(out, indent=2))
    else:
        print(f"  Loop: {loop_id}")
        print(f"  Dir: {loop_dir}")
        print(f"  Role: {role}")
        print(f"  Your turn: {'YES' if my_turn else 'NO'}")
        print(f"  Stage: {stage}")

        if is_terminal(session):
            _print_terminal_reason(session, role)
            print("  Loop ended.")
        elif is_paused(session):
            print("  Blocked -- waiting for Architect")
        elif my_turn:
            architect_msg = status.get("architect_message")
            if architect_msg:
                print(f"  Architect message: {architect_msg}")
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
            "draftor_joined": roles.get("draftor", {}).get("joined", False),
            "reviewer_joined": roles.get("reviewer", {}).get("joined", False),
            "turns": session.get("turns", []),
        }
        print(json.dumps(out, indent=2))
    else:
        print(f"  Loop: {loop_id}")
        print(f"  Dir: {loop_dir}")
        print(f"  Role: architect (supervisor)")
        print(f"  Stage: {stage}")

        if is_active(session):
            print(f"  Active role: {status.get('next_role', '?')}")
        elif is_paused(session):
            print(f"  Paused: {stage}")
        elif is_terminal(session):
            _print_terminal_reason(session, "architect")
            print("  Loop ended.")

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
            print()
            print("  Commands:")
            print(f"    gator loop unblock --token {args.token} --message \"...\"")
            print(f"    gator loop end --token {args.token} --reason \"...\"")

    # Architect exit codes: 0 = active (can act), 2 = paused/terminal
    if is_terminal(session) or is_paused(session):
        sys.exit(2)
    else:
        sys.exit(0)


def _print_action_prompt(session, role, loop_dir, token):
    """Print the action hint and next-step command for the active role."""
    stage = session["status"]["stage"]

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


def _print_terminal_reason(session, role):
    """Print why the loop ended."""
    stage = session["status"]["stage"]
    if stage == "plan_approved":
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
        if args.approve:
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
        loop_id, role, loop_dir = handle_escalate(args.token, args.reason)
        print(f"  Escalated. Loop blocked -- waiting for Architect.")
        print(f"  Loop: {loop_id}")
    except ValueError as e:
        print(f"  Error: {e}", file=sys.stderr)
        sys.exit(1)
    except PermissionError as e:
        print(f"  Rejected: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_unblock(args):
    from submit import handle_unblock
    try:
        loop_id, loop_dir = handle_unblock(
            args.token, next_role=args.next_role, stage=args.stage,
            message=args.message
        )
        from session import load_session
        session = load_session(loop_dir)
        stage = session["status"]["stage"]
        next_role = session["status"]["next_role"]
        print(f"  Unblocked. Resumed to {stage} (next: {next_role}).")
        print(f"  Loop: {loop_id}")
    except (FileNotFoundError, ValueError) as e:
        print(f"  Error: {e}", file=sys.stderr)
        sys.exit(1)
    except PermissionError as e:
        print(f"  Rejected: {e}", file=sys.stderr)
        sys.exit(1)


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


def _cmd_wait(args):
    """Block until the loop becomes actionable for this role."""
    import time as _time
    from session import resolve_token, load_session
    from state_machine import is_terminal, is_paused

    try:
        loop_id, role, loop_dir = resolve_token(args.token)
    except ValueError as e:
        print(f"  Error: {e}", file=sys.stderr)
        sys.exit(2)

    if role == "architect":
        print("  Error: wait is for model roles only. Use status for the architect view.", file=sys.stderr)
        sys.exit(1)

    poll = getattr(args, "poll", 2.0)
    session, wake_reason = _wait_for_actionable(
        loop_dir, role, poll, load_session, is_terminal, is_paused
    )

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
            "wake_reason": wake_reason,
        }
        print(json.dumps(out, indent=2))
    else:
        print(f"  Loop: {loop_id}")
        print(f"  Dir: {loop_dir}")
        print(f"  Role: {role}")
        print(f"  Your turn: {'YES' if my_turn else 'NO'}")
        print(f"  Stage: {stage}")

        if is_terminal(session):
            _print_terminal_reason(session, role)
            print("  Loop ended.")
        elif is_paused(session):
            print("  Blocked -- waiting for Architect")
        elif my_turn:
            architect_msg = status.get("architect_message")
            if architect_msg:
                print(f"  Architect message: {architect_msg}")
            _print_action_prompt(session, role, loop_dir, args.token)

        print(f"  Round: {rnd}/{max_rnd}")

    # Exit codes: 0 = your turn, 2 = paused/terminal
    if is_terminal(session) or is_paused(session):
        sys.exit(2)
    else:
        sys.exit(0)


def _wait_for_actionable(loop_dir, role, poll_interval, load_session, is_terminal, is_paused):
    """Poll session.json until the loop becomes actionable for this role.

    Returns (session, wake_reason). Read-only — never writes any file.
    """
    import time as _time

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
        _time.sleep(poll_interval)
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

def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="gator loop",
        description="Governed planning loop between AI models",
    )
    sub = parser.add_subparsers(dest="subcommand")

    # start
    p_start = sub.add_parser("start", help="Initialize a new planning loop")
    p_start.add_argument("--feature", required=True, help="Feature slug")
    p_start.add_argument("--sketch", required=True, help="Path to sketch file")
    p_start.add_argument("--max-rounds", type=int, default=3, help="Max revision rounds (default: 3)")
    p_start.add_argument("--turn-timeout", type=int, default=300, help="Turn timeout in seconds (default: 300)")

    # status
    p_status = sub.add_parser("status", help="Show role-scoped loop status")
    p_status.add_argument("--token", required=True, help="Role token")
    p_status.add_argument("--json", action="store_true", help="JSON output")

    # submit-draft
    p_draft = sub.add_parser("submit-draft", help="Submit a plan draft")
    p_draft.add_argument("--token", required=True, help="Draftor role token")
    p_draft.add_argument("--file", required=True, help="Path to plan file")

    # submit-review
    p_review = sub.add_parser("submit-review", help="Submit review findings or approve")
    p_review.add_argument("--token", required=True, help="Reviewer role token")
    p_review.add_argument("--file", required=True, help="Path to findings file")
    p_review.add_argument("--approve", action="store_true", help="Approve the plan (no findings)")

    # escalate
    p_esc = sub.add_parser("escalate", help="Escalate to Architect")
    p_esc.add_argument("--token", required=True, help="Role token")
    p_esc.add_argument("--reason", required=True, help="Escalation reason")

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
    p_unblock.add_argument("--message", help="Message to the resuming model (shown in their status)")

    # wait
    p_wait = sub.add_parser("wait", help="Block until it is your turn")
    p_wait.add_argument("--token", required=True, help="Role token")
    p_wait.add_argument("--poll", type=float, default=2.0, help="Poll interval in seconds (default: 2.0)")
    p_wait.add_argument("--json", action="store_true", help="JSON output with wake_reason")

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
        "submit-review": _cmd_submit_review,
        "escalate": _cmd_escalate,
        "pause": _cmd_pause,
        "interject": _cmd_interject,
        "end": _cmd_end,
        "unblock": _cmd_unblock,
        "wait": _cmd_wait,
        "tail": _cmd_tail,
        "list": _cmd_list,
    }

    handler = dispatch.get(args.subcommand)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(1)
