"""
Tests for gator-fleet-report.py — cross-repo governance status.

Fleet-report is the primary read-only fleet scan. Its scan_repo()
and read_gator_state() functions produce the data that drift and
audit both consume.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from conftest import load_script

fleet = load_script("gator-fleet-report")


class TestReadGatorState:
    def test_reads_full_state(self, mock_gator_repo):
        """Reads generation, charters, functions, threads, issues, hooks."""
        repo_root, _ = mock_gator_repo
        state = fleet.read_gator_state(repo_root)
        assert state["gatorized"] is True
        assert state["generation"] == 2
        assert state["charters"] == 1    # core.md (README.md and _template.md excluded)
        assert state["functions"] == 3   # parse_config, validate_input, process_data
        assert state["threads"] >= 1     # design.md
        assert state["has_hooks"] is True

    def test_not_gatorized(self, tmp_path):
        """Returns gatorized=False for a plain directory."""
        state = fleet.read_gator_state(tmp_path)
        assert state["gatorized"] is False
        assert state["generation"] == 0
        assert state["charters"] == 0

    def test_empty_gator_dir(self, tmp_path):
        """Handles a .gator/ with no content files."""
        gator = tmp_path / ".gator"
        gator.mkdir()
        state = fleet.read_gator_state(tmp_path)
        assert state["gatorized"] is True
        assert state["generation"] == 0
        assert state["charters"] == 0

    def test_windows_managed_hook_dir_counts_as_installed(self, mock_gator_repo):
        """Windows managed hook installs count as present."""
        repo_root, _ = mock_gator_repo
        managed = repo_root / ".git" / "gator-hooks"
        managed.mkdir(parents=True)
        (repo_root / ".git" / "hooks" / "pre-commit").unlink()
        (managed / "pre-commit").write_text("# hook\n", encoding="utf-8")

        with patch.object(fleet, "_hook_probe_dirs", return_value=[managed, repo_root / ".git" / "hooks"]):
            state = fleet.read_gator_state(repo_root)

        assert state["hooks_installed"] is True
        assert state["has_hooks"] is True


class TestScanRepo:
    def test_accessible_repo(self, mock_gator_repo):
        """Produces a full report for an accessible governed repo."""
        repo_root, _ = mock_gator_repo
        entry = {"name": "test-repo", "path": str(repo_root)}
        report = fleet.scan_repo(entry)
        assert report["accessible"] is True
        assert report["name"] == "test-repo"
        assert report["charters"] == 1
        assert report["functions"] == 3
        assert report["gatorized"] is True

    def test_inaccessible_repo(self, tmp_path):
        """Produces a minimal report for a missing repo."""
        entry = {"name": "ghost", "path": str(tmp_path / "nonexistent")}
        report = fleet.scan_repo(entry)
        assert report["accessible"] is False
        assert report["name"] == "ghost"
        # Should not have gator state keys
        assert "charters" not in report


class TestPrintJsonReport:
    def test_json_structure(self, mock_gator_repo, capsys):
        """JSON output has expected top-level structure."""
        repo_root, _ = mock_gator_repo
        entry = {"name": "test-repo", "path": str(repo_root)}
        reports = [fleet.scan_repo(entry)]
        fleet.print_json_report(reports)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "version" in data
        assert "timestamp" in data
        assert "repos" in data
        assert "summary" in data
        assert data["summary"]["total"] == 1
        assert data["summary"]["total_charters"] == 1
