"""
Tests for hook generation and installation in gator-update.py.

Covers build_git_hook_wrappers(), plan_hook_updates(), and
install_git_hooks() — including interpreter paths with spaces,
backslashes, platform-specific shebangs, and standard paths.
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from conftest import load_script

update = load_script("gator-update")


class TestHookShebang:
    """v2.10.0 Phase 2: `_hook_shebang()` is now a thin wrapper around
    `gator_core.resolve_python_launcher_for_hooks()`. Tests target the
    resolver seam via `update.resolve_python_launcher_for_hooks` (the
    name gator-update.py imports from gator_core at call time)."""

    def _mock_resolver(self, monkeypatch, result):
        """Patch the resolver where _hook_shebang() looks it up.

        `_hook_shebang` does `from gator_core import resolve_python_launcher_for_hooks`
        inside the function, so patching gator_core directly is the
        durable seam.
        """
        import gator_core
        monkeypatch.setattr(
            gator_core, "resolve_python_launcher_for_hooks",
            lambda: result,
        )

    def test_unix_uses_python3(self):
        """Unix shebang uses `python3` (guaranteed Python 3 command).
        Resolver is not consulted on non-Windows."""
        with patch.object(os, "name", "posix"):
            assert update._hook_shebang() == "#!/usr/bin/env python3"

    def test_windows_resolved_returns_shebang_with_path(self, monkeypatch):
        """Resolver returns a resolved result → _hook_shebang emits the
        `#!<path> -3` line unchanged."""
        with patch.object(os, "name", "nt"):
            self._mock_resolver(monkeypatch, {
                "status": "resolved",
                "source": "auto",
                "path": "C:/Windows/py.exe",
                "shebang_safe": True,
                "reason": "test",
                "checked": [],
            })
            shebang = update._hook_shebang()
        assert shebang == "#!C:/Windows/py.exe -3"

    def test_windows_resolved_from_user_preference(self, monkeypatch):
        """When the resolver reports source=user (preference file), the
        shebang uses that path — Phase 2 machine-preferences wiring."""
        with patch.object(os, "name", "nt"):
            self._mock_resolver(monkeypatch, {
                "status": "resolved",
                "source": "user",
                "path": "C:/Users/dev/AppData/Local/Programs/Python/Launcher/py.exe",
                "shebang_safe": True,
                "reason": "using launcher from preferences",
                "checked": [],
            })
            shebang = update._hook_shebang()
        assert shebang == (
            "#!C:/Users/dev/AppData/Local/Programs/Python/Launcher/py.exe -3"
        )

    def test_windows_degraded_raises_with_reason_and_checked_trail(self, monkeypatch):
        """Resolver-degraded → HookShebangUnresolvable whose message
        includes the resolver's `reason` AND a Checked: audit trail
        rendering the tiers the resolver tried."""
        with patch.object(os, "name", "nt"):
            self._mock_resolver(monkeypatch, {
                "status": "degraded",
                "source": "none",
                "path": None,
                "shebang_safe": False,
                "reason": "No spaceless launcher found on this machine.",
                "checked": [
                    {"tier": "preference-file", "path": "~/.gator/preferences.json", "outcome": "absent"},
                    {"tier": "shutil-which", "path": "", "outcome": "not-on-PATH"},
                    {"tier": "localappdata", "path": "C:/x/py.exe", "outcome": "invalid: file-not-found"},
                    {"tier": "windows-dir", "path": "C:\\Windows\\py.exe", "outcome": "invalid: file-not-found"},
                ],
            })
            with pytest.raises(update.HookShebangUnresolvable) as exc_info:
                update._hook_shebang()
        msg = str(exc_info.value)
        assert "No spaceless launcher found" in msg
        assert "Checked:" in msg
        assert "preference-file" in msg
        assert "shutil-which" in msg
        assert "localappdata" in msg
        assert "windows-dir" in msg

    def test_windows_malformed_preference_refuses_no_fallback(self, monkeypatch):
        """LOAD-BEARING (Finding 1 pin at the resolver-wrapper layer):
        the resolver signals malformed with source=user; `_hook_shebang`
        raises. If auto-detect also would have succeeded on this
        machine, that result is IRRELEVANT — the user configured a
        broken preference and the refusal must not silently fall back.
        The resolver enforces this; this test pins the wrapper's
        contract that a degraded result of any kind raises."""
        with patch.object(os, "name", "nt"):
            self._mock_resolver(monkeypatch, {
                "status": "degraded",
                "source": "user",
                "path": None,
                "shebang_safe": False,
                "reason": (
                    "~/.gator/preferences.json is malformed "
                    "(parse-error: Expecting property name enclosed in double quotes). "
                    "This is a loud refusal — never silently fall back."
                ),
                "checked": [
                    {"tier": "preference-file",
                     "path": "~/.gator/preferences.json",
                     "outcome": "malformed: parse-error: ..."},
                ],
            })
            with pytest.raises(update.HookShebangUnresolvable) as exc_info:
                update._hook_shebang()
        msg = str(exc_info.value)
        assert "malformed" in msg
        assert "loud refusal" in msg
        assert "preferences.json" in msg

    def test_windows_invalid_preference_refuses_no_fallback(self, monkeypatch):
        """LOAD-BEARING: preference points at a nonexistent file. Even
        though auto-detect would find `C:\\Windows\\py.exe` in the real
        world, the resolver refuses (source=user); wrapper raises."""
        with patch.object(os, "name", "nt"):
            self._mock_resolver(monkeypatch, {
                "status": "degraded",
                "source": "user",
                "path": None,
                "shebang_safe": False,
                "reason": (
                    "~/.gator/preferences.json python.windows_py_launcher "
                    "is invalid (file-not-found): 'C:/nowhere/py.exe'. "
                    "Loud refusal."
                ),
                "checked": [
                    {"tier": "preference-file",
                     "path": "C:/nowhere/py.exe",
                     "outcome": "invalid: file-not-found"},
                ],
            })
            with pytest.raises(update.HookShebangUnresolvable):
                update._hook_shebang()


class TestBuildGitHookWrappers:
    def test_returns_three_hooks(self):
        """Generates wrappers for pre-commit, commit-msg, and post-commit."""
        hooks = update.build_git_hook_wrappers()
        assert set(hooks.keys()) == {"pre-commit", "commit-msg", "post-commit"}

    def test_shebang_uses_platform_launcher(self):
        """Shebang uses the platform-correct launcher."""
        hooks = update.build_git_hook_wrappers()
        expected_shebang = update._hook_shebang()
        for name, content in hooks.items():
            assert content.startswith(f"{expected_shebang}\n"), (
                f"{name} shebang should be {expected_shebang}, got: {content.splitlines()[0]}"
            )

    def test_shebang_never_embeds_runtime_interpreter_path(self):
        """Shebang must not embed sys.executable."""
        hooks = update.build_git_hook_wrappers()
        python_path = sys.executable.replace("\\", "/")
        for name, content in hooks.items():
            shebang = content.splitlines()[0]
            assert python_path not in shebang, (
                f"{name} shebang must not embed literal interpreter path"
            )

    def test_subprocess_uses_exact_path(self):
        """subprocess.call uses sys.executable, not the shebang path."""
        python_path = sys.executable.replace("\\", "/")
        hooks = update.build_git_hook_wrappers()
        for name, content in hooks.items():
            assert f'r"{python_path}"' in content, (
                f"{name} should use exact interpreter path in subprocess.call"
            )

    def test_phases_correct(self):
        """Each hook calls the correct gator-pre-commit.py phase."""
        hooks = update.build_git_hook_wrappers()
        assert '"validate"' in hooks["pre-commit"]
        assert '"trailers"' in hooks["commit-msg"]
        assert '"cleanup"' in hooks["post-commit"]

    def test_commit_msg_passes_argv(self):
        """commit-msg hook passes sys.argv[1] as positional msg_file arg."""
        hooks = update.build_git_hook_wrappers()
        assert "sys.argv[1]" in hooks["commit-msg"]
        assert "--msg-file" not in hooks["commit-msg"]  # positional, not flag
        assert "sys.argv[1]" not in hooks["pre-commit"]
        assert "sys.argv[1]" not in hooks["post-commit"]

    @patch.object(sys, "executable", "C:/Program Files/Python313/python.exe")
    def test_spaces_in_path(self):
        """Paths with spaces work: shebang stays stable, subprocess uses raw string."""
        hooks = update.build_git_hook_wrappers()
        for name, content in hooks.items():
            # Shebang must NOT contain the spaced runtime path
            shebang = content.splitlines()[0]
            assert "Program Files" not in shebang, (
                f"{name} shebang must not embed a path with spaces"
            )
            # subprocess.call must use the full path as a raw string
            assert r'r"C:/Program Files/Python313/python.exe"' in content, (
                f"{name} subprocess.call must use exact spaced path"
            )

    @patch.object(sys, "executable", r"C:\Python313\python.exe")
    def test_backslashes_normalized(self):
        """Backslashes in sys.executable are normalized to forward slashes."""
        hooks = update.build_git_hook_wrappers()
        for name, content in hooks.items():
            assert "C:/Python313/python.exe" in content
            # No raw backslashes in the path portion
            assert "C:\\Python313" not in content

    @patch.object(sys, "executable", "/usr/bin/python3")
    def test_unix_path(self):
        """Unix paths work without modification."""
        hooks = update.build_git_hook_wrappers()
        for name, content in hooks.items():
            assert r'r"/usr/bin/python3"' in content

    @patch.object(os, "name", "nt")
    @patch.object(sys, "executable", "C:/Python313/python.exe")
    def test_windows_platform_shebang(self):
        """On Windows, generated hooks use a resolved spaceless py.exe
        launcher path in the shebang. The exact path depends on the
        machine's install; the shape is `#!<spaceless>/py.exe -3\\n`.

        Patches the resolver directly rather than the real `os.path.isfile`
        + `shutil.which` — on Linux CI those helpers still see real Linux
        paths regardless of a patched `os.name`, so a `C:\\Windows\\...`
        candidate would fail `os.path.isabs` (Linux-side) before reaching
        the space check. Patching the resolver seam skirts the whole
        platform-conditional path-check chain."""
        import gator_core
        fake_resolved = {
            "status": "resolved",
            "source": "auto",
            "path": "C:/Windows/py.exe",
            "shebang_safe": True,
            "reason": "test",
            "checked": [],
        }
        with patch.object(gator_core, "resolve_python_launcher_for_hooks",
                          return_value=fake_resolved):
            hooks = update.build_git_hook_wrappers()
        for name, content in hooks.items():
            first = content.splitlines()[0]
            assert first.startswith("#!")
            assert first.endswith(" -3")
            assert "py.exe" in first
            assert " " not in first[2:-3], (
                f"{name} shebang path must be spaceless (POSIX cannot quote): {first!r}"
            )

    @patch.object(os, "name", "posix")
    @patch.object(sys, "executable", "/usr/bin/python3")
    def test_unix_platform_shebang(self):
        """On Unix, generated hooks use python3 in shebang."""
        hooks = update.build_git_hook_wrappers()
        for name, content in hooks.items():
            assert content.startswith("#!/usr/bin/env python3\n")


class TestPlanHookUpdates:
    def test_missing_hooks_planned_as_add(self, mock_gator_repo):
        """Hooks not in .git/hooks/ are planned as 'add'."""
        repo_root, gator_dir = mock_gator_repo
        # Remove the existing pre-commit hook
        (repo_root / ".git" / "hooks" / "pre-commit").unlink()

        plan = update.plan_hook_updates(gator_dir, repo_root)
        actions = {name: action for name, action in plan}

        assert actions["pre-commit"] == "add"
        assert actions["commit-msg"] == "add"
        assert actions["post-commit"] == "add"

    def test_stale_hooks_planned_as_update(self, mock_gator_repo):
        """Hooks with wrong content are planned as 'update'."""
        repo_root, gator_dir = mock_gator_repo
        # Put a stale hook in the managed hook dir
        hook_dir = update.get_managed_hook_dir(repo_root)
        hook_dir.mkdir(parents=True, exist_ok=True)
        (hook_dir / "pre-commit").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

        with patch.object(update, "hooks_config_needs_update", return_value=False):
            plan = update.plan_hook_updates(gator_dir, repo_root)
        actions = {name: action for name, action in plan}

        assert actions["pre-commit"] == "update"

    def test_current_hooks_unchanged(self, mock_gator_repo):
        """Hooks matching generated content are 'unchanged'."""
        repo_root, gator_dir = mock_gator_repo
        # Install correct hooks first
        update.install_git_hooks(gator_dir, repo_root)

        with patch.object(update, "hooks_config_needs_update", return_value=False):
            plan = update.plan_hook_updates(gator_dir, repo_root)
        actions = {name: action for name, action in plan}

        for name in ("pre-commit", "commit-msg", "post-commit"):
            assert actions[name] == "unchanged"

    def test_no_gator_script_returns_empty(self, mock_gator_repo):
        """Returns empty list when gator-pre-commit.py doesn't exist."""
        repo_root, gator_dir = mock_gator_repo
        (gator_dir / "scripts" / "gator-pre-commit.py").unlink()

        plan = update.plan_hook_updates(gator_dir, repo_root)
        assert plan == []

    def test_no_git_dir_returns_empty(self, tmp_path):
        """Returns empty list when .git doesn't exist."""
        gator_dir = tmp_path / ".gator"
        gator_dir.mkdir()
        (gator_dir / "scripts").mkdir()
        (gator_dir / "scripts" / "gator-pre-commit.py").write_text("# stub\n")

        plan = update.plan_hook_updates(gator_dir, tmp_path)
        assert plan == []

    @pytest.mark.skipif(
        os.name != "nt",
        reason="Uses patch.object(os, 'name', 'nt') to reach Windows code paths "
               "that then call Path(...); on non-Windows, pathlib refuses to "
               "instantiate WindowsPath with NotImplementedError. Windows CI "
               "matrix cell covers this behavior natively without the mock.",
    )
    def test_windows_config_drift_planned_as_update(self, mock_gator_repo):
        """Windows treats stale core.hooksPath as an update even if files match."""
        repo_root, gator_dir = mock_gator_repo
        managed_dir = repo_root / ".git" / "gator-hooks"
        managed_dir.mkdir(parents=True)

        with patch.object(os, "name", "nt"):
            expected = update.build_git_hook_wrappers()
            for name, content in expected.items():
                (managed_dir / name).write_text(content, encoding="utf-8")
            with patch.object(update, "git", return_value=("", False)):
                plan = update.plan_hook_updates(gator_dir, repo_root)

        actions = {name: action for name, action in plan}
        assert actions["pre-commit"] == "update"
        assert actions["commit-msg"] == "update"
        assert actions["post-commit"] == "update"


class TestInstallGitHooks:
    def test_installs_three_hooks(self, mock_gator_repo):
        """Installs all three hook files."""
        repo_root, gator_dir = mock_gator_repo
        count = update.install_git_hooks(gator_dir, repo_root)

        assert count == 3
        hook_dir = update.get_managed_hook_dir(repo_root)
        for name in ("pre-commit", "commit-msg", "post-commit"):
            hook = hook_dir / name
            assert hook.exists()

    def test_hook_content_matches_wrappers(self, mock_gator_repo):
        """Installed hooks match build_git_hook_wrappers() exactly."""
        repo_root, gator_dir = mock_gator_repo
        update.install_git_hooks(gator_dir, repo_root)
        expected = update.build_git_hook_wrappers()

        hook_dir = update.get_managed_hook_dir(repo_root)
        for name, expected_content in expected.items():
            actual = (hook_dir / name).read_text(encoding="utf-8")
            assert actual == expected_content

    def test_no_git_dir_returns_zero(self, tmp_path):
        """Returns 0 when .git doesn't exist."""
        gator_dir = tmp_path / ".gator"
        gator_dir.mkdir()
        count = update.install_git_hooks(gator_dir, tmp_path)
        assert count == 0

    @patch.object(sys, "executable", "C:/Program Files/Python313/python.exe")
    def test_installed_hooks_handle_spaces(self, mock_gator_repo):
        """Hooks installed with a spaced path keep a stable shebang and correct subprocess call."""
        repo_root, gator_dir = mock_gator_repo
        update.install_git_hooks(gator_dir, repo_root)

        hook_dir = update.get_managed_hook_dir(repo_root)
        content = (hook_dir / "pre-commit").read_text(encoding="utf-8")
        assert content.startswith(update._hook_shebang())
        assert r'r"C:/Program Files/Python313/python.exe"' in content

    @pytest.mark.skipif(
        os.name != "nt",
        reason="Uses patch.object(os, 'name', 'nt') to reach Windows code paths "
               "that then call Path(...); on non-Windows, pathlib refuses to "
               "instantiate WindowsPath with NotImplementedError. Windows CI "
               "matrix cell covers this behavior natively without the mock.",
    )
    def test_windows_installs_into_managed_hook_dir(self, mock_gator_repo):
        """Windows installs into .git/gator-hooks and sets core.hooksPath."""
        repo_root, gator_dir = mock_gator_repo

        def fake_git(*args, **kwargs):
            if args[:3] == ("config", "--local", "core.hooksPath"):
                return "", True
            if args[:3] == ("config", "--local", "--get"):
                return ".git/gator-hooks", True
            return "", False

        with patch.object(os, "name", "nt"):
            with patch.object(update, "git", side_effect=fake_git):
                count = update.install_git_hooks(gator_dir, repo_root)

        assert count == 3
        for name in ("pre-commit", "commit-msg", "post-commit"):
            assert (repo_root / ".git" / "gator-hooks" / name).exists()

    @pytest.mark.skipif(
        os.name != "nt",
        reason="Uses patch.object(os, 'name', 'nt') to reach Windows code paths "
               "that then call Path(...); on non-Windows, pathlib refuses to "
               "instantiate WindowsPath with NotImplementedError. Windows CI "
               "matrix cell covers this behavior natively without the mock.",
    )
    def test_probe_dirs_include_legacy_fallback_on_windows(self, tmp_path):
        """Windows probes managed hooks first, then legacy .git/hooks."""
        repo_root = tmp_path
        with patch.object(os, "name", "nt"):
            probe_dirs = update.get_hook_probe_dirs(repo_root)
        assert probe_dirs == [
            repo_root / ".git" / "gator-hooks",
            repo_root / ".git" / "hooks",
        ]


class TestUnresolvableShebangRefusal:
    """When `_hook_shebang()` cannot find a spaceless launcher on
    Windows, the caller functions must refuse loudly (return 0 / [])
    with the exception's message on stderr, never silently write a
    broken hook. Regression pins for the 2026-08-28 fix that converted
    the pre-existing silent-hook-install-succeeds-but-hook-broken
    failure mode into a discoverable install-time error."""

    def test_install_git_hooks_returns_zero_when_shebang_unresolvable(
        self, mock_gator_repo, capsys
    ):
        repo_root, gator_dir = mock_gator_repo
        with patch.object(update, "_hook_shebang",
                          side_effect=update.HookShebangUnresolvable(
                              "no launcher for test")):
            count = update.install_git_hooks(gator_dir, repo_root)
        assert count == 0
        captured = capsys.readouterr()
        assert "cannot install git hooks" in captured.err
        assert "no launcher for test" in captured.err

    def test_plan_hook_updates_returns_empty_when_shebang_unresolvable(
        self, mock_gator_repo, capsys
    ):
        repo_root, gator_dir = mock_gator_repo
        with patch.object(update, "_hook_shebang",
                          side_effect=update.HookShebangUnresolvable(
                              "no launcher for test")):
            plan = update.plan_hook_updates(gator_dir, repo_root)
        assert plan == []
        captured = capsys.readouterr()
        assert "cannot plan git hook updates" in captured.err
        assert "no launcher for test" in captured.err


class TestPinAwareWrappers:
    """Runtime-split Phase 3: stubs gain a dispatcher-first branch on
    pinned repos, and fall through to the pre-Phase-3 invocation
    otherwise (pre-split repos untouched by construction)."""

    def test_dispatcher_branch_present_when_resolvable(self):
        """When the dispatcher path resolves, generated stubs carry the
        pin-aware branch. Patched rather than relying on the environment:
        CI's clean venv has no installed gator_command (2026-08-19 CI
        failure — these tests must not depend on install state)."""
        with patch.object(update, "_installed_dispatcher_path",
                          return_value="/fake/site-packages/gator_command/scripts/gator-hook.py"):
            hooks = update.build_git_hook_wrappers(
                gator_script=".gator/.includes/scripts/gator-pre-commit.py")
        for name, content in hooks.items():
            assert 'runtime-pin.json' in content, name
            assert 'gator-hook.py' in content, name
            assert f'"{name}"' in content, name

    def test_fallback_branch_always_present(self):
        """The pre-Phase-3 repo-script invocation survives verbatim as
        the fallthrough — pin absent or dispatcher gone → old behavior."""
        hooks = update.build_git_hook_wrappers(
            gator_script=".gator/.includes/scripts/gator-pre-commit.py")
        assert '"--phase", "validate"' in hooks["pre-commit"]
        assert '"--phase", "trailers", sys.argv[1]' in hooks["commit-msg"]
        assert '"--phase", "cleanup"' in hooks["post-commit"]
        for content in hooks.values():
            assert 'warning mode' in content

    def test_no_dispatcher_generates_stub_without_dispatch_branch(self):
        """Standalone template runs (no CLI importable) generate stubs
        with NO dispatcher branch. Phase 4: the fail-closed pin-refuse
        branch is ALWAYS present — a pinned, script-less repo must never
        commit ungoverned even when this stub was generated without a
        resolvable dispatcher."""
        with patch.object(update, "_installed_dispatcher_path", return_value=None):
            hooks = update.build_git_hook_wrappers()
            for content in hooks.values():
                assert "gator-hook.py" not in content
                assert "runtime-pin.json" in content  # the refuse branch
            assert "sys.exit(1)" in hooks["pre-commit"]
            assert "sys.exit(1)" not in hooks["post-commit"]

    def test_pin_refuse_branch_blocking_matrix(self):
        """Phase 4: pinned + script-missing fails closed ONLY for
        pre-commit; commit-msg/post-commit warn-and-proceed."""
        with patch.object(update, "_installed_dispatcher_path",
                          return_value="/fake/gator-hook.py"):
            hooks = update.build_git_hook_wrappers()
        pre = hooks["pre-commit"]
        assert "pipx install gator-command" in pre
        refuse_idx = pre.index("not os.path.isfile(script)")
        assert "sys.exit(1)" in pre[refuse_idx:]
        for name in ("commit-msg", "post-commit"):
            assert "pipx install gator-command" in hooks[name]
            assert "sys.exit(1)" not in hooks[name]

    def test_dispatcher_branch_forwards_argv(self):
        """The dispatcher call forwards sys.argv[1:] (commit-msg needs
        the msg-file argument)."""
        with patch.object(update, "_installed_dispatcher_path",
                          return_value="/fake/site-packages/gator_command/scripts/gator-hook.py"):
            hooks = update.build_git_hook_wrappers()
        assert "+ sys.argv[1:]" in hooks["commit-msg"]

    def test_plan_hook_updates_with_pin_but_no_script(self, mock_gator_repo):
        """S5 forward-compat: a pinned repo whose repo-resident script is
        gone (post-Phase-4 state) still plans stub installs."""
        repo_root, gator_dir = mock_gator_repo
        script = gator_dir / "scripts" / "gator-pre-commit.py"
        if script.exists():
            script.unlink()
        (gator_dir / "runtime-pin.json").write_text(
            '{"schema": "gator-runtime-pin-v1", "runtime_version": "9.9.9",'
            ' "pinned_at": "2026-08-19T00:00:00Z", "manifest": {}}',
            encoding="utf-8")
        plan = update.plan_hook_updates(gator_dir, repo_root)
        assert len(plan) == 3

    def test_plan_hook_updates_no_script_no_pin_is_empty(self, mock_gator_repo):
        repo_root, gator_dir = mock_gator_repo
        script = gator_dir / "scripts" / "gator-pre-commit.py"
        if script.exists():
            script.unlink()
        assert update.plan_hook_updates(gator_dir, repo_root) == []


class TestEnforcerReviewResolution:
    """Phase 4d: enforcer-review resolves the repo from CWD and the
    user config from the .gator/ root (canonical) with legacy fallbacks."""

    def _load_enforcer(self):
        from conftest import load_script
        return load_script("enforcer-review",
                           search_dir=Path(__file__).parent.parent / "src" /
                           "gator_command" / "templates" / "gator-starter" /
                           "scripts")

    def test_config_prefers_canonical_root_location(self, tmp_path, monkeypatch):
        er = self._load_enforcer()
        gator = tmp_path / ".gator"
        (gator / ".includes" / "scripts").mkdir(parents=True)
        (gator / "enforcer-config.json").write_text("{}", encoding="utf-8")
        (gator / ".includes" / "scripts" / "enforcer-config.json").write_text(
            "{}", encoding="utf-8")
        got = er._resolve_config_path(str(tmp_path))
        assert got.replace("\\", "/").endswith(".gator/enforcer-config.json")
        assert ".includes" not in got

    def test_config_falls_back_to_legacy_includes(self, tmp_path):
        er = self._load_enforcer()
        gator = tmp_path / ".gator"
        (gator / ".includes" / "scripts").mkdir(parents=True)
        (gator / ".includes" / "scripts" / "enforcer-config.json").write_text(
            "{}", encoding="utf-8")
        got = er._resolve_config_path(str(tmp_path))
        assert ".includes" in got

    def test_config_default_is_canonical_when_none_exist(self, tmp_path):
        er = self._load_enforcer()
        (tmp_path / ".gator").mkdir()
        got = er._resolve_config_path(str(tmp_path))
        assert got.replace("\\", "/").endswith(".gator/enforcer-config.json")

    def test_repo_root_resolves_from_cwd(self, tmp_path, monkeypatch):
        er = self._load_enforcer()
        (tmp_path / ".gator").mkdir()
        monkeypatch.chdir(tmp_path)
        assert Path(er._resolve_repo_root()) == tmp_path.resolve()

    def test_guidance_strings_name_canonical_config_path(self):
        """Whiteboard 2026-08-20: the script's OWN docstring and operator
        guidance must name the canonical config home — the 4c prose sweep
        covered template .md files but missed strings inside the script,
        leaving recovery guidance pointing at the retired scripts-dir
        location exactly where an operator follows it. Source-text pin in
        the test_hook_modes.py grep-anchored style; resolution-precedence
        code (the legacy probe list) is exempt by construction."""
        src = (Path(__file__).parent.parent / "src" / "gator_command" /
               "templates" / "gator-starter" / "scripts" /
               "enforcer-review.py").read_text(encoding="utf-8")
        offenders = [
            line for line in src.splitlines()
            if ".gator/scripts/enforcer-config.json" in line
            and "os.path.join" not in line  # the legacy probe is legitimate
        ]
        assert offenders == [], f"stale config-path guidance: {offenders}"
        assert ".gator/enforcer-config.json" in src.split('"""')[1], (
            "docstring must name the canonical config home"
        )
        assert "edit .gator/enforcer-config.json" in src, (
            "operator guidance must name the canonical config home"
        )
