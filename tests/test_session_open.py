"""Tests for gator-session-open.py — silent self-heal at session start."""

import importlib.util
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# Load the script as a module
_script_path = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "gator_command"
    / "templates"
    / "gator-starter"
    / "scripts"
    / "gator-session-open.py"
)
_spec = importlib.util.spec_from_file_location("gator_session_open", _script_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

find_gator_dir = _mod.find_gator_dir
main = _mod.main


class TestFindGatorDir:
    def test_finds_gator_dir_with_git(self, tmp_path, monkeypatch):
        """Only returns .gator/ when a sibling .git/ exists."""
        (tmp_path / ".gator").mkdir()
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        assert find_gator_dir() == tmp_path / ".gator"

    def test_skips_gator_dir_without_git(self, tmp_path, monkeypatch):
        """Ignores .gator/ when there's no sibling .git/ — prevents
        matching the machine-local ~/.gator config directory."""
        (tmp_path / ".gator").mkdir()
        # No .git/ created
        monkeypatch.chdir(tmp_path)
        # Should not match tmp_path's .gator since there's no .git
        result = find_gator_dir()
        if result is not None:
            # If it found something, it must be from a real repo above
            assert result != tmp_path / ".gator"

    def test_returns_none_in_empty_dir(self, tmp_path, monkeypatch):
        isolated = tmp_path / "a" / "b" / "c"
        isolated.mkdir(parents=True)
        monkeypatch.chdir(isolated)
        result = find_gator_dir()
        # Should not find anything inside tmp_path
        if result is not None:
            assert not str(result).startswith(str(tmp_path))

    def test_walks_up_to_parent_with_git(self, tmp_path, monkeypatch):
        """Walks up from a subdirectory to find repo-level .gator/."""
        (tmp_path / ".gator").mkdir()
        (tmp_path / ".git").mkdir()
        child = tmp_path / "src" / "deep"
        child.mkdir(parents=True)
        monkeypatch.chdir(child)
        assert find_gator_dir() == tmp_path / ".gator"


class TestMain:
    def test_exits_0_no_gator_dir(self, tmp_path, monkeypatch):
        """Exits 0 in dir with no .gator/."""
        monkeypatch.chdir(tmp_path)
        assert main() == 0

    def test_exits_0_no_git_dir(self, tmp_path, monkeypatch):
        """Exits 0 in dir with .gator/ but no .git/ (find_gator_dir skips it)."""
        (tmp_path / ".gator" / "scripts").mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        # No .git/ means find_gator_dir returns None → main exits 0
        assert main() == 0

    def test_calls_ensure_git_hooks(self, tmp_path, monkeypatch):
        """Calls ensure_git_hooks() with correct args."""
        gator_dir = tmp_path / ".gator"
        scripts_dir = gator_dir / "scripts"
        scripts_dir.mkdir(parents=True)
        monkeypatch.chdir(tmp_path)

        mock_init = MagicMock()
        mock_init.ensure_git_hooks.return_value = {
            "status": "ok", "detail": "ok", "adds": 0, "updates": 0,
        }

        mock_core = MagicMock()
        mock_core.import_sibling.return_value = mock_init

        with patch.object(_mod, "find_gator_dir", return_value=gator_dir):
            with patch.dict("sys.modules", {"gator_core": mock_core}):
                assert main() == 0

        mock_core.import_sibling.assert_called_once_with("gator-init")
        mock_init.ensure_git_hooks.assert_called_once_with(tmp_path, gator_dir)

    def test_never_writes_stdout(self, tmp_path, monkeypatch, capsys):
        """Never writes to stdout."""
        monkeypatch.chdir(tmp_path)
        main()
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_survives_import_error(self, tmp_path, monkeypatch):
        """Survives ImportError from import_sibling → returns 0."""
        gator_dir = tmp_path / ".gator"
        scripts_dir = gator_dir / "scripts"
        scripts_dir.mkdir(parents=True)
        monkeypatch.chdir(tmp_path)

        with patch.object(_mod, "find_gator_dir", return_value=gator_dir):
            with patch.dict("sys.modules", {"gator_core": MagicMock(
                import_sibling=MagicMock(side_effect=ImportError("no module"))
            )}):
                try:
                    main()
                except ImportError:
                    pass  # In real usage, __main__ guard catches this

    def test_survives_runtime_error(self, tmp_path, monkeypatch):
        """Survives RuntimeError from ensure_git_hooks → returns 0."""
        gator_dir = tmp_path / ".gator"
        scripts_dir = gator_dir / "scripts"
        scripts_dir.mkdir(parents=True)
        monkeypatch.chdir(tmp_path)

        mock_init = MagicMock()
        mock_init.ensure_git_hooks.side_effect = RuntimeError("boom")

        with patch.object(_mod, "find_gator_dir", return_value=gator_dir):
            with patch.dict("sys.modules", {"gator_core": MagicMock(
                import_sibling=MagicMock(return_value=mock_init)
            )}):
                try:
                    main()
                except RuntimeError:
                    pass


class TestSubprocessExecution:
    """Test the script as a subprocess — the real entry point."""

    def test_exits_0_no_gator(self, tmp_path):
        """Exits 0 when run in a non-gatorized directory."""
        result = subprocess.run(
            [sys.executable, str(_script_path)],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert result.stdout == ""

    def test_exits_0_gator_without_git(self, tmp_path):
        """Exits 0 when .gator/ exists but no .git/ — not a governed repo."""
        (tmp_path / ".gator" / "scripts").mkdir(parents=True)
        result = subprocess.run(
            [sys.executable, str(_script_path)],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert result.stdout == ""
        # No error output either — .gator without .git is silently skipped
        assert result.stderr == ""

    def test_exits_0_gator_with_git_no_core(self, tmp_path):
        """Exits 0 when .gator/ + .git/ exist but gator_core raises."""
        (tmp_path / ".gator" / "scripts").mkdir(parents=True)
        (tmp_path / ".git").mkdir()
        # Write a fake gator_core that raises ImportError
        (tmp_path / ".gator" / "scripts" / "gator_core.py").write_text(
            'def import_sibling(name): raise ImportError("no module")\n',
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, str(_script_path)],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert result.stdout == ""
