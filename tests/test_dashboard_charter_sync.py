"""Charter sync routes: `GET` / `POST /api/repo/<name>/charter-sync`.

A real DashboardHandler over a throwaway Git repository; the verifier is
stubbed so the tests prove routing and admission, not verifier heuristics
(`tests/test_charter_sync.py` owns the engine). Each test proves one risk:
the POST keeps every Dashboard mutation guard; a successful run is what the
GET serves and the Tier-2 route never shadows it; and the run shares the
heavy-work admission budget.
"""

import json
import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pytest

from conftest import load_script

import gator_core

dashboard = load_script("gator-dashboard")
charter_sync = sys.modules["dashboard.charter_sync"]

TIMEOUT = 30


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "target"
    (r / ".gator" / "charters").mkdir(parents=True)
    (r / ".gator" / "charters" / "mod.md").write_text(
        "# Charter: mod\n\n**Covers**: `src/*.py`\n", encoding="utf-8")
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "test@example.com")
    _git(r, "config", "user.name", "test")
    _git(r, "config", "commit.gpgsign", "false")
    _git(r, "config", "core.hooksPath", str(tmp_path / "no-hooks"))
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "init")
    return r


@pytest.fixture
def verifier(monkeypatch):
    calls = []

    def fake(script, *args, timeout=None):
        calls.append(args)
        return {"version": "x", "finding_count": 0, "summary": {}, "findings": [],
                "charters": [{"name": "mod", "path": ".gator/charters/mod.md",
                              "covers": ["src/*.py"]}]}
    monkeypatch.setattr(charter_sync, "run_json", fake)
    return calls


@pytest.fixture
def serve(tmp_path, monkeypatch):
    registry_file = tmp_path / "home" / "dashboard-repos.json"
    monkeypatch.setattr(gator_core, "DASHBOARD_REGISTRY", registry_file)
    saved_fleet = dashboard.DashboardHandler.fast_data
    servers = []

    def start(records):
        registry_file.parent.mkdir(parents=True, exist_ok=True)
        registry_file.write_text(json.dumps({
            "schema": "gator-dashboard-registry-v1", "repos": records}), encoding="utf-8")
        monkeypatch.setattr(dashboard, "_REGISTRY_REPOS", list(records))
        dashboard.DashboardHandler.fast_data = {
            "generated_at": "seed",
            "repos": [{"name": r["name"], "path": r["path"]} for r in records]}
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), dashboard.DashboardHandler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        servers.append(httpd)
        return f"http://127.0.0.1:{httpd.server_address[1]}"

    yield start
    for httpd in servers:
        httpd.shutdown()
        httpd.server_close()
    dashboard.DashboardHandler.fast_data = saved_fleet


def _call(url, path, post=False, auth=True):
    req = Request(url + path, data=b"{}" if post else None, method="POST" if post else "GET")
    if post:
        req.add_header("Content-Type", "application/json")
        if auth:
            req.add_header("X-Gator-Dashboard", "1")
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, json.loads(resp.read()), resp.headers
    except HTTPError as e:
        body = e.read() or b"{}"
        try:
            return e.code, json.loads(body), e.headers
        except ValueError:   # a pre-dispatch parse error may be plain text
            return e.code, {"text": body.decode("utf-8", "replace")}, e.headers


def _artifacts(repo):
    d = repo / ".gator" / "artifacts"
    return sorted(p.name for p in d.iterdir()) if d.is_dir() else []


@pytest.mark.parametrize("case, expected", [
    ("no-header", 403), ("unknown-repo", 404), ("repo-busy", 409),
])
def test_post_keeps_the_mutation_guards(serve, repo, verifier, case, expected):
    url = serve([{"name": "target", "path": str(repo)}])
    if case == "no-header":
        status = _call(url, "/api/repo/target/charter-sync", post=True, auth=False)[0]
    elif case == "unknown-repo":
        status = _call(url, "/api/repo/missing/charter-sync", post=True)[0]
    else:
        with dashboard._repo_action(str(repo)) as owned:
            assert owned
            status, data, _ = _call(url, "/api/repo/target/charter-sync", post=True)
        assert "another change is running" in data["error"]
    assert status == expected
    assert verifier == [] and _artifacts(repo) == []


def test_run_is_served_by_get_and_never_shadowed(serve, repo, verifier):
    url = serve([{"name": "target", "path": str(repo)}])
    status, data, headers = _call(url, "/api/repo/target/charter-sync")
    assert (status, data) == (200, {"state": "none"})   # not the Tier-2 repo status
    assert headers["Cache-Control"] == "no-store"

    status, ran, headers = _call(url, "/api/repo/target/charter-sync", post=True)
    assert status == 200 and ran["state"] == "current" and ran.pop("persisted") is True
    assert headers["Cache-Control"] == "no-store"
    assert (repo / ran["artifact_path"]).is_file()

    status, last, _ = _call(url, "/api/repo/target/charter-sync")
    assert (status, last) == (200, ran)
    assert _call(url, "/api/repo/missing/charter-sync")[0] == 400


@pytest.mark.parametrize("name", ["my repo", "répo-ünï 文档"])
def test_encoded_repository_names_resolve_once(serve, repo, verifier, name):
    url = serve([{"name": name, "path": str(repo)}])
    route = f"/api/repo/{quote(name, safe='')}/charter-sync"
    status, ran, _ = _call(url, route, post=True)
    assert status == 200 and ran.pop("persisted") is True
    assert _call(url, route)[:2] == (200, ran)


@pytest.mark.parametrize("raw_name", ["50%25off", "a%2Fb", "%25%32%30"])
def test_unsafe_encodings_are_refused_by_both_methods(serve, repo, verifier, raw_name):
    """The parse-once boundary: a decoded `%` (literal percent or double
    encoding) and an encoded separator are 400 for GET and POST alike."""
    url = serve([{"name": "50%off", "path": str(repo)}])
    route = f"/api/repo/{raw_name}/charter-sync"
    assert _call(url, route)[0] == 400
    assert _call(url, route, post=True)[0] == 400
    assert verifier == [] and _artifacts(repo) == []


def test_post_waits_for_a_shared_heavy_slot(serve, repo, verifier, monkeypatch):
    slots = threading.BoundedSemaphore(1)
    monkeypatch.setattr(dashboard, "_HEAVY_SLOTS", slots)
    monkeypatch.setattr(dashboard, "_HEAVY_TIMEOUT", 0.3)
    url = serve([{"name": "target", "path": str(repo)}])
    assert slots.acquire(timeout=1)        # another heavy route holds the only slot
    try:
        status, data, _ = _call(url, "/api/repo/target/charter-sync", post=True)
    finally:
        slots.release()
    assert (status, data) == (503, {"error": "dashboard busy; retry"})
    assert verifier == [] and _artifacts(repo) == []
    assert _call(url, "/api/repo/target/charter-sync", post=True)[0] == 200
