"""
Tests for gator-drift.py — policy drift detection.

Drift detection is the governance judgment layer. A false negative
(missing real drift) undermines trust; a false positive (flagging
a current repo) creates noise that erodes adoption.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from conftest import load_script

drift = load_script("gator-drift")


def _make_cp_state(generation=2, policy_date="2026-05-29"):
    """Build a command-post state dict for testing."""
    return {
        "generation": generation,
        "policy_date": policy_date,
        "policy_version": None,
        "git_failed": False,
    }


class TestCheckRepoDrift:
    def test_current_repo(self, mock_gator_repo):
        """A fully current repo has no generation or hook drift.

        Git-dependent checks (branch, trailers) may warn because the
        mock repo has no real git history — that's expected. We verify
        no structural drift findings fire.
        """
        repo_root, _ = mock_gator_repo
        entry = {"name": "test-repo", "path": str(repo_root)}
        result = drift.check_repo_drift(entry, _make_cp_state())
        # Check that structural drift findings (generation, hooks, gatorized)
        # don't fire. Git-dependent findings (branch, trailers, policy-version)
        # may fire because there's no real git in the mock.
        structural_checks = {"generation", "gatorized", "hooks", "constitution"}
        structural_drift = [
            f for f in result["findings"]
            if f["check"] in structural_checks and f["severity"] == "drift"
        ]
        assert len(structural_drift) == 0

    def test_stale_generation(self, mock_gator_repo):
        """Repo at gen 1 when command post is gen 2 triggers generation drift."""
        repo_root, gator_dir = mock_gator_repo
        # Downgrade repo to gen 1
        (gator_dir / ".gator-version").write_text("generation: 1\n")

        entry = {"name": "test-repo", "path": str(repo_root)}
        result = drift.check_repo_drift(entry, _make_cp_state(generation=2))
        checks = {f["check"]: f["severity"] for f in result["findings"]}
        assert checks.get("generation") == "drift"

    def test_no_hooks(self, mock_gator_repo):
        """Repo with no hook sources and no installed hooks triggers drift."""
        repo_root, gator_dir = mock_gator_repo
        # Remove hook sources and installed hooks
        import shutil
        shutil.rmtree(gator_dir / "scripts" / "hooks")
        (gator_dir / "scripts" / "hooks").mkdir()  # empty dir
        hooks_dir = repo_root / ".git" / "hooks"
        (hooks_dir / "pre-commit").unlink()

        entry = {"name": "test-repo", "path": str(repo_root)}
        result = drift.check_repo_drift(entry, _make_cp_state())
        checks = {f["check"]: f["severity"] for f in result["findings"]}
        assert checks.get("hooks") == "drift"

    def test_windows_managed_hook_dir_avoids_false_drift(self, mock_gator_repo):
        """Managed Windows hook dir counts as installed."""
        repo_root, _ = mock_gator_repo
        managed = repo_root / ".git" / "gator-hooks"
        managed.mkdir(parents=True)
        (repo_root / ".git" / "hooks" / "pre-commit").unlink()
        (repo_root / ".git" / "hooks" / "commit-msg").write_text("", encoding="utf-8")
        (managed / "pre-commit").write_text("# hook\n", encoding="utf-8")
        (managed / "commit-msg").write_text("# hook\n", encoding="utf-8")

        entry = {"name": "test-repo", "path": str(repo_root)}
        with patch.object(drift, "_hook_probe_dirs", return_value=[managed, repo_root / ".git" / "hooks"]):
            result = drift.check_repo_drift(entry, _make_cp_state())

        checks = {f["check"]: f["severity"] for f in result["findings"]}
        assert checks.get("hook-installed") is None

    def test_inaccessible_repo(self, tmp_path):
        """Non-existent repo path produces 'drift' severity."""
        entry = {"name": "ghost-repo", "path": str(tmp_path / "nonexistent")}
        result = drift.check_repo_drift(entry, _make_cp_state())
        assert result["accessible"] is False
        assert result["severity"] == "drift"

    def test_no_gator_dir(self, tmp_path):
        """Repo exists but has no .gator/ directory."""
        bare_repo = tmp_path / "bare"
        bare_repo.mkdir()
        entry = {"name": "bare", "path": str(bare_repo)}
        result = drift.check_repo_drift(entry, _make_cp_state())
        assert result["severity"] == "drift"
        checks = [f["check"] for f in result["findings"]]
        assert "gatorized" in checks
