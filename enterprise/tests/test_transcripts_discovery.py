"""Tests for the Claude Code transcript discovery module.

Exercises the pure-parse layer (no HTTP, no CLI). Fixture-driven —
builds a synthetic ~/.claude/projects/ tree and points the discover()
function at it via the CLAUDE_TRANSCRIPTS_ROOT env override.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Ensure enterprise-cli is importable — conftest already inserts it
# but this file may run in odd invocation orders.
_HERE = Path(__file__).resolve().parent
_CLI_ROOT = _HERE.parent / "enterprise-cli"
if str(_CLI_ROOT) not in sys.path:
    sys.path.insert(0, str(_CLI_ROOT))

from gator_enterprise_cli.transcripts_discovery import (
    DiscoveredTranscript,
    _parse_jsonl_metadata,
    claude_root_path,
    discover,
    discover_claude_transcripts,
)


def _write_transcript(
    path: Path,
    *,
    session_id: str,
    events: list[dict],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for event in events:
            event.setdefault("sessionId", session_id)
            f.write(json.dumps(event) + "\n")


def _turn(role: str, ts: str, *, model: str | None = None, cwd: str | None = None) -> dict:
    return {
        "type": role,
        "timestamp": ts,
        "cwd": cwd,
        "message": {"role": role, "model": model},
    }


@pytest.fixture
def fake_claude_root(tmp_path, monkeypatch):
    """Populated ~/.claude/projects with two sessions in one project."""
    root = tmp_path / "claude" / "projects"
    project = root / "C--Users-someone-code-repo"

    _write_transcript(
        project / "ba565a28-171b-4a8a-986d-b43a41bdbe2b.jsonl",
        session_id="ba565a28-171b-4a8a-986d-b43a41bdbe2b",
        events=[
            {"type": "mode", "mode": "default"},
            _turn("user", "2026-08-07T10:00:00.000Z", cwd="C:\\Users\\someone\\code\\repo"),
            _turn("assistant", "2026-08-07T10:00:05.100Z", model="claude-opus-4-7"),
            _turn("user", "2026-08-07T10:05:00.000Z"),
        ],
    )
    _write_transcript(
        project / "331a6a12-b575-4478-b623-d731a73fdbc2.jsonl",
        session_id="331a6a12-b575-4478-b623-d731a73fdbc2",
        events=[
            {"type": "mode", "mode": "default"},
            _turn("assistant", "2026-08-08T09:00:00.000Z", model="claude-opus-4-7"),
        ],
    )

    monkeypatch.setenv("CLAUDE_TRANSCRIPTS_ROOT", str(root))
    return root


class TestParseSingleTranscript:
    def test_extracts_session_id_from_first_event(self, tmp_path):
        path = tmp_path / "proj" / "ba565a28-171b-4a8a-986d-b43a41bdbe2b.jsonl"
        _write_transcript(
            path,
            session_id="ba565a28-171b-4a8a-986d-b43a41bdbe2b",
            events=[
                {"type": "mode", "mode": "default"},
                _turn("user", "2026-08-07T10:00:00.000Z", cwd="/repo/x"),
            ],
        )
        result = _parse_jsonl_metadata(path)
        assert result.vendor_session_id == "ba565a28-171b-4a8a-986d-b43a41bdbe2b"
        assert result.vendor == "anthropic"
        assert result.workspace_hint == "/repo/x"
        assert result.parse_error is None

    def test_extracts_model_from_assistant_turn(self, tmp_path):
        path = tmp_path / "proj" / "s.jsonl"
        _write_transcript(
            path,
            session_id="s",
            events=[
                _turn("user", "2026-08-07T10:00:00.000Z"),
                _turn("assistant", "2026-08-07T10:00:01.000Z", model="claude-opus-4-7"),
            ],
        )
        result = _parse_jsonl_metadata(path)
        assert result.model == "claude-opus-4-7"

    def test_started_ended_span_all_events(self, tmp_path):
        path = tmp_path / "proj" / "s.jsonl"
        _write_transcript(
            path,
            session_id="s",
            events=[
                _turn("user", "2026-08-07T10:00:00.000Z"),
                _turn("assistant", "2026-08-07T10:00:05.100Z"),
                _turn("user", "2026-08-07T11:30:00.000Z"),
            ],
        )
        result = _parse_jsonl_metadata(path)
        assert result.started_at == datetime(2026, 8, 7, 10, 0, 0, tzinfo=timezone.utc)
        assert result.ended_at == datetime(2026, 8, 7, 11, 30, 0, tzinfo=timezone.utc)
        assert result.turn_count == 3

    def test_falls_back_to_filename_when_session_id_missing(self, tmp_path):
        path = tmp_path / "proj" / "abcdef-1234.jsonl"
        _write_transcript(
            path,
            session_id="",  # Will be overwritten by empty string
            events=[
                # No sessionId anywhere
                {"type": "file-history-delta", "timestamp": "2026-08-07T10:00:00.000Z"},
            ],
        )
        # Rewrite manually to strip sessionId
        with path.open("w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "file-history-delta"}) + "\n")
        result = _parse_jsonl_metadata(path)
        assert result.vendor_session_id == "abcdef-1234"
        assert result.parse_error and "fell back to filename" in result.parse_error

    def test_survives_malformed_lines(self, tmp_path):
        path = tmp_path / "proj" / "s.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "mode", "sessionId": "s"}) + "\n")
            f.write("this is not valid json\n")
            f.write("\n")  # blank line
            f.write(json.dumps(_turn("user", "2026-08-07T10:00:00.000Z")) + "\n")
        result = _parse_jsonl_metadata(path)
        assert result.vendor_session_id == "s"
        assert result.turn_count == 1


class TestDiscoverClaude:
    def test_yields_every_transcript(self, fake_claude_root):
        found = list(discover_claude_transcripts())
        session_ids = sorted(r.vendor_session_id for r in found)
        assert session_ids == [
            "331a6a12-b575-4478-b623-d731a73fdbc2",
            "ba565a28-171b-4a8a-986d-b43a41bdbe2b",
        ]

    def test_since_filters_older_transcripts(self, fake_claude_root):
        cutoff = datetime(2026, 8, 8, 0, 0, 0, tzinfo=timezone.utc)
        found = list(discover_claude_transcripts(since=cutoff))
        assert [r.vendor_session_id for r in found] == [
            "331a6a12-b575-4478-b623-d731a73fdbc2",
        ]

    def test_project_hash_filter(self, fake_claude_root):
        found = list(
            discover_claude_transcripts(project_hash_filter="C--Users-someone-code-repo")
        )
        assert len(found) == 2

        found_other = list(discover_claude_transcripts(project_hash_filter="nonexistent"))
        assert found_other == []

    def test_returns_nothing_when_root_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_TRANSCRIPTS_ROOT", str(tmp_path / "does-not-exist"))
        assert list(discover_claude_transcripts()) == []


class TestVendorDispatch:
    def test_claude_alias_resolves(self, fake_claude_root):
        # Both "claude" and "anthropic" work
        assert len(list(discover("claude"))) == 2
        assert len(list(discover("anthropic"))) == 2

    def test_unknown_vendor_raises(self):
        with pytest.raises(ValueError, match="Unsupported vendor"):
            list(discover("gemini"))


class TestPhase2Hardening:
    """Phase 2 hardening regression pins (2026-08-14).

    Covers the two discovery-side additions:
    - `DiscoveredTranscript.unreadable` — distinguishes fatal-parse (OSError
      on read) from degraded-but-usable parse (missing sessionId → filename
      fallback). CLI uses this to skip fatal cases with a named-file
      diagnostic instead of attempting to upload a file it never read.
    - `claude_root_path()` — public accessor exposing the discovery root so
      the CLI can check existence up front and emit an informative warning
      instead of a silent zero-transcripts-discovered pull.
    """

    def test_unreadable_flag_set_on_permission_error(self, tmp_path, monkeypatch):
        """File that raises OSError on open() → unreadable=True + parse_error."""
        path = tmp_path / "proj" / "s.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")

        # Simulate an unreadable file by monkey-patching Path.open on this
        # specific path to raise OSError. Cross-platform (chmod-based
        # unreadable doesn't work on Windows for the current user).
        original_open = Path.open

        def _raise_on_target(self, *args, **kwargs):
            if self == path:
                raise OSError("Permission denied (simulated)")
            return original_open(self, *args, **kwargs)

        monkeypatch.setattr(Path, "open", _raise_on_target)
        result = _parse_jsonl_metadata(path)
        assert result.unreadable is True
        assert result.parse_error is not None
        assert "read failed" in result.parse_error

    def test_unreadable_flag_false_on_degraded_parse(self, tmp_path):
        """Missing sessionId → filename fallback → parse_error but unreadable=False.

        The record is still usable evidence — vendor_session_id gets the
        filename stem. CLI should upload it, not skip.
        """
        path = tmp_path / "proj" / "abcdef-1234.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "file-history-delta"}) + "\n")
        result = _parse_jsonl_metadata(path)
        assert result.vendor_session_id == "abcdef-1234"
        assert result.parse_error and "fell back to filename" in result.parse_error
        assert result.unreadable is False

    def test_unreadable_flag_default_false_on_clean_parse(self, tmp_path):
        """Well-formed transcript → unreadable=False, no parse_error."""
        path = tmp_path / "proj" / "s.jsonl"
        _write_transcript(
            path,
            session_id="s",
            events=[_turn("user", "2026-08-07T10:00:00.000Z")],
        )
        result = _parse_jsonl_metadata(path)
        assert result.unreadable is False
        assert result.parse_error is None

    def test_claude_root_path_returns_default(self, monkeypatch):
        """Accessor returns the same path _default_claude_root() would."""
        monkeypatch.delenv("CLAUDE_TRANSCRIPTS_ROOT", raising=False)
        expected = Path(os.path.expanduser("~/.claude/projects"))
        assert claude_root_path() == expected

    def test_claude_root_path_honors_env_override(self, tmp_path, monkeypatch):
        """Env override propagates through the public accessor.

        The CLI relies on this to check the SAME root the discovery code will
        actually walk — must not diverge.
        """
        override = tmp_path / "some-other-root"
        monkeypatch.setenv("CLAUDE_TRANSCRIPTS_ROOT", str(override))
        assert claude_root_path() == override
