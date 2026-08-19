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
    def test_windows_uses_py_launcher(self):
        """Windows shebang uses the native py launcher."""
        with patch.object(os, "name", "nt"):
            assert update._hook_shebang() == "#!C:/Windows/py.exe -3"

    def test_unix_uses_python3(self):
        """Unix shebang uses `python3` (guaranteed Python 3 command)."""
        with patch.object(os, "name", "posix"):
            assert update._hook_shebang() == "#!/usr/bin/env python3"


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
        """On Windows, generated hooks use the py launcher in shebang."""
        hooks = update.build_git_hook_wrappers()
        for name, content in hooks.items():
            assert content.startswith("#!C:/Windows/py.exe -3\n")

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

    def test_no_dispatcher_generates_pre_phase3_stub(self):
        """Standalone template runs (no CLI importable) generate stubs
        with NO dispatcher branch — byte-shape of the pre-Phase-3 era."""
        with patch.object(update, "_installed_dispatcher_path", return_value=None):
            hooks = update.build_git_hook_wrappers()
            for content in hooks.values():
                assert "runtime-pin.json" not in content
                assert "gator-hook.py" not in content

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
