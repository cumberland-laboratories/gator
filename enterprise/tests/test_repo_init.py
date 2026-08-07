"""Regression tests for repo_init.py — Finding #3 from the 2026-08-06
Enterprise Local Bring-Up (Phase 5).

Finding: `gator-enterprise repo init --mode evidence_only <path>` for a
repo that isn't yet tracked by any git provider silently fell through to
strict at commit time. Root cause: the requested mode was only registered
server-side (which no-ops for unknown repos), never written locally where
the global hook wrapper reads it. Fix: write local hook-policy.json intent
entry FIRST, regardless of server-side registration outcome. Sync merges
non-destructively (see test_activate_hooks.py::TestSyncMerge).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# Ensure gator_enterprise_cli is importable from source (same pattern as
# test_vendor_hooks.py, test_activate_hooks.py).
ENTERPRISE_CLI_ROOT = Path(__file__).resolve().parent.parent / "enterprise-cli"
if str(ENTERPRISE_CLI_ROOT) not in sys.path:
    sys.path.insert(0, str(ENTERPRISE_CLI_ROOT))

from gator_enterprise_cli.commands.repo_init import (
    _register_hook_policy,
    _write_local_hook_policy_intent,
)


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Redirect Path.home() to tmp_path — same pattern as
    test_activate_hooks.py::isolated_home. Kept local to this file so
    the test files don't have to share a conftest."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


class _FakeRegistrationClient:
    """Records GET/PUT calls. Returns configurable repo list from GET
    /api/v1/repos so tests can simulate 'repo not tracked yet' vs 'repo
    known to server'."""

    def __init__(self, repos=None):
        self._repos = repos if repos is not None else []
        self.gets = []
        self.puts = []

    def get(self, path):
        self.gets.append(path)
        if path == "/api/v1/repos":
            return self._repos
        return {}

    def put(self, path, json=None):
        self.puts.append((path, json))
        return {}


class TestWriteLocalHookPolicyIntent:
    """Core Finding #3 fix: intent is written to local hook-policy.json
    regardless of server-side registration outcome."""

    def _read_policy(self, home):
        return json.loads(
            (home / ".gator" / "enterprise" / "hook-policy.json")
            .read_text(encoding="utf-8")
        )

    def test_writes_new_policy_file_when_missing(self, isolated_home):
        _write_local_hook_policy_intent("local/sandbox", "evidence_only")
        policy = self._read_policy(isolated_home)
        assert policy == {"local/sandbox": {"mode": "evidence_only"}}

    def test_merges_with_existing_entries(self, isolated_home):
        """Existing entries for OTHER repos are preserved."""
        policy_path = (
            isolated_home / ".gator" / "enterprise" / "hook-policy.json"
        )
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        policy_path.write_text(
            json.dumps({"github.com/o/r": {"mode": "strict"}}),
            encoding="utf-8",
        )

        _write_local_hook_policy_intent("local/sandbox", "evidence_only")

        policy = self._read_policy(isolated_home)
        assert policy == {
            "github.com/o/r": {"mode": "strict"},
            "local/sandbox": {"mode": "evidence_only"},
        }

    def test_updates_own_entry_on_repeat(self, isolated_home):
        _write_local_hook_policy_intent("local/sandbox", "evidence_only")
        _write_local_hook_policy_intent("local/sandbox", "warning")
        policy = self._read_policy(isolated_home)
        assert policy == {"local/sandbox": {"mode": "warning"}}

    def test_recovers_from_corrupt_existing_file(self, isolated_home):
        """A corrupt hook-policy.json shouldn't block the intent write."""
        policy_path = (
            isolated_home / ".gator" / "enterprise" / "hook-policy.json"
        )
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        policy_path.write_text("{ this is not valid json", encoding="utf-8")

        _write_local_hook_policy_intent("local/sandbox", "evidence_only")

        policy = self._read_policy(isolated_home)
        assert policy == {"local/sandbox": {"mode": "evidence_only"}}


class TestRegisterHookPolicy:
    """Verifies the server-side registration attempt reports its outcome
    truthfully (returns True on success, False on 'repo not tracked' or
    errors) so callers can print correct diagnostics."""

    def test_returns_false_when_repo_not_in_server_list(self, isolated_home):
        client = _FakeRegistrationClient(repos=[])
        result = _register_hook_policy(client, "local/sandbox", "evidence_only")
        assert result is False
        assert client.puts == [], "should not PUT when repo is not tracked"

    def test_returns_true_and_puts_when_repo_known(self, isolated_home):
        client = _FakeRegistrationClient(
            repos=[{"id": "abc-123", "canonical_identifier": "github.com/o/r"}]
        )
        result = _register_hook_policy(client, "github.com/o/r", "strict")
        assert result is True
        assert client.puts == [
            ("/api/v1/hook-policy/abc-123", {"mode": "strict"})
        ]

    def test_returns_false_when_server_raises(self, isolated_home):
        class _BoomClient:
            def get(self, path):
                raise ConnectionError("server down")
        result = _register_hook_policy(
            _BoomClient(), "github.com/o/r", "strict"
        )
        assert result is False


class TestRepoInitIntegration:
    """End-to-end for the fix: `_do_repo_init` on a repo the server
    doesn't know about MUST still leave hook-policy.json with the local
    intent entry."""

    def test_do_repo_init_writes_intent_even_when_server_unknown(
        self, tmp_path, monkeypatch, isolated_home
    ):
        # Build a minimal fake repo with a .git/ dir
        repo = tmp_path / "sandbox_repo"
        repo.mkdir()
        (repo / ".git").mkdir()

        # Stub the bundled-scripts install so we don't need actual
        # bundled_scripts resources for this test.
        from gator_enterprise_cli.commands import repo_init as repo_init_mod
        monkeypatch.setattr(
            repo_init_mod, "_install_bundled_scripts", lambda scripts_dir: None
        )
        # Stub git operations so this test doesn't require a real git
        monkeypatch.setattr(
            repo_init_mod, "_git_add", lambda repo_path, paths: None
        )

        # Server doesn't know about our sandbox
        client = _FakeRegistrationClient(repos=[])

        args = SimpleNamespace(
            path=str(repo),
            mode="evidence_only",
            canonical_id="local/sandbox",
            commit=False,
            scripts_source=None,
            command="repo",
            repo_command="init",
        )
        repo_init_mod._do_repo_init(args, client)

        # THE ASSERTION: local hook-policy.json has our intent entry
        # even though the server didn't know about the repo.
        policy_path = (
            isolated_home / ".gator" / "enterprise" / "hook-policy.json"
        )
        assert policy_path.exists(), (
            "hook-policy.json was not written — the wrapper will fall "
            "back to strict and the requested mode will be silently ignored"
        )
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        assert policy.get("local/sandbox") == {"mode": "evidence_only"}, (
            f"local intent-mode not persisted; got {policy!r}"
        )
