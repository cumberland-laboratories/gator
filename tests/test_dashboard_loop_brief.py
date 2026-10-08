"""
#43 M2 (server + CLI) — Architect brief visibility.

Dashboard start with an optional brief; the strict, positionally bound
`/status` projection (metadata + integrity only, never content); coding
source-brief projection and decision; artifact serving; join-prompt
pointer; and CLI status brief lines with integrity markers.
"""

import hashlib
import json
import os
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

from test_loop_coding_mode import PLAN_TEXT, _tokens, git  # noqa: E402

# #55: flagged planning sources must declare checkpoints.
CHECKPOINTED_PLAN = PLAN_TEXT + (
    "\n## Coding Checkpoints\n\n1. **Fix** — Implement the change. "
    "Verify: the focused test.\n").encode("utf-8")

GATOR_LOOP = SCRIPTS_DIR / "gator-loop.py"
BRIEF = "# Brief\n\nSECRET-CONTENT-MARKER: prioritize Windows paths.\n"
MAX = loop_session.MAX_BRIEF_BYTES


def _rk(path):
    return hashlib.sha256(str(Path(path).resolve()).encode()).hexdigest()[:12]


def req(url, method="GET", body=None):
    data = json.dumps(body).encode() if method == "POST" else None
    r = Request(url, data=data, method=method)
    if method == "POST":
        r.add_header("Content-Type", "application/json")
        r.add_header("X-Gator-Dashboard", "1")
    try:
        resp = urlopen(r, timeout=20)
        return resp.status, resp.read().decode()
    except HTTPError as e:
        return e.code, e.read().decode()


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "T")
    (repo / ".gator").mkdir()
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-q", "-m", "base")
    (repo / "sketch.md").write_text("# Sketch\n", encoding="utf-8")
    git(repo, "add", "sketch.md")
    git(repo, "commit", "-q", "-m", "sketch")
    monkeypatch.chdir(repo)
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
    base = f"http://127.0.0.1:{httpd.server_address[1]}/api/repo-by-key/{rk}/loops"
    yield {"repo": repo, "base": base}
    httpd.shutdown()
    th.join(5)
    with dashboard._LOOP_HOSTS_LOCK:
        dashboard._LOOP_HOSTS.clear()


def loops(repo):
    d = repo / ".gator" / "loops"
    return sorted(p.name for p in d.iterdir() if p.is_dir()) if d.is_dir() else []


def start(env, **body):
    payload = {"feature": "feat", "sketch_path": "sketch.md"}
    payload.update(body)
    return req(env["base"] + "/start", "POST", payload)


def status(env, loop_id):
    code, text = req(env["base"] + f"/{loop_id}/status")
    assert code == 200, text
    return json.loads(text), text


def end_and_free(env, loop_id):
    """Make the loop terminal so the next start is allowed."""
    d = env["repo"] / ".gator" / "loops" / loop_id
    s = loop_session.load_session(d)
    s["status"].update(stage="ended_by_architect", next_role=None)
    loop_session.save_session(d, s)
    with dashboard._LOOP_HOSTS_LOCK:
        dashboard._LOOP_HOSTS.clear()


# ---------------------------------------------------------------------------
# Dashboard start with a brief
# ---------------------------------------------------------------------------

class TestStart:
    def test_start_with_brief(self, env):
        code, text = start(env, brief=BRIEF)
        assert code == 201, text
        loop_id = json.loads(text)["loop_id"]
        d = env["repo"] / ".gator" / "loops" / loop_id
        assert (d / "architect-brief.md").read_bytes() == BRIEF.encode()
        body, raw = status(env, loop_id)
        assert body["brief"] == {"artifact": "architect-brief.md",
                                 "sha256": hashlib.sha256(BRIEF.encode()).hexdigest(),
                                 "bytes": len(BRIEF.encode())}
        assert body["brief_check"] == "ok"
        assert "SECRET-CONTENT-MARKER" not in raw  # never content in /status

    @pytest.mark.parametrize("brief", [None, "", "   \n"])
    def test_no_brief_is_absent(self, env, brief):
        kw = {} if brief is None else {"brief": brief}
        code, text = start(env, **kw)
        assert code == 201, text
        body, _ = status(env, json.loads(text)["loop_id"])
        assert body["brief"] is None and body["brief_check"] == "absent"

    @pytest.mark.parametrize("brief,why", [
        (42, "string"),
        ("a\x00b", "NUL"),
        ("é" * (MAX // 2) + "x", "limit"),
    ], ids=["non-string", "nul", "over-by-one-multibyte"])
    def test_rejections_400_no_partial(self, env, brief, why):
        before = loops(env["repo"])
        code, text = start(env, brief=brief)
        assert code == 400 and why in text
        assert loops(env["repo"]) == before

    def test_exact_multibyte_limit_accepted(self, env):
        exact = "é" * (MAX // 2)
        assert len(exact.encode("utf-8")) == MAX
        code, text = start(env, brief=exact)
        assert code == 201, text


# ---------------------------------------------------------------------------
# Strict, positionally bound status projection
# ---------------------------------------------------------------------------

def started_with_brief(env):
    code, text = start(env, brief=BRIEF)
    assert code == 201, text
    loop_id = json.loads(text)["loop_id"]
    return loop_id, env["repo"] / ".gator" / "loops" / loop_id


class TestStatusProjection:
    def test_injected_fields_never_served(self, env):
        loop_id, d = started_with_brief(env)
        s = loop_session.load_session(d)
        s["brief"].update(content="INJECTED-CONTENT", path="../../etc",
                          extra="INJECTED-EXTRA")
        loop_session.save_session(d, s)
        body, raw = status(env, loop_id)
        assert set(body["brief"]) == {"artifact", "sha256", "bytes"}
        for needle in ("INJECTED-CONTENT", "../../etc", "INJECTED-EXTRA"):
            assert needle not in raw
        assert body["brief_check"] == "ok"

    @pytest.mark.parametrize("mutate", [
        lambda r: r.update(artifact="source-architect-brief.md"),  # swapped
        lambda r: r.update(artifact="../architect-brief.md"),
        lambda r: r.update(sha256="nothex"),
        lambda r: r.update(bytes="12"),
        lambda r: r.update(bytes=True),
    ])
    def test_malformed_or_swapped_ref(self, env, mutate):
        loop_id, d = started_with_brief(env)
        s = loop_session.load_session(d)
        mutate(s["brief"])
        loop_session.save_session(d, s)
        body, _ = status(env, loop_id)
        assert body["brief"] is None and body["brief_check"] == "invalid_ref"

    def test_integrity_states(self, env):
        loop_id, d = started_with_brief(env)
        f = d / "architect-brief.md"
        os.chmod(str(f), 0o666)
        f.write_text(BRIEF + "tampered", encoding="utf-8")
        body, _ = status(env, loop_id)
        assert body["brief_check"] == "mismatch" and body["brief"] is not None
        f.unlink()
        assert status(env, loop_id)[0]["brief_check"] == "missing"

    def test_generic_allowlist_has_no_brief(self):
        assert "brief" not in dashboard.DashboardHandler._LOOP_STATUS_ALLOWED_KEYS


# ---------------------------------------------------------------------------
# Coding source brief projection
# ---------------------------------------------------------------------------

def approved_planning_with_brief(env):
    loop_id, d = started_with_brief(env)
    s = loop_session.load_session(d)
    s["status"].update(stage="plan_approved", next_role=None)
    loop_session.save_session(d, s)
    (d / "plan.current.md").write_bytes(CHECKPOINTED_PLAN)
    with dashboard._LOOP_HOSTS_LOCK:
        dashboard._LOOP_HOSTS.clear()
    return loop_id, d


class TestCodingProjection:
    def test_kept_source_brief(self, env):
        src_id, _ = approved_planning_with_brief(env)
        cid, cd = loop_host.init_loop("code", None, repo_root=env["repo"],
                                      mode="coding", from_loop=src_id)
        body, raw = status(env, cid)
        c = body["coding"]
        assert c["source_brief"]["artifact"] == "source-architect-brief.md"
        assert c["source_brief_check"] == "ok"
        assert c["source_brief_decision"] == "kept"
        assert body["brief_check"] == "absent"
        assert "SECRET-CONTENT-MARKER" not in raw

    def test_source_brief_injection_and_swap(self, env):
        src_id, _ = approved_planning_with_brief(env)
        cid, cd = loop_host.init_loop("code", None, repo_root=env["repo"],
                                      mode="coding", from_loop=src_id)
        s = loop_session.load_session(cd)
        s["coding"]["source_brief"]["content"] = "INJECTED-SRC"
        loop_session.save_session(cd, s)
        body, raw = status(env, cid)
        assert "INJECTED-SRC" not in raw
        assert body["coding"]["source_brief_check"] == "ok"
        s["coding"]["source_brief"]["artifact"] = "architect-brief.md"  # swap
        loop_session.save_session(cd, s)
        body, _ = status(env, cid)
        assert body["coding"]["source_brief"] is None
        assert body["coding"]["source_brief_check"] == "invalid_ref"

    def test_dropped_decision(self, env):
        src_id, _ = approved_planning_with_brief(env)
        cid, _ = loop_host.init_loop("code", None, repo_root=env["repo"],
                                     mode="coding", from_loop=src_id,
                                     source_brief="drop")
        c = status(env, cid)[0]["coding"]
        assert c["source_brief_decision"] == "dropped"
        assert c["source_brief"] is None and c["source_brief_check"] == "absent"


# ---------------------------------------------------------------------------
# Artifacts and join prompt
# ---------------------------------------------------------------------------

class TestArtifactsAndPrompt:
    def test_brief_artifacts_served(self, env):
        src_id, _ = approved_planning_with_brief(env)
        code, text = req(env["base"] + f"/{src_id}/artifact/architect-brief.md")
        assert code == 200 and "SECRET-CONTENT-MARKER" in text
        cid, _ = loop_host.init_loop("code", None, repo_root=env["repo"],
                                     mode="coding", from_loop=src_id)
        code, text = req(env["base"] + f"/{cid}/artifact/source-architect-brief.md")
        assert code == 200 and "SECRET-CONTENT-MARKER" in text

    def test_prompt_pointer_only_with_brief(self, env):
        loop_id, _ = started_with_brief(env)
        code, text = req(env["base"] + f"/{loop_id}/prompt", "POST",
                         {"role": "draftor"})
        prompt = json.loads(text)["prompt"]
        assert "An Architect brief exists" in prompt
        assert "SECRET-CONTENT-MARKER" not in prompt
        end_and_free(env, loop_id)
        # A distinct feature: loop ids are feature + second-resolution
        # timestamp, so a same-feature restart in the same second collides.
        code, text = start(env, feature="feat-nobrief")
        nid = json.loads(text)["loop_id"]
        code, text = req(env["base"] + f"/{nid}/prompt", "POST",
                         {"role": "draftor"})
        assert "Architect brief" not in json.loads(text)["prompt"]

    def test_prompt_names_explicit_gator_init_start(self, env):
        """Gator-native entry point: the join prompt does not rely on native
        agent files; it names `gator init` and GATOR_INIT.md (pointer only)."""
        code, text = start(env, feature="feat-init-pointer")
        loop_id = json.loads(text)["loop_id"]
        code, text = req(env["base"] + f"/{loop_id}/prompt", "POST",
                         {"role": "reviewer"})
        prompt = json.loads(text)["prompt"]
        assert prompt.startswith("gator loop join\n")
        assert "Run `gator init` first" in prompt and "GATOR_INIT.md" in prompt
        assert prompt.index("gator loop status --token") < prompt.index("gator init")


# ---------------------------------------------------------------------------
# CLI status
# ---------------------------------------------------------------------------

def cli_status(repo, token, *extra):
    return subprocess.run([sys.executable, str(GATOR_LOOP), "status",
                           "--token", token, *extra], cwd=str(repo),
                          capture_output=True, text=True, timeout=60)


class TestCliStatus:
    def test_no_brief_prints_nothing(self, env):
        code, text = start(env)
        d = env["repo"] / ".gator" / "loops" / json.loads(text)["loop_id"]
        r = cli_status(env["repo"], _tokens(d)["draftor"])
        assert "Architect brief" not in r.stdout
        assert "Planning brief" not in r.stdout
        out = json.loads(cli_status(env["repo"], _tokens(d)["draftor"],
                                    "--json").stdout)
        assert "brief" not in out and "source_brief" not in out

    def test_brief_ok_and_mismatch_markers(self, env):
        loop_id, d = started_with_brief(env)
        tok = _tokens(d)
        r = cli_status(env["repo"], tok["draftor"])
        assert "Architect brief:" in r.stdout and "[OK] (required reading)" in r.stdout
        assert str(d / "architect-brief.md") in r.stdout
        f = d / "architect-brief.md"
        os.chmod(str(f), 0o666)
        f.write_text("changed", encoding="utf-8")
        r = cli_status(env["repo"], tok["reviewer"])
        assert "[!!] DIGEST MISMATCH" in r.stdout
        assert "Escalate to the Architect" in r.stdout
        r = cli_status(env["repo"], tok["architect"])
        assert "[!!] DIGEST MISMATCH" in r.stdout
        assert "Escalate" not in r.stdout
        out = json.loads(cli_status(env["repo"], tok["draftor"], "--json").stdout)
        assert out["brief"]["check"] == "mismatch"

    def test_coding_labels_and_dropped(self, env):
        src_id, _ = approved_planning_with_brief(env)
        cid, cd = loop_host.init_loop("code", None, repo_root=env["repo"],
                                      mode="coding", from_loop=src_id)
        r = cli_status(env["repo"], _tokens(cd)["draftor"])
        assert f"Architect brief (from approved plan {src_id})" in r.stdout
        end_and_free(env, cid)
        did, dd = loop_host.init_loop("code2", None, repo_root=env["repo"],
                                      mode="coding", from_loop=src_id,
                                      source_brief="drop")
        r = cli_status(env["repo"], _tokens(dd)["draftor"])
        assert "Planning brief: not carried forward" in r.stdout
        assert "from approved plan" not in r.stdout


# ---------------------------------------------------------------------------
# M2a — Dashboard coding-loop start
# ---------------------------------------------------------------------------

def coding_start(env, **body):
    payload = {"feature": "code", "mode": "coding"}
    payload.update(body)
    return req(env["base"] + "/start", "POST", payload)


def approved_planning(env, with_brief=True, feature="feat"):
    code, text = start(env, feature=feature,
                       **({"brief": BRIEF} if with_brief else {}))
    assert code == 201, text
    loop_id = json.loads(text)["loop_id"]
    d = env["repo"] / ".gator" / "loops" / loop_id
    s = loop_session.load_session(d)
    s["status"].update(stage="plan_approved", next_role=None)
    loop_session.save_session(d, s)
    (d / "plan.current.md").write_bytes(CHECKPOINTED_PLAN)
    with dashboard._LOOP_HOSTS_LOCK:
        dashboard._LOOP_HOSTS.clear()
    return loop_id, d


class TestCodingStart:
    def test_list_reports_mode(self, env):
        src_id, _ = approved_planning(env)
        code, text = req(env["base"])
        entry = [l for l in json.loads(text)["loops"] if l["loop_id"] == src_id][0]
        assert entry["mode"] == "planning" and entry["stage"] == "plan_approved"

    def test_keep_default_with_new_brief(self, env):
        src_id, _ = approved_planning(env)
        code, text = coding_start(env, from_loop=src_id, brief="Code brief.\n")
        assert code == 201, text
        cid = json.loads(text)["loop_id"]
        cd = env["repo"] / ".gator" / "loops" / cid
        s = loop_session.load_session(cd)
        assert s["mode"] == "coding"
        assert s["coding"]["source_brief_decision"] == "kept"
        assert (cd / "source-architect-brief.md").read_text(encoding="utf-8") == BRIEF
        assert (cd / "architect-brief.md").read_text(encoding="utf-8") == "Code brief.\n"
        body, _ = status(env, cid)
        assert body["brief_check"] == "ok"
        assert body["coding"]["source_brief_check"] == "ok"

    def test_drop_without_new_brief(self, env):
        src_id, _ = approved_planning(env)
        code, text = coding_start(env, from_loop=src_id, source_brief="drop")
        assert code == 201, text
        cd = env["repo"] / ".gator" / "loops" / json.loads(text)["loop_id"]
        s = loop_session.load_session(cd)
        assert s["coding"]["source_brief_decision"] == "dropped"
        assert not any(p.name.endswith("architect-brief.md") for p in cd.iterdir())

    def test_source_without_brief_none_available(self, env):
        src_id, _ = approved_planning(env, with_brief=False)
        code, text = coding_start(env, from_loop=src_id)
        assert code == 201, text
        cd = env["repo"] / ".gator" / "loops" / json.loads(text)["loop_id"]
        assert loop_session.load_session(cd)["coding"][
            "source_brief_decision"] == "none_available"

    @pytest.mark.parametrize("case", [
        "not_approved", "coding_source", "missing", "trailing_dot",
        "sketch_and_coding", "no_from_loop", "bad_mode", "nonstring_from",
        "bad_source_brief", "planning_with_from", "planning_with_source_brief",
    ])
    def test_rejections_400_no_partial(self, env, case):
        src_id, src_dir = approved_planning(env)
        body = {"feature": "code", "mode": "coding", "from_loop": src_id}
        if case == "not_approved":
            s = loop_session.load_session(src_dir)
            s["status"].update(stage="plan_review", next_role="reviewer")
            loop_session.save_session(src_dir, s)
        elif case == "coding_source":
            cid, _ = loop_host.init_loop("c0", None, repo_root=env["repo"],
                                         mode="coding", from_loop=src_id)
            end_and_free(env, cid)
            body["from_loop"] = cid
        elif case == "missing":
            body["from_loop"] = "no-such-loop"
        elif case == "trailing_dot":
            body["from_loop"] = src_id + "."
        elif case == "sketch_and_coding":
            body["sketch_path"] = "sketch.md"
        elif case == "no_from_loop":
            del body["from_loop"]
        elif case == "bad_mode":
            body["mode"] = "review"
        elif case == "nonstring_from":
            body["from_loop"] = 123
        elif case == "bad_source_brief":
            body["source_brief"] = "maybe"
        elif case == "planning_with_from":
            body = {"feature": "p2", "sketch_path": "sketch.md",
                    "from_loop": src_id}
        elif case == "planning_with_source_brief":
            body = {"feature": "p3", "sketch_path": "sketch.md",
                    "source_brief": "keep"}
        before = loops(env["repo"])
        if case == "not_approved":
            # A plan_review source is active: the single-active guard (409)
            # or the successor validation (400) refuses it — never 201.
            code, text = req(env["base"] + "/start", "POST", body)
            assert code in (400, 409), text
        else:
            code, text = req(env["base"] + "/start", "POST", body)
            assert code == 400, text
        assert loops(env["repo"]) == before

    def test_active_loop_409(self, env):
        src_id, _ = approved_planning(env)
        code, text = start(env, feature="busy")  # an active planning loop
        assert code == 201
        before = loops(env["repo"])
        code, text = coding_start(env, from_loop=src_id)
        assert code == 409
        assert loops(env["repo"]) == before

    @pytest.mark.parametrize("corrupt", ["mismatch", "missing", "invalid_ref"])
    def test_corrupt_source_keep_400_drop_201(self, env, corrupt):
        src_id, src_dir = approved_planning(env)
        f = src_dir / "architect-brief.md"
        if corrupt == "mismatch":
            os.chmod(str(f), 0o666)
            f.write_text("tampered", encoding="utf-8")
        elif corrupt == "missing":
            os.chmod(str(f), 0o666)
            f.unlink()
        else:
            s = loop_session.load_session(src_dir)
            s["brief"]["artifact"] = "source-architect-brief.md"
            loop_session.save_session(src_dir, s)
        before = loops(env["repo"])
        code, text = coding_start(env, from_loop=src_id)  # default keep
        assert code == 400
        assert corrupt in text and "--source-brief drop" in text
        assert loops(env["repo"]) == before
        code, text = coding_start(env, from_loop=src_id, source_brief="drop")
        assert code == 201, text
        cd = env["repo"] / ".gator" / "loops" / json.loads(text)["loop_id"]
        assert not (cd / "source-architect-brief.md").exists()
        body, _ = status(env, json.loads(text)["loop_id"])
        assert body["coding"]["source_brief"] is None
        assert body["coding"]["source_brief_decision"] == "dropped"
