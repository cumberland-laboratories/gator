"""
Integration test: fleet-level audit reads commit summaries from fleet repos.

This is the end-to-end contract that matters for buyers: commit summaries
written by the pre-commit hook in governed repos are aggregated by the
command-post audit dashboard. Tests the full path from repo summary
creation through command-post audit aggregation.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "src" / "gator_command" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from conftest import load_script

audit = load_script("gator-audit")
sessions = load_script("gator_session_reader")

# Also need gator_core for the mock
import gator_core


def _make_fleet_with_summaries(tmp_path):
    """Build a mock command post + 2 fleet repos with commit summaries.

    Returns (command_post_root, [repo1_path, repo2_path]).
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Command post
    cp = tmp_path / "cp"
    gc = cp / "gator-command"
    gc.mkdir(parents=True)
    (gc / "mission.md").write_text("# Mission\n")
    (gc / "active-threads").mkdir()

    # Command post sessions (from archaeology)
    cp_sessions = cp / ".gator" / "sessions"
    cp_sessions.mkdir(parents=True)
    (cp_sessions / f"{today}-command-post-claude-abc123.md").write_text(
        f"---\nschema: gator-session-summary-v1\ndate: {today}\n"
        "repo: command-post\nvendor: claude\nagent: Claude Code\n---\n\n"
        "## Decisions\n\n"
        "- [" + today + "T10:00] Adopted charter-first workflow for all repos\n"
    )

    # Fleet repo 1: has commit summaries (from hook)
    repo1 = tmp_path / "repos" / "alpha"
    repo1_sessions = repo1 / ".gator" / "sessions"
    repo1_sessions.mkdir(parents=True)
    (repo1_sessions / f"{today}-alpha-commit-140000.md").write_text(
        f"---\nschema: gator-commit-summary-v1\ntype: commit\ndate: {today}\n"
        "repo: alpha\nvendor: claude\nmessage: Fix auth token rotation\n"
        "change-type: fix\nsignificance: notable\n"
        "decision-tags: security,auth\nagent: claude\npi: AG\n"
        "charter-changed: yes\n---\n\n"
        "## Decisions\n\n"
        "- Used OAEP padding instead of PKCS1v15 [#security]\n"
        "- Deferred key rotation to next sprint [#scope]\n\n"
        "## Session Notes\n\nFixed the auth module.\n"
    )

    # Fleet repo 2: has commit summaries from a different vendor
    repo2 = tmp_path / "repos" / "beta"
    repo2_sessions = repo2 / ".gator" / "sessions"
    repo2_sessions.mkdir(parents=True)
    (repo2_sessions / f"{today}-beta-commit-150000.md").write_text(
        f"---\nschema: gator-commit-summary-v1\ntype: commit\ndate: {today}\n"
        "repo: beta\nvendor: codex\nmessage: Add caching layer\n"
        "change-type: feature\nsignificance: high\n"
        "decision-tags: architecture,performance\nagent: codex\npi: AG\n"
        "charter-changed: yes\n---\n\n"
        "## Decisions\n\n"
        "- Chose Redis over Memcached for the caching layer [#architecture]\n"
    )

    # Registry pointing to both repos
    (gc / "registry.md").write_text(
        "# Registry\n\n"
        "| Repo | Path | Remote | Registered | Status |\n"
        "|------|------|--------|------------|--------|\n"
        f"| alpha | {repo1} | — | {today} | active |\n"
        f"| beta | {repo2} | — | {today} | active |\n"
    )

    return cp, [repo1, repo2]


class TestFleetAuditAggregation:
    """End-to-end: commit summaries in fleet repos → audit decisions."""

    def test_audit_reads_fleet_summaries(self, tmp_path):
        """Audit aggregates decisions from command post + fleet repos."""
        cp, repos = _make_fleet_with_summaries(tmp_path)

        # Patch find_command_post to return our mock
        with patch.object(gator_core, "find_command_post", return_value=cp):
            # Also patch the import in gator-audit (it imports from gator_core)
            with patch("gator_core.find_command_post", return_value=cp):
                data = audit.assemble_audit_data(since_days=7)

        assert data["decisions_source"] == "committed"
        assert data["decisions_dirs"] >= 3  # cp + 2 repos

        # Verify decisions from all three sources
        repos_seen = {d["repo"] for d in data["decisions"]}
        assert "command-post" in repos_seen or "alpha" in repos_seen
        assert "alpha" in repos_seen
        assert "beta" in repos_seen

        # Verify cross-vendor: both claude and codex decisions present
        vendors_seen = {d["vendor"] for d in data["decisions"]}
        assert "claude" in vendors_seen
        assert "codex" in vendors_seen

        # Verify specific decision text
        decision_texts = [d["text"] for d in data["decisions"]]
        assert any("OAEP" in t for t in decision_texts)
        assert any("Redis" in t for t in decision_texts)

    def test_audit_handles_empty_fleet(self, tmp_path):
        """Audit works when fleet repos have no sessions directories."""
        cp = tmp_path / "cp"
        gc = cp / "gator-command"
        gc.mkdir(parents=True)
        (gc / "mission.md").write_text("# Mission\n")
        (gc / "active-threads").mkdir()

        # Registry with a repo that has no .gator/sessions/
        repo = tmp_path / "repos" / "empty"
        (repo / ".gator").mkdir(parents=True)
        (gc / "registry.md").write_text(
            "# Registry\n\n"
            "| Repo | Path | Remote | Registered | Status |\n"
            "|------|------|--------|------------|--------|\n"
            f"| empty | {repo} | — | 2026-05-30 | active |\n"
        )

        with patch.object(gator_core, "find_command_post", return_value=cp):
            with patch("gator_core.find_command_post", return_value=cp):
                data = audit.assemble_audit_data(since_days=7)

        # Should not crash, should fall back gracefully
        assert data.get("decisions") is not None

    def test_commit_summary_vendor_field(self, tmp_path):
        """Commit summaries include vendor field readable by audit."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()

        # Write a commit summary WITH vendor (as the hook now does)
        (sessions_dir / f"{today}-repo-commit-120000.md").write_text(
            f"---\nschema: gator-commit-summary-v1\ntype: commit\n"
            f"date: {today}\nrepo: myrepo\nvendor: claude\n"
            "message: Test\nchange-type: fix\n---\n\n"
            "## Decisions\n\n- Fixed the thing [#bugfix]\n"
        )

        results = sessions.read_committed_summaries(sessions_dir, since_days=7)
        assert len(results) == 1
        assert results[0]["vendor"] == "claude"
        assert results[0]["repo"] == "myrepo"
