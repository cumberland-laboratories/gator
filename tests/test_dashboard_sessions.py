"""
Tests for the /api/audit/sessions dashboard endpoint logic.

Tests _resolve_audit_sessions() — the extracted, testable function
that handles repo-hash resolution, fleet routing, and refresh propagation.
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from conftest import load_script

dashboard = load_script("gator-dashboard")
agg = load_script("gator-session-aggregator")

# Import the extracted data module directly for accurate monkeypatching.
# After the dashboard split, the real function bodies live in dashboard.data,
# not in the gator-dashboard.py aliases.
import dashboard.data as dashboard_data


def _make_summary(repo="test-repo", session_id="s1"):
    return {
        "schema": "gator-session-summary-v1",
        "session_id": session_id,
        "repo": repo,
        "repo_key": "abc123",
        "started_at": "2026-06-19T22:00:00Z",
        "ended_at": "2026-06-19T23:00:00Z",
        "goal": "Test goal",
        "commit_count": 1,
        "commits": [{"commit": "aaa", "short_commit": "aaa",
                      "intent": "Test", "change_type": "fix"}],
    }


class TestResolveAuditSessions:
    def test_fleet_mode(self, tmp_path):
        """fleet=true calls get_fleet_summaries."""
        repo = tmp_path / "repo1"
        snippet_dir = repo / ".gator" / "session-snippets"
        snippet_dir.mkdir(parents=True)
        snippet = {
            "schema": "gator-session-snippet-v2",
            "session_id": "s1", "repo": "repo1",
            "commit": "aaa", "short_commit": "aaa",
            "intent": "Test", "change_type": "fix",
            "significance": "routine", "branch": "main",
            "files_touched": ["a.py"], "decision_tags": ["fix"],
            "notes": [], "architect": "AG",
            "vendor_inferred": "anthropic", "model_inferred": "claude",
            "agent": "claude", "started_at": "2026-06-19T22:00:00Z",
            "ended_at": "2026-06-19T23:00:00Z",
            "transcript_session_id": None, "transcript_ref": None,
            "machine_label": "test", "machine_id": "test",
            "charter_changed": False,
        }
        (snippet_dir / "s.json").write_text(json.dumps(snippet))

        registry = tmp_path / "reg.json"
        registry.write_text(json.dumps({
            "schema": "gator-dashboard-registry-v1",
            "repos": [{"name": "repo1", "path": str(repo)}],
        }))

        result = dashboard._resolve_audit_sessions(
            fleet=True, registry_repos=[{"name": "repo1", "path": str(repo)}],
        )
        assert result["status"] == 200
        assert isinstance(result["data"], list)

    def test_repo_hash_resolution(self, tmp_path):
        """repo=<hash> resolves to the correct repo via session_cache_key."""
        repo = tmp_path / "myrepo"
        snippet_dir = repo / ".gator" / "session-snippets"
        snippet_dir.mkdir(parents=True)
        snippet = {
            "schema": "gator-session-snippet-v2",
            "session_id": "s1", "repo": "myrepo",
            "commit": "bbb", "short_commit": "bbb",
            "intent": "Work", "change_type": "feature",
            "significance": "routine", "branch": "main",
            "files_touched": ["b.py"], "decision_tags": [],
            "notes": [], "architect": "",
            "vendor_inferred": "anthropic", "model_inferred": "claude",
            "agent": "claude", "started_at": "2026-06-20T10:00:00Z",
            "ended_at": "2026-06-20T11:00:00Z",
            "transcript_session_id": None, "transcript_ref": None,
            "machine_label": "test", "machine_id": "test",
            "charter_changed": False,
        }
        (snippet_dir / "s.json").write_text(json.dumps(snippet))

        repo_hash = agg.session_cache_key(str(repo))
        registry_repos = [{"name": "myrepo", "path": str(repo)}]

        result = dashboard._resolve_audit_sessions(
            repo_hash=repo_hash, registry_repos=registry_repos,
        )
        assert result["status"] == 200
        assert isinstance(result["data"], list)
        assert len(result["data"]) == 1
        assert result["data"][0]["repo"] == "myrepo"

    def test_repo_hash_not_found(self):
        """Unknown repo hash returns 404."""
        result = dashboard._resolve_audit_sessions(
            repo_hash="nonexistent0", registry_repos=[],
        )
        assert result["status"] == 404
        assert "error" in result["data"]

    def test_refresh_propagation(self, tmp_path):
        """refresh=true is passed through to aggregator."""
        repo = tmp_path / "repo"
        snippet_dir = repo / ".gator" / "session-snippets"
        snippet_dir.mkdir(parents=True)
        snippet = {
            "schema": "gator-session-snippet-v2",
            "session_id": "s1", "repo": "repo",
            "commit": "ccc", "short_commit": "ccc",
            "intent": "Init", "change_type": "feature",
            "significance": "routine", "branch": "main",
            "files_touched": [], "decision_tags": [],
            "notes": [], "architect": "",
            "vendor_inferred": "anthropic", "model_inferred": "claude",
            "agent": "claude", "started_at": "2026-06-20T10:00:00Z",
            "ended_at": "2026-06-20T11:00:00Z",
            "transcript_session_id": None, "transcript_ref": None,
            "machine_label": "test", "machine_id": "test",
            "charter_changed": False,
        }
        (snippet_dir / "s.json").write_text(json.dumps(snippet))

        repo_hash = agg.session_cache_key(str(repo))
        registry_repos = [{"name": "repo", "path": str(repo)}]

        # First call populates cache
        r1 = dashboard._resolve_audit_sessions(
            repo_hash=repo_hash, registry_repos=registry_repos,
        )
        gen1 = r1["data"][0]["generated_at"]

        # Tamper cache
        cpath = agg.cache_dir(str(repo))
        for f in cpath.glob("*.json"):
            if f.name == "_repo.json":
                continue
            data = json.loads(f.read_text())
            data["generated_at"] = "1999-01-01T00:00:00Z"
            f.write_text(json.dumps(data))

        # Without refresh — returns tampered cache
        r2 = dashboard._resolve_audit_sessions(
            repo_hash=repo_hash, registry_repos=registry_repos,
        )
        assert r2["data"][0]["generated_at"] == "1999-01-01T00:00:00Z"

        # With refresh — regenerates
        r3 = dashboard._resolve_audit_sessions(
            repo_hash=repo_hash, registry_repos=registry_repos, refresh=True,
        )
        assert r3["data"][0]["generated_at"] != "1999-01-01T00:00:00Z"

    def test_default_returns_fleet(self, tmp_path):
        """No repo or fleet param defaults to fleet summaries."""
        result = dashboard._resolve_audit_sessions(
            registry_repos=[],
        )
        assert result["status"] == 200
        assert isinstance(result["data"], list)


class TestInjectRepoKeys:
    def test_adds_repo_key_to_fleet_repos(self, tmp_path):
        """_inject_repo_keys adds repo_key to repos that have a path."""
        repo = tmp_path / "myrepo"
        repo.mkdir()
        fast_data = {
            "fleet": {
                "repos": [
                    {"name": "myrepo", "path": str(repo)},
                ]
            }
        }
        result = dashboard._inject_repo_keys(fast_data)
        repos = result["fleet"]["repos"]
        assert repos[0]["repo_key"] == agg.session_cache_key(str(repo))

    def test_skips_repos_already_keyed(self, tmp_path):
        """_inject_repo_keys does not overwrite existing repo_key."""
        repo = tmp_path / "myrepo"
        repo.mkdir()
        fast_data = {
            "fleet": {
                "repos": [
                    {"name": "myrepo", "path": str(repo), "repo_key": "existing"},
                ]
            }
        }
        result = dashboard._inject_repo_keys(fast_data)
        assert result["fleet"]["repos"][0]["repo_key"] == "existing"

    def test_handles_empty_path(self):
        """_inject_repo_keys produces empty repo_key for repos with no path."""
        fast_data = {
            "fleet": {
                "repos": [
                    {"name": "no-path", "path": ""},
                ]
            }
        }
        result = dashboard._inject_repo_keys(fast_data)
        assert result["fleet"]["repos"][0]["repo_key"] == ""

    def test_handles_standalone_repos_key(self, tmp_path):
        """_inject_repo_keys works with standalone data shape (repos at top level)."""
        repo = tmp_path / "standalone-repo"
        repo.mkdir()
        fast_data = {
            "standalone": True,
            "repos": [
                {"name": "standalone-repo", "path": str(repo)},
            ]
        }
        result = dashboard._inject_repo_keys(fast_data)
        repos = result["repos"]
        assert repos[0]["repo_key"] == agg.session_cache_key(str(repo))

    # test_command_post_entry_gets_keyed removed — inject_command_post() retired in v1.9.1


class TestDashboardUpdateEndpoint:
    """Tests for POST /api/repo/<name>/update (Stage 1 of retire-gator-install plan).

    Exercises resolve_repo_update() — the extracted testable helper called by
    the endpoint handler. Verifies that the endpoint now invokes gator-update
    (not gatorize) and pre-checks for a .gator/ directory.
    """

    def _make_fixture(self, tmp_path, gatorized=True, accessible=True):
        repo = tmp_path / "myrepo"
        repo.mkdir()
        if gatorized:
            (repo / ".gator").mkdir()
        registry_repos = [{"name": "myrepo", "path": str(repo)}]
        fleet_data = {
            "repos": [
                {"name": "myrepo", "path": str(repo), "accessible": accessible},
            ],
        }
        return repo, registry_repos, fleet_data

    def test_endpoint_invokes_gator_update_not_gatorize(self, tmp_path):
        """Regression guard: endpoint runs gator-update, never gatorize.

        Stage 1 of the retire-gator-install plan (2026-07-30). The prior
        behavior invoked gatorize.py which silently switched to a
        gator-install branch.
        """
        repo, registry_repos, fleet_data = self._make_fixture(tmp_path)
        calls = []

        def fake_run_text(*args, **kwargs):
            calls.append((args, kwargs))
            return ("updated", "", 0)

        result = dashboard_data.resolve_repo_update(
            "myrepo",
            registry_repos=registry_repos,
            fleet_data=fleet_data,
            run_text_fn=fake_run_text,
        )
        assert result["status"] == 200
        assert len(calls) == 1
        args, kwargs = calls[0]
        assert args[0] == "gator-update"
        assert "gatorize" not in args
        # Pass repo path via --path (gator-update has no positional arg)
        assert "--path" in args
        path_idx = args.index("--path")
        assert args[path_idx + 1] == str(repo)

    def test_missing_gator_dir_returns_400(self, tmp_path):
        """Ungatorized repo (no .gator/) returns HTTP 400 with a message
        pointing at the Gatorize button.
        """
        repo, registry_repos, fleet_data = self._make_fixture(
            tmp_path, gatorized=False,
        )

        def fake_run_text(*args, **kwargs):
            raise AssertionError("run_text must not be called for ungatorized repos")

        result = dashboard_data.resolve_repo_update(
            "myrepo",
            registry_repos=registry_repos,
            fleet_data=fleet_data,
            run_text_fn=fake_run_text,
        )
        assert result["status"] == 400
        assert "not gatorized" in result["data"]["error"]
        assert "Gatorize button" in result["data"]["error"]

    def test_happy_path_returns_200_with_output_payload(self, tmp_path):
        """Governed repo returns HTTP 200 with the {status, output, exit_code}
        payload shape unchanged from prior behavior.
        """
        repo, registry_repos, fleet_data = self._make_fixture(tmp_path)

        def fake_run_text(*args, **kwargs):
            return ("Everything is current.", "", 0)

        result = dashboard_data.resolve_repo_update(
            "myrepo",
            registry_repos=registry_repos,
            fleet_data=fleet_data,
            run_text_fn=fake_run_text,
        )
        assert result["status"] == 200
        assert result["data"] == {
            "status": "ok",
            "output": "Everything is current.",
            "exit_code": 0,
        }

    def test_nonzero_exit_reports_error_status(self, tmp_path):
        """Failed gator-update returns status=error and preserves exit code."""
        repo, registry_repos, fleet_data = self._make_fixture(tmp_path)

        def fake_run_text(*args, **kwargs):
            return ("", "boom", 2)

        result = dashboard_data.resolve_repo_update(
            "myrepo",
            registry_repos=registry_repos,
            fleet_data=fleet_data,
            run_text_fn=fake_run_text,
        )
        assert result["status"] == 200
        assert result["data"] == {
            "status": "error",
            "output": "boom",
            "exit_code": 2,
        }

    def test_repo_not_in_registry_returns_404(self, tmp_path):
        """Unknown repo name (not in registry, not in fleet data) returns 404."""
        result = dashboard_data.resolve_repo_update(
            "nonexistent",
            registry_repos=[],
            fleet_data={"repos": []},
        )
        assert result["status"] == 404
        assert "not found" in result["data"]["error"]

    def test_empty_repo_name_returns_400(self):
        """Empty repo name returns 400."""
        result = dashboard_data.resolve_repo_update(
            "",
            registry_repos=[],
            fleet_data={"repos": []},
        )
        assert result["status"] == 400


class TestDashboardGatorizeEndpoint:
    """Tests for POST /api/repo/<name>/gatorize (Stage 3 fold-in of the
    retire-gator-install plan). Ungoverned-repo install path — parallels
    TestDashboardUpdateEndpoint's shape.
    """

    def _make_fixture(self, tmp_path, gatorized=False, accessible=True):
        repo = tmp_path / "myrepo"
        repo.mkdir()
        if gatorized:
            (repo / ".gator").mkdir()
        registry_repos = [{"name": "myrepo", "path": str(repo)}]
        fleet_data = {
            "repos": [
                {"name": "myrepo", "path": str(repo), "accessible": accessible},
            ],
        }
        return repo, registry_repos, fleet_data

    def test_endpoint_invokes_gatorize_with_yes(self, tmp_path):
        """gatorize is invoked with --yes and the repo path."""
        repo, registry_repos, fleet_data = self._make_fixture(tmp_path)
        calls = []

        def fake_run_text(*args, **kwargs):
            calls.append((args, kwargs))
            return ("installed", "", 0)

        result = dashboard_data.resolve_repo_gatorize(
            "myrepo",
            registry_repos=registry_repos,
            fleet_data=fleet_data,
            run_text_fn=fake_run_text,
        )
        assert result["status"] == 200
        assert len(calls) == 1
        args, _ = calls[0]
        assert args[0] == "gatorize"
        assert "--yes" in args
        assert str(repo) in args

    def test_already_gatorized_returns_400(self, tmp_path):
        """Governed repo (has .gator/) deflects to Update button with HTTP 400."""
        repo, registry_repos, fleet_data = self._make_fixture(
            tmp_path, gatorized=True,
        )

        def fake_run_text(*args, **kwargs):
            raise AssertionError("run_text must not be called for gatorized repos")

        result = dashboard_data.resolve_repo_gatorize(
            "myrepo",
            registry_repos=registry_repos,
            fleet_data=fleet_data,
            run_text_fn=fake_run_text,
        )
        assert result["status"] == 400
        assert "already gatorized" in result["data"]["error"]
        assert "Update button" in result["data"]["error"]

    def test_happy_path_returns_200_with_output_payload(self, tmp_path):
        """Ungoverned repo returns HTTP 200 + {status, output, exit_code}."""
        repo, registry_repos, fleet_data = self._make_fixture(tmp_path)

        def fake_run_text(*args, **kwargs):
            return ("Gatorized: myrepo", "", 0)

        result = dashboard_data.resolve_repo_gatorize(
            "myrepo",
            registry_repos=registry_repos,
            fleet_data=fleet_data,
            run_text_fn=fake_run_text,
        )
        assert result["status"] == 200
        assert result["data"] == {
            "status": "ok",
            "output": "Gatorized: myrepo",
            "exit_code": 0,
        }

    def test_nonzero_exit_reports_error_status(self, tmp_path):
        """Failed gatorize returns status=error and preserves exit code."""
        repo, registry_repos, fleet_data = self._make_fixture(tmp_path)

        def fake_run_text(*args, **kwargs):
            return ("", "dirty tree", 1)

        result = dashboard_data.resolve_repo_gatorize(
            "myrepo",
            registry_repos=registry_repos,
            fleet_data=fleet_data,
            run_text_fn=fake_run_text,
        )
        assert result["status"] == 200
        assert result["data"] == {
            "status": "error",
            "output": "dirty tree",
            "exit_code": 1,
        }

    def test_repo_not_in_registry_returns_404(self):
        """Unknown repo name returns 404."""
        result = dashboard_data.resolve_repo_gatorize(
            "nonexistent",
            registry_repos=[],
            fleet_data={"repos": []},
        )
        assert result["status"] == 404

    def test_empty_repo_name_returns_400(self):
        """Empty repo name returns 400."""
        result = dashboard_data.resolve_repo_gatorize(
            "",
            registry_repos=[],
            fleet_data={"repos": []},
        )
        assert result["status"] == 400


class TestResolveDiscoveryRoots:
    """resolve_discovery_roots() honors GATOR_DASHBOARD_DISCOVERY_ROOTS env
    var override, falls back to the default home-relative set when unset.
    Non-existent paths are filtered silently.

    Motivation: the Dashboard's Add Repository modal auto-discovers Git
    repos under a hardcoded set of common home-relative directories. That
    scoops up the user's real fleet even when they want to demo the
    discovery flow with an isolated set (e.g. for screenshot capture).
    The env var provides an exclusive override — when set, its paths are
    the ONLY roots scanned.
    """

    def test_defaults_when_env_var_unset(self, monkeypatch):
        """No env var → returns the DEFAULT_DISCOVERY_ROOTS home-relatives.

        We can't assert exact values (depends on which of the six directories
        actually exist on the test machine's home) — instead assert that any
        returned path IS one of the documented defaults.
        """
        monkeypatch.delenv("GATOR_DASHBOARD_DISCOVERY_ROOTS", raising=False)
        result = dashboard_data.resolve_discovery_roots()
        home = Path.home()
        default_names = set(dashboard_data.DEFAULT_DISCOVERY_ROOTS)
        for path in result:
            assert path.parent == home
            assert path.name in default_names

    def test_env_var_single_path(self, tmp_path, monkeypatch):
        """Single-path env var → that path becomes the only root."""
        monkeypatch.setenv(
            "GATOR_DASHBOARD_DISCOVERY_ROOTS", str(tmp_path),
        )
        result = dashboard_data.resolve_discovery_roots()
        assert result == [tmp_path]

    def test_env_var_multi_path(self, tmp_path, monkeypatch):
        """Multi-path env var (os.pathsep separated) → all listed paths."""
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()
        monkeypatch.setenv(
            "GATOR_DASHBOARD_DISCOVERY_ROOTS",
            f"{a}{os.pathsep}{b}",
        )
        result = dashboard_data.resolve_discovery_roots()
        assert set(result) == {a, b}

    def test_env_var_filters_nonexistent(self, tmp_path, monkeypatch):
        """Paths in the env var that don't exist as directories are filtered."""
        real = tmp_path / "real"
        real.mkdir()
        fake = tmp_path / "does-not-exist"
        monkeypatch.setenv(
            "GATOR_DASHBOARD_DISCOVERY_ROOTS",
            f"{real}{os.pathsep}{fake}",
        )
        result = dashboard_data.resolve_discovery_roots()
        assert result == [real]

    def test_env_var_empty_falls_back_to_defaults(self, monkeypatch):
        """Empty-string env var → treated as unset, defaults resume.

        Regression guard: an env var accidentally cleared to "" must NOT
        result in an empty root list (which would silently kill discovery).
        """
        monkeypatch.setenv("GATOR_DASHBOARD_DISCOVERY_ROOTS", "")
        result = dashboard_data.resolve_discovery_roots()
        home = Path.home()
        default_names = set(dashboard_data.DEFAULT_DISCOVERY_ROOTS)
        # Same shape as default case
        for path in result:
            assert path.parent == home
            assert path.name in default_names

    def test_env_var_whitespace_only_falls_back(self, monkeypatch):
        """Whitespace-only env var → treated as unset."""
        monkeypatch.setenv("GATOR_DASHBOARD_DISCOVERY_ROOTS", "   \t  ")
        result = dashboard_data.resolve_discovery_roots()
        home = Path.home()
        default_names = set(dashboard_data.DEFAULT_DISCOVERY_ROOTS)
        for path in result:
            assert path.parent == home
            assert path.name in default_names

    def test_env_var_expands_tilde(self, monkeypatch):
        """Tilde in env var expands to $HOME per entry."""
        monkeypatch.setenv("GATOR_DASHBOARD_DISCOVERY_ROOTS", "~")
        result = dashboard_data.resolve_discovery_roots()
        assert result == [Path.home()]
