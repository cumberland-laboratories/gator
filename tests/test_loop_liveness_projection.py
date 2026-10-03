"""
M3 tests for loop participant liveness projection (#36): D5 rules driven by
real loop transitions, idempotency, lock order, failure isolation, restart
recovery, and Re-notify eligibility.
"""

import json
import subprocess
import sys
import threading
from datetime import timedelta
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "src" / "gator_command" / "scripts"
LOOP_DIR = SCRIPTS_DIR / "loop"
for p in [str(SCRIPTS_DIR), str(LOOP_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import events as loop_events  # noqa: E402
import host as loop_host  # noqa: E402
import liveness as lv  # noqa: E402
import session as loop_session  # noqa: E402
import submit as loop_submit  # noqa: E402

LOOP_ID = "liveness-proj-2026-09-29T00-00-00Z"


@pytest.fixture
def env(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    loop_dir = tmp_path / ".gator" / "loops" / LOOP_ID
    loop_dir.mkdir(parents=True)
    loop_session.ensure_loops_gitignore(loop_dir.parent)
    loop_session.save_session(
        loop_dir, loop_session.create_session("liveness", LOOP_ID,
                                              max_rounds=1))
    loop_events.create_events_file(loop_dir)
    tok, stored = {}, {}
    for role in ("draftor", "reviewer", "architect"):
        t, nonce = loop_session.make_token(LOOP_ID, role)
        tok[role] = t
        stored[role] = {"nonce": nonce, "token": t}
    loop_session.save_tokens(loop_dir, stored)
    draft = tmp_path / "plan.md"
    draft.write_text("# Plan\n\n## Executive Summary\n\n- x\n\n"
                     "## Context Checked\n\n- scripts-loop charter\n", encoding="utf-8")
    findings = tmp_path / "findings.md"
    findings.write_text("# Findings\n\n## Executive Summary\n\n- y\n",
                        encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return {"root": tmp_path, "loop_dir": loop_dir, "tok": tok,
            "store": lv.open_store(loop_dir), "draft": str(draft),
            "findings": str(findings)}


def _project(env):
    return lv.project(env["loop_dir"], env["store"])


def _notes(env, role):
    return env["store"].read()["roles"][role]["notifications"]


def _kinds(env, role, pending_only=False):
    return [n["kind"] for n in _notes(env, role)
            if not pending_only or lv.is_pending(n)]


def _loop_bytes(env):
    d = env["loop_dir"]
    return ((d / "session.json").read_bytes(),
            (d / "events.jsonl").read_bytes())


# ---------------------------------------------------------------------------
# D5 rules on real transitions
# ---------------------------------------------------------------------------

class TestRules:
    def test_initial_turn_recorded_for_unregistered_draftor(self, env):
        assert _project(env) == lv.PROJECT_UPDATED
        assert _kinds(env, "draftor") == ["turn-ready"]
        assert _kinds(env, "reviewer") == []

    def test_one_turn_ready_per_transition_and_idempotent(self, env):
        before = _loop_bytes(env)
        _project(env)
        loop_submit.handle_submit_draft(env["tok"]["draftor"], env["draft"])
        assert _project(env) == lv.PROJECT_UPDATED
        for _ in range(10):
            assert _project(env) == lv.PROJECT_UNCHANGED
        assert _kinds(env, "reviewer", pending_only=True) == ["turn-ready"]
        drafts = _notes(env, "draftor")
        assert len(drafts) == 1
        assert drafts[0]["expired_reason"] == "state_changed"
        # Registration/projection never touched loop state beyond the submit.
        assert _loop_bytes(env) != before  # the submit itself wrote

    def test_review_round_trip(self, env):
        s = loop_session.load_session(env["loop_dir"])
        s["status"]["max_rounds"] = 3
        loop_session.save_session(env["loop_dir"], s)
        loop_submit.handle_submit_draft(env["tok"]["draftor"], env["draft"])
        _project(env)
        loop_submit.handle_submit_review(env["tok"]["reviewer"],
                                         env["findings"])
        _project(env)
        assert _kinds(env, "draftor", pending_only=True) == ["turn-ready"]
        assert _kinds(env, "reviewer", pending_only=True) == []
        assert _notes(env, "reviewer")[0]["expired_reason"] == "state_changed"
        assert _notes(env, "draftor")[-1]["stage"] == "plan_revision"

    def test_block_and_unblock(self, env):
        lv.register(env["tok"]["draftor"])
        lv.register(env["tok"]["reviewer"])
        loop_submit.handle_escalate(env["tok"]["draftor"], "need decision")
        _project(env)
        assert _kinds(env, "draftor", pending_only=True) == ["architect-block"]
        assert _kinds(env, "reviewer", pending_only=True) == ["architect-block"]
        loop_submit.handle_unblock(env["tok"]["architect"],
                                   message="decided: go")
        _project(env)
        assert _kinds(env, "draftor", pending_only=True) == ["turn-ready"]
        assert _kinds(env, "reviewer", pending_only=True) == []

    def test_architect_block_skips_unregistered(self, env):
        loop_submit.handle_pause(env["tok"]["architect"], "hold")
        _project(env)
        assert _kinds(env, "reviewer") == []

    def test_end_terminal_and_closure(self, env):
        tok = env["tok"]["reviewer"]
        reg = lv.register(tok)
        loop_submit.handle_end(env["tok"]["architect"], "done")
        _project(env)
        assert _kinds(env, "reviewer", pending_only=True) == ["terminal"]
        assert env["store"].read()["terminal_observed_at"] is not None
        # Still pending -> registration stays open for delivery.
        assert env["store"].read()["roles"]["reviewer"]["registration"][
            "state"] == "active"
        notes = lv.poll(tok, reg["registration_id"])
        lv.ack(tok, reg["registration_id"], notes[0]["seq"])
        _project(env)
        assert env["store"].read()["roles"]["reviewer"]["registration"][
            "state"] == "closed"
        assert len(_notes(env, "reviewer")) == 1  # no duplicate terminal

    def test_timeout_is_terminal(self, env):
        lv.register(env["tok"]["draftor"])
        s = loop_session.load_session(env["loop_dir"])
        s.get("contract", {}).pop("attention_interval", None)  # legacy: #47
        s["status"]["turn_deadline"] = "2000-01-01T00:00:00+00:00"
        loop_session.save_session(env["loop_dir"], s)
        loop_host._try_enforce_timeout(env["loop_dir"])
        _project(env)
        kinds = [(n["kind"], n["stage"]) for n in _notes(env, "draftor")
                 if lv.is_pending(n)]
        assert kinds == [("terminal", "turn_timed_out")]

    def test_extension_clears_terminal_and_new_turn(self, env):
        tok_d = env["tok"]["draftor"]
        lv.register(tok_d)
        loop_submit.handle_submit_draft(tok_d, env["draft"])
        loop_submit.handle_submit_review(env["tok"]["reviewer"],
                                         env["findings"])
        stage = loop_session.load_session(env["loop_dir"])["status"]["stage"]
        assert stage == "max_rounds_exceeded"
        _project(env)
        assert env["store"].read()["terminal_observed_at"] is not None
        loop_submit.handle_extend(env["tok"]["architect"], 1, "one more")
        _project(env)
        st = env["store"].read()
        assert st["terminal_observed_at"] is None
        pend = [n for n in st["roles"]["draftor"]["notifications"]
                if lv.is_pending(n)]
        assert [n["kind"] for n in pend] == ["turn-ready"]
        assert pend[0]["stage"] == "plan_revision"
        term = [n for n in st["roles"]["draftor"]["notifications"]
                if n["kind"] == "terminal"]
        assert term and term[0]["expired_reason"] == "state_changed"

    def test_closed_registration_never_reopened(self, env):
        tok = env["tok"]["reviewer"]
        reg = lv.register(tok)
        lv.release(tok, reg["registration_id"], "delivered", closed=True)
        loop_submit.handle_pause(env["tok"]["architect"], "hold")
        _project(env)
        loop_submit.handle_unblock(env["tok"]["architect"])
        _project(env)
        rec = env["store"].read()["roles"]["reviewer"]
        assert rec["registration"]["state"] == "closed"
        assert rec["notifications"] == []  # no informational to closed

    def test_projection_never_writes_loop_state(self, env):
        lv.register(env["tok"]["draftor"])
        before = _loop_bytes(env)
        for _ in range(3):
            _project(env)
        assert _loop_bytes(env) == before


# ---------------------------------------------------------------------------
# Lock order, failure isolation, recovery
# ---------------------------------------------------------------------------

class TestRobustness:
    def test_projection_completes_while_session_lock_held(self, env):
        """Leaf lock: project() never waits on the session lock."""
        held = threading.Event()
        release = threading.Event()

        def hold(session):
            held.set()
            release.wait(10)
            return None
        t = threading.Thread(target=loop_session.with_session_lock,
                             args=(env["loop_dir"], hold))
        t.start()
        assert held.wait(5)
        result = {}
        p = threading.Thread(target=lambda: result.update(r=_project(env)))
        p.start()
        p.join(5)
        try:
            assert not p.is_alive(), "projection blocked on the session lock"
            assert result["r"] == lv.PROJECT_UPDATED
        finally:
            release.set()
            t.join(5)

    def test_session_lock_never_taken_under_liveness_lock(self, env,
                                                          monkeypatch):
        inside = {"flag": False}
        real_with_lock = lv.LivenessStore.with_lock

        def tracking(self, fn):
            def wrapped(state):
                inside["flag"] = True
                try:
                    return fn(state)
                finally:
                    inside["flag"] = False
            return real_with_lock(self, wrapped)
        monkeypatch.setattr(lv.LivenessStore, "with_lock", tracking)
        real_session_lock = loop_session.with_session_lock

        def guarded(*a, **k):
            assert not inside["flag"], "session lock under liveness lock"
            return real_session_lock(*a, **k)
        monkeypatch.setattr(loop_session, "with_session_lock", guarded)
        monkeypatch.setattr(loop_submit, "with_session_lock", guarded,
                            raising=False)
        lv.register(env["tok"]["draftor"])
        loop_submit.handle_submit_draft(env["tok"]["draftor"], env["draft"])
        _project(env)

    def test_torn_session_read_retries_without_write(self, env, monkeypatch):
        _project(env)
        before = env["store"].path.read_bytes()
        loop_submit.handle_submit_draft(env["tok"]["draftor"], env["draft"])
        calls = {"n": 0}
        real = loop_session.load_session

        def flaky(d):
            calls["n"] += 1
            if calls["n"] == 1:
                raise PermissionError("rename in progress")
            return real(d)
        monkeypatch.setattr(loop_session, "load_session", flaky)
        assert _project(env) == lv.PROJECT_RETRY
        assert env["store"].path.read_bytes() == before
        assert _project(env) == lv.PROJECT_UPDATED

    def test_corrupt_session_json_retries(self, env):
        path = env["loop_dir"] / "session.json"
        loop_session._make_writable(path)  # read-only on POSIX
        path.write_text("{", encoding="utf-8")
        assert _project(env) == lv.PROJECT_RETRY

    def test_store_write_failure_isolated_in_host(self, env, monkeypatch):
        def boom(self, state):
            raise OSError("disk full")
        monkeypatch.setattr(lv.LivenessStore, "_save", boom)
        store = lv.open_host_store(env["loop_dir"])
        assert lv.project_for_host(env["loop_dir"], store) == "error"
        assert store.last_error == "projection_failed"
        assert loop_host._project_liveness(env["loop_dir"], store) == "error"
        assert loop_host._project_liveness(env["loop_dir"], None) is None

    def test_watch_loop_survives_projection_failure(self, env, monkeypatch):
        """Timeout enforcement still runs and the loop ends validly."""
        def boom(*a, **k):
            raise RuntimeError("projection exploded")
        monkeypatch.setattr(lv, "project", boom)
        monkeypatch.setattr(loop_host, "POLL_INTERVAL", 0.05)
        s = loop_session.load_session(env["loop_dir"])
        s.get("contract", {}).pop("attention_interval", None)  # legacy: #47
        s["status"]["turn_deadline"] = "2000-01-01T00:00:00+00:00"
        loop_session.save_session(env["loop_dir"], s)
        t = threading.Thread(target=loop_host.watch_loop,
                             args=(env["loop_dir"],), daemon=True)
        t.start()
        t.join(15)
        assert not t.is_alive()
        s = loop_session.load_session(env["loop_dir"])
        assert s["status"]["stage"] == "turn_timed_out"

    def test_watch_loop_projects_terminal(self, env, monkeypatch):
        monkeypatch.setattr(loop_host, "POLL_INTERVAL", 0.05)
        lv.register(env["tok"]["reviewer"])
        loop_submit.handle_end(env["tok"]["architect"], "stop")
        t = threading.Thread(target=loop_host.watch_loop,
                             args=(env["loop_dir"],), daemon=True)
        t.start()
        t.join(15)
        assert not t.is_alive()
        assert _kinds(env, "reviewer", pending_only=True) == ["terminal"]

    def test_restart_recovery_new_store_instance(self, env):
        lv.register(env["tok"]["draftor"])
        _project(env)
        fresh = lv.open_store(env["loop_dir"])  # as after a restart
        assert lv.project(env["loop_dir"], fresh) == lv.PROJECT_UNCHANGED
        reg = lv.register(env["tok"]["draftor"])
        got = lv.poll(env["tok"]["draftor"], reg["registration_id"])
        assert [n["kind"] for n in got] == ["turn-ready"]

    def test_vanished_loop_deletes_sidecar(self, env):
        import shutil
        _project(env)
        assert env["store"].path.exists()
        shutil.rmtree(env["loop_dir"])
        assert _project(env) == lv.PROJECT_DELETED
        assert not env["store"].path.exists()

    def test_terminal_retention_deletes(self, env):
        loop_submit.handle_end(env["tok"]["architect"], "done")
        lv.project(env["loop_dir"], env["store"])
        later = lv._now() + timedelta(days=8)
        assert lv.project(env["loop_dir"], env["store"], now=later) == \
            lv.PROJECT_DELETED
        assert not env["store"].path.exists()


# ---------------------------------------------------------------------------
# Re-notify eligibility (pure)
# ---------------------------------------------------------------------------

class TestEligibility:
    def _state_session(self, env):
        _project(env)
        return env["store"].read(), loop_session.load_session(env["loop_dir"])

    def test_current_turn_owner_eligible(self, env):
        st, s = self._state_session(env)
        assert lv.renotify_eligibility(st, s, "draftor") == (True, None)

    def test_other_role_not_actionable(self, env):
        st, s = self._state_session(env)
        assert lv.renotify_eligibility(st, s, "reviewer") == \
            (False, "not_actionable")
        assert lv.renotify_eligibility(st, s, "architect") == \
            (False, "not_actionable")

    def test_terminal(self, env):
        loop_submit.handle_end(env["tok"]["architect"], "done")
        st, s = self._state_session(env)
        assert lv.renotify_eligibility(st, s, "draftor") == (False, "terminal")

    def test_pending_block_eligibility_depends_on_watcher(self, env):
        reg = lv.register(env["tok"]["reviewer"])
        loop_submit.handle_pause(env["tok"]["architect"], "hold")
        st, s = self._state_session(env)
        now = lv._now()
        assert lv.renotify_eligibility(st, s, "reviewer", now) == \
            (False, "not_actionable")  # connected watcher will get it
        stale_now = now + timedelta(seconds=46)
        assert lv.renotify_eligibility(st, s, "reviewer", stale_now) == \
            (True, None)
        n = lv.poll(env["tok"]["reviewer"], reg["registration_id"])
        lv.ack(env["tok"]["reviewer"], reg["registration_id"], n[0]["seq"])
        st = env["store"].read()
        assert lv.renotify_eligibility(st, s, "reviewer", stale_now) == \
            (False, "already_acknowledged")
