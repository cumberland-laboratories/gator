"""
Tests for gator-hook.py — the machine-side hook dispatcher
(runtime-split Phase 3). plan_dispatch is pure; every decision-mode ×
runtime-availability combination is pinned here.
"""

from pathlib import Path

import pytest

from conftest import load_script

hook = load_script("gator-hook")


def _decision(mode, reason="why"):
    return {"mode": mode, "pin_version": "9.9.9",
            "cli_version": "2.9.0", "reason": reason}


@pytest.fixture
def repo(tmp_path):
    """Repo with a v2 repo-resident runtime."""
    scripts = tmp_path / ".gator" / ".includes" / "scripts"
    scripts.mkdir(parents=True)
    for name in ("gator-pre-commit.py", "gator-session-open.py",
                 "gator-session-start.py"):
        (scripts / name).write_text("# repo copy\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def bare_repo(tmp_path):
    """Repo with .gator/ but NO runtime scripts (post-Phase-4 shape)."""
    (tmp_path / ".gator").mkdir()
    return tmp_path


@pytest.fixture
def wheel(tmp_path_factory):
    """Fake wheel runtime dir."""
    d = tmp_path_factory.mktemp("wheel-runtime")
    for name in ("gator-pre-commit.py", "gator-session-open.py",
                 "gator-session-start.py"):
        (d / name).write_text("# wheel copy\n", encoding="utf-8")
    return d


class TestPlanDispatch:
    def test_current_runs_wheel(self, repo, wheel):
        p = hook.plan_dispatch("pre-commit", repo, _decision("current"), wheel)
        assert p["action"] == "run"
        assert p["script"] == wheel / "gator-pre-commit.py"
        assert p["advisory"] is None

    def test_cli_newer_runs_wheel_with_advisory(self, repo, wheel):
        p = hook.plan_dispatch("pre-commit", repo,
                               _decision("cli-newer", "run gator update"), wheel)
        assert p["action"] == "run"
        assert p["script"] == wheel / "gator-pre-commit.py"
        assert "gator update" in p["advisory"]

    def test_wheel_missing_script_falls_back_to_repo(self, repo, tmp_path_factory):
        empty_wheel = tmp_path_factory.mktemp("empty-wheel")
        p = hook.plan_dispatch("pre-commit", repo, _decision("current"), empty_wheel)
        assert p["action"] == "run"
        assert ".includes" in str(p["script"])
        assert "reinstall" in p["advisory"].lower()

    def test_wheel_and_repo_both_missing_blocks_pre_commit(
            self, bare_repo, tmp_path_factory):
        empty_wheel = tmp_path_factory.mktemp("empty-wheel2")
        p = hook.plan_dispatch("pre-commit", bare_repo,
                               _decision("current"), empty_wheel)
        assert p["action"] == "block"
        assert p["exit_code"] == 1

    def test_repo_scripts_mode_runs_repo_copy(self, repo, wheel):
        p = hook.plan_dispatch("pre-commit", repo, _decision("repo-scripts"), wheel)
        assert p["action"] == "run"
        assert ".includes" in str(p["script"])
        assert p["advisory"] is None

    def test_pin_unreadable_runs_repo_copy_with_advisory(self, repo, wheel):
        p = hook.plan_dispatch("pre-commit", repo,
                               _decision("pin-unreadable", "repair the pin"), wheel)
        assert p["action"] == "run"
        assert "repair the pin" in p["advisory"]

    def test_refuse_with_repo_copy_runs_pinned_runtime(self, repo, wheel):
        """While the repo copy exists it IS the pinned runtime — refusal
        runs it with an upgrade advisory instead of blocking."""
        p = hook.plan_dispatch("pre-commit", repo,
                               _decision("refuse", "upgrade needed"), wheel)
        assert p["action"] == "run"
        assert ".includes" in str(p["script"])
        assert "pinned runtime" in p["advisory"]

    def test_refuse_without_repo_copy_blocks_pre_commit(self, bare_repo, wheel):
        p = hook.plan_dispatch("pre-commit", bare_repo,
                               _decision("refuse", "upgrade needed"), wheel)
        assert p["action"] == "block"
        assert p["exit_code"] == 1
        assert "RUNTIME VERSION MISMATCH" in p["advisory"]

    def test_refuse_without_repo_copy_skips_non_blocking_hooks(
            self, bare_repo, wheel):
        """commit-msg/post-commit/session hooks must never strand a
        mid-flight commit or session open — warn and proceed."""
        for h in ("commit-msg", "post-commit", "session-open", "session-start"):
            p = hook.plan_dispatch(h, bare_repo,
                                   _decision("refuse", "upgrade"), wheel)
            assert p["action"] == "skip", h
            assert p["exit_code"] == 0, h

    def test_ungoverned_skips_with_warning(self, tmp_path, wheel):
        p = hook.plan_dispatch("pre-commit", tmp_path,
                               _decision("ungoverned"), wheel)
        assert p["action"] == "skip"
        assert p["exit_code"] == 0
        assert "warning mode" in p["advisory"]

    def test_repo_scripts_mode_without_scripts_skips(self, bare_repo, wheel):
        p = hook.plan_dispatch("pre-commit", bare_repo,
                               _decision("repo-scripts"), wheel)
        assert p["action"] == "skip"
        assert p["exit_code"] == 0

    def test_v1_layout_repo_copy_found(self, tmp_path, wheel):
        scripts = tmp_path / ".gator" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "gator-pre-commit.py").write_text("# v1\n", encoding="utf-8")
        p = hook.plan_dispatch("pre-commit", tmp_path,
                               _decision("repo-scripts"), wheel)
        assert p["action"] == "run"
        assert str(p["script"]).replace("\\", "/").endswith(
            ".gator/scripts/gator-pre-commit.py")


class TestHookMap:
    def test_all_seven_entries_mapped(self):
        assert set(hook.HOOK_MAP) == {"pre-commit", "commit-msg",
                                      "post-commit", "session-open",
                                      "session-start", "enforcer-review",
                                      "approve"}

    def test_approve_is_non_blocking_passthrough(self):
        """Phase 4d: the Architect override path stays reachable post-
        removal via `gator hook approve` — non-blocking, argv passthrough
        (--reason/--name). Reachability is verified here rather than by
        executing the script: the constitution forbids the agent running
        gator-approve.py."""
        assert "approve" not in hook.BLOCKING_HOOKS
        assert hook.HOOK_MAP["approve"] == ("gator-approve.py", [], True)
        wheel = hook._wheel_runtime_dir()
        assert (wheel / "gator-approve.py").is_file()

    def test_enforcer_review_reachable_in_wheel_runtime(self):
        wheel = hook._wheel_runtime_dir()
        assert (wheel / "enforcer-review.py").is_file()

    def test_enforcer_review_is_non_blocking_passthrough(self):
        assert "enforcer-review" not in hook.BLOCKING_HOOKS
        assert hook.HOOK_MAP["enforcer-review"][2] is True

    def test_only_pre_commit_blocks(self):
        assert hook.BLOCKING_HOOKS == {"pre-commit"}

    def test_commit_msg_wants_passthrough(self):
        assert hook.HOOK_MAP["commit-msg"][2] is True
        assert hook.HOOK_MAP["pre-commit"][2] is False


class TestMain:
    def test_unknown_hook_usage_error(self):
        assert hook.main(["not-a-hook"]) == 2

    def test_no_args_usage_error(self):
        assert hook.main([]) == 2

    def test_wheel_runtime_dir_points_at_templates(self):
        d = hook._wheel_runtime_dir()
        assert d.name == "scripts"
        assert d.parent.name == "gator-starter"
        assert (d / "gator-pre-commit.py").is_file()


# ── Issue #32: session-hook root resolution ─────────────────────
#
# `gator hook session-open` and `gator hook session-start` may be
# invoked by an AI tool whose cwd is a governed repository
# subdirectory (e.g. `repo/src/`). Before the fix, `main()` passed
# `Path.cwd()` directly to `resolve_governed_runtime`; the
# subdirectory was misclassified as ungoverned and the session
# hook skipped its existing behavior.
#
# The fix: for session-open and session-start only, resolve the
# enclosing Git worktree's top level via `git rev-parse
# --show-toplevel`. Commit hooks are unchanged — git itself invokes
# them with cwd at the top level.
#
# These tests use real `git init` calls in `tmp_path`. Git is
# available on every CI runner that also runs `actions/checkout`.

import subprocess as _subprocess


def _git_init(path):
    """Init a git repo at `path` with minimal identity for
    downstream `commit` / `worktree` calls."""
    _subprocess.run(["git", "init", "-q", "-b", "main", str(path)],
                    check=True)
    _subprocess.run(["git", "-C", str(path), "config",
                     "user.email", "t@t"], check=True)
    _subprocess.run(["git", "-C", str(path), "config",
                     "user.name", "t"], check=True)


class TestResolveRepoRoot:
    """Six acceptance-coverage cases from issue #32, one test per case."""

    def test_session_open_from_repo_root_unchanged(self, tmp_path):
        """Case 1: invocation at the governed repo root must behave
        exactly as before — cwd IS the top level, resolver returns
        the same path."""
        _git_init(tmp_path)
        (tmp_path / ".gator").mkdir()
        got = hook._resolve_repo_root(tmp_path, "session-open")
        assert got.resolve() == tmp_path.resolve()

    def test_session_open_from_governed_subdirectory_resolves_to_toplevel(
            self, tmp_path):
        """Case 2: cwd inside a governed subdirectory resolves to the
        governed repository's top level — the bug this issue fixes."""
        _git_init(tmp_path)
        (tmp_path / ".gator").mkdir()
        subdir = tmp_path / "src"
        subdir.mkdir()
        got = hook._resolve_repo_root(subdir, "session-open")
        assert got.resolve() == tmp_path.resolve()

    def test_session_start_from_governed_subdirectory_resolves_to_toplevel(
            self, tmp_path):
        """Same rule for session-start (the vendor SessionStart entry
        point). Pinned separately because the issue names both hooks."""
        _git_init(tmp_path)
        (tmp_path / ".gator").mkdir()
        subdir = tmp_path / "src" / "deep"
        subdir.mkdir(parents=True)
        got = hook._resolve_repo_root(subdir, "session-start")
        assert got.resolve() == tmp_path.resolve()

    def test_session_open_linked_worktree_resolves_to_worktree_toplevel(
            self, tmp_path):
        """Case 3: a linked worktree's subdirectory resolves to that
        worktree's own top level, NOT the main repo. `git rev-parse
        --show-toplevel` returns the worktree top when run from
        inside a linked worktree."""
        main_repo = tmp_path / "main-repo"
        main_repo.mkdir()
        _git_init(main_repo)
        (main_repo / "seed.txt").write_text("x\n", encoding="utf-8")
        _subprocess.run(["git", "-C", str(main_repo), "add", "."],
                        check=True)
        _subprocess.run(["git", "-C", str(main_repo), "commit", "-q",
                         "-m", "seed"], check=True)
        wt = tmp_path / "linked-worktree"
        _subprocess.run(["git", "-C", str(main_repo), "worktree",
                         "add", "-q", str(wt), "HEAD"], check=True)
        subdir = wt / "sub"
        subdir.mkdir()
        got = hook._resolve_repo_root(subdir, "session-open")
        assert got.resolve() == wt.resolve()

    def test_session_open_outside_git_returns_cwd(
            self, tmp_path, monkeypatch):
        """Case 4: invocation outside any Git tree preserves today's
        ungoverned, non-blocking behavior — resolver returns cwd
        unchanged, and downstream `resolve_governed_runtime` will
        report ungoverned.

        Hermetic: pytest's tmp_path may sit inside a parent Git tree
        (e.g. `--basetemp=.tmp/...` places it inside this checkout).
        A real `git rev-parse` from such a subdirectory correctly
        finds the enclosing repo. Mock `subprocess.run` to return
        the outside-Git shape (rc != 0) so the test asserts the
        outside-Git BRANCH of the resolver, not a coincidence of
        temp-dir placement."""
        outside = tmp_path / "no-git"
        outside.mkdir()

        def _mock_run(*args, **kwargs):
            class _R:
                returncode = 128
                stdout = ""
                stderr = ("fatal: not a git repository "
                          "(or any of the parent directories): .git\n")
            return _R()

        monkeypatch.setattr(hook.subprocess, "run", _mock_run)
        got = hook._resolve_repo_root(outside, "session-open")
        assert got.resolve() == outside.resolve()

    def test_session_open_nested_ungoverned_git_stays_at_nested_toplevel(
            self, tmp_path):
        """Case 5: a nested ungoverned Git repository inside a
        governed parent resolves to the nested top level (its own
        `.git` boundary) — do NOT walk past that boundary into the
        governed parent."""
        parent = tmp_path / "governed-parent"
        parent.mkdir()
        _git_init(parent)
        (parent / ".gator").mkdir()
        nested = parent / "vendored" / "otherproject"
        nested.mkdir(parents=True)
        _git_init(nested)
        # Nested has NO `.gator/` — the current code would classify
        # it as ungoverned once run from its top level, which is
        # correct. The bug case would be walking up to the governed
        # parent and running governed behavior from an unrelated
        # nested repo.
        subdir = nested / "src"
        subdir.mkdir()
        got = hook._resolve_repo_root(subdir, "session-open")
        assert got.resolve() == nested.resolve()

    @pytest.mark.parametrize("hook_name",
                             ["pre-commit", "commit-msg", "post-commit"])
    def test_commit_hooks_unchanged_by_root_resolution(
            self, tmp_path, hook_name):
        """Case 6: commit-hook dispatch behavior remains unchanged.
        Git itself invokes commit hooks with cwd already at the top
        level, so the resolver must NOT walk to the top level for
        them — even if invoked with a subdirectory cwd (test-only
        edge). Preserving cwd verbatim keeps commit-hook semantics
        identical to pre-fix behavior."""
        _git_init(tmp_path)
        subdir = tmp_path / "src"
        subdir.mkdir()
        got = hook._resolve_repo_root(subdir, hook_name)
        assert got == subdir


class TestResolveRepoRootAdditionalGuards:
    """Non-acceptance-coverage cases the resolver must handle
    gracefully to preserve today's fail-open behavior."""

    def test_git_missing_from_path_returns_cwd(self, tmp_path, monkeypatch):
        """If `git` is not on PATH (unusual but possible on stripped
        CI images or exotic dev machines), the resolver must not
        raise — return cwd, let the downstream ungoverned path
        handle it."""
        # Force `git` invocation to raise FileNotFoundError via a
        # PATH pointed at an empty dir.
        empty = tmp_path / "empty-path"
        empty.mkdir()
        monkeypatch.setenv("PATH", str(empty))
        # On Windows, PATHEXT / cmd.exe resolution may still find
        # git.exe via other means; skip cleanly if the test can't
        # actually poison the git resolution.
        try:
            _subprocess.run(["git", "--version"],
                            capture_output=True, timeout=2)
            pytest.skip("could not poison git PATH lookup on this platform")
        except (FileNotFoundError, OSError):
            pass
        got = hook._resolve_repo_root(tmp_path, "session-open")
        assert got == tmp_path

    def test_enforcer_review_and_approve_return_cwd_unchanged(
            self, tmp_path):
        """The dispatcher also handles `enforcer-review` and
        `approve` (non-git hooks); they run with cwd owned by the
        caller and MUST NOT get the Git-top-level lookup. Only
        session-open and session-start opt in."""
        _git_init(tmp_path)
        (tmp_path / ".gator").mkdir()
        subdir = tmp_path / "src"
        subdir.mkdir()
        for hook_name in ("enforcer-review", "approve"):
            got = hook._resolve_repo_root(subdir, hook_name)
            assert got == subdir, (
                f"{hook_name} should NOT walk to git top-level")


class TestMainSeamWiring:
    """Codex round-1 finding: the helper-level TestResolveRepoRoot
    tests would all still pass if a future edit reverted `main()`
    back to `repo_root = Path.cwd()` (bare) — the bug from issue
    #32 would silently reopen. These pins invoke `main()` from a
    governed subdirectory and assert the resolved-root value
    actually reaches `resolve_governed_runtime` (and, transitively,
    `plan_dispatch`).

    Method: mock `resolve_governed_runtime` to capture its
    argument and return an `ungoverned` decision. `plan_dispatch`
    then returns `action=skip, exit_code=0` on the ungoverned
    branch, so `main()` short-circuits before any subprocess spawn
    — the test never runs a real hook script."""

    def _ungoverned_capture(self, monkeypatch):
        captured = []

        def _mock_resolve(rr):
            captured.append(rr)
            return {"mode": "ungoverned", "pin_version": None,
                    "cli_version": "2.13.4",
                    "reason": "test-mock"}
        monkeypatch.setattr(hook, "resolve_governed_runtime", _mock_resolve)
        return captured

    @pytest.mark.parametrize("hook_name",
                             ["session-open", "session-start"])
    def test_main_session_hook_from_subdir_passes_git_toplevel(
            self, tmp_path, monkeypatch, hook_name):
        """Regression against a future revert of `main()`'s single
        line from `_resolve_repo_root(Path.cwd(), hook_name)` back
        to `Path.cwd()`. This pin would fail against pre-fix
        `main()` because the bare `Path.cwd()` would resolve to
        the subdirectory, not the git top level."""
        _git_init(tmp_path)
        (tmp_path / ".gator").mkdir()
        subdir = tmp_path / "src"
        subdir.mkdir()
        monkeypatch.chdir(subdir)
        captured = self._ungoverned_capture(monkeypatch)

        rc = hook.main([hook_name])

        assert rc == 0, (
            "ungoverned decision + non-blocking hook should exit 0")
        assert len(captured) == 1, (
            f"resolve_governed_runtime called {len(captured)} times, "
            f"expected 1")
        assert captured[0].resolve() == tmp_path.resolve(), (
            f"main() with cwd={subdir} and hook={hook_name!r} passed "
            f"{captured[0]!r} to resolve_governed_runtime instead of "
            f"the git top-level {tmp_path}. A future revert of "
            f"main()'s repo_root line to bare Path.cwd() would "
            f"re-open issue #32 while every TestResolveRepoRoot pin "
            f"still passed — that's the class of regression this "
            f"seam pin catches.")

    def test_main_pre_commit_from_subdir_passes_cwd_unchanged(
            self, tmp_path, monkeypatch):
        """Sibling seam pin: commit hooks must NOT walk to git top
        level even when invoked with a subdirectory cwd. Would fail
        if a future edit added `pre-commit` to
        `_HOOKS_NEEDING_GIT_TOPLEVEL`. Also demonstrates that the
        resolver's opt-in behavior actually reaches `main()`, not
        just the helper."""
        _git_init(tmp_path)
        (tmp_path / ".gator").mkdir()
        subdir = tmp_path / "src"
        subdir.mkdir()
        monkeypatch.chdir(subdir)
        captured = self._ungoverned_capture(monkeypatch)

        rc = hook.main(["pre-commit"])

        assert rc == 0, "ungoverned pre-commit exits 0 (warning-mode)"
        assert len(captured) == 1
        assert captured[0].resolve() == subdir.resolve(), (
            f"main() with cwd={subdir} and hook='pre-commit' passed "
            f"{captured[0]!r} instead of the subdirectory. Commit "
            f"hooks must NOT walk to git top-level.")
