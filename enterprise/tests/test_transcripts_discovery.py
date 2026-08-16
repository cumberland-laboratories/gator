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
    _parse_codex_jsonl_metadata,
    _parse_jsonl_metadata,
    claude_root_path,
    codex_root_path,
    discover,
    discover_claude_transcripts,
    discover_codex_transcripts,
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
        # Phase 3 (2026-08-15) added codex; Phase 4 (2026-08-15) added
        # gemini — the unknown-vendor branch now needs a slug no adapter
        # will ever claim.
        with pytest.raises(ValueError, match="Unsupported vendor"):
            list(discover("not-a-vendor"))

    def test_codex_alias_resolves(self, fake_codex_root):
        # Both "codex" and "openai" dispatch to the Codex handler.
        assert len(list(discover("codex"))) == 2
        assert len(list(discover("openai"))) == 2


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


# ---------------------------------------------------------------------------
# Phase 3 (2026-08-15) — Codex CLI (OpenAI) adapter
# ---------------------------------------------------------------------------
#
# Format reference — Codex JSONL is a per-event stream with these top-level
# event types:
#   session_meta   — payload.id is the session UUID; payload.cwd = workspace
#   turn_context   — payload.model
#   response_item  — payload.role in (user, assistant) → counts as a turn
#   event_msg      — task lifecycle (not consumed by discovery)


def _codex_session_meta(session_id: str, cwd: str, ts: str) -> dict:
    return {
        "type": "session_meta",
        "timestamp": ts,
        "payload": {
            "id": session_id,
            "cwd": cwd,
            "cli_version": "0.1.0",
            "model_provider": "openai",
            "git": {"commit_hash": "abc123", "branch": "main"},
        },
    }


def _codex_turn_context(ts: str, model: str, cwd: str | None = None) -> dict:
    payload = {
        "turn_id": "t1",
        "model": model,
        "approval_policy": "on-request",
        "sandbox_policy": "workspace-write",
    }
    if cwd is not None:
        payload["cwd"] = cwd
    return {"type": "turn_context", "timestamp": ts, "payload": payload}


def _codex_response_item(ts: str, role: str, text: str = "") -> dict:
    return {
        "type": "response_item",
        "timestamp": ts,
        "payload": {
            "role": role,
            "type": "message",
            "content": [{"type": "text", "text": text}],
        },
    }


def _write_codex_transcript(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")


@pytest.fixture
def fake_codex_root(tmp_path, monkeypatch):
    """Populated ~/.codex/sessions/ tree with two rollout files."""
    root = tmp_path / "codex" / "sessions"

    _write_codex_transcript(
        root / "2026" / "08" / "07"
        / "rollout-2026-08-07T10-00-00-abc12345-uuid.jsonl",
        events=[
            _codex_session_meta(
                "abc12345-uuid",
                "/repo/first",
                "2026-08-07T10:00:00.000Z",
            ),
            _codex_turn_context("2026-08-07T10:00:01.000Z", "gpt-5"),
            _codex_response_item("2026-08-07T10:00:02.000Z", "user", "hi"),
            _codex_response_item("2026-08-07T10:00:05.100Z", "assistant", "hello"),
        ],
    )
    _write_codex_transcript(
        root / "2026" / "08" / "08"
        / "rollout-2026-08-08T09-00-00-def67890-uuid.jsonl",
        events=[
            _codex_session_meta(
                "def67890-uuid",
                "/repo/second",
                "2026-08-08T09:00:00.000Z",
            ),
            _codex_turn_context("2026-08-08T09:00:01.000Z", "gpt-5-codex"),
            _codex_response_item("2026-08-08T09:00:02.000Z", "assistant", "reply"),
        ],
    )

    monkeypatch.setenv("CODEX_TRANSCRIPTS_ROOT", str(root))
    return root


class TestParseSingleCodexTranscript:
    def test_extracts_session_id_from_session_meta(self, tmp_path):
        path = tmp_path / "rollout-abc.jsonl"
        _write_codex_transcript(
            path,
            events=[
                _codex_session_meta(
                    "abc12345-uuid",
                    "/repo/x",
                    "2026-08-07T10:00:00.000Z",
                ),
                _codex_response_item("2026-08-07T10:00:01.000Z", "user"),
            ],
        )
        result = _parse_codex_jsonl_metadata(path)
        assert result.vendor == "openai"
        assert result.vendor_session_id == "abc12345-uuid"
        assert result.workspace_hint == "/repo/x"
        assert result.parse_error is None
        assert result.unreadable is False

    def test_extracts_model_from_turn_context(self, tmp_path):
        path = tmp_path / "rollout-abc.jsonl"
        _write_codex_transcript(
            path,
            events=[
                _codex_session_meta(
                    "s", "/repo", "2026-08-07T10:00:00.000Z",
                ),
                _codex_turn_context("2026-08-07T10:00:01.000Z", "gpt-5-codex"),
                _codex_response_item("2026-08-07T10:00:02.000Z", "assistant"),
            ],
        )
        result = _parse_codex_jsonl_metadata(path)
        assert result.model == "gpt-5-codex"

    def test_session_meta_cwd_takes_precedence_over_turn_context(self, tmp_path):
        """session_meta.cwd is the initial workspace and wins over turn_context.cwd.

        If an operator cd's mid-session, turn_context emits a new cwd; we
        stick with the session_meta value as authoritative.
        """
        path = tmp_path / "rollout-abc.jsonl"
        _write_codex_transcript(
            path,
            events=[
                _codex_session_meta(
                    "s", "/original/cwd", "2026-08-07T10:00:00.000Z",
                ),
                _codex_turn_context(
                    "2026-08-07T10:00:01.000Z", "gpt-5",
                    cwd="/changed/cwd",
                ),
            ],
        )
        result = _parse_codex_jsonl_metadata(path)
        assert result.workspace_hint == "/original/cwd"

    def test_turn_count_only_user_and_assistant(self, tmp_path):
        """Turn count excludes tool / system / event_msg events."""
        path = tmp_path / "rollout-abc.jsonl"
        _write_codex_transcript(
            path,
            events=[
                _codex_session_meta("s", "/r", "2026-08-07T10:00:00.000Z"),
                _codex_response_item("2026-08-07T10:00:01.000Z", "user"),
                _codex_response_item("2026-08-07T10:00:02.000Z", "assistant"),
                _codex_response_item("2026-08-07T10:00:03.000Z", "tool"),
                {
                    "type": "event_msg",
                    "timestamp": "2026-08-07T10:00:04.000Z",
                    "payload": {"type": "task_complete"},
                },
                _codex_response_item("2026-08-07T10:00:05.000Z", "user"),
            ],
        )
        result = _parse_codex_jsonl_metadata(path)
        assert result.turn_count == 3

    def test_started_ended_span_all_event_timestamps(self, tmp_path):
        path = tmp_path / "rollout-abc.jsonl"
        _write_codex_transcript(
            path,
            events=[
                _codex_session_meta("s", "/r", "2026-08-07T10:00:00.000Z"),
                _codex_response_item("2026-08-07T10:00:05.100Z", "user"),
                _codex_response_item("2026-08-07T11:30:00.000Z", "assistant"),
            ],
        )
        result = _parse_codex_jsonl_metadata(path)
        assert result.started_at == datetime(2026, 8, 7, 10, 0, 0, tzinfo=timezone.utc)
        assert result.ended_at == datetime(2026, 8, 7, 11, 30, 0, tzinfo=timezone.utc)

    def test_falls_back_to_filename_uuid_when_session_meta_missing(self, tmp_path):
        """No session_meta.id → last hyphen-segment of stem becomes session_id."""
        path = tmp_path / "rollout-2026-05-28T08-33-48-fallbackid.jsonl"
        _write_codex_transcript(
            path,
            events=[
                # Only response_items, no session_meta.
                _codex_response_item("2026-08-07T10:00:00.000Z", "user"),
            ],
        )
        result = _parse_codex_jsonl_metadata(path)
        assert result.vendor_session_id == "fallbackid"
        assert result.parse_error and "fell back to filename" in result.parse_error
        assert result.unreadable is False

    def test_survives_malformed_lines(self, tmp_path):
        path = tmp_path / "rollout-abc.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            f.write(json.dumps(_codex_session_meta("s", "/r", "2026-08-07T10:00:00.000Z")) + "\n")
            f.write("not valid json at all\n")
            f.write("\n")
            f.write(json.dumps(_codex_response_item("2026-08-07T10:00:01.000Z", "user")) + "\n")
        result = _parse_codex_jsonl_metadata(path)
        assert result.vendor_session_id == "s"
        assert result.turn_count == 1

    def test_unreadable_flag_set_on_permission_error(self, tmp_path, monkeypatch):
        """Path.open OSError → unreadable=True + parse_error."""
        path = tmp_path / "rollout-abc.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")

        original_open = Path.open

        def _raise_on_target(self, *args, **kwargs):
            if self == path:
                raise OSError("Permission denied (simulated)")
            return original_open(self, *args, **kwargs)

        monkeypatch.setattr(Path, "open", _raise_on_target)
        result = _parse_codex_jsonl_metadata(path)
        assert result.unreadable is True
        assert result.parse_error is not None
        assert "read failed" in result.parse_error


class TestDiscoverCodex:
    def test_yields_every_rollout(self, fake_codex_root):
        found = list(discover_codex_transcripts())
        session_ids = sorted(r.vendor_session_id for r in found)
        assert session_ids == ["abc12345-uuid", "def67890-uuid"]
        assert all(r.vendor == "openai" for r in found)

    def test_since_filters_older_rollouts(self, fake_codex_root):
        cutoff = datetime(2026, 8, 8, 0, 0, 0, tzinfo=timezone.utc)
        found = list(discover_codex_transcripts(since=cutoff))
        assert [r.vendor_session_id for r in found] == ["def67890-uuid"]

    def test_returns_nothing_when_root_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CODEX_TRANSCRIPTS_ROOT", str(tmp_path / "does-not-exist"))
        assert list(discover_codex_transcripts()) == []

    def test_returns_nothing_when_root_empty(self, tmp_path, monkeypatch):
        empty_root = tmp_path / "empty-codex"
        empty_root.mkdir()
        monkeypatch.setenv("CODEX_TRANSCRIPTS_ROOT", str(empty_root))
        assert list(discover_codex_transcripts()) == []

    def test_ignores_non_rollout_files(self, tmp_path, monkeypatch):
        """Only rollout-*.jsonl files should be picked up."""
        root = tmp_path / "codex" / "sessions" / "2026" / "08" / "07"
        root.mkdir(parents=True)
        (root / "not-a-rollout.jsonl").write_text("{}\n", encoding="utf-8")
        (root / "rollout-README.txt").write_text("hi\n", encoding="utf-8")
        _write_codex_transcript(
            root / "rollout-2026-08-07T10-00-00-real-uuid.jsonl",
            events=[
                _codex_session_meta("real-uuid", "/r", "2026-08-07T10:00:00.000Z"),
            ],
        )
        monkeypatch.setenv(
            "CODEX_TRANSCRIPTS_ROOT",
            str(tmp_path / "codex" / "sessions"),
        )
        found = list(discover_codex_transcripts())
        assert [r.vendor_session_id for r in found] == ["real-uuid"]


class TestCodexRootAccessor:
    """Codex root parallel to the Claude root_path tests."""

    def test_codex_root_path_returns_default(self, monkeypatch):
        monkeypatch.delenv("CODEX_TRANSCRIPTS_ROOT", raising=False)
        expected = Path(os.path.expanduser("~/.codex/sessions"))
        assert codex_root_path() == expected

    def test_codex_root_path_honors_env_override(self, tmp_path, monkeypatch):
        override = tmp_path / "some-other-codex-root"
        monkeypatch.setenv("CODEX_TRANSCRIPTS_ROOT", str(override))
        assert codex_root_path() == override
