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
