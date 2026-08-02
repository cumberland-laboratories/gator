"""
Tests for the gator loop subsystem.

Covers: token generation/resolution, session CRUD, state machine transitions,
submit handlers, event emission/formatting, CLI dispatch, and concurrency
safety (timeout-vs-submit race, write ordering).
"""

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Ensure loop package is importable
SCRIPTS_DIR = Path(__file__).parent.parent / "src" / "gator_command" / "scripts"
LOOP_DIR = SCRIPTS_DIR / "loop"
for p in [str(SCRIPTS_DIR), str(LOOP_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import session as loop_session
import events as loop_events
import state_machine as loop_sm
import submit as loop_submit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def loop_env(tmp_path, monkeypatch):
    """Set up a temporary loop environment with tokens.

    Returns a dict with loop_dir, loop_id, draftor_token, reviewer_token,
    and convenience paths for draft/findings files.
    """
    monkeypatch.setattr(loop_session, "find_gator_root", lambda start_path=None: tmp_path)
    monkeypatch.setattr(loop_submit, "find_gator_root", lambda start_path=None: tmp_path)

    loop_id = "test-feature-loop"
    loop_dir = tmp_path / ".gator" / "loops" / loop_id
    loop_dir.mkdir(parents=True)
    loop_session.ensure_loops_gitignore(loop_dir.parent)

    session = loop_session.create_session("test-feature", loop_id, max_rounds=3, turn_timeout=300)
    loop_session.save_session(loop_dir, session)
    loop_events.create_events_file(loop_dir)

    tok_d, nonce_d = loop_session.make_token(loop_id, "draftor")
    tok_r, nonce_r = loop_session.make_token(loop_id, "reviewer")
    tok_a, nonce_a = loop_session.make_token(loop_id, "architect")
    loop_session.save_tokens(loop_dir, {
        "draftor": {"nonce": nonce_d, "token": tok_d},
        "reviewer": {"nonce": nonce_r, "token": tok_r},
        "architect": {"nonce": nonce_a, "token": tok_a},
    })

    draft_file = tmp_path / "plan.md"
    draft_file.write_text("# Plan\n\nImplementation details.\n", encoding="utf-8")

    findings_file = tmp_path / "findings.md"
    findings_file.write_text("# Findings\n\n1. Fix error handling.\n", encoding="utf-8")

    return {
        "tmp": tmp_path,
        "loop_dir": loop_dir,
        "loop_id": loop_id,
        "draftor_token": tok_d,
        "reviewer_token": tok_r,
        "architect_token": tok_a,
        "draft_file": draft_file,
        "findings_file": findings_file,
    }


# ===========================================================================
# Unit tests: Token generation and resolution
# ===========================================================================

class TestTokenRoundtrip:
    def test_make_and_resolve(self, loop_env):
        """make_token -> resolve_token returns same loop_id + role."""
        token = loop_env["draftor_token"]
        loop_id, role, loop_dir = loop_session.resolve_token(token)
        assert loop_id == loop_env["loop_id"]
        assert role == "draftor"
        assert loop_dir == loop_env["loop_dir"]

    def test_reviewer_token(self, loop_env):
        """Reviewer token resolves to reviewer role."""
        _, role, _ = loop_session.resolve_token(loop_env["reviewer_token"])
        assert role == "reviewer"

    def test_token_prefix(self, loop_env):
        """Tokens start with glp_ prefix."""
        assert loop_env["draftor_token"].startswith("glp_")
        assert loop_env["reviewer_token"].startswith("glp_")


class TestTokenNonceValidation:
    def test_wrong_nonce_rejected(self, loop_env):
        """Token with wrong nonce is rejected."""
        # Tamper with the stored nonce
        tokens_path = loop_env["loop_dir"] / ".tokens.json"
        data = json.loads(tokens_path.read_text(encoding="utf-8"))
        data["draftor"]["nonce"] = "00000000"
        tokens_path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(ValueError, match="nonce mismatch"):
            loop_session.resolve_token(loop_env["draftor_token"])

    def test_invalid_prefix_rejected(self):
        """Token without glp_ prefix is rejected."""
        with pytest.raises(ValueError, match="missing.*prefix"):
            loop_session.resolve_token("bad_token_here")

    def test_corrupt_base64_rejected(self, loop_env):
        """Corrupt base64 payload is rejected."""
        with pytest.raises(ValueError):
            loop_session.resolve_token("glp_!!!notbase64!!!")


class TestTokenNotReconstructable:
    def test_session_json_has_no_nonce(self, loop_env):
        """session.json alone cannot produce a valid token (no nonce)."""
        session = loop_session.load_session(loop_env["loop_dir"])
        # session.json has roles but no nonces
        for role_data in session["roles"].values():
            assert "nonce" not in role_data
            assert "token" not in role_data


# ===========================================================================
# Unit tests: State machine
# ===========================================================================

class TestStateMachineHappyPath:
    def test_draft_review_approve(self):
        """draft -> review -> approve transitions correctly."""
        s = loop_session.create_session("t", "l", max_rounds=3, turn_timeout=300)
        assert loop_sm.is_active(s)

        loop_sm.advance_draft_submitted(s, 300)
        assert s["status"]["stage"] == "plan_review"
        assert s["status"]["next_role"] == "reviewer"

        loop_sm.advance_review_submitted(s, approved=True, findings_count=0, turn_timeout=300)
        assert s["status"]["stage"] == "plan_approved"
        assert loop_sm.is_terminal(s)
        assert s["status"]["unresolved_findings"] == 0


class TestStateMachineRevisionLoop:
    def test_draft_review_revise_cycles(self):
        """draft -> review(findings) -> revise -> review cycles."""
        s = loop_session.create_session("t", "l", max_rounds=5, turn_timeout=300)

        loop_sm.advance_draft_submitted(s, 300)
        loop_sm.advance_review_submitted(s, False, 2, 300)
        assert s["status"]["stage"] == "plan_revision"
        assert s["status"]["round"] == 1

        loop_sm.advance_draft_submitted(s, 300)
        assert s["status"]["stage"] == "plan_review"

        loop_sm.advance_review_submitted(s, False, 1, 300)
        assert s["status"]["round"] == 2

        loop_sm.advance_draft_submitted(s, 300)
        loop_sm.advance_review_submitted(s, True, 0, 300)
        assert s["status"]["stage"] == "plan_approved"


class TestStateMachineMaxRounds:
    def test_round_ceiling_triggers_terminal(self):
        """Round ceiling triggers max_rounds_exceeded."""
        s = loop_session.create_session("t", "l", max_rounds=2, turn_timeout=300)

        loop_sm.advance_draft_submitted(s, 300)
        loop_sm.advance_review_submitted(s, False, 1, 300)  # round 1
        loop_sm.advance_draft_submitted(s, 300)
        loop_sm.advance_review_submitted(s, False, 1, 300)  # round 2 = max

        assert s["status"]["stage"] == "max_rounds_exceeded"
        assert loop_sm.is_terminal(s)


class TestStateMachineEscalation:
    def test_escalate_from_any_active(self):
        """Escalate from any active state sets blocked."""
        s = loop_session.create_session("t", "l", max_rounds=3, turn_timeout=300)
        loop_sm.advance_escalated(s, "need input")
        assert s["status"]["stage"] == "blocked_on_architect"
        assert loop_sm.is_paused(s)
        assert s["status"]["resume_stage"] == "plan_drafting"
        assert s["status"]["resume_next_role"] == "draftor"


class TestValidation:
    def test_wrong_role_rejected(self):
        """submit-draft with reviewer token rejected."""
        s = loop_session.create_session("t", "l", max_rounds=3, turn_timeout=300)
        ok, _ = loop_sm.validate_action(s, "reviewer", "submit_draft")
        assert not ok

    def test_not_your_turn_rejected(self):
        """Submit when next_role doesn't match rejected."""
        s = loop_session.create_session("t", "l", max_rounds=3, turn_timeout=300)
        ok, reason = loop_sm.validate_action(s, "reviewer", "submit_review")
        assert not ok
        assert "not valid in stage" in reason.lower() or "turn" in reason.lower()

    def test_blocked_rejected(self):
        """Submit on blocked loop rejected."""
        s = loop_session.create_session("t", "l", max_rounds=3, turn_timeout=300)
        loop_sm.advance_escalated(s, "test")
        ok, _ = loop_sm.validate_action(s, "draftor", "submit_draft")
        assert not ok

    def test_escalate_bypasses_turn_check(self):
        """Either role can escalate regardless of whose turn it is."""
        s = loop_session.create_session("t", "l", max_rounds=3, turn_timeout=300)
        loop_sm.advance_draft_submitted(s, 300)
        assert s["status"]["next_role"] == "reviewer"

        # Draftor can escalate even though it's reviewer's turn
        ok, _ = loop_sm.validate_action(s, "draftor", "escalate")
        assert ok
        ok, _ = loop_sm.validate_action(s, "reviewer", "escalate")
        assert ok


class TestTurnTracking:
    def test_turns_accumulate_with_sequential_ids(self):
        """Turns accumulate correctly with sequential IDs."""
        s = loop_session.create_session("t", "l", max_rounds=3, turn_timeout=300)
        loop_session.append_turn(s, "draftor", "plan_draft", "Draft 1", "plan.md")
        loop_session.append_turn(s, "reviewer", "plan_review", "Review 1", "findings.md")
        loop_session.append_turn(s, "draftor", "plan_draft", "Draft 2", "plan.md")

        assert len(s["turns"]) == 3
        assert s["turns"][0]["turn_id"] == "draftor-001"
        assert s["turns"][1]["turn_id"] == "reviewer-001"
        assert s["turns"][2]["turn_id"] == "draftor-002"


class TestTurnTimeout:
    def test_expired_deadline_triggers_terminal(self):
        """Expired deadline triggers turn_timed_out terminal state."""
        s = loop_session.create_session("t", "l", max_rounds=3, turn_timeout=300)
        loop_sm.advance_turn_timed_out(s, "draftor")
        assert s["status"]["stage"] == "turn_timed_out"
        assert loop_sm.is_terminal(s)

    def test_deadline_resets_on_submit(self):
        """Each submit resets turn_deadline for the next role."""
        s = loop_session.create_session("t", "l", max_rounds=3, turn_timeout=300)
        old_deadline = s["status"]["turn_deadline"]
        time.sleep(0.01)  # ensure time difference
        loop_sm.advance_draft_submitted(s, 300)
        new_deadline = s["status"]["turn_deadline"]
        assert new_deadline != old_deadline


class TestUnblock:
    def test_restores_resume_state(self):
        """Unblock restores resume_stage and resume_next_role."""
        s = loop_session.create_session("t", "l", max_rounds=3, turn_timeout=300)
        loop_sm.advance_draft_submitted(s, 300)
        loop_sm.advance_escalated(s, "test")
        loop_sm.advance_unblocked(s, turn_timeout=300)
        assert s["status"]["stage"] == "plan_review"
        assert s["status"]["next_role"] == "reviewer"
        assert not s["status"]["blocked"]

    def test_override_stage_and_role(self):
        """Unblock with --next-role/--stage overrides resume defaults."""
        s = loop_session.create_session("t", "l", max_rounds=3, turn_timeout=300)
        loop_sm.advance_draft_submitted(s, 300)
        loop_sm.advance_escalated(s, "test")
        loop_sm.advance_unblocked(s, stage="plan_drafting", next_role="draftor", turn_timeout=300)
        assert s["status"]["stage"] == "plan_drafting"
        assert s["status"]["next_role"] == "draftor"

    def test_rejects_non_blocked(self):
        """Unblock on active/terminal loop fails validation."""
        s = loop_session.create_session("t", "l", max_rounds=3, turn_timeout=300)
        ok, _ = loop_sm.validate_unblock(s)
        assert not ok

    def test_rejects_mismatched_stage_role(self):
        """Unblock with stage/role mismatch raises ValueError."""
        s = loop_session.create_session("t", "l", max_rounds=3, turn_timeout=300)
        loop_sm.advance_escalated(s, "test")
        with pytest.raises(ValueError, match="belongs to"):
            loop_sm.advance_unblocked(s, stage="plan_drafting", next_role="reviewer", turn_timeout=300)


class TestIsPaused:
    def test_blocked_on_architect_is_paused(self):
        """is_paused returns true only for blocked_on_architect."""
        s = loop_session.create_session("t", "l", max_rounds=3, turn_timeout=300)
        assert not loop_sm.is_paused(s)
        loop_sm.advance_escalated(s, "test")
        assert loop_sm.is_paused(s)


class TestSessionAtomicWrite:
    def test_save_produces_valid_json(self, tmp_path):
        """save_session produces valid JSON even after multiple writes."""
        s = loop_session.create_session("t", "l", max_rounds=3, turn_timeout=300)
        loop_session.save_session(tmp_path, s)
        loaded = json.loads((tmp_path / "session.json").read_text(encoding="utf-8"))
        assert loaded["schema"] == "gator-loop-session-v1"

        # Second write
        s["status"]["stage"] = "plan_review"
        loop_session.save_session(tmp_path, s)
        loaded2 = json.loads((tmp_path / "session.json").read_text(encoding="utf-8"))
        assert loaded2["status"]["stage"] == "plan_review"


# ===========================================================================
# Unit tests: Events
# ===========================================================================

class TestEventFormatting:
    def test_format_known_events(self):
        """Known event types format with labels."""
        e = {"ts": "2026-07-26T14:30:00+00:00", "event": "loop_started", "detail": "init"}
        out = loop_events.format_event(e)
        assert "loop started" in out
        assert "14:30:00" in out

    def test_format_terminal_event(self):
        """Terminal events format with emphasis."""
        e = {"ts": "2026-07-26T15:00:00+00:00", "event": "plan_approved", "role": "reviewer", "round": 2}
        out = loop_events.format_event(e)
        assert "APPROVED" in out

    def test_format_unknown_event(self):
        """Unknown event types fall through gracefully."""
        e = {"ts": "2026-07-26T15:00:00+00:00", "event": "custom_event", "detail": "something"}
        out = loop_events.format_event(e)
        assert "custom_event" in out


class TestEventEmitRead:
    def test_roundtrip(self, tmp_path):
        """emit_event -> read_all_events roundtrip."""
        loop_events.create_events_file(tmp_path)
        loop_events.emit_event(tmp_path, {"event": "loop_started"})
        loop_events.emit_event(tmp_path, {"event": "draft_submitted", "role": "draftor"})
        events = loop_events.read_all_events(tmp_path)
        assert len(events) == 2
        assert events[0]["event"] == "loop_started"
        assert events[1]["role"] == "draftor"

    def test_events_have_timestamp_and_loop_id(self, tmp_path):
        """Emitted events get ts and loop_id auto-populated."""
        loop_events.create_events_file(tmp_path)
        loop_events.emit_event(tmp_path, {"event": "test"})
        events = loop_events.read_all_events(tmp_path)
        assert "ts" in events[0]
        assert "loop_id" in events[0]


# ===========================================================================
# Integration tests: Submit handlers
# ===========================================================================

class TestFullLoopApprove:
    def test_start_draft_review_approve(self, loop_env):
        """start -> submit-draft -> submit-review --approve -> terminal."""
        loop_submit.handle_submit_draft(loop_env["draftor_token"], str(loop_env["draft_file"]))
        loop_submit.handle_submit_review(
            loop_env["reviewer_token"], str(loop_env["findings_file"]), approve=True
        )

        s = loop_session.load_session(loop_env["loop_dir"])
        assert s["status"]["stage"] == "plan_approved"
        assert loop_sm.is_terminal(s)

        # Artifacts copied
        assert (loop_env["loop_dir"] / "plan.current.md").exists()
        assert (loop_env["loop_dir"] / "findings.current.md").exists()


class TestFullLoopRevise:
    def test_draft_review_revise_approve(self, loop_env):
        """start -> draft -> review(findings) -> revise -> review(approve)."""
        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        loop_submit.handle_submit_review(e["reviewer_token"], str(e["findings_file"]))

        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["stage"] == "plan_revision"
        assert s["status"]["round"] == 1

        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        loop_submit.handle_submit_review(e["reviewer_token"], str(e["findings_file"]), approve=True)

        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["stage"] == "plan_approved"


class TestFullLoopMaxRounds:
    def test_three_rounds_triggers_terminal(self, loop_env, monkeypatch):
        """3 rounds of revision -> max_rounds_exceeded."""
        # Override to max_rounds=2
        s = loop_session.load_session(loop_env["loop_dir"])
        s["status"]["max_rounds"] = 2
        loop_session.save_session(loop_env["loop_dir"], s)

        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        loop_submit.handle_submit_review(e["reviewer_token"], str(e["findings_file"]))  # round 1
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        loop_submit.handle_submit_review(e["reviewer_token"], str(e["findings_file"]))  # round 2 = max

        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["stage"] == "max_rounds_exceeded"


class TestStatusExitCodes:
    def test_your_turn_exit_0(self, loop_env):
        """Exit 0 when it IS your turn."""
        from cli import _cmd_status
        import argparse
        args = argparse.Namespace(token=loop_env["draftor_token"], json=False)
        with pytest.raises(SystemExit) as exc:
            _cmd_status(args)
        assert exc.value.code == 0

    def test_not_your_turn_exit_1(self, loop_env):
        """Exit 1 when it is NOT your turn."""
        from cli import _cmd_status
        import argparse
        args = argparse.Namespace(token=loop_env["reviewer_token"], json=False)
        with pytest.raises(SystemExit) as exc:
            _cmd_status(args)
        assert exc.value.code == 1

    def test_blocked_exit_2(self, loop_env):
        """Exit 2 when blocked."""
        loop_submit.handle_escalate(loop_env["draftor_token"], "test")
        from cli import _cmd_status
        import argparse
        args = argparse.Namespace(token=loop_env["draftor_token"], json=False)
        with pytest.raises(SystemExit) as exc:
            _cmd_status(args)
        assert exc.value.code == 2


class TestEventsEmitted:
    def test_correct_events_after_loop(self, loop_env):
        """events.jsonl contains correct entries after a full loop."""
        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        loop_submit.handle_submit_review(e["reviewer_token"], str(e["findings_file"]))
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        loop_submit.handle_submit_review(e["reviewer_token"], str(e["findings_file"]), approve=True)

        events = loop_events.read_all_events(e["loop_dir"])
        event_types = [ev["event"] for ev in events]
        assert event_types == [
            "draft_submitted",
            "revision_requested",
            "draft_submitted",
            "plan_approved",
        ]


class TestNoGitCommitOnTerminal:
    def test_residue_remains_no_commit(self, loop_env):
        """Terminal state leaves residue, does not commit."""
        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        loop_submit.handle_submit_review(e["reviewer_token"], str(e["findings_file"]), approve=True)

        # Session files remain
        assert (e["loop_dir"] / "session.json").exists()
        assert (e["loop_dir"] / "events.jsonl").exists()
        assert (e["loop_dir"] / "plan.current.md").exists()
        assert (e["loop_dir"] / "findings.current.md").exists()

        # No .git in the loop directory — no autonomous commit
        assert not (e["loop_dir"] / ".git").exists()


class TestEscalateUnblockResume:
    def test_draft_escalate_unblock_resumed_stage_accepts_submit(self, loop_env):
        """draft -> escalate -> unblock -> resumed stage accepts submit."""
        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))

        # Escalate (reviewer's turn, but either role can escalate)
        loop_submit.handle_escalate(e["reviewer_token"], "Scope question")

        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["stage"] == "blocked_on_architect"

        # Unblock
        loop_submit.handle_unblock(e["architect_token"])

        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["stage"] == "plan_review"

        # Resumed stage accepts review
        loop_submit.handle_submit_review(e["reviewer_token"], str(e["findings_file"]), approve=True)

        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["stage"] == "plan_approved"


class TestSessionWrittenBeforeEvent:
    def test_write_ordering(self, loop_env):
        """Event appears in events.jsonl only after session.json is updated."""
        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))

        # After the submit, session.json should already reflect the new state
        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["stage"] == "plan_review"

        # And the event should be present
        events = loop_events.read_all_events(e["loop_dir"])
        assert events[-1]["event"] == "draft_submitted"


class TestCurrentReferences:
    def test_current_draft_is_turn_reference(self, loop_env):
        """current.draft stores a turn reference dict, not a bare string."""
        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        s = loop_session.load_session(e["loop_dir"])
        draft = s["current"]["draft"]
        assert isinstance(draft, dict)
        assert "turn_id" in draft
        assert "summary" in draft
        assert "artifact_path" in draft

    def test_current_findings_is_turn_reference(self, loop_env):
        """current.findings stores a turn reference dict."""
        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        loop_submit.handle_submit_review(e["reviewer_token"], str(e["findings_file"]))
        s = loop_session.load_session(e["loop_dir"])
        findings = s["current"]["findings"]
        assert isinstance(findings, dict)
        assert "turn_id" in findings


class TestRoundVersionedArtifacts:
    def test_round_versioned_plan_created(self, loop_env):
        """After submit-draft, plan.round-N.md exists."""
        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        assert (e["loop_dir"] / "plan.round-0.md").exists()

    def test_round_versioned_findings_created(self, loop_env):
        """After submit-review, findings.round-N.md exists."""
        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        loop_submit.handle_submit_review(e["reviewer_token"], str(e["findings_file"]))
        assert (e["loop_dir"] / "findings.round-0.md").exists()

    def test_current_still_overwritten(self, loop_env):
        """plan.current.md still has latest content."""
        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        current = (e["loop_dir"] / "plan.current.md").read_text(encoding="utf-8")
        versioned = (e["loop_dir"] / "plan.round-0.md").read_text(encoding="utf-8")
        assert current == versioned

    def test_full_loop_preserves_all_rounds(self, loop_env):
        """After 2-round approve loop, all versioned files exist."""
        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        loop_submit.handle_submit_review(e["reviewer_token"], str(e["findings_file"]))
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        loop_submit.handle_submit_review(
            e["reviewer_token"], str(e["findings_file"]), approve=True
        )
        assert (e["loop_dir"] / "plan.round-0.md").exists()
        assert (e["loop_dir"] / "plan.round-1.md").exists()
        assert (e["loop_dir"] / "findings.round-0.md").exists()
        assert (e["loop_dir"] / "findings.round-1.md").exists()

    def test_round_number_correct(self, loop_env):
        """Round number in filename matches session round at submission time."""
        e = loop_env
        # Round 0: draft + review (review increments to round 1)
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        loop_submit.handle_submit_review(e["reviewer_token"], str(e["findings_file"]))
        # Round 1: draft
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))

        assert (e["loop_dir"] / "plan.round-0.md").exists()
        assert (e["loop_dir"] / "findings.round-0.md").exists()
        assert (e["loop_dir"] / "plan.round-1.md").exists()

    def test_turn_artifact_path_versioned(self, loop_env):
        """Turn entries reference plan.round-N.md, not plan.current.md."""
        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        s = loop_session.load_session(e["loop_dir"])
        turn = s["turns"][-1]
        assert turn["artifact_path"] == "plan.round-0.md"

    def test_current_reference_stays_current(self, loop_env):
        """session.current.draft.artifact_path is plan.current.md even after versioned turn."""
        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        s = loop_session.load_session(e["loop_dir"])
        assert s["current"]["draft"]["artifact_path"] == "plan.current.md"

    def test_findings_current_reference_stays_current(self, loop_env):
        """session.current.findings.artifact_path is findings.current.md."""
        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        loop_submit.handle_submit_review(e["reviewer_token"], str(e["findings_file"]))
        s = loop_session.load_session(e["loop_dir"])
        assert s["current"]["findings"]["artifact_path"] == "findings.current.md"


# ===========================================================================
# Concurrency safety
# ===========================================================================

class TestTimeoutEnforcement:
    def test_timeout_fires_when_expired(self, loop_env, monkeypatch):
        """Host re-reads inside lock, sees deadline expired, fires timeout."""
        from host import _try_enforce_timeout

        # Set deadline in the past
        s = loop_session.load_session(loop_env["loop_dir"])
        past = (datetime.now(tz=timezone.utc) - timedelta(seconds=10)).isoformat()
        s["status"]["turn_deadline"] = past
        loop_session.save_session(loop_env["loop_dir"], s)

        _try_enforce_timeout(loop_env["loop_dir"])

        s = loop_session.load_session(loop_env["loop_dir"])
        assert s["status"]["stage"] == "turn_timed_out"

    def test_timeout_skipped_after_submit(self, loop_env):
        """Host re-reads inside lock, sees state advanced, skips timeout."""
        from host import _try_enforce_timeout

        # Submit first (advances state, resets deadline)
        loop_submit.handle_submit_draft(
            loop_env["draftor_token"], str(loop_env["draft_file"])
        )

        # Now try to enforce timeout — should skip because deadline was reset
        _try_enforce_timeout(loop_env["loop_dir"])

        s = loop_session.load_session(loop_env["loop_dir"])
        assert s["status"]["stage"] == "plan_review"  # not timed out

    def test_no_timeout_while_paused(self, loop_env):
        """Host skips deadline check when blocked_on_architect."""
        from host import _try_enforce_timeout

        # Escalate to paused state with expired deadline
        loop_submit.handle_escalate(loop_env["draftor_token"], "test")
        s = loop_session.load_session(loop_env["loop_dir"])
        past = (datetime.now(tz=timezone.utc) - timedelta(seconds=10)).isoformat()
        s["status"]["turn_deadline"] = past
        loop_session.save_session(loop_env["loop_dir"], s)

        _try_enforce_timeout(loop_env["loop_dir"])

        s = loop_session.load_session(loop_env["loop_dir"])
        assert s["status"]["stage"] == "blocked_on_architect"  # not timed out

    def test_submit_fails_after_timeout(self, loop_env):
        """Submit re-reads inside lock, sees turn_timed_out, fails cleanly."""
        from host import _try_enforce_timeout

        # Force timeout
        s = loop_session.load_session(loop_env["loop_dir"])
        past = (datetime.now(tz=timezone.utc) - timedelta(seconds=10)).isoformat()
        s["status"]["turn_deadline"] = past
        loop_session.save_session(loop_env["loop_dir"], s)
        _try_enforce_timeout(loop_env["loop_dir"])

        # Submit should fail
        with pytest.raises(PermissionError, match="ended"):
            loop_submit.handle_submit_draft(
                loop_env["draftor_token"], str(loop_env["draft_file"])
            )


class TestArchitectMessage:
    def test_unblock_with_message(self, loop_env):
        """Unblock with --message stores message in session, visible in status."""
        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        loop_submit.handle_escalate(e["reviewer_token"], "Need permission to check API docs")

        loop_submit.handle_unblock(e["architect_token"], message="Yes, check the website. Use v2 API.")

        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["architect_message"] == "Yes, check the website. Use v2 API."
        assert s["status"]["stage"] == "plan_review"

    def test_message_in_status_output(self, loop_env):
        """Status output shows architect message when present."""
        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        loop_submit.handle_escalate(e["reviewer_token"], "Scope question")
        loop_submit.handle_unblock(e["architect_token"], message="Scope is correct, proceed.")

        from cli import _cmd_status
        import argparse
        import io, contextlib

        args = argparse.Namespace(token=e["reviewer_token"], json=False)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            try:
                _cmd_status(args)
            except SystemExit:
                pass
        assert "Architect message: Scope is correct, proceed." in output.getvalue()

    def test_message_in_json_status(self, loop_env):
        """JSON status includes architect_message field."""
        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        loop_submit.handle_escalate(e["reviewer_token"], "Question")
        loop_submit.handle_unblock(e["architect_token"], message="Answer here.")

        from cli import _cmd_status
        import argparse
        import io, contextlib

        args = argparse.Namespace(token=e["reviewer_token"], json=True)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            try:
                _cmd_status(args)
            except SystemExit:
                pass
        data = json.loads(output.getvalue())
        assert data["architect_message"] == "Answer here."

    def test_message_cleared_after_submit(self, loop_env):
        """Architect message is cleared after the model submits."""
        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        loop_submit.handle_escalate(e["reviewer_token"], "Question")
        loop_submit.handle_unblock(e["architect_token"], message="Go ahead.")

        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["architect_message"] == "Go ahead."

        # Reviewer submits — message should be cleared
        loop_submit.handle_submit_review(e["reviewer_token"], str(e["findings_file"]))
        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["architect_message"] is None

    def test_message_in_unblock_event(self, loop_env):
        """Unblock event includes architect message in detail."""
        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        loop_submit.handle_escalate(e["reviewer_token"], "Need input")
        loop_submit.handle_unblock(e["architect_token"], message="Approved, go ahead.")

        events = loop_events.read_all_events(e["loop_dir"])
        unblock_event = [ev for ev in events if ev["event"] == "loop_unblocked"][0]
        assert "Architect: Approved, go ahead." in unblock_event["detail"]

    def test_unblock_without_message(self, loop_env):
        """Unblock without message leaves architect_message as None."""
        e = loop_env
        loop_submit.handle_escalate(e["draftor_token"], "test")
        loop_submit.handle_unblock(e["architect_token"])

        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["architect_message"] is None


class TestArchitectToken:
    def test_architect_token_generated(self, loop_env):
        """Architect token exists in .tokens.json."""
        tokens = loop_session.load_tokens(loop_env["loop_dir"])
        assert "architect" in tokens
        assert "nonce" in tokens["architect"]
        assert "token" in tokens["architect"]
        assert tokens["architect"]["token"].startswith("glp_")

    def test_architect_in_session_roles(self, loop_env):
        """session.json includes architect role."""
        s = loop_session.load_session(loop_env["loop_dir"])
        assert "architect" in s["roles"]
        assert s["roles"]["architect"]["role"] == "architect"

    def test_architect_cannot_submit_draft(self, loop_env):
        """Architect token rejected for model commands."""
        with pytest.raises(PermissionError, match="model action"):
            loop_submit.handle_submit_draft(
                loop_env["architect_token"], str(loop_env["draft_file"])
            )

    def test_model_cannot_pause(self, loop_env):
        """Model token rejected for architect commands."""
        with pytest.raises(PermissionError, match="architect token"):
            loop_submit.handle_pause(loop_env["draftor_token"])

    def test_model_cannot_end(self, loop_env):
        """Model token rejected for end command."""
        with pytest.raises(PermissionError, match="architect token"):
            loop_submit.handle_end(loop_env["draftor_token"])

    def test_model_cannot_unblock(self, loop_env):
        """Model token rejected for unblock command."""
        loop_submit.handle_escalate(loop_env["draftor_token"], "test")
        with pytest.raises(PermissionError, match="architect token"):
            loop_submit.handle_unblock(loop_env["draftor_token"])


class TestArchitectPause:
    def test_pause_from_active(self, loop_env):
        """Architect can pause a running loop."""
        e = loop_env
        loop_submit.handle_pause(e["architect_token"], message="Hold on")
        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["stage"] == "paused_by_architect"
        assert loop_sm.is_paused(s)
        assert s["status"]["architect_message"] == "Hold on"
        assert s["status"]["resume_stage"] == "plan_drafting"

    def test_pause_emits_event(self, loop_env):
        """Pause emits loop_paused event."""
        loop_submit.handle_pause(loop_env["architect_token"])
        events = loop_events.read_all_events(loop_env["loop_dir"])
        assert events[-1]["event"] == "loop_paused"

    def test_pause_records_turn(self, loop_env):
        """Pause appends an architect turn."""
        loop_submit.handle_pause(loop_env["architect_token"], message="Wait")
        s = loop_session.load_session(loop_env["loop_dir"])
        arch_turns = [t for t in s["turns"] if t["role"] == "architect"]
        assert len(arch_turns) == 1
        assert arch_turns[0]["type"] == "pause"

    def test_unblock_after_pause(self, loop_env):
        """Unblock works for paused_by_architect (not just blocked_on_architect)."""
        e = loop_env
        loop_submit.handle_pause(e["architect_token"])
        loop_submit.handle_unblock(e["architect_token"], message="Resume")
        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["stage"] == "plan_drafting"
        assert not s["status"]["blocked"]


class TestArchitectInterject:
    def test_interject_stores_message(self, loop_env):
        """Interject stores message without changing state."""
        e = loop_env
        loop_submit.handle_interject(e["architect_token"], "Check the v2 API")
        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["stage"] == "plan_drafting"  # unchanged
        assert s["status"]["architect_message"] == "Check the v2 API"

    def test_interject_emits_event(self, loop_env):
        """Interject emits architect_interjection event."""
        loop_submit.handle_interject(loop_env["architect_token"], "Guidance")
        events = loop_events.read_all_events(loop_env["loop_dir"])
        assert events[-1]["event"] == "architect_interjection"
        assert events[-1]["detail"] == "Guidance"

    def test_interject_requires_message(self, loop_env):
        """Interject with empty message is rejected."""
        with pytest.raises(ValueError, match="required"):
            loop_submit.handle_interject(loop_env["architect_token"], "")

    def test_interject_message_cleared_on_submit(self, loop_env):
        """Message from interject is cleared when model submits."""
        e = loop_env
        loop_submit.handle_interject(e["architect_token"], "Heads up")
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["architect_message"] is None


class TestArchitectEnd:
    def test_end_from_active(self, loop_env):
        """Architect can end a running loop."""
        e = loop_env
        loop_submit.handle_end(e["architect_token"], reason="Scope changed")
        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["stage"] == "ended_by_architect"
        assert loop_sm.is_terminal(s)
        assert s["status"]["end_reason"] == "Scope changed"

    def test_end_emits_terminal_event(self, loop_env):
        """End emits loop_ended_by_architect event."""
        loop_submit.handle_end(loop_env["architect_token"], reason="Done")
        events = loop_events.read_all_events(loop_env["loop_dir"])
        assert events[-1]["event"] == "loop_ended_by_architect"

    def test_end_from_paused(self, loop_env):
        """Architect can end a paused loop."""
        e = loop_env
        loop_submit.handle_pause(e["architect_token"])
        loop_submit.handle_end(e["architect_token"], reason="Abandoning")
        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["stage"] == "ended_by_architect"

    def test_end_rejects_already_terminal(self, loop_env):
        """End on an already-terminal loop is rejected."""
        e = loop_env
        loop_submit.handle_end(e["architect_token"])
        with pytest.raises(PermissionError, match="already ended"):
            loop_submit.handle_end(e["architect_token"])

    def test_models_rejected_after_end(self, loop_env):
        """Models cannot submit after architect ends loop."""
        e = loop_env
        loop_submit.handle_end(e["architect_token"])
        with pytest.raises(PermissionError, match="ended"):
            loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))


class TestWaitCommand:
    def test_wait_returns_immediately_your_turn(self, loop_env):
        """Already your turn -> returns immediately with already_your_turn."""
        from cli import _wait_for_actionable
        from state_machine import is_terminal, is_paused

        session, reason = _wait_for_actionable(
            loop_env["loop_dir"], "draftor", 0.1,
            loop_session.load_session, is_terminal, is_paused
        )
        assert reason == "already_your_turn"
        assert session["status"]["next_role"] == "draftor"

    def test_wait_returns_on_terminal(self, loop_env):
        """Loop already terminal -> returns with terminal."""
        from cli import _wait_for_actionable
        from state_machine import is_terminal, is_paused
        from host import _try_enforce_timeout

        # Force timeout
        s = loop_session.load_session(loop_env["loop_dir"])
        past = (datetime.now(tz=timezone.utc) - timedelta(seconds=10)).isoformat()
        s["status"]["turn_deadline"] = past
        loop_session.save_session(loop_env["loop_dir"], s)
        _try_enforce_timeout(loop_env["loop_dir"])

        session, reason = _wait_for_actionable(
            loop_env["loop_dir"], "draftor", 0.1,
            loop_session.load_session, is_terminal, is_paused
        )
        assert reason == "terminal"

    def test_wait_returns_on_pause(self, loop_env):
        """Loop paused -> returns with paused."""
        from cli import _wait_for_actionable
        from state_machine import is_terminal, is_paused

        loop_submit.handle_pause(loop_env["architect_token"])

        session, reason = _wait_for_actionable(
            loop_env["loop_dir"], "draftor", 0.1,
            loop_session.load_session, is_terminal, is_paused
        )
        assert reason == "paused"

    def test_wait_blocks_then_wakes(self, loop_env):
        """Not your turn, then becomes your turn -> wakes with became_your_turn."""
        import threading
        from cli import _wait_for_actionable
        from state_machine import is_terminal, is_paused

        e = loop_env
        # Submit draft so it's reviewer's turn
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))

        result = {}

        def wait_in_thread():
            s, r = _wait_for_actionable(
                e["loop_dir"], "draftor", 0.1,
                loop_session.load_session, is_terminal, is_paused
            )
            result["reason"] = r

        t = threading.Thread(target=wait_in_thread)
        t.start()

        # Reviewer submits -> draftor's turn again
        import time
        time.sleep(0.2)
        loop_submit.handle_submit_review(e["reviewer_token"], str(e["findings_file"]))

        t.join(timeout=5)
        assert not t.is_alive()
        assert result["reason"] == "became_your_turn"

    def test_wait_json_includes_wake_reason(self, loop_env):
        """--json output has wake_reason field."""
        from cli import _cmd_wait
        import argparse, io, contextlib

        args = argparse.Namespace(
            token=loop_env["draftor_token"], json=True, poll=0.1
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            try:
                _cmd_wait(args)
            except SystemExit:
                pass
        data = json.loads(output.getvalue())
        assert "wake_reason" in data
        assert data["wake_reason"] == "already_your_turn"

    def test_wait_rejects_architect_token(self, loop_env):
        """Wait rejects architect tokens — architects use status, not wait."""
        from cli import _cmd_wait
        import argparse
        args = argparse.Namespace(token=loop_env["architect_token"], json=False, poll=0.1)
        with pytest.raises(SystemExit) as exc:
            _cmd_wait(args)
        assert exc.value.code == 1

    def test_wait_does_not_write(self, loop_env):
        """Wait does not modify session or events files."""
        from cli import _wait_for_actionable
        from state_machine import is_terminal, is_paused

        session_before = (loop_env["loop_dir"] / "session.json").read_bytes()
        events_before = (loop_env["loop_dir"] / "events.jsonl").read_bytes()

        _wait_for_actionable(
            loop_env["loop_dir"], "draftor", 0.1,
            loop_session.load_session, is_terminal, is_paused
        )

        session_after = (loop_env["loop_dir"] / "session.json").read_bytes()
        events_after = (loop_env["loop_dir"] / "events.jsonl").read_bytes()
        assert session_before == session_after
        assert events_before == events_after


class TestGitignore:
    def test_tokens_gitignored(self, loop_env):
        """loops/.gitignore includes .tokens.json."""
        gi = (loop_env["loop_dir"].parent / ".gitignore").read_text(encoding="utf-8")
        assert ".tokens.json" in gi
        assert "session.lock" in gi
