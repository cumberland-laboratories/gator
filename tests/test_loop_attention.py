"""
Tests for #47 M1: the attention-interval contract flag and turn-start
recording.

New sessions (planning and coding) carry ``contract.attention_interval``;
their transitions record ``turn_started_at`` and never set a deadline.
Legacy (unflagged) sessions keep the historical deadline semantics exactly.
"""

import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "src" / "gator_command" / "scripts"
LOOP_DIR = SCRIPTS_DIR / "loop"
for p in [str(SCRIPTS_DIR), str(LOOP_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import session as loop_session
import state_machine as sm

CODING = {"source_loop_id": "src", "plan_sha256": "0" * 64,
          "base_head": "1" * 40, "base_tree": "2" * 40}
ATTENTION_KEYS = {"turn_started_at", "attention_notified_turn"}


def planning():
    return loop_session.create_session("f", "f-loop", max_rounds=5, turn_timeout=300)


def coding():
    return loop_session.create_session("f", "f-loop", max_rounds=5,
                                       turn_timeout=300, mode="coding",
                                       coding=dict(CODING))


def legacy(s):
    """Pre-#47 session shape: no attention flag, a real deadline."""
    s["contract"].pop("attention_interval", None)
    if not s["contract"]:
        del s["contract"]
    for k in ATTENTION_KEYS:
        s["status"].pop(k, None)
    s["status"]["turn_deadline"] = loop_session._deadline_from_now(300)
    return s


def _iso(v):
    return datetime.fromisoformat(v)


# ---------------------------------------------------------------------------
# Contract and predicate
# ---------------------------------------------------------------------------

class TestContract:
    def test_planning_contract(self):
        s = planning()
        assert s["contract"] == {"attention_interval": 1, "context_evidence": 1,
                                 "coding_checkpoints": 1}
        assert loop_session.attention_mode(s) is True

    def test_coding_contract(self):
        s = coding()
        assert s["contract"] == {"attention_interval": 1}
        assert loop_session.attention_mode(s) is True

    @pytest.mark.parametrize("make", [planning, coding], ids=["planning", "coding"])
    def test_initial_turn_recorded_without_deadline(self, make):
        s = make()
        st = s["status"]
        assert st["turn_deadline"] is None
        assert _iso(st["turn_started_at"])
        assert st["attention_notified_turn"] is None
        assert st["turn_timeout_seconds"] == 300  # the stored interval

    def test_default_interval_unchanged(self):
        assert loop_session.DEFAULT_ATTENTION_INTERVAL == 300

    @pytest.mark.parametrize("contract", [
        None, {}, {"attention_interval": 0}, {"attention_interval": True},
        {"attention_interval": "1"}, {"context_evidence": 1}, "yes", [1],
    ], ids=["none", "empty", "zero", "bool", "str", "other-flag", "str-contract", "list"])
    def test_predicate_strict(self, contract):
        s = {} if contract is None else {"contract": contract}
        assert loop_session.attention_mode(s) is False

    def test_predicate_non_dict_session(self):
        assert loop_session.attention_mode(None) is False


# ---------------------------------------------------------------------------
# Transitions: flagged sessions begin/end attention turns
# ---------------------------------------------------------------------------

def _begin_checks(s, before):
    st = s["status"]
    assert st["turn_deadline"] is None
    assert st["turn_started_at"] and st["turn_started_at"] != before


def _ended_checks(s):
    st = s["status"]
    assert st["turn_deadline"] is None
    assert st["turn_started_at"] is None


class TestFlaggedTransitions:
    def test_draft_and_review_revise_begin_fresh_turns(self):
        s = planning()
        t0 = s["status"]["turn_started_at"]
        time.sleep(0.002)
        sm.advance_draft_submitted(s, 300)
        _begin_checks(s, t0)
        t1 = s["status"]["turn_started_at"]
        time.sleep(0.002)
        sm.advance_review_submitted(s, False, 1, 300)
        _begin_checks(s, t1)

    def test_approval_ends_turn(self):
        s = planning()
        sm.advance_draft_submitted(s, 300)
        sm.advance_review_submitted(s, True, 0, 300)
        _ended_checks(s)

    def test_max_rounds_ends_turn(self):
        s = loop_session.create_session("f", "l", max_rounds=1, turn_timeout=300)
        sm.advance_draft_submitted(s, 300)
        sm.advance_review_submitted(s, False, 1, 300)
        assert s["status"]["stage"] == "max_rounds_exceeded"
        _ended_checks(s)

    def test_escalate_then_unblock(self):
        s = planning()
        sm.advance_escalated(s, "need a decision")
        _ended_checks(s)
        sm.advance_unblocked(s, turn_timeout=300, message="go")
        _begin_checks(s, None)

    def test_pause_and_end(self):
        s = planning()
        sm.advance_paused_by_architect(s, "hold")
        _ended_checks(s)
        sm.advance_unblocked(s, turn_timeout=300)
        _begin_checks(s, None)
        sm.advance_ended_by_architect(s, "done")
        _ended_checks(s)

    def test_extend_begins_turn(self):
        s = loop_session.create_session("f", "l", max_rounds=1, turn_timeout=300)
        sm.advance_draft_submitted(s, 300)
        sm.advance_review_submitted(s, False, 1, 300)
        sm.advance_extended(s, 1, 300, message="more")
        _begin_checks(s, None)

    def test_coding_implementation_cycle(self):
        s = coding()
        t0 = s["status"]["turn_started_at"]
        time.sleep(0.002)
        sm.advance_implementation_submitted(s, 300)
        _begin_checks(s, t0)
        t1 = s["status"]["turn_started_at"]
        time.sleep(0.002)
        sm.advance_implementation_reviewed(s, False, 300)
        _begin_checks(s, t1)

    def test_coding_approval_and_reopen(self):
        s = coding()
        sm.advance_implementation_submitted(s, 300)
        sm.advance_implementation_reviewed(
            s, True, 300, approval={"tree": "a" * 40, "head": "b" * 40})
        _ended_checks(s)
        sm.advance_reopened(s, turn_timeout=300, message="stale")
        _begin_checks(s, None)

    def test_interject_does_not_touch_turn(self):
        s = planning()
        before = dict(s["status"])
        sm.advance_interjected(s, "note")
        assert s["status"]["turn_started_at"] == before["turn_started_at"]
        assert s["status"]["turn_deadline"] is None


# ---------------------------------------------------------------------------
# Legacy sessions: historical deadline semantics, no attention fields
# ---------------------------------------------------------------------------

class TestLegacyUnchanged:
    def _no_attention_fields(self, s):
        assert not (ATTENTION_KEYS & set(s["status"]))

    def test_legacy_submit_cycle_sets_deadlines(self):
        s = legacy(planning())
        d0 = s["status"]["turn_deadline"]
        time.sleep(0.002)
        sm.advance_draft_submitted(s, 300)
        assert s["status"]["turn_deadline"] and s["status"]["turn_deadline"] != d0
        sm.advance_review_submitted(s, False, 1, 300)
        assert s["status"]["turn_deadline"]
        self._no_attention_fields(s)

    def test_legacy_pause_clears_deadline_only(self):
        s = legacy(planning())
        sm.advance_paused_by_architect(s)
        assert s["status"]["turn_deadline"] is None
        self._no_attention_fields(s)
        sm.advance_unblocked(s, turn_timeout=600)
        assert s["status"]["turn_deadline"]
        self._no_attention_fields(s)

    def test_legacy_timeout_terminal_still_available(self):
        s = legacy(planning())
        sm.advance_turn_timed_out(s, "draftor")
        assert s["status"]["stage"] == "turn_timed_out"
        assert sm.is_terminal(s)
        self._no_attention_fields(s)

    def test_legacy_coding_reopen(self):
        s = legacy(coding())
        sm.advance_implementation_submitted(s, 300)
        sm.advance_implementation_reviewed(
            s, True, 300, approval={"tree": "a" * 40, "head": "b" * 40})
        sm.advance_reopened(s, turn_timeout=300, message="stale")
        assert s["status"]["turn_deadline"]
        self._no_attention_fields(s)


# ===========================================================================
# M2: attention emission (host) — crash-safe, one event per turn
# ===========================================================================

import hashlib
import json
import threading
from datetime import timedelta, timezone

import events as loop_events
import host as loop_host
import liveness as lv


def _env(tmp_path, *, flagged=True, interval=300, elapsed=400):
    loop_dir = tmp_path / ".gator" / "loops" / "att-loop"
    loop_dir.mkdir(parents=True)
    s = loop_session.create_session("att", "att-loop", max_rounds=5,
                                    turn_timeout=interval)
    if not flagged:
        legacy(s)
    else:
        started = datetime.now(tz=timezone.utc) - timedelta(seconds=elapsed)
        s["status"]["turn_started_at"] = started.isoformat()
    loop_session.save_session(loop_dir, s)
    loop_events.create_events_file(loop_dir)
    return loop_dir


def _attention_events(loop_dir):
    return [e for e in loop_events.read_all_events(loop_dir)
            if e.get("event") == loop_host.ATTENTION_EVENT]


def _marker(loop_dir):
    return loop_session.load_session(loop_dir)["status"]["attention_notified_turn"]


def _key(loop_dir):
    return loop_session.load_session(loop_dir)["status"]["turn_started_at"]


class TestAttentionEmission:
    def test_not_before_interval(self, tmp_path):
        d = _env(tmp_path, elapsed=10)
        assert loop_host._try_record_attention(d) is False
        assert _attention_events(d) == [] and _marker(d) is None

    def test_records_exactly_once_and_stays_active(self, tmp_path):
        d = _env(tmp_path)
        assert loop_host._try_record_attention(d) is True
        assert loop_host._try_record_attention(d) is False
        assert loop_host._try_record_attention(d) is False
        evs = _attention_events(d)
        assert len(evs) == 1 and evs[0]["attention_key"] == _key(d)
        s = loop_session.load_session(d)
        assert s["status"]["stage"] == "plan_drafting"
        assert s["status"]["next_role"] == "draftor"
        assert not sm.is_terminal(s) and not sm.is_paused(s)
        assert _marker(d) == _key(d)

    def test_flagged_never_times_out_even_with_forced_deadline(self, tmp_path):
        d = _env(tmp_path)
        s = loop_session.load_session(d)
        s["status"]["turn_deadline"] = "2000-01-01T00:00:00+00:00"
        loop_session.save_session(d, s)
        loop_host._try_enforce_timeout(d)
        assert loop_session.load_session(d)["status"]["stage"] == "plan_drafting"

    def test_legacy_still_times_out(self, tmp_path):
        d = _env(tmp_path, flagged=False)
        s = loop_session.load_session(d)
        s["status"]["turn_deadline"] = "2000-01-01T00:00:00+00:00"
        loop_session.save_session(d, s)
        loop_host._try_enforce_timeout(d)
        assert loop_session.load_session(d)["status"]["stage"] == "turn_timed_out"
        assert loop_host._try_record_attention(d) is False  # legacy: no attention

    def test_racing_observers_one_event(self, tmp_path):
        d = _env(tmp_path)
        barrier = threading.Barrier(4)
        errors = []

        def run():
            try:
                barrier.wait()
                loop_host._try_record_attention(d)
            except Exception as exc:  # pragma: no cover - surfaced below
                errors.append(exc)

        threads = [threading.Thread(target=run) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert len(_attention_events(d)) == 1

    def test_new_turn_gets_independent_event(self, tmp_path):
        d = _env(tmp_path)
        loop_host._try_record_attention(d)
        s = loop_session.load_session(d)
        sm.advance_draft_submitted(s, 300)
        loop_session.save_session(d, s)
        assert loop_host._try_record_attention(d) is False  # new turn, not due
        s = loop_session.load_session(d)
        s["status"]["turn_started_at"] = (
            datetime.now(tz=timezone.utc) - timedelta(seconds=400)).isoformat()
        loop_session.save_session(d, s)
        assert loop_host._try_record_attention(d) is True
        evs = _attention_events(d)
        assert len(evs) == 2 and evs[0]["attention_key"] != evs[1]["attention_key"]
        assert evs[1]["role"] == "reviewer"

    @pytest.mark.parametrize("pause", ["escalate", "pause"])
    def test_paused_never_records(self, tmp_path, pause):
        d = _env(tmp_path)
        s = loop_session.load_session(d)
        key = s["status"]["turn_started_at"]
        if pause == "escalate":
            sm.advance_escalated(s, "q")
        else:
            sm.advance_paused_by_architect(s)
        s["status"]["turn_started_at"] = key  # even if a stale key lingered
        loop_session.save_session(d, s)
        assert loop_host._try_record_attention(d) is False
        assert _attention_events(d) == []

    def test_terminal_never_records(self, tmp_path):
        d = _env(tmp_path)
        s = loop_session.load_session(d)
        sm.advance_ended_by_architect(s, "done")
        loop_session.save_session(d, s)
        assert loop_host._try_record_attention(d) is False

    def test_payload_minimal(self, tmp_path):
        d = _env(tmp_path)
        loop_host._try_record_attention(d)
        ev = _attention_events(d)[0]
        assert set(ev) == {"event", "attention_key", "role", "round", "stage",
                           "interval_seconds", "turn_started_at", "detail",
                           "ts", "loop_id"}
        blob = json.dumps(ev)
        assert "glp_" not in blob and "token" not in blob.lower()
        assert ev["interval_seconds"] == 300
        assert ev["detail"] == ("draftor active for at least 5m in plan drafting; "
                                "loop still running")

    def test_format_event_label(self, tmp_path):
        d = _env(tmp_path)
        loop_host._try_record_attention(d)
        line = loop_events.format_event(_attention_events(d)[0])
        assert "ATTENTION" in line and "loop still running" in line

    def test_attention_event_is_not_terminal(self):
        assert loop_host.ATTENTION_EVENT not in loop_events.TERMINAL_EVENTS


class TestAttentionFaultInjection:
    """Decision 3: the two-file update is not atomic; it converges."""

    def test_a_emit_raises_then_converges(self, tmp_path, monkeypatch):
        d = _env(tmp_path)

        def boom(*a, **k):
            raise OSError("disk full")
        monkeypatch.setattr(loop_host, "emit_event", boom)
        with pytest.raises(OSError):
            loop_host._try_record_attention(d)
        assert _attention_events(d) == [] and _marker(d) is None
        monkeypatch.undo()
        assert loop_host._try_record_attention(d) is True
        assert len(_attention_events(d)) == 1 and _marker(d) == _key(d)

    def test_b_save_fails_after_append_repairs_without_duplicate(self, tmp_path, monkeypatch):
        d = _env(tmp_path)
        real_save = loop_session.save_session
        calls = {"n": 0}

        def flaky(loop_dir, session):
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("save failed")
            return real_save(loop_dir, session)
        monkeypatch.setattr(loop_session, "save_session", flaky)
        with pytest.raises(OSError):
            loop_host._try_record_attention(d)
        assert len(_attention_events(d)) == 1 and _marker(d) is None
        assert loop_host._try_record_attention(d) is False  # repair, no append
        assert len(_attention_events(d)) == 1 and _marker(d) == _key(d)

    def test_c_crash_after_append_repairs(self, tmp_path):
        d = _env(tmp_path)
        key = _key(d)
        loop_events.emit_event(d, {"event": loop_host.ATTENTION_EVENT,
                                   "attention_key": key, "role": "draftor"})
        assert loop_host._try_record_attention(d) is False
        assert len(_attention_events(d)) == 1 and _marker(d) == key

    def test_d_torn_trailing_line_isolated(self, tmp_path):
        d = _env(tmp_path)
        path = d / "events.jsonl"
        loop_session._make_writable(path)
        with open(path, "ab") as f:
            f.write(b'{"event":"architect_attention_due","attention_key":"')
        assert loop_host._try_record_attention(d) is True
        assert len(_attention_events(d)) == 1
        raw = path.read_bytes()
        assert raw.endswith(b"\n")
        assert b'"attention_key":"{' not in raw  # never concatenated
        assert loop_host._try_record_attention(d) is False

    def test_e_other_turn_event_ignored(self, tmp_path):
        d = _env(tmp_path)
        loop_events.emit_event(d, {"event": loop_host.ATTENTION_EVENT,
                                   "attention_key": "2000-01-01T00:00:00+00:00"})
        assert loop_host._try_record_attention(d) is True
        keys = [e["attention_key"] for e in _attention_events(d)]
        assert keys == ["2000-01-01T00:00:00+00:00", _key(d)]

    def test_f_no_writes_after_convergence(self, tmp_path):
        d = _env(tmp_path)
        loop_host._try_record_attention(d)
        before = ((d / "session.json").read_bytes(), (d / "events.jsonl").read_bytes())
        for _ in range(3):
            assert loop_host._try_record_attention(d) is False
        after = ((d / "session.json").read_bytes(), (d / "events.jsonl").read_bytes())
        assert after == before


class TestAttentionLiveness:
    def _legacy_key(self, session):
        st = session["status"]
        material = {"round": st.get("round"), "stage": st.get("stage"),
                    "next_role": st.get("next_role"),
                    "turns": len(session.get("turns", [])),
                    "turn_deadline": st.get("turn_deadline")}
        blob = json.dumps(material, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def test_legacy_state_key_hash_unchanged(self):
        s = legacy(planning())
        assert lv.state_key(s) == self._legacy_key(s)

    def test_flagged_key_changes_per_turn(self):
        s = planning()
        k0 = lv.state_key(s)
        time.sleep(0.002)
        sm.advance_escalated(s, "q")
        sm.advance_unblocked(s, turn_timeout=300)  # same stage/role, new turn
        k1 = lv.state_key(s)
        assert k1 != k0

    def test_recording_attention_does_not_change_state_key(self, tmp_path):
        d = _env(tmp_path)
        k0 = lv.state_key(loop_session.load_session(d))
        loop_host._try_record_attention(d)
        assert lv.state_key(loop_session.load_session(d)) == k0


class TestWatchLoopAttention:
    """The real watch_loop Phase 2 records attention for flagged loops and
    keeps hosting (no state change); it exits only on a terminal event."""

    def _end(self, d):
        def _fn(session):
            sm.advance_ended_by_architect(session, "test done")
            return session, {"event": "loop_ended_by_architect",
                             "role": "architect", "detail": "test done"}
        loop_session.with_session_lock(d, _fn)

    def _run_watch(self, d, monkeypatch):
        monkeypatch.setattr(loop_host, "POLL_INTERVAL", 0.02)
        th = threading.Thread(target=loop_host.watch_loop, args=(d,), daemon=True)
        th.start()
        return th

    def _wait_for(self, pred, timeout=10.0):
        end = time.time() + timeout
        while time.time() < end:
            if pred():
                return True
            time.sleep(0.02)
        return False

    def test_watcher_records_once_and_keeps_hosting(self, tmp_path, monkeypatch):
        d = _env(tmp_path)
        th = self._run_watch(d, monkeypatch)
        assert self._wait_for(lambda: len(_attention_events(d)) == 1)
        time.sleep(0.2)  # several more polls
        assert th.is_alive()
        assert len(_attention_events(d)) == 1
        assert loop_session.load_session(d)["status"]["stage"] == "plan_drafting"
        self._end(d)
        th.join(timeout=10)
        assert not th.is_alive()

    def test_watcher_survives_recording_error(self, tmp_path, monkeypatch):
        d = _env(tmp_path)
        calls = {"n": 0}
        real = loop_host._try_record_attention

        def flaky(loop_dir, now=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("transient")
            return real(loop_dir, now)
        monkeypatch.setattr(loop_host, "_try_record_attention", flaky)
        th = self._run_watch(d, monkeypatch)
        assert self._wait_for(lambda: len(_attention_events(d)) == 1)
        assert th.is_alive() and calls["n"] >= 2
        self._end(d)
        th.join(timeout=10)

    def test_watcher_legacy_still_enforces_timeout(self, tmp_path, monkeypatch):
        d = _env(tmp_path, flagged=False)
        s = loop_session.load_session(d)
        s["status"]["turn_deadline"] = "2000-01-01T00:00:00+00:00"
        loop_session.save_session(d, s)
        th = self._run_watch(d, monkeypatch)
        th.join(timeout=10)
        assert not th.is_alive()
        assert loop_session.load_session(d)["status"]["stage"] == "turn_timed_out"
        assert _attention_events(d) == []


class TestAttentionMalformedTimestamps:
    """M2-1: malformed turn timestamps are 'not due', never an exception."""

    @pytest.mark.parametrize("value", [
        "2000-01-01T00:00:00",            # naive: parses, no offset
        "2000-01-01",                     # naive date
        "not-a-time",
        "",
        "9999-12-31T23:59:59+00:00",      # overflow when adding the interval
    ], ids=["naive", "naive-date", "garbage", "empty", "overflow"])
    def test_attention_due_returns_false(self, value):
        s = planning()
        s["status"]["turn_started_at"] = value
        now = datetime.now(tz=timezone.utc)
        assert loop_host._attention_due(s, now) is False

    @pytest.mark.parametrize("value", [123, None, ["x"]], ids=["int", "none", "list"])
    def test_non_string_key_returns_false(self, value):
        s = planning()
        s["status"]["turn_started_at"] = value
        assert loop_host._attention_due(s, datetime.now(tz=timezone.utc)) is False

    def test_record_noop_on_naive_key(self, tmp_path):
        d = _env(tmp_path)
        s = loop_session.load_session(d)
        s["status"]["turn_started_at"] = "2000-01-01T00:00:00"
        loop_session.save_session(d, s)
        assert loop_host._try_record_attention(d) is False
        assert _attention_events(d) == []

    def test_watcher_ignores_naive_key_and_keeps_hosting(self, tmp_path, monkeypatch):
        d = _env(tmp_path)
        s = loop_session.load_session(d)
        s["status"]["turn_started_at"] = "2000-01-01T00:00:00"
        loop_session.save_session(d, s)
        monkeypatch.setattr(loop_host, "POLL_INTERVAL", 0.02)
        th = threading.Thread(target=loop_host.watch_loop, args=(d,), daemon=True)
        th.start()
        time.sleep(0.3)  # many polls
        assert th.is_alive()
        assert _attention_events(d) == []
        st = loop_session.load_session(d)["status"]
        assert st["stage"] == "plan_drafting" and st["attention_notified_turn"] is None
        TestWatchLoopAttention()._end(d)
        th.join(timeout=10)
        assert not th.is_alive()


# ===========================================================================
# M3: CLI and participant language
# ===========================================================================

import submit as loop_submit

ROOT = Path(__file__).parent.parent


@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    """A tokened loop on disk; ``legacy=True`` variants via legacy_on_disk."""
    monkeypatch.setattr(loop_session, "find_gator_root", lambda start_path=None: tmp_path)
    monkeypatch.setattr(loop_submit, "find_gator_root", lambda start_path=None: tmp_path)
    loop_id = "cli-att-loop"
    loop_dir = tmp_path / ".gator" / "loops" / loop_id
    loop_dir.mkdir(parents=True)
    loop_session.ensure_loops_gitignore(loop_dir.parent)
    s = loop_session.create_session("cli-att", loop_id, max_rounds=3, turn_timeout=300)
    loop_session.save_session(loop_dir, s)
    loop_events.create_events_file(loop_dir)
    toks = {}
    for role in ("draftor", "reviewer", "architect"):
        tok, nonce = loop_session.make_token(loop_id, role)
        toks[role] = {"nonce": nonce, "token": tok}
    loop_session.save_tokens(loop_dir, toks)
    return {"loop_dir": loop_dir, **{r: v["token"] for r, v in toks.items()}}


def _legacy_on_disk(loop_dir):
    s = loop_session.load_session(loop_dir)
    loop_session.save_session(loop_dir, legacy(s))


def _run(argv, capsys):
    from cli import main
    with pytest.raises(SystemExit) as exc:
        main(argv)
    out = capsys.readouterr()
    return exc.value.code, out.out, out.err


TIME_WORDS = ("Turn window", "turn_timeout", "deadline", "remaining")


class TestParticipantSurfaces:
    def test_status_json_has_no_time_fields(self, cli_env, capsys):
        code, out, _ = _run(["status", "--token", cli_env["draftor"], "--json"], capsys)
        data = json.loads(out)
        assert code == 0 and data["your_turn"] is True
        assert "turn_timeout_seconds" not in data and "turn_deadline" not in data

    def test_status_text_has_no_time_words(self, cli_env, capsys):
        code, out, _ = _run(["status", "--token", cli_env["draftor"]], capsys)
        assert code == 0
        for w in TIME_WORDS:
            assert w not in out, w

    def test_legacy_status_keeps_window(self, cli_env, capsys):
        _legacy_on_disk(cli_env["loop_dir"])
        code, out, _ = _run(["status", "--token", cli_env["draftor"]], capsys)
        assert "Turn window: 300s" in out
        code, out, _ = _run(["status", "--token", cli_env["draftor"], "--json"], capsys)
        data = json.loads(out)
        assert data["turn_timeout_seconds"] == 300 and data["turn_deadline"]

    def test_wait_json_has_no_time_fields(self, cli_env, capsys):
        code, out, _ = _run(["wait", "--token", cli_env["draftor"], "--json",
                             "--max-seconds", "1"], capsys)
        data = json.loads(out)
        assert code == 0
        assert "turn_timeout_seconds" not in data and "turn_deadline" not in data

    def test_wait_text_has_no_time_words(self, cli_env, capsys):
        code, out, _ = _run(["wait", "--token", cli_env["draftor"],
                             "--max-seconds", "1"], capsys)
        assert code == 0
        for w in TIME_WORDS:
            assert w not in out, w

    def test_legacy_wait_json_keeps_fields(self, cli_env, capsys):
        _legacy_on_disk(cli_env["loop_dir"])
        code, out, _ = _run(["wait", "--token", cli_env["draftor"], "--json",
                             "--max-seconds", "1"], capsys)
        data = json.loads(out)
        assert data["turn_timeout_seconds"] == 300 and data["turn_deadline"]


class TestArchitectSurfaces:
    def _age(self, loop_dir, seconds):
        s = loop_session.load_session(loop_dir)
        s["status"]["turn_started_at"] = (
            datetime.now(tz=timezone.utc) - timedelta(seconds=seconds)).isoformat()
        loop_session.save_session(loop_dir, s)

    def test_architect_json_attention_view(self, cli_env, capsys):
        self._age(cli_env["loop_dir"], 30)
        code, out, _ = _run(["status", "--token", cli_env["architect"], "--json"], capsys)
        att = json.loads(out)["attention"]
        assert att["interval_seconds"] == 300 and att["due"] is False
        assert att["notified"] is False and 25 <= att["elapsed_seconds"] <= 120
        assert set(att) == {"interval_seconds", "turn_started_at", "elapsed_seconds",
                            "notified_turn", "notified", "due"}

    def test_architect_text_due_and_notified(self, cli_env, capsys):
        d = cli_env["loop_dir"]
        self._age(d, 400)
        code, out, _ = _run(["status", "--token", cli_env["architect"]], capsys)
        assert "Attention interval: 5 min (Architect notice only)" in out
        assert "Elapsed this turn: 6m" in out
        assert "no notice recorded yet" in out
        loop_host._try_record_attention(d)
        code, out, _ = _run(["status", "--token", cli_env["architect"]], capsys)
        assert "Attention: due (notice recorded)" in out
        assert "no action is required" in out

    def test_legacy_architect_json_has_no_attention(self, cli_env, capsys):
        _legacy_on_disk(cli_env["loop_dir"])
        code, out, _ = _run(["status", "--token", cli_env["architect"], "--json"], capsys)
        assert "attention" not in json.loads(out)

    def test_unblock_timeout_refused_for_attention_loop(self, cli_env, capsys):
        d = cli_env["loop_dir"]
        loop_submit.handle_pause(cli_env["architect"])
        before = (d / "session.json").read_bytes()
        from cli import main
        with pytest.raises(SystemExit) as exc:
            main(["unblock", "--token", cli_env["architect"], "--timeout", "600"])
        assert exc.value.code == 1
        assert "attention interval" in capsys.readouterr().err
        assert (d / "session.json").read_bytes() == before

    def test_unblock_output_shows_attention_interval(self, cli_env, capsys):
        loop_submit.handle_pause(cli_env["architect"])
        from cli import main
        main(["unblock", "--token", cli_env["architect"]])
        out = capsys.readouterr().out
        assert "Attention interval: 5 min" in out and "Turn window" not in out

    def test_paused_view_has_no_timeout_hint(self, cli_env, capsys):
        loop_submit.handle_pause(cli_env["architect"])
        code, out, _ = _run(["status", "--token", cli_env["architect"]], capsys)
        assert "--timeout" not in out and "Attention interval: 5 min" in out

    def test_handle_unblock_refusal_is_value_error(self, cli_env):
        loop_submit.handle_pause(cli_env["architect"])
        with pytest.raises(ValueError, match="attention interval"):
            loop_submit.handle_unblock(cli_env["architect"], turn_timeout=600)


class TestStartFlag:
    @pytest.mark.parametrize("flag", ["--attention-interval", "--turn-timeout"])
    def test_flag_and_alias(self, flag, monkeypatch):
        import host
        from cli import main
        seen = {}
        monkeypatch.setattr(host, "start_loop", lambda **kw: seen.update(kw))
        main(["start", "--feature", "f", "--sketch", "s.md", flag, "600"])
        assert seen["turn_timeout"] == 600

    def test_default_interval(self, monkeypatch):
        import host
        from cli import main
        seen = {}
        monkeypatch.setattr(host, "start_loop", lambda **kw: seen.update(kw))
        main(["start", "--feature", "f", "--sketch", "s.md"])
        assert seen["turn_timeout"] == 300


class TestParticipantDocs:
    PROTOCOLS = [ROOT / ".gator" / ".includes" / "procedures" / "gator-loop-protocol.md",
                 ROOT / "src" / "gator_command" / "templates" / "gator-starter"
                 / "procedures" / "gator-loop-protocol.md"]
    WATCHERS = [ROOT / ".gator" / ".includes" / "reference-notes" / "loop-participant-watcher.md",
                ROOT / "src" / "gator_command" / "templates" / "gator-starter"
                / "reference-notes" / "loop-participant-watcher.md"]
    JOINS = [ROOT / ".claude" / "commands" / "loop-join.md",
             ROOT / "src" / "gator_command" / "templates" / "gator-starter"
             / "commands" / "loop-join.md"]

    @pytest.mark.parametrize("pair", ["PROTOCOLS", "WATCHERS", "JOINS"])
    def test_pairs_identical(self, pair):
        a, b = getattr(self, pair)
        if not a.exists():
            pytest.skip("live copy absent")
        assert a.read_bytes() == b.read_bytes()

    def test_rule7_no_deadline(self):
        text = self.PROTOCOLS[1].read_text(encoding="utf-8")
        assert "Plan your work to fit within the timeout" not in text
        assert "### Rule 7: Work at the pace the artifact needs" in text
        assert "There is no participant deadline" in text
        assert "never to negotiate time" in text
        assert "to avoid timeout" not in text and "No timeout runs" not in text

    def test_time_words_only_in_legacy_note(self):
        text = self.PROTOCOLS[1].read_text(encoding="utf-8")
        for line in text.splitlines():
            low = line.lower()
            if "turn window" in low or "deadline" in low or "timeout" in low:
                assert ("legacy" in low or "no participant deadline" in low), line

    def test_join_and_watcher_have_no_time_language(self):
        join = self.JOINS[1].read_text(encoding="utf-8").lower()
        watcher = self.WATCHERS[1].read_text(encoding="utf-8").lower()
        for w in ("turn window", "turn timeout", "deadline", "time remaining"):
            assert w not in join and w not in watcher, w
