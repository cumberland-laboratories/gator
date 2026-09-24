"""
Tests for loop workspace API routes — Modules 1–2 (enumeration + resolver + events).

Exercises GET /api/repo-by-key/<repo_key>/loops,
GET /api/repo-by-key/<repo_key>/loops/<id>/status, and
GET /api/repo-by-key/<repo_key>/loops/<id>/events via direct HTTP
against a real DashboardHandler on an ephemeral HTTPServer.
"""

import hashlib
import json
import sys
import threading
from http.server import HTTPServer
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

from conftest import SCRIPTS_DIR, load_script

import gator_core

dashboard = load_script("gator-dashboard")


# ── helpers ──────────────────────────────────────────────────────────────────

def _repo_key(path):
    """Compute the same path-hash the dashboard uses for repo identity."""
    resolved = str(Path(path).resolve())
    return hashlib.sha256(resolved.encode()).hexdigest()[:12]


def _get(url, path):
    """GET helper. Returns (status, parsed_json)."""
    req = Request(url + path, method="GET")
    try:
        resp = urlopen(req, timeout=5)
        return resp.status, json.loads(resp.read())
    except HTTPError as e:
        return e.code, json.loads(e.read())


def _get_raw(url, path):
    """GET helper returning (status, body_bytes, content_type)."""
    req = Request(url + path, method="GET")
    try:
        resp = urlopen(req, timeout=5)
        return resp.status, resp.read(), resp.headers.get("Content-Type", "")
    except HTTPError as e:
        return e.code, e.read(), e.headers.get("Content-Type", "")


def _post(url, path, body=None):
    """POST helper with anti-CSRF header. Returns (status, parsed_json, headers)."""
    data = json.dumps(body or {}).encode("utf-8")
    req = Request(url + path, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Gator-Dashboard", "1")
    try:
        resp = urlopen(req, timeout=10)
        return resp.status, json.loads(resp.read()), resp.headers
    except HTTPError as e:
        return e.code, json.loads(e.read()), e.headers


def _write_session(loop_dir, session):
    """Write a session.json file into a loop directory."""
    loop_dir.mkdir(parents=True, exist_ok=True)
    (loop_dir / "session.json").write_text(
        json.dumps(session, indent=2), encoding="utf-8"
    )


def _write_events(loop_dir, events):
    """Write events.jsonl into a loop directory."""
    loop_dir.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(e, separators=(",", ":")) for e in events]
    (loop_dir / "events.jsonl").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def _make_session(loop_id, feature="test-feature", stage="plan_drafting",
                  round_num=0, max_rounds=3, blocked=False):
    """Build a minimal session dict for testing."""
    status = {
        "stage": stage,
        "next_role": "draftor",
        "round": round_num,
        "max_rounds": max_rounds,
        "blocked": blocked,
        "turn_deadline": "2026-09-22T10:05:00+00:00",
        "turn_timeout_seconds": 300,
        "last_updated": "2026-09-22T10:00:00+00:00",
    }
    if stage in ("blocked_on_architect", "paused_by_architect"):
        status["resume_stage"] = "plan_drafting"
        status["resume_next_role"] = "draftor"
    return {
        "schema": "gator-loop-session-v1",
        "loop_id": loop_id,
        "feature": feature,
        "created_at": "2026-09-22T10:00:00+00:00",
        "roles": {
            "draftor": {"role": "draftor", "joined": False},
            "reviewer": {"role": "reviewer", "joined": False},
            "architect": {"role": "architect"},
        },
        "status": status,
        "current": {"draft": None, "findings": None},
        "turns": [],
        "decisions": [],
    }


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def registry_file(tmp_path):
    reg = tmp_path / "dashboard-repos.json"
    return reg


def _write_registry(path, repos):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema": "gator-dashboard-registry-v1",
        "repos": repos,
    }, indent=2), encoding="utf-8")


@pytest.fixture
def server(monkeypatch, registry_file):
    """Ephemeral DashboardHandler HTTP server with isolation."""
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


# ── tests ────────────────────────────────────────────────────────────────────

class TestLoopList:

    def test_list_empty_no_loops_dir(self, server, tmp_path):
        """Repo with no .gator/loops/ returns an empty list."""
        repo = tmp_path / "repo-a"
        (repo / ".gator").mkdir(parents=True)
        rk = _repo_key(repo)
        server.start([{"name": "repo-a", "path": str(repo), "repo_key": rk}])

        status, data = _get(server.url, f"/api/repo-by-key/{rk}/loops")
        assert status == 200
        assert data["loops"] == []

    def test_list_with_loops(self, server, tmp_path):
        """Repo with loops returns them sorted by recency (name descending)."""
        repo = tmp_path / "repo-b"
        loops_dir = repo / ".gator" / "loops"
        loops_dir.mkdir(parents=True)

        _write_session(loops_dir / "feature-a-2026-09-20T10-00-00Z",
                       _make_session("feature-a-2026-09-20T10-00-00Z",
                                     feature="feature-a",
                                     stage="plan_approved"))
        _write_session(loops_dir / "feature-b-2026-09-22T10-00-00Z",
                       _make_session("feature-b-2026-09-22T10-00-00Z",
                                     feature="feature-b",
                                     stage="plan_drafting"))

        rk = _repo_key(repo)
        server.start([{"name": "repo-b", "path": str(repo), "repo_key": rk}])

        status, data = _get(server.url, f"/api/repo-by-key/{rk}/loops")
        assert status == 200
        loops = data["loops"]
        assert len(loops) == 2
        assert loops[0]["feature"] == "feature-b"
        assert loops[1]["feature"] == "feature-a"

        for loop in loops:
            assert "loop_id" in loop
            assert "stage" in loop
            assert "round" in loop
            assert "max_rounds" in loop
            assert "blocked" in loop
            assert "created_at" in loop

    def test_list_inaccessible_repo_returns_404(self, server):
        """Non-existent repo_key returns 404."""
        server.start([])
        status, data = _get(server.url, "/api/repo-by-key/nonexistent/loops")
        assert status == 404

    def test_two_repos_list_only_their_own_loops(self, server, tmp_path):
        """Each repo's loop list contains only its own loops."""
        repo_a = tmp_path / "repo-alpha"
        repo_b = tmp_path / "repo-beta"
        loops_a = repo_a / ".gator" / "loops"
        loops_b = repo_b / ".gator" / "loops"
        loops_a.mkdir(parents=True)
        loops_b.mkdir(parents=True)

        _write_session(loops_a / "loop-alpha-2026-09-22T10-00-00Z",
                       _make_session("loop-alpha-2026-09-22T10-00-00Z",
                                     feature="alpha-work"))
        _write_session(loops_b / "loop-beta-2026-09-22T10-00-00Z",
                       _make_session("loop-beta-2026-09-22T10-00-00Z",
                                     feature="beta-work"))

        rk_a = _repo_key(repo_a)
        rk_b = _repo_key(repo_b)
        server.start([
            {"name": "repo-alpha", "path": str(repo_a), "repo_key": rk_a},
            {"name": "repo-beta", "path": str(repo_b), "repo_key": rk_b},
        ])

        _, data_a = _get(server.url, f"/api/repo-by-key/{rk_a}/loops")
        _, data_b = _get(server.url, f"/api/repo-by-key/{rk_b}/loops")

        assert len(data_a["loops"]) == 1
        assert data_a["loops"][0]["feature"] == "alpha-work"
        assert len(data_b["loops"]) == 1
        assert data_b["loops"][0]["feature"] == "beta-work"


class TestLoopStatus:

    def test_status_found(self, server, tmp_path):
        """Valid loop returns session data without schema field."""
        repo = tmp_path / "repo-s"
        loops_dir = repo / ".gator" / "loops"
        loop_id = "status-test-2026-09-22T10-00-00Z"
        _write_session(loops_dir / loop_id,
                       _make_session(loop_id, feature="status-feature"))

        rk = _repo_key(repo)
        server.start([{"name": "repo-s", "path": str(repo), "repo_key": rk}])

        status, data = _get(server.url,
                            f"/api/repo-by-key/{rk}/loops/{loop_id}/status")
        assert status == 200
        assert data["feature"] == "status-feature"
        assert data["loop_id"] == loop_id
        assert "schema" not in data
        assert "status" in data
        assert data["status"]["stage"] == "plan_drafting"

    def test_status_not_found(self, server, tmp_path):
        """Non-existent loop returns 404."""
        repo = tmp_path / "repo-snf"
        (repo / ".gator" / "loops").mkdir(parents=True)
        rk = _repo_key(repo)
        server.start([{"name": "repo-snf", "path": str(repo), "repo_key": rk}])

        status, data = _get(server.url,
                            f"/api/repo-by-key/{rk}/loops/no-such-loop/status")
        assert status == 404

    def test_status_repo_without_gator_dir_returns_404(self, server, tmp_path):
        """Registered repo with no .gator/ returns 404, not 400."""
        repo = tmp_path / "repo-nogator"
        repo.mkdir(parents=True)
        rk = _repo_key(repo)
        server.start([{"name": "repo-nogator", "path": str(repo), "repo_key": rk}])

        status, data = _get(server.url,
                            f"/api/repo-by-key/{rk}/loops/any-loop/status")
        assert status == 404

    def test_status_repo_without_loops_dir_returns_404(self, server, tmp_path):
        """Registered repo with .gator/ but no loops/ returns 404, not 400."""
        repo = tmp_path / "repo-noloops"
        (repo / ".gator").mkdir(parents=True)
        rk = _repo_key(repo)
        server.start([{"name": "repo-noloops", "path": str(repo), "repo_key": rk}])

        status, data = _get(server.url,
                            f"/api/repo-by-key/{rk}/loops/any-loop/status")
        assert status == 404


class TestLoopIdValidation:

    def test_loop_id_with_dotdot_rejected(self, server, tmp_path):
        """Loop id containing '..' is rejected with 400."""
        repo = tmp_path / "repo-v1"
        (repo / ".gator" / "loops").mkdir(parents=True)
        rk = _repo_key(repo)
        server.start([{"name": "repo-v1", "path": str(repo), "repo_key": rk}])

        status, data = _get(server.url,
                            f"/api/repo-by-key/{rk}/loops/..secret/status")
        assert status == 400

    def test_loop_id_with_slash_rejected(self, tmp_path):
        """Loop id containing '/' is rejected by _resolve_loop_dir."""
        repo = tmp_path / "repo-v2"
        (repo / ".gator" / "loops").mkdir(parents=True)
        rk = _repo_key(repo)

        saved = dashboard._REGISTRY_REPOS
        dashboard._REGISTRY_REPOS = [
            {"name": "repo-v2", "path": str(repo), "repo_key": rk}
        ]
        try:
            with pytest.raises(ValueError, match="invalid loop id"):
                dashboard._resolve_loop_dir(rk, "bad/id")
            with pytest.raises(ValueError, match="invalid loop id"):
                dashboard._resolve_loop_dir(rk, "bad\\id")
            with pytest.raises(ValueError, match="invalid loop id"):
                dashboard._resolve_loop_dir(rk, "has\x00null")
        finally:
            dashboard._REGISTRY_REPOS = saved


class TestContainment:

    def _setup_resolver(self, repo_path):
        """Set _REGISTRY_REPOS for direct resolver testing."""
        rk = _repo_key(repo_path)
        dashboard._REGISTRY_REPOS = [
            {"name": "test", "path": str(repo_path), "repo_key": rk}
        ]
        return rk

    @pytest.fixture(autouse=True)
    def _save_restore_registry(self):
        saved = dashboard._REGISTRY_REPOS
        yield
        dashboard._REGISTRY_REPOS = saved

    def test_symlink_loop_dir_rejected(self, tmp_path):
        """A symlink inside loops/ is rejected even if it points at a valid dir."""
        repo = tmp_path / "repo"
        loops_dir = repo / ".gator" / "loops"
        real_loop = loops_dir / "real-loop"
        real_loop.mkdir(parents=True)
        _write_session(real_loop, _make_session("real-loop"))

        symlink = loops_dir / "alias-loop"
        try:
            symlink.symlink_to(real_loop, target_is_directory=True)
        except OSError:
            pytest.skip("symlink creation not supported")

        rk = self._setup_resolver(repo)
        with pytest.raises(ValueError, match="reparse point or symlink"):
            dashboard._resolve_loop_dir(rk, "alias-loop")

    def test_same_prefix_sibling_rejected(self, tmp_path):
        """A dir named 'loops-escape' with matching prefix is not traversable."""
        repo = tmp_path / "repo"
        loops_dir = repo / ".gator" / "loops"
        loops_dir.mkdir(parents=True)

        escape_dir = repo / ".gator" / "loops-escape"
        escape_dir.mkdir()
        (escape_dir / "session.json").write_text("{}", encoding="utf-8")

        rk = self._setup_resolver(repo)
        # The loop_id can't contain '..' or '/' so there's no way to
        # navigate to loops-escape from inside loops/ — the structural
        # parent check ensures this even if someone crafted a path.
        with pytest.raises(FileNotFoundError):
            dashboard._resolve_loop_dir(rk, "loops-escape")

    def test_loops_namespace_symlink_rejected_by_resolver(self, tmp_path):
        """.gator/loops itself being a symlink is rejected."""
        repo = tmp_path / "repo-ns"
        gator_dir = repo / ".gator"
        gator_dir.mkdir(parents=True)

        external = tmp_path / "external-loops"
        external_loop = external / "fake-loop"
        external_loop.mkdir(parents=True)
        _write_session(external_loop, _make_session("fake-loop"))

        loops_link = gator_dir / "loops"
        try:
            loops_link.symlink_to(external, target_is_directory=True)
        except OSError:
            pytest.skip("symlink creation not supported")

        rk = self._setup_resolver(repo)
        with pytest.raises(ValueError, match="loops.*reparse point or symlink"):
            dashboard._resolve_loop_dir(rk, "fake-loop")

    def test_loops_namespace_symlink_returns_empty_list(self, server, tmp_path):
        """.gator/loops being a symlink makes the list handler return empty."""
        repo = tmp_path / "repo-nsl"
        gator_dir = repo / ".gator"
        gator_dir.mkdir(parents=True)

        external = tmp_path / "external-loops2"
        external_loop = external / "leak-loop"
        external_loop.mkdir(parents=True)
        _write_session(external_loop, _make_session("leak-loop"))

        loops_link = gator_dir / "loops"
        try:
            loops_link.symlink_to(external, target_is_directory=True)
        except OSError:
            pytest.skip("symlink creation not supported")

        rk = _repo_key(repo)
        server.start([{"name": "repo-nsl", "path": str(repo), "repo_key": rk}])

        status, data = _get(server.url, f"/api/repo-by-key/{rk}/loops")
        assert status == 200
        assert data["loops"] == []

    def test_symlink_skipped_in_list(self, server, tmp_path):
        """Symlink entries inside loops/ are skipped by the list handler."""
        repo = tmp_path / "repo-sym"
        loops_dir = repo / ".gator" / "loops"
        real_loop = loops_dir / "real-2026-09-22T10-00-00Z"
        real_loop.mkdir(parents=True)
        _write_session(real_loop, _make_session("real-2026-09-22T10-00-00Z"))

        alias = loops_dir / "alias-2026-09-22T11-00-00Z"
        try:
            alias.symlink_to(real_loop, target_is_directory=True)
        except OSError:
            pytest.skip("symlink creation not supported")

        rk = _repo_key(repo)
        server.start([{"name": "repo-sym", "path": str(repo), "repo_key": rk}])

        status, data = _get(server.url, f"/api/repo-by-key/{rk}/loops")
        assert status == 200
        assert len(data["loops"]) == 1
        assert data["loops"][0]["loop_id"] == "real-2026-09-22T10-00-00Z"


class TestStatusAllowlist:

    def test_secret_fields_filtered_from_status(self, server, tmp_path):
        """Token-like and unexpected fields are filtered from status response."""
        repo = tmp_path / "repo-sec"
        loops_dir = repo / ".gator" / "loops"
        loop_id = "sec-test-2026-09-22T10-00-00Z"
        session = _make_session(loop_id, feature="secret-test")
        session["tokens"] = {"draftor": {"nonce": "abc123"}}
        session["secret_nonce"] = "should-not-appear"
        session["schema"] = "gator-loop-session-v1"
        _write_session(loops_dir / loop_id, session)

        rk = _repo_key(repo)
        server.start([{"name": "repo-sec", "path": str(repo), "repo_key": rk}])

        status, data = _get(server.url,
                            f"/api/repo-by-key/{rk}/loops/{loop_id}/status")
        assert status == 200
        assert "tokens" not in data
        assert "secret_nonce" not in data
        assert "schema" not in data
        assert data["feature"] == "secret-test"
        assert data["loop_id"] == loop_id
        assert "status" in data
        assert "roles" in data
        assert "turns" in data
        assert "decisions" in data


class TestLoopEvents:

    def test_events_found(self, server, tmp_path):
        """Loop with events returns them as a JSON array."""
        repo = tmp_path / "repo-ev"
        loops_dir = repo / ".gator" / "loops"
        loop_id = "events-test-2026-09-22T10-00-00Z"
        _write_session(loops_dir / loop_id,
                       _make_session(loop_id, feature="events-feature"))
        _write_events(loops_dir / loop_id, [
            {"type": "loop_started", "loop_id": loop_id,
             "ts": "2026-09-22T10:00:00+00:00"},
            {"type": "turn_started", "loop_id": loop_id, "role": "draftor",
             "ts": "2026-09-22T10:00:01+00:00"},
        ])

        rk = _repo_key(repo)
        server.start([{"name": "repo-ev", "path": str(repo), "repo_key": rk}])

        status, data = _get(server.url,
                            f"/api/repo-by-key/{rk}/loops/{loop_id}/events")
        assert status == 200
        assert len(data["events"]) == 2
        assert data["events"][0]["type"] == "loop_started"
        assert data["events"][1]["type"] == "turn_started"
        assert data["events"][1]["role"] == "draftor"

    def test_events_no_events_file(self, server, tmp_path):
        """Loop with no events.jsonl returns an empty array."""
        repo = tmp_path / "repo-noev"
        loops_dir = repo / ".gator" / "loops"
        loop_id = "no-events-2026-09-22T10-00-00Z"
        _write_session(loops_dir / loop_id,
                       _make_session(loop_id, feature="no-events"))

        rk = _repo_key(repo)
        server.start([{"name": "repo-noev", "path": str(repo), "repo_key": rk}])

        status, data = _get(server.url,
                            f"/api/repo-by-key/{rk}/loops/{loop_id}/events")
        assert status == 200
        assert data["events"] == []

    def test_events_loop_not_found(self, server, tmp_path):
        """Non-existent loop returns 404 for events."""
        repo = tmp_path / "repo-evnf"
        (repo / ".gator" / "loops").mkdir(parents=True)
        rk = _repo_key(repo)
        server.start([{"name": "repo-evnf", "path": str(repo), "repo_key": rk}])

        status, data = _get(server.url,
                            f"/api/repo-by-key/{rk}/loops/no-such-loop/events")
        assert status == 404

    def test_events_symlinked_events_file_rejected(self, server, tmp_path):
        """Symlinked events.jsonl is rejected — returns 404, not external content."""
        repo = tmp_path / "repo-evsym"
        loops_dir = repo / ".gator" / "loops"
        loop_id = "symev-test-2026-09-22T10-00-00Z"
        loop_dir = loops_dir / loop_id
        _write_session(loop_dir, _make_session(loop_id, feature="sym-events"))

        external = tmp_path / "external-events.jsonl"
        external.write_text(
            '{"type":"leaked","secret":"should-not-appear"}\n',
            encoding="utf-8",
        )

        events_link = loop_dir / "events.jsonl"
        try:
            events_link.symlink_to(external)
        except OSError:
            pytest.skip("symlink creation not supported")

        rk = _repo_key(repo)
        server.start([{"name": "repo-evsym", "path": str(repo), "repo_key": rk}])

        status, data = _get(server.url,
                            f"/api/repo-by-key/{rk}/loops/{loop_id}/events")
        assert status == 404


class TestLoopArtifact:

    def test_artifact_found(self, server, tmp_path):
        """Allowed artifact file is served as text/plain."""
        repo = tmp_path / "repo-art"
        loops_dir = repo / ".gator" / "loops"
        loop_id = "art-test-2026-09-22T10-00-00Z"
        loop_dir = loops_dir / loop_id
        _write_session(loop_dir, _make_session(loop_id))
        (loop_dir / "sketch.md").write_text("# Sketch\nHello", encoding="utf-8")

        rk = _repo_key(repo)
        server.start([{"name": "repo-art", "path": str(repo), "repo_key": rk}])

        status, body, ct = _get_raw(
            server.url,
            f"/api/repo-by-key/{rk}/loops/{loop_id}/artifact/sketch.md")
        assert status == 200
        assert b"# Sketch" in body
        assert "text/plain" in ct

    def test_artifact_not_allowed(self, server, tmp_path):
        """Non-allowlisted filenames are rejected with 403."""
        repo = tmp_path / "repo-artna"
        loops_dir = repo / ".gator" / "loops"
        loop_id = "artna-test-2026-09-22T10-00-00Z"
        loop_dir = loops_dir / loop_id
        _write_session(loop_dir, _make_session(loop_id))
        (loop_dir / "session.json").write_text("{}", encoding="utf-8")

        rk = _repo_key(repo)
        server.start([{"name": "repo-artna", "path": str(repo), "repo_key": rk}])

        status, data = _get(
            server.url,
            f"/api/repo-by-key/{rk}/loops/{loop_id}/artifact/session.json")
        assert status == 403

    def test_artifact_tokens_blocked(self, server, tmp_path):
        """.tokens.json is never served through the artifact endpoint."""
        repo = tmp_path / "repo-arttok"
        loops_dir = repo / ".gator" / "loops"
        loop_id = "arttok-test-2026-09-22T10-00-00Z"
        loop_dir = loops_dir / loop_id
        _write_session(loop_dir, _make_session(loop_id))
        (loop_dir / ".tokens.json").write_text(
            '{"secret":"nonce"}', encoding="utf-8")

        rk = _repo_key(repo)
        server.start([{"name": "repo-arttok", "path": str(repo), "repo_key": rk}])

        status, data = _get(
            server.url,
            f"/api/repo-by-key/{rk}/loops/{loop_id}/artifact/.tokens.json")
        assert status == 403

    def test_artifact_not_found(self, server, tmp_path):
        """Missing artifact file returns 404."""
        repo = tmp_path / "repo-artnf"
        loops_dir = repo / ".gator" / "loops"
        loop_id = "artnf-test-2026-09-22T10-00-00Z"
        loop_dir = loops_dir / loop_id
        _write_session(loop_dir, _make_session(loop_id))

        rk = _repo_key(repo)
        server.start([{"name": "repo-artnf", "path": str(repo), "repo_key": rk}])

        status, data = _get(
            server.url,
            f"/api/repo-by-key/{rk}/loops/{loop_id}/artifact/plan.current.md")
        assert status == 404

    def test_artifact_round_files_allowed(self, server, tmp_path):
        """Round-numbered artifact files are allowed."""
        repo = tmp_path / "repo-artrnd"
        loops_dir = repo / ".gator" / "loops"
        loop_id = "artrnd-test-2026-09-22T10-00-00Z"
        loop_dir = loops_dir / loop_id
        _write_session(loop_dir, _make_session(loop_id))
        (loop_dir / "plan.round-1.md").write_text("# Plan R1", encoding="utf-8")
        (loop_dir / "findings.round-2.md").write_text("# Findings R2",
                                                       encoding="utf-8")

        rk = _repo_key(repo)
        server.start([{"name": "repo-artrnd", "path": str(repo), "repo_key": rk}])

        s1, body1, _ = _get_raw(
            server.url,
            f"/api/repo-by-key/{rk}/loops/{loop_id}/artifact/plan.round-1.md")
        assert s1 == 200
        assert b"Plan R1" in body1

        s2, body2, _ = _get_raw(
            server.url,
            f"/api/repo-by-key/{rk}/loops/{loop_id}/artifact/findings.round-2.md")
        assert s2 == 200
        assert b"Findings R2" in body2

    def test_artifact_symlink_rejected(self, server, tmp_path):
        """Symlinked artifact file is rejected."""
        repo = tmp_path / "repo-artsym"
        loops_dir = repo / ".gator" / "loops"
        loop_id = "artsym-test-2026-09-22T10-00-00Z"
        loop_dir = loops_dir / loop_id
        _write_session(loop_dir, _make_session(loop_id))

        external = tmp_path / "external-sketch.md"
        external.write_text("# Leaked", encoding="utf-8")

        try:
            (loop_dir / "sketch.md").symlink_to(external)
        except OSError:
            pytest.skip("symlink creation not supported")

        rk = _repo_key(repo)
        server.start([{"name": "repo-artsym", "path": str(repo), "repo_key": rk}])

        status, data = _get(
            server.url,
            f"/api/repo-by-key/{rk}/loops/{loop_id}/artifact/sketch.md")
        assert status == 404

    def test_artifact_traversal_rejected(self, tmp_path):
        """Path traversal in artifact filename is rejected by the handler."""
        repo = tmp_path / "repo-arttrav"
        (repo / ".gator" / "loops").mkdir(parents=True)
        rk = _repo_key(repo)

        saved = dashboard._REGISTRY_REPOS
        dashboard._REGISTRY_REPOS = [
            {"name": "repo-arttrav", "path": str(repo), "repo_key": rk}
        ]
        try:
            handler = dashboard.DashboardHandler
            assert not handler._is_allowed_loop_artifact(handler, "../session.json")
            assert not handler._is_allowed_loop_artifact(handler, "plan.round-1/../../../etc/passwd.md")
            assert not handler._is_allowed_loop_artifact(handler, "sketch.md/../../secret")
            assert not handler._is_allowed_loop_artifact(handler, "plan.round-1\\..\\.md")
            assert not handler._is_allowed_loop_artifact(handler, "has\x00null.md")
        finally:
            dashboard._REGISTRY_REPOS = saved

    def test_artifact_pattern_traversal_rejected(self, server, tmp_path):
        """Crafted filename matching pattern prefix but containing traversal."""
        repo = tmp_path / "repo-artpat"
        loops_dir = repo / ".gator" / "loops"
        loop_id = "artpat-test-2026-09-22T10-00-00Z"
        loop_dir = loops_dir / loop_id
        _write_session(loop_dir, _make_session(loop_id))

        rk = _repo_key(repo)
        server.start([{"name": "repo-artpat", "path": str(repo), "repo_key": rk}])

        crafted = "plan.round-1/../../secret.md"
        status, data = _get(
            server.url,
            f"/api/repo-by-key/{rk}/loops/{loop_id}/artifact/{crafted}")
        assert status == 400

    def test_artifact_pattern_requires_digits(self, server, tmp_path):
        """Round pattern only matches digits, not arbitrary text."""
        repo = tmp_path / "repo-artdig"
        loops_dir = repo / ".gator" / "loops"
        loop_id = "artdig-test-2026-09-22T10-00-00Z"
        loop_dir = loops_dir / loop_id
        _write_session(loop_dir, _make_session(loop_id))
        (loop_dir / "plan.round-abc.md").write_text("bad", encoding="utf-8")

        rk = _repo_key(repo)
        server.start([{"name": "repo-artdig", "path": str(repo), "repo_key": rk}])

        status, data = _get(
            server.url,
            f"/api/repo-by-key/{rk}/loops/{loop_id}/artifact/plan.round-abc.md")
        assert status == 403


# ── Module 4: loop start + prompt ──────────────────────────────────────────


class TestLoopStart:

    def test_start_success(self, server, tmp_path):
        """Start creates a new loop and returns 201 with loop_id."""
        repo = tmp_path / "repo-start"
        (repo / ".gator").mkdir(parents=True)
        sketch = repo / "sketch.md"
        sketch.write_text("# My sketch\n\nContent here.\n",
                          encoding="utf-8")

        rk = _repo_key(repo)
        server.start([{"name": "start", "path": str(repo),
                       "repo_key": rk}])

        status, data, hdrs = _post(
            server.url,
            f"/api/repo-by-key/{rk}/loops/start",
            {"feature": "widget", "sketch_path": str(sketch)})
        assert status == 201
        assert "loop_id" in data
        assert "widget" in data["loop_id"]

        loop_dir = repo / ".gator" / "loops" / data["loop_id"]
        assert loop_dir.is_dir()
        assert (loop_dir / "session.json").is_file()
        assert (loop_dir / "sketch.md").is_file()
        assert (loop_dir / ".tokens.json").is_file()
        assert (loop_dir / "events.jsonl").is_file()

    def test_start_relative_sketch(self, server, tmp_path):
        """Sketch path relative to repo root resolves correctly."""
        repo = tmp_path / "repo-startrel"
        (repo / ".gator").mkdir(parents=True)
        sketch = repo / ".gator" / "scratch-sketch.md"
        sketch.write_text("# Relative sketch\n", encoding="utf-8")

        rk = _repo_key(repo)
        server.start([{"name": "startrel", "path": str(repo),
                       "repo_key": rk}])

        status, data, _ = _post(
            server.url,
            f"/api/repo-by-key/{rk}/loops/start",
            {"feature": "rel-feature",
             "sketch_path": ".gator/scratch-sketch.md"})
        assert status == 201

    def test_start_missing_feature(self, server, tmp_path):
        """Empty feature returns 400."""
        repo = tmp_path / "repo-startmf"
        (repo / ".gator").mkdir(parents=True)
        rk = _repo_key(repo)
        server.start([{"name": "startmf", "path": str(repo),
                       "repo_key": rk}])

        status, data, _ = _post(
            server.url,
            f"/api/repo-by-key/{rk}/loops/start",
            {"feature": "", "sketch_path": "/tmp/x.md"})
        assert status == 400

    def test_start_missing_sketch(self, server, tmp_path):
        """Non-existent sketch file returns 400."""
        repo = tmp_path / "repo-startms"
        (repo / ".gator").mkdir(parents=True)
        rk = _repo_key(repo)
        server.start([{"name": "startms", "path": str(repo),
                       "repo_key": rk}])

        status, data, _ = _post(
            server.url,
            f"/api/repo-by-key/{rk}/loops/start",
            {"feature": "f", "sketch_path": str(tmp_path / "no.md")})
        assert status == 400

    def test_start_empty_sketch(self, server, tmp_path):
        """Empty sketch file returns 400."""
        repo = tmp_path / "repo-startes"
        (repo / ".gator").mkdir(parents=True)
        sketch = repo / "empty.md"
        sketch.write_text("", encoding="utf-8")
        rk = _repo_key(repo)
        server.start([{"name": "startes", "path": str(repo),
                       "repo_key": rk}])

        status, data, _ = _post(
            server.url,
            f"/api/repo-by-key/{rk}/loops/start",
            {"feature": "f", "sketch_path": str(sketch)})
        assert status == 400

    def test_start_sketch_outside_repo(self, server, tmp_path):
        """Sketch path outside the repo is rejected."""
        repo = tmp_path / "repo-startout"
        (repo / ".gator").mkdir(parents=True)
        outside = tmp_path / "outside.md"
        outside.write_text("# External", encoding="utf-8")
        rk = _repo_key(repo)
        server.start([{"name": "startout", "path": str(repo),
                       "repo_key": rk}])

        status, data, _ = _post(
            server.url,
            f"/api/repo-by-key/{rk}/loops/start",
            {"feature": "f", "sketch_path": str(outside)})
        assert status == 400
        assert "inside the repo" in data.get("error", "")

    def test_start_while_active_loop_exists(self, server, tmp_path):
        """Starting a loop when one is already active returns 409."""
        repo = tmp_path / "repo-startdup"
        loops_dir = repo / ".gator" / "loops"
        existing_id = "existing-2026-09-22T10-00-00Z"
        _write_session(
            loops_dir / existing_id,
            _make_session(existing_id, stage="plan_drafting"))
        sketch = repo / "sketch.md"
        sketch.write_text("# Sketch", encoding="utf-8")
        rk = _repo_key(repo)
        server.start([{"name": "startdup", "path": str(repo),
                       "repo_key": rk}])

        status, data, _ = _post(
            server.url,
            f"/api/repo-by-key/{rk}/loops/start",
            {"feature": "second", "sketch_path": str(sketch)})
        assert status == 409
        assert data.get("loop_id") == existing_id

    def test_start_repo_not_found(self, server, tmp_path):
        """Start on a non-existent repo_key returns 404."""
        repo = tmp_path / "repo-startnf"
        (repo / ".gator").mkdir(parents=True)
        rk = _repo_key(repo)
        server.start([{"name": "startnf", "path": str(repo),
                       "repo_key": rk}])

        status, data, _ = _post(
            server.url,
            "/api/repo-by-key/nonexistent/loops/start",
            {"feature": "f", "sketch_path": "/tmp/x.md"})
        assert status == 404

    def test_start_gitignore_includes_locks(self, server, tmp_path):
        """After start, .gitignore includes host.lock and start.lock."""
        repo = tmp_path / "repo-startgi"
        (repo / ".gator").mkdir(parents=True)
        sketch = repo / "sketch.md"
        sketch.write_text("# GI sketch\n", encoding="utf-8")
        rk = _repo_key(repo)
        server.start([{"name": "startgi", "path": str(repo),
                       "repo_key": rk}])

        status, data, _ = _post(
            server.url,
            f"/api/repo-by-key/{rk}/loops/start",
            {"feature": "gi-test", "sketch_path": str(sketch)})
        assert status == 201

        gitignore = repo / ".gator" / "loops" / ".gitignore"
        assert gitignore.is_file()
        content = gitignore.read_text(encoding="utf-8")
        assert "host.lock" in content
        assert "start.lock" in content


def _setup_loop_with_tokens(tmp_path, name, stage="plan_drafting",
                            blocked=False):
    """Create a repo with a loop that has tokens. Returns (repo, rk, loop_id)."""
    _loop_dir = str(
        Path(__file__).resolve().parent.parent
        / "src" / "gator_command" / "scripts" / "loop"
    )
    if _loop_dir not in sys.path:
        sys.path.insert(0, _loop_dir)
    from session import make_token, save_tokens

    repo = tmp_path / f"repo-{name}"
    loops_dir = repo / ".gator" / "loops"
    loop_id = f"{name}-2026-09-22T10-00-00Z"
    loop_dir = loops_dir / loop_id
    _write_session(loop_dir, _make_session(loop_id, stage=stage,
                                           blocked=blocked))

    tok_d, nonce_d = make_token(loop_id, "draftor")
    tok_r, nonce_r = make_token(loop_id, "reviewer")
    tok_a, nonce_a = make_token(loop_id, "architect")
    save_tokens(loop_dir, {
        "draftor": {"nonce": nonce_d, "token": tok_d},
        "reviewer": {"nonce": nonce_r, "token": tok_r},
        "architect": {"nonce": nonce_a, "token": tok_a},
    })

    rk = _repo_key(repo)
    return repo, rk, loop_id


class TestLoopPrompt:

    def test_prompt_draftor(self, server, tmp_path):
        """Prompt endpoint returns draftor prompt text."""
        repo, rk, loop_id = _setup_loop_with_tokens(
            tmp_path, "prompt-d")
        server.start([{"name": "prompt-d", "path": str(repo),
                       "repo_key": rk}])

        status, data, hdrs = _post(
            server.url,
            f"/api/repo-by-key/{rk}/loops/{loop_id}/prompt",
            {"role": "draftor"})
        assert status == 200
        assert "prompt" in data
        assert "draftor" in data["prompt"].lower()
        assert hdrs.get("Cache-Control") == "no-store"

    def test_prompt_reviewer(self, server, tmp_path):
        """Prompt endpoint returns reviewer prompt text."""
        repo, rk, loop_id = _setup_loop_with_tokens(
            tmp_path, "prompt-r")
        server.start([{"name": "prompt-r", "path": str(repo),
                       "repo_key": rk}])

        status, data, hdrs = _post(
            server.url,
            f"/api/repo-by-key/{rk}/loops/{loop_id}/prompt",
            {"role": "reviewer"})
        assert status == 200
        assert "prompt" in data
        assert hdrs.get("Cache-Control") == "no-store"

    def test_prompt_architect_rejected(self, server, tmp_path):
        """Requesting architect prompt is rejected with 400."""
        repo, rk, loop_id = _setup_loop_with_tokens(
            tmp_path, "prompt-a")
        server.start([{"name": "prompt-a", "path": str(repo),
                       "repo_key": rk}])

        status, data, hdrs = _post(
            server.url,
            f"/api/repo-by-key/{rk}/loops/{loop_id}/prompt",
            {"role": "architect"})
        assert status == 400
        assert hdrs.get("Cache-Control") == "no-store"

    def test_prompt_terminal_loop_rejected(self, server, tmp_path):
        """Prompt for a terminal loop returns 410."""
        repo, rk, loop_id = _setup_loop_with_tokens(
            tmp_path, "prompt-t", stage="plan_approved")
        server.start([{"name": "prompt-t", "path": str(repo),
                       "repo_key": rk}])

        status, data, hdrs = _post(
            server.url,
            f"/api/repo-by-key/{rk}/loops/{loop_id}/prompt",
            {"role": "draftor"})
        assert status == 410
        assert hdrs.get("Cache-Control") == "no-store"

    def test_prompt_no_store_header(self, server, tmp_path):
        """All prompt responses carry Cache-Control: no-store."""
        repo, rk, loop_id = _setup_loop_with_tokens(
            tmp_path, "prompt-cc")
        server.start([{"name": "prompt-cc", "path": str(repo),
                       "repo_key": rk}])

        _, _, hdrs = _post(
            server.url,
            f"/api/repo-by-key/{rk}/loops/{loop_id}/prompt",
            {"role": "draftor"})
        assert hdrs.get("Cache-Control") == "no-store"

    def test_prompt_loop_not_found(self, server, tmp_path):
        """Prompt for nonexistent loop returns 404."""
        repo = tmp_path / "repo-promptnf"
        (repo / ".gator" / "loops").mkdir(parents=True)
        rk = _repo_key(repo)
        server.start([{"name": "promptnf", "path": str(repo),
                       "repo_key": rk}])

        status, data, _ = _post(
            server.url,
            f"/api/repo-by-key/{rk}/loops/fake-loop/prompt",
            {"role": "draftor"})
        assert status == 404


class TestLoopStartCrossRepo:

    def test_start_targets_correct_repo(self, server, tmp_path):
        """Starting a loop creates session under the correct repo."""
        repo_a = tmp_path / "repo-xra"
        (repo_a / ".gator").mkdir(parents=True)
        sketch_a = repo_a / "sketch.md"
        sketch_a.write_text("# A sketch\n", encoding="utf-8")

        repo_b = tmp_path / "repo-xrb"
        (repo_b / ".gator").mkdir(parents=True)

        rk_a = _repo_key(repo_a)
        rk_b = _repo_key(repo_b)
        server.start([
            {"name": "xra", "path": str(repo_a), "repo_key": rk_a},
            {"name": "xrb", "path": str(repo_b), "repo_key": rk_b},
        ])

        status, data, _ = _post(
            server.url,
            f"/api/repo-by-key/{rk_a}/loops/start",
            {"feature": "cross-a", "sketch_path": str(sketch_a)})
        assert status == 201

        loop_id = data["loop_id"]
        assert (repo_a / ".gator" / "loops" / loop_id).is_dir()
        assert not (repo_b / ".gator" / "loops").exists() or \
            not (repo_b / ".gator" / "loops" / loop_id).exists()


class TestLoopStartNumericValidation:

    def test_max_rounds_string_rejected(self, server, tmp_path):
        repo = tmp_path / "repo-numval1"
        (repo / ".gator").mkdir(parents=True)
        sketch = repo / "sketch.md"
        sketch.write_text("# Sketch\n", encoding="utf-8")
        rk = _repo_key(repo)
        server.start([{"name": "numval1", "path": str(repo),
                       "repo_key": rk}])
        status, data, _ = _post(
            server.url, f"/api/repo-by-key/{rk}/loops/start",
            {"feature": "f", "sketch_path": str(sketch),
             "max_rounds": "three"})
        assert status == 400
        assert "max_rounds" in data.get("error", "")

    def test_max_rounds_boolean_rejected(self, server, tmp_path):
        repo = tmp_path / "repo-numval2"
        (repo / ".gator").mkdir(parents=True)
        sketch = repo / "sketch.md"
        sketch.write_text("# Sketch\n", encoding="utf-8")
        rk = _repo_key(repo)
        server.start([{"name": "numval2", "path": str(repo),
                       "repo_key": rk}])
        status, data, _ = _post(
            server.url, f"/api/repo-by-key/{rk}/loops/start",
            {"feature": "f", "sketch_path": str(sketch),
             "max_rounds": True})
        assert status == 400

    def test_max_rounds_zero_rejected(self, server, tmp_path):
        repo = tmp_path / "repo-numval3"
        (repo / ".gator").mkdir(parents=True)
        sketch = repo / "sketch.md"
        sketch.write_text("# Sketch\n", encoding="utf-8")
        rk = _repo_key(repo)
        server.start([{"name": "numval3", "path": str(repo),
                       "repo_key": rk}])
        status, data, _ = _post(
            server.url, f"/api/repo-by-key/{rk}/loops/start",
            {"feature": "f", "sketch_path": str(sketch),
             "max_rounds": 0})
        assert status == 400

    def test_max_rounds_over_limit_rejected(self, server, tmp_path):
        repo = tmp_path / "repo-numval4"
        (repo / ".gator").mkdir(parents=True)
        sketch = repo / "sketch.md"
        sketch.write_text("# Sketch\n", encoding="utf-8")
        rk = _repo_key(repo)
        server.start([{"name": "numval4", "path": str(repo),
                       "repo_key": rk}])
        status, data, _ = _post(
            server.url, f"/api/repo-by-key/{rk}/loops/start",
            {"feature": "f", "sketch_path": str(sketch),
             "max_rounds": 21})
        assert status == 400

    def test_turn_timeout_string_rejected(self, server, tmp_path):
        repo = tmp_path / "repo-numval5"
        (repo / ".gator").mkdir(parents=True)
        sketch = repo / "sketch.md"
        sketch.write_text("# Sketch\n", encoding="utf-8")
        rk = _repo_key(repo)
        server.start([{"name": "numval5", "path": str(repo),
                       "repo_key": rk}])
        status, data, _ = _post(
            server.url, f"/api/repo-by-key/{rk}/loops/start",
            {"feature": "f", "sketch_path": str(sketch),
             "turn_timeout": "fast"})
        assert status == 400
        assert "turn_timeout" in data.get("error", "")

    def test_turn_timeout_too_low_rejected(self, server, tmp_path):
        repo = tmp_path / "repo-numval6"
        (repo / ".gator").mkdir(parents=True)
        sketch = repo / "sketch.md"
        sketch.write_text("# Sketch\n", encoding="utf-8")
        rk = _repo_key(repo)
        server.start([{"name": "numval6", "path": str(repo),
                       "repo_key": rk}])
        status, data, _ = _post(
            server.url, f"/api/repo-by-key/{rk}/loops/start",
            {"feature": "f", "sketch_path": str(sketch),
             "turn_timeout": 10})
        assert status == 400

    def test_turn_timeout_too_high_rejected(self, server, tmp_path):
        repo = tmp_path / "repo-numval7"
        (repo / ".gator").mkdir(parents=True)
        sketch = repo / "sketch.md"
        sketch.write_text("# Sketch\n", encoding="utf-8")
        rk = _repo_key(repo)
        server.start([{"name": "numval7", "path": str(repo),
                       "repo_key": rk}])
        status, data, _ = _post(
            server.url, f"/api/repo-by-key/{rk}/loops/start",
            {"feature": "f", "sketch_path": str(sketch),
             "turn_timeout": 7200})
        assert status == 400

    def test_valid_custom_settings_accepted(self, server, tmp_path):
        repo = tmp_path / "repo-numval8"
        (repo / ".gator").mkdir(parents=True)
        sketch = repo / "sketch.md"
        sketch.write_text("# Sketch\n", encoding="utf-8")
        rk = _repo_key(repo)
        server.start([{"name": "numval8", "path": str(repo),
                       "repo_key": rk}])
        status, data, _ = _post(
            server.url, f"/api/repo-by-key/{rk}/loops/start",
            {"feature": "custom", "sketch_path": str(sketch),
             "max_rounds": 5, "turn_timeout": 600})
        assert status == 201


class TestHostOwnership:

    _LOCK_HOLDER_SCRIPT = '''\
import os, sys
lock_path = sys.argv[1]
fd = os.open(lock_path, os.O_RDWR | os.O_CREAT)
if sys.platform == "win32":
    import msvcrt
    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
else:
    import fcntl
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
sys.stdout.write("locked\\n")
sys.stdout.flush()
sys.stdin.readline()
os.close(fd)
'''

    def test_cross_process_host_lock_not_adopted(self, monkeypatch, tmp_path,
                                                 registry_file):
        """A loop whose host.lock is held by a separate process is not
        adopted by _adopt_orphaned_loops()."""
        import subprocess

        repo = tmp_path / "repo-xproc"
        loops_dir = repo / ".gator" / "loops"
        loop_id = "xproc-2026-09-22T10-00-00Z"
        loop_dir = loops_dir / loop_id
        _write_session(loop_dir, _make_session(loop_id,
                                               stage="plan_drafting"))

        lock_path = str(loop_dir / "host.lock")
        proc = subprocess.Popen(
            [sys.executable, "-c", self._LOCK_HOLDER_SCRIPT, lock_path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True)
        try:
            line = proc.stdout.readline().strip()
            assert line == "locked", f"subprocess did not acquire lock: {line}"

            repo_path = str(Path(str(repo)).resolve())
            _write_registry(registry_file, [
                {"name": "xproc", "path": str(repo),
                 "repo_key": _repo_key(repo)}])
            monkeypatch.setattr(gator_core, "DASHBOARD_REGISTRY",
                                registry_file)
            monkeypatch.setattr(dashboard, "_REGISTRY_REPOS",
                                [{"name": "xproc", "path": str(repo)}])

            dashboard._LOOP_HOSTS.clear()
            dashboard._adopt_orphaned_loops()

            with dashboard._LOOP_HOSTS_LOCK:
                assert (repo_path, loop_id) not in dashboard._LOOP_HOSTS, \
                    "Loop with cross-process held host.lock must not be adopted"
        finally:
            proc.stdin.write("quit\n")
            proc.stdin.flush()
            proc.wait(timeout=5)

    def test_cross_process_start_lock_blocks_dashboard(self, server, tmp_path):
        """A start.lock held by a separate process causes the dashboard
        start endpoint to return 409."""
        import subprocess

        repo = tmp_path / "repo-xstart"
        (repo / ".gator" / "loops").mkdir(parents=True)
        sketch = repo / "sketch.md"
        sketch.write_text("# XProc sketch\n", encoding="utf-8")
        rk = _repo_key(repo)
        server.start([{"name": "xstart", "path": str(repo),
                       "repo_key": rk}])

        lock_path = str(repo / ".gator" / "loops" / "start.lock")
        proc = subprocess.Popen(
            [sys.executable, "-c", self._LOCK_HOLDER_SCRIPT, lock_path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True)
        try:
            line = proc.stdout.readline().strip()
            assert line == "locked"

            status, data, _ = _post(
                server.url, f"/api/repo-by-key/{rk}/loops/start",
                {"feature": "xstart-feat", "sketch_path": str(sketch)})
            assert status == 409, f"Expected 409 with held start.lock, got {status}"
            assert "another start" in data.get("error", "")
        finally:
            proc.stdin.write("quit\n")
            proc.stdin.flush()
            proc.wait(timeout=5)

    def test_start_lock_released_after_success(self, server, tmp_path):
        """After a successful start, start.lock is released and reacquirable."""
        import sys as _sys

        _loop_dir = str(
            Path(__file__).resolve().parent.parent
            / "src" / "gator_command" / "scripts" / "loop"
        )
        if _loop_dir not in _sys.path:
            _sys.path.insert(0, _loop_dir)
        from host import acquire_start_lock, release_start_lock

        repo = tmp_path / "repo-slrel"
        (repo / ".gator").mkdir(parents=True)
        sketch = repo / "sketch.md"
        sketch.write_text("# SL sketch\n", encoding="utf-8")
        rk = _repo_key(repo)
        server.start([{"name": "slrel", "path": str(repo),
                       "repo_key": rk}])

        status, data, _ = _post(
            server.url, f"/api/repo-by-key/{rk}/loops/start",
            {"feature": "slrel-feat", "sketch_path": str(sketch)})
        assert status == 201

        loops_base = repo / ".gator" / "loops"
        fd = acquire_start_lock(loops_base)
        assert fd is not None, "start.lock should be released after success"
        release_start_lock(fd)

    def test_start_lock_released_on_active_conflict(self, server, tmp_path):
        """start.lock is released even when the start fails due to
        an existing active loop (409 path)."""
        import sys as _sys

        _loop_dir = str(
            Path(__file__).resolve().parent.parent
            / "src" / "gator_command" / "scripts" / "loop"
        )
        if _loop_dir not in _sys.path:
            _sys.path.insert(0, _loop_dir)
        from host import acquire_start_lock, release_start_lock

        repo = tmp_path / "repo-slconfl"
        loops_dir = repo / ".gator" / "loops"
        existing_id = "existing-2026-09-22T10-00-00Z"
        _write_session(loops_dir / existing_id,
                       _make_session(existing_id, stage="plan_drafting"))
        sketch = repo / "sketch.md"
        sketch.write_text("# SL sketch\n", encoding="utf-8")
        rk = _repo_key(repo)
        server.start([{"name": "slconfl", "path": str(repo),
                       "repo_key": rk}])

        status, data, _ = _post(
            server.url, f"/api/repo-by-key/{rk}/loops/start",
            {"feature": "slconfl-feat", "sketch_path": str(sketch)})
        assert status == 409

        fd = acquire_start_lock(loops_dir)
        assert fd is not None, "start.lock should be released after 409"
        release_start_lock(fd)

    def test_orphan_terminal_not_adopted(self, monkeypatch, tmp_path,
                                         registry_file):
        """Terminal loops are skipped by the adoption scan."""
        repo = tmp_path / "repo-orphterm"
        loops_dir = repo / ".gator" / "loops"
        loop_id = "orphterm-2026-09-22T10-00-00Z"
        _write_session(loops_dir / loop_id,
                       _make_session(loop_id, stage="plan_approved"))

        repo_path = str(Path(str(repo)).resolve())
        _write_registry(registry_file, [
            {"name": "orphterm", "path": str(repo),
             "repo_key": _repo_key(repo)}])
        monkeypatch.setattr(gator_core, "DASHBOARD_REGISTRY",
                            registry_file)
        monkeypatch.setattr(dashboard, "_REGISTRY_REPOS",
                            [{"name": "orphterm", "path": str(repo)}])

        dashboard._LOOP_HOSTS.clear()
        dashboard._adopt_orphaned_loops()

        with dashboard._LOOP_HOSTS_LOCK:
            assert (repo_path, loop_id) not in dashboard._LOOP_HOSTS

    def test_orphan_active_adopted(self, monkeypatch, tmp_path,
                                   registry_file):
        """An orphaned non-terminal loop is adopted — registry entry exists."""
        import time

        repo = tmp_path / "repo-orphanact"
        loops_dir = repo / ".gator" / "loops"
        loop_id = "orphanact-2026-09-22T10-00-00Z"
        loop_dir = loops_dir / loop_id
        _write_session(loop_dir, _make_session(loop_id,
                                               stage="plan_drafting"))

        repo_path = str(Path(str(repo)).resolve())
        _write_registry(registry_file, [
            {"name": "orphanact", "path": str(repo),
             "repo_key": _repo_key(repo)}])
        monkeypatch.setattr(gator_core, "DASHBOARD_REGISTRY",
                            registry_file)
        monkeypatch.setattr(dashboard, "_REGISTRY_REPOS",
                            [{"name": "orphanact", "path": str(repo)}])

        dashboard._LOOP_HOSTS.clear()
        dashboard._adopt_orphaned_loops()

        time.sleep(0.2)

        with dashboard._LOOP_HOSTS_LOCK:
            entry = dashboard._LOOP_HOSTS.get((repo_path, loop_id))
            assert entry is not None, "Active orphan should be adopted"
            assert entry.host_lock_fd is not None


class TestWatcherLifecycle:

    def test_immediate_exit_cleans_registry(self, monkeypatch, tmp_path):
        """A watcher that exits immediately leaves no stale registry entry
        and releases the host lock fd."""
        import os
        import sys
        import time

        _loop_dir = str(
            Path(__file__).resolve().parent.parent
            / "src" / "gator_command" / "scripts" / "loop"
        )
        if _loop_dir not in sys.path:
            sys.path.insert(0, _loop_dir)
        from host import acquire_host_lock, HOST_LOCK_FILENAME

        repo_path = str(Path(str(tmp_path / "repo-imm")).resolve())
        loop_id = "imm-exit"
        loop_dir = tmp_path / "repo-imm" / ".gator" / "loops" / loop_id
        loop_dir.mkdir(parents=True)
        _write_session(loop_dir, _make_session(loop_id,
                                               stage="plan_approved"))
        _write_events(loop_dir, [
            {"event": "plan_approved", "role": "reviewer",
             "round": 1, "detail": "approved",
             "ts": "2026-09-22T10:05:00+00:00",
             "loop_id": loop_id}])

        fd = acquire_host_lock(loop_dir)
        assert fd is not None

        nonce = "test-nonce-imm"
        t = threading.Thread(
            target=dashboard._run_watcher,
            args=(loop_dir, fd, repo_path, loop_id, nonce),
            daemon=True,
        )
        with dashboard._LOOP_HOSTS_LOCK:
            dashboard._LOOP_HOSTS[(repo_path, loop_id)] = \
                dashboard._HostEntry(t, loop_dir, fd, nonce)
        t.start()
        t.join(timeout=10)
        assert not t.is_alive()

        with dashboard._LOOP_HOSTS_LOCK:
            assert (repo_path, loop_id) not in dashboard._LOOP_HOSTS, \
                "Registry entry should be cleaned up after watcher exit"

        reacquired = acquire_host_lock(loop_dir)
        assert reacquired is not None, \
            "Lock should be released after watcher exit"
        from host import release_host_lock
        release_host_lock(reacquired)

    def test_nonce_mismatch_preserves_replacement(self, tmp_path):
        """A watcher whose nonce no longer matches does not remove the
        replacement entry."""
        import os
        import sys
        import time

        _loop_dir = str(
            Path(__file__).resolve().parent.parent
            / "src" / "gator_command" / "scripts" / "loop"
        )
        if _loop_dir not in sys.path:
            sys.path.insert(0, _loop_dir)
        from host import acquire_host_lock

        repo_path = str(Path(str(tmp_path / "repo-nonce")).resolve())
        loop_id = "nonce-mismatch"
        loop_dir = tmp_path / "repo-nonce" / ".gator" / "loops" / loop_id
        loop_dir.mkdir(parents=True)
        _write_session(loop_dir, _make_session(loop_id,
                                               stage="plan_approved"))
        _write_events(loop_dir, [
            {"event": "plan_approved", "role": "reviewer",
             "round": 1, "detail": "approved",
             "ts": "2026-09-22T10:05:00+00:00",
             "loop_id": loop_id}])

        fd = acquire_host_lock(loop_dir)
        assert fd is not None

        old_nonce = "old-nonce"
        replacement_nonce = "replacement-nonce"

        t = threading.Thread(
            target=dashboard._run_watcher,
            args=(loop_dir, fd, repo_path, loop_id, old_nonce),
            daemon=True,
        )
        with dashboard._LOOP_HOSTS_LOCK:
            dashboard._LOOP_HOSTS[(repo_path, loop_id)] = \
                dashboard._HostEntry(t, loop_dir, fd, replacement_nonce)
        t.start()
        t.join(timeout=10)

        with dashboard._LOOP_HOSTS_LOCK:
            entry = dashboard._LOOP_HOSTS.get((repo_path, loop_id))
            assert entry is not None, \
                "Replacement entry must survive old watcher's cleanup"
            assert entry.entry_nonce == replacement_nonce

        with dashboard._LOOP_HOSTS_LOCK:
            del dashboard._LOOP_HOSTS[(repo_path, loop_id)]


class TestConcurrentStart:

    def test_cross_process_start_lock_serializes(self, tmp_path):
        """Two subprocesses racing to acquire start.lock — exactly one wins,
        the other fails, proving cross-process exclusion."""
        import subprocess

        loops_base = tmp_path / "repo-conc2" / ".gator" / "loops"
        loops_base.mkdir(parents=True)
        lock_path = str(loops_base / "start.lock")

        script = '''\
import os, sys
lock_path = sys.argv[1]
fd = os.open(lock_path, os.O_RDWR | os.O_CREAT)
if sys.platform == "win32":
    import msvcrt
    try:
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        print("acquired")
    except (OSError, IOError):
        print("failed")
        os.close(fd)
        sys.exit(0)
else:
    import fcntl
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        print("acquired")
    except (OSError, IOError):
        print("failed")
        os.close(fd)
        sys.exit(0)
sys.stdout.flush()
sys.stdin.readline()
os.close(fd)
'''
        p1 = subprocess.Popen(
            [sys.executable, "-c", script, lock_path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        r1 = p1.stdout.readline().strip()
        assert r1 == "acquired"

        p2 = subprocess.Popen(
            [sys.executable, "-c", script, lock_path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        r2 = p2.stdout.readline().strip()
        assert r2 == "failed", \
            "Second process must fail to acquire the lock"

        p1.stdin.write("quit\n")
        p1.stdin.flush()
        p1.wait(timeout=5)
        p2.wait(timeout=5)


class TestArchitectControls:

    # -- pause ---------------------------------------------------------------

    def test_pause_active_loop(self, server, tmp_path):
        """Pause an active loop succeeds."""
        repo, rk, loop_id = _setup_loop_with_tokens(
            tmp_path, "ctrl-pause", stage="plan_drafting")
        server.start([{"name": "ctrl-pause", "path": str(repo),
                       "repo_key": rk}])
        status, data, _ = _post(
            server.url,
            f"/api/repo-by-key/{rk}/loops/{loop_id}/pause",
            {"message": "taking a break"})
        assert status == 200
        assert data.get("ok") is True

        st, sess = _get(server.url,
                        f"/api/repo-by-key/{rk}/loops/{loop_id}/status")
        assert sess["status"]["stage"] == "paused_by_architect"

    def test_pause_terminal_rejected(self, server, tmp_path):
        """Pausing a terminal loop returns 409."""
        repo, rk, loop_id = _setup_loop_with_tokens(
            tmp_path, "ctrl-pause-term", stage="plan_approved")
        server.start([{"name": "ctrl-pause-term", "path": str(repo),
                       "repo_key": rk}])
        status, data, _ = _post(
            server.url,
            f"/api/repo-by-key/{rk}/loops/{loop_id}/pause", {})
        assert status == 409

    def test_pause_without_message(self, server, tmp_path):
        """Pause with no message succeeds."""
        repo, rk, loop_id = _setup_loop_with_tokens(
            tmp_path, "ctrl-pause-nm", stage="plan_drafting")
        server.start([{"name": "ctrl-pause-nm", "path": str(repo),
                       "repo_key": rk}])
        status, data, _ = _post(
            server.url,
            f"/api/repo-by-key/{rk}/loops/{loop_id}/pause", {})
        assert status == 200

    # -- interject -----------------------------------------------------------

    def test_interject_with_message(self, server, tmp_path):
        """Interject delivers guidance without pausing."""
        repo, rk, loop_id = _setup_loop_with_tokens(
            tmp_path, "ctrl-interj", stage="plan_drafting")
        server.start([{"name": "ctrl-interj", "path": str(repo),
                       "repo_key": rk}])
        status, data, _ = _post(
            server.url,
            f"/api/repo-by-key/{rk}/loops/{loop_id}/interject",
            {"message": "consider edge cases"})
        assert status == 200
        assert data.get("ok") is True

        st, sess = _get(server.url,
                        f"/api/repo-by-key/{rk}/loops/{loop_id}/status")
        assert sess["status"]["stage"] == "plan_drafting"

    def test_interject_without_message_rejected(self, server, tmp_path):
        """Interject requires a message."""
        repo, rk, loop_id = _setup_loop_with_tokens(
            tmp_path, "ctrl-interj-nm", stage="plan_drafting")
        server.start([{"name": "ctrl-interj-nm", "path": str(repo),
                       "repo_key": rk}])
        status, data, _ = _post(
            server.url,
            f"/api/repo-by-key/{rk}/loops/{loop_id}/interject", {})
        assert status == 400
        assert "message" in data.get("error", "")

    def test_interject_terminal_rejected(self, server, tmp_path):
        """Interject on terminal loop returns 409."""
        repo, rk, loop_id = _setup_loop_with_tokens(
            tmp_path, "ctrl-interj-term", stage="plan_approved")
        server.start([{"name": "ctrl-interj-term", "path": str(repo),
                       "repo_key": rk}])
        status, data, _ = _post(
            server.url,
            f"/api/repo-by-key/{rk}/loops/{loop_id}/interject",
            {"message": "too late"})
        assert status == 409

    # -- unblock -------------------------------------------------------------

    def test_unblock_paused_loop(self, server, tmp_path):
        """Unblock a paused loop succeeds."""
        repo, rk, loop_id = _setup_loop_with_tokens(
            tmp_path, "ctrl-unbl", stage="paused_by_architect",
            blocked=True)
        server.start([{"name": "ctrl-unbl", "path": str(repo),
                       "repo_key": rk}])
        status, data, _ = _post(
            server.url,
            f"/api/repo-by-key/{rk}/loops/{loop_id}/unblock",
            {"message": "resolved"})
        assert status == 200
        assert data.get("ok") is True

        st, sess = _get(server.url,
                        f"/api/repo-by-key/{rk}/loops/{loop_id}/status")
        assert sess["status"]["stage"] in ("plan_drafting", "plan_review",
                                           "plan_revision")

    def test_unblock_blocked_on_architect(self, server, tmp_path):
        """Unblock a loop blocked_on_architect succeeds."""
        repo, rk, loop_id = _setup_loop_with_tokens(
            tmp_path, "ctrl-unbl-boa", stage="blocked_on_architect",
            blocked=True)
        server.start([{"name": "ctrl-unbl-boa", "path": str(repo),
                       "repo_key": rk}])
        status, data, _ = _post(
            server.url,
            f"/api/repo-by-key/{rk}/loops/{loop_id}/unblock",
            {"message": "decision made"})
        assert status == 200

    def test_unblock_active_rejected(self, server, tmp_path):
        """Unblock an active (non-paused) loop returns 409."""
        repo, rk, loop_id = _setup_loop_with_tokens(
            tmp_path, "ctrl-unbl-act", stage="plan_drafting")
        server.start([{"name": "ctrl-unbl-act", "path": str(repo),
                       "repo_key": rk}])
        status, data, _ = _post(
            server.url,
            f"/api/repo-by-key/{rk}/loops/{loop_id}/unblock", {})
        assert status == 409

    # -- end -----------------------------------------------------------------

    def test_end_active_loop(self, server, tmp_path):
        """End an active loop succeeds."""
        repo, rk, loop_id = _setup_loop_with_tokens(
            tmp_path, "ctrl-end", stage="plan_drafting")
        server.start([{"name": "ctrl-end", "path": str(repo),
                       "repo_key": rk}])
        status, data, _ = _post(
            server.url,
            f"/api/repo-by-key/{rk}/loops/{loop_id}/end",
            {"reason": "scope changed"})
        assert status == 200
        assert data.get("ok") is True

        st, sess = _get(server.url,
                        f"/api/repo-by-key/{rk}/loops/{loop_id}/status")
        assert sess["status"]["stage"] == "ended_by_architect"

    def test_end_paused_loop(self, server, tmp_path):
        """End a paused loop succeeds."""
        repo, rk, loop_id = _setup_loop_with_tokens(
            tmp_path, "ctrl-end-psd", stage="paused_by_architect",
            blocked=True)
        server.start([{"name": "ctrl-end-psd", "path": str(repo),
                       "repo_key": rk}])
        status, data, _ = _post(
            server.url,
            f"/api/repo-by-key/{rk}/loops/{loop_id}/end", {})
        assert status == 200

        st, sess = _get(server.url,
                        f"/api/repo-by-key/{rk}/loops/{loop_id}/status")
        assert sess["status"]["stage"] == "ended_by_architect"

    def test_end_terminal_rejected(self, server, tmp_path):
        """End on terminal loop returns 409."""
        repo, rk, loop_id = _setup_loop_with_tokens(
            tmp_path, "ctrl-end-term", stage="plan_approved")
        server.start([{"name": "ctrl-end-term", "path": str(repo),
                       "repo_key": rk}])
        status, data, _ = _post(
            server.url,
            f"/api/repo-by-key/{rk}/loops/{loop_id}/end",
            {"reason": "too late"})
        assert status == 409

    # -- cross-cutting -------------------------------------------------------

    def test_control_loop_not_found(self, server, tmp_path):
        """Control on non-existent loop returns 404."""
        repo = tmp_path / "repo-ctrl-nf"
        (repo / ".gator" / "loops").mkdir(parents=True)
        rk = _repo_key(repo)
        server.start([{"name": "ctrl-nf", "path": str(repo),
                       "repo_key": rk}])
        status, data, _ = _post(
            server.url,
            f"/api/repo-by-key/{rk}/loops/nonexistent/pause", {})
        assert status == 404

    def test_control_malicious_loop_id(self, server, tmp_path):
        """Traversal loop_id is rejected."""
        repo = tmp_path / "repo-ctrl-mal"
        (repo / ".gator" / "loops").mkdir(parents=True)
        rk = _repo_key(repo)
        server.start([{"name": "ctrl-mal", "path": str(repo),
                       "repo_key": rk}])
        status, data, _ = _post(
            server.url,
            f"/api/repo-by-key/{rk}/loops/..%2f..%2fetc/pause", {})
        assert status == 400


class TestArchitectControlsErrorPayload:
    """Control failures return structured error JSON the UI can display."""

    def test_terminal_rejection_includes_error_message(self, server, tmp_path):
        """A 409 response for a terminal loop carries an 'error' field."""
        repo, rk, loop_id = _setup_loop_with_tokens(
            tmp_path, "err-payload", stage="plan_approved")
        server.start([{"name": "err-payload", "path": str(repo),
                       "repo_key": rk}])
        status, data, _ = _post(
            server.url,
            f"/api/repo-by-key/{rk}/loops/{loop_id}/pause", {})
        assert status == 409
        assert "error" in data
        assert len(data["error"]) > 0


class TestArchitectControlsCrossRepo:
    """Multi-repo control isolation — control one, verify the other."""

    def test_pause_one_repo_other_unaffected(self, server, tmp_path):
        """Pausing a loop in repo-A does not affect repo-B."""
        repo_a, rk_a, lid_a = _setup_loop_with_tokens(
            tmp_path, "cross-a", stage="plan_drafting")
        repo_b, rk_b, lid_b = _setup_loop_with_tokens(
            tmp_path, "cross-b", stage="plan_drafting")
        server.start([
            {"name": "cross-a", "path": str(repo_a), "repo_key": rk_a},
            {"name": "cross-b", "path": str(repo_b), "repo_key": rk_b},
        ])

        status, data, _ = _post(
            server.url,
            f"/api/repo-by-key/{rk_a}/loops/{lid_a}/pause",
            {"message": "isolating"})
        assert status == 200

        st_a, sess_a = _get(
            server.url,
            f"/api/repo-by-key/{rk_a}/loops/{lid_a}/status")
        assert sess_a["status"]["stage"] == "paused_by_architect"

        st_b, sess_b = _get(
            server.url,
            f"/api/repo-by-key/{rk_b}/loops/{lid_b}/status")
        assert sess_b["status"]["stage"] == "plan_drafting"
