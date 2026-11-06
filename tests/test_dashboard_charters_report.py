"""Charter report relay: `GET` / `POST /api/repo/<name>/charters-report`.

A real DashboardHandler over a throwaway Git repository. The producer is
replaced by an in-process `charter_report.build_report()` call (or a broken
output), so the tests prove the relay, not the report's arithmetic
(`tests/test_charter_report.py` owns that). Each test proves one risk: GET
serves the record with an honest freshness; POST records only a sanitized v1
report and never damages the previous record; POST keeps every Dashboard
mutation guard and both methods share the heavy-work budget; and the
repository name is decoded exactly once, as for charter-sync.
"""

import json
import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pytest

from conftest import load_script

import charter_report
import gator_core

dashboard = load_script("gator-dashboard")
relay = sys.modules["dashboard.charters_report"]

TIMEOUT = 30
ROUTE = "/api/repo/target/charters-report"


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                          text=True).stdout


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "target"
    (r / ".gator" / "charters").mkdir(parents=True)
    (r / ".gator" / "charters" / "mod.md").write_text(
        "# Charter: mod\n\n**Covers**: `src/*.py`\n", encoding="utf-8")
    (r / "src").mkdir()
    (r / "src" / "a.py").write_text("A = 1\n", encoding="utf-8")
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "test@example.com")
    _git(r, "config", "user.name", "test")
    _git(r, "config", "commit.gpgsign", "false")
    _git(r, "config", "core.hooksPath", str(tmp_path / "no-hooks"))
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "init")
    return r


@pytest.fixture
def producer(monkeypatch):
    """`relay.run_json` stand-in. `.output` overrides the real report when set."""
    class Producer:
        calls = []
        output = None

    def fake(script, *args, timeout=None):
        Producer.calls.append(args)
        if Producer.output is not None:
            return Producer.output(Path(args[-1])) if callable(Producer.output) else Producer.output
        return charter_report.build_report(args[-1])
    monkeypatch.setattr(relay, "run_json", fake)
    return Producer


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
        except ValueError:
            return e.code, {"text": body.decode("utf-8", "replace")}, e.headers


def _record(repo):
    path = Path(_git(repo, "rev-parse", "--git-path", relay.RECORD_NAME).strip())
    return path if path.is_absolute() else repo / path


def test_get_serves_the_record_with_its_freshness(serve, repo, producer, tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    url = serve([{"name": "target", "path": str(repo)}, {"name": "plain", "path": str(plain)}])
    status, data, headers = _call(url, ROUTE)
    assert (status, data) == (200, {"state": "none"})          # never the Tier-2 repo status
    assert headers["Cache-Control"] == "no-store"
    status, ran, _ = _call(url, ROUTE, post=True)
    assert status == 200 and ran["freshness"] == "current" and ran.pop("persisted") is True
    assert _call(url, ROUTE)[:2] == (200, ran)

    (repo / "src" / "a.py").write_text("A = 2\nB = 3\n", encoding="utf-8")   # inputs changed
    status, data, _ = _call(url, ROUTE)
    assert (data["state"], data["freshness"]) == ("report", "stale")
    assert data["report"] == ran["report"]                     # the cached figures stay readable
    assert _call(url, "/api/repo/plain/charters-report")[1]["state"] == "unavailable"


def _with_extra_keys(path):
    r = charter_report.build_report(path)
    r["future_field"] = {"x": 1}
    r["code"]["future_metric"] = 7
    return r


def test_record_keeps_only_allowlisted_fields(serve, repo, producer):
    producer.output = _with_extra_keys
    url = serve([{"name": "target", "path": str(repo)}])
    status, ran, _ = _call(url, ROUTE, post=True)
    assert status == 200
    saved = json.loads(_record(repo).read_text(encoding="utf-8"))
    assert "future_field" not in saved and "future_metric" not in saved["code"]
    assert saved == ran["report"]


def test_a_record_from_before_module_paths_still_loads(repo):
    """`modules[].paths` is additive in v1: an older record sanitizes without it."""
    r = charter_report.build_report(repo)
    for m in r["code"]["modules"]:
        del m["paths"], m["paths_truncated"]
    clean = relay.sanitize(r)
    assert clean is not None
    assert all(m["paths"] == [] and m["paths_truncated"] is False for m in clean["code"]["modules"])


def _bad_path(path):
    r = charter_report.build_report(path)
    r["coverage"]["uncovered"] = ["../outside.py"]
    return r


def _wrong_schema(path):
    r = charter_report.build_report(path)
    r["schema"] = "gator-charters-report-v2"
    return r


@pytest.mark.parametrize("output, needle", [
    (_bad_path, "did not validate"),
    (_wrong_schema, "did not validate"),
    ({"error": "gator-charters timed out after 60s"}, "timed out"),
    ({"schema": "gator-charters-report-v1", "status": "failed", "error": "boom"}, "boom"),
    ("not a report", "no result"),
])
def test_a_bad_refresh_never_touches_the_record(serve, repo, producer, output, needle):
    url = serve([{"name": "target", "path": str(repo)}])
    assert _call(url, ROUTE, post=True)[0] == 200
    before = _record(repo).read_bytes()
    producer.output = output
    status, data, _ = _call(url, ROUTE, post=True)
    assert (status, data["state"]) == (500, "failed") and needle in data["error"]
    assert _record(repo).read_bytes() == before


@pytest.mark.parametrize("case, expected", [
    ("no-header", 403), ("unknown-repo", 404), ("repo-busy", 409), ("heavy-busy", 503),
])
def test_post_keeps_the_mutation_guards(serve, repo, producer, monkeypatch, case, expected):
    url = serve([{"name": "target", "path": str(repo)}])
    if case == "no-header":
        status = _call(url, ROUTE, post=True, auth=False)[0]
    elif case == "unknown-repo":
        status = _call(url, "/api/repo/missing/charters-report", post=True)[0]
    elif case == "repo-busy":
        with dashboard._repo_action(str(repo)) as owned:
            assert owned
            status, data, _ = _call(url, ROUTE, post=True)
        assert "another change is running" in data["error"]
    else:
        slots = threading.BoundedSemaphore(1)
        monkeypatch.setattr(dashboard, "_HEAVY_SLOTS", slots)
        monkeypatch.setattr(dashboard, "_HEAVY_TIMEOUT", 0.3)
        assert slots.acquire(timeout=1)
        try:
            status, data, _ = _call(url, ROUTE, post=True)
            assert _call(url, ROUTE)[:2] == (503, {"error": "dashboard busy; retry"})
        finally:
            slots.release()
    assert status == expected
    assert producer.calls == [] and not _record(repo).exists()


@pytest.mark.parametrize("name", ["my repo", "répo-ünï 文档"])
def test_encoded_repository_names_resolve_once(serve, repo, producer, name):
    url = serve([{"name": name, "path": str(repo)}])
    route = f"/api/repo/{quote(name, safe='')}/charters-report"
    status, ran, _ = _call(url, route, post=True)
    assert status == 200 and ran.pop("persisted") is True
    assert _call(url, route)[:2] == (200, ran)


@pytest.mark.parametrize("raw_name", ["50%25off", "a%2Fb", "%25%32%30"])
def test_unsafe_encodings_are_refused_by_both_methods(serve, repo, producer, raw_name):
    url = serve([{"name": "50%off", "path": str(repo)}])
    route = f"/api/repo/{raw_name}/charters-report"
    assert _call(url, route)[0] == 400
    assert _call(url, route, post=True)[0] == 400
    assert producer.calls == [] and not _record(repo).exists()
