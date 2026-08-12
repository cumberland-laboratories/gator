"""
Tests for gator_session_reader.py — surviving committed-summary reader.

Extracted from tests/test_sessions.py::TestReadCommittedSummaries in Phase 2
of the 2026-08-11 non-Enterprise session cleanup. The original class stays in
tests/test_sessions.py through Phase 2 (still pins the legacy copy in
gator-sessions.py); Phase 3 deletes it along with the whole vendor-discovery
half of test_sessions.py.

Behavior pinned here is byte-identical to the legacy pins — parse and read
logic was copied verbatim into the new module.
"""

from datetime import datetime, timezone

from conftest import load_script

reader = load_script("gator_session_reader")


class TestReadCommittedSummaries:
    def test_reads_summaries(self, tmp_path):
        """Parses committed summary markdown files."""
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()

        (sessions_dir / "2026-05-30-myrepo-claude-abc123.md").write_text(
            "---\n"
            "schema: gator-session-summary-v1\n"
            "date: 2026-05-30\n"
            "repo: myrepo\n"
            "vendor: claude\n"
            "agent: Claude Code (Opus 4.6)\n"
            "---\n\n"
            "# Session Summary\n\n"
            "## Goal\n\nFix the parsing bug.\n\n"
            "## Decisions\n\n"
            "- [2026-05-30T10:00] Use SQLite instead of PostgreSQL\n"
            "- [2026-05-30T11:00] Defer key rotation to next session\n\n"
            "## Files Changed\n\n- src/main.py\n"
        )

        # since_days is intentionally large -- this test's intent is to
        # verify parsing, not the age filter. The fixture date is fixed
        # at 2026-05-30; since_days=7 aged the test out.
        results = reader.read_committed_summaries(sessions_dir, since_days=99999)
        assert len(results) == 1
        assert results[0]["repo"] == "myrepo"
        assert results[0]["vendor"] == "claude"
        assert len(results[0]["decisions"]) == 2
        assert "SQLite" in results[0]["decisions"][0]["text"]

    def test_empty_dir(self, tmp_path):
        """Returns empty list for empty directory."""
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        assert reader.read_committed_summaries(sessions_dir) == []

    def test_missing_dir(self, tmp_path):
        """Returns empty list for nonexistent directory."""
        assert reader.read_committed_summaries(tmp_path / "nope") == []

    def test_reads_commit_summaries(self, tmp_path):
        """Parses commit-level summaries (from pre-commit hook)."""
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        (sessions_dir / f"{today}-myrepo-commit-143022.md").write_text(
            "---\n"
            "schema: gator-commit-summary-v1\n"
            "type: commit\n"
            f"date: {today}\n"
            "repo: myrepo\n"
            "change-type: fix\n"
            "significance: routine\n"
            "decision-tags: bugfix\n"
            "agent: claude\n"
            "---\n\n"
            "## Decisions\n\n"
            "- Chose SQLite over PostgreSQL for local cache [#architecture]\n\n"
            "## Session Notes\n\n"
            "Fixed the parsing bug.\n"
        )

        results = reader.read_committed_summaries(sessions_dir, since_days=7)
        assert len(results) == 1
        assert results[0]["repo"] == "myrepo"
        assert len(results[0]["decisions"]) == 1
        assert "SQLite" in results[0]["decisions"][0]["text"]

    def test_date_filtering(self, tmp_path):
        """Filters out sessions older than since_days."""
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()

        # Old session (60 days ago)
        (sessions_dir / "2026-03-01-repo-claude-old123.md").write_text(
            "---\ndate: 2026-03-01\nrepo: repo\nvendor: claude\n---\n\n"
            "## Decisions\n\n- [2026-03-01] Old decision\n"
        )
        # Recent session
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        (sessions_dir / f"{today}-repo-claude-new123.md").write_text(
            f"---\ndate: {today}\nrepo: repo\nvendor: claude\n---\n\n"
            "## Decisions\n\n- [" + today + "] New decision\n"
        )

        results = reader.read_committed_summaries(sessions_dir, since_days=7)
        assert len(results) == 1
        assert "New decision" in results[0]["decisions"][0]["text"]
