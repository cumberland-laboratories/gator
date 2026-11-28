"""
#104: `.gator/inbox.md` is each person's own notes, never tracked.

Covers the ignore rule, the visible #78-style untracking, the migration
wording, the one-time restore after a teammate's pull deletes the file,
and the conditional `gator init` read.
"""

import json
import subprocess
from pathlib import Path

import pytest

from conftest import load_script

gatorize = load_script("gatorize")
init = load_script("gator-init")

import gator_layout  # noqa: E402  (on sys.path via conftest)

INBOX = ".gator/inbox.md"
LOCAL = ".gator/inbox.local.md"   # #113: never tracked


def _git(cwd, *args, check=True):
    r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                        "-c", "commit.gpgsign=false", *args],
                       cwd=cwd, capture_output=True, text=True, timeout=30)
    if check:
        assert r.returncode == 0, r.stderr
    return r


@pytest.fixture
def tracked_inbox(tmp_path):
    """A repository that committed its inbox (an install before #104)."""
    repo = tmp_path / "origin-clone"
    (repo / ".gator").mkdir(parents=True)
    _git(tmp_path, "init", "-q", str(repo))
    _git(repo, "config", "core.hooksPath", str(tmp_path / "no-hooks"))
    (repo / INBOX).write_text("# Inbox\n\n- shared note\n", encoding="utf-8")
    (repo / ".gator" / "roadmap.md").write_text("# Roadmap\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


class TestIgnoreAndUntrack:

    def test_rule_is_added_and_a_tracked_inbox_is_untracked(self, tracked_inbox):
        untracked = gatorize.ensure_repo_gitignore(tracked_inbox)
        assert untracked == [INBOX]
        assert INBOX in (tracked_inbox / ".gitignore").read_text(encoding="utf-8").splitlines()
        assert _git(tracked_inbox, "ls-files", "--", INBOX).stdout == ""
        # Index only: the file stays on disk with its content.
        assert "shared note" in (tracked_inbox / INBOX).read_text(encoding="utf-8")
        assert _git(tracked_inbox, "check-ignore", INBOX).returncode == 0
        staged = _git(tracked_inbox, "diff", "--cached", "--name-status").stdout
        assert staged.strip() == f"D\t{INBOX}"

    def test_dry_run_prediction_lists_it(self, tracked_inbox):
        assert gatorize.tracked_transient_files(tracked_inbox) == [INBOX]


class TestMigrationWording:

    def test_inbox_alone(self):
        r = gatorize.transient_untrack_result([INBOX])
        assert r["message"].startswith("Gator removed 1 machine-local path from the Git index.")
        assert r["why"] == gatorize.PERSONAL_UNTRACK_WHY
        lines = gatorize.format_transient_untrack(r, predicted=True)
        assert lines[0] == "  Machine-local paths to remove from the Git index (1):"

    def test_inbox_with_hook_files_explains_both(self):
        r = gatorize.transient_untrack_result([".gator/status.json", INBOX])
        assert r["message"].startswith("Gator removed 2 machine-local paths ")
        assert r["why"] == (gatorize.TRANSIENT_UNTRACK_WHY + " "
                            + gatorize.PERSONAL_UNTRACK_WHY)

    def test_hook_files_alone_keep_the_78_wording(self):
        r = gatorize.transient_untrack_result([".gator/status.json"])
        assert r["message"].startswith("Gator removed 1 hook-ephemera path ")
        assert r["why"] == gatorize.TRANSIENT_UNTRACK_WHY


class TestRestoreAfterPull:

    def _migrate_and_clone(self, tracked_inbox, tmp_path):
        """Clone B, then A untracks and commits, then B pulls."""
        b = tmp_path / "teammate"
        _git(tmp_path, "clone", "-q", str(tracked_inbox), str(b))
        _git(b, "config", "core.hooksPath", str(tmp_path / "no-hooks"))
        assert (b / INBOX).exists()
        gatorize.ensure_repo_gitignore(tracked_inbox)
        _git(tracked_inbox, "add", ".gitignore")
        _git(tracked_inbox, "commit", "-q", "-m", "inbox is personal")
        _git(b, "pull", "-q", "--ff-only")
        return b

    def test_pull_deletes_the_copy_and_restore_brings_it_back(self, tracked_inbox, tmp_path):
        b = self._migrate_and_clone(tracked_inbox, tmp_path)
        assert not (b / INBOX).exists()          # what #104 must not leave behind
        sha = gatorize.restore_personal_inbox(b)
        assert sha
        assert "shared note" in (b / LOCAL).read_text(encoding="utf-8")
        assert not (b / INBOX).exists()
        assert _git(b, "status", "--porcelain", "--ignored=no").stdout == ""   # ignored

    def test_restore_happens_once_per_clone(self, tracked_inbox, tmp_path):
        b = self._migrate_and_clone(tracked_inbox, tmp_path)
        assert gatorize.restore_personal_inbox(b)
        (b / LOCAL).unlink()                      # a deliberate deletion later
        assert gatorize.restore_personal_inbox(b) is None
        assert not (b / LOCAL).exists()

    def test_a_check_before_the_migration_does_not_use_up_the_restore(
            self, tracked_inbox, tmp_path):
        b = tmp_path / "early"
        _git(tmp_path, "clone", "-q", str(tracked_inbox), str(b))
        _git(b, "config", "core.hooksPath", str(tmp_path / "no-hooks"))
        assert gatorize.restore_personal_inbox(b) is None    # still tracked here
        gatorize.ensure_repo_gitignore(tracked_inbox)
        _git(tracked_inbox, "add", ".gitignore")
        _git(tracked_inbox, "commit", "-q", "-m", "inbox is personal")
        _git(b, "pull", "-q", "--ff-only")
        assert gatorize.restore_personal_inbox(b)
        assert (b / LOCAL).exists()

    def test_an_existing_inbox_is_never_touched(self, tracked_inbox):
        gatorize.ensure_repo_gitignore(tracked_inbox)
        _git(tracked_inbox, "commit", "-q", "-m", "inbox is personal")
        (tracked_inbox / INBOX).write_text("mine\n", encoding="utf-8")
        assert gatorize.restore_personal_inbox(tracked_inbox) is None
        assert (tracked_inbox / INBOX).read_text(encoding="utf-8") == "mine\n"

    def test_outside_git_does_nothing(self, tmp_path):
        assert gatorize.restore_personal_inbox(tmp_path) is None


class TestSessionOpening:

    def _repo(self, tmp_path, with_inbox):
        gator = tmp_path / ".gator"
        (gator / ".includes" / "scripts").mkdir(parents=True)
        (gator / ".includes" / "constitution.md").write_text("# c\n", encoding="utf-8")
        (gator / "layout-version.json").write_text('{"layout": "v2"}\n', encoding="utf-8")
        if with_inbox:
            (gator / "inbox.local.md").write_text("# Inbox\n", encoding="utf-8")
        return tmp_path

    def test_inbox_is_read_only_where_it_exists(self, tmp_path):
        repo = self._repo(tmp_path, with_inbox=True)
        _, reads = init.session_opening_reads(repo, gator_layout.get_gator_paths(repo))
        assert reads[-1] == ".gator/inbox.local.md"
        text = "\n".join(init.session_opening_directive(repo, gator_layout.get_gator_paths(repo)))
        assert "inbox.local.md — your own notes (not shared)" in text

    def test_no_inbox_no_read(self, tmp_path):
        repo = self._repo(tmp_path, with_inbox=False)
        _, reads = init.session_opening_reads(repo, gator_layout.get_gator_paths(repo))
        assert ".gator/inbox.local.md" not in reads
        text = "\n".join(init.session_opening_directive(repo, gator_layout.get_gator_paths(repo)))
        assert "inbox.md" not in text


class TestRescueFromOlderCheckouts:
    """#113: Git overwrites an ignored file when a checkout brings back a
    commit that tracks its path, and deletes it when moving forward again.
    The personal inbox therefore lives at a path no commit tracks."""

    def _migrated(self, tracked_inbox):
        _git(tracked_inbox, "branch", "old")
        gatorize.ensure_repo_gitignore(tracked_inbox)
        _git(tracked_inbox, "add", ".gitignore")
        _git(tracked_inbox, "commit", "-q", "-m", "inbox is personal")
        return _git(tracked_inbox, "branch", "--show-current").stdout.strip()

    def test_the_reported_sequence_keeps_the_notes(self, tracked_inbox):
        current = self._migrated(tracked_inbox)
        with open(tracked_inbox / INBOX, "a", encoding="utf-8") as f:
            f.write("- personal note after 2.40\n")
        assert gatorize.rescue_personal_inbox(tracked_inbox) == ("moved", LOCAL)
        assert not (tracked_inbox / INBOX).exists()

        _git(tracked_inbox, "checkout", "-q", "old")        # tracks inbox.md
        assert "personal note" not in (tracked_inbox / INBOX).read_text(encoding="utf-8")
        _git(tracked_inbox, "checkout", "-q", current)
        _git(tracked_inbox, "merge", "-q", "--no-edit", "old")
        text = (tracked_inbox / LOCAL).read_text(encoding="utf-8")
        assert "personal note after 2.40" in text and "shared note" in text
        # Nothing for Git to show or commit: both names are ignored.
        assert _git(tracked_inbox, "status", "--porcelain").stdout == ""

    def test_without_the_rescue_git_loses_them(self, tracked_inbox):
        """The bug itself, so the test above means something."""
        current = self._migrated(tracked_inbox)
        with open(tracked_inbox / INBOX, "a", encoding="utf-8") as f:
            f.write("- personal note after 2.40\n")
        _git(tracked_inbox, "checkout", "-q", "old")
        _git(tracked_inbox, "checkout", "-q", current)
        assert not (tracked_inbox / INBOX).exists()

    def test_still_tracked_here_means_shared_content_is_left_alone(self, tracked_inbox):
        assert gatorize.rescue_personal_inbox(tracked_inbox) is None
        assert (tracked_inbox / INBOX).exists() and not (tracked_inbox / LOCAL).exists()

    def test_identical_copies_collapse(self, tracked_inbox):
        self._migrated(tracked_inbox)
        (tracked_inbox / LOCAL).write_bytes((tracked_inbox / INBOX).read_bytes())
        assert gatorize.rescue_personal_inbox(tracked_inbox) == ("identical", LOCAL)
        assert not (tracked_inbox / INBOX).exists()

    def test_different_copies_are_both_kept(self, tracked_inbox):
        self._migrated(tracked_inbox)
        (tracked_inbox / LOCAL).write_text("newer\n", encoding="utf-8")
        first = gatorize.rescue_personal_inbox(tracked_inbox)
        assert first == ("kept-both", ".gator/inbox.local.md.from-inbox-md")
        assert (tracked_inbox / LOCAL).read_text(encoding="utf-8") == "newer\n"
        (tracked_inbox / INBOX).write_text("third\n", encoding="utf-8")
        second = gatorize.rescue_personal_inbox(tracked_inbox)
        assert second == ("kept-both", ".gator/inbox.local.md.from-inbox-md-2")
        assert _git(tracked_inbox, "status", "--porcelain").stdout == ""
        assert "Merge them by hand" in gatorize.format_inbox_rescue(second)

    def test_outside_git_does_nothing(self, tmp_path):
        (tmp_path / ".gator").mkdir()
        (tmp_path / INBOX).write_text("x\n", encoding="utf-8")
        assert gatorize.rescue_personal_inbox(tmp_path) is None
        assert (tmp_path / INBOX).exists()

    def test_a_fresh_install_writes_the_personal_path(self, tmp_path):
        for d in ("charters", "sessions", "vault"):
            (tmp_path / d).mkdir()
        gatorize.write_stubs(tmp_path)
        assert (tmp_path / "inbox.local.md").is_file()
        assert not (tmp_path / "inbox.md").exists()
