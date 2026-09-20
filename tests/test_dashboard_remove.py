"""
Tests for POST /api/repos/remove — dashboard registry removal endpoint.

Exercises the route via direct HTTP against a real DashboardHandler
running on an ephemeral HTTPServer. Isolation: monkeypatch
gator_core.DASHBOARD_REGISTRY, the module-level _REGISTRY_REPOS,
and DashboardHandler.fast_data.
"""

import json
import threading
from http.server import HTTPServer
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

from conftest import SCRIPTS_DIR, load_script

import gator_core

dashboard = load_script("gator-dashboard")


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def registry_file(tmp_path):
    """Create a temp registry file and return its path."""
    reg = tmp_path / "dashboard-repos.json"
    return reg


def _write_registry(path, repos):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema": "gator-dashboard-registry-v1",
        "repos": repos,
    }, indent=2), encoding="utf-8")


def _read_registry(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("repos", [])


@pytest.fixture
def server(monkeypatch, registry_file):
    """Start an ephemeral DashboardHandler HTTP server.

    Returns a callable that sets up the three isolation seams and
    provides a `url` attribute for requests.
    """
    class Ctx:
        def __init__(self):
            self.url = None
            self._httpd = None
            self._thread = None

        def start(self, repos):
            _write_registry(registry_file, repos)
            monkeypatch.setattr(gator_core, "DASHBOARD_REGISTRY", registry_file)

            registry_list = list(repos)
            monkeypatch.setattr(dashboard, "_REGISTRY_REPOS", registry_list)
            self._registry_list = registry_list

            fast_repos = [{"name": r["name"], "path": r["path"]} for r in repos]
            dashboard.DashboardHandler.fast_data = {"repos": fast_repos}

            self._httpd = HTTPServer(("127.0.0.1", 0), dashboard.DashboardHandler)
            port = self._httpd.server_address[1]
            self.url = f"http://127.0.0.1:{port}"
            self._thread = threading.Thread(target=self._httpd.serve_forever,
                                            daemon=True)
            self._thread.start()

        def stop(self):
            if self._httpd:
                self._httpd.shutdown()
                self._thread.join(timeout=5)

    ctx = Ctx()
    yield ctx
    ctx.stop()


def _post(url, path, body=None, *, auth=True):
    """POST helper. Returns (status, parsed_json)."""
    data = json.dumps(body).encode("utf-8") if body is not None else b""
    req = Request(url + path, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if auth:
        req.add_header("X-Gator-Dashboard", "1")
    try:
        resp = urlopen(req, timeout=5)
        return resp.status, json.loads(resp.read())
    except HTTPError as e:
        return e.code, json.loads(e.read())


# ── tests ─────────────────────────────────────────────────────────────────────


class TestRemoveRepo:

    def test_remove_repo_by_path_returns_ok(self, server, registry_file):
        repo_path = str(Path("C:/fake/test-repo").resolve())
        server.start([{"name": "test-repo", "path": repo_path}])

        status, data = _post(server.url, "/api/repos/remove",
                             {"path": repo_path})
        assert status == 200
        assert data["status"] == "ok"
        assert data["removed"] == repo_path

        persisted = _read_registry(registry_file)
        assert not any(r["path"] == repo_path for r in persisted)

    def test_remove_repo_not_found_returns_404(self, server):
        repo_path = str(Path("C:/fake/exists").resolve())
        server.start([{"name": "exists", "path": repo_path}])

        status, data = _post(server.url, "/api/repos/remove",
                             {"path": "C:/fake/not-here"})
        assert status == 404
        assert "not found" in data.get("error", "")

    def test_remove_repo_without_auth_header_returns_403(self, server):
        repo_path = str(Path("C:/fake/repo").resolve())
        server.start([{"name": "repo", "path": repo_path}])

        status, data = _post(server.url, "/api/repos/remove",
                             {"path": repo_path}, auth=False)
        assert status == 403

    def test_remove_repo_duplicate_names_only_removes_target(
            self, server, registry_file):
        path_a = str(Path("C:/fake/project-a").resolve())
        path_b = str(Path("C:/fake/project-b").resolve())
        server.start([
            {"name": "repo", "path": path_a},
            {"name": "repo", "path": path_b},
        ])

        status, data = _post(server.url, "/api/repos/remove",
                             {"path": path_a})
        assert status == 200

        persisted = _read_registry(registry_file)
        assert len(persisted) == 1
        assert persisted[0]["path"] == path_b

    def test_remove_repo_missing_directory_succeeds(
            self, server, registry_file):
        missing = str(Path("C:/nonexistent/deleted-repo").resolve())
        server.start([{"name": "deleted-repo", "path": missing}])

        status, data = _post(server.url, "/api/repos/remove",
                             {"path": missing})
        assert status == 200
        assert data["status"] == "ok"

        persisted = _read_registry(registry_file)
        assert len(persisted) == 0

    def test_remove_repo_cache_coherence(self, server):
        repo_path = str(Path("C:/fake/cached").resolve())
        server.start([{"name": "cached", "path": repo_path}])

        _post(server.url, "/api/repos/remove", {"path": repo_path})

        assert not any(
            str(Path(r.get("path", "")).resolve()) == repo_path
            for r in server._registry_list
        )
        fast_repos = dashboard.DashboardHandler.fast_data.get("repos", [])
        assert not any(
            str(Path(r.get("path", "")).resolve()) == repo_path
            for r in fast_repos
        )

    def test_remove_repo_invalid_body_returns_400(self, server):
        server.start([{"name": "x", "path": "C:/fake/x"}])

        status, data = _post(server.url, "/api/repos/remove",
                             {"not_path": "something"})
        assert status == 400
        assert "path" in data.get("error", "").lower()
