"""
Tests for gator-session-block.py — session-block companion capture.

Tests extraction engine functions using synthetic data (no real vendor
transcripts or git repos).
"""

import gzip
import json
from pathlib import Path

import pytest

from conftest import load_script

sb = load_script("gator-session-block")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_snippet(commit="abc1234567890abcdef1234567890abcdef123456",
                  short_commit="abc1234",
                  transcript_session_id="test-uuid-1234",
                  vendor_inferred="anthropic",
                  previous_commit_in_session=None,
                  commit_index=0,
                  **overrides):
    """Build a minimal snippet dict for testing."""
    d = {
        "schema": "gator-session-snippet-v2",
        "type": "session_snippet",
        "commit": commit,
        "short_commit": short_commit,
        "snippet_id": f"snippet-{short_commit}",
        "session_id": "20260621-claude-opus-4-6-120000",
        "session_group_key": f"anthropic:{transcript_session_id}",
        "transcript_session_id": transcript_session_id,
        "repo": "test-repo",
        "branch": "main",
        "commit_index": commit_index,
        "previous_commit_in_session": previous_commit_in_session,
        "started_at": "2026-06-21T12:00:00Z",
        "ended_at": "2026-06-21T12:30:00Z",
        "vendor_inferred": vendor_inferred,
        "model_inferred": "claude-opus-4-6",
        "machine_id": "test-machine",
    }
    d.update(overrides)
    return d


def _write_snippet(snippets_dir, snippet, stem=None):
    """Write a snippet to the snippets directory. Returns the path."""
    if stem is None:
        stem = f"2026-06-21-test-repo-{snippet['short_commit']}"
    path = snippets_dir / f"{stem}.json"
    path.write_text(json.dumps(snippet, indent=2), encoding="utf-8")
    return path


def _make_claude_jsonl(turns_data):
    """Build Claude Code JSONL content from a list of turn specs.

    Each spec: {"type": str, "role": str, "content": str|list, "timestamp": str}
    """
    lines = []
    for t in turns_data:
        entry = {
            "type": t.get("type", "assistant"),
            "message": {
                "role": t.get("role", "assistant"),
                "content": t.get("content", ""),
            },
            "timestamp": t.get("timestamp", "2026-06-21T12:00:00Z"),
        }
        lines.append(json.dumps(entry))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Snippet resolution
# ---------------------------------------------------------------------------

class TestResolveSnippet:
    def test_one_snippet_found(self, tmp_path):
        gator_dir = tmp_path / ".gator"
        snippets_dir = gator_dir / "session-snippets"
        snippets_dir.mkdir(parents=True)

        snippet = _make_snippet()
        _write_snippet(snippets_dir, snippet)

        result, path = sb.resolve_snippet(gator_dir, snippet["commit"])
        assert result["commit"] == snippet["commit"]
        assert result["short_commit"] == snippet["short_commit"]

    def test_zero_snippets_raises(self, tmp_path):
        gator_dir = tmp_path / ".gator"
        snippets_dir = gator_dir / "session-snippets"
        snippets_dir.mkdir(parents=True)

        with pytest.raises(sb.SnippetNotFound):
            sb.resolve_snippet(gator_dir, "deadbeef" * 5)

    def test_multiple_snippets_raises(self, tmp_path):
        gator_dir = tmp_path / ".gator"
        snippets_dir = gator_dir / "session-snippets"
        snippets_dir.mkdir(parents=True)

        snippet = _make_snippet()
        _write_snippet(snippets_dir, snippet, stem="dup-1")
        _write_snippet(snippets_dir, snippet, stem="dup-2")

        with pytest.raises(sb.SnippetInvariantViolation):
            sb.resolve_snippet(gator_dir, snippet["commit"])

    def test_no_snippets_dir_raises(self, tmp_path):
        gator_dir = tmp_path / ".gator"
        gator_dir.mkdir()

        with pytest.raises(sb.SnippetNotFound):
            sb.resolve_snippet(gator_dir, "deadbeef" * 5)


# ---------------------------------------------------------------------------
# Transcript discovery
# ---------------------------------------------------------------------------

class TestDiscoverTranscript:
    def test_claude_found(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        session_id = "test-uuid-abcd"
        project_dir = tmp_path / ".claude" / "projects" / "test-project"
        project_dir.mkdir(parents=True)
        transcript = project_dir / f"{session_id}.jsonl"
        transcript.write_text("{}\n", encoding="utf-8")

        result = sb.discover_transcript("anthropic", session_id)
        assert result == transcript

    def test_not_found_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        with pytest.raises(sb.TranscriptNotFound):
            sb.discover_transcript("anthropic", "nonexistent-uuid")

    def test_multiple_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        session_id = "test-uuid-multi"

        for slug in ("proj-a", "proj-b"):
            d = tmp_path / ".claude" / "projects" / slug
            d.mkdir(parents=True)
            (d / f"{session_id}.jsonl").write_text("{}\n", encoding="utf-8")

        with pytest.raises(sb.MultipleTranscriptsFound) as exc_info:
            sb.discover_transcript("anthropic", session_id)
        assert len(exc_info.value.candidates) == 2

    def test_unknown_vendor_searches_claude(self, tmp_path, monkeypatch):
        """Unknown vendor still searches Claude paths."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        session_id = "test-uuid-unknown"
        project_dir = tmp_path / ".claude" / "projects" / "proj"
        project_dir.mkdir(parents=True)
        transcript = project_dir / f"{session_id}.jsonl"
        transcript.write_text("{}\n", encoding="utf-8")

        result = sb.discover_transcript("unknown", session_id)
        assert result == transcript

    def test_openai_vendor_searches_codex(self, tmp_path, monkeypatch):
        """Canonical vendor 'openai' searches Codex paths."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        session_id = "test-uuid-codex"
        codex_dir = tmp_path / ".codex" / "sessions" / "2026-06-21" / "sub"
        codex_dir.mkdir(parents=True)
        transcript = codex_dir / f"rollout-0-{session_id}.jsonl"
        transcript.write_text("{}\n", encoding="utf-8")

        result = sb.discover_transcript("openai", session_id)
        assert result == transcript

    def test_google_vendor_searches_gemini(self, tmp_path, monkeypatch):
        """Canonical vendor 'google' searches Gemini paths."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        session_id = "test-uuid-gemini"
        gemini_dir = tmp_path / ".gemini" / "tmp" / "projhash" / "chats"
        gemini_dir.mkdir(parents=True)
        transcript = gemini_dir / f"session-0-{session_id}.json"
        transcript.write_text("{}\n", encoding="utf-8")

        result = sb.discover_transcript("google", session_id)
        assert result == transcript


# ---------------------------------------------------------------------------
# Anchor scanning
# ---------------------------------------------------------------------------

class TestFindCommitAnchors:
    def test_both_hashes_found(self):
        turns = [
            {"content": "starting work", "is_tool_output": False},
            {"content": "[main abc1234] First commit", "is_tool_output": True},
            {"content": "more work", "is_tool_output": False},
            {"content": "[main def5678] Second commit", "is_tool_output": True},
            {"content": "done", "is_tool_output": False},
        ]
        start, end, start_found = sb.find_commit_anchors(turns, "abc1234", "def5678")
        assert start == 1
        assert end == 3
        assert start_found is True

    def test_first_commit_no_start(self):
        turns = [
            {"content": "hello", "is_tool_output": False},
            {"content": "[main abc1234] Initial commit", "is_tool_output": True},
        ]
        start, end, start_found = sb.find_commit_anchors(turns, None, "abc1234")
        assert start == 0
        assert end == 1
        assert start_found is False

    def test_end_not_found_raises(self):
        turns = [
            {"content": "[main abc1234] commit", "is_tool_output": True},
        ]
        with pytest.raises(sb.AnchorNotFound):
            sb.find_commit_anchors(turns, "abc1234", "missing1")

    def test_hash_in_non_tool_output_ignored(self):
        """Hash in conversational text should NOT be matched."""
        turns = [
            {"content": "[main def5678] I mentioned a commit", "is_tool_output": False},
            {"content": "[main abc1234] real commit", "is_tool_output": True},
        ]
        # def5678 is in conversation, not tool output — should not be found
        with pytest.raises(sb.AnchorNotFound):
            sb.find_commit_anchors(turns, "abc1234", "def5678")

    def test_empty_start_hash(self):
        """Empty string start hash treated as no start."""
        turns = [
            {"content": "hello", "is_tool_output": False},
            {"content": "[main abc1234] commit", "is_tool_output": True},
        ]
        start, end, start_found = sb.find_commit_anchors(turns, "", "abc1234")
        assert start == 0
        assert end == 1
        assert start_found is False

    def test_start_hash_provided_but_not_found_raises(self):
        """Truthy start hash that doesn't appear in tool output → AnchorNotFound."""
        turns = [
            {"content": "[main def5678] Second commit", "is_tool_output": True},
        ]
        with pytest.raises(sb.AnchorNotFound, match="Start anchor"):
            sb.find_commit_anchors(turns, "abc1234", "def5678")


# ---------------------------------------------------------------------------
# Parse + normalize
# ---------------------------------------------------------------------------

class TestParseClaudeTranscript:
    def test_basic_parse(self, tmp_path):
        jsonl = _make_claude_jsonl([
            {"type": "user", "role": "user", "content": "Fix the bug"},
            {"type": "assistant", "role": "assistant", "content": [
                {"type": "text", "text": "I'll fix it"},
                {"type": "tool_use", "name": "Edit", "input": {"file": "a.py"}},
            ]},
        ])
        f = tmp_path / "transcript.jsonl"
        f.write_text(jsonl, encoding="utf-8")

        turns = sb.parse_claude_transcript(f)
        assert len(turns) == 2
        assert turns[0]["role"] == "user"
        assert turns[0]["content"] == "Fix the bug"
        assert turns[1]["role"] == "assistant"
        assert "I'll fix it" in turns[1]["content"]
        assert turns[1]["tool_calls"][0]["tool"] == "Edit"

    def test_tool_result_not_truncated(self, tmp_path):
        """Tool results should be full, not truncated to 200 chars."""
        long_content = "x" * 500
        jsonl = _make_claude_jsonl([
            {"type": "assistant", "role": "assistant", "content": [
                {"type": "tool_result", "content": long_content},
            ]},
        ])
        f = tmp_path / "transcript.jsonl"
        f.write_text(jsonl, encoding="utf-8")

        turns = sb.parse_claude_transcript(f)
        assert len(turns[0]["content"]) == 500
        assert turns[0]["is_tool_output"] is True

    def test_malformed_lines_skipped(self, tmp_path):
        content = '{"type":"user","message":{"role":"user","content":"ok"},"timestamp":""}\n'
        content += "NOT JSON\n"
        content += '{"type":"assistant","message":{"role":"assistant","content":"yes"},"timestamp":""}\n'
        f = tmp_path / "transcript.jsonl"
        f.write_text(content, encoding="utf-8")

        turns = sb.parse_claude_transcript(f)
        assert len(turns) == 2

    def test_is_tool_output_flag(self, tmp_path):
        jsonl = _make_claude_jsonl([
            {"type": "user", "role": "user", "content": "hello"},
            {"type": "assistant", "role": "assistant", "content": [
                {"type": "tool_result", "content": "file contents"},
            ]},
        ])
        f = tmp_path / "transcript.jsonl"
        f.write_text(jsonl, encoding="utf-8")

        turns = sb.parse_claude_transcript(f)
        assert turns[0]["is_tool_output"] is False
        assert turns[1]["is_tool_output"] is True


class TestNormalizeTurns:
    def test_seq_and_role_mapping(self):
        raw = [
            {"role": "user", "timestamp": "t1", "content": "a",
             "tool_calls": [], "is_tool_output": False},
            {"role": "assistant", "timestamp": "t2", "content": "b",
             "tool_calls": [], "is_tool_output": False},
            {"role": "assistant", "timestamp": "t3", "content": "c",
             "tool_calls": [], "is_tool_output": True},
        ]
        result = sb.normalize_turns(raw, 0, 2)
        assert len(result) == 3
        assert result[0]["seq"] == 1
        assert result[0]["role"] == "human"
        assert result[1]["seq"] == 2
        assert result[1]["role"] == "assistant"
        assert result[2]["seq"] == 3
        assert result[2]["role"] == "tool_result"

    def test_slicing(self):
        raw = [
            {"role": "user", "timestamp": "", "content": "a",
             "tool_calls": [], "is_tool_output": False},
            {"role": "assistant", "timestamp": "", "content": "b",
             "tool_calls": [], "is_tool_output": False},
            {"role": "user", "timestamp": "", "content": "c",
             "tool_calls": [], "is_tool_output": False},
        ]
        result = sb.normalize_turns(raw, 1, 2)
        assert len(result) == 2
        assert result[0]["seq"] == 1  # re-indexed
        assert result[0]["content"] == "b"


# ---------------------------------------------------------------------------
# Render + emit
# ---------------------------------------------------------------------------

class TestRenderSessionBlock:
    def test_valid_block(self):
        turns = [
            {"seq": 1, "role": "human", "ts": None, "content": "fix", "tool_calls": []},
            {"seq": 2, "role": "assistant", "ts": None, "content": "ok", "tool_calls": []},
            {"seq": 3, "role": "tool_result", "ts": None, "content": "done", "tool_calls": []},
        ]
        snippet = _make_snippet()
        block = sb.render_session_block(turns, "exact", "commit-hash-anchors", snippet)

        assert block["schema"] == "gator-session-block-v1"
        assert block["type"] == "session_block"
        assert block["target_commit"] == snippet["commit"]
        assert block["capture_status"] == "captured"
        assert block["capture_quality"] == "exact"
        assert block["content_policy"] == "raw"
        assert block["turn_count"] == 3
        assert block["metrics"]["human_turns"] == 1
        assert block["metrics"]["assistant_turns"] == 1
        assert block["metrics"]["tool_result_turns"] == 1

    def test_deterministic(self):
        turns = [
            {"seq": 1, "role": "human", "ts": None, "content": "x", "tool_calls": []},
        ]
        snippet = _make_snippet()
        b1 = sb.render_session_block(turns, "exact", "commit-hash-anchors", snippet)
        b2 = sb.render_session_block(turns, "exact", "commit-hash-anchors", snippet)
        # Everything except generated_at should be identical
        b1.pop("generated_at")
        b2.pop("generated_at")
        assert b1 == b2


class TestEmitSessionBlock:
    def test_writes_gzip(self, tmp_path):
        gator_dir = tmp_path / ".gator"
        gator_dir.mkdir()
        block = {"schema": "gator-session-block-v1", "turns": []}
        stem = "2026-06-21-test-repo-abc1234"

        out = sb.emit_session_block(gator_dir, block, stem)
        assert out.suffix == ".gz"
        assert out.exists()

        # Decompress and verify
        raw = gzip.decompress(out.read_bytes())
        parsed = json.loads(raw)
        assert parsed["schema"] == "gator-session-block-v1"

    def test_filename_stem(self, tmp_path):
        gator_dir = tmp_path / ".gator"
        gator_dir.mkdir()
        stem = "2026-06-21-test-repo-abc1234"
        out = sb.emit_session_block(gator_dir, {"test": True}, stem)
        assert out.name == f"{stem}.json.gz"

    def test_idempotent(self, tmp_path):
        gator_dir = tmp_path / ".gator"
        gator_dir.mkdir()
        block = {"test": True, "data": "same"}
        stem = "idem-test"

        out1 = sb.emit_session_block(gator_dir, block, stem)
        mtime1 = out1.stat().st_mtime
        out2 = sb.emit_session_block(gator_dir, block, stem)
        mtime2 = out2.stat().st_mtime

        assert out1 == out2
        # File should not have been rewritten
        assert mtime1 == mtime2


# ---------------------------------------------------------------------------
# Capture quality
# ---------------------------------------------------------------------------

class TestCaptureQuality:
    def test_both_anchors_exact(self):
        turns = [
            {"content": "[main aaa1111] first", "is_tool_output": True,
             "role": "assistant", "timestamp": "", "tool_calls": []},
            {"content": "work", "is_tool_output": False,
             "role": "user", "timestamp": "", "tool_calls": []},
            {"content": "[main bbb2222] second", "is_tool_output": True,
             "role": "assistant", "timestamp": "", "tool_calls": []},
        ]
        start_idx, end_idx, start_found = sb.find_commit_anchors(
            turns, "aaa1111", "bbb2222"
        )
        assert start_found is True
        norm = sb.normalize_turns(turns, start_idx, end_idx)
        assert len(norm) > 0

    def test_first_commit_bounded(self):
        turns = [
            {"content": "hello", "is_tool_output": False,
             "role": "user", "timestamp": "", "tool_calls": []},
            {"content": "[main abc1234] commit", "is_tool_output": True,
             "role": "assistant", "timestamp": "", "tool_calls": []},
        ]
        start_idx, end_idx, start_found = sb.find_commit_anchors(
            turns, None, "abc1234"
        )
        assert start_found is False
        assert start_idx == 0

    def test_start_provided_but_missing_raises(self):
        """If start hash is provided but not found, AnchorNotFound is raised."""
        turns = [
            {"content": "[main bbb2222] second", "is_tool_output": True,
             "role": "assistant", "timestamp": "", "tool_calls": []},
        ]
        with pytest.raises(sb.AnchorNotFound, match="Start anchor"):
            sb.find_commit_anchors(turns, "aaa1111", "bbb2222")


# ---------------------------------------------------------------------------
# Integration: fake transcript + snippets
# ---------------------------------------------------------------------------

class TestIntegration:
    def _build_scenario(self, tmp_path):
        """Build a fake Claude JSONL with two commits and matching snippets."""
        # Transcript with two commit outputs in tool results
        jsonl_lines = [
            # Pre-commit discussion
            json.dumps({
                "type": "user", "timestamp": "2026-06-21T12:00:00Z",
                "message": {"role": "user", "content": "Fix the parser bug"},
            }),
            json.dumps({
                "type": "assistant", "timestamp": "2026-06-21T12:01:00Z",
                "message": {"role": "assistant", "content": [
                    {"type": "text", "text": "I'll fix it"},
                ]},
            }),
            # First commit (tool output)
            json.dumps({
                "type": "assistant", "timestamp": "2026-06-21T12:05:00Z",
                "message": {"role": "assistant", "content": [
                    {"type": "tool_result",
                     "content": "[main aaa1111] Fix parser null check\n 1 file changed"},
                ]},
            }),
            # Work toward second commit
            json.dumps({
                "type": "user", "timestamp": "2026-06-21T12:10:00Z",
                "message": {"role": "user", "content": "Now add tests"},
            }),
            json.dumps({
                "type": "assistant", "timestamp": "2026-06-21T12:11:00Z",
                "message": {"role": "assistant", "content": [
                    {"type": "text", "text": "Adding tests now"},
                ]},
            }),
            # Second commit (tool output)
            json.dumps({
                "type": "assistant", "timestamp": "2026-06-21T12:15:00Z",
                "message": {"role": "assistant", "content": [
                    {"type": "tool_result",
                     "content": "[main bbb2222] Add parser tests\n 2 files changed"},
                ]},
            }),
        ]

        transcript_path = tmp_path / "transcript.jsonl"
        transcript_path.write_text("\n".join(jsonl_lines) + "\n", encoding="utf-8")

        # Snippets
        gator_dir = tmp_path / ".gator"
        snippets_dir = gator_dir / "session-snippets"
        snippets_dir.mkdir(parents=True)

        commit1_hash = "a" * 40
        commit2_hash = "b" * 40

        snippet1 = _make_snippet(
            commit=commit1_hash, short_commit="aaa1111",
            commit_index=0, previous_commit_in_session=None,
        )
        snippet2 = _make_snippet(
            commit=commit2_hash, short_commit="bbb2222",
            commit_index=1, previous_commit_in_session=commit1_hash,
        )
        _write_snippet(snippets_dir, snippet1, stem="2026-06-21-test-repo-aaa1111")
        _write_snippet(snippets_dir, snippet2, stem="2026-06-21-test-repo-bbb2222")

        return transcript_path, gator_dir, snippet1, snippet2

    def test_second_commit_exact_interval(self, tmp_path):
        transcript_path, gator_dir, snippet1, snippet2 = self._build_scenario(tmp_path)

        turns, quality, method = sb.extract_interval(
            transcript_path, "anthropic",
            start_short_hash="aaa1111",
            end_short_hash="bbb2222",
        )

        assert quality == "exact"
        assert method == "commit-hash-anchors"
        assert len(turns) >= 2
        # Should include the work between commits
        content_joined = " ".join(t["content"] for t in turns)
        assert "Now add tests" in content_joined or "Adding tests" in content_joined

    def test_first_commit_bounded(self, tmp_path):
        transcript_path, gator_dir, snippet1, snippet2 = self._build_scenario(tmp_path)

        turns, quality, method = sb.extract_interval(
            transcript_path, "anthropic",
            start_short_hash=None,
            end_short_hash="aaa1111",
        )

        assert quality == "bounded"
        assert len(turns) >= 1

    def test_full_pipeline(self, tmp_path):
        """End-to-end: parse → anchor → normalize → render → emit."""
        transcript_path, gator_dir, snippet1, snippet2 = self._build_scenario(tmp_path)

        turns, quality, method = sb.extract_interval(
            transcript_path, "anthropic", "aaa1111", "bbb2222",
        )

        block = sb.render_session_block(turns, quality, method, snippet2)
        assert block["schema"] == "gator-session-block-v1"
        assert block["target_commit"] == snippet2["commit"]
        assert block["turn_count"] == len(turns)
        assert block["capture_quality"] == "exact"

        out_path = sb.emit_session_block(gator_dir, block, "2026-06-21-test-repo-bbb2222")
        assert out_path.exists()

        # Verify roundtrip
        raw = gzip.decompress(out_path.read_bytes())
        recovered = json.loads(raw)
        assert recovered["target_commit"] == snippet2["commit"]
        assert recovered["turn_count"] == block["turn_count"]
