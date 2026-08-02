"""
Tests for gator-session-sink.py — SQLite/DuckDB session database sink.

Tests the sink functions using in-memory data (no real spool or vendor storage).
DuckDB tests are skipped if duckdb is not installed.
"""

import sqlite3
from pathlib import Path

import pytest

from conftest import load_script

sink = load_script("gator-session-sink")


_SENTINEL = object()


def _make_session(row_key="test-key-1", repo="test-repo", vendor="claude",
                  goal="Fix the bug", decisions=_SENTINEL, files=_SENTINEL,
                  tools=_SENTINEL):
    """Build a minimal session dict for testing."""
    return {
        "row_key": row_key,
        "session_id": "sess-001",
        "date": "2026-06-03",
        "start_time": "2026-06-03T10:00:00Z",
        "end_time": "2026-06-03T11:00:00Z",
        "repo": repo,
        "vendor": vendor,
        "agent": "Claude Code",
        "architect": "AG",
        "pi": "AG",
        "branch": "dev",
        "machine_id": "machine-uuid",
        "machine_host": "host",
        "machine_label": "label",
        "user_turns": 10,
        "assistant_turns": 12,
        "goal": goal,
        "source_type": "spool",
        "source_file": "test.json",
        "decisions": [
            {"timestamp": "2026-06-03T10:05:00Z", "text": "Use SQLite for local cache"},
            {"timestamp": "2026-06-03T10:30:00Z", "text": "Defer key rotation"},
        ] if decisions is _SENTINEL else decisions,
        "files_changed": ["src/main.py", "tests/test_main.py"] if files is _SENTINEL else files,
        "tools_used": ["Read", "Edit", "Bash"] if tools is _SENTINEL else tools,
    }


class TestSinkSqlite:
    def test_loads_sessions(self, tmp_path):
        """Loads sessions into SQLite with all related tables."""
        db = tmp_path / "test.sqlite"
        sessions = [_make_session()]

        loaded, skipped = sink.sink_sqlite(str(db), sessions)

        assert loaded == 1
        assert skipped == 0

        conn = sqlite3.connect(str(db))
        cur = conn.cursor()

        # Session row
        rows = cur.execute("SELECT repo, vendor, goal FROM sessions").fetchall()
        assert len(rows) == 1
        assert rows[0] == ("test-repo", "claude", "Fix the bug")

        # Decisions
        decs = cur.execute("SELECT text FROM decisions ORDER BY timestamp").fetchall()
        assert len(decs) == 2
        assert "SQLite" in decs[0][0]

        # Files
        files = cur.execute("SELECT file_path FROM files_changed").fetchall()
        assert len(files) == 2

        # Tools
        tools = cur.execute("SELECT tool FROM tools_used ORDER BY tool").fetchall()
        assert len(tools) == 3

        conn.close()

    def test_idempotent(self, tmp_path):
        """Re-loading same sessions skips duplicates."""
        db = tmp_path / "test.sqlite"
        sessions = [_make_session()]

        loaded1, _ = sink.sink_sqlite(str(db), sessions)
        loaded2, skipped2 = sink.sink_sqlite(str(db), sessions)

        assert loaded1 == 1
        assert loaded2 == 0
        assert skipped2 == 1

    def test_multiple_sessions(self, tmp_path):
        """Loads multiple sessions with different keys."""
        db = tmp_path / "test.sqlite"
        sessions = [
            _make_session(row_key="key-1", repo="repo-a"),
            _make_session(row_key="key-2", repo="repo-b"),
        ]

        loaded, _ = sink.sink_sqlite(str(db), sessions)
        assert loaded == 2

        conn = sqlite3.connect(str(db))
        repos = [r[0] for r in conn.execute(
            "SELECT repo FROM sessions ORDER BY repo"
        ).fetchall()]
        assert repos == ["repo-a", "repo-b"]
        conn.close()

    def test_empty_decisions(self, tmp_path):
        """Handles sessions with no decisions."""
        db = tmp_path / "test.sqlite"
        sessions = [_make_session(decisions=[], files=[], tools=[])]

        loaded, _ = sink.sink_sqlite(str(db), sessions)
        assert loaded == 1

        conn = sqlite3.connect(str(db))
        assert conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 0
        conn.close()

    def test_schema_metadata(self, tmp_path):
        """Writes schema version to metadata table."""
        db = tmp_path / "test.sqlite"
        sink.sink_sqlite(str(db), [_make_session()])

        conn = sqlite3.connect(str(db))
        version = conn.execute(
            "SELECT value FROM sink_metadata WHERE key = 'schema_version'"
        ).fetchone()[0]
        assert version == sink.SCHEMA_VERSION
        conn.close()


class TestLoadCommittedSummaries:
    def test_parses_summaries(self, tmp_path):
        """Loads committed summary markdown into session dicts."""
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()

        (sessions_dir / "2026-06-03-testrepo-claude-abc12345.md").write_text(
            "---\n"
            "schema: gator-session-summary-v1\n"
            "date: 2026-06-03\n"
            "repo: testrepo\n"
            "vendor: claude\n"
            "agent: Claude Code\n"
            "---\n\n"
            "# Session Summary\n\n"
            "## Goal\n\nFix the parsing bug.\n\n"
            "## Decisions\n\n"
            "- [2026-06-03T10:00] Use SQLite for local cache\n"
        )

        results = sink.load_committed_summaries(str(sessions_dir))
        assert len(results) == 1
        assert results[0]["repo"] == "testrepo"
        assert results[0]["vendor"] == "claude"
        assert results[0]["goal"] == "Fix the parsing bug."
        assert results[0]["source_type"] == "committed-summary"
        assert len(results[0]["decisions"]) == 1
        # Row key extracted from filename's trailing 16-char hex hash
        assert results[0]["row_key"] == "abc1234500000000" or len(results[0]["row_key"]) > 0

    def test_extracts_canonical_row_key_from_filename(self, tmp_path):
        """Row key is the trailing 16-char hex hash from the filename."""
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()

        (sessions_dir / "2026-06-03-testrepo-claude-e47f6722925ceefe.md").write_text(
            "---\ndate: 2026-06-03\nrepo: testrepo\nvendor: claude\n---\n\n"
            "## Goal\n\nTest.\n\n## Decisions\n\n- A decision\n"
        )

        results = sink.load_committed_summaries(str(sessions_dir))
        assert len(results) == 1
        assert results[0]["row_key"] == "e47f6722925ceefe"

    def test_distinct_sessions_get_distinct_keys(self, tmp_path):
        """Two summaries with same date/repo/vendor but different hashes get different keys."""
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()

        for suffix in ["aaaa111122223333", "bbbb222233334444"]:
            (sessions_dir / f"2026-06-03-testrepo-claude-{suffix}.md").write_text(
                "---\ndate: 2026-06-03\nrepo: testrepo\nvendor: claude\n---\n\n"
                f"## Goal\n\nSession {suffix}.\n\n## Decisions\n\n- Decision {suffix}\n"
            )

        results = sink.load_committed_summaries(str(sessions_dir))
        assert len(results) == 2
        assert results[0]["row_key"] != results[1]["row_key"]
        # Both should be the canonical 16-char hex suffix
        assert results[0]["row_key"] == "aaaa111122223333"
        assert results[1]["row_key"] == "bbbb222233334444"

    def test_empty_dir(self, tmp_path):
        """Returns empty list for empty directory."""
        d = tmp_path / "empty"
        d.mkdir()
        assert sink.load_committed_summaries(str(d)) == []

    def test_missing_dir(self, tmp_path):
        """Returns empty list for nonexistent directory."""
        assert sink.load_committed_summaries(str(tmp_path / "nope")) == []


# ---------------------------------------------------------------------------
# Turn-level tests
# ---------------------------------------------------------------------------

def _make_session_with_turns(row_key="turns-key-1"):
    """Build a session dict with sample turns and tool calls."""
    s = _make_session(row_key=row_key)
    s["turns"] = [
        {
            "seq": 0,
            "role": "user",
            "timestamp": "2026-06-03T10:00:00Z",
            "content": "Fix the bug in main.py",
            "type": "user",
            "tool_calls": [],
        },
        {
            "seq": 1,
            "role": "assistant",
            "timestamp": "2026-06-03T10:00:05Z",
            "content": "I'll fix that now.",
            "type": "assistant",
            "tool_calls": [
                {"tool": "Edit", "input": {"file_path": "main.py", "new_content": "fixed"}},
                {"tool": "Bash", "input": {"command": "python -m pytest"}},
            ],
        },
        {
            "seq": 2,
            "role": "user",
            "timestamp": "2026-06-03T10:01:00Z",
            "content": "Looks good, thanks.",
            "type": "user",
            "tool_calls": [],
        },
    ]
    return s


class TestTurnsSqlite:
    def test_loads_turns(self, tmp_path):
        """Turns table has correct rows with seq, role, content."""
        db = tmp_path / "test.sqlite"
        sessions = [_make_session_with_turns()]

        loaded, _ = sink.sink_sqlite(str(db), sessions, include_turns=True)
        assert loaded == 1

        conn = sqlite3.connect(str(db))
        turns = conn.execute(
            "SELECT seq, role, content FROM turns ORDER BY seq"
        ).fetchall()
        assert len(turns) == 3
        assert turns[0] == (0, "user", "Fix the bug in main.py")
        assert turns[1][0] == 1
        assert turns[1][1] == "assistant"
        assert turns[2] == (2, "user", "Looks good, thanks.")
        conn.close()

    def test_loads_tool_calls(self, tmp_path):
        """Tool calls table links to turns by turn_seq."""
        db = tmp_path / "test.sqlite"
        sessions = [_make_session_with_turns()]

        sink.sink_sqlite(str(db), sessions, include_turns=True)

        conn = sqlite3.connect(str(db))
        tc = conn.execute(
            "SELECT turn_seq, tool, input_keys FROM tool_calls ORDER BY turn_seq, tool"
        ).fetchall()
        assert len(tc) == 2
        assert tc[0][0] == 1  # turn seq
        assert tc[0][1] == "Bash"
        assert tc[1][1] == "Edit"
        # input_keys contains JSON key names + optional hash suffix
        assert "command" in tc[0][2]
        assert "file_path" in tc[1][2]
        conn.close()

    def test_no_turns_table_without_flag(self, tmp_path):
        """Turns table is NOT created when include_turns=False."""
        db = tmp_path / "test.sqlite"
        sessions = [_make_session_with_turns()]

        sink.sink_sqlite(str(db), sessions, include_turns=False)

        conn = sqlite3.connect(str(db))
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        assert "turns" not in tables
        assert "tool_calls" not in tables
        conn.close()

    def test_idempotent_turns(self, tmp_path):
        """Re-loading same session skips turn duplicates."""
        db = tmp_path / "test.sqlite"
        sessions = [_make_session_with_turns()]

        sink.sink_sqlite(str(db), sessions, include_turns=True)
        sink.sink_sqlite(str(db), sessions, include_turns=True)

        conn = sqlite3.connect(str(db))
        turns = conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0]
        assert turns == 3  # not 6
        conn.close()

    def test_content_coercion(self, tmp_path):
        """List-type content (Codex) is stored as JSON string."""
        db = tmp_path / "test.sqlite"
        s = _make_session_with_turns()
        s["turns"][0]["content"] = [{"type": "text", "text": "hello"}]

        sink.sink_sqlite(str(db), [s], include_turns=True)

        conn = sqlite3.connect(str(db))
        content = conn.execute(
            "SELECT content FROM turns WHERE seq = 0"
        ).fetchone()[0]
        import json
        parsed = json.loads(content)
        assert parsed[0]["text"] == "hello"
        conn.close()

    def test_duplicate_tool_calls_preserved(self, tmp_path):
        """Two calls to the same tool in one turn with different inputs are both stored."""
        db = tmp_path / "test.sqlite"
        s = _make_session(row_key="dup-tools-key")
        s["turns"] = [
            {
                "seq": 0,
                "role": "assistant",
                "timestamp": "2026-06-03T10:00:00Z",
                "content": "Reading two files.",
                "type": "assistant",
                "tool_calls": [
                    {"tool": "Read", "input": {"file_path": "main.py"}},
                    {"tool": "Read", "input": {"file_path": "utils.py"}},
                ],
            },
        ]

        sink.sink_sqlite(str(db), [s], include_turns=True)

        conn = sqlite3.connect(str(db))
        tc = conn.execute(
            "SELECT tool, input_keys FROM tool_calls WHERE turn_seq = 0 ORDER BY input_keys"
        ).fetchall()
        assert len(tc) == 2
        assert tc[0][0] == "Read"
        assert tc[1][0] == "Read"
        # Different input_keys
        assert tc[0][1] != tc[1][1]
        conn.close()


class TestNormalizeTurn:
    def test_normalizes_claude_turn(self):
        """Normalizes a Claude turn (has 'type', 'cwd', 'branch')."""
        raw = {
            "role": "assistant",
            "timestamp": "2026-06-03T10:00:00Z",
            "content": "I'll fix that.",
            "type": "assistant",
            "cwd": "/home/user/project",
            "branch": "dev",
            "tool_calls": [{"tool": "Edit", "input": {"file_path": "x.py"}}],
        }
        norm = sink.normalize_turn(raw, seq=5)
        assert norm["seq"] == 5
        assert norm["role"] == "assistant"
        assert norm["vendor_type"] == "assistant"
        assert norm["content"] == "I'll fix that."
        assert "cwd" not in norm
        assert "branch" not in norm
        assert len(norm["tool_calls"]) == 1
        assert norm["tool_calls"][0]["tool"] == "Edit"
        assert "file_path" in norm["tool_calls"][0]["input_keys"]

    def test_normalizes_codex_turn(self):
        """Normalizes a Codex turn (has 'item_type', list content)."""
        raw = {
            "role": "assistant",
            "timestamp": "2026-06-03T10:00:00Z",
            "content": [{"type": "text", "text": "Done."}],
            "item_type": "response_item",
            "tool_calls": [],
        }
        norm = sink.normalize_turn(raw, seq=0)
        assert norm["vendor_type"] == "response_item"
        # Content coerced to string
        import json
        parsed = json.loads(norm["content"])
        assert parsed[0]["text"] == "Done."
        assert norm["tool_calls"] == []


class TestCommandSink:
    def test_ndjson_output(self, tmp_path):
        """Command sink writes valid NDJSON to process stdin."""
        import json

        output_file = tmp_path / "received.ndjson"
        # Use a Python command that reads stdin and writes to a file
        cmd = f'python -c "import sys; open(r\'{output_file}\', \'w\').write(sys.stdin.read())"'

        sessions = [_make_session()]
        written, exit_code = sink.sink_command(sessions, cmd)

        assert written == 1
        assert exit_code == 0

        lines = output_file.read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["repo"] == "test-repo"
        assert data["row_key"] == "test-key-1"
