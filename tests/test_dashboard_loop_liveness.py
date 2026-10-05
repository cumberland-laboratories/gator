"""
M4 tests: Dashboard participant-liveness endpoint and Architect Re-notify
(#36). Covers the allowlisted observer view for every state, no-store,
degraded modes, POST auth/eligibility/rate limit, no loop-state writes,
isolation from participant-facing routes, and the supervised lifecycle as
seen through the endpoint.
"""

import hashlib
import json
import subprocess
import sys
import threading
import time
from datetime import timedelta
from http.server import HTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from conftest import SCRIPTS_DIR, load_script

import gator_core

dashboard = load_script("gator-dashboard")

LOOP_DIR = SCRIPTS_DIR / "loop"
if str(LOOP_DIR) not in sys.path:
    sys.path.insert(0, str(LOOP_DIR))

import events as loop_events  # noqa: E402
import liveness as lv  # noqa: E402
import session as loop_session  # noqa: E402
import submit as loop_submit  # noqa: E402

GATOR_LOOP = SCRIPTS_DIR / "gator-loop.py"
LOOP_ID = "liveness-dash-2026-09-29T00-00-00Z"


def _repo_key(path):
    return hashlib.sha256(str(Path(path).resolve()).encode()).hexdigest()[:12]


def _request(url, method="GET", body=None, header=True):
    data = json.dumps(body or {}).encode() if method == "POST" else None
    req = Request(url, data=data, method=method)
    if method == "POST":
        req.add_header("Content-Type", "application/json")
        if header:
            req.add_header("X-Gator-Dashboard", "1")
    try:
        resp = urlopen(req, timeout=10)
        return resp.status, resp.read().decode(), resp.headers
    except HTTPError as e:
        return e.code, e.read().decode(), e.headers


@pytest.fixture
def env(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    loop_dir = repo / ".gator" / "loops" / LOOP_ID
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
    draft = repo / "plan.md"
    draft.write_text("# Plan\n\n## Executive Summary\n\n- x\n\n"
                     "## Context Checked\n\n- scripts-loop charter\n"
                     "\n## Coding Checkpoints\n\n1. **Fix** \u2014 Implement the change. Verify: the focused test.\n", encoding="utf-8")
    monkeypatch.chdir(repo)

    rk = _repo_key(repo)
    reg_file = tmp_path / "dashboard-repos.json"
    repos = [{"name": "repo", "path": str(repo), "repo_key": rk}]
    reg_file.write_text(json.dumps({"schema": "gator-dashboard-registry-v1",
                                    "repos": repos}), encoding="utf-8")
    monkeypatch.setattr(gator_core, "DASHBOARD_REGISTRY", reg_file)
    monkeypatch.setattr(dashboard, "_REGISTRY_REPOS", list(repos))
    dashboard.DashboardHandler.fast_data = {"repos": repos}
    dashboard.DashboardHandler._renotify_last.clear()
    httpd = HTTPServer(("127.0.0.1", 0), dashboard.DashboardHandler)
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    loop_url = f"{base}/api/repo-by-key/{rk}/loops/{LOOP_ID}"
    yield {"repo": repo, "loop_dir": loop_dir, "tok": tok,
           "store": lv.open_store(loop_dir), "url": loop_url,
           "draft": str(draft), "rk": rk, "base": base}
    httpd.shutdown()
    th.join(5)


def _view(env):
    status, text, headers = _request(env["url"] + "/liveness")
    assert status == 200, text
    assert headers.get("Cache-Control") == "no-store"
    return json.loads(text), text


def _renotify(env, role, reason=None, header=True):
    body = {"role": role}
    if reason is not None:
        body["reason"] = reason
    status, text, headers = _request(env["url"] + "/renotify", "POST", body,
                                     header=header)
    return status, json.loads(text), headers


def _loop_bytes(env):
    d = env["loop_dir"]
    return ((d / "session.json").read_bytes(),
            (d / "events.jsonl").read_bytes())


# ---------------------------------------------------------------------------
# GET /liveness
# ---------------------------------------------------------------------------

class TestView:
    def test_not_registered_initial(self, env):
        v, _ = _view(env)
        assert v["available"] is True and v["degraded"] is None
        assert v["schema"] == lv.OBSERVER_SCHEMA
        for role in ("draftor", "reviewer"):
            assert v["roles"][role]["state"] == "not_registered"
        assert v["roles"]["draftor"]["renotify_eligible"] is True
        assert v["roles"]["reviewer"]["renotify_reason_code"] == \
            "not_actionable"

    def test_states_connected_released_closed(self, env):
        tok = env["tok"]["reviewer"]
        reg = lv.register(tok)
        assert _view(env)[0]["roles"]["reviewer"]["state"] == "connected"
        lv.release(tok, reg["registration_id"], "delivered")
        assert _view(env)[0]["roles"]["reviewer"]["state"] == "released"
        reg = lv.register(tok)
        lv.release(tok, reg["registration_id"], "delivered", closed=True)
        assert _view(env)[0]["roles"]["reviewer"]["state"] == "closed"

    def test_stale_and_expired(self, env, monkeypatch):
        lv.register(env["tok"]["reviewer"])
        real = lv._now
        monkeypatch.setattr(lv, "_now",
                            lambda now=None: real() + timedelta(seconds=46))
        assert _view(env)[0]["roles"]["reviewer"]["state"] == "stale"
        monkeypatch.setattr(lv, "_now",
                            lambda now=None: real() + timedelta(hours=25))
        assert _view(env)[0]["roles"]["reviewer"]["state"] == \
            "not_registered"

    def test_allowlist_excludes_secrets(self, env):
        tok = env["tok"]["reviewer"]
        reg = lv.register(tok, adapter_label="my-private-label")
        loop_submit.handle_submit_draft(env["tok"]["draftor"], env["draft"])
        lv.project(env["loop_dir"], env["store"])
        lv.poll(tok, reg["registration_id"])
        assert _renotify(env, "reviewer", "secret-reason-text")[0] == 200
        v, text = _view(env)
        state = env["store"].read()
        keys = {n["state_key"] for r in state["roles"].values()
                for n in r["notifications"]}
        for secret in [reg["registration_id"], "my-private-label",
                       "secret-reason-text", *keys,
                       *env["tok"].values()]:
            assert secret not in text
        assert set(v) == {"schema", "available", "roles", "audit", "degraded"}
        assert set(v["roles"]["reviewer"]) == {
            "state", "adapter_kind", "last_seen_at", "pending",
            "last_notification", "renotify_eligible", "renotify_reason_code"}
        assert set(v["roles"]["reviewer"]["last_notification"]) == {
            "kind", "created_at", "created_by", "delivered_at", "acked_at",
            "expired_reason"}
        assert v["audit"]["renotify_count"] == 1
        assert v["audit"]["last_actor"] == "architect"

    def test_unavailable_store(self, env, monkeypatch):
        monkeypatch.setattr(lv, "resolve_store_dir", lambda root: None)
        v, _ = _view(env)
        assert v["available"] is False and v["degraded"] == "unavailable"
        assert v["roles"] is None

    def test_transient_read_failure_is_retry(self, env, monkeypatch):
        monkeypatch.setattr(lv.LivenessStore, "read", lambda self: None)
        v, _ = _view(env)
        assert v["available"] is False and v["degraded"] == "retry"

    def test_corrupt_sidecar_degraded_and_untouched(self, env):
        env["store"].store_dir.mkdir(parents=True, exist_ok=True)
        env["store"].path.write_text("{bad", encoding="utf-8")
        v, _ = _view(env)
        assert v["available"] is True and v["degraded"] == "corrupt"
        assert env["store"].path.read_text(encoding="utf-8") == "{bad"

    def test_unknown_loop_404_and_bad_id_400(self, env):
        base = env["url"].rsplit("/", 1)[0]
        assert _request(base + "/no-such-loop/liveness")[0] == 404
        assert _request(base + "/..%5Cx/liveness")[0] in (400, 404)

    def test_artifact_named_liveness_not_hijacked(self, env):
        status, text, _ = _request(env["url"] + "/artifact/liveness")
        assert lv.OBSERVER_SCHEMA not in text

    def test_get_writes_nothing(self, env):
        before = _loop_bytes(env)
        _view(env)
        _view(env)
        assert _loop_bytes(env) == before
        assert not env["store"].path.exists()


# ---------------------------------------------------------------------------
# POST /renotify
# ---------------------------------------------------------------------------

class TestRenotify:
    def test_requires_anti_csrf_header(self, env):
        # No body: the server rejects before reading one, and on Windows an
        # unread request body can surface as ConnectionAbortedError (flake).
        req = Request(env["url"] + "/renotify", data=b"", method="POST")
        try:
            urlopen(req, timeout=10)
            status = 200
        except HTTPError as e:
            status = e.code
        assert status == 403
        assert not env["store"].path.exists()

    def test_role_validation(self, env):
        for bad in ("architect", "", None, "nobody"):
            assert _renotify(env, bad)[0] == 400
        status, body, _ = _request(env["url"] + "/renotify", "POST",
                                   {"role": "draftor", "reason": 5})[:2] + (None,)
        assert status == 400

    def test_unknown_loop(self, env):
        base = env["url"].rsplit("/", 1)[0]
        status, _, _ = _request(base + "/no-such-loop/renotify", "POST",
                                {"role": "draftor"})
        assert status == 404

    def test_ineligible_409_with_code(self, env):
        status, body, headers = _renotify(env, "reviewer")
        assert status == 409 and body["code"] == "not_actionable"
        assert headers.get("Cache-Control") == "no-store"
        loop_submit.handle_end(env["tok"]["architect"], "done")
        status, body, _ = _renotify(env, "draftor")
        assert status == 409 and body["code"] == "terminal"

    def test_appends_one_record_and_audit_without_loop_writes(self, env):
        loop_before = _loop_bytes(env)
        _, status_before, _ = _request(env["url"] + "/status")
        _, events_before, _ = _request(env["url"] + "/events")
        status, body, headers = _renotify(env, "draftor", "please look")
        assert status == 200 and body == {"ok": True, "role": "draftor",
                                          "kind": "turn-ready"}
        assert headers.get("Cache-Control") == "no-store"
        st = env["store"].read()
        notes = st["roles"]["draftor"]["notifications"]
        assert [n["created_by"] for n in notes] == ["architect"]
        assert st["audit"][0]["reason"] == "please look"
        assert st["audit"][0]["actor"] == "architect"
        assert _loop_bytes(env) == loop_before
        assert _request(env["url"] + "/status")[1] == status_before
        assert _request(env["url"] + "/events")[1] == events_before

    def test_rate_limited_and_refusal_does_not_consume(self, env):
        assert _renotify(env, "reviewer")[0] == 409  # refusal: no slot used
        assert _renotify(env, "draftor")[0] == 200
        status, body, _ = _renotify(env, "draftor")
        assert status == 429 and body["code"] == "rate_limited"
        assert len(env["store"].read()["roles"]["draftor"][
            "notifications"]) == 1

    def test_stale_pending_role_eligible(self, env, monkeypatch):
        """A role with an undelivered record and a dead watcher."""
        lv.register(env["tok"]["reviewer"])
        loop_submit.handle_pause(env["tok"]["architect"], "hold")
        lv.project(env["loop_dir"], env["store"])
        status, body, _ = _renotify(env, "reviewer")
        assert status == 409 and body["code"] == "not_actionable"
        real = lv._now
        monkeypatch.setattr(lv, "_now",
                            lambda now=None: real() + timedelta(seconds=46))
        status, body, _ = _renotify(env, "reviewer")
        assert status == 200 and body["kind"] == "architect-block"

    def test_unavailable_store_503(self, env, monkeypatch):
        monkeypatch.setattr(lv, "resolve_store_dir", lambda root: None)
        status, body, _ = _renotify(env, "draftor")
        assert status == 503 and body["code"] == "unavailable"

    def test_reason_sanitized(self, env):
        tok = env["tok"]["draftor"]
        _renotify(env, "draftor", f"see {tok}\x00" + "x" * 400)
        reason = env["store"].read()["audit"][0]["reason"]
        assert tok not in reason and len(reason) <= 200 and "\x00" not in reason


# ---------------------------------------------------------------------------
# Architect authority (whiteboard M4 P1)
# ---------------------------------------------------------------------------

def _tokens_path(env):
    return env["loop_dir"] / loop_session.TOKENS_FILENAME


def _break_tokens(env, how):
    p = _tokens_path(env)
    if how == "missing":
        p.unlink()
    elif how == "malformed":
        p.write_text("{not json", encoding="utf-8")
    elif how == "not_object":
        p.write_text("[1, 2]", encoding="utf-8")
    elif how == "no_architect":
        data = json.loads(p.read_text(encoding="utf-8"))
        del data["architect"]
        p.write_text(json.dumps(data), encoding="utf-8")
    elif how == "wrong_nonce":
        data = json.loads(p.read_text(encoding="utf-8"))
        data["architect"]["nonce"] = "00000000"
        p.write_text(json.dumps(data), encoding="utf-8")


AUTH_CASES = [("missing", 404), ("malformed", 404), ("not_object", 404),
              ("no_architect", 404), ("wrong_nonce", 403)]


class TestArchitectAuthority:
    @pytest.mark.parametrize("how,code", AUTH_CASES)
    def test_renotify_denied_without_architect_authority(self, env, how,
                                                         code):
        _break_tokens(env, how)
        loop_before = _loop_bytes(env)
        status, body, headers = _renotify(env, "draftor", "nudge")
        assert status == code, body
        assert headers.get("Cache-Control") == "no-store"
        assert not env["store"].path.exists()  # no sidecar write
        assert _loop_bytes(env) == loop_before
        assert dashboard.DashboardHandler._renotify_last == {}

    @pytest.mark.parametrize("how,code", AUTH_CASES)
    def test_liveness_view_denied_without_architect_authority(self, env, how,
                                                              code):
        _break_tokens(env, how)
        status, text, headers = _request(env["url"] + "/liveness")
        assert status == code, text
        assert headers.get("Cache-Control") == "no-store"
        assert lv.OBSERVER_SCHEMA not in text

    def test_denial_never_echoes_tokens(self, env):
        _break_tokens(env, "wrong_nonce")
        status, body, _ = _renotify(env, "draftor")
        for tok in env["tok"].values():
            assert tok not in json.dumps(body)

    def test_existing_action_malformed_tokens_is_404_not_500(self, env):
        _break_tokens(env, "malformed")
        status, text, _ = _request(env["url"] + "/pause", "POST",
                                   {"message": "x"})
        assert status == 404 and "tokens unreadable" in text


# ---------------------------------------------------------------------------
# Startup retention sweep
# ---------------------------------------------------------------------------

def test_startup_sweep_deletes_orphans_and_is_guarded(env, monkeypatch):
    import shutil
    lv.project(env["loop_dir"], env["store"])
    orphan = lv.LivenessStore(env["store"].store_dir, "gone-loop")
    orphan.with_lock(lambda s: (s, None))
    assert orphan.path.exists()
    dashboard._sweep_liveness(str(env["repo"]))
    assert not orphan.path.exists()
    assert env["store"].path.exists()  # live loop kept
    shutil.rmtree(env["loop_dir"])
    dashboard._sweep_liveness(str(env["repo"]))
    assert not env["store"].path.exists()

    def boom(*a, **k):
        raise RuntimeError("sweep exploded")
    monkeypatch.setattr(lv, "sweep", boom)
    dashboard._sweep_liveness(str(env["repo"]))  # never raises
    monkeypatch.setattr(dashboard, "_REGISTRY_REPOS",
                        [{"name": "repo", "path": str(env["repo"])}])
    dashboard._adopt_orphaned_loops()  # adoption unaffected by sweep failure


# ---------------------------------------------------------------------------
# Participant-facing routes never carry liveness data
# ---------------------------------------------------------------------------

def test_participant_routes_carry_no_liveness(env):
    tok = env["tok"]["reviewer"]
    reg = lv.register(tok, adapter_label="lbl-xyz")
    lv.project(env["loop_dir"], env["store"])
    _renotify(env, "draftor", "audit-reason-xyz")
    for route in ("/status", "/events"):
        _, text, _ = _request(env["url"] + route)
        # (The fixture loop's feature is named "liveness", so match on
        # data that can only come from the sidecar.)
        for needle in (reg["registration_id"], "lbl-xyz", "audit-reason-xyz",
                       "renotify", "turn-ready", "generic-watcher",
                       "last_seen_at", "registration_id"):
            assert needle not in text, (route, needle)
    status_json = json.loads(_request(env["url"] + "/status")[1])
    assert not [k for k in status_json if "liveness" in k or "notif" in k]


# ---------------------------------------------------------------------------
# Supervised lifecycle through the endpoint (extends the M3 test)
# ---------------------------------------------------------------------------

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


def _launch(env, name):
    out = env["repo"] / f"{name}.out"
    r = subprocess.run(
        [sys.executable, "-c", LAUNCHER, str(out), str(GATOR_LOOP),
         "participant", "watch", "--token", env["tok"]["reviewer"],
         "--max-seconds", "60", "--poll-seconds", "0.2", "--json"],
        cwd=str(env["repo"]), capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return out, int(r.stdout.strip())


def _wait_state(env, want, timeout=30):
    end = time.monotonic() + timeout
    last = None
    while time.monotonic() < end:
        v = _view(env)[0]
        if not v["available"]:  # degraded "retry" mid-write: poll again
            last = v["degraded"]
            time.sleep(0.1)
            continue
        last = v["roles"]["reviewer"]["state"]
        if last == want:
            return
        time.sleep(0.1)
    raise AssertionError(f"reviewer state {last!r}, wanted {want!r}")


def _kill(pid):
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                       capture_output=True)
    else:
        import os
        os.kill(pid, 9)


def test_lifecycle_through_endpoint(env, monkeypatch):
    _launch(env, "w1")
    _wait_state(env, "connected")
    loop_submit.handle_submit_draft(env["tok"]["draftor"], env["draft"])
    _wait_state(env, "released")
    v = _view(env)[0]["roles"]["reviewer"]
    assert v["last_notification"]["kind"] == "turn-ready"
    assert v["last_notification"]["acked_at"] is not None

    _launch(env, "w2")
    _wait_state(env, "connected")
    loop_submit.handle_end(env["tok"]["architect"], "done")
    _wait_state(env, "closed")

    # Killed watcher on a fresh loop state: stale + Re-notify eligible.
    loop_session.save_session(
        env["loop_dir"], loop_session.create_session("liveness", LOOP_ID))
    lv.project(env["loop_dir"], env["store"])
    _, pid = _launch(env, "w3")
    _wait_state(env, "connected")
    _kill(pid)
    loop_session.save_session(env["loop_dir"], dict(
        loop_session.load_session(env["loop_dir"]),
        status=dict(loop_session.load_session(env["loop_dir"])["status"],
                    stage="plan_review", next_role="reviewer")))
    lv.project(env["loop_dir"], env["store"])
    real = lv._now
    monkeypatch.setattr(lv, "_now",
                        lambda now=None: real() + timedelta(seconds=46))
    v = _view(env)[0]["roles"]["reviewer"]
    assert v["state"] == "stale"
    assert v["renotify_eligible"] is True
