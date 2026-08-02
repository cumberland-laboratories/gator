"""
Tests for gator-fleet-intel.py — per-repo intelligence profile generation.

Tests the data collection and rendering functions using synthetic repo structures.
"""

from pathlib import Path

import pytest

from conftest import load_script

intel = load_script("gator-fleet-intel")


def _make_repo(tmp_path, name="test-repo", with_mission=True, with_charters=True,
               with_sessions=True, with_outbox=True):
    """Create a synthetic repo with .gator/ structure."""
    repo = tmp_path / name
    gator = repo / ".gator"
    gator.mkdir(parents=True)

    # .git dir (for git commands — they'll fail gracefully)
    (repo / ".git").mkdir()

    if with_mission:
        (gator / "mission.md").write_text(
            "# Mission\n\n**Test Repo** — a test repository for unit testing.\n"
        )

    if with_charters:
        charters = gator / "charters"
        charters.mkdir()
        (charters / "INDEX.md").write_text("# Charter Index\n")
        (charters / "_template.md").write_text("# Template\n")
        (charters / "core.md").write_text("# Charter: Core\n")
        (charters / "utils.md").write_text("# Charter: Utils\n")

    if with_sessions:
        sessions = gator / "sessions"
        sessions.mkdir()
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        (sessions / f"{today}-test-repo-claude-abc123.md").write_text(
            f"---\nschema: gator-session-summary-v1\ndate: {today}\n"
            f"repo: test-repo\nvendor: claude\n---\n\n"
            "## Goal\n\nFix the parsing bug.\n\n"
            "## Decisions\n\n"
            "- [2026-06-03T10:00] Use SQLite for caching\n"
            "- [2026-06-03T11:00] Defer migration to next sprint\n"
        )

    if with_outbox:
        (gator / "outbox.md").write_text(
            "# Outbox\n\n- Pattern from test-repo could help other-repo\n"
        )

    (gator / "issues.md").write_text(
        "# Issues\n\n### Bug 1\n**Status**: Open\n\n### Bug 2\n**Status**: Resolved\n"
    )

    (gator / "active-threads").mkdir()
    (gator / "active-threads" / "design.md").write_text("# Design\n")

    return repo


class TestReadMission:
    def test_reads_mission(self, tmp_path):
        """Extracts mission text from .gator/mission.md."""
        repo = _make_repo(tmp_path)
        result = intel.read_mission(repo)
        assert "Test Repo" in result

    def test_no_mission(self, tmp_path):
        """Returns empty string when no mission.md."""
        repo = _make_repo(tmp_path, with_mission=False)
        assert intel.read_mission(repo) == ""


class TestReadCharterNames:
    def test_reads_charters(self, tmp_path):
        """Returns charter names excluding templates and index."""
        repo = _make_repo(tmp_path)
        names = intel.read_charter_names(repo)
        assert "core" in names
        assert "utils" in names
        assert "_template" not in names
        assert "INDEX" not in names

    def test_no_charters_dir(self, tmp_path):
        """Returns empty list when no charters directory."""
        repo = _make_repo(tmp_path, with_charters=False)
        assert intel.read_charter_names(repo) == []


class TestReadActiveThreads:
    def test_reads_threads(self, tmp_path):
        """Returns thread names from active-threads/."""
        repo = _make_repo(tmp_path)
        threads = intel.read_active_threads(repo)
        assert "design" in threads


class TestReadIssuesCount:
    def test_counts_open(self, tmp_path):
        """Counts open issues only."""
        repo = _make_repo(tmp_path)
        assert intel.read_issues_count(repo) == 1


class TestReadCommittedDecisions:
    def test_reads_decisions(self, tmp_path):
        """Extracts decisions from committed summaries."""
        repo = _make_repo(tmp_path)
        decisions = intel.read_committed_decisions(repo)
        assert len(decisions) == 2
        assert "SQLite" in decisions[0]

    def test_no_sessions(self, tmp_path):
        """Returns empty list when no sessions directory."""
        repo = _make_repo(tmp_path, with_sessions=False)
        assert intel.read_committed_decisions(repo) == []


class TestReadOutbox:
    def test_reads_outbox(self, tmp_path):
        """Extracts outbox items."""
        repo = _make_repo(tmp_path)
        items = intel.read_outbox(repo)
        assert len(items) == 1
        assert "other-repo" in items[0]

    def test_no_outbox(self, tmp_path):
        """Returns empty list when no outbox."""
        repo = _make_repo(tmp_path, with_outbox=False)
        assert intel.read_outbox(repo) == []


class TestGetChangeTypeDistribution:
    def test_counts_types(self):
        """Groups change types from commits."""
        commits = [
            {"change_type": "fix"},
            {"change_type": "fix"},
            {"change_type": "feature"},
            {"change_type": ""},
        ]
        dist = intel.get_change_type_distribution(commits)
        assert dist == {"fix": 2, "feature": 1}

    def test_empty(self):
        assert intel.get_change_type_distribution([]) == {}


class TestRenderThread:
    def test_renders_profile(self, tmp_path):
        """Renders a complete profile as markdown."""
        profile = {
            "name": "test-repo",
            "accessible": True,
            "path": str(tmp_path),
            "mission": "A test repository.",
            "activity": "moderate",
            "commits_7d": 5,
            "commits_30d": 20,
            "charters": ["core", "utils"],
            "threads": ["design"],
            "open_issues": 1,
            "change_types": {"fix": 3, "feature": 1},
            "commit_themes": [("fix", 3), ("add", 1)],
            "recent_commits": [
                {"hash": "abc123", "message": "Fix bug", "date": "2026-06-03"},
            ],
            "decisions": ["Use SQLite for caching"],
            "outbox": ["Pattern useful elsewhere"],
            "generated_at": "2026-06-03T12:00:00Z",
        }

        md = intel.render_thread(profile)

        assert "# test-repo" in md
        assert "A test repository." in md
        assert "moderate" in md
        assert "core, utils" in md
        assert "Fix bug" in md
        assert "Use SQLite" in md
        assert "Pattern useful elsewhere" in md
        assert "Generated by gator fleet-intel" in md
