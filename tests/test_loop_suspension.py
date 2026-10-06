"""
#53 — durable non-terminal suspension: state and resume integrity.

Pins the suspension contract owned by ``state_machine._suspend`` /
``_clear_suspension`` and the recipient-scoped Architect message:

- suspend -> unblock restores the exact stage and role in both modes and
  leaves no resume target, timestamp, or pause reason behind;
- a pause never writes the model-facing message; an unblock without a
  message never erases one; a decision response reaches the escalator and
  survives the other role's submission;
- end resolves a pending request as ``cancelled_by_end``;
- a legacy session paused before #53 unblocks exactly as before.
"""

import argparse
import contextlib
import io
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "src" / "gator_command" / "scripts"
LOOP_DIR = SCRIPTS_DIR / "loop"
for p in [str(SCRIPTS_DIR), str(LOOP_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import session as loop_session
import state_machine as loop_sm
import submit as loop_submit
import cli as loop_cli

from test_loop import loop_env  # noqa: F401  (shared fixture)

SUSPENSION_FIELDS = ("resume_stage", "resume_next_role", "suspended_at",
                     "pause_reason")


def _planning_session():
    return loop_session.create_session("f", "loop-f", max_rounds=3,
                                       turn_timeout=300)


def _coding_session():
    items = [{"id": f"cp{i}", "title": f"Part {i}", "scope": "s",
              "verify": "v"} for i in (1, 2)]
    manifest = loop_session.build_checkpoint_manifest(items, "declared",
                                                      "tree0")
    coding = {"source_loop_id": "src", "plan_sha256": "0" * 64,
              "base_head": "head0", "base_tree": "tree0", "generations": [],
              "approval": None, "checkpoints": manifest}
    return loop_session.create_session("f", "loop-f", max_rounds=3,
                                       turn_timeout=300, mode="coding",
                                       coding=coding)


def _at_owner(session, owner):
    """Move a fresh session to the given turn owner's active stage."""
    if owner == "reviewer":
        if loop_session.loop_mode(session) == "coding":
            loop_sm.advance_implementation_submitted(session, 300)
        else:
            loop_sm.advance_draft_submitted(session, 300)
    return session


def _suspend(session, kind):
    if kind == "pause":
        loop_sm.advance_paused_by_architect(session, message="Hold for review")
    else:
        loop_sm.advance_escalated(session, "Need a decision")


# ---------------------------------------------------------------------------
# 1. Transition table: suspend -> unblock restores exactly, no residue
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("make", [_planning_session, _coding_session],
                         ids=["planning", "coding-checkpoint"])
@pytest.mark.parametrize("kind", ["pause", "escalate"])
@pytest.mark.parametrize("owner", ["draftor", "reviewer"])
def test_suspend_then_unblock_restores_exactly(make, kind, owner):
    s = _at_owner(make(), owner)
    stage, role = s["status"]["stage"], s["status"]["next_role"]
    current = (s.get("coding") or {}).get("checkpoints", {}).get("current")

    _suspend(s, kind)
    st = s["status"]
    assert loop_sm.is_paused(s)
    assert st["next_role"] is None and st["blocked"] is True
    assert (st["resume_stage"], st["resume_next_role"]) == (stage, role)
    assert st["suspended_at"]
    assert st["pause_reason"] == ("Hold for review" if kind == "pause" else None)
    assert st["architect_message"] is None  # suspension never writes it

    loop_sm.advance_unblocked(s, turn_timeout=300)
    assert (st["stage"], st["next_role"]) == (stage, role)
    assert loop_sm.is_active(s) and st["blocked"] is False
    for field in SUSPENSION_FIELDS:
        assert st[field] is None, field
    if current is not None:  # pause/unblock keep the active checkpoint
        assert s["coding"]["checkpoints"]["current"] == current


def test_suspend_requires_active_loop():
    s = _planning_session()
    loop_sm.advance_paused_by_architect(s)
    with pytest.raises(ValueError):
        loop_sm.advance_escalated(s, "nested")
    assert s["status"]["resume_stage"] == "plan_drafting"  # not overwritten


# ---------------------------------------------------------------------------
# 2. Mixed sequence through the real handlers
# ---------------------------------------------------------------------------

def _status_text(token):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        with pytest.raises(SystemExit):
            loop_cli._cmd_status(argparse.Namespace(token=token, json=False))
    return out.getvalue()


def _load(e):
    return loop_session.load_session(e["loop_dir"])


def test_mixed_sequence_keeps_messages_and_targets(loop_env):  # noqa: F811
    e = loop_env
    arch = e["architect_token"]

    # An interjection survives a pause and a message-less unblock.
    loop_submit.handle_interject(arch, "Mind the lock order.")
    loop_submit.handle_pause(arch, message="Lunch")
    loop_submit.handle_unblock(arch)
    s = _load(e)
    assert loop_cli._message_for_role(s, "draftor")[0] == "Mind the lock order."
    assert all(s["status"].get(f) is None for f in SUSPENSION_FIELDS)

    # The reviewer escalates during the Draftor's turn; the multiline
    # response is addressed to the reviewer, not the resumed Draftor.
    loop_submit.handle_escalate(e["reviewer_token"], "Is X in scope?")
    response = "X is in scope.\nKeep Y out."
    loop_submit.handle_unblock(arch, message=response)
    s = _load(e)
    assert s["status"]["next_role"] == "draftor"
    assert s["status"]["architect_message_for"] == "reviewer"
    assert loop_cli._message_for_role(s, "draftor") == (None, None, None)
    assert loop_cli._message_for_role(s, "reviewer") == (
        response, None, "decision-1")

    # The Draftor's submission does not consume the reviewer's response.
    loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
    s = _load(e)
    assert s["status"]["architect_message"] == response
    text = _status_text(e["reviewer_token"])
    assert "Architect response to your escalation: decision-1" in text
    assert "  Architect message: X is in scope.\n    Keep Y out.\n" in text

    # The reviewer's own submission consumes it.
    loop_submit.handle_submit_review(e["reviewer_token"],
                                     str(e["findings_file"]))
    s = _load(e)
    assert s["status"]["architect_message"] is None
    assert s["status"]["architect_message_for"] is None

    # Pause then end: no stale resume target survives.
    loop_submit.handle_pause(arch, message="Stop here")
    loop_submit.handle_end(arch, reason="Done for today")
    s = _load(e)
    assert s["status"]["stage"] == "ended_by_architect"
    assert all(s["status"].get(f) is None for f in SUSPENSION_FIELDS)


def test_later_pause_message_never_inherits_decision_label(loop_env):  # noqa: F811
    """A decision label belongs to the response message itself: after an
    escalation is resolved, a later pause/unblock message is not labelled
    as that decision's response."""
    e = loop_env
    arch = e["architect_token"]
    loop_submit.handle_escalate(e["draftor_token"], "Which API?")
    loop_submit.handle_unblock(arch, message="Use v2.")
    s = _load(e)
    assert loop_cli._message_for_role(s, "draftor") == ("Use v2.", None,
                                                       "decision-1")

    loop_submit.handle_pause(arch, message="Hold")
    loop_submit.handle_unblock(arch, message="Resume; also add tests.")
    s = _load(e)
    assert loop_cli._message_for_role(s, "draftor") == (
        "Resume; also add tests.", None, None)
    text = _status_text(e["draftor_token"])
    assert "Architect message: Resume; also add tests." in text
    assert "Architect response to your escalation" not in text


# ---------------------------------------------------------------------------
# 3. End while blocked resolves the request
# ---------------------------------------------------------------------------

def test_end_while_blocked_cancels_pending_decision(loop_env):  # noqa: F811
    e = loop_env
    loop_submit.handle_escalate(e["draftor_token"], "Which API?")
    loop_submit.handle_end(e["architect_token"], reason="Superseded by #60")
    s = _load(e)
    (decision,) = s["decisions"]
    assert decision["response"]["kind"] == loop_submit.CANCELLED_BY_END
    assert decision["response"]["message"] == "Superseded by #60"
    assert decision["response"]["ts"]
    assert all(s["status"].get(f) is None for f in SUSPENSION_FIELDS)
    import events as loop_events
    ended = [ev for ev in loop_events.read_all_events(e["loop_dir"])
             if ev["event"] == "loop_ended_by_architect"]
    assert ended[-1]["decision_id"] == "decision-1"


# ---------------------------------------------------------------------------
# 4. Legacy session paused before #53
# ---------------------------------------------------------------------------

def test_legacy_pause_unblocks_as_before():
    s = _planning_session()
    st = s["status"]
    # The pre-#53 pause shape: reason in architect_message, no suspended_at.
    st.update(resume_stage="plan_drafting", resume_next_role="draftor",
              stage="paused_by_architect", next_role=None, blocked=True,
              architect_message="old pause reason")
    st.pop("suspended_at", None)
    loop_sm.advance_unblocked(s, turn_timeout=300)
    assert (st["stage"], st["next_role"]) == ("plan_drafting", "draftor")
    assert st["architect_message"] is None  # old reason is not re-shown
    assert st["resume_stage"] is None and st["resume_next_role"] is None


# ---------------------------------------------------------------------------
# 5. Checkpoint 2: participants stay in the loop through suspension
# ---------------------------------------------------------------------------

def _run(fn, **kw):
    import json as _json
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        with pytest.raises(SystemExit) as exc:
            fn(argparse.Namespace(**kw))
    text = out.getvalue()
    return exc.value.code, (_json.loads(text) if kw.get("json") else text)


def _suspend_via(e, kind):
    if kind == "paused":
        loop_submit.handle_pause(e["architect_token"], message="Hold on")
    else:
        loop_submit.handle_escalate(e["draftor_token"], "Which API?")


@pytest.mark.parametrize("kind", ["paused", "blocked"])
def test_status_and_wait_keep_participant_in_loop(loop_env, kind):  # noqa: F811
    e = loop_env
    _suspend_via(e, kind)

    # status: exit 1 (keep waiting), never 2; additive suspension JSON.
    code, out = _run(loop_cli._cmd_status, token=e["draftor_token"], json=True)
    assert code == 1
    sus = out["suspension"]
    assert sus["kind"] == ("architect_hold" if kind == "paused"
                           else "architect_decision")
    assert (sus["resume_stage"], sus["resume_role"]) == ("plan_drafting",
                                                         "draftor")
    assert sus["since"]
    if kind == "paused":
        assert sus["reason"] == "Hold on" and sus["decision_id"] is None
    else:
        assert sus["decision_id"] == "decision-1"
        assert sus["requested_by"] == "draftor" and sus["reason"] is None
    code, text = _run(loop_cli._cmd_status, token=e["draftor_token"],
                      json=False)
    assert code == 1
    assert "You are still a loop participant" in text
    assert "--max-seconds 45" in text

    # bounded wait: still_waiting (3) through the suspension, never 2.
    code, out = _run(loop_cli._cmd_wait, token=e["reviewer_token"], json=True,
                     max_seconds=0.2, poll=0.05)
    assert code == loop_cli.WAIT_EXIT_STILL_WAITING
    assert out["wake_reason"] == "still_waiting"
    assert out["suspension"]["kind"] == sus["kind"]

    # unblock: the resumed role wakes at once (0); end: wait exits 2.
    kw = {"message": "Use v2."} if kind == "blocked" else {}
    loop_submit.handle_unblock(e["architect_token"], **kw)
    code, out = _run(loop_cli._cmd_wait, token=e["draftor_token"], json=True,
                     max_seconds=0.2, poll=0.05)
    assert code == 0 and out["suspension"] is None
    loop_submit.handle_end(e["architect_token"], reason="done")
    code, _ = _run(loop_cli._cmd_wait, token=e["reviewer_token"], json=True,
                   max_seconds=0.2, poll=0.05)
    assert code == 2
