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

from session import _deadline_from_now, loop_mode, MODE_PLANNING, MODE_CODING


# ---------------------------------------------------------------------------
# State sets
# ---------------------------------------------------------------------------

# Planning-mode sets (unchanged; exported for backward compatibility).
ACTIVE_STAGES = frozenset({"plan_drafting", "plan_review", "plan_revision"})
PAUSED_STAGES = frozenset({"blocked_on_architect", "paused_by_architect"})
TERMINAL_STAGES = frozenset({"plan_approved", "max_rounds_exceeded", "turn_timed_out", "ended_by_architect"})

# Coding-mode sets (#41). Paused stages and the shared terminal outcomes
# (round limit, timeout, Architect end) are common to both modes.
CODING_ACTIVE_STAGES = frozenset({
    "implementation_drafting", "implementation_review",
    "implementation_revision",
})
CODING_TERMINAL_STAGES = frozenset({
    "implementation_approved", "max_rounds_exceeded", "turn_timed_out",
    "ended_by_architect",
})

# ALL_STAGES keeps its pre-#41 meaning: every PLANNING-mode stage (the set
# the participant protocol's state table documents and tests pin).
ALL_STAGES = ACTIVE_STAGES | PAUSED_STAGES | TERMINAL_STAGES
CODING_ALL_STAGES = CODING_ACTIVE_STAGES | PAUSED_STAGES | CODING_TERMINAL_STAGES
EVERY_STAGE = ALL_STAGES | CODING_ALL_STAGES

# The single mode-indexed stage table (#41). Every categorizer, the
# unblock stage/role check, and the extension target read it through
# stages_for(); planning entries are the pre-#41 values exactly.
STAGES = {
    MODE_PLANNING: {
        "active": ACTIVE_STAGES,
        "paused": PAUSED_STAGES,
        "terminal": TERMINAL_STAGES,
        "role_by_stage": {
            "plan_drafting": "draftor",
            "plan_review": "reviewer",
            "plan_revision": "draftor",
        },
        "initial_stage": "plan_drafting",
        "extension_resume_stage": "plan_revision",
    },
    MODE_CODING: {
        "active": CODING_ACTIVE_STAGES,
        "paused": PAUSED_STAGES,
        "terminal": CODING_TERMINAL_STAGES,
        "role_by_stage": {
            "implementation_drafting": "draftor",
            "implementation_review": "reviewer",
            "implementation_revision": "draftor",
        },
        "initial_stage": "implementation_drafting",
        "extension_resume_stage": "implementation_revision",
    },
}


def stages_for(session):
    """The stage table for this session's (normalized) loop mode."""
    return STAGES[loop_mode(session)]


# ---------------------------------------------------------------------------
# State categorization
# ---------------------------------------------------------------------------

def is_active(session):
    """True when a role is expected to submit and timeouts are enforced."""
    return session["status"]["stage"] in stages_for(session)["active"]


def is_paused(session):
    """True when the loop is suspended awaiting Architect intervention."""
    return session["status"]["stage"] in stages_for(session)["paused"]


def is_terminal(session):
    """True when the loop is over."""
    return session["status"]["stage"] in stages_for(session)["terminal"]


# ---------------------------------------------------------------------------
# Action validation
# ---------------------------------------------------------------------------

# Maps action names to (required_role, valid_source_stages), per mode.
# required_role: specific role string, or None for "any model role".
# A planning action is unknown in coding mode and vice versa.
_MODEL_ACTION_RULES_BY_MODE = {
    MODE_PLANNING: {
        "submit_draft": ("draftor", {"plan_drafting", "plan_revision"}),
        "submit_review": ("reviewer", {"plan_review"}),
        "escalate": (None, ACTIVE_STAGES),  # any model role, any active state
    },
    MODE_CODING: {
        "submit_implementation": (
            "draftor", {"implementation_drafting", "implementation_revision"}),
        "submit_review": ("reviewer", {"implementation_review"}),
        "escalate": (None, CODING_ACTIVE_STAGES),
    },
}
# Backward-compatible alias (planning rules).
_MODEL_ACTION_RULES = _MODEL_ACTION_RULES_BY_MODE[MODE_PLANNING]

# Architect actions — require role == "architect"
_ARCHITECT_ACTIONS = frozenset({"pause", "interject", "end", "unblock", "extend",
                                "reopen"})

# The only stage a coding loop may be reopened from (#41).
REOPENABLE_STAGE = "implementation_approved"

# The only terminal stage that may be resumed (via extend). Every other
# terminal stage is final.
EXTENDABLE_STAGE = "max_rounds_exceeded"

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

    # Action-specific rules (mode-indexed)
    mode = loop_mode(session)
    rules = _MODEL_ACTION_RULES_BY_MODE[mode]
    if action not in rules:
        if any(action in r for r in _MODEL_ACTION_RULES_BY_MODE.values()):
            return False, f"Action '{action}' is not valid in a {mode} loop"
        return False, f"Unknown action: {action}"

    required_role, valid_stages = rules[action]

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

    if action == "extend":
        if stage != EXTENDABLE_STAGE:
            return False, (
                "Only a loop that ended at its round limit can be extended "
                f"(stage: {stage})")
        return True, "ok"

    if action == "reopen":
        if loop_mode(session) != MODE_CODING:
            return False, "Only a coding loop can be reopened"
        if stage != REOPENABLE_STAGE:
            return False, (
                "Only an approved coding loop can be reopened "
                f"(stage: {stage})")
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
    status["architect_response_artifact"] = None
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
        status["architect_response_artifact"] = None
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
        status["architect_response_artifact"] = None
        status["turn_deadline"] = None
        status["blocked"] = True
        status["last_updated"] = datetime.now(tz=timezone.utc).isoformat()
        return session

    # More rounds available — back to draftor
    status["stage"] = "plan_revision"
    status["next_role"] = "draftor"
    status["plan_status"] = "revision"
    status["architect_message"] = None
    status["architect_response_artifact"] = None
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

    # Resume targets are validated against THIS session's mode table, so a
    # coding loop can never be unblocked into a planning stage (or v.v.).
    table = stages_for(session)
    if not target_stage or target_stage not in table["active"]:
        raise ValueError(
            f"Cannot unblock to stage '{target_stage}' — "
            f"must be one of {sorted(table['active'])}"
        )

    # Validate stage-role consistency: the state machine assigns each
    # active stage to exactly one role.
    expected_role = table["role_by_stage"][target_stage]
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


def advance_extended(session, rounds, turn_timeout, message=None):
    """Resume a loop that ended at its round limit.

    max_rounds_exceeded -> the mode's ``extension_resume_stage``
    (plan_revision for planning, implementation_revision for coding #41;
    next_role=draftor), with the round ceiling raised by ``rounds``. The round counter, current
    artifact references, turns, decisions, and unresolved findings are
    preserved — history is never renumbered or rewritten.

    ``rounds`` is an already-validated positive increment; the caller owns
    CLI/HTTP input policy. Returns (previous_max_rounds, new_max_rounds).
    Raises ValueError when the source state is not extendable.
    """
    status = session["status"]
    stage = status.get("stage")
    if stage != EXTENDABLE_STAGE:
        raise ValueError(
            "Only a loop that ended at its round limit can be extended "
            f"(stage: {stage})")
    if isinstance(rounds, bool) or not isinstance(rounds, int) or rounds < 1:
        raise ValueError(f"rounds must be a positive integer, got {rounds!r}")

    previous = status["max_rounds"]
    if status.get("round", 0) > previous:
        raise ValueError(
            f"Inconsistent session: round {status.get('round')} exceeds "
            f"max_rounds {previous}")

    # Mode-indexed resume target (#41): plan_revision for planning,
    # implementation_revision for coding; the owner comes from the table.
    table = stages_for(session)
    resume = table["extension_resume_stage"]
    status["max_rounds"] = previous + rounds
    status["stage"] = resume
    status["next_role"] = table["role_by_stage"][resume]
    status["plan_status"] = "revision"
    status["blocked"] = False
    status["architect_action_required"] = False
    status["architect_message"] = message
    status["architect_response_artifact"] = None
    status["resume_stage"] = None
    status["resume_next_role"] = None
    status["turn_deadline"] = _deadline_from_now(turn_timeout)
    status["last_updated"] = datetime.now(tz=timezone.utc).isoformat()
    return previous, status["max_rounds"]


def advance_implementation_submitted(session, turn_timeout):
    """Coding (#41): Draftor submitted a staged candidate.

    implementation_drafting / implementation_revision -> implementation_review
    (next_role=reviewer) with a fresh deadline. The candidate binding (the
    raw snapshot) is recorded by the caller as a new generation.
    """
    if loop_mode(session) != MODE_CODING:
        raise ValueError("Only a coding loop accepts implementation submissions")
    status = session["status"]
    if status.get("stage") not in ("implementation_drafting",
                                   "implementation_revision"):
        raise ValueError(
            "Implementation can only be submitted while drafting or revising "
            f"(stage: {status.get('stage')})")
    table = stages_for(session)
    status["stage"] = "implementation_review"
    status["next_role"] = table["role_by_stage"]["implementation_review"]
    status["plan_status"] = "in_review"
    status["architect_message"] = None  # clear after the model acts on it
    status["architect_response_artifact"] = None
    status["turn_deadline"] = _deadline_from_now(turn_timeout)
    status["last_updated"] = datetime.now(tz=timezone.utc).isoformat()
    return session


def advance_implementation_reviewed(session, approved, turn_timeout,
                                    approval=None):
    """Coding (#41): Reviewer verdict on the latest candidate generation.

    approved: implementation_review -> implementation_approved (terminal,
      resumable only via reopen); ``approval`` ({tree, head, round, ts}) is
      stored as ``coding.approval``.
    findings: round += 1; at the ceiling -> max_rounds_exceeded (terminal,
      extendable #39); otherwise -> implementation_revision (Draftor).
    """
    if loop_mode(session) != MODE_CODING:
        raise ValueError("Only a coding loop accepts implementation reviews")
    status = session["status"]
    if status.get("stage") != "implementation_review":
        raise ValueError(
            f"No implementation is under review (stage: {status.get('stage')})")
    now = datetime.now(tz=timezone.utc).isoformat()
    table = stages_for(session)

    if approved:
        if not isinstance(approval, dict) or not approval.get("tree"):
            raise ValueError("An approval must bind the reviewed tree")
        session["coding"]["approval"] = dict(approval)
        status["stage"] = "implementation_approved"
        status["next_role"] = None
        status["plan_status"] = "approved"
        status["unresolved_findings"] = 0
        status["architect_message"] = None
        status["architect_response_artifact"] = None
        status["turn_deadline"] = None
        status["blocked"] = False
        status["last_updated"] = now
        return session

    status["round"] += 1
    status["unresolved_findings"] = 1
    status["architect_message"] = None
    status["architect_response_artifact"] = None
    status["last_updated"] = now
    if status["round"] >= status["max_rounds"]:
        status["stage"] = "max_rounds_exceeded"
        status["next_role"] = None
        status["plan_status"] = "max_rounds"
        status["turn_deadline"] = None
        status["blocked"] = True
        return session
    status["stage"] = "implementation_revision"
    status["next_role"] = table["role_by_stage"]["implementation_revision"]
    status["plan_status"] = "revision"
    status["turn_deadline"] = _deadline_from_now(turn_timeout)
    return session


# Approval resolution states (#41). Meaning is never encoded by these
# strings alone in a UI — callers pair them with explicit text.
APPROVAL_COMMITTED = "committed"
APPROVAL_PENDING = "pending"
APPROVAL_STALE = "stale"
APPROVAL_UNKNOWN = "unknown"
APPROVAL_NONE = "none"
APPROVAL_INVALIDATED = "invalidated"


def resolve_approval(approval, snap):
    """Pure: where does an approved candidate stand against live Git facts?

    - committed: HEAD moved and ``HEAD^{tree}`` equals the approved tree
      (the ordinary commit landed exactly the reviewed candidate).
    - pending: HEAD is still the approved HEAD and the staged tree is still
      the approved tree (return to the Draftor for one normal commit).
    - stale: anything else, with a reason — ``staged_tree_changed`` (HEAD
      unchanged, index differs), ``head_moved_tree_differs`` (a commit or
      branch move whose tree is not the approved tree, including a hook
      that changed committed content), or ``detached_mismatch``.
    - unknown: the snapshot failed; never treated as approved.
    - none / invalidated: no approval, or one invalidated by reopen.
    """
    base = {"approved_tree": None, "approved_head": None}
    if not isinstance(approval, dict) or not approval.get("tree"):
        return dict(base, state=APPROVAL_NONE, reason=None)
    base = {"approved_tree": approval.get("tree"),
            "approved_head": approval.get("head")}
    if approval.get("invalidated_at"):
        return dict(base, state=APPROVAL_INVALIDATED, reason="reopened")
    if not isinstance(snap, dict) or not snap.get("ok"):
        return dict(base, state=APPROVAL_UNKNOWN,
                    reason=(snap or {}).get("error") or "snapshot_failed")
    out = dict(base, current_head=snap.get("current_head"),
               head_tree=snap.get("head_tree"),
               staged_tree=snap.get("staged_tree"),
               detached=bool(snap.get("detached")))
    if snap.get("current_head") == approval.get("head"):
        if snap.get("staged_tree") == approval.get("tree"):
            return dict(out, state=APPROVAL_PENDING, reason=None)
        return dict(out, state=APPROVAL_STALE, reason="staged_tree_changed")
    if snap.get("head_tree") == approval.get("tree"):
        return dict(out, state=APPROVAL_COMMITTED, reason=None,
                    commit=snap.get("current_head"))
    reason = ("detached_mismatch" if snap.get("detached")
              else "head_moved_tree_differs")
    return dict(out, state=APPROVAL_STALE, reason=reason)


def advance_reopened(session, turn_timeout, message=None):
    """Reopen an approved coding loop for revision (#41).

    implementation_approved -> implementation_revision (next_role=draftor)
    with a fresh deadline. The round counter is kept (the next submission
    is round + 1) and any approval record is marked invalidated so a stale
    approval can never be read as current. Raises ValueError when the
    session is not a coding loop in ``implementation_approved``.
    """
    status = session["status"]
    if loop_mode(session) != MODE_CODING:
        raise ValueError("Only a coding loop can be reopened")
    if status.get("stage") != REOPENABLE_STAGE:
        raise ValueError(
            "Only an approved coding loop can be reopened "
            f"(stage: {status.get('stage')})")

    now = datetime.now(tz=timezone.utc).isoformat()
    approval = session.get("coding", {}).get("approval")
    if isinstance(approval, dict):
        approval["invalidated_at"] = now

    table = stages_for(session)
    status["stage"] = "implementation_revision"
    status["next_role"] = table["role_by_stage"]["implementation_revision"]
    status["plan_status"] = "revision"
    status["blocked"] = False
    status["architect_action_required"] = False
    status["architect_message"] = message
    status["architect_response_artifact"] = None
    status["resume_stage"] = None
    status["resume_next_role"] = None
    status["turn_deadline"] = _deadline_from_now(turn_timeout)
    status["last_updated"] = now
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
