"""
#108: a repository registered outside a running Dashboard (by `gator
gatorize` or `gator init`, which write the registry file only) is picked
up without a restart.

Exercises the real routes on an ephemeral HTTPServer. Isolation:
monkeypatch gator_core.DASHBOARD_REGISTRY, the module-level
_REGISTRY_REPOS / _REGISTRY_FILE_STAMP, and DashboardHandler.fast_data.
"""

import json
import os
import threading
import time
from http.server import HTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from conftest import load_script

import gator_core

dashboard = load_script("gator-dashboard")


def _get(url, path):
    try:
        resp = urlopen(Request(url + path), timeout=10)
        return resp.status, json.loads(resp.read())
    except HTTPError as e:
        return e.code, json.loads(e.read())


def _post(url, path, body):
    req = Request(url + path, data=json.dumps(body).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Gator-Dashboard", "1")
    try:
        resp = urlopen(req, timeout=10)
        return resp.status, json.loads(resp.read())
    except HTTPError as e:
        return e.code, json.loads(e.read())


def _make_repo(root, name):
    repo = root / name
    (repo / ".git").mkdir(parents=True)
    return repo


def _registry_paths():
    return {str(Path(r["path"]).resolve()) for r in dashboard._registry_snapshot()}


@pytest.fixture
def dash(monkeypatch, tmp_path):
    """A Dashboard that loaded an empty registry file at startup, as main() does."""
    registry_file = tmp_path / "home" / ".gator" / "dashboard-repos.json"
    monkeypatch.setattr(gator_core, "DASHBOARD_REGISTRY", registry_file)
    monkeypatch.setattr(dashboard, "_REGISTRY_REPOS", ())
    monkeypatch.setattr(dashboard, "_REGISTRY_FILE_STAMP", None)
    monkeypatch.setattr(dashboard.DashboardHandler, "fast_data", {"repos": []})
    scan_root = tmp_path / "code"
    scan_root.mkdir()
    monkeypatch.setenv("GATOR_DASHBOARD_DISCOVERY_ROOTS", str(scan_root))

    with dashboard._STATE_WRITE_LOCK:
        dashboard._registry_load_from_disk()

    httpd = HTTPServer(("127.0.0.1", 0), dashboard.DashboardHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    class Ctx:
        url = f"http://127.0.0.1:{httpd.server_address[1]}"
        root = scan_root

        def cli_register(self, repo):
            """Register the way `gator gatorize` / `gator init` do."""
            # A distinct mtime even on coarse filesystem clocks.
            time.sleep(0.01)
            result = gator_core.ensure_dashboard_registry_entry(repo, source="gatorize")
            assert result["status"] == "added"

    yield Ctx()
    httpd.shutdown()
    thread.join(timeout=5)


class TestRegisterAfterCliRegistration:

    def test_add_succeeds_and_publishes_the_repo(self, dash):
        """The reported failure: Add said "Already registered" and the
        repository stayed out of the in-memory registry."""
        repo = _make_repo(dash.root, "new-repo")
        dash.cli_register(repo)
        assert _registry_paths() == set()

        status, data = _post(dash.url, "/api/repos/register", {"path": str(repo)})

        assert status == 200, data
        assert data["registered"] is True
        assert str(repo.resolve()) in _registry_paths()

    def test_add_still_409_when_the_dashboard_already_shows_it(self, dash):
        repo = _make_repo(dash.root, "shown")
        status, _ = _post(dash.url, "/api/repos/register", {"path": str(repo)})
        assert status == 200

        status, data = _post(dash.url, "/api/repos/register", {"path": str(repo)})
        assert status == 409
        assert data["error"] == "Already registered"

    def test_add_adopts_without_a_startup_stamp(self, dash, monkeypatch):
        """The register fix does not depend on the file-sync stamp."""
        monkeypatch.setattr(dashboard, "_REGISTRY_FILE_STAMP", None)
        repo = _make_repo(dash.root, "unstamped")
        dash.cli_register(repo)

        status, _ = _post(dash.url, "/api/repos/register", {"path": str(repo)})
        assert status == 200
        assert str(repo.resolve()) in _registry_paths()


class TestDiscoverSyncsTheRegistryFile:

    def test_cli_registered_repo_is_registered_not_discoverable(self, dash):
        repo = _make_repo(dash.root, "from-cli")
        status, data = _get(dash.url, "/api/repos/discover")
        assert [r["name"] for r in data["repos"]] == ["from-cli"]
        assert data["registry_changed"] is False

        dash.cli_register(repo)
        status, data = _get(dash.url, "/api/repos/discover")

        assert status == 200
        assert data["repos"] == []
        assert data["registry_changed"] is True
        assert str(repo.resolve()) in _registry_paths()

        # Unchanged file: no reload, no second Fleet refresh.
        _, data = _get(dash.url, "/api/repos/discover")
        assert data["registry_changed"] is False

    def test_no_stamp_means_no_sync(self, dash, monkeypatch):
        """A process that never loaded the file keeps its own registry."""
        monkeypatch.setattr(dashboard, "_REGISTRY_FILE_STAMP", None)
        dash.cli_register(_make_repo(dash.root, "ignored"))

        _, data = _get(dash.url, "/api/repos/discover")
        assert data["registry_changed"] is False
        assert _registry_paths() == set()

    def test_a_different_registry_file_is_never_mixed_in(self, dash, monkeypatch, tmp_path):
        other = tmp_path / "other" / "dashboard-repos.json"
        monkeypatch.setattr(gator_core, "DASHBOARD_REGISTRY", other)
        dash.cli_register(_make_repo(dash.root, "elsewhere"))

        assert dashboard._registry_sync_from_disk() is False
        assert _registry_paths() == set()


class TestRefreshSyncsTheRegistryFile:

    def _refresh_and_wait(self, url):
        status, data = _get(url, "/api/refresh")
        assert status == 200 and data["status"] == "refreshing"
        deadline = time.time() + 30
        while time.time() < deadline:
            if dashboard.DashboardHandler._refresh_lock.acquire(blocking=False):
                dashboard.DashboardHandler._refresh_lock.release()
                return
            time.sleep(0.05)
        pytest.fail("refresh did not finish")

    def test_refresh_shows_a_cli_registered_repo_in_fleet(self, dash, monkeypatch):
        collected = []

        def fake_collect(registry):
            collected.append([r["path"] for r in registry])
            return {"repos": [{"name": r["name"], "path": r["path"]} for r in registry],
                    "generated_at": "now"}

        monkeypatch.setattr(dashboard, "collect_standalone_data", fake_collect)
        repo = _make_repo(dash.root, "fleet-repo")
        dash.cli_register(repo)

        self._refresh_and_wait(dash.url)

        assert collected and str(repo.resolve()) in {str(Path(p).resolve()) for p in collected[-1]}
        fleet = dashboard._fleet_snapshot()
        assert [r["name"] for r in fleet["repos"]] == ["fleet-repo"]

    def test_refresh_drops_a_repo_the_cli_removed(self, dash, monkeypatch):
        monkeypatch.setattr(
            dashboard, "collect_standalone_data",
            lambda registry: {"repos": [{"name": r["name"], "path": r["path"]}
                                        for r in registry], "generated_at": "now"})
        repo = _make_repo(dash.root, "going")
        assert _post(dash.url, "/api/repos/register", {"path": str(repo)})[0] == 200

        time.sleep(0.01)
        assert gator_core.remove_dashboard_repo(str(repo.resolve()))
        self._refresh_and_wait(dash.url)

        assert _registry_paths() == set()
        assert dashboard._fleet_snapshot()["repos"] == []
