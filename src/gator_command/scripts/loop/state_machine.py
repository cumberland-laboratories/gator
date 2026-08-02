"""
State machine for gator loop.

Owns: state categorization, action validation, and all state transitions.
The session dict is mutated in place by advance_* functions — callers are
responsible for persisting via save_session() inside a session lock.

States fall into three categories:
  Active  — a role is expected to submit, timeout enforcement is live
  Paused  — loop suspended awaiting Architect intervention
  Terminal — loop is over, host exits, residue remains
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

_LOOP_DIR = str(Path(__file__).resolve().parent)
if _LOOP_DIR not in sys.path:
    sys.path.insert(0, _LOOP_DIR)

from session import _deadline_from_now


# ---------------------------------------------------------------------------
# State sets
# ---------------------------------------------------------------------------

ACTIVE_STAGES = frozenset({"plan_drafting", "plan_review", "plan_revision"})
PAUSED_STAGES = frozenset({"blocked_on_architect", "paused_by_architect"})
TERMINAL_STAGES = frozenset({"plan_approved", "max_rounds_exceeded", "turn_timed_out", "ended_by_architect"})
ALL_STAGES = ACTIVE_STAGES | PAUSED_STAGES | TERMINAL_STAGES


# ---------------------------------------------------------------------------
# State categorization
# ---------------------------------------------------------------------------

def is_active(session):
    """True when a role is expected to submit and timeouts are enforced."""
    return session["status"]["stage"] in ACTIVE_STAGES


def is_paused(session):
    """True when the loop is suspended awaiting Architect intervention."""
    return session["status"]["stage"] in PAUSED_STAGES


def is_terminal(session):
    """True when the loop is over."""
    return session["status"]["stage"] in TERMINAL_STAGES


# ---------------------------------------------------------------------------
# Action validation
# ---------------------------------------------------------------------------

# Maps action names to (required_role, valid_source_stages)
# required_role: specific role string, or None for "any model role"
_MODEL_ACTION_RULES = {
    "submit_draft": ("draftor", {"plan_drafting", "plan_revision"}),
    "submit_review": ("reviewer", {"plan_review"}),
    "escalate": (None, ACTIVE_STAGES),  # any model role, any active state
}

# Architect actions — require role == "architect"
_ARCHITECT_ACTIONS = frozenset({"pause", "interject", "end", "unblock"})

# Model roles — used to reject architect from model commands
_MODEL_ROLES = frozenset({"draftor", "reviewer"})


def validate_action(session, role, action):
    """Check whether a role can perform an action in the current state.

    Returns (allowed: bool, reason: str). When allowed is False, reason
    explains why.
    """
    stage = session["status"]["stage"]

    # --- Architect actions ---
    if action in _ARCHITECT_ACTIONS:
        if role != "architect":
            return False, f"Action '{action}' requires the architect token"
        return _validate_architect_action(session, action)

    # --- Model actions ---
    # Reject architect role from model commands
    if role == "architect":
        return False, f"Architect cannot perform model action '{action}'"

    # Terminal check
    if is_terminal(session):
        return False, f"Loop has ended ({stage})"

    # Blocked check
    if session["status"].get("blocked", False):
        return False, f"Loop is blocked ({stage}) — waiting for Architect"

    # Action-specific rules
    if action not in _MODEL_ACTION_RULES:
        return False, f"Unknown action: {action}"

    required_role, valid_stages = _MODEL_ACTION_RULES[action]

    # Role check (escalate allows any model role)
    if required_role and role != required_role:
        return False, f"Action '{action}' requires role '{required_role}', got '{role}'"

    # Stage check
    if stage not in valid_stages:
        return False, f"Action '{action}' not valid in stage '{stage}'"

    # Turn check — must be this role's turn (escalate bypasses this;
    # the plan says any role can escalate from any active state)
    if action != "escalate":
        next_role = session["status"].get("next_role")
        if next_role and next_role != role:
            return False, f"Not your turn — waiting for '{next_role}'"

    return True, "ok"


def _validate_architect_action(session, action):
    """Validate an Architect-only action against current state."""
    stage = session["status"]["stage"]

    if action == "pause":
        if not is_active(session):
            return False, f"Cannot pause — loop is not active (stage: {stage})"
        return True, "ok"

    if action == "interject":
        if not is_active(session):
            return False, f"Cannot interject — loop is not active (stage: {stage})"
        return True, "ok"

    if action == "end":
        if is_terminal(session):
            return False, f"Loop has already ended ({stage})"
        return True, "ok"

    if action == "unblock":
        if stage not in PAUSED_STAGES:
            return False, f"Loop is not paused (current stage: {stage})"
        return True, "ok"

    return False, f"Unknown architect action: {action}"


def validate_unblock(session):
    """Check whether unblock is valid. Kept for backward compatibility.

    Returns (allowed: bool, reason: str).
    """
    stage = session["status"]["stage"]
    if stage not in PAUSED_STAGES:
        return False, f"Loop is not paused (current stage: {stage})"
    return True, "ok"


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------

def advance_draft_submitted(session, turn_timeout):
    """Transition after draftor submits a plan.

    plan_drafting → plan_review
    plan_revision → plan_review
    """
    status = session["status"]
    status["stage"] = "plan_review"
    status["next_role"] = "reviewer"
    status["plan_status"] = "in_review"
    status["architect_message"] = None  # clear after model acts on it
    status["turn_deadline"] = _deadline_from_now(turn_timeout)
    status["last_updated"] = datetime.now(tz=timezone.utc).isoformat()
    return session


def advance_review_submitted(session, approved, findings_count, turn_timeout):
    """Transition after reviewer submits findings or approves.

    If approved: plan_review → plan_approved (terminal)
    If findings:
      - Increment round
      - If round >= max_rounds: → max_rounds_exceeded (terminal)
      - Else: plan_review → plan_revision (next_role=draftor)
    """
    status = session["status"]

    if approved:
        status["stage"] = "plan_approved"
        status["next_role"] = None
        status["plan_status"] = "approved"
        status["unresolved_findings"] = 0
        status["architect_message"] = None
        status["turn_deadline"] = None
        status["blocked"] = False
        status["last_updated"] = datetime.now(tz=timezone.utc).isoformat()
        return session

    # Findings submitted — advance round
    status["round"] += 1
    status["unresolved_findings"] = findings_count

    if status["round"] >= status["max_rounds"]:
        status["stage"] = "max_rounds_exceeded"
        status["next_role"] = None
        status["plan_status"] = "max_rounds"
        status["architect_message"] = None
        status["turn_deadline"] = None
        status["blocked"] = True
        status["last_updated"] = datetime.now(tz=timezone.utc).isoformat()
        return session

    # More rounds available — back to draftor
    status["stage"] = "plan_revision"
    status["next_role"] = "draftor"
    status["plan_status"] = "revision"
    status["architect_message"] = None
    status["turn_deadline"] = _deadline_from_now(turn_timeout)
    status["last_updated"] = datetime.now(tz=timezone.utc).isoformat()
    return session


def advance_escalated(session, reason):
    """Transition to blocked_on_architect from any active state.

    Saves resume_stage and resume_next_role so unblock can restore.
    """
    status = session["status"]
    status["resume_stage"] = status["stage"]
    status["resume_next_role"] = status["next_role"]
    status["stage"] = "blocked_on_architect"
    status["next_role"] = None
    status["architect_action_required"] = True
    status["blocked"] = True
    status["turn_deadline"] = None
    status["last_updated"] = datetime.now(tz=timezone.utc).isoformat()
    return session


def advance_unblocked(session, stage=None, next_role=None, turn_timeout=300, message=None):
    """Transition from blocked_on_architect back to an active state.

    Defaults to resume_stage/resume_next_role saved at escalation time.
    Architect can override with explicit stage/next_role arguments.
    Optional message is stored for the resuming model to read via status.
    """
    status = session["status"]

    target_stage = stage or status.get("resume_stage")
    target_role = next_role or status.get("resume_next_role")

    if not target_stage or target_stage not in ACTIVE_STAGES:
        raise ValueError(
            f"Cannot unblock to stage '{target_stage}' — "
            f"must be one of {sorted(ACTIVE_STAGES)}"
        )

    # Validate stage-role consistency: the plan's state machine assigns
    # each active stage to exactly one role.
    _STAGE_OWNER = {
        "plan_drafting": "draftor",
        "plan_review": "reviewer",
        "plan_revision": "draftor",
    }
    expected_role = _STAGE_OWNER[target_stage]
    if target_role and target_role != expected_role:
        raise ValueError(
            f"Stage '{target_stage}' belongs to '{expected_role}', "
            f"not '{target_role}'"
        )

    status["stage"] = target_stage
    status["next_role"] = target_role
    status["architect_action_required"] = False
    status["blocked"] = False
    status["architect_message"] = message
    status["resume_stage"] = None
    status["resume_next_role"] = None
    status["turn_deadline"] = _deadline_from_now(turn_timeout)
    status["last_updated"] = datetime.now(tz=timezone.utc).isoformat()
    return session


def advance_turn_timed_out(session, timed_out_role):
    """Transition to turn_timed_out terminal state.

    Called by the host's timeout enforcer when the active role does not
    submit within the deadline.
    """
    status = session["status"]
    status["stage"] = "turn_timed_out"
    status["next_role"] = None
    status["blocked"] = True
    status["turn_deadline"] = None
    status["last_updated"] = datetime.now(tz=timezone.utc).isoformat()
    return session


def advance_paused_by_architect(session, message=None):
    """Transition to paused_by_architect from any active state.

    Architect-initiated pause. Saves resume state like escalation.
    """
    status = session["status"]
    status["resume_stage"] = status["stage"]
    status["resume_next_role"] = status["next_role"]
    status["stage"] = "paused_by_architect"
    status["next_role"] = None
    status["blocked"] = True
    status["architect_message"] = message
    status["turn_deadline"] = None
    status["last_updated"] = datetime.now(tz=timezone.utc).isoformat()
    return session


def advance_interjected(session, message):
    """Store an Architect interjection without changing state.

    The message appears in the active model's next status check.
    No stage change, no deadline change.
    """
    status = session["status"]
    status["architect_message"] = message
    status["last_updated"] = datetime.now(tz=timezone.utc).isoformat()
    return session


def advance_ended_by_architect(session, reason=None):
    """Transition to ended_by_architect terminal state.

    Architect terminates the loop prematurely from any non-terminal state.
    """
    status = session["status"]
    status["stage"] = "ended_by_architect"
    status["next_role"] = None
    status["blocked"] = True
    status["turn_deadline"] = None
    if reason:
        status["end_reason"] = reason
    status["last_updated"] = datetime.now(tz=timezone.utc).isoformat()
    return session
