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
