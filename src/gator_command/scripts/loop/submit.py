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
    resolve_token, with_session_lock, append_turn,
    find_gator_root, _make_writable, _make_readonly,
)
from state_machine import (
    validate_action, validate_unblock,
    advance_draft_submitted, advance_review_submitted,
    advance_escalated, advance_unblocked,
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
# Submit handlers
# ---------------------------------------------------------------------------

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

    def _submit(session):
        # Validate inside lock (session may have changed)
        allowed, reason = validate_action(session, role, "submit_draft")
        if not allowed:
            raise PermissionError(reason)

        # Copy artifact — round-versioned first, then current
        round_num = session["status"]["round"]
        versioned_name = f"plan.round-{round_num}.md"
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
            "detail": f"Plan draft submitted, advancing to plan_review",
        }
        return session, event

    with_session_lock(loop_dir, _submit)

    return loop_id, role, loop_dir


def handle_submit_review(token, file_path, approve=False):
    """Process a reviewer submission (findings or approval).

    Resolves token, validates role and turn, copies findings to
    findings.current.md, advances state based on --approve flag.
    """
    source = Path(file_path)
    if not source.exists():
        raise FileNotFoundError(f"Review file not found: {file_path}")
    if source.stat().st_size == 0:
        raise ValueError(f"Review file is empty: {file_path}")

    loop_id, role, loop_dir = resolve_token(token)

    def _submit(session):
        allowed, reason = validate_action(session, role, "submit_review")
        if not allowed:
            raise PermissionError(reason)

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
                "detail": "Reviewer approved the plan",
            }
        elif session["status"]["stage"] == "max_rounds_exceeded":
            event = {
                "event": "max_rounds_exceeded",
                "role": role,
                "round": session["status"]["round"],
                "detail": f"Round limit reached ({session['status']['max_rounds']})",
            }
        else:
            event = {
                "event": "revision_requested",
                "role": role,
                "round": session["status"]["round"],
                "detail": "Findings submitted, revision requested",
            }
        return session, event

    with_session_lock(loop_dir, _submit)

    return loop_id, role, loop_dir


def handle_escalate(token, reason):
    """Escalate to blocked_on_architect from any active state.

    Either role can escalate when it's their turn.
    """
    if not reason or not reason.strip():
        raise ValueError("Escalation reason is required")

    loop_id, role, loop_dir = resolve_token(token)

    def _escalate(session):
        allowed, msg = validate_action(session, role, "escalate")
        if not allowed:
            raise PermissionError(msg)

        # Track turn
        append_turn(
            session, role, "escalation",
            f"Escalated: {reason}"
        )

        # Advance state
        advance_escalated(session, reason)

        event = {
            "event": "escalated",
            "role": role,
            "round": session["status"]["round"],
            "detail": reason,
        }
        return session, event

    with_session_lock(loop_dir, _escalate)

    return loop_id, role, loop_dir


def handle_unblock(token, next_role=None, stage=None, message=None):
    """Architect command: unblock a paused loop.

    Requires architect token. Both next_role and stage are optional;
    defaults come from the resume state saved at escalation/pause time.
    Optional message is stored in session and shown in the resuming
    model's status output.
    """
    loop_id, role, loop_dir = resolve_token(token)
    if role != "architect":
        raise PermissionError("Unblock requires the architect token")

    def _unblock(session):
        allowed, reason = validate_unblock(session)
        if not allowed:
            raise PermissionError(reason)

        timeout = session["status"]["turn_timeout_seconds"]
        advance_unblocked(session, stage=stage, next_role=next_role,
                          turn_timeout=timeout, message=message)

        # Record architect turn
        append_turn(session, "architect", "unblock",
                    message or "Loop unblocked")

        detail = (f"Resumed to {session['status']['stage']} "
                  f"(next: {session['status']['next_role']})")
        if message:
            detail += f" -- Architect: {message}"
        event = {
            "event": "loop_unblocked",
            "role": "architect",
            "round": session["status"]["round"],
            "detail": detail,
        }
        return session, event

    with_session_lock(loop_dir, _unblock)

    return loop_id, loop_dir


def handle_pause(token, message=None):
    """Architect command: pause a running loop.

    Requires architect token. Transitions to paused_by_architect.
    """
    loop_id, role, loop_dir = resolve_token(token)
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


def handle_interject(token, message):
    """Architect command: inject guidance without pausing.

    Requires architect token. Stores message in session, emits event,
    but does not change stage or deadline.
    """
    if not message or not message.strip():
        raise ValueError("Interjection message is required")

    loop_id, role, loop_dir = resolve_token(token)
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


def handle_end(token, reason=None):
    """Architect command: terminate the loop prematurely.

    Requires architect token. Transitions to ended_by_architect.
    """
    loop_id, role, loop_dir = resolve_token(token)
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
