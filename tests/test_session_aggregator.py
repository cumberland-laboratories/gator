"""
Tests for gator-session-aggregator.py — session summary aggregator.

Covers snippet reading, aggregation, goal derivation, fingerprinting,
cache freshness, transcript-ref aggregation, and fleet iteration.
"""

import json
import os
from pathlib import Path

import pytest

from conftest import load_script

agg = load_script("gator-session-aggregator")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_snippet(session_id="20260619-claude-opus-4-6-223347", repo="test-repo",
                 commit="aaa111", short_commit="aaa111", intent="Fix bug",
                 change_type="fix", significance="routine", branch="main",
                 files_touched=None, decision_tags=None, notes=None,
                 architect="AG", vendor_inferred="anthropic",
                 model_inferred="claude-opus-4-6", agent="claude-opus-4-6",
                 started_at="2026-06-19T22:33:46Z",
                 ended_at="2026-06-19T22:45:00Z",
                 transcript_session_id=None, transcript_ref=None,
                 session_group_key=None,
                 machine_label="test-machine"):
    return {
        "schema": "gator-session-snippet-v2",
        "type": "session_snippet",
        "session_id": session_id,
        "session_group_key": session_group_key,
        "repo": repo,
        "commit": commit,
        "short_commit": short_commit,
        "intent": intent,
        "change_type": change_type,
        "significance": significance,
        "branch": branch,
        "files_touched": files_touched or ["file.py"],
        "decision_tags": decision_tags or ["fix"],
        "notes": notes or [],
        "architect": architect,
        "vendor_inferred": vendor_inferred,
        "model_inferred": model_inferred,
        "agent": agent,
        "started_at": started_at,
        "ended_at": ended_at,
        "transcript_session_id": transcript_session_id,
        "transcript_ref": transcript_ref,
        "machine_label": machine_label,
        "charter_changed": False,
        "machine_id": "test-machine-id",
    }


def write_snippet(snippet_dir, snippet, filename=None):
    """Write a snippet dict as JSON to the snippet directory."""
    if filename is None:
        commit = snippet.get("commit", "unknown")
        filename = f"2026-06-19-test-repo-{commit}.json"
    path = snippet_dir / filename
    raw = json.dumps(snippet, indent=2).encode("utf-8")
    path.write_bytes(raw)
    return path


def setup_repo_with_snippets(tmp_path, snippets):
    """Create a repo directory with .gator/session-snippets/ and write snippets."""
    snippet_dir = tmp_path / ".gator" / "session-snippets"
    snippet_dir.mkdir(parents=True)
    for i, s in enumerate(snippets):
        write_snippet(snippet_dir, s, filename=f"snippet-{i}.json")
    return tmp_path


# ---------------------------------------------------------------------------
# read_snippets
# ---------------------------------------------------------------------------

class TestReadSnippets:
    def test_reads_json_snippets(self, tmp_path):
        s = make_snippet()
        setup_repo_with_snippets(tmp_path, [s])
        records = agg.read_snippets(str(tmp_path))
        assert len(records) == 1
        assert records[0]["data"]["session_id"] == s["session_id"]
        assert isinstance(records[0]["raw_bytes"], bytes)
        assert records[0]["path"].endswith(".json")

    def test_missing_directory_returns_empty(self, tmp_path):
        assert agg.read_snippets(str(tmp_path)) == []

    def test_skips_legacy_md_files(self, tmp_path):
        snippet_dir = tmp_path / ".gator" / "session-snippets"
        snippet_dir.mkdir(parents=True)
        (snippet_dir / "old-snippet.md").write_text("---\nschema: v1\n---\n")
        write_snippet(snippet_dir, make_snippet())
        records = agg.read_snippets(str(tmp_path))
        assert len(records) == 1  # only the .json

    def test_skips_corrupt_json(self, tmp_path):
        snippet_dir = tmp_path / ".gator" / "session-snippets"
        snippet_dir.mkdir(parents=True)
        (snippet_dir / "bad.json").write_text("{not valid json")
        write_snippet(snippet_dir, make_snippet())
        records = agg.read_snippets(str(tmp_path))
        assert len(records) == 1

    def test_skips_missing_schema(self, tmp_path):
        snippet_dir = tmp_path / ".gator" / "session-snippets"
        snippet_dir.mkdir(parents=True)
        (snippet_dir / "no-schema.json").write_text('{"foo": "bar"}')
        write_snippet(snippet_dir, make_snippet())
        records = agg.read_snippets(str(tmp_path))
        assert len(records) == 1


# ---------------------------------------------------------------------------
# aggregate_sessions
# ---------------------------------------------------------------------------

class TestAggregateSessions:
    def test_single_snippet_session(self, tmp_path):
        s = make_snippet()
        summaries = agg.aggregate_sessions([s], str(tmp_path))
        assert len(summaries) == 1
        summary = summaries[0]
        assert summary["session_id"] == s["session_id"]
        assert summary["commit_count"] == 1
        assert summary["schema"] == "gator-session-summary-v1"
        assert summary["repo_key"] == agg.session_cache_key(str(tmp_path))

    def test_multi_snippet_aggregation(self, tmp_path):
        s1 = make_snippet(commit="aaa", started_at="2026-06-19T22:00:00Z",
                          ended_at="2026-06-19T22:30:00Z", intent="Fix bug",
                          files_touched=["a.py"], decision_tags=["fix"],
                          significance="routine")
        s2 = make_snippet(commit="bbb", started_at="2026-06-19T22:30:00Z",
                          ended_at="2026-06-19T23:00:00Z", intent="Add feature",
                          change_type="feature", files_touched=["b.py"],
                          decision_tags=["feature"], significance="minor")
        summaries = agg.aggregate_sessions([s1, s2], str(tmp_path))
        assert len(summaries) == 1
        summary = summaries[0]
        assert summary["commit_count"] == 2
        assert summary["started_at"] == "2026-06-19T22:00:00Z"
        assert summary["ended_at"] == "2026-06-19T23:00:00Z"
        assert "a.py" in summary["files_touched"]
        assert "b.py" in summary["files_touched"]
        assert "fix" in summary["decision_tags"]
        assert "feature" in summary["decision_tags"]
        assert summary["significance"] == "minor"  # max of routine, minor
        assert len(summary["intents"]) == 2

    def test_separate_sessions(self, tmp_path):
        s1 = make_snippet(session_id="session-1")
        s2 = make_snippet(session_id="session-2")
        summaries = agg.aggregate_sessions([s1, s2], str(tmp_path))
        assert len(summaries) == 2

    def test_max_significance(self, tmp_path):
        s1 = make_snippet(commit="a", significance="routine")
        s2 = make_snippet(commit="b", significance="high")
        s3 = make_snippet(commit="c", significance="minor")
        summaries = agg.aggregate_sessions([s1, s2, s3], str(tmp_path))
        assert summaries[0]["significance"] == "high"


# ---------------------------------------------------------------------------
# effective_session_key
# ---------------------------------------------------------------------------

class TestEffectiveSessionKey:
    def test_vendor_session_group_key(self):
        """Uses session_group_key when present."""
        s = make_snippet(session_group_key="anthropic:sess-abc", repo="my-repo")
        assert agg.effective_session_key(s) == "group:my-repo:anthropic:sess-abc"

    def test_legacy_fallback(self):
        """Falls back to session_id when session_group_key is None."""
        s = make_snippet(session_id="legacy-id", repo="my-repo", session_group_key=None)
        assert agg.effective_session_key(s) == "legacy:my-repo:legacy-id"

    def test_empty_session_group_key(self):
        """Empty string session_group_key treated as absent."""
        s = make_snippet(session_id="sid", session_group_key="")
        # Truthy check: empty string is falsy
        key = agg.effective_session_key(s)
        assert key.startswith("legacy:")

    def test_deterministic(self):
        """Same snippet always produces same key."""
        s = make_snippet(session_group_key="anthropic:x")
        assert agg.effective_session_key(s) == agg.effective_session_key(s)


# ---------------------------------------------------------------------------
# Vendor session grouping
# ---------------------------------------------------------------------------

class TestVendorSessionGrouping:
    def test_same_group_key_different_session_id(self, tmp_path):
        """Snippets with same session_group_key but different session_id are grouped together."""
        s1 = make_snippet(commit="aaa", session_id="gator-sid-1",
                          session_group_key="anthropic:vendor-sess-1",
                          started_at="2026-06-19T22:00:00Z")
        s2 = make_snippet(commit="bbb", session_id="gator-sid-2",
                          session_group_key="anthropic:vendor-sess-1",
                          started_at="2026-06-19T22:30:00Z")
        summaries = agg.aggregate_sessions([s1, s2], str(tmp_path))
        assert len(summaries) == 1
        assert summaries[0]["commit_count"] == 2
        assert summaries[0]["session_group_key"] == "anthropic:vendor-sess-1"
        # session_id comes from first snippet for backward compat
        assert summaries[0]["session_id"] == "gator-sid-1"

    def test_different_group_keys_stay_separate(self, tmp_path):
        """Different session_group_key values produce separate sessions."""
        s1 = make_snippet(commit="aaa", session_group_key="anthropic:sess-1")
        s2 = make_snippet(commit="bbb", session_group_key="anthropic:sess-2")
        summaries = agg.aggregate_sessions([s1, s2], str(tmp_path))
        assert len(summaries) == 2

    def test_mixed_vendor_and_legacy(self, tmp_path):
        """Vendor-keyed and legacy snippets are never merged."""
        s1 = make_snippet(commit="aaa", session_group_key="anthropic:sess-1",
                          session_id="shared-sid")
        s2 = make_snippet(commit="bbb", session_group_key=None,
                          session_id="shared-sid")
        summaries = agg.aggregate_sessions([s1, s2], str(tmp_path))
        assert len(summaries) == 2

    def test_legacy_grouping_unchanged(self, tmp_path):
        """Without session_group_key, snippets still group by session_id."""
        s1 = make_snippet(commit="aaa", session_id="same-sid",
                          session_group_key=None)
        s2 = make_snippet(commit="bbb", session_id="same-sid",
                          session_group_key=None)
        summaries = agg.aggregate_sessions([s1, s2], str(tmp_path))
        assert len(summaries) == 1
        assert summaries[0]["commit_count"] == 2
        assert summaries[0]["session_group_key"] is None


# ---------------------------------------------------------------------------
# models field
# ---------------------------------------------------------------------------

class TestModelsAggregation:
    def test_single_model(self, tmp_path):
        s = make_snippet(model_inferred="claude-opus-4-6")
        summaries = agg.aggregate_sessions([s], str(tmp_path))
        assert summaries[0]["models"] == ["claude-opus-4-6"]
        # Legacy model field: first snippet's model
        assert summaries[0]["model"] == "claude-opus-4-6"

    def test_multiple_distinct_models(self, tmp_path):
        s1 = make_snippet(commit="aaa", model_inferred="claude-opus-4-6")
        s2 = make_snippet(commit="bbb", model_inferred="claude-sonnet-4-6")
        summaries = agg.aggregate_sessions([s1, s2], str(tmp_path))
        assert summaries[0]["models"] == ["claude-opus-4-6", "claude-sonnet-4-6"]
        # Legacy model: first snippet's
        assert summaries[0]["model"] == "claude-opus-4-6"

    def test_duplicate_models_deduplicated(self, tmp_path):
        s1 = make_snippet(commit="aaa", model_inferred="claude-opus-4-6")
        s2 = make_snippet(commit="bbb", model_inferred="claude-opus-4-6")
        summaries = agg.aggregate_sessions([s1, s2], str(tmp_path))
        assert summaries[0]["models"] == ["claude-opus-4-6"]


# ---------------------------------------------------------------------------
# Transcript ref aggregation (fix for finding #1)
# ---------------------------------------------------------------------------

class TestTranscriptRefAggregation:
    def test_first_nonempty_transcript_ref(self, tmp_path):
        """Empty string in first snippet should not block later non-empty value."""
        s1 = make_snippet(commit="a", transcript_ref="",
                          transcript_session_id="")
        s2 = make_snippet(commit="b", transcript_ref="ref-123",
                          transcript_session_id="tsid-456")
        summaries = agg.aggregate_sessions([s1, s2], str(tmp_path))
        assert summaries[0]["transcript_ref"] == "ref-123"
        assert summaries[0]["transcript_session_id"] == "tsid-456"

    def test_none_in_first_snippet(self, tmp_path):
        """None in first snippet should not block later non-empty value."""
        s1 = make_snippet(commit="a", transcript_ref=None,
                          transcript_session_id=None)
        s2 = make_snippet(commit="b", transcript_ref="ref-789",
                          transcript_session_id="tsid-012")
        summaries = agg.aggregate_sessions([s1, s2], str(tmp_path))
        assert summaries[0]["transcript_ref"] == "ref-789"
        assert summaries[0]["transcript_session_id"] == "tsid-012"

    def test_all_empty_stays_none(self, tmp_path):
        s1 = make_snippet(commit="a", transcript_ref=None,
                          transcript_session_id=None)
        s2 = make_snippet(commit="b", transcript_ref="",
                          transcript_session_id="")
        summaries = agg.aggregate_sessions([s1, s2], str(tmp_path))
        # Should be falsy (None or "")
        assert not summaries[0]["transcript_ref"]
        assert not summaries[0]["transcript_session_id"]


# ---------------------------------------------------------------------------
# derive_goal
# ---------------------------------------------------------------------------

class TestDeriveGoal:
    def test_single_intent(self):
        assert agg.derive_goal(["Fix auth bug"], []) == "Fix auth bug"

    def test_empty_intents(self):
        assert agg.derive_goal([], []) is None

    def test_skips_release(self):
        commits = [
            {"intent": "Release v1.0", "change_type": "release"},
            {"intent": "Add dashboard", "change_type": "feature"},
        ]
        intents = ["Release v1.0", "Add dashboard"]
        assert agg.derive_goal(intents, commits) == "Add dashboard"

    def test_skips_merge(self):
        commits = [
            {"intent": "Merge main", "change_type": "merge"},
            {"intent": "Fix tests", "change_type": "fix"},
        ]
        intents = ["Merge main", "Fix tests"]
        assert agg.derive_goal(intents, commits) == "Fix tests"

    def test_skips_cleanup(self):
        commits = [
            {"intent": "Cleanup imports", "change_type": "cleanup"},
            {"intent": "Add API", "change_type": "feature"},
        ]
        intents = ["Cleanup imports", "Add API"]
        assert agg.derive_goal(intents, commits) == "Add API"

    def test_falls_back_to_first_if_all_skipped(self):
        commits = [
            {"intent": "Release v1.0", "change_type": "release"},
            {"intent": "Merge main", "change_type": "merge"},
        ]
        intents = ["Release v1.0", "Merge main"]
        assert agg.derive_goal(intents, commits) == "Release v1.0"


# ---------------------------------------------------------------------------
# Fingerprinting
# ---------------------------------------------------------------------------

class TestFingerprint:
    def test_deterministic(self):
        r1 = {"raw_bytes": b'{"a": 1}'}
        r2 = {"raw_bytes": b'{"b": 2}'}
        fp1 = agg.snippet_fingerprint([r1, r2])
        fp2 = agg.snippet_fingerprint([r1, r2])
        assert fp1 == fp2
        assert fp1.startswith("sha256:")

    def test_order_independent(self):
        r1 = {"raw_bytes": b'{"a": 1}'}
        r2 = {"raw_bytes": b'{"b": 2}'}
        fp_ab = agg.snippet_fingerprint([r1, r2])
        fp_ba = agg.snippet_fingerprint([r2, r1])
        assert fp_ab == fp_ba

    def test_content_change_invalidates(self):
        r1 = {"raw_bytes": b'{"a": 1}'}
        r1_mod = {"raw_bytes": b'{"a": 2}'}
        fp1 = agg.snippet_fingerprint([r1])
        fp2 = agg.snippet_fingerprint([r1_mod])
        assert fp1 != fp2


# ---------------------------------------------------------------------------
# Cache freshness
# ---------------------------------------------------------------------------

class TestCacheFreshness:
    def test_fresh_cache_is_reused(self, tmp_path):
        snippets = [make_snippet()]
        setup_repo_with_snippets(tmp_path, snippets)

        # First call populates cache
        s1 = agg.get_session_summaries(str(tmp_path))
        assert len(s1) == 1
        gen1 = s1[0]["generated_at"]

        # Second call should reuse cache (same generated_at)
        s2 = agg.get_session_summaries(str(tmp_path))
        assert s2[0]["generated_at"] == gen1

    def test_force_refresh_regenerates(self, tmp_path):
        snippets = [make_snippet()]
        setup_repo_with_snippets(tmp_path, snippets)

        s1 = agg.get_session_summaries(str(tmp_path))

        # Tamper with the cached file to prove force_refresh actually regenerates.
        # Write a bogus generated_at into the cache — if force_refresh works,
        # the returned summary will have a fresh generated_at, not the bogus one.
        cpath = agg.cache_dir(str(tmp_path))
        for f in cpath.glob("*.json"):
            if f.name == "_repo.json":
                continue
            data = json.loads(f.read_text())
            data["generated_at"] = "1999-01-01T00:00:00Z"
            f.write_text(json.dumps(data))

        # Without force_refresh, should return the tampered cache
        s_cached = agg.get_session_summaries(str(tmp_path))
        assert s_cached[0]["generated_at"] == "1999-01-01T00:00:00Z"

        # With force_refresh, should regenerate past the tampered cache
        s2 = agg.get_session_summaries(str(tmp_path), force_refresh=True)
        assert s2[0]["generated_at"] != "1999-01-01T00:00:00Z"
        assert s2[0]["schema"] == "gator-session-summary-v1"

    def test_new_snippet_invalidates_cache(self, tmp_path):
        snippets = [make_snippet(commit="aaa")]
        repo = setup_repo_with_snippets(tmp_path, snippets)

        s1 = agg.get_session_summaries(str(repo))
        assert s1[0]["commit_count"] == 1

        # Add a second snippet
        snippet_dir = repo / ".gator" / "session-snippets"
        write_snippet(snippet_dir, make_snippet(
            commit="bbb", intent="Second commit",
            started_at="2026-06-19T23:00:00Z",
            ended_at="2026-06-19T23:30:00Z",
        ), filename="snippet-new.json")

        s2 = agg.get_session_summaries(str(repo))
        assert s2[0]["commit_count"] == 2


# ---------------------------------------------------------------------------
# Fleet aggregation
# ---------------------------------------------------------------------------

class TestFleetSummaries:
    def test_fleet_across_repos(self, tmp_path):
        # Create two repos
        repo1 = tmp_path / "repo1"
        repo2 = tmp_path / "repo2"
        setup_repo_with_snippets(repo1, [
            make_snippet(repo="repo1", session_id="s1",
                         started_at="2026-06-19T22:00:00Z"),
        ])
        setup_repo_with_snippets(repo2, [
            make_snippet(repo="repo2", session_id="s2",
                         started_at="2026-06-20T10:00:00Z"),
        ])

        # Write registry
        registry = tmp_path / "registry.json"
        registry.write_text(json.dumps({
            "schema": "gator-dashboard-registry-v1",
            "repos": [
                {"name": "repo1", "path": str(repo1)},
                {"name": "repo2", "path": str(repo2)},
            ]
        }))

        summaries = agg.get_fleet_summaries(str(registry))
        assert len(summaries) == 2
        # Most recent first
        assert summaries[0]["repo"] == "repo2"
        assert summaries[1]["repo"] == "repo1"

    def test_fleet_skips_missing_repos(self, tmp_path):
        repo1 = tmp_path / "exists"
        setup_repo_with_snippets(repo1, [make_snippet(repo="exists")])

        registry = tmp_path / "registry.json"
        registry.write_text(json.dumps({
            "schema": "gator-dashboard-registry-v1",
            "repos": [
                {"name": "exists", "path": str(repo1)},
                {"name": "gone", "path": str(tmp_path / "nonexistent")},
            ]
        }))

        summaries = agg.get_fleet_summaries(str(registry))
        assert len(summaries) == 1
        assert summaries[0]["repo"] == "exists"

    def test_fleet_missing_registry(self, tmp_path):
        assert agg.get_fleet_summaries(str(tmp_path / "nope.json")) == []
