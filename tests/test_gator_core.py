"""
Tests for gator_core.py — shared infrastructure module.

These functions are imported by 7+ scripts. A bug here breaks
fleet-report, drift, audit, init, update, and version.
"""

import sys
from pathlib import Path

import pytest

# Ensure scripts/ is importable
SCRIPTS_DIR = Path(__file__).parent.parent / "src" / "gator_command" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import gator_core


class TestNormalizePath:
    def test_msys2_path(self):
        """MSYS2/Git Bash paths get converted to Windows native."""
        assert gator_core.normalize_path("/c/Users/curator/code") == "C:/Users/curator/code"

    def test_uppercase_drive(self):
        """Drive letter is uppercased."""
        assert gator_core.normalize_path("/d/projects/repo") == "D:/projects/repo"

    def test_native_path_unchanged(self):
        """Already-native paths pass through."""
        assert gator_core.normalize_path("C:/Users/curator") == "C:/Users/curator"

    def test_relative_path_unchanged(self):
        """Relative paths pass through."""
        assert gator_core.normalize_path("../some/path") == "../some/path"


class TestFindCommandPost:  # LEGACY — command-post retired, kept for enterprise compat
    def test_from_root(self, mock_command_post):
        """Finds command post when called from its root."""
        result = gator_core.find_command_post(mock_command_post)
        assert result == mock_command_post

    def test_from_subdir(self, mock_command_post):
        """Finds command post when called from inside gator-command/."""
        gc_dir = mock_command_post / "gator-command"
        result = gator_core.find_command_post(gc_dir)
        assert result == mock_command_post

    def test_not_found(self, tmp_path):
        """Returns None when no command post exists."""
        assert gator_core.find_command_post(tmp_path) is None


class TestFindGatorRoot:
    def test_finds_repo(self, mock_gator_repo):
        """Finds governed repo root from a subdirectory."""
        repo_root, _ = mock_gator_repo
        sub = repo_root / "src" / "deep"
        sub.mkdir(parents=True)
        assert gator_core.find_gator_root(sub) == repo_root

    def test_not_found(self, tmp_path):
        """Returns None when no .gator/ exists in the search path."""
        # Use a deep isolated path that can't walk up to a real .gator/
        isolated = tmp_path / "a" / "b" / "c"
        isolated.mkdir(parents=True)
        # find_gator_root walks up via parents, and tmp_path is under the
        # system temp dir which may have .gator/ above it. Test the
        # direct case: no .gator/ in the given path or its parents
        # within tmp_path.
        result = gator_core.find_gator_root(isolated)
        # If the real filesystem has a .gator/ above tmp, this will find it.
        # The meaningful test is that it doesn't find one in the mock tree.
        if result is not None:
            # It found a real .gator/ above tmp_path — that's fine,
            # verify it's not inside our tmp_path
            assert not str(result).startswith(str(tmp_path))


class TestIsEnterpriseActive:
    """Pin the production impl to the contracts-layer semantics.

    contracts/compatibility/test_enterprise_marker.py declares the
    canonical fail-closed reference impl; gator_core.is_enterprise_active
    MUST match those semantics byte-for-behavior. If either drifts,
    both should be updated together.
    """

    def test_bare_gator_dir_is_inactive(self, tmp_path):
        gator_dir = tmp_path / ".gator"
        gator_dir.mkdir()
        assert gator_core.is_enterprise_active(gator_dir) is False

    def test_marker_missing_is_inactive(self, tmp_path):
        gator_dir = tmp_path / ".gator"
        gator_dir.mkdir()
        # Explicitly no enterprise.json present
        assert not (gator_dir / "enterprise.json").exists()
        assert gator_core.is_enterprise_active(gator_dir) is False

    def test_marker_enabled_false_is_inactive(self, tmp_path):
        gator_dir = tmp_path / ".gator"
        gator_dir.mkdir()
        (gator_dir / "enterprise.json").write_text(
            '{"enabled": false}', encoding="utf-8"
        )
        assert gator_core.is_enterprise_active(gator_dir) is False

    def test_marker_enabled_true_is_active(self, tmp_path):
        gator_dir = tmp_path / ".gator"
        gator_dir.mkdir()
        (gator_dir / "enterprise.json").write_text(
            '{"enabled": true, "api_url": "https://ex.example", "org_id": "acme"}',
            encoding="utf-8",
        )
        assert gator_core.is_enterprise_active(gator_dir) is True

    def test_malformed_marker_fails_closed(self, tmp_path):
        gator_dir = tmp_path / ".gator"
        gator_dir.mkdir()
        (gator_dir / "enterprise.json").write_text("{ not json", encoding="utf-8")
        assert gator_core.is_enterprise_active(gator_dir) is False

    @pytest.mark.parametrize("non_object_json", [
        "[]", '["enabled"]', "42", "true", '"foo"', "null",
    ])
    def test_non_object_marker_fails_closed(self, tmp_path, non_object_json):
        """Valid JSON that isn't an object MUST fail closed, not crash.

        Codex Phase 4b review caught a real hole: `[]`/`42`/`"foo"` parse
        as valid JSON but crash `.get("enabled")` with AttributeError.
        Fail-closed extends to shape, not just to parseability.
        """
        gator_dir = tmp_path / ".gator"
        gator_dir.mkdir()
        (gator_dir / "enterprise.json").write_text(non_object_json, encoding="utf-8")
        assert gator_core.is_enterprise_active(gator_dir) is False

    def test_enabled_wrong_type_is_inactive(self, tmp_path):
        """enabled must be literal `true`, not truthy string/int/etc.

        The `is True` identity check in the impl is deliberate — matches
        the contract's fail-closed posture. `enabled: "true"` (string)
        or `enabled: 1` (int) are marker-shape errors, not activations.
        """
        gator_dir = tmp_path / ".gator"
        gator_dir.mkdir()
        for bad in ('"true"', "1", "null"):
            (gator_dir / "enterprise.json").write_text(
                f'{{"enabled": {bad}}}', encoding="utf-8"
            )
            assert gator_core.is_enterprise_active(gator_dir) is False, (
                f"enabled={bad} should NOT activate Enterprise"
            )

    def test_accepts_string_gator_dir(self, tmp_path):
        """Callers may pass a str path — Path() coercion in the impl handles it."""
        gator_dir = tmp_path / ".gator"
        gator_dir.mkdir()
        (gator_dir / "enterprise.json").write_text(
            '{"enabled": true, "api_url": "https://x", "org_id": "y"}',
            encoding="utf-8",
        )
        assert gator_core.is_enterprise_active(str(gator_dir)) is True


class TestParseRegistry:  # LEGACY — command-post retired, kept for enterprise compat
    def test_parses_table(self, mock_command_post):
        """Parses registry.md markdown table into repo dicts."""
        repos = gator_core.parse_registry(mock_command_post)
        assert len(repos) == 2
        assert repos[0]["name"] == "test-repo"
        assert repos[1]["name"] == "other-repo"
        assert repos[1]["remote"] == "github.com/org/other"
        assert repos[0]["status"] == "active"

    def test_missing_registry(self, tmp_path):
        """Returns empty list when registry.md doesn't exist."""
        assert gator_core.parse_registry(tmp_path) == []


class TestResolveThinLink:
    def test_resolves_absolute(self, mock_gator_repo, mock_command_post):
        """Resolves the command-post-absolute field in command-post.md."""
        _, gator_dir = mock_gator_repo
        # The fixture writes command-post-absolute pointing to tmp_path/cp
        result = gator_core.resolve_thin_link(gator_dir)
        assert result is not None
        assert (result / "gator-command" / "mission.md").exists()

    def test_missing_file(self, tmp_path):
        """Returns None when command-post.md doesn't exist."""
        assert gator_core.resolve_thin_link(tmp_path) is None


class TestEnsureDashboardRegistryEntry:
    def test_adds_repo_to_empty_registry(self, tmp_path, monkeypatch):
        """Adds a repo when the registry is empty."""
        reg_file = tmp_path / "dashboard-repos.json"
        monkeypatch.setattr(gator_core, "DASHBOARD_REGISTRY", reg_file)

        repo = tmp_path / "my-repo"
        repo.mkdir()

        result = gator_core.ensure_dashboard_registry_entry(repo, source="test")
        assert result["status"] == "added"

        repos = gator_core.read_dashboard_registry()
        assert len(repos) == 1
        assert repos[0]["name"] == "my-repo"
        assert repos[0]["source"] == "test"

    def test_idempotent_second_call(self, tmp_path, monkeypatch):
        """Second call returns already_registered, registry unchanged."""
        reg_file = tmp_path / "dashboard-repos.json"
        monkeypatch.setattr(gator_core, "DASHBOARD_REGISTRY", reg_file)

        repo = tmp_path / "my-repo"
        repo.mkdir()

        first = gator_core.ensure_dashboard_registry_entry(repo)
        second = gator_core.ensure_dashboard_registry_entry(repo)

        assert first["status"] == "added"
        assert second["status"] == "already_registered"
        assert len(gator_core.read_dashboard_registry()) == 1

    def test_unavailable_for_missing_path(self, tmp_path, monkeypatch):
        """Returns unavailable when repo path doesn't exist."""
        reg_file = tmp_path / "dashboard-repos.json"
        monkeypatch.setattr(gator_core, "DASHBOARD_REGISTRY", reg_file)

        result = gator_core.ensure_dashboard_registry_entry(tmp_path / "nonexistent")
        assert result["status"] == "unavailable"

    def test_add_dashboard_repo_uses_shared_helper(self, tmp_path, monkeypatch):
        """add_dashboard_repo delegates to ensure_dashboard_registry_entry."""
        reg_file = tmp_path / "dashboard-repos.json"
        monkeypatch.setattr(gator_core, "DASHBOARD_REGISTRY", reg_file)

        repo = tmp_path / "my-repo"
        repo.mkdir()

        added = gator_core.add_dashboard_repo(repo)
        assert added is True

        added_again = gator_core.add_dashboard_repo(repo)
        assert added_again is False
        assert len(gator_core.read_dashboard_registry()) == 1


class TestGitEncoding:
    """Regression guard for the v2.4.4 hotfix: `git()` must decode subprocess
    output as UTF-8 with error replacement, not the platform-default locale
    codec (cp1252 on Windows). Prior form used `text=True` without `encoding=`,
    which crashed with UnicodeDecodeError on any git output containing bytes
    unrepresentable in cp1252 — surfaced as an "Empty reply from server" from
    the Dashboard History endpoint when git log emitted non-ASCII commit
    subjects, author names, or trailer content.

    Same fix already lived in `dashboard/helpers.py::git_run` per the charter
    ("`_git_run()` uses `encoding='utf-8'` (not `text=True`) — same fix as
    gator-deploy.py for Windows cp1252 compatibility"). The `gator_core.git()`
    copy just never got the same treatment.
    """

    def test_git_uses_utf8_encoding_with_replace(self):
        """Grep-verify that the fix is present in source. A subprocess-level
        test would need a git repo with a non-cp1252 commit message, which
        is heavy to fixture; the guarantee we need is that the encoding args
        stay on the subprocess call.
        """
        import inspect
        source = inspect.getsource(gator_core.git)
        assert 'encoding="utf-8"' in source, (
            "gator_core.git() must specify UTF-8 encoding — see v2.4.4 hotfix"
        )
        assert 'errors="replace"' in source, (
            "gator_core.git() must specify errors='replace' as defense against "
            "genuinely non-UTF-8 git output"
        )
        # Regression guard: bare `text=True` (without encoding=) crashes on
        # non-cp1252 bytes on Windows.
        assert "text=True" not in source, (
            "gator_core.git() must not use bare text=True — explicit encoding required"
        )

    def test_get_version_git_subprocess_calls_use_utf8(self):
        """get_version's git describe / git rev-parse calls must also use
        explicit UTF-8 encoding — same class of bug, same fix.
        """
        import inspect
        source = inspect.getsource(gator_core.get_version)
        # Both subprocess calls in get_version should have encoding="utf-8"
        assert source.count('encoding="utf-8"') >= 2, (
            "get_version's git subprocess calls should specify UTF-8 encoding"
        )
        assert "text=True" not in source


class TestWriteRuntimePin:
    """Runtime-split Phase 1 (roadmap item 19): write_runtime_pin emits the
    committed record of which shipped runtime is in force."""

    def _make_v2_gator(self, tmp_path):
        gator = tmp_path / ".gator"
        scripts = gator / ".includes" / "scripts"
        (scripts / "hooks").mkdir(parents=True)
        (scripts / "gator-pre-commit.py").write_text("print('hook')\n", encoding="utf-8")
        (scripts / "hooks" / "pre-commit").write_text("#!/bin/bash\n", encoding="utf-8")
        # __pycache__ must be excluded from the manifest
        pyc = scripts / "__pycache__"
        pyc.mkdir()
        (pyc / "x.cpython-313.pyc").write_bytes(b"\x00")
        return gator

    def test_v2_layout_pin_written_with_manifest(self, tmp_path):
        import hashlib
        import json
        gator = self._make_v2_gator(tmp_path)
        pin = gator_core.write_runtime_pin(gator, version="9.9.9")
        assert pin is not None
        on_disk = json.loads((gator / "runtime-pin.json").read_text(encoding="utf-8"))
        assert on_disk == pin
        assert pin["schema"] == "gator-runtime-pin-v1"
        assert pin["runtime_version"] == "9.9.9"
        assert set(pin["manifest"]) == {"gator-pre-commit.py", "hooks/pre-commit"}
        # Manifest is byte-exact over the on-disk file (platform newlines
        # included) — "the runtime in force on this checkout". Cross-platform
        # verification semantics (autocrlf) are a Phase 2 concern.
        raw = (gator / ".includes" / "scripts" / "gator-pre-commit.py").read_bytes()
        expected = "sha256:" + hashlib.sha256(raw).hexdigest()
        assert pin["manifest"]["gator-pre-commit.py"] == expected

    def test_pycache_excluded(self, tmp_path):
        gator = self._make_v2_gator(tmp_path)
        pin = gator_core.write_runtime_pin(gator, version="9.9.9")
        assert not any("__pycache__" in k for k in pin["manifest"])

    def test_v1_layout_fallback(self, tmp_path):
        gator = tmp_path / ".gator"
        scripts = gator / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "gator-pre-commit.py").write_text("x = 1\n", encoding="utf-8")
        pin = gator_core.write_runtime_pin(gator, version="9.9.9")
        assert pin is not None
        assert set(pin["manifest"]) == {"gator-pre-commit.py"}

    def test_no_scripts_dir_returns_none_and_writes_nothing(self, tmp_path):
        gator = tmp_path / ".gator"
        gator.mkdir()
        assert gator_core.write_runtime_pin(gator, version="9.9.9") is None
        assert not (gator / "runtime-pin.json").exists()

    def test_pinned_at_shape_and_machine_field_present(self, tmp_path):
        import re
        gator = self._make_v2_gator(tmp_path)
        pin = gator_core.write_runtime_pin(gator, version="9.9.9")
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", pin["pinned_at"])
        assert "pinned_by_machine" in pin  # str or None, both legal

    def test_reemission_is_idempotent_for_same_content(self, tmp_path):
        gator = self._make_v2_gator(tmp_path)
        first = gator_core.write_runtime_pin(gator, version="9.9.9")
        second = gator_core.write_runtime_pin(gator, version="9.9.9")
        assert first["manifest"] == second["manifest"]


class TestResolveGovernedRuntime:
    """Runtime-split Phase 2 (roadmap item 19, Variant A): fail-closed
    version negotiation. Every branch of the plan §4.4 resolution order."""

    def _repo(self, tmp_path, pin_version=None, scripts=True, pin_raw=None):
        gator = tmp_path / ".gator"
        if scripts:
            (gator / ".includes" / "scripts").mkdir(parents=True)
        else:
            gator.mkdir(parents=True, exist_ok=True)
        if pin_raw is not None:
            (gator / "runtime-pin.json").write_text(pin_raw, encoding="utf-8")
        elif pin_version is not None:
            import json
            (gator / "runtime-pin.json").write_text(
                json.dumps({"schema": "gator-runtime-pin-v1",
                            "runtime_version": pin_version,
                            "pinned_at": "2026-08-18T00:00:00Z",
                            "manifest": {}}),
                encoding="utf-8")
        return tmp_path

    def test_equal_versions_current(self, tmp_path):
        repo = self._repo(tmp_path, pin_version="2.9.0")
        d = gator_core.resolve_governed_runtime(repo, cli_version="2.9.0")
        assert d["mode"] == "current"
        assert d["pin_version"] == "2.9.0"

    def test_cli_newer_runs_and_advises(self, tmp_path):
        repo = self._repo(tmp_path, pin_version="2.8.0")
        d = gator_core.resolve_governed_runtime(repo, cli_version="2.9.0")
        assert d["mode"] == "cli-newer"
        assert "gator update" in d["reason"]

    def test_cli_older_refuses_fail_closed(self, tmp_path):
        repo = self._repo(tmp_path, pin_version="2.9.0")
        d = gator_core.resolve_governed_runtime(repo, cli_version="2.8.0")
        assert d["mode"] == "refuse"
        assert "pipx upgrade gator-command" in d["reason"]

    def test_rc_suffix_tolerated_in_comparison(self, tmp_path):
        repo = self._repo(tmp_path, pin_version="2.9.0")
        d = gator_core.resolve_governed_runtime(repo, cli_version="2.9.0rc1")
        assert d["mode"] == "current"

    def test_no_pin_with_v2_scripts_falls_back(self, tmp_path):
        repo = self._repo(tmp_path)
        d = gator_core.resolve_governed_runtime(repo, cli_version="2.9.0")
        assert d["mode"] == "repo-scripts"

    def test_no_pin_with_v1_scripts_falls_back(self, tmp_path):
        gator = tmp_path / ".gator"
        (gator / "scripts").mkdir(parents=True)
        d = gator_core.resolve_governed_runtime(tmp_path, cli_version="2.9.0")
        assert d["mode"] == "repo-scripts"

    def test_nothing_at_all_is_ungoverned(self, tmp_path):
        repo = self._repo(tmp_path, scripts=False)
        d = gator_core.resolve_governed_runtime(repo, cli_version="2.9.0")
        assert d["mode"] == "ungoverned"

    def test_malformed_pin_fails_open_to_repo_scripts(self, tmp_path):
        repo = self._repo(tmp_path, pin_raw="{not json")
        d = gator_core.resolve_governed_runtime(repo, cli_version="2.9.0")
        assert d["mode"] == "pin-unreadable"
        assert "gator update" in d["reason"]

    def test_pin_missing_version_key_fails_open(self, tmp_path):
        repo = self._repo(tmp_path, pin_raw='{"schema": "gator-runtime-pin-v1"}')
        d = gator_core.resolve_governed_runtime(repo, cli_version="2.9.0")
        assert d["mode"] == "pin-unreadable"

    def test_unparseable_version_fails_open(self, tmp_path):
        repo = self._repo(tmp_path, pin_version="not-a-version")
        d = gator_core.resolve_governed_runtime(repo, cli_version="2.9.0")
        assert d["mode"] == "pin-unreadable"

    def test_unparseable_version_without_scripts_is_ungoverned(self, tmp_path):
        """Whiteboard 2026-08-19 Finding 1: the unparseable-VERSION branch
        must degrade the same way the malformed-JSON branch does — to
        `ungoverned` when there are no repo-resident scripts to fall back
        to, with a reason that does not promise an impossible fallback."""
        repo = self._repo(tmp_path, scripts=False, pin_version="not-a-version")
        d = gator_core.resolve_governed_runtime(repo, cli_version="2.9.0")
        assert d["mode"] == "ungoverned"
        assert "no repo-resident scripts exist" in d["reason"]
        assert "gator update" in d["reason"]

    def test_malformed_pin_without_scripts_is_ungoverned(self, tmp_path):
        repo = self._repo(tmp_path, scripts=False, pin_raw="{not json")
        d = gator_core.resolve_governed_runtime(repo, cli_version="2.9.0")
        assert d["mode"] == "ungoverned"

    def test_decision_is_pure_no_side_effects(self, tmp_path):
        repo = self._repo(tmp_path, pin_version="2.9.0")
        before = sorted(p.name for p in (repo / ".gator").rglob("*"))
        gator_core.resolve_governed_runtime(repo, cli_version="1.0.0")
        after = sorted(p.name for p in (repo / ".gator").rglob("*"))
        assert before == after

    def test_bom_pin_still_parses_and_refuses(self, tmp_path):
        """A UTF-8 BOM on the pin (Windows editors, PowerShell 5.1
        Set-Content) must NOT downgrade fail-closed refusal to fail-open
        fallback. Live-caught during Phase 2 dogfooding: a BOM'd pin hit
        JSONDecodeError -> pin-unreadable instead of refuse."""
        import json
        gator = tmp_path / ".gator"
        (gator / ".includes" / "scripts").mkdir(parents=True)
        pin = json.dumps({"schema": "gator-runtime-pin-v1",
                          "runtime_version": "99.0.0",
                          "pinned_at": "2026-08-18T00:00:00Z",
                          "manifest": {}})
        (gator / "runtime-pin.json").write_bytes(b"\xef\xbb\xbf" + pin.encode("utf-8"))
        d = gator_core.resolve_governed_runtime(tmp_path, cli_version="2.9.0")
        assert d["mode"] == "refuse"



class TestVersionTuple:
    def test_plain(self):
        assert gator_core._version_tuple("2.9.0") == (2, 9, 0)

    def test_rc_suffix(self):
        assert gator_core._version_tuple("2.9.0rc1") == (2, 9, 0)

    def test_two_part(self):
        assert gator_core._version_tuple("2.9") == (2, 9)

    def test_garbage_none(self):
        assert gator_core._version_tuple("dev") is None
        assert gator_core._version_tuple("") is None
        assert gator_core._version_tuple(None) is None

    def test_dev_suffix_stops_cleanly(self):
        assert gator_core._version_tuple("2.9.dev1") == (2, 9)


class TestWriteRuntimePinRuntimeDir:
    """Runtime-split Phase 4a: manifest source override — callers pass the
    wheel's template scripts (the bytes in force under Variant A)."""

    def test_runtime_dir_used_when_provided(self, tmp_path):
        import hashlib
        gator = tmp_path / ".gator"
        gator.mkdir()
        wheel = tmp_path / "wheel-scripts"
        wheel.mkdir()
        (wheel / "gator-pre-commit.py").write_bytes(b"wheel bytes\n")
        pin = gator_core.write_runtime_pin(gator, version="9.9.9",
                                           runtime_dir=wheel)
        assert pin is not None
        expected = "sha256:" + hashlib.sha256(b"wheel bytes\n").hexdigest()
        assert pin["manifest"] == {"gator-pre-commit.py": expected}

    def test_runtime_dir_wins_over_repo_copy(self, tmp_path):
        gator = tmp_path / ".gator"
        scripts = gator / ".includes" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "gator-pre-commit.py").write_bytes(b"repo bytes\n")
        wheel = tmp_path / "wheel-scripts"
        wheel.mkdir()
        (wheel / "gator-pre-commit.py").write_bytes(b"wheel bytes\n")
        pin = gator_core.write_runtime_pin(gator, version="9.9.9",
                                           runtime_dir=wheel)
        import hashlib
        expected = "sha256:" + hashlib.sha256(b"wheel bytes\n").hexdigest()
        assert pin["manifest"]["gator-pre-commit.py"] == expected

    def test_missing_runtime_dir_falls_back_to_repo(self, tmp_path):
        gator = tmp_path / ".gator"
        scripts = gator / ".includes" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "x.py").write_bytes(b"x\n")
        pin = gator_core.write_runtime_pin(
            gator, version="9.9.9", runtime_dir=tmp_path / "nope")
        assert pin is not None
        assert set(pin["manifest"]) == {"x.py"}


class TestPolicyStalenessNudge:
    """Runtime-split D6 decision (c), Architect-ratified 2026-08-22:
    purely LOCAL staleness check — no network in any session-opening
    path; Enterprise-active repos only; never raises."""

    def _enterprise_repo(self, tmp_path):
        gator = tmp_path / ".gator"
        gator.mkdir()
        (gator / "enterprise.json").write_text(
            '{"enabled": true, "api_url": "https://x", "org_id": "o"}',
            encoding="utf-8")
        return gator

    def _fake_home(self, tmp_path, monkeypatch, mtime_age_days=None):
        home = tmp_path / "home"
        (home / ".gator" / "enterprise").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        if mtime_age_days is not None:
            import os as _os
            import time as _time
            f = home / ".gator" / "enterprise" / "org-policies.json"
            f.write_text("{}", encoding="utf-8")
            old = _time.time() - mtime_age_days * 86400
            _os.utime(f, (old, old))
        return home

    def test_non_enterprise_repo_is_none(self, tmp_path, monkeypatch):
        gator = tmp_path / ".gator"
        gator.mkdir()
        self._fake_home(tmp_path, monkeypatch, mtime_age_days=100)
        assert gator_core.policy_staleness_nudge(gator) is None

    def test_never_pulled_nudges(self, tmp_path, monkeypatch):
        gator = self._enterprise_repo(tmp_path)
        self._fake_home(tmp_path, monkeypatch)
        msg = gator_core.policy_staleness_nudge(gator)
        assert msg and "never pulled" in msg
        assert "gator-enterprise policies pull" in msg

    def test_fresh_pull_is_quiet(self, tmp_path, monkeypatch):
        gator = self._enterprise_repo(tmp_path)
        self._fake_home(tmp_path, monkeypatch, mtime_age_days=1)
        assert gator_core.policy_staleness_nudge(gator) is None

    def test_stale_pull_nudges_with_age(self, tmp_path, monkeypatch):
        gator = self._enterprise_repo(tmp_path)
        self._fake_home(tmp_path, monkeypatch, mtime_age_days=12)
        msg = gator_core.policy_staleness_nudge(gator)
        assert msg and "12 day(s)" in msg

    def test_threshold_override(self, tmp_path, monkeypatch):
        gator = self._enterprise_repo(tmp_path)
        self._fake_home(tmp_path, monkeypatch, mtime_age_days=3)
        assert gator_core.policy_staleness_nudge(gator, stale_days=2)
        assert gator_core.policy_staleness_nudge(gator, stale_days=5) is None

    def test_never_raises(self, tmp_path, monkeypatch):
        gator = self._enterprise_repo(tmp_path)
        monkeypatch.setattr(Path, "home",
                            staticmethod(lambda: (_ for _ in ()).throw(OSError("boom"))))
        assert gator_core.policy_staleness_nudge(gator) is None

    def test_banner_shows_policy_nudge_wiring(self, tmp_path, monkeypatch,
                                              capsys):
        """Whiteboard 2026-08-22 r3: the `gator init` banner wiring itself
        — the original referenced an undefined name and the blanket
        except swallowed the NameError, making the agent-facing D6
        surface dead code while helper-only tests stayed green. This
        test patches the HELPER and asserts the line lands in the
        banner, pinning the wiring end-to-end."""
        from conftest import load_script
        init = load_script("gator-init")
        gator_layout = load_script("gator_layout")

        gator = tmp_path / ".gator"
        includes = gator / ".includes"
        includes.mkdir(parents=True)
        (includes / "constitution.md").write_text("# c\n", encoding="utf-8")
        (includes / "scripts").mkdir()
        (gator / "layout-version.json").write_text(
            '{"layout": "v2"}\n', encoding="utf-8")
        (gator / "mission.md").write_text("# m\n", encoding="utf-8")
        paths = gator_layout.get_gator_paths(tmp_path)

        monkeypatch.setattr(gator_core, "policy_staleness_nudge",
                            lambda gd, **kw: "WIRING-SENTINEL nudge")
        init.print_boot_sequence(
            tmp_path, paths,
            {"status": "ok", "detail": "ok", "adds": 0, "updates": 0},
            {"status": "ok", "detail": "registered"},
        )
        out = capsys.readouterr().out
        assert "! policy" in out and "WIRING-SENTINEL" in out

    def test_banner_survives_nudge_helper_raising(self, tmp_path,
                                                  monkeypatch, capsys):
        from conftest import load_script
        init = load_script("gator-init")
        gator_layout = load_script("gator_layout")
        gator = tmp_path / ".gator"
        includes = gator / ".includes"
        includes.mkdir(parents=True)
        (includes / "constitution.md").write_text("# c\n", encoding="utf-8")
        (includes / "scripts").mkdir()
        (gator / "layout-version.json").write_text(
            '{"layout": "v2"}\n', encoding="utf-8")
        paths = gator_layout.get_gator_paths(tmp_path)

        def _boom(gd, **kw):
            raise RuntimeError("boom")
        monkeypatch.setattr(gator_core, "policy_staleness_nudge", _boom)
        init.print_boot_sequence(
            tmp_path, paths,
            {"status": "ok", "detail": "ok", "adds": 0, "updates": 0},
            {"status": "ok", "detail": "registered"},
        )
        out = capsys.readouterr().out
        assert "! policy" not in out
        assert "navigation coding" in out  # banner completed

    def test_banner_ends_with_session_opening_directive(self, tmp_path,
                                                        monkeypatch, capsys):
        """Inbox 2026-08-23 (constitution-skip finding): the banner must
        NOT end on the tagline-as-completion. It hands off to the
        session-opening reads with the blunt resolved constitution path
        (no conditional two-path lookup) plus the three context reads."""
        from conftest import load_script
        init = load_script("gator-init")
        gator_layout = load_script("gator_layout")
        gator = tmp_path / ".gator"
        includes = gator / ".includes"
        includes.mkdir(parents=True)
        (includes / "constitution.md").write_text("# c\n", encoding="utf-8")
        (includes / "scripts").mkdir()
        (gator / "layout-version.json").write_text(
            '{"layout": "v2"}\n', encoding="utf-8")
        paths = gator_layout.get_gator_paths(tmp_path)
        monkeypatch.setattr(gator_core, "policy_staleness_nudge",
                            lambda gd, **kw: None)
        init.print_boot_sequence(
            tmp_path, paths,
            {"status": "ok", "detail": "ok", "adds": 0, "updates": 0},
            {"status": "ok", "detail": "registered"},
        )
        out = capsys.readouterr().out
        assert "session opening is not finished" in out
        assert ".gator/.includes/constitution.md" in out
        assert "mission.md" in out and "roadmap.md" in out \
            and "inbox.md" in out
        # directive sits between tagline and the prompt marker
        assert out.index("terrain is mapped") \
            < out.index("session opening is not finished")

    def test_session_opening_directive_resolves_v2_path(self, tmp_path):
        from conftest import load_script
        init = load_script("gator-init")
        gator_layout = load_script("gator_layout")
        gator = tmp_path / ".gator"
        includes = gator / ".includes"
        includes.mkdir(parents=True)
        (includes / "constitution.md").write_text("# c\n", encoding="utf-8")
        (includes / "scripts").mkdir()
        (gator / "layout-version.json").write_text(
            '{"layout": "v2"}\n', encoding="utf-8")
        paths = gator_layout.get_gator_paths(tmp_path)
        lines = init.session_opening_directive(tmp_path, paths)
        joined = "\n".join(lines)
        assert ".gator/.includes/constitution.md" in joined
        assert ".gator/mission.md" in joined


class TestReadPreferences:
    """gator-preferences-v1 reader — the discriminated result is the
    load-bearing invariant so callers can distinguish 'absent' (safe to
    fall back to auto-detect) from 'malformed' (loud degradation, no
    fallback). Regression pin for 2026-08-29 whiteboard finding 1."""

    def _patched_home(self, tmp_path, monkeypatch):
        # gator_core caches PREFERENCES_FILE at import time from Path.home();
        # patch the constant directly to point at the tmp path.
        prefs = tmp_path / ".gator" / "preferences.json"
        monkeypatch.setattr(gator_core, "PREFERENCES_FILE", prefs)
        return prefs

    def test_absent_returns_absent_state(self, tmp_path, monkeypatch):
        prefs = self._patched_home(tmp_path, monkeypatch)
        assert not prefs.exists()
        result = gator_core.read_preferences()
        assert result == {"state": "absent"}

    def test_valid_file_returns_present_with_data(self, tmp_path, monkeypatch):
        import json as _json
        prefs = self._patched_home(tmp_path, monkeypatch)
        prefs.parent.mkdir(parents=True)
        payload = {
            "schema": "gator-preferences-v1",
            "updated_at": "2026-08-29T00:00:00Z",
            "python": {
                "source": "user",
                "windows_py_launcher": "C:/Windows/py.exe",
            },
        }
        prefs.write_text(_json.dumps(payload), encoding="utf-8")
        result = gator_core.read_preferences()
        assert result["state"] == "present"
        assert result["data"]["schema"] == "gator-preferences-v1"
        assert result["data"]["python"]["windows_py_launcher"] == "C:/Windows/py.exe"

    def test_malformed_json_returns_malformed(self, tmp_path, monkeypatch):
        prefs = self._patched_home(tmp_path, monkeypatch)
        prefs.parent.mkdir(parents=True)
        prefs.write_text("{this is not { valid JSON,", encoding="utf-8")
        result = gator_core.read_preferences()
        assert result["state"] == "malformed"
        assert "parse-error" in result["reason"]

    def test_wrong_schema_tag_returns_malformed(self, tmp_path, monkeypatch):
        import json as _json
        prefs = self._patched_home(tmp_path, monkeypatch)
        prefs.parent.mkdir(parents=True)
        prefs.write_text(_json.dumps({"schema": "gator-preferences-v999"}),
                         encoding="utf-8")
        result = gator_core.read_preferences()
        assert result["state"] == "malformed"
        assert "schema-mismatch" in result["reason"]

    def test_top_level_array_returns_malformed(self, tmp_path, monkeypatch):
        import json as _json
        prefs = self._patched_home(tmp_path, monkeypatch)
        prefs.parent.mkdir(parents=True)
        prefs.write_text(_json.dumps(["not", "an", "object"]),
                         encoding="utf-8")
        result = gator_core.read_preferences()
        assert result["state"] == "malformed"
        assert result["reason"] == "top-level-not-object"

    def test_valid_without_python_section_is_present(self, tmp_path, monkeypatch):
        """A file with only `schema:` is legal — a machine may have a
        stub file or (post-follow-on) only `hooks:` preferences."""
        import json as _json
        prefs = self._patched_home(tmp_path, monkeypatch)
        prefs.parent.mkdir(parents=True)
        prefs.write_text(_json.dumps({"schema": "gator-preferences-v1"}),
                         encoding="utf-8")
        result = gator_core.read_preferences()
        assert result["state"] == "present"
        assert "python" not in result["data"]

    def test_utf8_bom_tolerated(self, tmp_path, monkeypatch):
        """PowerShell 5.1's Set-Content -Encoding utf8 writes a BOM;
        matches the utf-8-sig read pattern used by resolve_governed_runtime."""
        import json as _json
        prefs = self._patched_home(tmp_path, monkeypatch)
        prefs.parent.mkdir(parents=True)
        payload = _json.dumps({"schema": "gator-preferences-v1"})
        prefs.write_bytes(b"\xef\xbb\xbf" + payload.encode("utf-8"))
        result = gator_core.read_preferences()
        assert result["state"] == "present"

    def test_python_section_as_list_returns_malformed(self, tmp_path, monkeypatch):
        """LOAD-BEARING (2026-08-29 whiteboard finding 1): a tagged file
        whose `python:` is a JSON list rather than an object would slip
        through the top-level-not-object + schema-tag checks, then crash
        the resolver's `.get(...)` chain with AttributeError. Reader
        must return malformed here so the resolver's 'never raises'
        contract holds."""
        import json as _json
        prefs = self._patched_home(tmp_path, monkeypatch)
        prefs.parent.mkdir(parents=True)
        prefs.write_text(_json.dumps({
            "schema": "gator-preferences-v1",
            "python": [],
        }), encoding="utf-8")
        result = gator_core.read_preferences()
        assert result["state"] == "malformed"
        assert "shape" in result["reason"]
        assert "python" in result["reason"]

    def test_hooks_section_as_string_returns_malformed(self, tmp_path, monkeypatch):
        """Same defense for the reserved `hooks:` section — the follow-on
        plan will consume this section directly; a wrong-type shape must
        surface as malformed, not crash the future hook-mode resolver."""
        import json as _json
        prefs = self._patched_home(tmp_path, monkeypatch)
        prefs.parent.mkdir(parents=True)
        prefs.write_text(_json.dumps({
            "schema": "gator-preferences-v1",
            "hooks": "not-an-object",
        }), encoding="utf-8")
        result = gator_core.read_preferences()
        assert result["state"] == "malformed"
        assert "hooks" in result["reason"]

    def test_windows_py_launcher_as_int_returns_malformed(self, tmp_path, monkeypatch):
        """Nested field type check: `python.windows_py_launcher: 42`
        would slip past the section-level check and crash the validator
        when it calls `os.path.isabs(42)`."""
        import json as _json
        prefs = self._patched_home(tmp_path, monkeypatch)
        prefs.parent.mkdir(parents=True)
        prefs.write_text(_json.dumps({
            "schema": "gator-preferences-v1",
            "python": {"windows_py_launcher": 42},
        }), encoding="utf-8")
        result = gator_core.read_preferences()
        assert result["state"] == "malformed"
        assert "windows_py_launcher" in result["reason"]

    def test_allow_for_hook_shebang_as_string_returns_malformed(
        self, tmp_path, monkeypatch
    ):
        """Nested boolean field type check: `python.allow_for_hook_shebang:
        "yes"` is truthy but not a bool; without shape validation the
        resolver would silently treat it as True."""
        import json as _json
        prefs = self._patched_home(tmp_path, monkeypatch)
        prefs.parent.mkdir(parents=True)
        prefs.write_text(_json.dumps({
            "schema": "gator-preferences-v1",
            "python": {"allow_for_hook_shebang": "yes"},
        }), encoding="utf-8")
        result = gator_core.read_preferences()
        assert result["state"] == "malformed"
        assert "allow_for_hook_shebang" in result["reason"]

    def test_unknown_top_level_section_tolerated_in_reader(
        self, tmp_path, monkeypatch
    ):
        """Shape validator must NOT reject unknown sections — schema
        contract is additive-friendly. Only DOCUMENTED sections get
        type-checked."""
        import json as _json
        prefs = self._patched_home(tmp_path, monkeypatch)
        prefs.parent.mkdir(parents=True)
        prefs.write_text(_json.dumps({
            "schema": "gator-preferences-v1",
            "future_section": {"anything": "goes"},
        }), encoding="utf-8")
        result = gator_core.read_preferences()
        assert result["state"] == "present"

    def test_empty_windows_py_launcher_returns_malformed(
        self, tmp_path, monkeypatch
    ):
        """LOAD-BEARING (2026-08-29 whiteboard follow-up finding):
        `python.windows_py_launcher: ""` is a string (passes isinstance)
        but violates the shipped schema's `minLength: 1`. Without a
        runtime enforcement of that constraint, the empty string slips
        through as `present`, then the resolver's `if not launcher:`
        shortcut treats it as "no launcher configured" and silently
        falls through to auto-detect — recreating the silent-fallback
        class this feature exists to prevent. Reader must catch it."""
        import json as _json
        prefs = self._patched_home(tmp_path, monkeypatch)
        prefs.parent.mkdir(parents=True)
        prefs.write_text(_json.dumps({
            "schema": "gator-preferences-v1",
            "python": {"windows_py_launcher": ""},
        }), encoding="utf-8")
        result = gator_core.read_preferences()
        assert result["state"] == "malformed"
        assert "windows_py_launcher" in result["reason"]
        assert "non-empty" in result["reason"] or "minLength" in result["reason"]


class TestValidateLauncherCandidate:
    """The four rules that any candidate py.exe path must satisfy to be
    usable for hook-shebang generation on Windows. Existence is checked
    last so configuration reasons (basename, relative, spaces) surface
    even when the file is missing."""

    def test_empty_returns_empty_path(self):
        valid, reason = gator_core._validate_launcher_candidate("")
        assert not valid
        assert reason == "empty-path"

    def test_none_returns_empty_path(self):
        valid, reason = gator_core._validate_launcher_candidate(None)
        assert not valid
        assert reason == "empty-path"

    def test_relative_returns_relative_path(self):
        valid, reason = gator_core._validate_launcher_candidate("py.exe")
        assert not valid
        assert reason == "relative-path"

    def test_wrong_basename_returns_basename_mismatch(self, tmp_path):
        target = tmp_path / "python.exe"
        target.write_text("")
        valid, reason = gator_core._validate_launcher_candidate(str(target))
        assert not valid
        assert "basename-mismatch" in reason
        assert "python.exe" in reason

    def test_spaced_absolute_returns_spaced_path(self):
        valid, reason = gator_core._validate_launcher_candidate(
            "C:/Users/John Doe/AppData/Local/Programs/Python/Launcher/py.exe")
        assert not valid
        assert reason == "spaced-path"

    def test_missing_file_returns_file_not_found(self):
        valid, reason = gator_core._validate_launcher_candidate(
            "C:/nonexistent/absolutely/does-not-exist/py.exe")
        assert not valid
        assert reason == "file-not-found"

    def test_valid_returns_true_empty_reason(self, tmp_path):
        target = tmp_path / "py.exe"
        target.write_text("")
        valid, reason = gator_core._validate_launcher_candidate(str(target))
        assert valid
        assert reason == ""

    def test_for_shebang_false_permits_spaces(self, tmp_path):
        """When called for non-shebang uses (e.g. future subprocess seams),
        spaces are acceptable — subprocess.call([...]) handles them."""
        spaced_dir = tmp_path / "with space"
        spaced_dir.mkdir()
        target = spaced_dir / "py.exe"
        target.write_text("")
        valid, reason = gator_core._validate_launcher_candidate(
            str(target), for_shebang=False)
        assert valid
        assert reason == ""


class TestResolvePythonLauncherForHooks:
    """resolve_python_launcher_for_hooks() — the canonical launcher
    resolver used by _hook_shebang() and (later) any other seam that
    needs a spaceless absolute py.exe. Contract:

      - Windows-only; non-Windows returns not-applicable.
      - Preference file precedence: valid → resolved user; invalid →
        degraded user (NEVER fall through — Sketch §9 Rule 2); absent
        or no python section → auto-detect.
      - Auto-detect: shutil.which → LocalAppData → C:\\Windows,
        each space-checked.
      - Nothing usable → degraded none, checked trail populated.

    Windows-only tests skip on non-Windows because they patch
    os.path.expandvars / shutil.which in ways that require the nt
    branch of the resolver to execute; on Unix the resolver short-circuits.
    """

    def _patch_prefs(self, monkeypatch, tmp_path):
        prefs = tmp_path / ".gator" / "preferences.json"
        monkeypatch.setattr(gator_core, "PREFERENCES_FILE", prefs)
        return prefs

    def test_non_windows_returns_not_applicable(self, monkeypatch):
        import os as _os
        monkeypatch.setattr(_os, "name", "posix")
        result = gator_core.resolve_python_launcher_for_hooks()
        assert result["status"] == "not-applicable"
        assert result["source"] == "none"
        assert result["path"] is None

    @pytest.mark.skipif(
        __import__("os").name != "nt",
        reason="Windows resolver uses os.path.isfile on Windows-style "
               "paths; patching os.name is not enough on POSIX.",
    )
    def test_preference_absent_auto_succeeds(self, tmp_path, monkeypatch):
        self._patch_prefs(monkeypatch, tmp_path)
        # Force shutil.which to return a spaceless real path
        launcher = tmp_path / "py.exe"
        launcher.write_text("")
        import shutil as _shutil
        monkeypatch.setattr(_shutil, "which", lambda n: str(launcher))
        result = gator_core.resolve_python_launcher_for_hooks()
        assert result["status"] == "resolved"
        assert result["source"] == "auto"
        assert result["path"].replace("\\", "/") == str(launcher).replace("\\", "/")

    @pytest.mark.skipif(
        __import__("os").name != "nt",
        reason="Windows resolver branch",
    )
    def test_valid_preference_wins_over_auto(self, tmp_path, monkeypatch):
        """Preference file with a valid launcher must win even when
        auto-detect would also succeed."""
        import json as _json
        prefs = self._patch_prefs(monkeypatch, tmp_path)
        prefs.parent.mkdir(parents=True)
        launcher = tmp_path / "py.exe"
        launcher.write_text("")
        prefs.write_text(_json.dumps({
            "schema": "gator-preferences-v1",
            "python": {"windows_py_launcher": str(launcher).replace("\\", "/")},
        }), encoding="utf-8")
        # Auto-detect would ALSO succeed — we're proving preference wins
        other = tmp_path / "other-py.exe"
        other.write_text("")
        import shutil as _shutil
        monkeypatch.setattr(_shutil, "which", lambda n: str(other))
        result = gator_core.resolve_python_launcher_for_hooks()
        assert result["status"] == "resolved"
        assert result["source"] == "user"
        assert "py.exe" in result["path"]
        assert "other-py.exe" not in result["path"]

    @pytest.mark.skipif(
        __import__("os").name != "nt",
        reason="Windows resolver branch",
    )
    def test_malformed_preference_refuses_no_fallback(self, tmp_path, monkeypatch):
        """LOAD-BEARING (Finding 1 pin at the resolver): a malformed
        preferences file must degrade with source=user, NEVER silently
        fall through to auto-detect. If auto WOULD succeed on this
        machine, that's irrelevant — the user configured the file and
        it's broken; falling back would defeat their override."""
        prefs = self._patch_prefs(monkeypatch, tmp_path)
        prefs.parent.mkdir(parents=True)
        prefs.write_text("{malformed", encoding="utf-8")
        # Auto-detect WOULD succeed — proving the refusal doesn't fall through
        launcher = tmp_path / "py.exe"
        launcher.write_text("")
        import shutil as _shutil
        monkeypatch.setattr(_shutil, "which", lambda n: str(launcher))
        result = gator_core.resolve_python_launcher_for_hooks()
        assert result["status"] == "degraded"
        assert result["source"] == "user"
        assert result["path"] is None
        assert "malformed" in result["reason"]
        assert "loud refusal" in result["reason"]

    @pytest.mark.skipif(
        __import__("os").name != "nt",
        reason="Windows resolver branch",
    )
    def test_invalid_preference_refuses_no_fallback(self, tmp_path, monkeypatch):
        """LOAD-BEARING: a valid-JSON but points-at-nonexistent-file
        preference must degrade with source=user, NEVER fall through."""
        import json as _json
        prefs = self._patch_prefs(monkeypatch, tmp_path)
        prefs.parent.mkdir(parents=True)
        prefs.write_text(_json.dumps({
            "schema": "gator-preferences-v1",
            "python": {"windows_py_launcher": "C:/nowhere/does-not-exist/py.exe"},
        }), encoding="utf-8")
        # Auto-detect WOULD succeed
        launcher = tmp_path / "py.exe"
        launcher.write_text("")
        import shutil as _shutil
        monkeypatch.setattr(_shutil, "which", lambda n: str(launcher))
        result = gator_core.resolve_python_launcher_for_hooks()
        assert result["status"] == "degraded"
        assert result["source"] == "user"
        assert "invalid" in result["reason"]
        assert "file-not-found" in result["reason"]

    @pytest.mark.skipif(
        __import__("os").name != "nt",
        reason="Windows resolver branch",
    )
    def test_allow_for_hook_shebang_false_falls_through_to_auto(
        self, tmp_path, monkeypatch
    ):
        """LOAD-BEARING (2026-08-29 whiteboard finding 2): the
        `allow_for_hook_shebang: false` opt-out was documented in the
        schema, fixture, and operator procedure but the resolver
        ignored it. With this pin, a launcher preference marked
        opt-out falls through to auto-detect (the operator is signaling
        the launcher is valid for other uses but not for shebang).

        Both launchers use the mandated `py.exe` basename in different
        subdirectories — the basename check would reject `auto-py.exe`
        etc. even without the opt-out logic."""
        import json as _json
        prefs = self._patch_prefs(monkeypatch, tmp_path)
        prefs.parent.mkdir(parents=True)
        opted_dir = tmp_path / "opted-out"
        opted_dir.mkdir()
        opted_launcher = opted_dir / "py.exe"
        opted_launcher.write_text("")
        prefs.write_text(_json.dumps({
            "schema": "gator-preferences-v1",
            "python": {
                "windows_py_launcher": str(opted_launcher).replace("\\", "/"),
                "allow_for_hook_shebang": False,
            },
        }), encoding="utf-8")
        # Auto-detect finds a DIFFERENT launcher in a different subdir
        auto_dir = tmp_path / "auto"
        auto_dir.mkdir()
        auto_launcher = auto_dir / "py.exe"
        auto_launcher.write_text("")
        import shutil as _shutil
        monkeypatch.setattr(_shutil, "which", lambda n: str(auto_launcher))
        result = gator_core.resolve_python_launcher_for_hooks()
        assert result["status"] == "resolved"
        assert result["source"] == "auto", (
            f"opt-out must fall through to auto, not use user preference. "
            f"Got: {result!r}"
        )
        assert "/auto/py.exe" in result["path"]
        assert "/opted-out/" not in result["path"]
        # Audit trail must record the opt-out so it's inspectable
        pref_check = next(
            c for c in result["checked"] if c["tier"] == "preference-file"
        )
        assert "opted-out" in pref_check["outcome"]

    @pytest.mark.skipif(
        __import__("os").name != "nt",
        reason="Windows resolver branch",
    )
    def test_allow_for_hook_shebang_true_default_uses_preference(
        self, tmp_path, monkeypatch
    ):
        """The opt-out field defaults true — a valid launcher without
        the field set must still be used."""
        import json as _json
        prefs = self._patch_prefs(monkeypatch, tmp_path)
        prefs.parent.mkdir(parents=True)
        launcher = tmp_path / "py.exe"
        launcher.write_text("")
        prefs.write_text(_json.dumps({
            "schema": "gator-preferences-v1",
            "python": {"windows_py_launcher": str(launcher).replace("\\", "/")},
        }), encoding="utf-8")
        result = gator_core.resolve_python_launcher_for_hooks()
        assert result["status"] == "resolved"
        assert result["source"] == "user"

    @pytest.mark.skipif(
        __import__("os").name != "nt",
        reason="Windows resolver branch",
    )
    def test_present_preference_but_no_python_section_falls_through(
        self, tmp_path, monkeypatch
    ):
        """Sketch B forward-compat pin: a preferences file that exists
        for other reasons (e.g. future `hooks:` section) but has no
        python.windows_py_launcher must fall through to auto-detect."""
        import json as _json
        prefs = self._patch_prefs(monkeypatch, tmp_path)
        prefs.parent.mkdir(parents=True)
        prefs.write_text(_json.dumps({
            "schema": "gator-preferences-v1",
            "hooks": {"_": "reserved"},
        }), encoding="utf-8")
        launcher = tmp_path / "py.exe"
        launcher.write_text("")
        import shutil as _shutil
        monkeypatch.setattr(_shutil, "which", lambda n: str(launcher))
        result = gator_core.resolve_python_launcher_for_hooks()
        assert result["status"] == "resolved"
        assert result["source"] == "auto"

    @pytest.mark.skipif(
        __import__("os").name != "nt",
        reason="Windows resolver branch",
    )
    def test_empty_launcher_refuses_no_fallback_even_if_reader_bypassed(
        self, tmp_path, monkeypatch
    ):
        """Belt-and-suspenders (2026-08-29 whiteboard follow-up
        finding): the reader now rejects `windows_py_launcher: ""`
        (returns malformed), so this branch shouldn't fire in normal
        flow. This test bypasses the reader — synthesizes a `present`
        result carrying an empty launcher — to prove the resolver
        would ALSO refuse loudly if the empty string ever reached it.

        The pre-fix resolver did `if not launcher:` which lumped `""`
        with None and silently fell through to auto-detect. The post-fix
        resolver does `if launcher is None:` — an empty string now
        routes through `_validate_launcher_candidate` which returns
        `empty-path` and the resolver refuses with `source="user"`."""
        monkeypatch.setattr(gator_core, "read_preferences", lambda: {
            "state": "present",
            "data": {
                "schema": "gator-preferences-v1",
                "python": {"windows_py_launcher": ""},
            },
        })
        # Auto-detect WOULD succeed — proving no fallback
        launcher = tmp_path / "py.exe"
        launcher.write_text("")
        import shutil as _shutil
        monkeypatch.setattr(_shutil, "which", lambda n: str(launcher))
        result = gator_core.resolve_python_launcher_for_hooks()
        assert result["status"] == "degraded", (
            f"empty launcher must refuse (source=user), not fall through. "
            f"Got: {result!r}"
        )
        assert result["source"] == "user"
        assert result["path"] is None
        assert "empty-path" in result["reason"] or "invalid" in result["reason"]

    @pytest.mark.skipif(
        __import__("os").name != "nt",
        reason="Windows resolver branch",
    )
    def test_all_tiers_fail_returns_degraded_none_with_checked_trail(
        self, tmp_path, monkeypatch
    ):
        """No launcher anywhere → degraded, source=none, checked array
        populated with every tier the resolver tried.

        On the developer's machine C:\\Windows\\py.exe may actually
        exist (system-wide Python install), so we also patch os.path.isfile
        to force the auto-detect probes to fail. Preserves the validator's
        distinction between "exists at path" vs "well-known location" —
        _validate_launcher_candidate itself is unpatched (its own tests
        cover it).
        """
        self._patch_prefs(monkeypatch, tmp_path)
        import shutil as _shutil
        import os as _os
        monkeypatch.setattr(_shutil, "which", lambda n: None)
        # Force ALL isfile checks the resolver makes to say False. The
        # reader also uses .exists() for the preferences file check, which
        # is unaffected because we pointed PREFERENCES_FILE at tmp_path.
        monkeypatch.setattr(_os.path, "isfile", lambda p: False)
        result = gator_core.resolve_python_launcher_for_hooks()
        assert result["status"] == "degraded"
        assert result["source"] == "none"
        assert result["path"] is None
        assert any(c["tier"] == "preference-file" for c in result["checked"])
        assert any(c["tier"] == "shutil-which" for c in result["checked"])
        assert "preferences.json" in result["reason"]
        assert "configure-machine-preferences" in result["reason"]
