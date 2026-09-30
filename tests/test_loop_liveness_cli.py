"""
M2 tests for loop participant liveness: register / heartbeat / poll / ack /
release, the run_watch receiver, and the `gator loop participant` CLI (#36).

In-process tests stub projection to a no-op so they exercise the M2
primitives in isolation (projection is covered by
test_loop_liveness_projection.py); notifications are seeded with the REAL
current state_key, so the subprocess CLI tests — which run the real M3
projection — keep them as current-generation records.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "src" / "gator_command" / "scripts"
LOOP_DIR = SCRIPTS_DIR / "loop"
for p in [str(SCRIPTS_DIR), str(LOOP_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import events as loop_events  # noqa: E402
import liveness as lv  # noqa: E402
import session as loop_session  # noqa: E402

GATOR_LOOP = SCRIPTS_DIR / "gator-loop.py"
LOOP_ID = "liveness-cli-2026-09-29T00-00-00Z"


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A Git worktree with one loop and role tokens; cwd = repo root."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    loop_dir = tmp_path / ".gator" / "loops" / LOOP_ID
    loop_dir.mkdir(parents=True)
    loop_session.ensure_loops_gitignore(loop_dir.parent)
    loop_session.save_session(
        loop_dir, loop_session.create_session("liveness", LOOP_ID))
    loop_events.create_events_file(loop_dir)
    tokens = {}
    stored = {}
    for role in ("draftor", "reviewer", "architect"):
        tok, nonce = loop_session.make_token(LOOP_ID, role)
        tokens[role] = tok
        stored[role] = {"nonce": nonce, "token": tok}
    loop_session.save_tokens(loop_dir, stored)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(lv, "project", lambda *a, **k: "unchanged")
    store = lv.open_store(loop_dir)
    return {"root": tmp_path, "loop_dir": loop_dir, "tok": tokens,
            "store": store}


def _seed(store, role, kind="turn-ready", stage="plan_review", rnd=1):
    """Append one pending notification for the CURRENT state generation."""
    key = lv.state_key(loop_session.load_session(
        Path.cwd() / ".gator" / "loops" / LOOP_ID))

    def _fn(state):
        rec = state["roles"][role]
        seq = rec["next_seq"]
        rec["notifications"].append({
            "seq": seq, "kind": kind, "state_key": key, "stage": stage,
            "round": rnd, "created_at": lv.iso(lv._now()),
            "created_by": "projection",
            "delivered_at": None, "delivered_generation": None,
            "acked_at": None, "acked_generation": None,
            "expired_at": None, "expired_reason": None,
        })
        rec["next_seq"] = seq + 1
        return state, seq
    return store.with_lock(_fn)


def _loop_bytes(env):
    d = env["loop_dir"]
    return ((d / "session.json").read_bytes(),
            (d / "events.jsonl").read_bytes())


def _reg_state(env, role):
    return env["store"].read()["roles"][role]["registration"]


# ---------------------------------------------------------------------------
# Registration and authentication
# ---------------------------------------------------------------------------

class TestRegister:
    @pytest.mark.parametrize("role", ["draftor", "reviewer"])
    def test_model_roles_register(self, env, role):
        reg = lv.register(env["tok"][role])
        assert re.fullmatch(r"[0-9a-f]{32}", reg["registration_id"])
        assert reg["generation"] == 1 and reg["role"] == role
        stored = _reg_state(env, role)
        assert stored["state"] == "active"
        assert stored["adapter"] == {"kind": "generic-watcher",
                                     "capabilities": ["poll", "ack"]}
        other = "reviewer" if role == "draftor" else "draftor"
        assert _reg_state(env, other) is None

    def test_architect_token_rejected_without_write(self, env):
        with pytest.raises(PermissionError):
            lv.register(env["tok"]["architect"])
        assert not env["store"].path.exists()

    def test_tampered_token_rejected_without_write(self, env):
        bad = env["tok"]["reviewer"][:-2] + "zz"
        with pytest.raises(ValueError) as ei:
            lv.register(bad)
        assert bad not in str(ei.value)
        assert not env["store"].path.exists()

    def test_wrong_loop_dir_rejected(self, env, tmp_path):
        other = env["root"] / ".gator" / "loops" / "some-other-loop"
        other.mkdir()
        with pytest.raises(ValueError):
            lv.register(env["tok"]["reviewer"], loop_dir=other)

    def test_label_sanitized(self, env):
        lv.register(env["tok"]["reviewer"],
                    adapter_label="claude\tglp_secretish" + "x" * 80)
        label = _reg_state(env, "reviewer")["adapter"]["label"]
        assert len(label) <= 40 and "\t" not in label
        assert "glp_secretish" not in label

    def test_unavailable_outside_git(self, env, monkeypatch):
        monkeypatch.setattr(lv, "resolve_store_dir", lambda root: None)
        with pytest.raises(lv.LivenessUnavailableError):
            lv.register(env["tok"]["reviewer"])


# ---------------------------------------------------------------------------
# Supersession, poll, ack
# ---------------------------------------------------------------------------

class TestPollAck:
    def test_poll_delivers_once_per_generation(self, env):
        reg = lv.register(env["tok"]["reviewer"])
        _seed(env["store"], "reviewer")
        first = lv.poll(env["tok"]["reviewer"], reg["registration_id"])
        assert [n["seq"] for n in first] == [1]
        assert set(first[0]) == {"seq", "kind", "stage", "round",
                                 "created_at", "created_by"}
        assert lv.poll(env["tok"]["reviewer"], reg["registration_id"]) == []

    def test_cross_role_isolation(self, env):
        rd = lv.register(env["tok"]["draftor"])
        rr = lv.register(env["tok"]["reviewer"])
        _seed(env["store"], "reviewer")
        assert lv.poll(env["tok"]["draftor"], rd["registration_id"]) == []
        # Another role's registration id is useless with this role's token.
        with pytest.raises(lv.SupersededError):
            lv.poll(env["tok"]["draftor"], rr["registration_id"])

    def test_reregistration_supersedes_and_redelivers(self, env):
        tok = env["tok"]["reviewer"]
        old = lv.register(tok)
        _seed(env["store"], "reviewer")
        assert len(lv.poll(tok, old["registration_id"])) == 1  # not acked
        new = lv.register(tok)
        assert new["generation"] == 2
        with pytest.raises(lv.SupersededError):
            lv.poll(tok, old["registration_id"])
        with pytest.raises(lv.SupersededError):
            lv.ack(tok, old["registration_id"], 1)
        with pytest.raises(lv.SupersededError):
            lv.heartbeat(tok, old["registration_id"])
        again = lv.poll(tok, new["registration_id"])
        assert [n["seq"] for n in again] == [1]
        assert lv.ack(tok, new["registration_id"], 1) is True
        rec = env["store"].read()["roles"]["reviewer"]
        assert rec["notifications"][0]["acked_generation"] == 2
        assert rec["superseded"][-1]["generation"] == 1

    def test_generation_never_reused_after_retention_drop(self, env):
        tok = env["tok"]["reviewer"]
        reg = lv.register(tok)
        _seed(env["store"], "reviewer")
        lv.poll(tok, reg["registration_id"])

        def _drop(state):  # as prune() does for an expired registration
            state["roles"]["reviewer"]["registration"] = None
            state["roles"]["reviewer"]["superseded"] = []
            return state, None
        env["store"].with_lock(_drop)
        new = lv.register(tok)
        assert new["generation"] == 2
        assert [n["seq"] for n in lv.poll(tok, new["registration_id"])] == [1]

    def test_ack_rules(self, env):
        tok = env["tok"]["reviewer"]
        reg = lv.register(tok)
        _seed(env["store"], "reviewer")
        with pytest.raises(lv.SupersededError):  # not delivered yet
            lv.ack(tok, reg["registration_id"], 1)
        lv.poll(tok, reg["registration_id"])
        assert lv.ack(tok, reg["registration_id"], 1) is True
        assert lv.ack(tok, reg["registration_id"], 1) is False
        with pytest.raises(KeyError):
            lv.ack(tok, reg["registration_id"], 99)

    def test_heartbeat_and_release(self, env):
        tok = env["tok"]["draftor"]
        reg = lv.register(tok)
        lv.release(tok, reg["registration_id"], "delivered")
        assert _reg_state(env, "draftor")["state"] == "released"
        lv.heartbeat(tok, reg["registration_id"])
        st = _reg_state(env, "draftor")
        assert st["state"] == "active" and "released_reason" not in st
        lv.release(tok, reg["registration_id"], "delivered", closed=True)
        assert _reg_state(env, "draftor")["state"] == "closed"
        with pytest.raises(ValueError):
            lv.release(tok, reg["registration_id"], "bored")

    def test_closed_is_one_way(self, env):
        """Whiteboard P2 regression: after terminal delivery closes the
        registration, the old in-process id cannot revive it."""
        _seed(env["store"], "reviewer", kind="terminal", stage="plan_approved")
        tok = env["tok"]["reviewer"]
        reg = lv.register(tok)
        lv.poll(tok, reg["registration_id"])
        lv.ack(tok, reg["registration_id"], 1)
        lv.release(tok, reg["registration_id"], "delivered", closed=True)
        loop_before = _loop_bytes(env)
        store_before = env["store"].path.read_bytes()
        rid = reg["registration_id"]
        for call in (lambda: lv.heartbeat(tok, rid),
                     lambda: lv.poll(tok, rid),
                     lambda: lv.ack(tok, rid, 1),
                     lambda: lv.release(tok, rid, "delivered"),
                     lambda: lv.release(tok, rid, "interrupted", closed=True)):
            with pytest.raises(lv.RegistrationClosedError):
                call()
        assert _reg_state(env, "reviewer")["state"] == "closed"
        assert env["store"].path.read_bytes() == store_before
        assert _loop_bytes(env) == loop_before
        # A freshly launched watcher may still supersede it.
        new = lv.register(tok)
        assert new["generation"] == reg["generation"] + 1
        assert _reg_state(env, "reviewer")["state"] == "active"

    def test_no_session_or_event_mutation(self, env):
        before = _loop_bytes(env)
        tok = env["tok"]["reviewer"]
        reg = lv.register(tok)
        _seed(env["store"], "reviewer")
        lv.poll(tok, reg["registration_id"])
        lv.ack(tok, reg["registration_id"], 1)
        lv.heartbeat(tok, reg["registration_id"])
        lv.release(tok, reg["registration_id"], "delivered")
        lv.own_status(tok)
        assert _loop_bytes(env) == before


# ---------------------------------------------------------------------------
# run_watch (D2a receiver)
# ---------------------------------------------------------------------------

class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


class TestRunWatch:
    @pytest.mark.parametrize("kind,code,wake,reg_state", [
        ("turn-ready", 0, "turn_ready", "released"),
        ("architect-block", 2, "architect_block", "released"),
        ("terminal", 2, "terminal", "closed"),
    ])
    def test_delivery_outcomes(self, env, kind, code, wake, reg_state):
        _seed(env["store"], "reviewer", kind=kind)
        clk = _Clock()
        got, payload = lv.run_watch(env["tok"]["reviewer"], 30,
                                    clock=clk, sleep=clk.sleep)
        assert got == code
        assert payload["wake_reason"] == wake and payload["acked"] is True
        assert payload["kind"] == kind and payload["role"] == "reviewer"
        reg = _reg_state(env, "reviewer")
        assert reg["state"] == reg_state
        assert reg["released_reason"] == "delivered"
        note = env["store"].read()["roles"]["reviewer"]["notifications"][0]
        assert note["acked_at"] is not None

    def test_newest_reported_all_acked(self, env):
        _seed(env["store"], "draftor", kind="architect-block")
        _seed(env["store"], "draftor", kind="turn-ready", stage="plan_revision")
        clk = _Clock()
        code, payload = lv.run_watch(env["tok"]["draftor"], 30,
                                     clock=clk, sleep=clk.sleep)
        assert code == 0 and payload["seq"] == 2
        notes = env["store"].read()["roles"]["draftor"]["notifications"]
        assert all(n["acked_at"] for n in notes)

    def test_delivery_after_waiting(self, env):
        clk = _Clock()
        calls = {"n": 0}

        def sleep(s):
            clk.sleep(s)
            calls["n"] += 1
            if calls["n"] == 2:
                _seed(env["store"], "reviewer")
        code, payload = lv.run_watch(env["tok"]["reviewer"], 60,
                                     poll_seconds=5, clock=clk, sleep=sleep)
        assert code == 0 and clk.t == 10

    def test_still_waiting(self, env):
        clk = _Clock()
        code, payload = lv.run_watch(env["tok"]["reviewer"], 12,
                                     poll_seconds=5, clock=clk,
                                     sleep=clk.sleep)
        assert code == lv.WATCH_EXIT_STILL_WAITING == 3
        assert payload["wake_reason"] == "still_waiting"
        assert clk.t == 12  # last sleep capped at the remaining time
        reg = _reg_state(env, "reviewer")
        assert reg["state"] == "released"
        assert reg["released_reason"] == "still_waiting"

    def test_superseded_mid_watch_leaves_new_receiver_alone(self, env):
        clk = _Clock()
        holder = {}

        def sleep(s):
            clk.sleep(s)
            holder["new"] = lv.register(env["tok"]["reviewer"])
        code, payload = lv.run_watch(env["tok"]["reviewer"], 60,
                                     clock=clk, sleep=sleep)
        assert code == 4 and payload["wake_reason"] == "superseded"
        reg = _reg_state(env, "reviewer")
        assert reg["registration_id"] == holder["new"]["registration_id"]
        assert reg["state"] == "active"

    def test_closed_mid_watch_reports_terminal_without_write(self, env):
        clk = _Clock()

        def sleep(s):
            clk.sleep(s)

            def _close(state):  # the terminal path closes the receiver
                state["roles"]["reviewer"]["registration"]["state"] = "closed"
                return state, None
            env["store"].with_lock(_close)
            sleep.snapshot = env["store"].path.read_bytes()
        code, payload = lv.run_watch(env["tok"]["reviewer"], 60,
                                     clock=clk, sleep=sleep)
        assert code == 2 and payload["wake_reason"] == "terminal"
        assert _reg_state(env, "reviewer")["state"] == "closed"
        assert env["store"].path.read_bytes() == sleep.snapshot

    def test_interrupted_releases(self, env):
        def sleep(s):
            raise KeyboardInterrupt()
        code, payload = lv.run_watch(env["tok"]["reviewer"], 60, sleep=sleep)
        assert code == 130 and payload["wake_reason"] == "interrupted"
        reg = _reg_state(env, "reviewer")
        assert reg["state"] == "released"
        assert reg["released_reason"] == "interrupted"

    def test_heartbeat_advertised(self, env):
        clk = _Clock()
        lv.run_watch(env["tok"]["reviewer"], 1, poll_seconds=40,
                     clock=clk, sleep=clk.sleep)
        assert _reg_state(env, "reviewer")["heartbeat_seconds"] == 40

    def test_errors_are_redacted(self, env):
        bad = env["tok"]["reviewer"][:-2] + "zz"
        code, payload = lv.run_watch(bad, 5)
        assert code == 1 and payload["wake_reason"] == "error"
        assert bad not in json.dumps(payload)
        code, _ = lv.run_watch(env["tok"]["architect"], 5)
        assert code == 1

    def test_unavailable_store(self, env, monkeypatch):
        monkeypatch.setattr(lv, "resolve_store_dir", lambda root: None)
        code, payload = lv.run_watch(env["tok"]["reviewer"], 5)
        assert code == 1 and "unavailable" in payload["error"]


# ---------------------------------------------------------------------------
# CLI (real subprocess — the adapter contract)
# ---------------------------------------------------------------------------

def _cli(env, *args):
    return subprocess.run(
        [sys.executable, str(GATOR_LOOP), "participant", *args],
        cwd=str(env["root"]), capture_output=True, text=True, timeout=60)


class TestCli:
    def test_watch_json_single_line_contract(self, env):
        _seed(env["store"], "reviewer")
        tok = env["tok"]["reviewer"]
        proc = _cli(env, "watch", "--token", tok, "--max-seconds", "10",
                    "--poll-seconds", "0.1", "--json")
        assert proc.returncode == 0, proc.stderr
        assert proc.stderr == ""
        lines = proc.stdout.strip().splitlines()
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["wake_reason"] == "turn_ready"
        assert payload["schema"] == lv.PARTICIPANT_SCHEMA
        reg_id = _reg_state(env, "reviewer")["registration_id"]
        key = env["store"].read()["roles"]["reviewer"]["notifications"][0][
            "state_key"]
        for secret in (tok, reg_id, key):
            assert secret not in proc.stdout

    def test_watch_still_waiting_exit_3(self, env):
        # Reviewer: the draftor owns the first turn, so real projection
        # would (correctly) give the draftor an immediate turn-ready.
        proc = _cli(env, "watch", "--token", env["tok"]["reviewer"],
                    "--max-seconds", "0.3", "--poll-seconds", "0.1", "--json")
        assert proc.returncode == 3
        assert json.loads(proc.stdout)["wake_reason"] == "still_waiting"

    def test_watch_requires_max_seconds(self, env):
        proc = _cli(env, "watch", "--token", env["tok"]["draftor"])
        assert proc.returncode == 2
        assert "--max-seconds" in proc.stderr

    def test_watch_architect_rejected(self, env):
        tok = env["tok"]["architect"]
        proc = _cli(env, "watch", "--token", tok, "--max-seconds", "1",
                    "--json")
        assert proc.returncode == 1
        assert json.loads(proc.stdout)["wake_reason"] == "error"
        assert tok not in proc.stdout + proc.stderr
        assert not env["store"].path.exists()

    def test_watch_text_mode_no_secrets(self, env):
        _seed(env["store"], "reviewer", kind="terminal", stage="plan_approved")
        tok = env["tok"]["reviewer"]
        proc = _cli(env, "watch", "--token", tok, "--max-seconds", "5",
                    "--poll-seconds", "0.1")
        assert proc.returncode == 2
        assert "Loop ended" in proc.stdout
        assert "not that any work was done" in proc.stdout
        assert tok not in proc.stdout

    def test_status_own_role_only(self, env):
        lv.register(env["tok"]["draftor"])
        rr = lv.register(env["tok"]["reviewer"])
        _seed(env["store"], "reviewer")
        proc = _cli(env, "status", "--token", env["tok"]["draftor"], "--json")
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert out["role"] == "draftor" and out["state"] == "connected"
        assert out["pending"] == 0 and out["last_notification"] is None
        assert "reviewer" not in proc.stdout
        assert rr["registration_id"] not in proc.stdout

    def test_status_unavailable_outside_git(self, env):
        import shutil
        shutil.rmtree(env["root"] / ".git")
        proc = _cli(env, "status", "--token", env["tok"]["draftor"], "--json")
        # A parent directory could be a Git repo; accept either outcome but
        # never a crash, and state must be consistent with availability.
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert (out["available"] is False) == (out["state"] == "unavailable")

    def test_wait_unchanged_without_registration(self, env):
        """M6 compatibility: bounded `wait` keeps its exit contract and never
        creates or touches the liveness sidecar when nobody registered."""
        def wait(role, secs="0.3"):
            return subprocess.run(
                [sys.executable, str(GATOR_LOOP), "wait", "--token",
                 env["tok"][role], "--max-seconds", secs, "--poll", "0.1",
                 "--json"],
                cwd=str(env["root"]), capture_output=True, text=True,
                timeout=60)
        before = _loop_bytes(env)
        r = wait("draftor")
        assert r.returncode == 0
        assert json.loads(r.stdout)["wake_reason"] == "already_your_turn"
        r = wait("reviewer")
        assert r.returncode == 3
        assert json.loads(r.stdout)["wake_reason"] == "still_waiting"
        assert _loop_bytes(env) == before
        store_dir = env["store"].store_dir
        assert not store_dir.exists() or not any(store_dir.iterdir())
        import submit as loop_submit
        loop_submit.handle_end(env["tok"]["architect"], "done")
        r = wait("reviewer")
        assert r.returncode == 2
        assert json.loads(r.stdout)["wake_reason"] == "terminal"
        assert not store_dir.exists() or not any(store_dir.iterdir())

    def test_cli_leaves_loop_untouched(self, env):
        before = _loop_bytes(env)
        _seed(env["store"], "reviewer")
        _cli(env, "watch", "--token", env["tok"]["reviewer"],
             "--max-seconds", "5", "--poll-seconds", "0.1", "--json")
        _cli(env, "status", "--token", env["tok"]["reviewer"])
        assert _loop_bytes(env) == before
