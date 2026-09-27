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


class TestResolveTokenExplicitLoopDir:
    """Tests for resolve_token(token, loop_dir=...) — the repo-scoped
    token seam used by the dashboard to bypass find_gator_root()."""

    def test_explicit_loop_dir_skips_cwd_discovery(self, loop_env):
        """With loop_dir provided, resolve_token returns the correct
        result without needing find_gator_root()."""
        token = loop_env["draftor_token"]
        loop_id, role, resolved = loop_session.resolve_token(
            token, loop_dir=loop_env["loop_dir"])
        assert loop_id == loop_env["loop_id"]
        assert role == "draftor"
        assert resolved == loop_env["loop_dir"]

    def test_explicit_loop_dir_validates_nonce(self, loop_env):
        """Nonce validation still runs with explicit loop_dir."""
        tokens_path = loop_env["loop_dir"] / ".tokens.json"
        data = json.loads(tokens_path.read_text(encoding="utf-8"))
        data["draftor"]["nonce"] = "00000000"
        tokens_path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(ValueError, match="nonce mismatch"):
            loop_session.resolve_token(
                loop_env["draftor_token"],
                loop_dir=loop_env["loop_dir"])

    def test_mismatched_token_loop_id_rejected(self, tmp_path, loop_env):
        """Token minted for loop A combined with loop_dir pointing to
        loop B is rejected even if B has valid nonces."""
        other_id = "other-loop"
        other_dir = tmp_path / ".gator" / "loops" / other_id
        other_dir.mkdir(parents=True)
        tok_o, nonce_o = loop_session.make_token(other_id, "draftor")
        loop_session.save_tokens(other_dir, {
            "draftor": {"nonce": nonce_o, "token": tok_o},
        })
        with pytest.raises(ValueError, match="does not match"):
            loop_session.resolve_token(
                loop_env["draftor_token"],
                loop_dir=other_dir)

    def test_all_roles_resolve_with_explicit_loop_dir(self, loop_env):
        """Each role token resolves correctly with explicit loop_dir."""
        for role_name, token_key in [("draftor", "draftor_token"),
                                      ("reviewer", "reviewer_token"),
                                      ("architect", "architect_token")]:
            _, role, _ = loop_session.resolve_token(
                loop_env[token_key], loop_dir=loop_env["loop_dir"])
            assert role == role_name


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


def _max_rounds_session(max_rounds=2, turn_timeout=300):
    """A session driven to max_rounds_exceeded through real transitions."""
    s = loop_session.create_session("t", "l", max_rounds=max_rounds,
                                    turn_timeout=turn_timeout)
    for _ in range(max_rounds):
        loop_sm.advance_draft_submitted(s, turn_timeout)
        loop_sm.advance_review_submitted(s, False, 1, turn_timeout)
    assert s["status"]["stage"] == "max_rounds_exceeded"
    return s


class TestAdvanceExtended:
    """#39 M1 — max_rounds_exceeded -> plan_revision via extend."""

    def test_resumes_plan_revision_for_draftor(self):
        s = _max_rounds_session(max_rounds=3)
        prev, new = loop_sm.advance_extended(s, 2, 300, message="Keep going")
        st = s["status"]
        assert (prev, new) == (3, 5)
        assert st["max_rounds"] == 5
        assert st["stage"] == "plan_revision"
        assert st["next_role"] == "draftor"
        assert st["plan_status"] == "revision"
        assert st["blocked"] is False
        assert st["architect_action_required"] is False
        assert st["architect_message"] == "Keep going"
        assert st["architect_response_artifact"] is None
        assert loop_sm.is_active(s) and not loop_sm.is_terminal(s)

    def test_preserves_history(self):
        s = _max_rounds_session(max_rounds=2)
        s["turns"].append({"id": "draftor-001", "summary": "x"})
        s["decisions"].append({"id": "decision-1", "request": {}, "response": {"message": "m"}})
        s["current"]["draft"] = {"turn_id": "draftor-001", "artifact_path": "plan.round-1.md"}
        before = json.loads(json.dumps({k: s[k] for k in ("turns", "decisions", "current")}))
        round_before = s["status"]["round"]
        findings_before = s["status"]["unresolved_findings"]

        loop_sm.advance_extended(s, 1, 300, message="m")

        assert s["status"]["round"] == round_before, "round must never be renumbered"
        assert s["status"]["unresolved_findings"] == findings_before
        assert {k: s[k] for k in ("turns", "decisions", "current")} == before

    def test_deadline_uses_given_timeout(self):
        s = _max_rounds_session(max_rounds=2)
        loop_sm.advance_extended(s, 1, 900, message="m")
        remaining = (datetime.fromisoformat(s["status"]["turn_deadline"])
                     - datetime.now(tz=timezone.utc)).total_seconds()
        assert 800 < remaining <= 900

    def test_extended_loop_runs_normal_cycle_to_new_ceiling(self):
        s = _max_rounds_session(max_rounds=2)
        loop_sm.advance_extended(s, 1, 300, message="one more")
        loop_sm.advance_draft_submitted(s, 300)
        assert s["status"]["architect_message"] is None  # cleared once acted on
        loop_sm.advance_review_submitted(s, False, 1, 300)
        assert s["status"]["round"] == 3
        assert s["status"]["stage"] == "max_rounds_exceeded"
        # ...and it can be extended again
        assert loop_sm.advance_extended(s, 2, 300, message="again") == (3, 5)

    @pytest.mark.parametrize("stage", [
        "plan_approved", "turn_timed_out", "ended_by_architect",
        "plan_drafting", "plan_review", "plan_revision",
        "blocked_on_architect", "paused_by_architect",
    ])
    def test_rejects_every_other_stage_without_mutation(self, stage):
        s = _max_rounds_session(max_rounds=2)
        s["status"]["stage"] = stage
        before = json.dumps(s, sort_keys=True)
        with pytest.raises(ValueError, match="round limit"):
            loop_sm.advance_extended(s, 1, 300, message="m")
        assert json.dumps(s, sort_keys=True) == before

    @pytest.mark.parametrize("bad", [0, -1, True, 1.5, "2", None])
    def test_rejects_non_positive_int_rounds_without_mutation(self, bad):
        s = _max_rounds_session(max_rounds=2)
        before = json.dumps(s, sort_keys=True)
        with pytest.raises(ValueError, match="positive integer"):
            loop_sm.advance_extended(s, bad, 300, message="m")
        assert json.dumps(s, sort_keys=True) == before

    def test_rejects_inconsistent_round_over_ceiling(self):
        s = _max_rounds_session(max_rounds=2)
        s["status"]["round"] = 5
        with pytest.raises(ValueError, match="Inconsistent"):
            loop_sm.advance_extended(s, 1, 300, message="m")
        assert s["status"]["stage"] == "max_rounds_exceeded"


class TestValidateExtendAction:
    def test_architect_may_extend_max_rounds(self):
        s = _max_rounds_session()
        assert loop_sm.validate_action(s, "architect", "extend") == (True, "ok")

    @pytest.mark.parametrize("role", ["draftor", "reviewer"])
    def test_model_roles_rejected(self, role):
        s = _max_rounds_session()
        allowed, reason = loop_sm.validate_action(s, role, "extend")
        assert allowed is False
        assert "architect token" in reason

    @pytest.mark.parametrize("stage", [
        "plan_approved", "turn_timed_out", "ended_by_architect",
        "plan_revision", "blocked_on_architect",
    ])
    def test_non_extendable_stages_rejected(self, stage):
        s = _max_rounds_session()
        s["status"]["stage"] = stage
        allowed, reason = loop_sm.validate_action(s, "architect", "extend")
        assert allowed is False
        assert "round limit" in reason and stage in reason


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


class TestEventArtifactPath:
    """Submission events carry artifact_path to the immutable round artifact."""

    def test_draft_event_has_artifact_path(self, loop_env):
        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        events = loop_events.read_all_events(e["loop_dir"])
        draft_ev = [ev for ev in events if ev["event"] == "draft_submitted"]
        assert len(draft_ev) == 1
        assert draft_ev[0]["artifact_path"] == "plan.round-0.md"

    def test_revision_requested_event_has_artifact_path(self, loop_env):
        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        loop_submit.handle_submit_review(e["reviewer_token"], str(e["findings_file"]))
        events = loop_events.read_all_events(e["loop_dir"])
        rev_ev = [ev for ev in events if ev["event"] == "revision_requested"]
        assert len(rev_ev) == 1
        assert rev_ev[0]["artifact_path"] == "findings.round-0.md"

    def test_plan_approved_event_has_artifact_path(self, loop_env):
        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        loop_submit.handle_submit_review(
            e["reviewer_token"], str(e["findings_file"]), approve=True)
        events = loop_events.read_all_events(e["loop_dir"])
        approved_ev = [ev for ev in events if ev["event"] == "plan_approved"]
        assert len(approved_ev) == 1
        assert approved_ev[0]["artifact_path"] == "findings.round-0.md"

    def test_multi_round_artifact_paths_are_immutable(self, loop_env):
        """Each round's event points to its own round artifact, not current."""
        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        loop_submit.handle_submit_review(e["reviewer_token"], str(e["findings_file"]))
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        loop_submit.handle_submit_review(
            e["reviewer_token"], str(e["findings_file"]), approve=True)
        events = loop_events.read_all_events(e["loop_dir"])
        draft_events = [ev for ev in events if ev["event"] == "draft_submitted"]
        assert draft_events[0]["artifact_path"] == "plan.round-0.md"
        assert draft_events[1]["artifact_path"] == "plan.round-1.md"
        rev_ev = [ev for ev in events if ev["event"] == "revision_requested"]
        assert rev_ev[0]["artifact_path"] == "findings.round-0.md"
        approved_ev = [ev for ev in events if ev["event"] == "plan_approved"]
        assert approved_ev[0]["artifact_path"] == "findings.round-1.md"


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

        # Unblock (an escalation requires a response)
        loop_submit.handle_unblock(e["architect_token"], message="Scope confirmed")

        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["stage"] == "plan_review"

        # Resumed stage accepts review
        loop_submit.handle_submit_review(e["reviewer_token"], str(e["findings_file"]), approve=True)

        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["stage"] == "plan_approved"


class TestStructuredDecisionRequests:
    """Module 2: escalate --file creates structured decision entries."""

    def test_escalate_with_file_copies_artifact(self, loop_env):
        """escalate --file copies decision-request artifact into loop dir."""
        e = loop_env
        request_file = e["tmp"] / "decision-request.md"
        request_file.write_text("# Decision Request\n\nWhich API version?\n", encoding="utf-8")

        loop_submit.handle_escalate(
            e["draftor_token"], "Need API version guidance",
            file_path=str(request_file)
        )

        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["stage"] == "blocked_on_architect"

        # Artifact copied to loop dir with decision-seq in name
        copied = e["loop_dir"] / "decision-request.decision-1.round-0.md"
        assert copied.exists()
        assert "Which API version?" in copied.read_text(encoding="utf-8")

        # Decisions entry created
        assert len(s["decisions"]) == 1
        d = s["decisions"][0]
        assert d["id"] == "decision-1"
        assert d["request"]["reason"] == "Need API version guidance"
        assert d["request"]["artifact_path"] == "decision-request.decision-1.round-0.md"
        assert d["request"]["role"] == "draftor"
        assert d["request"]["round"] == 0
        assert d["response"] is None

    def test_escalate_without_file_backwards_compat(self, loop_env):
        """escalate without --file still works and creates a decisions entry."""
        e = loop_env
        loop_submit.handle_escalate(e["draftor_token"], "Scope unclear")

        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["stage"] == "blocked_on_architect"
        assert len(s["decisions"]) == 1
        d = s["decisions"][0]
        assert d["request"]["reason"] == "Scope unclear"
        assert d["request"]["artifact_path"] is None
        assert d["response"] is None

    def test_escalate_file_must_exist(self, loop_env):
        """escalate --file with nonexistent path raises FileNotFoundError."""
        e = loop_env
        with pytest.raises(FileNotFoundError, match="not found"):
            loop_submit.handle_escalate(
                e["draftor_token"], "reason",
                file_path=str(e["tmp"] / "nonexistent.md")
            )

    def test_escalate_file_must_be_nonempty(self, loop_env):
        """escalate --file with empty file raises ValueError."""
        e = loop_env
        empty = e["tmp"] / "empty.md"
        empty.write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="empty"):
            loop_submit.handle_escalate(
                e["draftor_token"], "reason",
                file_path=str(empty)
            )

    def test_decisions_array_in_fresh_session(self, loop_env):
        """Fresh session has an empty decisions array."""
        s = loop_session.load_session(loop_env["loop_dir"])
        assert s["decisions"] == []

    def test_escalate_event_includes_decision_request(self, loop_env):
        """Event dict includes decision_request when file is provided."""
        e = loop_env
        request_file = e["tmp"] / "request.md"
        request_file.write_text("# Request\n\nDetails.\n", encoding="utf-8")

        loop_submit.handle_escalate(
            e["draftor_token"], "Need guidance",
            file_path=str(request_file)
        )

        events_text = (e["loop_dir"] / "events.jsonl").read_text(encoding="utf-8")
        events = [json.loads(line) for line in events_text.strip().splitlines()]
        escalation_events = [ev for ev in events if ev["event"] == "escalated"]
        assert len(escalation_events) == 1
        assert escalation_events[0]["decision_request"] == "decision-request.decision-1.round-0.md"

    def test_repeated_escalations_same_round_unique_files(self, loop_env):
        """Two escalations in the same round produce distinct files."""
        e = loop_env
        req_a = e["tmp"] / "request-a.md"
        req_a.write_text("# Request A\n\nFirst question.\n", encoding="utf-8")
        req_b = e["tmp"] / "request-b.md"
        req_b.write_text("# Request B\n\nSecond question.\n", encoding="utf-8")

        # First escalation
        loop_submit.handle_escalate(
            e["draftor_token"], "First question",
            file_path=str(req_a)
        )
        # Unblock back to same stage/round
        loop_submit.handle_unblock(e["architect_token"], message="Answered first")

        # Second escalation in the same round
        loop_submit.handle_escalate(
            e["draftor_token"], "Second question",
            file_path=str(req_b)
        )

        # Both files exist with distinct contents
        file_1 = e["loop_dir"] / "decision-request.decision-1.round-0.md"
        file_2 = e["loop_dir"] / "decision-request.decision-2.round-0.md"
        assert file_1.exists()
        assert file_2.exists()
        assert "First question" in file_1.read_text(encoding="utf-8")
        assert "Second question" in file_2.read_text(encoding="utf-8")

        # Both decisions entries present with correct artifact paths
        s = loop_session.load_session(e["loop_dir"])
        assert len(s["decisions"]) == 2
        assert s["decisions"][0]["request"]["artifact_path"] == "decision-request.decision-1.round-0.md"
        assert s["decisions"][1]["request"]["artifact_path"] == "decision-request.decision-2.round-0.md"

    def test_architect_status_shows_pending_decision(self, loop_env):
        """Architect text status displays pending decision info when blocked."""
        import argparse, io, contextlib

        e = loop_env
        req = e["tmp"] / "request.md"
        req.write_text("# Decision needed\n\nDetails.\n", encoding="utf-8")

        loop_submit.handle_escalate(
            e["draftor_token"], "Need API version guidance",
            file_path=str(req)
        )

        args = argparse.Namespace(token=e["architect_token"], json=False)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            try:
                from cli import _cmd_status
                _cmd_status(args)
            except SystemExit:
                pass
        text = output.getvalue()
        assert "decision-1" in text
        assert "Need API version guidance" in text
        assert "decision-request.decision-1.round-0.md" in text

    def test_architect_json_status_includes_decisions(self, loop_env):
        """Architect JSON status includes decisions and pending_decisions."""
        import argparse, io, contextlib

        e = loop_env
        loop_submit.handle_escalate(e["draftor_token"], "Scope unclear")

        args = argparse.Namespace(token=e["architect_token"], json=True)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            try:
                from cli import _cmd_status
                _cmd_status(args)
            except SystemExit:
                pass
        data = json.loads(output.getvalue())
        assert "decisions" in data
        assert "pending_decisions" in data
        assert len(data["pending_decisions"]) == 1
        assert data["pending_decisions"][0]["id"] == "decision-1"

    def test_escalate_with_file_not_your_turn(self, loop_env):
        """Escalate with --file works when it is NOT the caller's turn."""
        e = loop_env
        # Submit draft so it's reviewer's turn
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))

        req = e["tmp"] / "off-turn-request.md"
        req.write_text("# Off-turn request\n\nBlocked on external info.\n", encoding="utf-8")

        # Draftor escalates even though it's reviewer's turn
        loop_submit.handle_escalate(
            e["draftor_token"], "Blocked on external info",
            file_path=str(req)
        )

        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["stage"] == "blocked_on_architect"
        assert len(s["decisions"]) == 1
        assert s["decisions"][0]["request"]["role"] == "draftor"
        copied = e["loop_dir"] / s["decisions"][0]["request"]["artifact_path"]
        assert copied.exists()

    def test_unblock_resolves_pending_decision(self, loop_env):
        """Escalate d1 -> unblock -> escalate d2 -> only d2 pending, d1 has response."""
        e = loop_env

        # Decision 1: escalate with reason
        loop_submit.handle_escalate(e["draftor_token"], "Need API version guidance")

        s = loop_session.load_session(e["loop_dir"])
        assert len(s["decisions"]) == 1
        assert s["decisions"][0]["response"] is None

        # Architect unblocks with a message
        loop_submit.handle_unblock(
            e["architect_token"], message="Use API v2"
        )

        s = loop_session.load_session(e["loop_dir"])
        d1 = s["decisions"][0]
        assert d1["response"] is not None
        assert d1["response"]["message"] == "Use API v2"
        assert d1["response"]["ts"]

        # Decision 2: escalate again
        loop_submit.handle_escalate(e["draftor_token"], "Need deployment target")

        s = loop_session.load_session(e["loop_dir"])
        assert len(s["decisions"]) == 2
        # d1 still resolved
        assert s["decisions"][0]["response"] is not None
        assert s["decisions"][0]["response"]["message"] == "Use API v2"
        # d2 pending
        assert s["decisions"][1]["response"] is None

        # Pending list has only d2
        pending = [d for d in s["decisions"] if d["response"] is None]
        assert len(pending) == 1
        assert pending[0]["id"] == "decision-2"

    def test_cli_escalate_bad_file_prints_error(self, loop_env):
        """CLI escalate with nonexistent --file prints error, not traceback."""
        import argparse, io, contextlib

        args = argparse.Namespace(
            token=loop_env["draftor_token"],
            reason="test",
            file=str(loop_env["tmp"] / "nonexistent.md")
        )
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            try:
                from cli import _cmd_escalate
                _cmd_escalate(args)
            except SystemExit as exc:
                assert exc.code == 1
        assert "Error:" in stderr.getvalue()
        assert "not found" in stderr.getvalue()


class TestDurableArchitectResponses:
    """Module 3: unblock --file creates durable response artifacts."""

    def test_unblock_with_file_creates_durable_response(self, loop_env):
        """Escalate with file, unblock with file -> response artifact in loop dir."""
        e = loop_env

        req = e["tmp"] / "my-request.md"
        req.write_text("# Request\n\nWhich API version?\n", encoding="utf-8")
        loop_submit.handle_escalate(
            e["draftor_token"], "Need API version", file_path=str(req)
        )

        resp = e["tmp"] / "my-response.md"
        resp.write_text("# Response\n\nUse API v2.\n", encoding="utf-8")
        loop_submit.handle_unblock(
            e["architect_token"], message="Use API v2", file_path=str(resp)
        )

        s = loop_session.load_session(e["loop_dir"])
        d = s["decisions"][0]
        assert d["response"]["message"] == "Use API v2"
        assert d["response"]["artifact_path"] == "decision-response.decision-1.md"
        assert d["response"]["ts"]

        copied = e["loop_dir"] / "decision-response.decision-1.md"
        assert copied.exists()
        assert "Use API v2" in copied.read_text(encoding="utf-8")

    def test_unblock_message_only_no_artifact(self, loop_env):
        """Escalate, unblock with --message only -> artifact_path is null."""
        e = loop_env
        loop_submit.handle_escalate(e["draftor_token"], "Need guidance")
        loop_submit.handle_unblock(
            e["architect_token"], message="Proceed with plan A"
        )

        s = loop_session.load_session(e["loop_dir"])
        d = s["decisions"][0]
        assert d["response"]["message"] == "Proceed with plan A"
        assert d["response"]["artifact_path"] is None

    def test_decisions_survive_to_terminal(self, loop_env):
        """Full loop: escalate -> unblock -> submit -> approve -> decisions intact."""
        e = loop_env

        # Escalate and unblock
        loop_submit.handle_escalate(e["draftor_token"], "Need guidance")
        loop_submit.handle_unblock(
            e["architect_token"], message="Go ahead"
        )

        # Complete the loop: draft -> review (approve)
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        loop_submit.handle_submit_review(
            e["reviewer_token"], str(e["findings_file"]), approve=True
        )

        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["stage"] == "plan_approved"
        assert len(s["decisions"]) == 1
        assert s["decisions"][0]["response"] is not None
        assert s["decisions"][0]["response"]["message"] == "Go ahead"

    def test_unblock_after_pause_no_decision_entry(self, loop_env):
        """Pause -> unblock. decisions[] is untouched (empty)."""
        e = loop_env

        from submit import handle_pause
        handle_pause(e["architect_token"], message="Taking a break")
        loop_submit.handle_unblock(e["architect_token"])

        s = loop_session.load_session(e["loop_dir"])
        assert s.get("decisions", []) == []

    def test_unblock_with_file_after_pause_rejected(self, loop_env):
        """Pause -> unblock with --file raises ValueError, stage stays paused."""
        e = loop_env

        from submit import handle_pause
        handle_pause(e["architect_token"], message="Taking a break")

        resp = e["tmp"] / "unsolicited-response.md"
        resp.write_text("# Response\n\nSome answer.\n", encoding="utf-8")

        with pytest.raises(ValueError, match="pending decision"):
            loop_submit.handle_unblock(
                e["architect_token"], message="Here's my answer",
                file_path=str(resp)
            )

        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["stage"] == "paused_by_architect"
        assert not (e["loop_dir"] / "decision-response.decision-1.md").exists()

    def test_unblock_event_includes_decision_id(self, loop_env):
        """Unblock event includes decision_id when resolving a pending decision."""
        e = loop_env
        loop_submit.handle_escalate(e["draftor_token"], "Need decision")
        loop_submit.handle_unblock(
            e["architect_token"], message="Decided"
        )

        events_file = e["loop_dir"] / "events.jsonl"
        import json
        events = [json.loads(line) for line in
                  events_file.read_text(encoding="utf-8").strip().split("\n")]
        unblock_events = [ev for ev in events if ev["event"] == "loop_unblocked"]
        assert len(unblock_events) == 1
        assert unblock_events[0]["decision_id"] == "decision-1"

    def test_unblock_file_must_exist(self, loop_env):
        """Unblock with nonexistent --file raises FileNotFoundError."""
        e = loop_env
        loop_submit.handle_escalate(e["draftor_token"], "Need decision")
        with pytest.raises(FileNotFoundError, match="not found"):
            loop_submit.handle_unblock(
                e["architect_token"], message="Here",
                file_path=str(e["tmp"] / "ghost.md")
            )

    def test_unblock_file_must_be_nonempty(self, loop_env):
        """Unblock with empty --file raises ValueError."""
        e = loop_env
        loop_submit.handle_escalate(e["draftor_token"], "Need decision")
        empty = e["tmp"] / "empty.md"
        empty.write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="empty"):
            loop_submit.handle_unblock(
                e["architect_token"], message="Here",
                file_path=str(empty)
            )


    def test_status_shows_response_artifact_after_unblock_file(self, loop_env):
        """Model status (text + JSON) shows architect_response_artifact after unblock --file."""
        import argparse, io, json, contextlib
        e = loop_env

        req = e["tmp"] / "req.md"
        req.write_text("# Request\n\nWhich API?\n", encoding="utf-8")
        loop_submit.handle_escalate(
            e["draftor_token"], "Need decision", file_path=str(req)
        )

        resp = e["tmp"] / "resp.md"
        resp.write_text("# Response\n\nUse v2.\n", encoding="utf-8")
        loop_submit.handle_unblock(
            e["architect_token"], message="Use v2", file_path=str(resp)
        )

        # Session stores relative name only (portable)
        s = loop_session.load_session(e["loop_dir"])
        raw = s["status"].get("architect_response_artifact")
        assert raw == "decision-response.decision-1.md"

        # JSON status renders absolute path (actionable)
        args = argparse.Namespace(
            token=e["draftor_token"], json=True
        )
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            try:
                from cli import _cmd_status
                _cmd_status(args)
            except SystemExit:
                pass
        out = json.loads(stdout.getvalue())
        assert out["architect_response_artifact"] is not None
        assert out["architect_response_artifact"].endswith(
            "decision-response.decision-1.md")
        # Absolute path includes the loop dir
        assert str(e["loop_dir"]) in out["architect_response_artifact"]

    def test_response_artifact_clears_after_submit(self, loop_env):
        """architect_response_artifact clears after the model submits."""
        e = loop_env

        req = e["tmp"] / "req.md"
        req.write_text("# Request\n\nWhich API?\n", encoding="utf-8")
        loop_submit.handle_escalate(
            e["draftor_token"], "Need decision", file_path=str(req)
        )

        resp = e["tmp"] / "resp.md"
        resp.write_text("# Response\n\nUse v2.\n", encoding="utf-8")
        loop_submit.handle_unblock(
            e["architect_token"], message="Use v2", file_path=str(resp)
        )

        # Model submits — artifact should clear
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))

        s = loop_session.load_session(e["loop_dir"])
        assert s["status"].get("architect_response_artifact") is None

    def test_text_only_unblock_no_response_artifact(self, loop_env):
        """Text-only unblock leaves architect_response_artifact as null."""
        e = loop_env
        loop_submit.handle_escalate(e["draftor_token"], "Need guidance")
        loop_submit.handle_unblock(
            e["architect_token"], message="Just proceed"
        )

        s = loop_session.load_session(e["loop_dir"])
        assert s["status"].get("architect_response_artifact") is None


    def test_terminal_session_has_no_absolute_artifact_path(self, loop_env):
        """If loop ends before model submits, session has relative name, not absolute."""
        e = loop_env

        req = e["tmp"] / "req.md"
        req.write_text("# Request\n\nWhich API?\n", encoding="utf-8")
        loop_submit.handle_escalate(
            e["draftor_token"], "Need decision", file_path=str(req)
        )

        resp = e["tmp"] / "resp.md"
        resp.write_text("# Response\n\nUse v2.\n", encoding="utf-8")
        loop_submit.handle_unblock(
            e["architect_token"], message="Use v2", file_path=str(resp)
        )

        # Architect ends the loop before the model submits
        from submit import handle_end
        handle_end(e["architect_token"], reason="Ending for test")

        s = loop_session.load_session(e["loop_dir"])
        raw = s["status"].get("architect_response_artifact")
        # If still present, must be relative (no path separator prefix)
        if raw is not None:
            import os
            assert not os.path.isabs(raw), (
                f"absolute path persisted in terminal session: {raw}")


class TestArtifactFormatAlignment:
    """Module 4: artifact format + uncertainty classification."""

    def test_artifact_format_contains_assumptions_field(self):
        """Plan template uses 'Assumptions, Risks, and Required Architect Decisions'."""
        from pathlib import Path
        fmt = Path(__file__).resolve().parent.parent / (
            ".gator/.includes/reference-notes/loop-artifact-formats.md"
        )
        content = fmt.read_text(encoding="utf-8")
        assert "Assumptions, Risks, and Required Architect Decisions" in content
        assert "Risks and Open Questions" not in content

    def test_protocol_classifies_uncertainty(self):
        """Protocol escalation section classifies non-blocking vs blocking."""
        from pathlib import Path
        proto = Path(__file__).resolve().parent.parent / (
            ".gator/.includes/procedures/gator-loop-protocol.md"
        )
        content = proto.read_text(encoding="utf-8")
        assert "Non-blocking" in content
        assert "Blocking" in content
        assert "Classifying uncertainty" in content

    def test_escalate_verdict_requires_cli_escalate(self):
        """Findings template documents that ESCALATE verdict needs CLI escalate."""
        from pathlib import Path
        fmt = Path(__file__).resolve().parent.parent / (
            ".gator/.includes/reference-notes/loop-artifact-formats.md"
        )
        content = fmt.read_text(encoding="utf-8")
        assert "ESCALATE verdict MUST be accompanied by" in content

    def test_decision_request_template_exists(self):
        """Artifact formats includes a Decision Request template."""
        from pathlib import Path
        fmt = Path(__file__).resolve().parent.parent / (
            ".gator/.includes/reference-notes/loop-artifact-formats.md"
        )
        content = fmt.read_text(encoding="utf-8")
        assert "## Decision Request" in content
        assert "Decision Needed" in content
        assert "Options Considered" in content
        assert "Consequence of Delay" in content

    def test_decision_response_template_exists(self):
        """Artifact formats includes a Decision Response template."""
        from pathlib import Path
        fmt = Path(__file__).resolve().parent.parent / (
            ".gator/.includes/reference-notes/loop-artifact-formats.md"
        )
        content = fmt.read_text(encoding="utf-8")
        assert "## Decision Response" in content
        assert "Rationale" in content
        assert "Next Action" in content

    def test_starter_copies_match(self):
        """Shipped template copies are byte-identical to live .includes copies."""
        from pathlib import Path
        repo = Path(__file__).resolve().parent.parent
        pairs = [
            (
                repo / ".gator/.includes/reference-notes/loop-artifact-formats.md",
                repo / "src/gator_command/templates/gator-starter/reference-notes/loop-artifact-formats.md",
            ),
            (
                repo / ".gator/.includes/procedures/gator-loop-protocol.md",
                repo / "src/gator_command/templates/gator-starter/procedures/gator-loop-protocol.md",
            ),
        ]
        for live, shipped in pairs:
            assert live.read_bytes() == shipped.read_bytes(), (
                f"{live.name}: live and shipped copies differ"
            )


class TestEscalateVerdictWarning:
    """Module 5: soft warning when findings contain ESCALATE but use submit-review."""

    def test_submit_review_warns_on_escalate_verdict(self, loop_env):
        """Findings with ESCALATE via submit-review succeeds but emits warning."""
        import io, contextlib
        e = loop_env

        # Submit draft first so reviewer can submit
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))

        # Write findings with ESCALATE verdict
        escalate_findings = e["tmp"] / "escalate-findings.md"
        escalate_findings.write_text(
            "# Review\n\n## Verdict\n\nESCALATE\n\nScope is unclear.\n",
            encoding="utf-8",
        )

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            loop_submit.handle_submit_review(
                e["reviewer_token"], str(escalate_findings)
            )

        warning = stderr.getvalue()
        assert "Warning" in warning
        assert "ESCALATE" in warning
        assert "submit-review" in warning

        # Submission still succeeded — entered revision, not blocked
        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["stage"] in ("plan_revision", "max_rounds_exceeded")

    def test_submit_review_no_warning_without_escalate(self, loop_env):
        """Normal findings via submit-review emits no warning."""
        import io, contextlib
        e = loop_env

        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            loop_submit.handle_submit_review(
                e["reviewer_token"], str(e["findings_file"])
            )

        assert stderr.getvalue() == ""

    def test_approve_no_warning_even_with_escalate_text(self, loop_env):
        """Approval with ESCALATE text in file emits no warning."""
        import io, contextlib
        e = loop_env

        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))

        findings_with_escalate = e["tmp"] / "approval-with-escalate.md"
        findings_with_escalate.write_text(
            "# Review\n\n## Verdict\n\nAPPROVE\n\n"
            "Previously considered ESCALATE but resolved.\n",
            encoding="utf-8",
        )

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            loop_submit.handle_submit_review(
                e["reviewer_token"], str(findings_with_escalate), approve=True
            )

        assert stderr.getvalue() == ""

    def test_revise_mentioning_escalate_no_warning(self, loop_env):
        """REVISE findings that casually mention 'escalate' emit no warning."""
        import io, contextlib
        e = loop_env

        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))

        findings = e["tmp"] / "revise-mention-escalate.md"
        findings.write_text(
            "# Review\n\n## Verdict\n\nREVISE\n\n"
            "Do not escalate this — handle it in the plan.\n",
            encoding="utf-8",
        )

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            loop_submit.handle_submit_review(
                e["reviewer_token"], str(findings)
            )

        assert stderr.getvalue() == ""

    def test_non_utf8_findings_submit_succeeds(self, loop_env):
        """Non-UTF-8 findings file submits successfully without exception."""
        import io, contextlib
        e = loop_env

        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))

        binary_findings = e["tmp"] / "binary-findings.md"
        content = b"# Review\n\n## Verdict\n\nREVISE\n\nBad byte: \xff\xfe here.\n"
        binary_findings.write_bytes(content)

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            loop_submit.handle_submit_review(
                e["reviewer_token"], str(binary_findings)
            )

        # Submission succeeded
        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["stage"] in ("plan_revision", "max_rounds_exceeded")


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
        """Unblocking an ordinary pause without message leaves architect_message None.

        (An escalation cannot be unblocked blank — see TestUnblockResponseContract.)
        """
        e = loop_env
        loop_submit.handle_pause(e["architect_token"])
        loop_submit.handle_unblock(e["architect_token"])

        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["architect_message"] is None


def _loop_bytes(loop_dir):
    return ((loop_dir / "session.json").read_bytes(),
            (loop_dir / "events.jsonl").read_bytes())


def _last_event(loop_dir):
    lines = (loop_dir / "events.jsonl").read_text(encoding="utf-8").strip().splitlines()
    return json.loads(lines[-1])


class TestValidateTurnTimeout:
    @pytest.mark.parametrize("good,expected", [(30, 30), (3600, 3600), (600, 600), ("600", 600), (" 45 ", 45)])
    def test_accepts_integral_in_range(self, good, expected):
        assert loop_session.validate_turn_timeout(good) == expected

    @pytest.mark.parametrize("bad", [29, 3601, 0, -30, 600.0, 600.5, True, None, "abc", "6e2", "", "-45"])
    def test_rejects_invalid(self, bad):
        with pytest.raises(ValueError):
            loop_session.validate_turn_timeout(bad)


class TestValidateRoundCount:
    @pytest.mark.parametrize("good,expected", [(1, 1), (20, 20), (2, 2), ("5", 5), (" 3 ", 3)])
    def test_accepts_integral_in_range(self, good, expected):
        assert loop_session.validate_round_count(good) == expected

    @pytest.mark.parametrize("bad", [0, 21, -1, 1.5, 2.0, True, None, "x", "", "-2", "1e1"])
    def test_rejects_invalid(self, bad):
        with pytest.raises(ValueError, match="rounds"):
            loop_session.validate_round_count(bad)

    def test_turn_timeout_messages_unchanged_by_refactor(self):
        with pytest.raises(ValueError, match="turn timeout must be between 30 and 3600 seconds"):
            loop_session.validate_turn_timeout(10)
        with pytest.raises(ValueError, match="turn timeout must be an integer number of seconds"):
            loop_session.validate_turn_timeout("fast")


def _drive_to_max_rounds(e):
    """Run real draft/review submissions until the loop hits its ceiling."""
    for _ in range(loop_session.load_session(e["loop_dir"])["status"]["max_rounds"]):
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        loop_submit.handle_submit_review(e["reviewer_token"], str(e["findings_file"]))
    s = loop_session.load_session(e["loop_dir"])
    assert s["status"]["stage"] == "max_rounds_exceeded"
    return s


class TestHandleExtend:
    """#39 M2 — durable extend transaction + loop_extended event."""

    def test_extend_resumes_and_records_audit(self, loop_env):
        e = loop_env
        before = _drive_to_max_rounds(e)
        turns_before = len(before["turns"])

        loop_id, loop_dir, prev, new = loop_submit.handle_extend(
            e["architect_token"], 2, "  Verify the revised boundary.  ")

        assert (prev, new) == (3, 5)
        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["stage"] == "plan_revision"
        assert s["status"]["next_role"] == "draftor"
        assert s["status"]["round"] == 3
        assert s["status"]["max_rounds"] == 5
        assert s["status"]["architect_message"] == "Verify the revised boundary."
        assert "extension_count" not in s["status"]

        assert len(s["turns"]) == turns_before + 1
        turn = s["turns"][-1]
        assert turn["role"] == "architect"
        assert turn["summary"] == "Verify the revised boundary."

        ev = _last_event(e["loop_dir"])
        assert ev["event"] == "loop_extended"
        assert ev["role"] == "architect"
        assert ev["round"] == 3
        assert ev["rounds_added"] == 2
        assert ev["previous_max_rounds"] == 3
        assert ev["max_rounds"] == 5
        assert ev["stage"] == "plan_revision"
        assert ev["next_role"] == "draftor"
        assert ev["reason"] == "Verify the revised boundary."
        assert "3 -> 5" in ev["detail"]
        assert "EXTENDED" in loop_events.format_event(ev)
        assert "loop_extended" not in loop_events.TERMINAL_EVENTS

    def test_resumed_loop_accepts_draftor_revision(self, loop_env):
        e = loop_env
        _drive_to_max_rounds(e)
        loop_submit.handle_extend(e["architect_token"], 1, "one more")
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["stage"] == "plan_review"
        assert s["status"]["architect_message"] is None

    def test_second_cycle_can_be_extended_again(self, loop_env):
        e = loop_env
        _drive_to_max_rounds(e)
        loop_submit.handle_extend(e["architect_token"], 1, "first extension")
        # One more draft/review cycle -> round 4 == new ceiling.
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        loop_submit.handle_submit_review(e["reviewer_token"], str(e["findings_file"]))
        assert loop_session.load_session(e["loop_dir"])["status"]["stage"] == "max_rounds_exceeded"
        _, _, prev, new = loop_submit.handle_extend(e["architect_token"], 2, "second extension")
        assert (prev, new) == (4, 6)
        events = loop_events.read_all_events(e["loop_dir"])
        ext = [(ev["previous_max_rounds"], ev["max_rounds"])
               for ev in events if ev["event"] == "loop_extended"]
        assert ext == [(3, 4), (4, 6)]

    @pytest.mark.parametrize("role", ["draftor", "reviewer"])
    def test_model_token_rejected_without_write(self, loop_env, role):
        e = loop_env
        _drive_to_max_rounds(e)
        before = _loop_bytes(e["loop_dir"])
        with pytest.raises(PermissionError, match="architect token"):
            loop_submit.handle_extend(e[f"{role}_token"], 2, "reason")
        assert _loop_bytes(e["loop_dir"]) == before

    @pytest.mark.parametrize("msg", [None, "", "   "])
    def test_blank_reason_rejected_without_write(self, loop_env, msg):
        e = loop_env
        _drive_to_max_rounds(e)
        before = _loop_bytes(e["loop_dir"])
        with pytest.raises(ValueError, match="reason"):
            loop_submit.handle_extend(e["architect_token"], 2, msg)
        assert _loop_bytes(e["loop_dir"]) == before

    @pytest.mark.parametrize("bad", [0, 21, -1, 1.5, True, "x", None])
    def test_bad_rounds_rejected_without_write(self, loop_env, bad):
        e = loop_env
        _drive_to_max_rounds(e)
        before = _loop_bytes(e["loop_dir"])
        with pytest.raises(ValueError, match="rounds"):
            loop_submit.handle_extend(e["architect_token"], bad, "reason")
        assert _loop_bytes(e["loop_dir"]) == before

    def _to_stage(self, e, stage):
        if stage == "plan_approved":
            loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
            loop_submit.handle_submit_review(e["reviewer_token"], str(e["findings_file"]),
                                             approve=True)
        elif stage == "turn_timed_out":
            from host import _try_enforce_timeout
            s = loop_session.load_session(e["loop_dir"])
            s["status"]["turn_deadline"] = (
                datetime.now(tz=timezone.utc) - timedelta(seconds=10)).isoformat()
            loop_session.save_session(e["loop_dir"], s)
            _try_enforce_timeout(e["loop_dir"])
        elif stage == "ended_by_architect":
            loop_submit.handle_end(e["architect_token"])
        elif stage == "paused_by_architect":
            loop_submit.handle_pause(e["architect_token"])
        elif stage == "blocked_on_architect":
            loop_submit.handle_escalate(e["draftor_token"], "need input")
        # "plan_drafting": fresh loop, nothing to do
        assert loop_session.load_session(e["loop_dir"])["status"]["stage"] == stage

    @pytest.mark.parametrize("stage", [
        "plan_approved", "turn_timed_out", "ended_by_architect",
        "plan_drafting", "paused_by_architect", "blocked_on_architect",
    ])
    def test_non_extendable_stage_rejected_without_write(self, loop_env, stage):
        e = loop_env
        self._to_stage(e, stage)
        before = _loop_bytes(e["loop_dir"])
        with pytest.raises(PermissionError, match="round limit"):
            loop_submit.handle_extend(e["architect_token"], 2, "reason")
        assert _loop_bytes(e["loop_dir"]) == before


class TestWatchLoopReplay:
    """#39 M3 — terminal detection is session-authoritative."""

    def _start_watcher(self, loop_dir, monkeypatch):
        import threading
        import host as loop_host
        monkeypatch.setattr(loop_host, "POLL_INTERVAL", 0.05)
        t = threading.Thread(target=loop_host.watch_loop, args=(loop_dir,), daemon=True)
        t.start()
        return t

    def test_replayed_terminal_event_does_not_end_live_watcher(self, loop_env, monkeypatch):
        import host as loop_host
        e = loop_env
        _drive_to_max_rounds(e)
        loop_host.extend_loop(e["architect_token"], 2, "continue")
        events = [ev["event"] for ev in loop_events.read_all_events(e["loop_dir"])]
        assert events.index("max_rounds_exceeded") < events.index("loop_extended")

        t = self._start_watcher(e["loop_dir"], monkeypatch)
        t.join(timeout=0.6)
        assert t.is_alive(), "watcher exited on a historical terminal event"

        loop_submit.handle_end(e["architect_token"])  # a real terminal state
        t.join(timeout=5)
        assert not t.is_alive(), "watcher must exit once the session is terminal"

    def test_real_terminal_still_exits(self, loop_env, monkeypatch):
        e = loop_env
        _drive_to_max_rounds(e)
        t = self._start_watcher(e["loop_dir"], monkeypatch)
        t.join(timeout=5)
        assert not t.is_alive()

    def test_unreadable_session_fails_safe_to_terminal(self, tmp_path):
        import host as loop_host
        assert loop_host._session_is_terminal(tmp_path / "missing-loop") is True


class TestHostLockRetry:
    """#39 M3 — watcher attachment states."""

    def test_free_lock_attaches(self, loop_env):
        import host as loop_host
        fd, state, detail = loop_host.acquire_host_lock_with_retry(
            loop_env["loop_dir"], attempts=3, delay=0, sleep=lambda s: None)
        try:
            assert state == loop_host.HOST_ATTACHED and fd is not None and detail is None
        finally:
            loop_host.release_host_lock(fd)

    def test_held_lock_reports_already_hosted_without_second_fd(self, loop_env):
        import host as loop_host
        holder = loop_host.acquire_host_lock(loop_env["loop_dir"])
        assert holder is not None
        sleeps = []
        try:
            fd, state, detail = loop_host.acquire_host_lock_with_retry(
                loop_env["loop_dir"], attempts=3, delay=0.2, sleep=sleeps.append)
            assert fd is None
            assert state == loop_host.HOST_ALREADY_HOSTED
            assert "host.lock held" in detail
            assert sleeps == [0.2, 0.2], "retries between attempts only"
        finally:
            loop_host.release_host_lock(holder)

    def test_release_during_retry_window_attaches(self, loop_env):
        import host as loop_host
        holder = [loop_host.acquire_host_lock(loop_env["loop_dir"])]

        def releasing_sleep(_s):
            if holder[0] is not None:
                loop_host.release_host_lock(holder[0])  # terminal watcher exits
                holder[0] = None

        fd, state, _ = loop_host.acquire_host_lock_with_retry(
            loop_env["loop_dir"], attempts=5, delay=0.2, sleep=releasing_sleep)
        try:
            assert state == loop_host.HOST_ATTACHED and fd is not None
        finally:
            loop_host.release_host_lock(fd)

    def test_open_error_fails_immediately(self, loop_env, monkeypatch):
        import host as loop_host

        def boom(*a, **k):
            raise OSError("disk says no")

        monkeypatch.setattr(loop_host.os, "open", boom)
        sleeps = []
        fd, state, detail = loop_host.acquire_host_lock_with_retry(
            loop_env["loop_dir"], attempts=5, delay=0.2, sleep=sleeps.append)
        assert (fd, state) == (None, loop_host.HOST_FAILED)
        assert "disk says no" in detail
        assert sleeps == []

    def test_acquire_host_lock_contract_unchanged(self, loop_env):
        import host as loop_host
        first = loop_host.acquire_host_lock(loop_env["loop_dir"])
        try:
            assert first is not None
            assert loop_host.acquire_host_lock(loop_env["loop_dir"]) is None
        finally:
            loop_host.release_host_lock(first)

    def test_read_host_metadata_best_effort(self, loop_env):
        import host as loop_host
        lock_file = loop_env["loop_dir"] / loop_host.HOST_LOCK_FILENAME
        assert loop_host.read_host_metadata(loop_env["loop_dir"]) is None  # absent
        lock_file.write_text('{"pid": 4242, "nonce": "ab"}', encoding="utf-8")
        assert loop_host.read_host_metadata(loop_env["loop_dir"])["pid"] == 4242
        lock_file.write_text("not json", encoding="utf-8")
        assert loop_host.read_host_metadata(loop_env["loop_dir"]) is None


class TestExtendLoopGuard:
    """#39 M3 — extension holds start.lock and keeps one active loop per repo."""

    def _start_lock_free(self, loops_base):
        import host as loop_host
        fd = loop_host.acquire_start_lock(loops_base)
        if fd is None:
            return False
        loop_host.release_start_lock(fd)
        return True

    def test_extend_success_releases_start_lock(self, loop_env):
        import host as loop_host
        e = loop_env
        _drive_to_max_rounds(e)
        loop_id, loop_dir, prev, new = loop_host.extend_loop(e["architect_token"], 2, "go")
        assert (loop_id, prev, new) == (e["loop_id"], 3, 5)
        assert self._start_lock_free(e["loop_dir"].parent)

    def test_rejected_when_another_loop_is_active(self, loop_env):
        import host as loop_host
        e = loop_env
        _drive_to_max_rounds(e)
        other = e["loop_dir"].parent / "other-active-loop"
        other.mkdir()
        loop_session.save_session(other, loop_session.create_session(
            "other", "other-active-loop", max_rounds=3, turn_timeout=300))
        before = _loop_bytes(e["loop_dir"])
        with pytest.raises(RuntimeError, match="active loop already exists: other-active-loop"):
            loop_host.extend_loop(e["architect_token"], 2, "go")
        assert _loop_bytes(e["loop_dir"]) == before
        assert self._start_lock_free(e["loop_dir"].parent)

    def test_rejected_while_start_lock_held(self, loop_env):
        import host as loop_host
        e = loop_env
        _drive_to_max_rounds(e)
        held = loop_host.acquire_start_lock(e["loop_dir"].parent)
        before = _loop_bytes(e["loop_dir"])
        try:
            with pytest.raises(RuntimeError, match="in progress"):
                loop_host.extend_loop(e["architect_token"], 2, "go")
        finally:
            loop_host.release_start_lock(held)
        assert _loop_bytes(e["loop_dir"]) == before

    def test_handler_rejection_propagates_and_releases_start_lock(self, loop_env):
        import host as loop_host
        e = loop_env
        _drive_to_max_rounds(e)
        before = _loop_bytes(e["loop_dir"])
        with pytest.raises(ValueError, match="reason"):
            loop_host.extend_loop(e["architect_token"], 2, "   ")
        with pytest.raises(PermissionError, match="architect token"):
            loop_host.extend_loop(e["draftor_token"], 2, "go")
        assert _loop_bytes(e["loop_dir"]) == before
        assert self._start_lock_free(e["loop_dir"].parent)

    def test_invalid_token_rejected_before_locking(self, loop_env):
        import host as loop_host
        with pytest.raises(ValueError):
            loop_host.extend_loop("not-a-token", 2, "go")
        assert self._start_lock_free(loop_env["loop_dir"].parent)


class TestCliExtend:
    """#39 M4 — `gator loop extend` with the always-attach host contract."""

    def _fast_retry(self, monkeypatch):
        import host as loop_host
        orig = loop_host.acquire_host_lock_with_retry
        monkeypatch.setattr(
            loop_host, "acquire_host_lock_with_retry",
            lambda loop_dir: orig(loop_dir, attempts=2, delay=0, sleep=lambda s: None))

    def _lock_is_free(self, loop_dir):
        import host as loop_host
        fd = loop_host.acquire_host_lock(loop_dir)
        if fd is None:
            return False
        loop_host.release_host_lock(fd)
        return True

    @pytest.mark.parametrize("argv", [
        ["--rounds", "2"],                       # missing --message
        ["--message", "go"],                     # missing --rounds
        ["--rounds", "0", "--message", "go"],
        ["--rounds", "21", "--message", "go"],
        ["--rounds", "x", "--message", "go"],
    ])
    def test_usage_errors_exit_2_without_write(self, loop_env, argv):
        from cli import main
        e = loop_env
        _drive_to_max_rounds(e)
        before = _loop_bytes(e["loop_dir"])
        with pytest.raises(SystemExit) as exc:
            main(["extend", "--token", e["architect_token"]] + argv)
        assert exc.value.code == 2
        assert _loop_bytes(e["loop_dir"]) == before

    def test_attached_runs_foreground_watcher_and_releases_lock(self, loop_env, monkeypatch, capsys):
        import host as loop_host
        from cli import main
        e = loop_env
        _drive_to_max_rounds(e)
        seen = {}

        def fake_watch(loop_dir, host_lock_fd=None):
            seen["fd"] = host_lock_fd
            seen["held"] = not self._lock_is_free(loop_dir)

        monkeypatch.setattr(loop_host, "watch_loop", fake_watch)
        main(["extend", "--token", e["architect_token"], "--rounds", "2",
              "--message", "Verify boundaries"])

        out = capsys.readouterr().out
        assert "Extended: max rounds 3 -> 5 (round 3)." in out
        assert "Resumed to plan_revision (next: draftor)." in out
        assert "re-engaged" in out
        assert "watching in the foreground" in out
        assert seen["fd"] is not None and seen["held"] is True
        assert self._lock_is_free(e["loop_dir"]), "host.lock must be released after watching"
        assert loop_session.load_session(e["loop_dir"])["status"]["stage"] == "plan_revision"

    def test_ctrl_c_reports_enforcement_stopped_and_releases(self, loop_env, monkeypatch, capsys):
        import host as loop_host
        from cli import main
        e = loop_env
        _drive_to_max_rounds(e)

        def interrupted(loop_dir, host_lock_fd=None):
            raise KeyboardInterrupt

        monkeypatch.setattr(loop_host, "watch_loop", interrupted)
        main(["extend", "--token", e["architect_token"], "--rounds", "1", "--message", "go"])
        assert "no longer enforced" in capsys.readouterr().out
        assert self._lock_is_free(e["loop_dir"])

    def test_already_hosted_exits_0_without_second_watcher(self, loop_env, monkeypatch, capsys):
        import host as loop_host
        from cli import main
        e = loop_env
        _drive_to_max_rounds(e)
        self._fast_retry(monkeypatch)
        monkeypatch.setattr(loop_host, "watch_loop",
                            lambda *a, **k: pytest.fail("must not start a second watcher"))
        holder = loop_host.acquire_host_lock(e["loop_dir"])
        try:
            main(["extend", "--token", e["architect_token"], "--rounds", "2", "--message", "go"])
        finally:
            loop_host.release_host_lock(holder)
        assert "already hosted" in capsys.readouterr().out
        assert loop_session.load_session(e["loop_dir"])["status"]["max_rounds"] == 5

    def test_attach_failure_keeps_extension_and_exits_1(self, loop_env, monkeypatch, capsys):
        import host as loop_host
        from cli import main
        e = loop_env
        _drive_to_max_rounds(e)
        monkeypatch.setattr(loop_host, "acquire_host_lock_with_retry",
                            lambda loop_dir: (None, loop_host.HOST_FAILED, "open failed: nope"))
        with pytest.raises(SystemExit) as exc:
            main(["extend", "--token", e["architect_token"], "--rounds", "2", "--message", "go"])
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "NOT being enforced" in err and "open failed: nope" in err
        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["stage"] == "plan_revision" and s["status"]["max_rounds"] == 5

    def test_rejected_extension_exits_1_before_any_host_step(self, loop_env, monkeypatch, capsys):
        import host as loop_host
        from cli import main
        e = loop_env  # fresh loop: plan_drafting, not extendable
        monkeypatch.setattr(loop_host, "acquire_host_lock_with_retry",
                            lambda *a, **k: pytest.fail("no host step after a rejection"))
        before = _loop_bytes(e["loop_dir"])
        with pytest.raises(SystemExit) as exc:
            main(["extend", "--token", e["architect_token"], "--rounds", "2", "--message", "go"])
        assert exc.value.code == 1
        assert "Rejected:" in capsys.readouterr().err
        assert _loop_bytes(e["loop_dir"]) == before

    def test_blank_message_is_an_error(self, loop_env, capsys):
        from cli import main
        e = loop_env
        _drive_to_max_rounds(e)
        with pytest.raises(SystemExit) as exc:
            main(["extend", "--token", e["architect_token"], "--rounds", "2", "--message", "  "])
        assert exc.value.code == 1
        assert "reason" in capsys.readouterr().err

    def test_architect_status_shows_extend_hint_only_at_max_rounds(self, loop_env, capsys):
        from cli import main
        e = loop_env
        _drive_to_max_rounds(e)
        with pytest.raises(SystemExit):
            main(["status", "--token", e["architect_token"]])
        assert "gator loop extend --token" in capsys.readouterr().out

    def test_no_extend_hint_for_other_terminal(self, loop_env, capsys):
        from cli import main
        e = loop_env
        loop_submit.handle_end(e["architect_token"])
        with pytest.raises(SystemExit):
            main(["status", "--token", e["architect_token"]])
        assert "gator loop extend" not in capsys.readouterr().out


class TestUnblockTurnWindow:
    def test_timeout_persists_and_sets_fresh_deadline(self, loop_env):
        e = loop_env
        loop_submit.handle_pause(e["architect_token"])
        loop_submit.handle_unblock(e["architect_token"], turn_timeout=900)

        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["turn_timeout_seconds"] == 900
        remaining = (datetime.fromisoformat(s["status"]["turn_deadline"])
                     - datetime.now(tz=timezone.utc)).total_seconds()
        assert 800 < remaining <= 900

        ev = _last_event(e["loop_dir"])
        assert ev["event"] == "loop_unblocked"
        assert ev["turn_timeout_seconds"] == 900
        assert ev["previous_turn_timeout_seconds"] == 300
        assert "300s -> 900s" in ev["detail"]

    def test_new_timeout_applies_to_next_transition(self, loop_env):
        e = loop_env
        loop_submit.handle_pause(e["architect_token"])
        loop_submit.handle_unblock(e["architect_token"], turn_timeout=1200)
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))

        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["turn_timeout_seconds"] == 1200
        remaining = (datetime.fromisoformat(s["status"]["turn_deadline"])
                     - datetime.now(tz=timezone.utc)).total_seconds()
        assert 1100 < remaining <= 1200

    def test_omitted_timeout_keeps_current_window(self, loop_env):
        e = loop_env
        loop_submit.handle_pause(e["architect_token"])
        loop_submit.handle_unblock(e["architect_token"])
        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["turn_timeout_seconds"] == 300
        ev = _last_event(e["loop_dir"])
        assert ev["turn_timeout_seconds"] == 300
        assert "previous_turn_timeout_seconds" not in ev

    @pytest.mark.parametrize("bad", [10, 7200, 600.5, "fast", True])
    def test_invalid_timeout_rejected_without_state_change(self, loop_env, bad):
        e = loop_env
        loop_submit.handle_pause(e["architect_token"])
        before = _loop_bytes(e["loop_dir"])
        with pytest.raises(ValueError):
            loop_submit.handle_unblock(e["architect_token"], turn_timeout=bad)
        assert _loop_bytes(e["loop_dir"]) == before

    def test_cli_rejects_out_of_range_timeout_as_usage_error(self, loop_env):
        from cli import main
        loop_submit.handle_pause(loop_env["architect_token"])
        with pytest.raises(SystemExit) as exc:
            main(["unblock", "--token", loop_env["architect_token"], "--timeout", "5"])
        assert exc.value.code == 2

    def test_cli_unblock_timeout_and_status_shows_window(self, loop_env, capsys):
        from cli import main
        e = loop_env
        loop_submit.handle_pause(e["architect_token"])
        main(["unblock", "--token", e["architect_token"], "--timeout", "600"])
        out = capsys.readouterr().out
        assert "Turn window: 600s" in out

        with pytest.raises(SystemExit) as exc:
            main(["status", "--token", e["draftor_token"]])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "Turn window: 600s" in out

        with pytest.raises(SystemExit):
            main(["status", "--token", e["draftor_token"], "--json"])
        data = json.loads(capsys.readouterr().out)
        assert data["turn_timeout_seconds"] == 600
        assert data["turn_deadline"]


class TestUnblockResponseContract:
    def _escalate(self, e):
        loop_submit.handle_escalate(e["draftor_token"], "Need a scope decision")

    def test_blank_unblock_of_escalation_rejected_without_state_change(self, loop_env):
        e = loop_env
        self._escalate(e)
        before = _loop_bytes(e["loop_dir"])
        for msg in (None, "", "   "):
            with pytest.raises(ValueError, match="response is required"):
                loop_submit.handle_unblock(e["architect_token"], message=msg)
        assert _loop_bytes(e["loop_dir"]) == before

    def test_blank_rejection_also_leaves_timeout_untouched(self, loop_env):
        e = loop_env
        self._escalate(e)
        with pytest.raises(ValueError):
            loop_submit.handle_unblock(e["architect_token"], turn_timeout=900)
        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["turn_timeout_seconds"] == 300
        assert s["status"]["stage"] == "blocked_on_architect"

    def test_message_response(self, loop_env):
        e = loop_env
        self._escalate(e)
        loop_submit.handle_unblock(e["architect_token"], message="Narrow to #35 only.")
        s = loop_session.load_session(e["loop_dir"])
        resp = s["decisions"][0]["response"]
        assert resp["message"] == "Narrow to #35 only."
        assert resp["artifact_path"] is None
        assert resp["kind"] == "message"
        assert s["status"]["architect_message"] == "Narrow to #35 only."
        ev = _last_event(e["loop_dir"])
        assert ev["decision_id"] == "decision-1"
        assert ev["response_kind"] == "message"

    def test_artifact_only_response_is_meaningful(self, loop_env, tmp_path):
        e = loop_env
        self._escalate(e)
        resp_file = tmp_path / "response.md"
        resp_file.write_text("# Decision Response\n\nProceed.\n", encoding="utf-8")
        loop_submit.handle_unblock(e["architect_token"], file_path=str(resp_file))
        s = loop_session.load_session(e["loop_dir"])
        resp = s["decisions"][0]["response"]
        assert resp["message"] is None
        assert resp["artifact_path"] == "decision-response.decision-1.md"
        assert resp["kind"] == "artifact"
        assert s["status"]["architect_message"] == loop_submit.ARTIFACT_ONLY_RESPONSE_SUMMARY
        assert s["status"]["architect_response_artifact"] == "decision-response.decision-1.md"
        ev = _last_event(e["loop_dir"])
        assert loop_submit.ARTIFACT_ONLY_RESPONSE_SUMMARY in ev["detail"]
        assert ev["response_kind"] == "artifact"

    def test_message_and_artifact_response(self, loop_env, tmp_path):
        e = loop_env
        self._escalate(e)
        resp_file = tmp_path / "response.md"
        resp_file.write_text("# Decision Response\n", encoding="utf-8")
        loop_submit.handle_unblock(e["architect_token"], message="See doc.",
                                   file_path=str(resp_file))
        resp = loop_session.load_session(e["loop_dir"])["decisions"][0]["response"]
        assert resp["kind"] == "message_and_artifact"
        assert resp["message"] == "See doc."

    def test_deliberate_empty_is_distinct_from_omitted(self, loop_env):
        e = loop_env
        self._escalate(e)
        loop_submit.handle_unblock(e["architect_token"], no_response=True)
        s = loop_session.load_session(e["loop_dir"])
        resp = s["decisions"][0]["response"]
        assert resp["kind"] == "deliberate_empty"
        assert resp["message"] is None and resp["artifact_path"] is None
        assert s["status"]["architect_message"] == loop_submit.DELIBERATE_EMPTY_RESPONSE_SUMMARY
        assert _last_event(e["loop_dir"])["response_kind"] == "deliberate_empty"

    def test_no_response_mutually_exclusive(self, loop_env, tmp_path):
        e = loop_env
        self._escalate(e)
        resp_file = tmp_path / "response.md"
        resp_file.write_text("x\n", encoding="utf-8")
        with pytest.raises(ValueError, match="mutually exclusive"):
            loop_submit.handle_unblock(e["architect_token"], message="hi", no_response=True)
        with pytest.raises(ValueError, match="mutually exclusive"):
            loop_submit.handle_unblock(e["architect_token"], file_path=str(resp_file),
                                       no_response=True)

    def test_no_response_rejected_for_ordinary_pause(self, loop_env):
        e = loop_env
        loop_submit.handle_pause(e["architect_token"])
        before = _loop_bytes(e["loop_dir"])
        with pytest.raises(ValueError, match="no outstanding decisions"):
            loop_submit.handle_unblock(e["architect_token"], no_response=True)
        assert _loop_bytes(e["loop_dir"]) == before

    def test_ordinary_pause_unblocks_without_response(self, loop_env):
        e = loop_env
        loop_submit.handle_pause(e["architect_token"])
        loop_submit.handle_unblock(e["architect_token"])
        s = loop_session.load_session(e["loop_dir"])
        assert s["status"]["stage"] == "plan_drafting"
        ev = _last_event(e["loop_dir"])
        assert "response_kind" not in ev

    def test_cli_no_response_flag(self, loop_env, capsys):
        from cli import main
        e = loop_env
        self._escalate(e)
        main(["unblock", "--token", e["architect_token"], "--no-response"])
        resp = loop_session.load_session(e["loop_dir"])["decisions"][0]["response"]
        assert resp["kind"] == "deliberate_empty"

    def test_cli_blank_unblock_of_escalation_errors(self, loop_env, capsys):
        from cli import main
        e = loop_env
        self._escalate(e)
        with pytest.raises(SystemExit) as exc:
            main(["unblock", "--token", e["architect_token"]])
        assert exc.value.code == 1
        assert "response is required" in capsys.readouterr().err

    def test_architect_status_states_response_required(self, loop_env, capsys):
        from cli import main
        e = loop_env
        self._escalate(e)
        with pytest.raises(SystemExit):
            main(["status", "--token", e["architect_token"]])
        out = capsys.readouterr().out
        assert "Response required" in out
        assert "--no-response" in out
        assert "Turn window: 300s" in out


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

    def test_model_cannot_interject(self, loop_env):
        """Model token rejected for interject command."""
        with pytest.raises(PermissionError, match="architect token"):
            loop_submit.handle_interject(loop_env["draftor_token"], "test")

    def test_model_cannot_end(self, loop_env):
        """Model token rejected for end command."""
        with pytest.raises(PermissionError, match="architect token"):
            loop_submit.handle_end(loop_env["draftor_token"])

    def test_model_cannot_unblock(self, loop_env):
        """Model token rejected for unblock command."""
        loop_submit.handle_escalate(loop_env["draftor_token"], "test")
        with pytest.raises(PermissionError, match="architect token"):
            loop_submit.handle_unblock(loop_env["draftor_token"])

    def test_reviewer_cannot_pause(self, loop_env):
        """Reviewer token also rejected for architect commands."""
        with pytest.raises(PermissionError, match="architect token"):
            loop_submit.handle_pause(loop_env["reviewer_token"])

    def test_reviewer_cannot_interject(self, loop_env):
        """Reviewer token rejected for interject command."""
        with pytest.raises(PermissionError, match="architect token"):
            loop_submit.handle_interject(loop_env["reviewer_token"], "test")

    def test_reviewer_cannot_end(self, loop_env):
        """Reviewer token rejected for end command."""
        with pytest.raises(PermissionError, match="architect token"):
            loop_submit.handle_end(loop_env["reviewer_token"])

    def test_reviewer_cannot_unblock(self, loop_env):
        """Reviewer token rejected for unblock command."""
        loop_submit.handle_escalate(loop_env["draftor_token"], "test")
        with pytest.raises(PermissionError, match="architect token"):
            loop_submit.handle_unblock(loop_env["reviewer_token"])

    def test_handler_with_explicit_loop_dir_rejects_model(self, loop_env):
        """Model token rejected even when explicit loop_dir provided."""
        with pytest.raises(PermissionError, match="architect token"):
            loop_submit.handle_pause(
                loop_env["draftor_token"],
                loop_dir=loop_env["loop_dir"])

    def test_handler_with_explicit_loop_dir_accepts_architect(self, loop_env):
        """Architect token succeeds with explicit loop_dir."""
        loop_submit.handle_pause(
            loop_env["architect_token"],
            loop_dir=loop_env["loop_dir"])
        s = loop_session.load_session(loop_env["loop_dir"])
        assert s["status"]["stage"] == "paused_by_architect"


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


class _FakeClock:
    """Deterministic monotonic clock + sleep for bounded-wait tests.

    `on_sleep` (optional) runs after each sleep with the call index, so a
    test can change loop state "during" the wait without real threads.
    """

    def __init__(self, on_sleep=None):
        self.now = 1000.0
        self.sleeps = []
        self.on_sleep = on_sleep

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds
        if self.on_sleep:
            self.on_sleep(len(self.sleeps))


class TestBoundedWait:
    """`gator loop wait --max-seconds` (#36 short-term slice)."""

    def _wait(self, loop_env, role, clock, max_seconds, poll=2.0):
        from cli import _wait_for_actionable
        from state_machine import is_terminal, is_paused
        return _wait_for_actionable(
            loop_env["loop_dir"], role, poll,
            loop_session.load_session, is_terminal, is_paused,
            max_seconds=max_seconds, clock=clock.clock, sleep=clock.sleep,
        )

    def test_already_actionable_returns_without_sleeping(self, loop_env):
        fc = _FakeClock()
        _, reason = self._wait(loop_env, "draftor", fc, max_seconds=45)
        assert reason == "already_your_turn"
        assert fc.sleeps == []

    def test_becomes_actionable_before_deadline(self, loop_env):
        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))

        def reviewer_submits(n):
            if n == 2:
                loop_submit.handle_submit_review(e["reviewer_token"], str(e["findings_file"]))

        fc = _FakeClock(on_sleep=reviewer_submits)
        _, reason = self._wait(e, "draftor", fc, max_seconds=45)
        assert reason == "became_your_turn"
        assert fc.sleeps == [2.0, 2.0]

    def test_turn_change_at_deadline_wins_over_still_waiting(self, loop_env):
        """The session is re-read after the final capped sleep."""
        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))

        def reviewer_submits_on_last_sleep(n):
            if n == 3:
                loop_submit.handle_submit_review(e["reviewer_token"], str(e["findings_file"]))

        fc = _FakeClock(on_sleep=reviewer_submits_on_last_sleep)
        _, reason = self._wait(e, "draftor", fc, max_seconds=5)
        assert reason == "became_your_turn"

    def test_deadline_returns_still_waiting_without_overrun(self, loop_env):
        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        session_before = (e["loop_dir"] / "session.json").read_bytes()
        events_before = (e["loop_dir"] / "events.jsonl").read_bytes()

        fc = _FakeClock()
        session, reason = self._wait(e, "draftor", fc, max_seconds=5)

        assert reason == "still_waiting"
        assert session["status"]["next_role"] == "reviewer"
        # Final sleep is capped at the remaining time: 2 + 2 + 1, never 2 + 2 + 2.
        assert fc.sleeps == [2.0, 2.0, 1.0]
        assert sum(fc.sleeps) == 5
        assert (e["loop_dir"] / "session.json").read_bytes() == session_before
        assert (e["loop_dir"] / "events.jsonl").read_bytes() == events_before

    def test_pause_preempts_deadline(self, loop_env):
        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))

        def architect_pauses(n):
            if n == 1:
                loop_submit.handle_pause(e["architect_token"])

        fc = _FakeClock(on_sleep=architect_pauses)
        _, reason = self._wait(e, "draftor", fc, max_seconds=45)
        assert reason == "paused"
        assert fc.sleeps == [2.0]

    def test_terminal_preempts_deadline(self, loop_env):
        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))

        def architect_ends(n):
            if n == 1:
                loop_submit.handle_end(e["architect_token"])

        fc = _FakeClock(on_sleep=architect_ends)
        _, reason = self._wait(e, "draftor", fc, max_seconds=45)
        assert reason == "terminal"

    @pytest.mark.parametrize("bad", ["0", "-1", "nan", "inf", "abc", ""])
    def test_positive_seconds_rejects_invalid(self, bad):
        import argparse
        from cli import _positive_seconds
        with pytest.raises(argparse.ArgumentTypeError):
            _positive_seconds(bad)

    def test_parser_rejects_nonpositive_max_seconds(self, loop_env):
        from cli import main
        with pytest.raises(SystemExit) as exc:
            main(["wait", "--token", loop_env["draftor_token"], "--max-seconds", "0"])
        assert exc.value.code == 2

    def test_cmd_wait_rejects_invalid_max_seconds_before_polling(self, loop_env, capsys):
        import argparse
        from cli import _cmd_wait
        args = argparse.Namespace(
            token=loop_env["draftor_token"], json=False, poll=0.01, max_seconds=-3,
        )
        with pytest.raises(SystemExit) as exc:
            _cmd_wait(args)
        assert exc.value.code == 2
        assert "--max-seconds" in capsys.readouterr().err

    def _run_cmd_wait(self, loop_env, as_json):
        import argparse, io, contextlib
        from cli import _cmd_wait
        e = loop_env
        loop_submit.handle_submit_draft(e["draftor_token"], str(e["draft_file"]))
        args = argparse.Namespace(
            token=e["draftor_token"], json=as_json, poll=0.01, max_seconds=0.05,
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with pytest.raises(SystemExit) as exc:
                _cmd_wait(args)
        return exc.value.code, output.getvalue()

    def test_cmd_wait_still_waiting_text_exit_3_with_reissue(self, loop_env):
        from cli import WAIT_EXIT_STILL_WAITING
        code, text = self._run_cmd_wait(loop_env, as_json=False)
        assert code == WAIT_EXIT_STILL_WAITING == 3
        assert "Still waiting" in text
        assert f"gator loop wait --token {loop_env['draftor_token']} --max-seconds 0.05" in text
        assert "Your turn: NO" in text

    def test_cmd_wait_still_waiting_json(self, loop_env):
        code, raw = self._run_cmd_wait(loop_env, as_json=True)
        data = json.loads(raw)
        assert code == 3
        assert data["schema"] == "gator-loop-status-v1"
        assert data["wake_reason"] == "still_waiting"
        assert data["your_turn"] is False
        assert data["max_seconds"] == 0.05
        assert isinstance(data["waited_seconds"], float)
        assert data["reissue_command"].endswith("--max-seconds 0.05")

    def test_cmd_wait_unbounded_json_has_null_bounded_fields(self, loop_env):
        import argparse, io, contextlib
        from cli import _cmd_wait
        args = argparse.Namespace(token=loop_env["draftor_token"], json=True, poll=0.1)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with pytest.raises(SystemExit) as exc:
                _cmd_wait(args)
        data = json.loads(output.getvalue())
        assert exc.value.code == 0
        assert data["wake_reason"] == "already_your_turn"
        assert data["max_seconds"] is None
        assert data["reissue_command"] is None


class TestGitignore:
    def test_tokens_gitignored(self, loop_env):
        """loops/.gitignore includes .tokens.json."""
        gi = (loop_env["loop_dir"].parent / ".gitignore").read_text(encoding="utf-8")
        assert ".tokens.json" in gi
        assert "session.lock" in gi


# ===========================================================================
# Content-pin tests: participant-facing instructions reference `wait`
# ===========================================================================

TEMPLATES_DIR = Path(__file__).parent.parent / "src" / "gator_command" / "templates" / "gator-starter"
INCLUDES_DIR = Path(__file__).parent.parent / ".gator" / ".includes"


class TestWaitHandoffAlignment:
    """All participant-facing surfaces must teach `gator loop wait`."""

    def test_loop_join_template_references_wait(self):
        """Slash-command template tells not-up participants to use wait."""
        text = (TEMPLATES_DIR / "commands" / "loop-join.md").read_text(encoding="utf-8")
        assert "gator loop wait" in text
        assert "Report your status and wait" not in text

    def test_protocol_references_wait_in_rule_1(self):
        """Protocol Rule 1 tells participants to run wait on exit code 1."""
        for base in [INCLUDES_DIR / "procedures", TEMPLATES_DIR / "procedures"]:
            text = (base / "gator-loop-protocol.md").read_text(encoding="utf-8")
            assert "gator loop wait" in text
            assert "Do not poll in a tight loop" not in text

    def test_protocol_quick_reference_mentions_wait(self):
        """Quick Reference section mentions the bounded wait command for exit code 1."""
        for base in [INCLUDES_DIR / "procedures", TEMPLATES_DIR / "procedures"]:
            text = (base / "gator-loop-protocol.md").read_text(encoding="utf-8")
            assert "`gator loop wait --token <token> --max-seconds 45`" in text

    def _participant_surfaces(self):
        gatorize_dir = str(Path(__file__).parent.parent / "src" / "gator_command" / "scripts" / "gatorize")
        if gatorize_dir not in sys.path:
            sys.path.insert(0, gatorize_dir)
        from entry_points import render_entry_content
        repo_root = Path(__file__).parent.parent
        surfaces = {
            "render_entry_content": render_entry_content(has_command_post=False),
            "loop-join template": (TEMPLATES_DIR / "commands" / "loop-join.md").read_text(encoding="utf-8"),
            "loop-join live": (repo_root / ".claude" / "commands" / "loop-join.md").read_text(encoding="utf-8"),
            "protocol (.includes)": (INCLUDES_DIR / "procedures" / "gator-loop-protocol.md").read_text(encoding="utf-8"),
            "protocol (template)": (TEMPLATES_DIR / "procedures" / "gator-loop-protocol.md").read_text(encoding="utf-8"),
        }
        for name in ["CLAUDE.md", "AGENTS.md", "GEMINI.md"]:
            surfaces[name] = (repo_root / name).read_text(encoding="utf-8")
        return surfaces

    def test_all_surfaces_teach_bounded_wait_and_reissue(self):
        """Every participant surface teaches the bounded wait and the exit-3 reissue path."""
        for name, text in self._participant_surfaces().items():
            assert "--max-seconds 45" in text, f"{name} missing bounded wait"
            assert "exit 3" in text.lower() or "exits 3" in text.lower() or "`3`" in text, (
                f"{name} missing exit-3 guidance"
            )
            assert "reissue" in text.lower(), f"{name} missing reissue instruction"
            # No surface may still teach the bare unbounded form as the participant path.
            assert "`gator loop wait --token <your-token>`" not in text, f"{name} teaches unbounded wait"
            assert "`gator loop wait --token <token>`" not in text, f"{name} teaches unbounded wait"

    def test_loop_join_live_copy_matches_template(self):
        """The repo's live /loop-join command is byte-identical to the shipped template."""
        repo_root = Path(__file__).parent.parent
        live = (repo_root / ".claude" / "commands" / "loop-join.md").read_bytes()
        template = (TEMPLATES_DIR / "commands" / "loop-join.md").read_bytes()
        assert live == template

    def test_entry_point_rendering_references_wait(self):
        """render_entry_content() output includes wait instruction."""
        gatorize_dir = str(Path(__file__).parent.parent / "src" / "gator_command" / "scripts" / "gatorize")
        if gatorize_dir not in sys.path:
            sys.path.insert(0, gatorize_dir)
        from entry_points import render_entry_content
        content = render_entry_content(has_command_post=False)
        assert "gator loop wait" in content

    def test_protocol_copies_are_identical(self):
        """Shipped template and .includes/ protocol are byte-identical."""
        includes = (INCLUDES_DIR / "procedures" / "gator-loop-protocol.md").read_text(encoding="utf-8")
        template = (TEMPLATES_DIR / "procedures" / "gator-loop-protocol.md").read_text(encoding="utf-8")
        assert includes == template

    def test_protocol_documents_architect_extension(self):
        """#39: Rule 10 keeps 'stop at terminal' for participants but documents
        the Architect-only max-rounds extension and the re-engagement path."""
        for base in [INCLUDES_DIR / "procedures", TEMPLATES_DIR / "procedures"]:
            text = (base / "gator-loop-protocol.md").read_text(encoding="utf-8")
            rule10 = text[text.index("### Rule 10"):text.index("## State Machine")]
            assert "gator loop extend" in rule10
            assert "`max_rounds_exceeded`" in rule10
            assert "fresh join prompt" in rule10
            assert "Do not wait for or poll for an extension" in rule10
            assert "No other terminal state can be resumed" in rule10
            assert "`ended_by_architect`" in rule10
            assert "done unless the Architect extends it" in text

    def test_protocol_state_table_matches_state_machine(self):
        """The participant State Machine table lists every stage the state
        machine defines, and the category summary matches its sets."""
        import re
        for base in [INCLUDES_DIR / "procedures", TEMPLATES_DIR / "procedures"]:
            text = (base / "gator-loop-protocol.md").read_text(encoding="utf-8")
            section = text[text.index("## State Machine"):]
            section = section[:section.index("\n---")]
            rows = set(re.findall(r"^\| `([a-z_]+)` \|", section, re.MULTILINE))
            assert rows == set(loop_sm.ALL_STAGES), (
                f"{base}: table stages {sorted(rows)} != state machine {sorted(loop_sm.ALL_STAGES)}")
            for label, stages in (("Active (3)", loop_sm.ACTIVE_STAGES),
                                  ("Paused (2)", loop_sm.PAUSED_STAGES),
                                  ("Terminal (4)", loop_sm.TERMINAL_STAGES)):
                line = next(l for l in section.splitlines() if label in l)
                for stage in stages:
                    assert f"`{stage}`" in line, f"{label} summary missing {stage}"
            final_rows = [l for l in section.splitlines() if "done, final" in l]
            assert {re.match(r"^\| `([a-z_]+)`", l).group(1) for l in final_rows} == \
                set(loop_sm.TERMINAL_STAGES) - {loop_sm.EXTENDABLE_STAGE}

    def test_escalate_before_wait_ordering(self):
        """All surfaces teach escalate-first, then wait — not the reverse."""
        gatorize_dir = str(Path(__file__).parent.parent / "src" / "gator_command" / "scripts" / "gatorize")
        if gatorize_dir not in sys.path:
            sys.path.insert(0, gatorize_dir)
        from entry_points import render_entry_content

        surfaces = {
            "render_entry_content": render_entry_content(has_command_post=False),
            "loop-join template": (TEMPLATES_DIR / "commands" / "loop-join.md").read_text(encoding="utf-8"),
            "protocol (.includes)": (INCLUDES_DIR / "procedures" / "gator-loop-protocol.md").read_text(encoding="utf-8"),
            "protocol (template)": (TEMPLATES_DIR / "procedures" / "gator-loop-protocol.md").read_text(encoding="utf-8"),
        }
        for name, text in surfaces.items():
            assert "escalate" in text.lower(), f"{name} missing escalate guidance"
            escalate_pos = text.lower().index("escalate first")
            wait_pos = text.lower().index("gator loop wait")
            assert escalate_pos < wait_pos, (
                f"{name}: escalate must appear before wait in the exit-1 guidance"
            )

    def test_live_entry_points_reference_wait(self):
        """CLAUDE.md, AGENTS.md, GEMINI.md managed blocks include wait."""
        repo_root = Path(__file__).parent.parent
        for name in ["CLAUDE.md", "AGENTS.md", "GEMINI.md"]:
            text = (repo_root / name).read_text(encoding="utf-8")
            assert "gator loop wait" in text, f"{name} missing wait instruction"
            assert "escalate first" in text, f"{name} missing escalate-first ordering"


class TestExecutiveSummaryProducerPaths:
    """All participant-facing surfaces must teach the Executive Summary requirement."""

    def test_entry_point_rendering_mentions_executive_summary(self):
        """render_entry_content() output includes executive summary requirement."""
        gatorize_dir = str(Path(__file__).parent.parent / "src" / "gator_command" / "scripts" / "gatorize")
        if gatorize_dir not in sys.path:
            sys.path.insert(0, gatorize_dir)
        from entry_points import render_entry_content
        content = render_entry_content(has_command_post=False)
        assert "Executive Summary" in content
        assert "four bullets" in content

    def test_loop_join_template_mentions_executive_summary(self):
        """Slash-command template tells participants about the executive summary requirement."""
        text = (TEMPLATES_DIR / "commands" / "loop-join.md").read_text(encoding="utf-8")
        assert "Executive Summary" in text

    def test_protocol_mentions_executive_summary(self):
        """Loop protocol documents the Executive Summary section in draftor/reviewer output."""
        for base in [INCLUDES_DIR / "procedures", TEMPLATES_DIR / "procedures"]:
            text = (base / "gator-loop-protocol.md").read_text(encoding="utf-8")
            assert "Executive Summary" in text

    def test_artifact_formats_include_executive_summary_template(self):
        """Artifact format reference includes Executive Summary section in plan and findings templates."""
        for base in [INCLUDES_DIR / "reference-notes", TEMPLATES_DIR / "reference-notes"]:
            text = (base / "loop-artifact-formats.md").read_text(encoding="utf-8")
            assert "## Executive Summary" in text
            assert "four bullets" in text.lower() or "Four bullets" in text
