"""
Tests for gator-sessions.py — session orchestrator CLI.

Tests the pure utility functions (parse_since, filter_sessions_since,
_spool_slug, exported state) without requiring real vendor session data.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from conftest import load_script

sessions = load_script("gator-sessions")


class TestParseSince:
    def test_days(self):
        """Parses '7d' into a datetime ~7 days ago."""
        result = sessions.parse_since("7d")
        assert result is not None
        expected = datetime.now(timezone.utc) - timedelta(days=7)
        # Within 5 seconds tolerance
        assert abs((result - expected).total_seconds()) < 5

    def test_hours(self):
        """Parses '24h' into a datetime ~24 hours ago."""
        result = sessions.parse_since("24h")
        assert result is not None
        expected = datetime.now(timezone.utc) - timedelta(hours=24)
        assert abs((result - expected).total_seconds()) < 5

    def test_weeks(self):
        """Parses '2w' into a datetime ~14 days ago."""
        result = sessions.parse_since("2w")
        assert result is not None
        expected = datetime.now(timezone.utc) - timedelta(weeks=2)
        assert abs((result - expected).total_seconds()) < 5

    def test_invalid(self):
        """Returns None for unparseable strings."""
        assert sessions.parse_since("foo") is None
        assert sessions.parse_since("") is None
        assert sessions.parse_since(None) is None


class TestFilterSessionsSince:
    def test_filters_by_date(self):
        """Filters sessions by modified timestamp."""
        now = datetime.now(timezone.utc)
        old_date = (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M")
        recent_date = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")

        test_sessions = [
            {"vendor": "claude", "session_id": "old", "modified": old_date},
            {"vendor": "claude", "session_id": "recent", "modified": recent_date},
        ]

        since_dt = now - timedelta(days=7)
        filtered = sessions.filter_sessions_since(test_sessions, since_dt)
        assert len(filtered) == 1
        assert filtered[0]["session_id"] == "recent"

    def test_none_since(self):
        """Returns all sessions when since_dt is None."""
        test_sessions = [
            {"vendor": "claude", "session_id": "a", "modified": "2026-01-01"},
        ]
        filtered = sessions.filter_sessions_since(test_sessions, None)
        assert len(filtered) == 1


class TestSpoolSlug:
    def test_deterministic(self):
        """Same inputs produce same slug."""
        slug1 = sessions._spool_slug("abc123", "/path/to/session")
        slug2 = sessions._spool_slug("abc123", "/path/to/session")
        assert slug1 == slug2

    def test_different_inputs(self):
        """Different inputs produce different slugs."""
        slug1 = sessions._spool_slug("abc123", "/path/a")
        slug2 = sessions._spool_slug("abc123", "/path/b")
        assert slug1 != slug2

    def test_length(self):
        """Slug is 16 hex chars."""
        slug = sessions._spool_slug("test", "path")
        assert len(slug) == 16
        assert all(c in "0123456789abcdef" for c in slug)


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
        results = sessions.read_committed_summaries(sessions_dir, since_days=99999)
        assert len(results) == 1
        assert results[0]["repo"] == "myrepo"
        assert results[0]["vendor"] == "claude"
        assert len(results[0]["decisions"]) == 2
        assert "SQLite" in results[0]["decisions"][0]["text"]

    def test_empty_dir(self, tmp_path):
        """Returns empty list for empty directory."""
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        assert sessions.read_committed_summaries(sessions_dir) == []

    def test_missing_dir(self, tmp_path):
        """Returns empty list for nonexistent directory."""
        assert sessions.read_committed_summaries(tmp_path / "nope") == []

    def test_reads_commit_summaries(self, tmp_path):
        """Parses commit-level summaries (from pre-commit hook)."""
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()

        from datetime import datetime, timezone
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

        results = sessions.read_committed_summaries(sessions_dir, since_days=7)
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
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        (sessions_dir / f"{today}-repo-claude-new123.md").write_text(
            f"---\ndate: {today}\nrepo: repo\nvendor: claude\n---\n\n"
            "## Decisions\n\n- [" + today + "] New decision\n"
        )

        results = sessions.read_committed_summaries(sessions_dir, since_days=7)
        assert len(results) == 1
        assert "New decision" in results[0]["decisions"][0]["text"]


# ---------------------------------------------------------------------------
# Turn manifest tests
# ---------------------------------------------------------------------------

def _make_spool_export(session_id="test-session-123", source_path="/home/user/project",
                       vendor="claude", turns=None):
    """Build a synthetic spool export dict for testing."""
    if turns is None:
        turns = [
            {
                "seq": 1, "role": "user", "type": "user",
                "timestamp": "2026-06-04T10:00:00Z",
                "content": "Please review `gator-sessions.py` and fix the make_row_key() bug.",
            },
            {
                "seq": 2, "role": "assistant", "type": "assistant",
                "timestamp": "2026-06-04T10:01:00Z",
                "content": "I'll look at the `gator-session-common.py` file. The issue is in extract_intelligence().",
                "tool_calls": [{"tool": "Read"}, {"tool": "Edit"}],
            },
            {
                "seq": 3, "role": "user", "type": "user",
                "timestamp": "2026-06-04T10:02:00Z",
                "content": "Looks good. Let's also update the def validate_schema(data) function.",
            },
        ]
    return {
        "schema": "gator-session-export-v1",
        "exported_at": "2026-06-04T10:05:00Z",
        "vendor": vendor,
        "metadata": {
            "session_id": session_id,
            "source_path": source_path,
            "project": "gator-command",
        },
        "summary": {"row_key": None},
        "turns": turns,
    }


class TestExtractMentionsFiles:
    def test_backtick_paths(self):
        text = "Check `gator-sessions.py` and `src/main.rs` for issues."
        result = sessions.extract_mentions_files(text)
        assert "gator-sessions.py" in result
        assert "src/main.rs" in result

    def test_quoted_paths(self):
        text = 'Look at "config/settings.yaml" for the config.'
        result = sessions.extract_mentions_files(text)
        assert "config/settings.yaml" in result

    def test_bare_paths(self):
        text = "The file gator-sessions.py has the bug. Also check utils.ts nearby."
        result = sessions.extract_mentions_files(text)
        assert "gator-sessions.py" in result
        assert "utils.ts" in result

    def test_dedup(self):
        text = "Edit `main.py` and then re-read `main.py` again."
        result = sessions.extract_mentions_files(text)
        assert result.count("main.py") == 1

    def test_cap_at_20(self):
        text = " ".join(f"`file{i}.py`" for i in range(30))
        result = sessions.extract_mentions_files(text)
        assert len(result) <= 20

    def test_skips_http(self):
        text = 'See `http://example.com/foo.py` for details.'
        result = sessions.extract_mentions_files(text)
        assert not any("http" in f for f in result)


class TestExtractMentionsFunctions:
    def test_function_call(self):
        text = "The make_row_key() function is broken."
        result = sessions.extract_mentions_functions(text)
        assert "make_row_key" in result

    def test_method_call(self):
        text = "Call Session.validate() to check."
        result = sessions.extract_mentions_functions(text)
        assert "Session.validate" in result

    def test_def_pattern(self):
        text = "def validate_schema(data):\n    pass"
        result = sessions.extract_mentions_functions(text)
        assert "validate_schema" in result

    def test_no_matches(self):
        text = "No functions mentioned here at all."
        result = sessions.extract_mentions_functions(text)
        assert result == []

    def test_dedup(self):
        text = "Call foo() then foo() again."
        result = sessions.extract_mentions_functions(text)
        assert result.count("foo") == 1

    def test_skips_builtins(self):
        text = "if (x) return print(y)"
        result = sessions.extract_mentions_functions(text)
        assert "if" not in result
        assert "print" not in result


class TestExtractKeywords:
    def test_counting(self):
        text = "session session session review review config"
        result = sessions.extract_keywords(text, top_n=3)
        assert result[0] == "session"
        assert "review" in result

    def test_stopwords(self):
        text = "the and this that with session"
        result = sessions.extract_keywords(text)
        assert "session" in result
        assert "the" not in result

    def test_cap_at_top_n(self):
        text = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
        result = sessions.extract_keywords(text, top_n=3)
        assert len(result) == 3


class TestBuildTurnManifest:
    def test_schema_and_structure(self):
        export = _make_spool_export()
        manifest = sessions.build_turn_manifest(export)
        assert manifest["schema"] == "gator-turn-manifest-v1"
        assert manifest["turn_count"] == 3
        assert len(manifest["turns"]) == 3
        assert manifest["vendor"] == "claude"
        assert manifest["session_id"] == "test-session-123"

    def test_row_key_from_content(self):
        export = _make_spool_export()
        expected_key = sessions._spool_slug("test-session-123", "/home/user/project")
        manifest = sessions.build_turn_manifest(export)
        assert manifest["row_key"] == expected_key

    def test_turn_fields(self):
        export = _make_spool_export()
        manifest = sessions.build_turn_manifest(export)
        turn1 = manifest["turns"][0]
        assert turn1["seq"] == 1
        assert turn1["role"] == "user"
        assert "gator-sessions.py" in turn1["mentions_files"]
        assert "make_row_key" in turn1["mentions_functions"]
        assert isinstance(turn1["preview"], str)
        assert turn1["chars"] > 0

    def test_tool_types(self):
        export = _make_spool_export()
        manifest = sessions.build_turn_manifest(export)
        turn2 = manifest["turns"][1]
        assert turn2["has_tool_calls"] is True
        assert "Edit" in turn2["tool_types"]
        assert "Read" in turn2["tool_types"]

    def test_missing_seq(self):
        """Turns without seq get auto-numbered."""
        export = _make_spool_export(turns=[
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ])
        manifest = sessions.build_turn_manifest(export)
        assert manifest["turns"][0]["seq"] == 1
        assert manifest["turns"][1]["seq"] == 2


class TestLegacySpoolIdentity:
    def test_no_source_path(self):
        """Legacy export with no source_path gets deterministic row_key."""
        export = _make_spool_export(session_id="legacy-abc", source_path="")
        # Simulate missing source_path
        del export["metadata"]["source_path"]
        manifest = sessions.build_turn_manifest(export)
        expected = sessions._spool_slug("legacy-abc", "")
        assert manifest["row_key"] == expected

    def test_null_source_path(self):
        """Legacy export with null source_path normalized to empty string."""
        export = _make_spool_export(session_id="legacy-null")
        export["metadata"]["source_path"] = None
        manifest = sessions.build_turn_manifest(export)
        # None should be coerced to "" for consistent identity
        expected = sessions._spool_slug("legacy-null", "")
        assert manifest["row_key"] == expected


class TestCurrentSpoolIdentity:
    def test_with_source_path(self):
        """Current export with source_path produces different key from legacy."""
        sid = "same-session-id"
        key_with = sessions._spool_slug(sid, "/home/user/project")
        key_without = sessions._spool_slug(sid, "")
        assert key_with != key_without

    def test_manifest_filename(self):
        """Manifest filename uses row_key from content."""
        export = _make_spool_export()
        manifest = sessions.build_turn_manifest(export)
        expected_filename = f"{manifest['row_key']}.turns.json"
        assert expected_filename.endswith(".turns.json")
        assert len(manifest["row_key"]) == 16


class TestShowTurnsLookup:
    def test_finds_spool_by_row_key(self, tmp_path, monkeypatch):
        """show-turns resolves the right spool file for both legacy and current exports."""
        spool = tmp_path / "spool"
        spool.mkdir()
        monkeypatch.setattr(sessions, "SPOOL_DIR", spool)

        # Write a legacy export (no source_path)
        legacy_export = _make_spool_export(session_id="legacy-sess", source_path="")
        del legacy_export["metadata"]["source_path"]
        legacy_key = sessions._spool_slug("legacy-sess", "")
        (spool / f"claude-{legacy_key}.json").write_text(json.dumps(legacy_export))

        # Write a current export (with source_path)
        current_export = _make_spool_export(session_id="current-sess", source_path="/path/to/file")
        current_key = sessions._spool_slug("current-sess", "/path/to/file")
        (spool / f"claude-{current_key}.json").write_text(json.dumps(current_export))

        # _load_spool_sessions should find both
        results = sessions._load_spool_sessions()
        keys = {r[0] for r in results}
        assert legacy_key in keys
        assert current_key in keys

    def test_legacy_and_current_different_keys(self, tmp_path, monkeypatch):
        """Same session_id with and without source_path → different row_keys."""
        spool = tmp_path / "spool"
        spool.mkdir()
        monkeypatch.setattr(sessions, "SPOOL_DIR", spool)

        sid = "shared-session-id"
        legacy_export = _make_spool_export(session_id=sid, source_path="")
        del legacy_export["metadata"]["source_path"]
        (spool / "claude-legacy.json").write_text(json.dumps(legacy_export))

        current_export = _make_spool_export(session_id=sid, source_path="/some/path")
        (spool / "claude-current.json").write_text(json.dumps(current_export))

        results = sessions._load_spool_sessions()
        keys = [r[0] for r in results]
        assert len(set(keys)) == 2  # Different row_keys


class TestTurnManifestSkipExisting:
    def test_skips_existing_without_force(self, tmp_path, monkeypatch):
        """Default run skips sessions that already have a manifest file."""
        spool = tmp_path / "spool"
        spool.mkdir()
        manifests = tmp_path / "manifests"
        manifests.mkdir()
        monkeypatch.setattr(sessions, "SPOOL_DIR", spool)
        monkeypatch.setattr(sessions, "MANIFEST_DIR", manifests)

        # Two spool exports
        export1 = _make_spool_export(session_id="sess-1", source_path="/p1")
        key1 = sessions._spool_slug("sess-1", "/p1")
        (spool / f"claude-{key1}.json").write_text(json.dumps(export1))

        export2 = _make_spool_export(session_id="sess-2", source_path="/p2")
        key2 = sessions._spool_slug("sess-2", "/p2")
        (spool / f"claude-{key2}.json").write_text(json.dumps(export2))

        # Pre-existing manifest for sess-1
        (manifests / f"{key1}.turns.json").write_text("{}")

        class Args:
            row_key = None
            force = False
        sessions.cmd_turn_manifest(Args())

        # Only sess-2 should have gotten a manifest
        assert (manifests / f"{key2}.turns.json").exists()
        # sess-1's manifest should still be the empty one we wrote
        content = json.loads((manifests / f"{key1}.turns.json").read_text())
        assert content == {}  # unchanged

    def test_row_key_skips_existing_without_force(self, tmp_path, monkeypatch):
        """--row-key also skips existing manifests unless --force is set."""
        spool = tmp_path / "spool"
        spool.mkdir()
        manifests = tmp_path / "manifests"
        manifests.mkdir()
        monkeypatch.setattr(sessions, "SPOOL_DIR", spool)
        monkeypatch.setattr(sessions, "MANIFEST_DIR", manifests)

        export = _make_spool_export(session_id="sess-1", source_path="/p1")
        key = sessions._spool_slug("sess-1", "/p1")
        (spool / f"claude-{key}.json").write_text(json.dumps(export))

        # Pre-existing manifest
        (manifests / f"{key}.turns.json").write_text("{}")

        class Args:
            row_key = key
            force = False
        sessions.cmd_turn_manifest(Args())

        # Should NOT have been overwritten
        content = json.loads((manifests / f"{key}.turns.json").read_text())
        assert content == {}

    def test_generates_for_new(self, tmp_path, monkeypatch):
        """Generates manifests for sessions without one."""
        spool = tmp_path / "spool"
        spool.mkdir()
        manifests = tmp_path / "manifests"
        manifests.mkdir()
        monkeypatch.setattr(sessions, "SPOOL_DIR", spool)
        monkeypatch.setattr(sessions, "MANIFEST_DIR", manifests)

        export = _make_spool_export(session_id="new-sess", source_path="/new")
        key = sessions._spool_slug("new-sess", "/new")
        (spool / f"claude-{key}.json").write_text(json.dumps(export))

        class Args:
            row_key = None
            force = False
        sessions.cmd_turn_manifest(Args())

        manifest_file = manifests / f"{key}.turns.json"
        assert manifest_file.exists()
        manifest = json.loads(manifest_file.read_text())
        assert manifest["schema"] == "gator-turn-manifest-v1"
        assert manifest["turn_count"] == 3


class TestExportedState:
    def test_load_empty(self, tmp_path, monkeypatch):
        """Returns empty set when state file doesn't exist."""
        monkeypatch.setattr(sessions, "SPOOL_STATE_FILE", tmp_path / "nonexistent.json")
        assert sessions.load_exported_state() == set()

    def test_save_and_load(self, tmp_path, monkeypatch):
        """Round-trips exported IDs through save/load."""
        spool = tmp_path / "spool"
        spool.mkdir()
        state_file = spool / ".exported.json"
        monkeypatch.setattr(sessions, "SPOOL_DIR", spool)
        monkeypatch.setattr(sessions, "SPOOL_STATE_FILE", state_file)

        ids = {"claude-abc123", "codex-def456"}
        sessions.save_exported_state(ids)
        loaded = sessions.load_exported_state()
        assert loaded == ids
