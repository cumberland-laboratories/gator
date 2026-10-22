"""
#41 Module 2 — Git snapshot helper (`loop/gitsnap.py`).

Real throwaway repos for every promised environment: clean, staged,
unstaged/untracked, renames, unborn, conflict (unmerged index), linked
worktree, bad base, detached HEAD, bare, not-a-repo, Git missing, and the
index-lock busy retry. Python 3.9-compatible fixtures.

#85: the opt-in ``approval_history`` first-parent-successor fact.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "src" / "gator_command" / "scripts"
LOOP_DIR = SCRIPTS_DIR / "loop"
for p in [str(SCRIPTS_DIR), str(LOOP_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import gitsnap  # noqa: E402


def git(cwd, *args, check=True):
    return subprocess.run(["git", *args], cwd=str(cwd), check=check,
                          capture_output=True, text=True)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


@pytest.fixture
def ceiling(tmp_path, monkeypatch):
    # Never let discovery escape into an enclosing repository.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    return tmp_path


@pytest.fixture
def repo(ceiling):
    r = ceiling / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    git(r, "config", "user.email", "t@example.com")
    git(r, "config", "user.name", "T")
    git(r, "config", "core.autocrlf", "false")
    write(r / "a.txt", "one\n")
    write(r / "b.txt", "bee\n")
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "base")
    return r


def head(r):
    return git(r, "rev-parse", "HEAD").stdout.strip()


class TestHappyPath:
    def test_clean_repo(self, repo):
        s = gitsnap.snapshot(repo)
        assert s["ok"] is True and s["schema"] == gitsnap.SNAPSHOT_SCHEMA
        assert Path(s["worktree_root"]).resolve() == repo.resolve()
        assert s["current_head"] == head(repo)
        assert s["staged_tree"] == s["head_tree"]
        assert s["changed_paths"] == [] and s["unstaged_paths"] == []
        assert s["detached"] is False and s["branch"] == "refs/heads/main"
        assert s["base_head"] is None and s["base_tree"] is None

    def test_staged_changes_against_base(self, repo):
        base = head(repo)
        write(repo / "a.txt", "two\n")
        write(repo / "new.txt", "n\n")
        git(repo, "rm", "-q", "b.txt")
        git(repo, "add", "-A")
        s = gitsnap.snapshot(repo, base)
        assert s["ok"] and s["base_head"] == base
        assert s["base_tree"] == git(repo, "rev-parse",
                                     base + "^{tree}").stdout.strip()
        assert s["staged_tree"] != s["base_tree"]
        assert s["staged_tree"] == git(repo, "write-tree").stdout.strip()
        got = {(c["status"], c["path"]) for c in s["changed_paths"]}
        assert got == {("M", "a.txt"), ("A", "new.txt"), ("D", "b.txt")}

    def test_base_after_branch_moves(self, repo):
        base = head(repo)
        write(repo / "a.txt", "committed\n")
        git(repo, "commit", "-q", "-am", "move")
        write(repo / "b.txt", "staged\n")
        git(repo, "add", "b.txt")
        s = gitsnap.snapshot(repo, base)
        assert s["current_head"] != base
        paths = {c["path"] for c in s["changed_paths"]}
        assert paths == {"a.txt", "b.txt"}  # diff is against the base

    def test_rename_detected(self, repo):
        base = head(repo)
        git(repo, "mv", "a.txt", "renamed.txt")
        s = gitsnap.snapshot(repo, base)
        assert s["changed_paths"] == [{"status": "R", "old_path": "a.txt",
                                       "path": "renamed.txt"}]

    def test_unstaged_and_untracked_disclosed_not_staged(self, repo):
        write(repo / "a.txt", "dirty\n")          # unstaged tracked
        write(repo / "scratch.log", "u\n")        # untracked
        write(repo / ".gitignore", "*.tmp\n")
        write(repo / "ignored.tmp", "x\n")         # ignored: not residue
        s = gitsnap.snapshot(repo, head(repo))
        assert s["ok"]
        assert s["staged_tree"] == s["head_tree"]  # nothing staged
        assert s["unstaged_paths"] == [".gitignore", "a.txt", "scratch.log"]

    def test_subdirectory_resolves_worktree_root(self, repo):
        (repo / "sub").mkdir()
        s = gitsnap.snapshot(repo / "sub")
        assert Path(s["worktree_root"]).resolve() == repo.resolve()

    def test_detached_head(self, repo):
        git(repo, "checkout", "-q", "--detach")
        s = gitsnap.snapshot(repo)
        assert s["ok"] and s["detached"] is True and s["branch"] is None

    def test_linked_worktree_uses_its_own_index(self, repo, ceiling):
        wt = ceiling / "wt"
        git(repo, "worktree", "add", "-q", str(wt), "-b", "feature")
        write(wt / "a.txt", "in worktree\n")
        git(wt, "add", "a.txt")
        s_wt = gitsnap.snapshot(wt, head(repo))
        s_main = gitsnap.snapshot(repo, head(repo))
        assert Path(s_wt["worktree_root"]).resolve() == wt.resolve()
        assert s_wt["branch"] == "refs/heads/feature"
        assert s_wt["staged_tree"] != s_main["staged_tree"]
        assert [c["path"] for c in s_wt["changed_paths"]] == ["a.txt"]
        assert s_main["changed_paths"] == []

    def test_path_lists_are_capped_and_counted(self, repo, monkeypatch):
        monkeypatch.setattr(gitsnap, "MAX_PATHS", 2)
        for i in range(5):
            write(repo / f"u{i}.txt", "x\n")
        s = gitsnap.snapshot(repo)
        assert len(s["unstaged_paths"]) == 2
        assert s["unstaged_truncated"] == 3


class TestFailures:
    def test_unborn(self, ceiling):
        r = ceiling / "unborn"
        r.mkdir()
        git(r, "init", "-q")
        s = gitsnap.snapshot(r)
        assert s == {"schema": gitsnap.SNAPSHOT_SCHEMA, "ok": False,
                     "error": "unborn", "detail": "HEAD has no commit yet"}

    def test_conflict(self, repo):
        git(repo, "checkout", "-q", "-b", "other")
        write(repo / "a.txt", "other side\n")
        git(repo, "commit", "-q", "-am", "other")
        git(repo, "checkout", "-q", "main")
        write(repo / "a.txt", "main side\n")
        git(repo, "commit", "-q", "-am", "main")
        git(repo, "merge", "-q", "other", check=False)
        s = gitsnap.snapshot(repo)
        assert s["ok"] is False and s["error"] == "conflict"

    def test_bad_base(self, repo):
        s = gitsnap.snapshot(repo, "0" * 40)
        assert s["ok"] is False and s["error"] == "bad_base"

    def test_bare(self, ceiling):
        b = ceiling / "bare.git"
        git(ceiling, "init", "-q", "--bare", str(b))
        s = gitsnap.snapshot(b)
        assert s["ok"] is False and s["error"] == "bare"

    def test_not_a_repo(self, ceiling):
        plain = ceiling / "plain"
        plain.mkdir()
        s = gitsnap.snapshot(plain)
        assert s["ok"] is False and s["error"] == "not_a_repo"

    def test_missing_path(self, ceiling):
        s = gitsnap.snapshot(ceiling / "nope")
        assert s["ok"] is False and s["error"] == "not_a_repo"

    def test_existing_file_input_is_not_a_repo(self, repo, monkeypatch):
        """Whiteboard P2: a real file path is an input error, never
        ``git_unavailable``, and is rejected before any Git invocation."""
        calls = []
        real = gitsnap._run

        def spy(args, cwd):
            calls.append(args)
            return real(args, cwd)
        monkeypatch.setattr(gitsnap, "_run", spy)
        s = gitsnap.snapshot(repo / "a.txt")
        assert s["ok"] is False and s["error"] == "not_a_repo"
        assert "not a directory" in s["detail"]
        assert calls == []

    def test_cwd_vanishing_is_not_git_unavailable(self, repo, monkeypatch):
        """A launch failure caused by a bad cwd is classified by the cwd,
        not blamed on Git."""
        gone = repo / "gone"

        def bad_cwd(args, cwd):
            raise NotADirectoryError(f"[WinError 267] {cwd}")
        monkeypatch.setattr(gitsnap, "_run", bad_cwd)
        with pytest.raises(gitsnap._GitError) as ei:
            gitsnap._git(["status"], gone)
        assert ei.value.code == "not_a_repo"

    def test_other_oserror_is_git_error(self, repo, monkeypatch):
        def weird(args, cwd):
            raise OSError("something else")
        monkeypatch.setattr(gitsnap, "_run", weird)
        s = gitsnap.snapshot(repo)
        assert s["ok"] is False and s["error"] == "git_error"

    def test_git_unavailable(self, repo, monkeypatch):
        def missing(args, cwd):
            raise FileNotFoundError("git")
        monkeypatch.setattr(gitsnap, "_run", missing)
        s = gitsnap.snapshot(repo)
        assert s["ok"] is False and s["error"] == "git_unavailable"

    def test_index_lock_retries_once_then_busy(self, repo, monkeypatch):
        monkeypatch.setattr(gitsnap, "_BUSY_RETRY_DELAY", 0)
        real = gitsnap._run
        calls = {"n": 0}

        def locked(args, cwd):
            if args[:1] == ["write-tree"]:
                calls["n"] += 1
                return subprocess.CompletedProcess(
                    args, 128, b"", b"fatal: Unable to create 'index.lock'")
            return real(args, cwd)
        monkeypatch.setattr(gitsnap, "_run", locked)
        s = gitsnap.snapshot(repo)
        assert s["ok"] is False and s["error"] == "git_busy"
        assert calls["n"] == 2

    def test_index_lock_transient_recovers(self, repo, monkeypatch):
        monkeypatch.setattr(gitsnap, "_BUSY_RETRY_DELAY", 0)
        real = gitsnap._run
        calls = {"n": 0}

        def flaky(args, cwd):
            if args[:1] == ["write-tree"]:
                calls["n"] += 1
                if calls["n"] == 1:
                    return subprocess.CompletedProcess(
                        args, 128, b"", b"fatal: Unable to create 'index.lock'")
            return real(args, cwd)
        monkeypatch.setattr(gitsnap, "_run", flaky)
        assert gitsnap.snapshot(repo)["ok"] is True

    @pytest.mark.parametrize("stderr", [
        b"fatal: Unable to create '/r/.git/index.lock': Permission denied",
        b"fatal: Unable to create 'C:/r/.git/index.lock': Access is denied.",
        b"error: insufficient permission for adding an object to "
        b"repository database .git/objects",
        b"FATAL: UNABLE TO CREATE '.GIT/INDEX.LOCK': PERMISSION DENIED",
    ])
    def test_permission_denied_classified_without_retry(
            self, repo, monkeypatch, stderr):
        """#67: a host denial is git_permission_denied after exactly one
        invocation, with no sleep, even when it names index.lock."""
        def no_sleep(_):
            raise AssertionError("permission denial must not sleep")
        monkeypatch.setattr(gitsnap.time, "sleep", no_sleep)
        real = gitsnap._run
        calls = {"n": 0}

        def denied(args, cwd):
            if args[:1] == ["write-tree"]:
                calls["n"] += 1
                return subprocess.CompletedProcess(args, 128, b"", stderr)
            return real(args, cwd)
        monkeypatch.setattr(gitsnap, "_run", denied)
        s = gitsnap.snapshot(repo)
        assert s["ok"] is False and s["error"] == "git_permission_denied"
        assert s["detail"] == stderr.decode().strip()
        assert calls["n"] == 1

    def test_permission_on_retry_is_permission(self, repo, monkeypatch):
        """A lock-only first failure followed by a permission denial is
        git_permission_denied, never git_busy."""
        monkeypatch.setattr(gitsnap, "_BUSY_RETRY_DELAY", 0)
        real = gitsnap._run
        calls = {"n": 0}

        def lock_then_denied(args, cwd):
            if args[:1] == ["write-tree"]:
                calls["n"] += 1
                msg = (b"fatal: Unable to create 'index.lock': File exists."
                       if calls["n"] == 1 else
                       b"fatal: Unable to create 'index.lock': "
                       b"Permission denied")
                return subprocess.CompletedProcess(args, 128, b"", msg)
            return real(args, cwd)
        monkeypatch.setattr(gitsnap, "_run", lock_then_denied)
        s = gitsnap.snapshot(repo)
        assert s["ok"] is False and s["error"] == "git_permission_denied"
        assert calls["n"] == 2

    def test_permission_text_on_read_only_call_is_unchanged(
            self, repo, monkeypatch):
        """The check runs only on retry_busy (index-touching) calls."""
        def denied(args, cwd):
            return subprocess.CompletedProcess(
                args, 128, b"", b"fatal: Permission denied")
        monkeypatch.setattr(gitsnap, "_run", denied)
        s = gitsnap.snapshot(repo)
        assert s["ok"] is False and s["error"] == "not_a_repo"

    def test_launch_permission_error_stays_unavailable(self, repo,
                                                      monkeypatch):
        def refused(args, cwd):
            raise PermissionError("[WinError 5] Access is denied")
        monkeypatch.setattr(gitsnap, "_run", refused)
        s = gitsnap.snapshot(repo)
        assert s["ok"] is False and s["error"] == "git_unavailable"

    def test_failure_text_and_guidance(self):
        assert "git_permission_denied" in gitsnap.ERROR_CODES
        assert gitsnap.error_guidance("git_permission_denied") == \
            gitsnap.PERMISSION_GUIDANCE
        assert "execution-permission condition" in gitsnap.PERMISSION_GUIDANCE
        assert "Codex" not in gitsnap.PERMISSION_GUIDANCE
        for code in sorted(gitsnap.ERROR_CODES - {"git_permission_denied"}):
            assert gitsnap.error_guidance(code) is None
            snap = {"ok": False, "error": code, "detail": "d"}
            assert gitsnap.failure_text(snap) == f"{code} (d)"
        snap = {"ok": False, "error": "git_permission_denied",
                "detail": "Permission denied"}
        assert gitsnap.failure_text(snap) == (
            "git_permission_denied (Permission denied) -- "
            + gitsnap.PERMISSION_GUIDANCE)
        assert gitsnap.failure_text({"ok": False, "error": "git_busy"}) == \
            "git_busy ()"

    def test_never_mutates_refs_index_or_worktree(self, repo):
        write(repo / "a.txt", "staged\n")
        git(repo, "add", "a.txt")
        write(repo / "a.txt", "unstaged on top\n")
        before = (head(repo), git(repo, "ls-files", "--stage").stdout,
                  (repo / "a.txt").read_bytes(),
                  git(repo, "status", "--porcelain").stdout)
        gitsnap.snapshot(repo, head(repo))
        gitsnap.snapshot(repo, head(repo), approved_head=head(repo))
        after = (head(repo), git(repo, "ls-files", "--stage").stdout,
                 (repo / "a.txt").read_bytes(),
                 git(repo, "status", "--porcelain").stdout)
        assert before == after


def commit(r, name, text, msg=None):
    write(r / name, text)
    git(r, "add", name)
    git(r, "commit", "-q", "-m", msg or name)
    return head(r)


def history(r, approved):
    s = gitsnap.snapshot(r, approved_head=approved)
    assert s["ok"] is True
    return s["approval_history"]


class TestApprovalHistory:
    """#85: the immediate first-parent successor of the approved HEAD."""

    def test_absent_unless_requested(self, repo):
        assert "approval_history" not in gitsnap.snapshot(repo, head(repo))

    def test_same_head(self, repo):
        assert history(repo, head(repo)) == {"ok": True, "status": "same_head"}

    @pytest.mark.parametrize("later", [0, 2])
    def test_successor_is_first_commit_after_approval(self, repo, later):
        approved = head(repo)
        first = commit(repo, "a.txt", "approved\n")
        tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
        for i in range(later):
            commit(repo, f"later{i}.txt", "x\n")
        h = history(repo, approved)
        assert h == {"ok": True, "status": "successor", "commit": first,
                     "tree": tree}

    def test_not_ancestor_after_branch_switch(self, repo):
        git(repo, "checkout", "-q", "-b", "side")
        approved = commit(repo, "a.txt", "on side\n")
        git(repo, "checkout", "-q", "main")
        commit(repo, "b.txt", "on main\n")
        assert history(repo, approved) == {"ok": True, "status": "diverged",
                                           "why": "not_ancestor"}

    @pytest.mark.parametrize("approved", ["0" * 40, "-x", "ABC", 12345])
    def test_head_missing(self, repo, monkeypatch, approved):
        calls = []
        real = gitsnap._run

        def spy(args, cwd):
            calls.append(list(args))
            return real(args, cwd)
        monkeypatch.setattr(gitsnap, "_run", spy)
        s = gitsnap.snapshot(repo, approved_head=approved)
        assert s["approval_history"] == {"ok": True, "status": "diverged",
                                         "why": "head_missing"}
        # A malformed value never reaches Git.
        if approved != "0" * 40:
            assert not any(str(approved) in " ".join(a) for a in calls)

    def test_not_first_parent(self, repo):
        git(repo, "checkout", "-q", "-b", "side")
        approved = commit(repo, "side.txt", "s\n")
        git(repo, "checkout", "-q", "main")
        commit(repo, "b.txt", "main\n")
        git(repo, "merge", "-q", "--no-ff", "-m", "merge side", "side")
        assert history(repo, approved) == {"ok": True, "status": "diverged",
                                           "why": "not_first_parent"}

    @pytest.mark.parametrize("probe", ["rev-parse", "rev-list"])
    def test_fatal_probe_is_failure_not_divergence(self, repo, monkeypatch,
                                                    probe):
        approved = head(repo)
        commit(repo, "a.txt", "approved\n")
        real = gitsnap._run

        def fatal(args, cwd):
            hit = (args[:1] == ["rev-list"] if probe == "rev-list"
                   else args[:3] == ["rev-parse", "--verify", "-q"]
                   and args[3].startswith(approved))
            if hit:
                return subprocess.CompletedProcess(
                    args, 128 if probe == "rev-list" else 1, b"",
                    b"fatal: bad object")
            return real(args, cwd)
        monkeypatch.setattr(gitsnap, "_run", fatal)
        s = gitsnap.snapshot(repo, approved_head=approved)
        assert s["ok"] is True and s["staged_tree"]
        h = s["approval_history"]
        assert h["ok"] is False and h["error"] == "git_error"
        assert "status" not in h


def test_parse_name_status_rejects_malformed():
    with pytest.raises(gitsnap._GitError):
        gitsnap._parse_name_status_z(b"R100\0only-old\0")
    with pytest.raises(gitsnap._GitError):
        gitsnap._parse_name_status_z(b"M\0")
