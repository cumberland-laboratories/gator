"""
Tests for the Dashboard's machine-integration routes (CP3):
GET /api/integration and POST /api/integration/dismiss-codex-reminder.

A real DashboardHandler on an ephemeral port; `_INTEGRATION_HOME` /
`_INTEGRATION_ENV` point at a temporary home, so the real machine is
never read or written.
"""

import json
import threading
from http.server import HTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from conftest import load_script

import machine_integration as mi  # the same module object the Dashboard imports

dashboard = load_script("gator-dashboard")


@pytest.fixture
def home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    monkeypatch.setattr(dashboard, "_INTEGRATION_HOME", home)
    monkeypatch.setattr(dashboard, "_INTEGRATION_ENV", {})
    return home


@pytest.fixture
def url():
    httpd = HTTPServer(("127.0.0.1", 0), dashboard.DashboardHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    thread.join(timeout=5)


def _get(url, path):
    with urlopen(url + path, timeout=5) as resp:
        return resp.status, json.loads(resp.read())


def _post(url, path, auth=True):
    req = Request(url + path, data=b"", method="POST")
    if auth:
        req.add_header("X-Gator-Dashboard", "1")
    try:
        with urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except HTTPError as e:
        return e.code, json.loads(e.read())


def test_status_reports_this_machine(home, url):
    status, body = _get(url, "/api/integration")
    assert status == 200 and body["state"] == "missing"
    assert body["vendors"]["codex"]["present"] is True
    assert body["vendors"]["codex"]["connected"] is False
    assert body["vendors"]["claude"]["present"] is False

    mi.ensure(home=home, env={})
    _, body = _get(url, "/api/integration")
    assert body["vendors"]["codex"]["connected"] is True
    assert body["codex_reminder_due"] is True


def test_status_never_connects_tools(home, url):
    _get(url, "/api/integration")
    assert not (home / ".codex" / "hooks.json").exists()
    assert not (home / ".gator").exists()


def test_dismiss_flips_the_reminder(home, url):
    mi.ensure(home=home, env={})
    status, body = _post(url, "/api/integration/dismiss-codex-reminder")
    assert status == 200
    assert body["codex_reminder_due"] is False
    _, again = _get(url, "/api/integration")
    assert again["codex_reminder_due"] is False


def test_dismiss_without_state_is_409(home, url):
    status, body = _post(url, "/api/integration/dismiss-codex-reminder")
    assert status == 409
    assert body["status"]["state"] == "missing"
    assert not (home / ".gator").exists()


def test_dismiss_requires_dashboard_header(home, url):
    mi.ensure(home=home, env={})
    status, _ = _post(url, "/api/integration/dismiss-codex-reminder", auth=False)
    assert status == 403
    assert mi.status(home=home, env={})["codex_reminder_due"] is True


def test_status_error_still_answers(home, url, monkeypatch):
    def boom(**kw):
        raise RuntimeError("state exploded")
    monkeypatch.setattr(mi, "status", boom)
    status, body = _get(url, "/api/integration")
    assert status == 200
    assert body["state"] == "error" and "state exploded" in body["detail"]
