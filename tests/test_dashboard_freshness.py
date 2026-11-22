"""
Dashboard freshness (#107, #108, #20): numbered Fleet collections, the
`/api/state` probe, and the page build stamp.

Real routes on an ephemeral threaded server. Isolation: monkeypatch
gator_core.DASHBOARD_REGISTRY, the module-level registry / collection
state, DashboardHandler.fast_data and collect_standalone_data.
"""

import json
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

from conftest import load_script

import gator_core

dashboard = load_script("gator-dashboard")
TIMEOUT = 20


def _get(url, path):
    resp = urlopen(Request(url + path), timeout=TIMEOUT)
    body = resp.read().decode("utf-8")
    return resp.status, body


def _json(url, path):
    return json.loads(_get(url, path)[1])


def _wait_until(predicate, what):
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting for {what}")


def _idle():
    return not dashboard.DashboardHandler._refresh_lock.locked()


def _fleet(registry, ts="new"):
    return {"generated_at": ts,
            "repos": [{"name": r["name"], "path": r["path"]} for r in registry]}


@pytest.fixture
def server(monkeypatch, tmp_path):
    registry_file = tmp_path / "home" / ".gator" / "dashboard-repos.json"
    registry_file.parent.mkdir(parents=True)
    registry_file.write_text(json.dumps({"schema": "gator-dashboard-registry-v1",
                                         "repos": []}), encoding="utf-8")
    monkeypatch.setattr(gator_core, "DASHBOARD_REGISTRY", registry_file)
    monkeypatch.setattr(dashboard, "_REGISTRY_REPOS", ())
    monkeypatch.setattr(dashboard, "_REGISTRY_FILE_STAMP", None)
    monkeypatch.setattr(dashboard, "_COLLECTION",
                        {"started": 0, "finished": 0, "again": False})
    monkeypatch.setattr(dashboard.DashboardHandler, "fast_data",
                        {"generated_at": "seed", "repos": [], "collection": 0})
    monkeypatch.setattr(dashboard, "collect_standalone_data", _fleet)
    with dashboard._STATE_WRITE_LOCK:
        dashboard._registry_load_from_disk()

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), dashboard.DashboardHandler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    _wait_until(_idle, "refresh to finish at teardown")
    httpd.shutdown()
    thread.join(timeout=5)


class TestNumberedCollections:

    def test_refresh_names_its_collection_and_the_data_carries_it(self, server):
        body = _json(server, "/api/refresh")
        assert body == {"status": "refreshing", "collection": 1}
        _wait_until(_idle, "refresh")
        assert _json(server, "/api/data")["collection"] == 1
        state = _json(server, "/api/state")
        assert (state["collection"], state["started"], state["finished"]) == (1, 1, 1)

    def test_a_refresh_during_a_collection_waits_for_the_rerun(self, server, monkeypatch):
        """#107: the running collection may predate the caller's Update."""
        entered, release = threading.Event(), threading.Event()
        calls = []

        def slow(registry):
            calls.append(1)
            if len(calls) == 1:
                entered.set()
                assert release.wait(TIMEOUT)
            return _fleet(registry, ts=f"c{len(calls)}")

        monkeypatch.setattr(dashboard, "collect_standalone_data", slow)
        assert _json(server, "/api/refresh")["collection"] == 1
        assert entered.wait(TIMEOUT)
        assert _json(server, "/api/refresh") == {"status": "already_refreshing",
                                                 "collection": 2}
        assert _json(server, "/api/refresh")["collection"] == 2   # still one rerun
        release.set()
        _wait_until(_idle, "both collections")
        assert len(calls) == 2
        data = _json(server, "/api/data")
        assert (data["collection"], data["generated_at"]) == (2, "c2")

    def test_a_failed_collection_still_finishes(self, server, monkeypatch):
        def boom(registry):
            raise RuntimeError("simulated")

        monkeypatch.setattr(dashboard, "collect_standalone_data", boom)
        assert _json(server, "/api/refresh")["collection"] == 1
        _wait_until(_idle, "failed refresh")
        state = _json(server, "/api/state")
        assert state["finished"] == 1          # a waiter stops waiting
        assert state["collection"] == 0        # the old Fleet stays published


class TestStateProbe:

    def test_state_reports_the_build(self, server):
        assert _json(server, "/api/state")["build"] == dashboard.DASHBOARD_BUILD

    def test_a_terminal_registration_starts_a_refresh(self, server, tmp_path):
        """#108 follow-up: Fleet learns of it without a click."""
        repo = tmp_path / "code" / "from-cli"
        (repo / ".git").mkdir(parents=True)
        time.sleep(0.01)
        assert gator_core.ensure_dashboard_registry_entry(repo, source="gatorize")["status"] == "added"

        state = _json(server, "/api/state")
        assert state["started"] == 1
        _wait_until(_idle, "refresh")
        names = [r["name"] for r in _json(server, "/api/data")["repos"]]
        assert names == ["from-cli"]

        # An unchanged registry file starts nothing.
        assert _json(server, "/api/state")["started"] == 1


class TestBuildStamp:

    def test_served_page_carries_the_build_meta(self, server):
        _, html = _get(server, "/")
        assert (f'<meta name="gator-dashboard-build" '
                f'content="{dashboard.DASHBOARD_BUILD}">') in html

    def test_build_id_changes_when_an_asset_changes(self, monkeypatch, tmp_path):
        assets = tmp_path / "dashboard"
        (assets / "views").mkdir(parents=True)
        (assets / "dashboard.js").write_text("a", encoding="utf-8")
        (assets / "views" / "fleet.js").write_text("b", encoding="utf-8")
        (assets / "notes.txt").write_text("ignored", encoding="utf-8")
        monkeypatch.setattr(dashboard, "DASHBOARD_DIR", assets)
        first = dashboard._dashboard_build_id()
        assert len(first) == 12
        (assets / "notes.txt").write_text("still ignored", encoding="utf-8")
        assert dashboard._dashboard_build_id() == first
        (assets / "views" / "fleet.js").write_text("c", encoding="utf-8")
        assert dashboard._dashboard_build_id() != first
