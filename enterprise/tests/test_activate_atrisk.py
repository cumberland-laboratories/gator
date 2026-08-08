"""Tests for Phase 5 activate.py additions.

Covers:
- `_GATOR_SCRIPT_RESOLVER`-based v2-first hook script discovery in the
  three hook wrapper templates
- `_enumerate_at_risk_hooks` — reads a repo's `.git/hooks/*`, detects
  non-.sample active hooks + framework markers, honors repo-local
  `core.hooksPath` as an immunity marker
- `_warn_about_at_risk_hooks` — silent when nothing is at risk, blocking
  Y/n prompt on Linux/macOS when at-risk hooks exist, informational-
  only on Windows, honors --yes / non-interactive skip
"""
from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

import pytest

# sys.path bootstrap identical to test_activate_hooks.py
ENTERPRISE_CLI_ROOT = Path(__file__).resolve().parent.parent / "enterprise-cli"
if str(ENTERPRISE_CLI_ROOT) not in sys.path:
    sys.path.insert(0, str(ENTERPRISE_CLI_ROOT))

from gator_enterprise_cli.commands.activate import (
    COMMIT_MSG_HOOK,
    POST_COMMIT_HOOK,
    PRE_COMMIT_HOOK,
    _enumerate_at_risk_hooks,
    _warn_about_at_risk_hooks,
)


# ============================================================
# v2-first script discovery (§11 Change 2)
# ============================================================


class TestV2FirstScriptDiscovery:
    """The three hook templates must probe v2 (.includes/scripts/) before
    v1 (scripts/). The old templates hardcoded v1 only, silently no-op'ing
    governance on v2 repos."""

    @pytest.mark.parametrize(
        "template,name",
        [
            (PRE_COMMIT_HOOK, "PRE_COMMIT_HOOK"),
            (COMMIT_MSG_HOOK, "COMMIT_MSG_HOOK"),
            (POST_COMMIT_HOOK, "POST_COMMIT_HOOK"),
        ],
    )
    def test_v2_path_probed_first(self, template, name):
        v2 = ".gator/.includes/scripts/gator-pre-commit.py"
        v1 = ".gator/scripts/gator-pre-commit.py"
        assert v2 in template, f"{name} missing v2 path {v2}"
        assert v1 in template, f"{name} missing v1 fallback {v1}"
        assert template.index(v2) < template.index(v1), (
            f"{name} probes v1 path before v2 — v2-only ratification "
            f"requires v2-first ordering"
        )

    @pytest.mark.parametrize(
        "template,name",
        [
            (PRE_COMMIT_HOOK, "PRE_COMMIT_HOOK"),
            (COMMIT_MSG_HOOK, "COMMIT_MSG_HOOK"),
            (POST_COMMIT_HOOK, "POST_COMMIT_HOOK"),
        ],
    )
    def test_gator_script_variable_set_from_probe(self, template, name):
        # The resolver assigns GATOR_SCRIPT from whichever path exists;
        # the wrapper then invokes "$PYTHON" "$GATOR_SCRIPT". Verify the
        # assignment shape is present.
        assert 'GATOR_SCRIPT=".gator/.includes/scripts/gator-pre-commit.py"' in template
        assert 'GATOR_SCRIPT=".gator/scripts/gator-pre-commit.py"' in template

    def test_post_commit_block_script_uses_v2_first(self):
        """The session-block generator fallback in POST_COMMIT_HOOK should
        follow the same v2-first pattern as the main pre-commit resolver.
        """
        v2 = ".gator/.includes/scripts/gator-session-block.py"
        v1 = ".gator/scripts/gator-session-block.py"
        assert v2 in POST_COMMIT_HOOK
        assert v1 in POST_COMMIT_HOOK
        assert POST_COMMIT_HOOK.index(v2) < POST_COMMIT_HOOK.index(v1)


# ============================================================
# _enumerate_at_risk_hooks
# ============================================================


def _init_git_repo(root: Path) -> None:
    """Create a bare .git/hooks dir structure without invoking git."""
    (root / ".git" / "hooks").mkdir(parents=True, exist_ok=True)


class TestEnumerateAtRiskHooks:
    def test_nonexistent_repo(self, tmp_path):
        result = _enumerate_at_risk_hooks(tmp_path / "does-not-exist")
        assert result["hooks"] == []
        assert result["frameworks"] == []
        assert result["has_local_hookspath"] is False

    def test_repo_without_git_dir(self, tmp_path):
        (tmp_path / "some_file.txt").write_text("hi", encoding="utf-8")
        result = _enumerate_at_risk_hooks(tmp_path)
        assert result["hooks"] == []
        assert result["frameworks"] == []

    def test_sample_files_are_ignored(self, tmp_path):
        _init_git_repo(tmp_path)
        (tmp_path / ".git" / "hooks" / "pre-commit.sample").write_text("#!/bin/sh\n")
        (tmp_path / ".git" / "hooks" / "pre-push.sample").write_text("#!/bin/sh\n")
        result = _enumerate_at_risk_hooks(tmp_path)
        assert result["hooks"] == []

    def test_active_hooks_detected(self, tmp_path):
        _init_git_repo(tmp_path)
        (tmp_path / ".git" / "hooks" / "pre-commit").write_text(
            "#!/bin/sh\nformat && lint\n"
        )
        (tmp_path / ".git" / "hooks" / "pre-push").write_text(
            "#!/bin/sh\nrun tests\n"
        )
        (tmp_path / ".git" / "hooks" / "pre-commit.sample").write_text("#!/bin/sh\n")
        result = _enumerate_at_risk_hooks(tmp_path)
        names = sorted(h["name"] for h in result["hooks"])
        assert names == ["pre-commit", "pre-push"]
        for hook in result["hooks"]:
            assert hook["bytes"] > 0
            assert len(hook["mtime_iso"]) == 10  # YYYY-MM-DD

    def test_framework_markers_detected(self, tmp_path):
        _init_git_repo(tmp_path)
        (tmp_path / ".pre-commit-config.yaml").write_text("repos: []\n")
        (tmp_path / "lefthook.yml").write_text("pre-commit: {}\n")
        result = _enumerate_at_risk_hooks(tmp_path)
        assert ".pre-commit-config.yaml" in result["frameworks"]
        assert "lefthook.yml" in result["frameworks"]

    def test_local_hookspath_marks_repo_immune(self, tmp_path, monkeypatch):
        _init_git_repo(tmp_path)
        (tmp_path / ".git" / "hooks" / "pre-commit").write_text("#!/bin/sh\n")

        # Fake git subprocess to report a local core.hooksPath. Patching
        # subprocess.run keeps the test hermetic (no real git needed).
        real_run = subprocess.run

        def fake_run(cmd, **kw):
            if (
                len(cmd) >= 5
                and cmd[0] == "git"
                and "--local" in cmd
                and cmd[-1] == "core.hooksPath"
            ):
                class R:
                    returncode = 0
                    stdout = ".git/hooks\n"
                    stderr = ""
                return R()
            return real_run(cmd, **kw)

        monkeypatch.setattr(
            "gator_enterprise_cli.commands.activate.subprocess.run",
            fake_run,
        )
        result = _enumerate_at_risk_hooks(tmp_path)
        assert result["has_local_hookspath"] is True
        # The hook file still gets enumerated, but the warning helper
        # treats has_local_hookspath as immunity.
        assert len(result["hooks"]) == 1


# ============================================================
# _warn_about_at_risk_hooks
# ============================================================


class _FakePrompt:
    def __init__(self, reply: str):
        self.reply = reply
        self.calls = 0

    def __call__(self, msg: str) -> str:
        self.calls += 1
        return self.reply


class TestWarnAboutAtRiskHooks:
    def test_silent_when_no_at_risk_repos(self, tmp_path):
        # Repo exists but has only sample hooks — no risk
        _init_git_repo(tmp_path)
        (tmp_path / ".git" / "hooks" / "pre-commit.sample").write_text("#!/bin/sh\n")
        stream = io.StringIO()
        _warn_about_at_risk_hooks(
            [{"path": str(tmp_path)}], stream=stream,
        )
        assert stream.getvalue() == ""

    def test_silent_when_repo_list_empty(self):
        stream = io.StringIO()
        _warn_about_at_risk_hooks([], stream=stream)
        assert stream.getvalue() == ""

    def test_prints_warning_with_at_risk_hook(self, tmp_path):
        _init_git_repo(tmp_path)
        (tmp_path / ".git" / "hooks" / "pre-commit").write_text(
            "#!/bin/sh\nrun-formatter\n"
        )
        stream = io.StringIO()
        prompt = _FakePrompt("y")
        _warn_about_at_risk_hooks(
            [{"path": str(tmp_path)}],
            stream=stream, prompt_fn=prompt,
        )
        output = stream.getvalue()
        assert "will take over the git-hook path" in output
        assert "pre-commit" in output
        assert str(tmp_path) in output
        assert prompt.calls == 1

    def test_blocks_on_no_reply(self, tmp_path):
        _init_git_repo(tmp_path)
        (tmp_path / ".git" / "hooks" / "pre-commit").write_text("#!/bin/sh\n")
        stream = io.StringIO()
        prompt = _FakePrompt("n")
        with pytest.raises(SystemExit) as exc:
            _warn_about_at_risk_hooks(
                [{"path": str(tmp_path)}],
                stream=stream, prompt_fn=prompt,
            )
        assert exc.value.code == 1

    def test_yes_flag_skips_prompt(self, tmp_path):
        _init_git_repo(tmp_path)
        (tmp_path / ".git" / "hooks" / "pre-commit").write_text("#!/bin/sh\n")
        stream = io.StringIO()
        prompt = _FakePrompt("n")  # would block if consulted
        _warn_about_at_risk_hooks(
            [{"path": str(tmp_path)}],
            assume_yes=True, stream=stream, prompt_fn=prompt,
        )
        assert prompt.calls == 0
        assert "--yes was passed" in stream.getvalue()

    def test_windows_informational_only(self, tmp_path):
        _init_git_repo(tmp_path)
        (tmp_path / ".git" / "hooks" / "pre-commit").write_text("#!/bin/sh\n")
        stream = io.StringIO()
        prompt = _FakePrompt("n")  # would block if consulted
        _warn_about_at_risk_hooks(
            [{"path": str(tmp_path)}],
            is_windows=True, stream=stream, prompt_fn=prompt,
        )
        assert prompt.calls == 0
        output = stream.getvalue()
        assert "will take over the git-hook path" in output
        assert "Windows:" in output
        assert "informational" in output

    def test_repos_with_local_hookspath_are_not_at_risk(self, tmp_path, monkeypatch):
        _init_git_repo(tmp_path)
        (tmp_path / ".git" / "hooks" / "pre-commit").write_text("#!/bin/sh\n")

        real_run = subprocess.run

        def fake_run(cmd, **kw):
            if len(cmd) >= 5 and cmd[0] == "git" and cmd[-1] == "core.hooksPath":
                class R:
                    returncode = 0
                    stdout = ".git/hooks\n"
                    stderr = ""
                return R()
            return real_run(cmd, **kw)

        monkeypatch.setattr(
            "gator_enterprise_cli.commands.activate.subprocess.run",
            fake_run,
        )
        stream = io.StringIO()
        # Because the repo has local core.hooksPath, warn helper should
        # treat it as immune and NOT prompt.
        _warn_about_at_risk_hooks(
            [{"path": str(tmp_path)}], stream=stream,
        )
        assert stream.getvalue() == ""

    def test_framework_marker_alone_triggers_warning(self, tmp_path):
        # No hook file, but pre-commit-config.yaml exists
        _init_git_repo(tmp_path)
        (tmp_path / ".pre-commit-config.yaml").write_text("repos: []\n")
        stream = io.StringIO()
        prompt = _FakePrompt("y")
        _warn_about_at_risk_hooks(
            [{"path": str(tmp_path)}],
            stream=stream, prompt_fn=prompt,
        )
        output = stream.getvalue()
        assert ".pre-commit-config.yaml" in output
        assert prompt.calls == 1
