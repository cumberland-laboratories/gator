"""
M3 supervised end-to-end lifecycle for the D2a receiver contract (#36).

A test-owned supervisor stands in for a vendor runtime's background-process
facility: a short-lived *launcher* process starts `gator loop participant
watch` detached, with stdout/stderr redirected to an output file (as Claude
Code background tasks do), and then EXITS — the interactive turn ending.
The watcher must outlive it, deliver, acknowledge, and exit per contract.

This proves the Gator side only. Vendor re-invocation was proven manually
by the M0 spike (.gator/vault/artifacts/2026-09-29-liveness-m0-vendor-spike.md).
"""

import json
import os
import subprocess
import sys
import time
from datetime import timedelta
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
import submit as loop_submit  # noqa: E402

GATOR_LOOP = SCRIPTS_DIR / "gator-loop.py"
LOOP_ID = "liveness-e2e-2026-09-29T00-00-00Z"

# Launcher: start the watcher detached with output to a file, then exit.
LAUNCHER = r"""
import subprocess, sys
out = open(sys.argv[1], "wb")
kw = {}
if sys.platform == "win32":
    kw["creationflags"] = (subprocess.DETACHED_PROCESS
                           | subprocess.CREATE_NEW_PROCESS_GROUP)
else:
    kw["start_new_session"] = True
p = subprocess.Popen([sys.executable] + sys.argv[2:], stdout=out,
                     stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **kw)
print(p.pid)
"""


@pytest.fixture
def env(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    loop_dir = tmp_path / ".gator" / "loops" / LOOP_ID
    loop_dir.mkdir(parents=True)
    loop_session.ensure_loops_gitignore(loop_dir.parent)
    loop_session.save_session(
        loop_dir, loop_session.create_session("liveness", LOOP_ID))
    loop_events.create_events_file(loop_dir)
    tok, stored = {}, {}
    for role in ("draftor", "reviewer", "architect"):
        t, nonce = loop_session.make_token(LOOP_ID, role)
        tok[role] = t
        stored[role] = {"nonce": nonce, "token": t}
    loop_session.save_tokens(loop_dir, stored)
    draft = tmp_path / "plan.md"
    draft.write_text("# Plan\n\n## Executive Summary\n\n- x\n\n"
                     "## Context Checked\n\n- scripts-loop charter\n"
                     "\n## Coding Checkpoints\n\n1. **Fix** \u2014 Implement the change. Verify: the focused test.\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return {"root": tmp_path, "loop_dir": loop_dir, "tok": tok,
            "store": lv.open_store(loop_dir), "draft": str(draft)}


def _launch(env, role, name):
    """Supervisor launch; the launcher process itself exits immediately."""
    out = env["root"] / f"{name}.out"
    launcher = subprocess.run(
        [sys.executable, "-c", LAUNCHER, str(out), str(GATOR_LOOP),
         "participant", "watch", "--token", env["tok"][role],
         "--max-seconds", "60", "--poll-seconds", "0.2", "--json"],
        cwd=str(env["root"]), capture_output=True, text=True, timeout=30)
    assert launcher.returncode == 0, launcher.stderr
    return out, int(launcher.stdout.strip())


def _wait_for(pred, timeout=30, what="condition"):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = pred()
        if v:
            return v
        time.sleep(0.1)
    raise AssertionError(f"timed out waiting for {what}")


def _last_json(out):
    """What an adapter does: last line of the output file that is JSON."""
    try:
        text = out.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in reversed(text.strip().splitlines()):
        try:
            return json.loads(line)
        except ValueError:
            continue
    return None


def _reg(env, role):
    st = env["store"].read()
    return st["roles"][role]["registration"] if st else None


def _loop_bytes(env):
    d = env["loop_dir"]
    return ((d / "session.json").read_bytes(),
            (d / "events.jsonl").read_bytes())


def _kill(pid):
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                       capture_output=True)
    else:
        os.kill(pid, 9)


def test_supervised_watcher_lifecycle(env):
    tok_r = env["tok"]["reviewer"]

    # 1. Launch under the supervisor; launcher has already exited.
    out1, _ = _launch(env, "reviewer", "watch1")
    _wait_for(lambda: _reg(env, "reviewer"), what="registration")
    now = lv._now()
    assert lv.classify(env["store"].read()["roles"]["reviewer"], now) == \
        "connected"
    assert _last_json(out1) is None  # still waiting

    # 2. The other role submits -> watcher delivers turn_ready, exit 0.
    loop_before = _loop_bytes(env)
    loop_submit.handle_submit_draft(env["tok"]["draftor"], env["draft"])
    loop_after_submit = _loop_bytes(env)
    assert loop_after_submit != loop_before
    payload = _wait_for(lambda: _last_json(out1), what="turn_ready delivery")
    assert payload["wake_reason"] == "turn_ready"
    assert payload["role"] == "reviewer" and payload["acked"] is True
    text = out1.read_text(encoding="utf-8")
    assert tok_r not in text and _reg(env, "reviewer")["registration_id"] \
        not in text
    rec = env["store"].read()["roles"]["reviewer"]
    assert rec["registration"]["state"] == "released"
    assert lv.classify(rec, lv._now() + timedelta(minutes=5)) == "released"
    note = [n for n in rec["notifications"] if n["kind"] == "turn-ready"][-1]
    assert note["delivered_at"] and note["acked_at"]

    # 3. Relaunch; the Architect ends the loop -> exit 2 terminal, closed.
    out2, _ = _launch(env, "reviewer", "watch2")
    _wait_for(lambda: (_reg(env, "reviewer") or {}).get("state") == "active",
              what="relaunch registration")
    loop_submit.handle_end(env["tok"]["architect"], "done")
    loop_after_end = _loop_bytes(env)
    payload = _wait_for(lambda: _last_json(out2), what="terminal delivery")
    assert payload["wake_reason"] == "terminal"
    assert _reg(env, "reviewer")["state"] == "closed"
    n_before = len(env["store"].read()["roles"]["reviewer"]["notifications"])

    # A further launch exits 2 immediately with no new notification.
    out3, _ = _launch(env, "reviewer", "watch3")
    payload = _wait_for(lambda: _last_json(out3), timeout=20,
                        what="immediate terminal exit")
    assert payload["wake_reason"] == "terminal"
    assert _reg(env, "reviewer")["state"] == "closed"
    assert len(env["store"].read()["roles"]["reviewer"]["notifications"]) \
        == n_before

    # 5. The liveness bridge never wrote loop state.
    assert _loop_bytes(env) == loop_after_end


def test_killed_watcher_goes_stale(env):
    # Reviewer: not its turn, so the watcher is still waiting when killed.
    out, pid = _launch(env, "reviewer", "killme")
    _wait_for(lambda: _reg(env, "reviewer"), what="registration")
    loop_before = _loop_bytes(env)
    _kill(pid)
    time.sleep(0.5)
    state = env["store"].read()
    rec = state["roles"]["reviewer"]
    assert rec["registration"]["state"] == "active"  # no clean release
    later = lv._now() + timedelta(
        seconds=lv.STALE_FACTOR * rec["registration"]["heartbeat_seconds"] + 1)
    assert lv.classify(rec, later) == "stale"
    session = loop_session.load_session(env["loop_dir"])
    # Stale, but nothing pending and not its turn: nothing to re-notify.
    assert lv.renotify_eligibility(state, session, "reviewer", later) == \
        (False, "not_actionable")
    assert _loop_bytes(env) == loop_before

    # The turn passes to the dead watcher's role: the turn-ready stays
    # undelivered (no receiver) and Re-notify becomes eligible.
    loop_submit.handle_submit_draft(env["tok"]["draftor"], env["draft"])
    lv.project(env["loop_dir"], env["store"])
    state = env["store"].read()
    pend = [n for n in state["roles"]["reviewer"]["notifications"]
            if lv.is_pending(n)]
    assert [n["kind"] for n in pend] == ["turn-ready"]
    assert pend[0]["delivered_at"] is None
    assert lv.classify(state["roles"]["reviewer"], later) == "stale"
    session = loop_session.load_session(env["loop_dir"])
    assert lv.renotify_eligibility(state, session, "reviewer", later) == \
        (True, None)
    assert _last_json(out) is None  # killed: never reported anything
