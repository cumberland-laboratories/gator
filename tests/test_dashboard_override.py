"""
#76 — the Dashboard blocked-commit override relay.

The Dashboard relays the repository's own `gator hook override ... --json`
(through the governed dispatcher) and serves only an allowlisted
projection. Unit tests drive `dashboard.data` with a fake runner; the
HTTP tests run a real DashboardHandler; the end-to-end tests use a
throwaway governed repository whose real hooks block a commit, then
approve or discard it through the routes. Approval runs only inside those
temp repos, never against this repository.
"""

import json
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from conftest import load_script

import gator_core

dashboard = load_script("gator-dashboard")
dashboard_data = sys.modules["dashboard.data"]

# Real-repo helpers from the pre-commit override suite (functions only, so
# no test classes are re-collected here).
from test_precommit_override import (  # noqa: E402
    SCRIPTS, _backdate_block, _commit, _last_message, _make_repo, _stage_code)

TIMEOUT = 30
REV = "0123456789abcdef"
BLOCK = "a1b2c3d4"


def _status_obj(**over):
    obj = {
        "schema": "gator-override-status-v1", "state": "blocked", "revision": REV,
        "malformed": [], "block": {
            "block_id": BLOCK, "created_at": "t", "created_epoch": 1.0,
            "expires_at": "t", "expires_epoch": 2.0, "age_seconds": 30,
            "tree_matches": True, "files": ["foo.py"]},
        "findings": [{"rule": "charter-alongside-code", "resolution": "external-approval",
                      "message": "m", "covered": False}],
        "approval": {"state": "absent", "detail": "no approval recorded"},
        "approvable_rules": ["charter-alongside-code"], "covered_rules": [],
        "uncovered_external_rules": ["charter-alongside-code"], "can_approve": True,
        "approve_refusal": None, "approve_wait_seconds": 0,
        "min_approval_delay_seconds": 10, "architect_default": "Test",
    }
    obj.update(over)
    return obj


class FakeRunner:
    def __init__(self, stdout="", stderr="", code=0):
        self.calls = []
        self.result = (stdout, stderr, code)

    def __call__(self, repo_path, *args):
        self.calls.append(list(args))
        return self.result


# ── shaping (fake runner) ─────────────────────────────────────────────────────

def test_status_shaping_drops_unknown_fields_and_caps_text():
    obj = _status_obj(secret="raw", findings=[
        {"rule": "charter-alongside-code", "resolution": "external-approval",
         "message": "x" * 5000, "covered": False, "match": "source text"},
        {"rule": "bogus", "resolution": "approvable", "message": "legacy value"},
    ])
    obj["block"]["index_tree"] = "deadbeef"
    obj["block"]["files"] = [f"f{i}.py" for i in range(600)]
    obj["approval"]["reason"] = "private reason"
    data = dashboard_data.shape_override_status(json.dumps(obj), "", 0)
    assert "secret" not in data and "index_tree" not in data["block"]
    assert "reason" not in data["approval"]
    assert [f["rule"] for f in data["findings"]] == ["charter-alongside-code"]
    assert "match" not in data["findings"][0]
    assert data["findings"][0]["message"].startswith("x" * 2000)
    assert len(data["block"]["files"]) == 500 and data["block"]["files_total"] == 600
    assert data["state"] == "incomplete", "the unrepresentable finding was dropped"
    assert data["revision"] == REV and data["can_approve"] is False


def _many_findings(n):
    return [{"rule": f"SQL-001@m{i}.sql:1", "resolution": "external-approval",
             "message": "m", "covered": False} for i in range(n)]


@pytest.mark.parametrize("findings, incomplete", [
    (_many_findings(200), False),
    (_many_findings(201), True),
    ([{"rule": "x", "resolution": "approvable", "message": "m"}], True),
])
def test_findings_over_the_limit_are_never_approvable(findings, incomplete):
    """Round 1 review: a block whose findings cannot all be shown is
    read-only (terminal guidance), never silently cut while approvable."""
    obj = _status_obj(findings=findings,
                      uncovered_external_rules=[f["rule"] for f in findings])
    data = dashboard_data.shape_override_status(json.dumps(obj), "", 0)
    if not incomplete:
        assert data["state"] == "blocked" and data["can_approve"] is True
        assert len(data["findings"]) == 200
        return
    assert data["state"] == "incomplete"
    assert data["can_approve"] is False and data["uncovered_external_rules"] == []
    assert data["approve_refusal"] == "too-many-findings"
    assert data["findings_total"] == len(findings)
    assert "gator hook override" in data["message"]
    assert data["revision"] == REV, "Discard stays available"


def test_direct_approve_post_refuses_incomplete_findings():
    status = json.dumps(_status_obj(findings=_many_findings(201)))
    runner = FakeRunner(status)
    result = dashboard_data.resolve_repo_override("approve", "/repo", GOOD, run_fn=runner)
    assert result["status"] == 409 and result["data"]["refusal"] == "too-many-findings"
    assert runner.calls == [["status", "--json"]], "the approve command never ran"


def test_long_message_is_cut_visibly():
    obj = _status_obj()
    obj["findings"][0]["message"] = "x" * 5000
    data = dashboard_data.shape_override_status(json.dumps(obj), "", 0)
    assert data["findings"][0]["message"].endswith("see `gator hook override status`)")


@pytest.mark.parametrize("stdout, code, state", [
    ("", 2, "unsupported"),                      # older runtime: argparse exit 2
    ("  gator override status\n", 0, "unsupported"),  # human text
    (json.dumps({"schema": "other-v1", "state": "none"}), 0, "unsupported"),
    ("", 0, "ungoverned"),                       # dispatcher skip
])
def test_unusable_cli_output_degrades(stdout, code, state):
    data = dashboard_data.shape_override_status(stdout, "usage: ...", code)
    assert data["state"] == state
    if state == "unsupported":
        assert "gator update" in data["message"]
        assert data["command"] == "gator hook override status"


GOOD = {"block_id": BLOCK, "revision": REV, "name": "Architect", "reason": "ok"}


@pytest.mark.parametrize("body", [
    "not an object",
    dict(GOOD, name=""), dict(GOOD, name="   "), dict(GOOD, name="x" * 81),
    dict(GOOD, reason=" \r\n\t "), dict(GOOD, reason=""), dict(GOOD, reason="r" * 501),
    dict(GOOD, reason="a\x07b"), dict(GOOD, reason="a\x1b[31mb"),
    dict(GOOD, block_id="xyz"), dict(GOOD, block_id=None),
    dict(GOOD, revision="short"), {k: v for k, v in GOOD.items() if k != "revision"},
])
def test_approve_rejects_invalid_body(body):
    runner = FakeRunner()
    result = dashboard_data.resolve_repo_override("approve", "/repo", body, run_fn=runner)
    assert result["status"] == 400 and "error" in result["data"]
    assert runner.calls == [], "validation runs before any subprocess"


def test_approve_folds_pasted_line_breaks_into_one_line():
    """A reason pasted from a terminal (CRLF, LF, tabs) is accepted and sent
    as one line, as the trailer would make it anyway; 500 characters fit."""
    args, error = dashboard_data.override_cli_args("approve", dict(
        GOOD, name="Dash\nArchitect", reason="  first line\r\n\tsecond  line\n"))
    assert error is None
    assert args[-4:] == ["--name", "Dash Architect", "--reason", "first line second line"]
    args, error = dashboard_data.override_cli_args("approve", dict(GOOD, reason="r" * 500))
    assert error is None and args[-1] == "r" * 500


def test_cancel_body_validation_and_argv():
    ok = json.dumps({"schema": "gator-override-cancel-v1", "ok": True,
                     "message": "m", "removed": ["block.json"]})
    runner = FakeRunner(ok)
    result = dashboard_data.resolve_repo_override(
        "cancel", "/repo", {"block_id": None, "revision": REV}, run_fn=runner)
    assert result["status"] == 200 and result["data"]["removed"] == ["block.json"]
    assert runner.calls[-1] == ["cancel", "--json", "--expect-revision", REV]
    dashboard_data.resolve_repo_override(
        "cancel", "/repo", {"block_id": BLOCK, "revision": REV}, run_fn=runner)
    assert runner.calls[-1] == ["cancel", "--json", "--expect-block", BLOCK,
                                "--expect-revision", REV]
    bad = dashboard_data.resolve_repo_override(
        "cancel", "/repo", {"block_id": None}, run_fn=runner)
    assert bad["status"] == 400 and len(runner.calls) == 2


@pytest.mark.parametrize("refusal", ["tree-changed", "expired", "findings-changed"])
def test_cli_refusal_is_relayed_as_409(refusal):
    out = json.dumps({"schema": "gator-override-approve-v1", "ok": False,
                      "refusal": refusal, "message": "Refused.",
                      "retry_after_seconds": None, "approval": None,
                      "remaining": {"fix_required": [], "paused": ["dangerous-pattern-pause"]}})
    runner = FakeRunner(out, "", 1)
    result = dashboard_data.resolve_repo_override("approve", "/repo", GOOD, run_fn=runner)
    assert result["status"] == 409
    assert result["data"]["refusal"] == refusal and result["data"]["ok"] is False
    assert result["data"]["remaining"]["paused"] == ["dangerous-pattern-pause"]
    assert runner.calls[0] == ["status", "--json"], "the incomplete-findings pre-check"
    argv = runner.calls[-1]
    assert argv[:2] == ["approve", "--json"]
    assert argv[argv.index("--expect-block") + 1] == BLOCK
    assert argv[argv.index("--expect-revision") + 1] == REV


def test_unsupported_runtime_on_approve_is_409_with_command():
    result = dashboard_data.resolve_repo_override(
        "approve", "/repo", GOOD, run_fn=FakeRunner("", "usage: ...", 2))
    assert result["status"] == 409
    assert result["data"]["refusal"] == "unsupported-runtime"
    assert result["data"]["command"] == "gator hook override approve"


# ── HTTP ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def serve(monkeypatch, tmp_path):
    """Serve a real DashboardHandler over a seeded registry."""
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


def _call(url, path, body=None, auth=True):
    if body is None:
        req = Request(url + path)
    else:
        req = Request(url + path, data=json.dumps(body).encode("utf-8"), method="POST")
        req.add_header("Content-Type", "application/json")
        if auth:
            req.add_header("X-Gator-Dashboard", "1")
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, json.loads(resp.read()), resp.headers
    except HTTPError as e:
        return e.code, json.loads(e.read() or b"{}"), e.headers


@pytest.mark.parametrize("action", ["approve", "cancel"])
def test_override_posts_require_dashboard_header(serve, tmp_path, monkeypatch, action):
    runner = FakeRunner()
    monkeypatch.setattr(dashboard_data, "run_override_cli", runner)
    url = serve([{"name": "target", "path": str(tmp_path)}])
    status, _, _ = _call(url, f"/api/repo/target/override/{action}", GOOD, auth=False)
    assert status == 403 and runner.calls == []


def test_override_post_is_excluded_while_repo_busy(serve, tmp_path, monkeypatch):
    runner = FakeRunner()
    monkeypatch.setattr(dashboard_data, "run_override_cli", runner)
    path = str(tmp_path)
    url = serve([{"name": "target", "path": path}])
    with dashboard._repo_action(path) as owned:
        assert owned
        status, data, _ = _call(url, "/api/repo/target/override/approve", GOOD)
    assert status == 409 and "another change is running" in data["error"]
    assert runner.calls == []


def test_override_routes_unknown_repo(serve, tmp_path):
    url = serve([{"name": "target", "path": str(tmp_path)}])
    assert _call(url, "/api/repo/missing/override")[0] == 400
    assert _call(url, "/api/repo/missing/override/cancel",
                 {"block_id": None, "revision": REV})[0] == 404


# ── end to end: real repository, real dispatcher, real hooks ─────────────────

@pytest.fixture
def governed(tmp_path):
    """A throwaway governed repo pinned to this CLI, so the dispatcher runs
    the source template runtime (the checkpoint under test)."""
    repo = _make_repo(tmp_path, SCRIPTS)
    (repo / ".gator" / "runtime-pin.json").write_text(json.dumps({
        "schema": "gator-runtime-pin-v1",
        "runtime_version": gator_core.get_version()}), encoding="utf-8")
    return repo


def test_dashboard_approval_end_to_end(serve, governed):
    _stage_code(governed)
    assert _commit(governed)[0] != 0
    url = serve([{"name": "target", "path": str(governed)}])

    status, data, headers = _call(url, "/api/repo/target/override")
    assert status == 200 and data["state"] == "blocked", data
    assert data["architect_default"] == "Test"
    assert "no-store" in headers.get("Cache-Control", "")
    body = {"block_id": data["block"]["block_id"], "revision": data["revision"],
            "name": "Dash Architect", "reason": "no charter edit needed"}

    status, refused, _ = _call(url, "/api/repo/target/override/approve", body)
    assert status == 409 and refused["refusal"] == "too-recent", refused

    _backdate_block(governed)
    status, refused, _ = _call(url, "/api/repo/target/override/approve",
                               dict(body, block_id="deadbeef"))
    assert status == 409 and refused["refusal"] == "block-changed"
    status, refused, _ = _call(url, "/api/repo/target/override/approve",
                               dict(body, revision="f" * 16))
    assert status == 409 and refused["refusal"] == "findings-changed"

    status, ok, _ = _call(url, "/api/repo/target/override/approve", body)
    assert status == 200 and ok["ok"] is True, ok
    assert ok["approval"]["approved_rules"] == ["charter-alongside-code"]

    rc, out = _commit(governed)
    assert rc == 0, out
    msg = _last_message(governed)
    assert "Gator-Override-Approved-By: Dash Architect" in msg
    assert "Gator-Override-Reason: no charter edit needed" in msg
    assert "Gator-Override-Rules: charter-alongside-code" in msg
    assert _call(url, "/api/repo/target/override")[1]["state"] == "none"


@pytest.mark.parametrize("case", ["readable", "malformed"])
def test_dashboard_cancel_end_to_end(serve, governed, case):
    if case == "readable":
        _stage_code(governed)
        assert _commit(governed)[0] != 0
    else:
        sdir = dashboard_data_state_dir(governed)
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "block.json").write_text("{not json", encoding="utf-8")
    url = serve([{"name": "target", "path": str(governed)}])
    status, data, _ = _call(url, "/api/repo/target/override")
    assert status == 200
    assert data["state"] == ("blocked" if case == "readable" else "malformed")
    block_id = data["block"]["block_id"] if data["block"] else None
    status, ok, _ = _call(url, "/api/repo/target/override/cancel",
                          {"block_id": block_id, "revision": data["revision"]})
    assert status == 200 and ok["ok"] is True, ok
    assert _call(url, "/api/repo/target/override")[1]["state"] == "none"


def dashboard_data_state_dir(repo):
    """The temp repo's override state dir (test-side only; the Dashboard
    itself never computes or reads it)."""
    import precommit_override as ovr
    return ovr.state_dir(repo)
