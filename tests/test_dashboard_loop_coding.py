"""
#41 Module 5 (server) — Dashboard coding-loop surfaces.

Covers the slim status projection (no raw path lists on the poll), coding
artifact serving, the Architect-only live `/snapshot` resolution
(authority, no-store, planning 409, pending/committed/stale/unknown), and
POST `/reopen` (anti-CSRF, message, stage, single-active, watcher
reporting) against a real Dashboard handler and real Git repos.
"""

import hashlib
import json
import subprocess
import sys
import threading
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

import host as loop_host  # noqa: E402
import session as loop_session  # noqa: E402
import submit as loop_submit  # noqa: E402

from test_loop_coding_mode import _tokens, git, make_planning_source, start_coding  # noqa: E402
from test_loop_coding_submit import GOOD_ARTIFACT, stage_change, write  # noqa: E402

REVIEW = "# Review\n\n## Verdict\n\nAPPROVE\n"


def _rk(path):
    return hashlib.sha256(str(Path(path).resolve()).encode()).hexdigest()[:12]


def req(url, method="GET", body=None, header=True):
    data = json.dumps(body or {}).encode() if method == "POST" else None
    r = Request(url, data=data, method=method)
    if method == "POST":
        r.add_header("Content-Type", "application/json")
        if header:
            r.add_header("X-Gator-Dashboard", "1")
    try:
        resp = urlopen(r, timeout=20)
        return resp.status, resp.read().decode(), resp.headers
    except HTTPError as e:
        return e.code, e.read().decode(), e.headers


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "T")
    (repo / ".gator").mkdir()
    write(repo / "README.md", "hello\n")
    git(repo, "add", "README.md")
    git(repo, "commit", "-q", "-m", "base")
    monkeypatch.chdir(repo)
    src_id, src_dir = make_planning_source(repo)
    loop_id, loop_dir = start_coding(repo, src_id)
    art = tmp_path / "impl.md"
    write(art, GOOD_ARTIFACT)

    rk = _rk(repo)
    reg = tmp_path / "dashboard-repos.json"
    repos = [{"name": "repo", "path": str(repo), "repo_key": rk}]
    reg.write_text(json.dumps({"schema": "gator-dashboard-registry-v1",
                               "repos": repos}), encoding="utf-8")
    monkeypatch.setattr(gator_core, "DASHBOARD_REGISTRY", reg)
    monkeypatch.setattr(dashboard, "_REGISTRY_REPOS", list(repos))
    dashboard.DashboardHandler.fast_data = {"repos": repos}
    httpd = HTTPServer(("127.0.0.1", 0), dashboard.DashboardHandler)
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}/api/repo-by-key/{rk}/loops/"
    yield {"repo": repo, "loop_dir": loop_dir, "loop_id": loop_id,
           "tok": _tokens(loop_dir), "art": art, "base": base,
           "src_id": src_id, "src_dir": src_dir}
    httpd.shutdown()
    th.join(5)
    # Drop any watcher this test attached so its host.lock is released.
    with dashboard._LOOP_HOSTS_LOCK:
        dashboard._LOOP_HOSTS.clear()


def url(env, suffix, loop_id=None):
    return env["base"] + (loop_id or env["loop_id"]) + suffix


def submit_and_approve(env):
    stage_change(env["repo"])
    loop_submit.handle_submit_implementation(
        env["tok"]["draftor"], str(env["art"]), loop_dir=env["loop_dir"])
    f = Path(str(env["art"]) + ".r.md")
    write(f, REVIEW)
    loop_submit.handle_submit_review(env["tok"]["reviewer"], str(f),
                                     approve=True, loop_dir=env["loop_dir"])


class TestStatusProjection:
    def test_slim_coding_view(self, env):
        stage_change(env["repo"])
        write(env["repo"] / "scratch.txt", "x\n")
        loop_submit.handle_submit_implementation(
            env["tok"]["draftor"], str(env["art"]), loop_dir=env["loop_dir"])
        status, text, _ = req(url(env, "/status"))
        assert status == 200
        body = json.loads(text)
        assert body["mode"] == "coding"
        c = body["coding"]
        assert set(c) == {"source_loop_id", "plan_sha256", "base_head",
                          "base_tree", "generations", "approval",
                          # #43: strict source-brief metadata + integrity
                          "source_brief", "source_brief_check",
                          "source_brief_decision",
                          # #55: declared-checkpoint projection + generation
                          "checkpoints", "generation"}
        assert c["checkpoints"] is None and c["generation"] == 0
        assert c["source_brief"] is None
        assert c["source_brief_check"] == "absent"
        assert c["source_brief_decision"] == "none_available"
        g = c["generations"][0]
        assert g["changed_count"] == 1 and g["changed_by_status"] == {"A": 1}
        assert g["residue_other_count"] == 1
        assert g["residue_loop_count"] > 0
        # Never the raw lists on the poll.
        for key in ("unstaged_paths", "changed_paths", "snapshot"):
            assert key not in text
        assert "scratch.txt" not in text
        for tok in env["tok"].values():
            assert tok not in text

    def test_planning_status_has_no_coding_key(self, env):
        status, text, _ = req(url(env, "/status", env["src_id"]))
        assert status == 200 and "coding" not in json.loads(text)


class TestArtifacts:
    @pytest.mark.parametrize("name", ["approved-plan.md",
                                      "implementation.current.md",
                                      "implementation.round-0.md"])
    def test_coding_artifacts_served(self, env, name):
        stage_change(env["repo"])
        loop_submit.handle_submit_implementation(
            env["tok"]["draftor"], str(env["art"]), loop_dir=env["loop_dir"])
        status, text, _ = req(url(env, "/artifact/" + name))
        assert status == 200 and text

    @pytest.mark.parametrize("name", ["session.json", ".tokens.json",
                                      "implementation.round-x.md"])
    def test_other_names_refused(self, env, name):
        status, _, _ = req(url(env, "/artifact/" + name))
        assert status in (400, 403, 404)


class TestSnapshot:
    def test_pending_then_committed_then_header(self, env):
        submit_and_approve(env)
        status, text, headers = req(url(env, "/snapshot"))
        assert status == 200
        assert headers.get("Cache-Control") == "no-store"
        body = json.loads(text)
        assert body["schema"] == "gator-loop-coding-snapshot-v1"
        assert body["approval_resolution"]["state"] == "pending"
        assert body["live"]["ok"] is True
        assert "unstaged_paths" not in text and "changed_paths" not in text
        git(env["repo"], "commit", "-q", "-m", "normal commit")
        body = json.loads(req(url(env, "/snapshot"))[1])
        assert body["approval_resolution"]["state"] == "committed"

    def test_stale(self, env):
        submit_and_approve(env)
        stage_change(env["repo"], text="print('drift')\n")
        body = json.loads(req(url(env, "/snapshot"))[1])
        r = body["approval_resolution"]
        assert (r["state"], r["reason"]) == ("stale", "staged_tree_changed")

    def test_unknown_on_git_failure(self, env, monkeypatch):
        import gitsnap
        submit_and_approve(env)
        monkeypatch.setattr(gitsnap, "snapshot", lambda root, base=None: {
            "ok": False, "error": "conflict", "detail": "x"})
        body = json.loads(req(url(env, "/snapshot"))[1])
        assert body["approval_resolution"]["state"] == "unknown"
        assert body["live"] == {"ok": False, "error": "conflict"}

    def test_planning_loop_409(self, env):
        status, _, headers = req(url(env, "/snapshot", env["src_id"]))
        assert status == 409 and headers.get("Cache-Control") == "no-store"

    @pytest.mark.parametrize("how,code", [("missing", 404), ("wrong_nonce", 403)])
    def test_architect_authority(self, env, how, code):
        p = env["loop_dir"] / loop_session.TOKENS_FILENAME
        if how == "missing":
            p.unlink()
        else:
            data = json.loads(p.read_text(encoding="utf-8"))
            data["architect"]["nonce"] = "00000000"
            p.write_text(json.dumps(data), encoding="utf-8")
        status, text, headers = req(url(env, "/snapshot"))
        assert status == code and headers.get("Cache-Control") == "no-store"
        assert "approval_resolution" not in text


class TestReopen:
    def test_requires_anti_csrf_header(self, env):
        submit_and_approve(env)
        r = Request(url(env, "/reopen"), data=b"", method="POST")
        try:
            urlopen(r, timeout=10)
            status = 200
        except HTTPError as e:
            status = e.code
        assert status == 403
        assert loop_session.load_session(env["loop_dir"])["status"][
            "stage"] == "implementation_approved"

    def test_rejected_post_with_body_is_delivered_reliably(self, env):
        """The 403 for a header-less POST is delivered even when the request
        carries a body: the server drains it first, so Windows never resets
        the connection (previously an intermittent ConnectionAbortedError)."""
        body = json.dumps({"message": "x" * 4000}).encode()
        for _ in range(40):
            r = Request(url(env, "/reopen"), data=body, method="POST")
            r.add_header("Content-Type", "application/json")
            try:
                urlopen(r, timeout=10)
                status = 200
            except HTTPError as e:
                status = e.code
            assert status == 403

    def test_message_required(self, env):
        submit_and_approve(env)
        status, text, _ = req(url(env, "/reopen"), "POST", {"message": "  "})
        assert status == 400 and "message" in text

    def test_wrong_stage_409(self, env):
        status, _, _ = req(url(env, "/reopen"), "POST", {"message": "x"})
        assert status == 409

    def test_success_attaches_watcher(self, env):
        submit_and_approve(env)
        status, text, _ = req(url(env, "/reopen"), "POST",
                              {"message": "drifted"})
        assert status == 200, text
        body = json.loads(text)
        assert body["ok"] is True and body["stage"] == "implementation_revision"
        assert body["watcher"] in ("attached", "already_hosted")
        s = loop_session.load_session(env["loop_dir"])
        assert s["coding"]["approval"]["invalidated_at"]
        assert s["turns"][-1]["type"] == "reopen"

    def test_single_active_guard(self, env):
        submit_and_approve(env)
        other_src, _ = make_planning_source(env["repo"], feature="other")
        start_coding(env["repo"], other_src, feature="other-coding")
        before = (env["loop_dir"] / "session.json").read_bytes()
        status, _, _ = req(url(env, "/reopen"), "POST", {"message": "x"})
        assert status == 409
        assert (env["loop_dir"] / "session.json").read_bytes() == before


# ---------------------------------------------------------------------------
# #55 M4: checkpoint projection on /status and checkpoint_summary on /loops
# ---------------------------------------------------------------------------

@pytest.fixture
def cp_env(env, tmp_path):
    """env's legacy coding loop ended; a declared two-checkpoint loop driven
    to max_rounds_exceeded on cp2 (status.round 3 > max_rounds 2)."""
    from test_loop_checkpoints import TWO_CP_PLAN, _drive_to_budget
    loop_submit.handle_end(env["tok"]["architect"], "done",
                           loop_dir=env["loop_dir"])
    src_id, _ = make_planning_source(env["repo"], plan=TWO_CP_PLAN,
                                     legacy=False, feature="cp-source")
    cp_id, cp_dir = start_coding(env["repo"], src_id, feature="cp-feature",
                                 max_rounds=2)
    c = {"repo": env["repo"], "loop_dir": cp_dir, "tok": _tokens(cp_dir),
         "art": env["art"], "tmp": tmp_path}
    _drive_to_budget(c)
    return dict(env, cp_id=cp_id, cp_src_id=src_id)


@pytest.mark.parametrize("which", ["checkpoint", "legacy-coding", "planning"])
def test_checkpoint_projection_and_list_summary(cp_env, which):
    loop_id = {"checkpoint": cp_env["cp_id"], "legacy-coding": cp_env["loop_id"],
               "planning": cp_env["cp_src_id"]}[which]
    code, text, _ = req(url(cp_env, "/status", loop_id))
    assert code == 200
    body = json.loads(text)
    code, ltext, _ = req(cp_env["base"].rstrip("/"))
    assert code == 200
    item = [i for i in json.loads(ltext)["loops"] if i["loop_id"] == loop_id][0]

    if which != "checkpoint":
        assert "checkpoint_summary" not in item
        if which == "legacy-coding":
            assert body["coding"]["checkpoints"] is None
        return

    cps = body["coding"]["checkpoints"]
    assert cps["source"] == "declared" and cps["current"] == 1
    assert cps["count"] == 2
    cp1, cp2 = cps["items"]
    assert set(cp1) == {"id", "index", "title", "state", "base_tree",
                        "accepted_tree", "findings_rounds"}
    assert (cp1["id"], cp1["title"], cp1["state"]) == ("cp1", "Widget core",
                                                       "approved")
    assert cp1["accepted_tree"] == cp2["base_tree"]
    assert (cp2["state"], cp2["findings_rounds"]) == ("active", 2)
    assert body["coding"]["generation"] == 3
    assert [g["generation"] for g in body["coding"]["generations"]] == [0, 1, 2, 3]
    assert [g["checkpoint_id"] for g in body["coding"]["generations"]] == \
        ["cp1", "cp1", "cp2", "cp2"]
    # Title only: scope and verify are never projected.
    assert "Wire the widget in" not in text and "integration test" not in text
    # Global round 3 exceeds the budget 2; the summary reports the budget.
    assert (item["round"], item["max_rounds"]) == (3, 2)
    assert item["checkpoint_summary"] == {
        "index": 2, "count": 2, "findings_round": 2, "findings_budget": 2,
        "generation": 3}
    assert "Wire the widget in" not in ltext
