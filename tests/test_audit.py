"""
Tests for gator-audit.py — convergence dashboard.

Tests the presentation layer and decision filter. The audit dashboard
is the investor-facing output — its correctness is product credibility.
"""

import json

import pytest

from conftest import load_script

audit = load_script("gator-audit")


class TestIsRealDecision:
    def test_filters_bare_confirmations(self):
        """Short confirmations are not governance decisions."""
        assert audit._is_real_decision("yes") is False
        assert audit._is_real_decision("ok") is False
        assert audit._is_real_decision("sure") is False
        assert audit._is_real_decision("yes, proceed") is False

    def test_filters_choreography(self):
        """Session navigation phrases are not decisions."""
        assert audit._is_real_decision("let's review the code changes") is False
        assert audit._is_real_decision("please review the constitution") is False
        assert audit._is_real_decision("gator init and check status") is False

    def test_filters_short_text(self):
        """Text under 20 chars or 4 words is filtered."""
        assert audit._is_real_decision("fix it") is False
        assert audit._is_real_decision("do the thing") is False

    def test_passes_real_decisions(self):
        """Substantive architectural decisions pass the filter."""
        assert audit._is_real_decision(
            "We decided to use SQLite instead of PostgreSQL for the local cache"
        ) is True
        assert audit._is_real_decision(
            "The session logging schema should include a machine-id field for dedup"
        ) is True

    def test_filters_tool_results(self):
        """Tool result prefixes are filtered."""
        assert audit._is_real_decision("[tool result] something happened here") is False


class TestRenderText:
    def _minimal_data(self):
        """Build a minimal but complete audit data dict."""
        return {
            "schema": "gator-audit-v1",
            "generated_at": "2026-05-30T00:00:00Z",
            "generated_local": "2026-05-30 12:00",
            "version": "test",
            "since_days": 7,
            "machine": {"label": "test-machine", "id": "abc123"},
            "fleet_status": [],
            "drift": [],
            "drift_summary": {},
            "sessions": {},
            "governance": {},
            "decisions": [],
        }

    def test_no_crash_on_empty(self):
        """Empty data produces output without crashing."""
        output = audit.render_text(self._minimal_data())
        assert isinstance(output, str)
        assert "gator audit" in output

    def test_sections_present(self):
        """Populated data includes expected section headers."""
        data = self._minimal_data()
        data["fleet_status"] = [
            {"name": "repo1", "accessible": True, "has_hooks": True,
             "trailers": {"Gator-Agent": "claude"}, "charters": 2,
             "functions": 5, "issues": 0, "last_commit": {"age": "1 hour ago"}},
        ]
        data["drift"] = [{"name": "repo1", "severity": "ok", "findings": []}]
        data["drift_summary"] = {"ok": 1, "warn": 0, "drift": 0}
        data["governance"] = {
            "repos": 1, "charters": 2, "functions": 5,
            "issues": 0, "hooks_installed": 1, "trailers_flowing": 1,
        }
        output = audit.render_text(data)
        assert "FLEET STATUS" in output
        assert "DRIFT" in output
        assert "GOVERNANCE COVERAGE" in output


class TestRenderHtml:
    def test_self_contained(self):
        """HTML output is self-contained: inline CSS, no external deps."""
        data = {
            "schema": "gator-audit-v1",
            "generated_at": "2026-05-30T00:00:00Z",
            "generated_local": "2026-05-30 12:00",
            "version": "test",
            "since_days": 7,
            "machine": {"label": "test-machine", "id": "abc12345"},
            "fleet_status": [],
            "drift": [],
            "drift_summary": {"ok": 0, "warn": 0, "drift": 0, "command_post": {}},
            "sessions": {"by_vendor": {}, "since_days": 7, "recent": 0,
                         "total": 0, "pending_export": 0, "exported": 0},
            "governance": {"repos": 0, "charters": 0, "functions": 0,
                           "issues": 0, "hooks_installed": 0, "trailers_flowing": 0},
            "decisions": [],
        }
        html = audit.render_html(data)
        assert html.startswith("<!DOCTYPE html>")
        assert "<style>" in html
        # No external dependencies
        assert '<script src=' not in html
        assert '<link rel="stylesheet" href=' not in html


# ---------------------------------------------------------------------------
# Renderer seam tests — structural invariant assertions
# ---------------------------------------------------------------------------

def _rich_audit_data():
    """Build a realistic audit data dict for seam tests."""
    return {
        "schema": "gator-audit-v1",
        "generated_at": "2026-06-20T22:00:00Z",
        "generated_local": "2026-06-20 22:00",
        "version": "1.2.0",
        "since_days": 7,
        "machine": {"label": "test-machine", "id": "abc12345"},
        "fleet_status": [
            {"name": "gator-command", "accessible": True, "has_hooks": True,
             "trailers": {"Gator-Agent": "claude"}, "charters": 11,
             "functions": 45, "issues": 0, "last_commit": {"age": "2 hours ago"}},
            {"name": "smart-sort", "accessible": True, "has_hooks": True,
             "trailers": {"Gator-Agent": "codex"}, "charters": 3,
             "functions": 12, "issues": 1, "last_commit": {"age": "1 day ago"}},
            {"name": "offline-repo", "accessible": False},
        ],
        "drift": [
            {"name": "gator-command", "severity": "ok", "findings": []},
            {"name": "smart-sort", "severity": "warn",
             "findings": [{"check": "hooks", "severity": "warn", "message": "hooks outdated"}]},
        ],
        "drift_summary": {"ok": 1, "warn": 1, "drift": 0, "command_post": {}},
        "sessions": {
            "by_vendor": {"claude": 5, "codex": 2},
            "by_repo": {"gator-command": 4, "smart-sort": 3},
            "since_days": 7, "recent": 7, "total": 15,
            "pending_export": 2, "exported": 13,
        },
        "governance": {
            "repos": 3, "charters": 14, "functions": 57,
            "issues": 1, "hooks_installed": 2, "trailers_flowing": 2,
        },
        "decisions": [
            {"timestamp": "2026-06-20T21:00:00Z", "repo": "gator-command",
             "text": "Approved the session summary aggregator implementation plan after 6 review cycles"},
            {"timestamp": "2026-06-19T15:00:00Z", "repo": "smart-sort",
             "text": "Decided to use SQLite for local analytics instead of DuckDB for simplicity"},
        ],
    }


class TestRenderTextInvariants:
    """Structural invariant tests for render_text after extraction."""

    def test_fleet_status_with_repos(self):
        data = _rich_audit_data()
        output = audit.render_text(data)
        assert "FLEET STATUS (3 repos)" in output
        assert "gator-command" in output
        assert "smart-sort" in output
        assert "NOT ACCESSIBLE" in output  # offline-repo

    def test_fleet_hook_and_trailer_indicators(self):
        data = _rich_audit_data()
        output = audit.render_text(data)
        # Repos with hooks show ✓
        assert "hooks: ✓" in output

    def test_governance_coverage_metrics(self):
        data = _rich_audit_data()
        output = audit.render_text(data)
        assert "GOVERNANCE COVERAGE" in output
        assert "14" in output  # charters count
        assert "57" in output  # functions count
        assert "3 repos" in output

    def test_sessions_section(self):
        data = _rich_audit_data()
        output = audit.render_text(data)
        assert "SESSIONS" in output
        assert "7 of 15 total" in output

    def test_decisions_section(self):
        data = _rich_audit_data()
        output = audit.render_text(data)
        assert "RECENT DECISIONS (2)" in output
        assert "aggregator" in output  # from decision text

    def test_drift_section(self):
        data = _rich_audit_data()
        output = audit.render_text(data)
        assert "DRIFT" in output
        assert "1 current" in output
        assert "1 warnings" in output


class TestRenderHtmlInvariants:
    """Structural invariant tests for render_html after extraction."""

    def test_fleet_table_contains_repos(self):
        data = _rich_audit_data()
        html = audit.render_html(data)
        assert "gator-command" in html
        assert "smart-sort" in html
        assert "NOT ACCESSIBLE" in html

    def test_drift_findings_rendered(self):
        data = _rich_audit_data()
        html = audit.render_html(data)
        assert "hooks outdated" in html
        assert "smart-sort" in html

    def test_governance_stats_rendered(self):
        data = _rich_audit_data()
        html = audit.render_html(data)
        # Stat cards
        assert ">14<" in html  # charters stat value
        assert ">57<" in html  # functions stat value

    def test_decisions_rendered(self):
        data = _rich_audit_data()
        html = audit.render_html(data)
        assert "aggregator" in html
        assert "SQLite" in html

    def test_html_structure(self):
        data = _rich_audit_data()
        html = audit.render_html(data)
        assert html.startswith("<!DOCTYPE html>")
        assert "<style>" in html
        assert "Fleet Status" in html
        assert "Drift Findings" in html
        assert "Governance Coverage" in html


# ---------------------------------------------------------------------------
# Assembler → renderer end-to-end seam test
# ---------------------------------------------------------------------------

class TestAssemblerRendererSeam:
    """Verify that assemble_audit_data() output is compatible with both renderers.

    This is the real regression surface introduced by the renderer extraction:
    if assemble_audit_data() changes its output schema, these tests fail even
    if hand-built data tests still pass.
    """

    def test_assembler_output_renders_text(self):
        """assemble_audit_data() output passes through render_text() without error."""
        data = audit.assemble_audit_data(since_days=1)
        output = audit.render_text(data)
        assert isinstance(output, str)
        assert "gator audit" in output
        # Must contain the version and timestamp from the assembler
        assert data["version"] in output
        assert data["generated_local"] in output

    def test_assembler_output_renders_html(self):
        """assemble_audit_data() output passes through render_html() without error."""
        data = audit.assemble_audit_data(since_days=1)
        html = audit.render_html(data)
        assert html.startswith("<!DOCTYPE html>")
        assert "<style>" in html
        # Must contain the version and machine label from the assembler
        assert data["version"] in html
        assert "Gator Audit Dashboard" in html

    def test_assembler_output_has_required_keys(self):
        """assemble_audit_data() returns all keys that renderers depend on."""
        data = audit.assemble_audit_data(since_days=1)
        # Keys used by render_text
        assert "generated_local" in data
        assert "version" in data
        assert "machine" in data
        assert "fleet_status" in data
        assert "drift" in data
        assert "drift_summary" in data
        assert "sessions" in data
        assert "governance" in data
        assert "decisions" in data
        # Keys used by render_html
        assert "generated_at" in data


# ---------------------------------------------------------------------------
# Session summary rendering
# ---------------------------------------------------------------------------

def _make_summary(repo="test-repo", session_id="s1", model="claude-opus-4-6",
                  started_at="2026-06-19T22:00:00Z", ended_at="2026-06-19T23:00:00Z",
                  goal="Fix auth bug", commit_count=2, significance="minor",
                  decision_tags=None, commits=None):
    return {
        "schema": "gator-session-summary-v1",
        "session_id": session_id,
        "repo": repo,
        "repo_key": "abc123",
        "branch": "main",
        "vendor": "anthropic",
        "model": model,
        "agent": model,
        "architect": "AG",
        "started_at": started_at,
        "ended_at": ended_at,
        "goal": goal,
        "commit_count": commit_count,
        "commits": commits or [
            {"commit": "aaa", "short_commit": "aaa", "intent": "Fix auth", "change_type": "fix"},
            {"commit": "bbb", "short_commit": "bbb", "intent": "Add tests", "change_type": "test"},
        ],
        "files_touched": ["auth.py"],
        "decision_tags": decision_tags or ["auth"],
        "intents": ["Fix auth", "Add tests"],
        "significance": significance,
        "change_types": ["fix", "test"],
        "machine_label": "test-machine",
        "transcript_session_id": None,
        "transcript_ref": None,
        "notes": [],
    }


class TestRenderSessionsText:
    def test_empty_sessions(self):
        output = audit._render_sessions_text([])
        assert "No sessions found" in output

    def test_single_session(self):
        output = audit._render_sessions_text([_make_summary()])
        assert "claude-opus-4-6" in output
        assert "2 commits" in output
        assert "Fix auth bug" in output
        assert "aaa fix" in output

    def test_fleet_groups_by_repo(self):
        """Fleet mode groups sessions by repo, not interleaved."""
        summaries = [
            _make_summary(repo="alpha", session_id="s1",
                          started_at="2026-06-20T10:00:00Z"),
            _make_summary(repo="beta", session_id="s2",
                          started_at="2026-06-20T09:00:00Z"),
            _make_summary(repo="alpha", session_id="s3",
                          started_at="2026-06-20T08:00:00Z"),
        ]
        output = audit._render_sessions_text(summaries, fleet=True)
        # Alpha sessions should be contiguous, not interleaved with beta
        alpha_first = output.index("Sessions for alpha")
        beta_first = output.index("Sessions for beta")
        # All alpha content should come before beta
        alpha_lines = [i for i, line in enumerate(output.splitlines())
                       if "alpha" in line.lower() or "s1" in line or "s3" in line]
        beta_lines = [i for i, line in enumerate(output.splitlines())
                      if "Sessions for beta" in line]
        # The beta header should appear after the alpha block
        assert alpha_first < beta_first

    def test_fleet_descending_within_repo(self):
        """Within each repo, sessions are sorted most-recent-first."""
        summaries = [
            _make_summary(repo="alpha", session_id="old",
                          started_at="2026-06-18T10:00:00Z",
                          ended_at="2026-06-18T11:00:00Z",
                          goal="Old work"),
            _make_summary(repo="alpha", session_id="new",
                          started_at="2026-06-20T10:00:00Z",
                          ended_at="2026-06-20T11:00:00Z",
                          goal="New work"),
        ]
        output = audit._render_sessions_text(summaries, fleet=True)
        new_pos = output.index("New work")
        old_pos = output.index("Old work")
        assert new_pos < old_pos

    def test_handle_sessions_json(self, monkeypatch, capsys):
        """--sessions --json routes through _handle_sessions and produces valid JSON."""
        summaries = [_make_summary()]

        # Stub the aggregator import
        class FakeAggregator:
            @staticmethod
            def get_session_summaries(repo_path, force_refresh=False):
                return summaries

        monkeypatch.setattr(audit, "_import_script", lambda name: FakeAggregator())
        monkeypatch.setattr(audit, "find_gator_root", lambda: "/fake/repo")

        # Build a minimal args namespace
        class Args:
            sessions = True
            json = True
            fleet = False
            refresh = False

        audit._handle_sessions(Args())
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert len(parsed) == 1
        assert parsed[0]["schema"] == "gator-session-summary-v1"
        assert parsed[0]["session_id"] == "s1"
