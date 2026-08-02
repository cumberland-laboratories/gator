"""
Tests for gator_remote.py — remote fleet scanning via bare clone cache.

Tests the thin-fetch model without hitting real network remotes.
Uses a local bare repo as a stand-in for a remote, verifying that
git show, ls-tree, and log operations produce correct results.
"""

import subprocess
from pathlib import Path

import pytest

import gator_remote


@pytest.fixture
def local_bare_remote(tmp_path):
    """Create a local git repo and its bare clone to simulate remote scanning.

    Structure:
      tmp_path/source/   — a normal repo with .gator/ governance state
      tmp_path/remote.git — bare clone of source (simulates the "remote")

    Returns (source_path, bare_path).
    """
    source = tmp_path / "source"
    source.mkdir()

    # Init a repo with governance content
    subprocess.run(["git", "init", str(source)], capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=source, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=source, capture_output=True,
    )

    # Create .gator/ structure
    gator = source / ".gator"
    (gator / "charters").mkdir(parents=True)
    (gator / "active-threads").mkdir()
    (gator / "scripts" / "hooks").mkdir(parents=True)
    (gator / "sessions").mkdir()

    (gator / ".gator-version").write_text(
        "generation: 2\ninstalled: 2026-05-25\nsource: gator-command\n"
    )
    (gator / "command-post.md").write_text(
        "command-post: ../gator-command\nversion: 2026-05-29\n"
    )
    (gator / "constitution.md").write_text("# Constitution\n\nRules here.\n")
    (gator / "issues.md").write_text(
        "# Issues\n\n### Bug A\n**Status**: Open\n\n"
        "### Bug B\n**Status**: Resolved\n"
    )
    (gator / "mission.md").write_text(
        "# Mission\n\nA test project for governance.\n"
    )
    (gator / "charters" / "core.md").write_text(
        "# Core Module\n\n"
        "### parse_config(path)\nReads config.\n\n"
        "### validate(data)\nValidates input.\n"
    )
    (gator / "charters" / "README.md").write_text("# Charters\n")
    (gator / "charters" / "_template.md").write_text("# Template\n")
    (gator / "active-threads" / "design.md").write_text("# Design\n")
    (gator / "scripts" / "hooks" / "pre-commit").write_text("#!/bin/sh\nexit 0\n")

    # A committed session summary
    (gator / "sessions" / "2026-05-30-commit-140000.md").write_text(
        "---\nrepo: test-project\nvendor: claude\n---\n\n"
        "## Decisions\n\n"
        "- Chose OAEP padding [#architecture] [#security] -pi\n"
        "- Deferred key rotation [#scope] -pi\n"
    )

    # Commit everything
    subprocess.run(["git", "add", "-A"], cwd=source, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial governance setup\n\n"
         "Gator-Charters: 1\nGator-Functions: 2\n"
         "Gator-Significance: high\nGator-Change-Type: feature\n"
         "Gator-Agent: claude\nGator-PI: AG"],
        cwd=source, capture_output=True,
    )

    # Create bare clone
    bare = tmp_path / "remote.git"
    subprocess.run(
        ["git", "clone", "--bare", str(source), str(bare)],
        capture_output=True,
    )

    return source, bare


class TestResolveRef:
    def test_finds_main(self, local_bare_remote):
        _, bare = local_bare_remote
        ref = gator_remote._resolve_ref(bare)
        # Git init creates 'master' by default on most systems
        assert ref in ("main", "master")

    def test_falls_back_to_head(self, tmp_path):
        """Returns HEAD when no recognized branch exists."""
        bare = tmp_path / "empty.git"
        subprocess.run(["git", "init", "--bare", str(bare)], capture_output=True)
        ref = gator_remote._resolve_ref(bare)
        assert ref == "HEAD"


class TestGitShow:
    def test_reads_file(self, local_bare_remote):
        _, bare = local_bare_remote
        ref = gator_remote._resolve_ref(bare)
        content = gator_remote.git_show(bare, ref, ".gator/constitution.md")
        assert content is not None
        assert "# Constitution" in content

    def test_returns_none_for_missing(self, local_bare_remote):
        _, bare = local_bare_remote
        ref = gator_remote._resolve_ref(bare)
        content = gator_remote.git_show(bare, ref, "nonexistent.md")
        assert content is None


class TestGitLsTree:
    def test_lists_charters(self, local_bare_remote):
        _, bare = local_bare_remote
        ref = gator_remote._resolve_ref(bare)
        entries = gator_remote.git_ls_tree(bare, ref, ".gator/charters")
        assert "core.md" in entries
        assert "README.md" in entries
        assert "_template.md" in entries

    def test_lists_sessions(self, local_bare_remote):
        _, bare = local_bare_remote
        ref = gator_remote._resolve_ref(bare)
        entries = gator_remote.git_ls_tree(bare, ref, ".gator/sessions")
        assert "2026-05-30-commit-140000.md" in entries

    def test_returns_empty_for_missing_dir(self, local_bare_remote):
        _, bare = local_bare_remote
        ref = gator_remote._resolve_ref(bare)
        entries = gator_remote.git_ls_tree(bare, ref, "nonexistent/path")
        assert entries == []


class TestGitLogTrailers:
    def test_extracts_gator_trailers(self, local_bare_remote):
        _, bare = local_bare_remote
        ref = gator_remote._resolve_ref(bare)
        trailers = gator_remote.git_log_trailers(bare, ref)
        assert trailers.get("Gator-Significance") == "high"
        assert trailers.get("Gator-Change-Type") == "feature"
        assert trailers.get("Gator-Agent") == "claude"

    def test_returns_empty_on_no_trailers(self, tmp_path):
        """Repo with no Gator trailers returns empty dict."""
        source = tmp_path / "notrailers"
        source.mkdir()
        subprocess.run(["git", "init", str(source)], capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=source, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"],
            cwd=source, capture_output=True,
        )
        (source / "file.txt").write_text("hello")
        subprocess.run(["git", "add", "."], cwd=source, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "plain commit"],
            cwd=source, capture_output=True,
        )
        bare = tmp_path / "notrailers.git"
        subprocess.run(
            ["git", "clone", "--bare", str(source), str(bare)],
            capture_output=True,
        )
        ref = gator_remote._resolve_ref(bare)
        trailers = gator_remote.git_log_trailers(bare, ref)
        assert trailers == {}


class TestGitLogLastCommit:
    def test_returns_commit_info(self, local_bare_remote):
        _, bare = local_bare_remote
        ref = gator_remote._resolve_ref(bare)
        commit = gator_remote.git_log_last_commit(bare, ref)
        assert commit is not None
        assert "Initial governance setup" in commit["message"]
        assert len(commit["hash"]) >= 7
        assert commit["date"]  # non-empty


class TestGitCommitCount:
    def test_counts_recent_commits(self, local_bare_remote):
        _, bare = local_bare_remote
        ref = gator_remote._resolve_ref(bare)
        count = gator_remote.git_commit_count(bare, ref, days=30)
        assert count >= 1


class TestReadGatorStateRemote:
    def test_full_state(self, local_bare_remote):
        _, bare = local_bare_remote
        ref = gator_remote._resolve_ref(bare)
        state = gator_remote.read_gator_state_remote(bare, ref)

        assert state["gatorized"] is True
        assert state["generation"] == 2
        assert state["policy_version"] == "2026-05-29"
        assert state["charters"] == 1  # core.md (README/template excluded)
        assert state["functions"] == 2  # parse_config, validate
        assert state["threads"] >= 1   # design.md in active-threads
        assert state["issues"] == 1    # Bug A is Open
        assert state["hooks_sources"] is True
        assert state["mission_summary"] == "A test project for governance."
        assert state["scan_mode"] == "remote"

    def test_not_gatorized(self, tmp_path):
        """Repo without .gator/ reports gatorized=False."""
        source = tmp_path / "plain"
        source.mkdir()
        subprocess.run(["git", "init", str(source)], capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=source, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"],
            cwd=source, capture_output=True,
        )
        (source / "README.md").write_text("# Hello\n")
        subprocess.run(["git", "add", "."], cwd=source, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=source, capture_output=True,
        )
        bare = tmp_path / "plain.git"
        subprocess.run(
            ["git", "clone", "--bare", str(source), str(bare)],
            capture_output=True,
        )
        ref = gator_remote._resolve_ref(bare)
        state = gator_remote.read_gator_state_remote(bare, ref)
        assert state["gatorized"] is False
        assert state["generation"] == 0
        assert state["charters"] == 0


class TestScanRepoRemote:
    def test_scan_with_bare_cache(self, local_bare_remote, monkeypatch):
        """scan_repo_remote uses ensure_cache and produces a full report."""
        _, bare = local_bare_remote

        # Monkeypatch ensure_cache to return our local bare clone
        monkeypatch.setattr(
            gator_remote, "ensure_cache",
            lambda name, url: bare,
        )

        entry = {
            "name": "test-project",
            "path": "/nonexistent",
            "remote": "https://example.com/test-project.git",
            "registered": "2026-05-25",
            "status": "active",
        }
        report = gator_remote.scan_repo_remote(entry)

        assert report["accessible"] is True
        assert report["scan_mode"] == "remote"
        assert report["gatorized"] is True
        assert report["generation"] == 2
        assert report["charters"] == 1
        assert report["functions"] == 2
        assert report["last_commit"] is not None
        assert "Initial governance setup" in report["last_commit"]["message"]
        assert report["trailers"].get("Gator-Significance") == "high"

    def test_scan_no_remote_url(self):
        """Reports error when no remote URL available."""
        entry = {
            "name": "no-remote",
            "path": "/nonexistent",
            "remote": "—",
        }
        report = gator_remote.scan_repo_remote(entry)
        assert report["accessible"] is False
        assert "no remote URL" in report.get("error", "")

    def test_scan_fetch_failure(self, monkeypatch):
        """Reports error when fetch fails."""
        monkeypatch.setattr(
            gator_remote, "ensure_cache",
            lambda name, url: None,
        )
        entry = {
            "name": "broken",
            "path": "/nonexistent",
            "remote": "https://example.com/broken.git",
        }
        report = gator_remote.scan_repo_remote(entry)
        assert report["accessible"] is False
        assert "failed to fetch" in report.get("error", "")


class TestCommittedSessionsRemote:
    def test_list_sessions(self, local_bare_remote):
        _, bare = local_bare_remote
        ref = gator_remote._resolve_ref(bare)
        sessions = gator_remote.list_committed_sessions_remote(bare, ref)
        assert "2026-05-30-commit-140000.md" in sessions

    def test_read_session_summary(self, local_bare_remote):
        _, bare = local_bare_remote
        ref = gator_remote._resolve_ref(bare)
        content = gator_remote.read_session_summary_remote(
            bare, "2026-05-30-commit-140000.md", ref
        )
        assert content is not None
        assert "OAEP padding" in content
        assert "[#architecture]" in content


class TestEnsureCache:
    def test_clones_local_path_as_remote(self, local_bare_remote, tmp_path, monkeypatch):
        """ensure_cache can clone from a local path (used as fake remote)."""
        source, _ = local_bare_remote
        # Point CACHE_DIR to a temp location
        cache_dir = tmp_path / "cache"
        monkeypatch.setattr(gator_remote, "CACHE_DIR", cache_dir)

        remote_url = str(source)
        result = gator_remote.ensure_cache("test-clone", remote_url)
        assert result is not None
        assert result.is_dir()
        # Cache key includes URL hash for collision safety
        expected_name = gator_remote._cache_key("test-clone", remote_url)
        assert result.name == expected_name

        # Second call should fetch (update), not clone
        result2 = gator_remote.ensure_cache("test-clone", remote_url)
        assert result2 == result

    def test_different_urls_same_name_get_separate_keys(self, tmp_path, monkeypatch):
        """Two different remotes with the same repo name produce different cache keys."""
        cache_dir = tmp_path / "cache"
        monkeypatch.setattr(gator_remote, "CACHE_DIR", cache_dir)

        key_a = gator_remote._cache_key("api", "https://github.com/org-a/api.git")
        key_b = gator_remote._cache_key("api", "https://github.com/org-b/api.git")

        # Same name, different URLs → different keys
        assert key_a != key_b
        assert key_a.startswith("api-")
        assert key_b.startswith("api-")
        assert key_a.endswith(".git")
        assert key_b.endswith(".git")

    def test_returns_none_on_bad_url(self, tmp_path, monkeypatch):
        """Returns None when remote URL is unreachable."""
        cache_dir = tmp_path / "cache"
        monkeypatch.setattr(gator_remote, "CACHE_DIR", cache_dir)

        result = gator_remote.ensure_cache("bad", "https://nonexistent.invalid/repo.git")
        assert result is None


class TestGetCacheStatus:
    def test_reports_cached_repos(self, local_bare_remote, tmp_path, monkeypatch):
        """get_cache_status reports on cached bare repos."""
        source, _ = local_bare_remote
        cache_dir = tmp_path / "cache"
        monkeypatch.setattr(gator_remote, "CACHE_DIR", cache_dir)

        # Create a cached clone
        gator_remote.ensure_cache("status-test", str(source))

        status = gator_remote.get_cache_status()
        assert len(status) == 1
        assert status[0]["name"] == "status-test"
        assert "status-test-" in status[0]["cache_path"]

    def test_empty_cache(self, tmp_path, monkeypatch):
        """Returns empty list when no cache exists."""
        monkeypatch.setattr(gator_remote, "CACHE_DIR", tmp_path / "empty")
        status = gator_remote.get_cache_status()
        assert status == []
