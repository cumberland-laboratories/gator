"""
Tests for gatorize.py — the cross-platform Gator installer.
"""

import io
import sys
from pathlib import Path

import pytest

from conftest import load_script

SCRIPTS_DIR = Path(__file__).parent.parent / "src" / "gator_command" / "scripts"
gatorize = load_script("gatorize", search_dir=SCRIPTS_DIR)

# gatorize.helpers is the sibling sub-module we need to poke for AUTO_YES tests.
# It's imported through gatorize (as `gatorize.helpers`), so it's already loaded.
from gatorize import helpers as gatorize_helpers


def _setup_gator_dir(tmp_path):
    """Create the minimal .gator/ structure that write_stubs expects."""
    gator_dir = tmp_path / ".gator"
    gator_dir.mkdir()
    (gator_dir / "sessions").mkdir()
    (gator_dir / "charters").mkdir()
    return gator_dir


class TestWriteStubsVault:
    """Tests for vault directory creation and gitignore in write_stubs()."""

    def test_creates_vault_directory(self, tmp_path):
        """write_stubs creates .gator/vault/ with .gitkeep."""
        gator_dir = _setup_gator_dir(tmp_path)

        gatorize.write_stubs(gator_dir)

        vault_dir = gator_dir / "vault"
        assert vault_dir.is_dir()
        assert (vault_dir / ".gitkeep").exists()

    def test_appends_vault_to_existing_gitignore(self, tmp_path):
        """write_stubs appends .gator/vault/ to an existing .gitignore."""
        gator_dir = _setup_gator_dir(tmp_path)

        # Pre-existing .gitignore without vault rule
        gi = tmp_path / ".gitignore"
        gi.write_text("__pycache__/\n*.pyc\n", encoding="utf-8")

        gatorize.write_stubs(gator_dir)

        gi_text = gi.read_text(encoding="utf-8")
        assert ".gator/vault/" in gi_text
        # Original content preserved
        assert "__pycache__/" in gi_text

    def test_creates_gitignore_if_missing(self, tmp_path):
        """write_stubs creates .gitignore with vault rule if none exists."""
        gator_dir = _setup_gator_dir(tmp_path)

        gatorize.write_stubs(gator_dir)

        gi = tmp_path / ".gitignore"
        assert gi.exists()
        assert ".gator/vault/" in gi.read_text(encoding="utf-8")

    def test_idempotent_vault_gitignore(self, tmp_path):
        """Running write_stubs twice doesn't duplicate the vault rule."""
        gator_dir = _setup_gator_dir(tmp_path)

        gatorize.write_stubs(gator_dir)
        gatorize.write_stubs(gator_dir)

        gi_text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        assert gi_text.count(".gator/vault/") == 1

    def test_vault_not_overwritten_if_exists(self, tmp_path):
        """Existing vault directory content is preserved."""
        gator_dir = _setup_gator_dir(tmp_path)
        vault_dir = gator_dir / "vault"
        vault_dir.mkdir()
        secret = vault_dir / "api-key.txt"
        secret.write_text("sk-secret-123", encoding="utf-8")

        gatorize.write_stubs(gator_dir)

        assert secret.exists()
        assert secret.read_text(encoding="utf-8") == "sk-secret-123"


class TestEnsureRepoGitignore:
    """Tests for ensure_repo_gitignore() — called on both install and upgrade."""

    def test_adds_all_standard_rules(self, tmp_path):
        """All three standard rules are added to a bare repo."""
        gatorize.ensure_repo_gitignore(tmp_path)
        gi_text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        assert ".gator/vault/" in gi_text
        assert ".vscode/" in gi_text
        assert "__pycache__/" in gi_text

    def test_appends_missing_rules_to_existing(self, tmp_path):
        """Only missing rules are added; existing content preserved."""
        gi = tmp_path / ".gitignore"
        gi.write_text("node_modules/\n.gator/vault/\n", encoding="utf-8")

        gatorize.ensure_repo_gitignore(tmp_path)

        gi_text = gi.read_text(encoding="utf-8")
        assert "node_modules/" in gi_text
        assert gi_text.count(".gator/vault/") == 1  # not duplicated
        assert ".vscode/" in gi_text  # newly added
        assert "__pycache__/" in gi_text  # newly added

    def test_idempotent(self, tmp_path):
        """Running twice doesn't duplicate rules."""
        gatorize.ensure_repo_gitignore(tmp_path)
        gatorize.ensure_repo_gitignore(tmp_path)

        gi_text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        assert gi_text.count("__pycache__/") == 1
        assert gi_text.count(".vscode/") == 1
        assert gi_text.count(".gator/vault/") == 1

    def test_upgrade_path_gets_rules(self, tmp_path):
        """Simulates the upgrade scenario: repo already has .gitignore but missing new rules."""
        gi = tmp_path / ".gitignore"
        # Simulate an older gatorized repo that only had vault
        gi.write_text("# Old rules\n.gator/vault/\n", encoding="utf-8")

        gatorize.ensure_repo_gitignore(tmp_path)

        gi_text = gi.read_text(encoding="utf-8")
        assert "__pycache__/" in gi_text
        assert ".vscode/" in gi_text
        assert "# Old rules" in gi_text  # preserved

    def test_adds_local_agent_companion_rules(self, tmp_path):
        """The three *.local.md companion rules are added on a bare repo."""
        gatorize.ensure_repo_gitignore(tmp_path)
        gi_text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        assert "AGENTS.local.md" in gi_text
        assert "CLAUDE.local.md" in gi_text
        assert "GEMINI.local.md" in gi_text

    def test_local_companion_rules_idempotent(self, tmp_path):
        """Repeat invocations do not duplicate the *.local.md rules."""
        gatorize.ensure_repo_gitignore(tmp_path)
        gatorize.ensure_repo_gitignore(tmp_path)
        gi_text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        assert gi_text.count("AGENTS.local.md") == 1
        assert gi_text.count("CLAUDE.local.md") == 1
        assert gi_text.count("GEMINI.local.md") == 1

    def test_local_companion_rules_added_on_upgrade(self, tmp_path):
        """A repo that predates the *.local.md rules picks them up on convergence."""
        gi = tmp_path / ".gitignore"
        # Simulate a repo gatorized before the local-companion rules landed
        gi.write_text(
            "# Old rules\n.gator/vault/\n.vscode/\n__pycache__/\n",
            encoding="utf-8",
        )
        gatorize.ensure_repo_gitignore(tmp_path)
        gi_text = gi.read_text(encoding="utf-8")
        assert "AGENTS.local.md" in gi_text
        assert "CLAUDE.local.md" in gi_text
        assert "GEMINI.local.md" in gi_text
        # Pre-existing content preserved, not duplicated
        assert gi_text.count(".gator/vault/") == 1
        assert "# Old rules" in gi_text


class TestRenderEntryContentLocalCompanion:
    """Tests for the local-companion block in render_entry_content()."""

    def test_claude_references_claude_local_md(self):
        content = gatorize.render_entry_content(has_command_post=False, agent_type="claude")
        assert "**Personal skills**" in content
        assert "`CLAUDE.local.md`" in content
        assert "`AGENTS.local.md`" not in content
        assert "`GEMINI.local.md`" not in content

    def test_agents_references_agents_local_md(self):
        content = gatorize.render_entry_content(has_command_post=False, agent_type="agents")
        assert "**Personal skills**" in content
        assert "`AGENTS.local.md`" in content
        assert "`CLAUDE.local.md`" not in content
        assert "`GEMINI.local.md`" not in content

    def test_gemini_references_gemini_local_md(self):
        content = gatorize.render_entry_content(has_command_post=False, agent_type="gemini")
        assert "**Personal skills**" in content
        assert "`GEMINI.local.md`" in content
        assert "`CLAUDE.local.md`" not in content
        assert "`AGENTS.local.md`" not in content

    def test_team_shared_skills_wording_present(self):
        """All three vendors carry identical team-shared skills teaching."""
        for agent_type in ("claude", "agents", "gemini"):
            content = gatorize.render_entry_content(has_command_post=False, agent_type=agent_type)
            assert "**Team-shared skills**" in content
            assert ".gator/procedures/" in content
            assert ".gator/charters/" in content

    def test_precedence_contract_wording_present(self):
        """The MUST NOT override precedence contract appears verbatim (Invariant #9)."""
        for agent_type in ("claude", "agents", "gemini"):
            content = gatorize.render_entry_content(has_command_post=False, agent_type=agent_type)
            assert "gitignored" in content
            assert "never touched by Gator" in content
            assert "MUST NOT override" in content

    def test_reference_note_pointer_present(self):
        """The layout-defensive pointer to local-agent-skills.md is included."""
        for agent_type in ("claude", "agents", "gemini"):
            content = gatorize.render_entry_content(has_command_post=False, agent_type=agent_type)
            assert "local-agent-skills.md" in content
            assert ".gator/reference-notes/" in content
            assert ".gator/.includes/reference-notes/" in content

    def test_agents_still_carries_enforcer_note(self):
        """Adding the local-companion block did not displace the AGENTS-only enforcer note."""
        content = gatorize.render_entry_content(has_command_post=False, agent_type="agents")
        assert "enforcer review" in content
        assert "enforcer-prompt.md" in content


class TestUpgradeLegacyEntryPoint:
    """Byte-format snapshot tests for upgrade_legacy_entry_point() — pins the
    contract Stage 4's `gator state repair` will rely on. Any refactor that
    changes these byte-formats must be a plan-level decision."""

    def _managed_block(self, agent_type):
        from gatorize.managed_block import GATOR_BEGIN, GATOR_END, render_managed_region
        content = gatorize.render_entry_content(has_command_post=False, agent_type=agent_type)
        return f"{GATOR_BEGIN}{render_managed_region(content)}{GATOR_END}"

    def test_legacy_with_gator_marker_and_pre_gator_section(self, tmp_path):
        """Legacy file with prose before GATOR_MARKER + a Pre-Gator section
        preserves the section, drops the prose before the marker, and rewraps
        in sentinels."""
        from gatorize.entry_points import upgrade_legacy_entry_point
        target = tmp_path
        (target / "CLAUDE.md").write_text(
            "# Custom Header\n\n"
            "Old prose that predates Gator.\n\n"
            "# --- Gator Navigation Coding ---\n"
            "old legacy governance text\n\n"
            "## Pre-Gator Instructions\n\n"
            "Custom instructions that must survive.\n",
            encoding="utf-8",
        )
        upgrade_legacy_entry_point(target, "CLAUDE.md", has_command_post=False, agent_type="claude")
        result = (target / "CLAUDE.md").read_text(encoding="utf-8")
        block = self._managed_block("claude")
        expected = (
            "# Custom Header\n\n"
            "Old prose that predates Gator.\n\n"
            f"{block}\n\n"
            "## Pre-Gator Instructions\n\n"
            "Custom instructions that must survive.\n\n"
        )
        assert result == expected

    def test_legacy_with_no_marker_but_fingerprint_and_no_pre_gator(self, tmp_path):
        """Fingerprint-only legacy (e.g. mentions gator-init.py but no marker)
        with no Pre-Gator section: gets fresh header + placeholder + sentinels,
        original file content is dropped."""
        from gatorize.entry_points import upgrade_legacy_entry_point
        target = tmp_path
        (target / "AGENTS.md").write_text(
            "loose prose that mentions gator-init.py somewhere\n",
            encoding="utf-8",
        )
        upgrade_legacy_entry_point(target, "AGENTS.md", has_command_post=False, agent_type="agents")
        result = (target / "AGENTS.md").read_text(encoding="utf-8")
        block = self._managed_block("agents")
        expected = (
            "# Codex Entry Point\n\n"
            "You are the primary agent for this project.\n\n"
            f"{block}\n"
        )
        assert result == expected

    def test_legacy_with_marker_but_no_pre_gator_section(self, tmp_path):
        """Marker present, prose before it, no Pre-Gator section: prose before
        the marker is preserved as pre_gator, no post_gator appended."""
        from gatorize.entry_points import upgrade_legacy_entry_point
        target = tmp_path
        (target / "GEMINI.md").write_text(
            "# Gemini Notes\n\n"
            "Some prose before.\n\n"
            "# --- Gator Command Post ---\n"
            "old thin-link text\n",
            encoding="utf-8",
        )
        upgrade_legacy_entry_point(target, "GEMINI.md", has_command_post=False, agent_type="gemini")
        result = (target / "GEMINI.md").read_text(encoding="utf-8")
        block = self._managed_block("gemini")
        expected = (
            "# Gemini Notes\n\n"
            "Some prose before.\n\n"
            f"{block}\n"
        )
        assert result == expected

    def test_legacy_fingerprint_with_pre_gator_section(self, tmp_path):
        """Fingerprint but no marker, with Pre-Gator section: no pre_gator
        prose (marker not found), fresh header used, Pre-Gator section preserved."""
        from gatorize.entry_points import upgrade_legacy_entry_point
        target = tmp_path
        (target / "CLAUDE.md").write_text(
            "loose prose mentions .gator/constitution.md\n\n"
            "## Pre-Gator Instructions\n\n"
            "Kept content.\n",
            encoding="utf-8",
        )
        upgrade_legacy_entry_point(target, "CLAUDE.md", has_command_post=False, agent_type="claude")
        result = (target / "CLAUDE.md").read_text(encoding="utf-8")
        block = self._managed_block("claude")
        expected = (
            "# Claude Code Entry Point\n\n"
            "You are the primary agent for this project.\n\n"
            f"{block}\n\n"
            "## Pre-Gator Instructions\n\n"
            "Kept content.\n\n"
        )
        assert result == expected


# ── Stage 2 of retire-gator-install plan (2026-07-30) ─────────────────────────
# --yes flag scaffold + explicit-opt-in contract in helpers.prompt / helpers.confirm.
# Behavior is byte-identical to today for every existing call site.
# Sites do not opt in during Stage 2 — that's Stage 3.

@pytest.fixture(autouse=False)
def reset_auto_yes():
    """Reset helpers.AUTO_YES around each test so module-level state does
    not leak between cases.
    """
    prior = gatorize_helpers.get_auto_yes()
    gatorize_helpers.set_auto_yes(False)
    yield
    gatorize_helpers.set_auto_yes(prior)


class TestYesFlagParser:
    """--yes / -y is parsed into args and reaches helpers.AUTO_YES exactly
    when gatorize.py:main() writes it via helpers.set_auto_yes().
    """

    def test_argparse_accepts_yes_flag(self, tmp_path, monkeypatch, reset_auto_yes):
        """--yes on the CLI sets helpers.AUTO_YES to True."""
        # Short-circuit main() after argparse+set_auto_yes by making
        # detect_scenario raise SystemExit(0) — before any filesystem action.
        monkeypatch.setattr(gatorize, "detect_scenario", lambda t: (_ for _ in ()).throw(SystemExit(0)))
        monkeypatch.setattr(sys, "argv", ["gatorize", str(tmp_path), "--yes"])
        with pytest.raises(SystemExit):
            gatorize.main()
        assert gatorize_helpers.get_auto_yes() is True

    def test_argparse_accepts_short_flag(self, tmp_path, monkeypatch, reset_auto_yes):
        """-y on the CLI sets helpers.AUTO_YES to True."""
        monkeypatch.setattr(gatorize, "detect_scenario", lambda t: (_ for _ in ()).throw(SystemExit(0)))
        monkeypatch.setattr(sys, "argv", ["gatorize", str(tmp_path), "-y"])
        with pytest.raises(SystemExit):
            gatorize.main()
        assert gatorize_helpers.get_auto_yes() is True

    def test_argparse_default_is_false(self, tmp_path, monkeypatch, reset_auto_yes):
        """Without --yes, helpers.AUTO_YES stays False after main() runs."""
        monkeypatch.setattr(gatorize, "detect_scenario", lambda t: (_ for _ in ()).throw(SystemExit(0)))
        monkeypatch.setattr(sys, "argv", ["gatorize", str(tmp_path)])
        with pytest.raises(SystemExit):
            gatorize.main()
        assert gatorize_helpers.get_auto_yes() is False

    def test_helpers_auto_yes_reset_between_tests(self, reset_auto_yes):
        """The reset_auto_yes fixture restores prior state on teardown.

        Direct assertion that the fixture pattern works — if this test's
        mutation leaked to the next case, TestPromptExplicitOptIn's
        stdin-read tests would silently short-circuit.
        """
        gatorize_helpers.set_auto_yes(True)
        assert gatorize_helpers.get_auto_yes() is True
        # Teardown will flip it back to prior (False from the fixture).


class TestPromptExplicitOptIn:
    """helpers.prompt(auto_yes=<value>) short-circuits ONLY when both the
    module flag AND the call-site opt-in are set. Sites without auto_yes=
    continue to read stdin exactly as before.
    """

    def test_prompt_without_auto_yes_reads_stdin(self, monkeypatch, reset_auto_yes):
        """Regression guard: default behavior unchanged when auto_yes is not passed."""
        gatorize_helpers.set_auto_yes(False)
        monkeypatch.setattr("builtins.input", lambda _prompt: "2")
        assert gatorize_helpers.prompt("Choice", "1/2/x") == "2"

    def test_prompt_with_auto_yes_and_flag_short_circuits(self, monkeypatch, reset_auto_yes):
        """AUTO_YES True + auto_yes= passed → returns opt-in value without stdin."""
        gatorize_helpers.set_auto_yes(True)
        def _no_stdin(_prompt):
            raise AssertionError("stdin must not be read under auto_yes short-circuit")
        monkeypatch.setattr("builtins.input", _no_stdin)
        assert gatorize_helpers.prompt("Choice", "1/2/x", auto_yes="1") == "1"

    def test_prompt_with_auto_yes_but_flag_off_reads_stdin(self, monkeypatch, reset_auto_yes):
        """Regression guard: auto_yes= is ignored when the --yes flag was not set."""
        gatorize_helpers.set_auto_yes(False)
        monkeypatch.setattr("builtins.input", lambda _prompt: "user-choice")
        assert gatorize_helpers.prompt("Choice", "1/2/x", auto_yes="1") == "user-choice"

    def test_prompt_still_returns_default_on_eof_without_auto_yes(self, monkeypatch, reset_auto_yes):
        """Regression guard: EOF fallback behavior is preserved."""
        gatorize_helpers.set_auto_yes(False)
        def _raise_eof(_prompt):
            raise EOFError
        monkeypatch.setattr("builtins.input", _raise_eof)
        assert gatorize_helpers.prompt("Choice", "1/2/x", default="fallback") == "fallback"


class TestConfirmExplicitOptIn:
    """helpers.confirm(auto_yes=True/False) short-circuits ONLY when both
    the module flag AND the call-site opt-in are set.
    """

    def test_confirm_with_auto_yes_true_and_flag_short_circuits(self, monkeypatch, reset_auto_yes):
        gatorize_helpers.set_auto_yes(True)
        def _no_stdin(_prompt):
            raise AssertionError("stdin must not be read under auto_yes short-circuit")
        monkeypatch.setattr("builtins.input", _no_stdin)
        assert gatorize_helpers.confirm("Proceed?", auto_yes=True) is True

    def test_confirm_with_auto_yes_false_and_flag_short_circuits(self, monkeypatch, reset_auto_yes):
        gatorize_helpers.set_auto_yes(True)
        def _no_stdin(_prompt):
            raise AssertionError("stdin must not be read under auto_yes short-circuit")
        monkeypatch.setattr("builtins.input", _no_stdin)
        assert gatorize_helpers.confirm("Proceed?", auto_yes=False) is False

    def test_confirm_with_auto_yes_but_flag_off_reads_stdin(self, monkeypatch, reset_auto_yes):
        """Regression guard: auto_yes= is ignored without the --yes flag."""
        gatorize_helpers.set_auto_yes(False)
        monkeypatch.setattr("builtins.input", lambda _prompt: "n")
        assert gatorize_helpers.confirm("Proceed?", auto_yes=True) is False

    def test_confirm_without_auto_yes_reads_stdin(self, monkeypatch, reset_auto_yes):
        """Regression guard: legacy call sites unchanged."""
        gatorize_helpers.set_auto_yes(False)
        monkeypatch.setattr("builtins.input", lambda _prompt: "y")
        assert gatorize_helpers.confirm("Proceed?") is True


# ── Stage 3 of retire-gator-install plan (2026-07-30) ─────────────────────────
# Branch-dance removal (action_feature_branch gone, GATOR_BRANCH gone),
# scenario-aware pre-action summary, dirty-tree gate, Y/n confirmation gate.

import subprocess


def _init_git_repo(path, branch="main"):
    """Initialize a git repo at `path` with one commit on `branch`."""
    subprocess.run(["git", "init", "-q", str(path)], check=True, timeout=10)
    subprocess.run(["git", "-C", str(path), "checkout", "-qB", branch], check=True, timeout=10)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@t"], check=True, timeout=10)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "t"], check=True, timeout=10)
    (path / "README.md").write_text("seed")
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True, timeout=10)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", "seed"], check=True, timeout=10)


class TestNoBranchDance:
    """action_feature_branch() and GATOR_BRANCH are gone. action_git_init()
    leaves Scenario 1 on git's default branch — never gator-install.
    """

    def test_gator_branch_constant_removed(self):
        """GATOR_BRANCH constant no longer exists on the module."""
        assert not hasattr(gatorize, "GATOR_BRANCH")

    def test_action_feature_branch_function_removed(self):
        """action_feature_branch function no longer exists on the module."""
        assert not hasattr(gatorize, "action_feature_branch")

    def test_git_default_branch_reads_init_default_branch(self, tmp_path):
        """_git_default_branch reads init.defaultBranch when set."""
        _init_git_repo(tmp_path, branch="main")
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "init.defaultBranch", "trunk"],
            check=True, timeout=10,
        )
        import os
        cwd = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            assert gatorize._git_default_branch() == "trunk"
        finally:
            os.chdir(cwd)

    def test_git_default_branch_fallback_is_main(self, tmp_path, monkeypatch):
        """When init.defaultBranch is unset, _git_default_branch returns 'main'."""
        # Simulate an environment where git config --get returns empty
        def _fake_git(*args, cwd=None):
            if args[:2] == ("config", "--get") and "init.defaultBranch" in args:
                return "", False
            return "", True
        monkeypatch.setattr(gatorize, "git", _fake_git)
        assert gatorize._git_default_branch() == "main"

    def test_action_git_init_no_gator_install_branch(self, tmp_path):
        """action_git_init() creates no gator-install branch."""
        # Scenario 1 requires the target dir to exist and have no .git/
        gatorize.action_git_init(tmp_path)
        result = subprocess.run(
            ["git", "-C", str(tmp_path), "branch", "--list", "gator-install"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.stdout.strip() == "", (
            f"gator-install branch must not exist after action_git_init; "
            f"got: {result.stdout!r}"
        )


class TestDirtyTreeGating:
    """_check_dirty_tree_and_gate: clean → return, dirty+yes → exit 1,
    dirty+interactive → c/a prompt.
    """

    def test_clean_tree_returns_silently(self, tmp_path, reset_auto_yes):
        _init_git_repo(tmp_path)
        # No changes since the seed commit → clean tree, no side effect
        gatorize._check_dirty_tree_and_gate(tmp_path)

    def test_dirty_tree_yes_flag_exits_1(self, tmp_path, reset_auto_yes, capsys):
        _init_git_repo(tmp_path)
        # Create an untracked file → dirty tree
        (tmp_path / "dirty.txt").write_text("uncommitted")
        gatorize_helpers.set_auto_yes(True)
        with pytest.raises(SystemExit) as exc:
            gatorize._check_dirty_tree_and_gate(tmp_path)
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "dirty tree" in out
        assert "non-interactive" in out

    def test_dirty_tree_interactive_c_proceeds(self, tmp_path, monkeypatch, reset_auto_yes):
        _init_git_repo(tmp_path)
        (tmp_path / "dirty.txt").write_text("uncommitted")
        monkeypatch.setattr("builtins.input", lambda _p: "c")
        # Should not raise
        gatorize._check_dirty_tree_and_gate(tmp_path)

    def test_dirty_tree_interactive_a_exits_0(self, tmp_path, monkeypatch, reset_auto_yes):
        _init_git_repo(tmp_path)
        (tmp_path / "dirty.txt").write_text("uncommitted")
        monkeypatch.setattr("builtins.input", lambda _p: "a")
        with pytest.raises(SystemExit) as exc:
            gatorize._check_dirty_tree_and_gate(tmp_path)
        assert exc.value.code == 0


class TestPreActionSummary:
    """Scenario-aware pre-action summary: Scenario 1 says 'new directory',
    Scenarios 2-5 say 'branch <name>' and include a safety-branch hint.
    """

    def test_scenario_1_omits_branch_phrase(self, tmp_path, capsys):
        """Codex Round-6 Finding 2 regression guard."""
        # tmp_path is a fresh dir with no git — Scenario 1 shape
        gatorize.print_pre_action_summary(tmp_path, 1)
        out = capsys.readouterr().out
        assert "Gatorizing new directory" in out
        assert "Gatorizing branch" not in out

    def test_scenario_1_omits_safety_branch_hint(self, tmp_path, capsys):
        """No safety-branch hint on Scenario 1 (no branches to branch from)."""
        gatorize.print_pre_action_summary(tmp_path, 1)
        out = capsys.readouterr().out
        assert "my-gator-experiment" not in out
        assert "safety-branch pattern applies" in out.lower() or \
               "no safety-branch pattern applies" in out.lower()

    def test_scenario_2_prints_branch_name(self, tmp_path, capsys):
        _init_git_repo(tmp_path, branch="dev")
        gatorize.print_pre_action_summary(tmp_path, 2)
        out = capsys.readouterr().out
        assert "Gatorizing branch 'dev'" in out
        assert "Gatorizing new directory" not in out

    def test_scenario_2_includes_safety_branch_hint(self, tmp_path, capsys):
        _init_git_repo(tmp_path, branch="dev")
        gatorize.print_pre_action_summary(tmp_path, 2)
        out = capsys.readouterr().out
        assert "my-gator-experiment" in out
        assert "git checkout -b" in out

    def test_summary_prints_target_path(self, tmp_path, capsys):
        _init_git_repo(tmp_path, branch="dev")
        gatorize.print_pre_action_summary(tmp_path, 2)
        assert str(tmp_path) in capsys.readouterr().out


class TestYesFlagPerSiteBehavior:
    """Codex Round-3 Finding 1 regression guards: the surviving multi-choice
    prompts declare their `auto_yes=` opt-in at the call site. Verified via
    source-string inspection because full end-to-end gatorize runs are heavy.
    """

    def test_entry_points_prompt_declares_auto_yes_1(self):
        """entry_points.py:215 prompt call passes auto_yes='1' (Backup & replace)."""
        source = (SCRIPTS_DIR / "gatorize" / "entry_points.py").read_text()
        assert 'auto_yes="1"' in source, (
            "entry_points.py must pass auto_yes='1' at the foreign-entry-point "
            "prompt (see Stage 3 plan)."
        )

    def test_gatorize_scenario_5_prompt_declares_auto_yes_x(self):
        """Scenario 5 morph/upgrade/cancel prompt passes auto_yes='x' (Cancel)."""
        source = (SCRIPTS_DIR / "gatorize.py").read_text()
        assert 'auto_yes="x"' in source, (
            "gatorize.py must pass auto_yes='x' at the Scenario 5 prompt."
        )

    def test_gatorize_scenario_5_yes_mode_error_message_present(self):
        """Scenario 5 under --yes prints a specific error before sys.exit(1)."""
        source = (SCRIPTS_DIR / "gatorize.py").read_text()
        # The message wording is checked in fragments because Python's
        # string-literal concatenation splits it across two adjacent literals
        # in the source; the runtime string is joined, the raw file is not.
        assert "Scenario 5" in source, (
            "gatorize.py must name Scenario 5 in the --yes refusal error."
        )
        assert "requires an interactive" in source, (
            "gatorize.py must explain why Scenario 5 refuses under --yes."
        )
        assert "helpers.get_auto_yes()" in source, (
            "The --yes refusal branch must gate on helpers.get_auto_yes()."
        )

    def test_morph_confirm_declares_auto_yes_true(self):
        """morph.py's 'Proceed with morph?' confirm passes auto_yes=True.

        Codex Stage-3 enforcer finding: without this opt-in, Scenario 4
        (legacy memex → morph) hangs under --yes because the Y/n prompt has
        no non-interactive path. Only Scenario 4 reaches this confirm under
        --yes (Scenario 5's morph path refuses earlier at auto_yes='x').
        """
        source = (SCRIPTS_DIR / "gatorize" / "morph.py").read_text()
        assert "auto_yes=True" in source, (
            "morph.py must pass auto_yes=True at the 'Proceed with morph?' confirm."
        )


# ── Stage 5 of retire-gator-install plan (2026-07-30) ─────────────────────────
# print_summary() signature rewrite (gator_branch → current_branch), scenario-
# aware recovery messaging, honest entry_points cancellation hint.

# post_install is a sub-module of gatorize. Load via importlib to keep parity
# with how gatorize itself is loaded (hyphenless top-level).
from gatorize import post_install as gatorize_post_install
from gatorize import entry_points as gatorize_entry_points


class TestPrintSummary:
    """print_summary(target, scenario, current_branch): new signature, honest
    recovery messaging, safety-branch pattern as the load-bearing recommendation.
    """

    def test_signature_has_current_branch_not_gator_branch(self):
        """Parameter name is current_branch (Stage 5 rename)."""
        import inspect
        params = list(inspect.signature(gatorize_post_install.print_summary).parameters)
        assert params == ["target", "scenario", "current_branch"], (
            f"print_summary signature must be (target, scenario, current_branch); got {params}"
        )

    def test_summary_prints_current_branch_name(self, tmp_path, capsys):
        """The current_branch value appears in the finalize section."""
        gatorize_post_install.print_summary(tmp_path, 2, "feature/my-branch")
        out = capsys.readouterr().out
        assert "feature/my-branch" in out

    def test_summary_no_gator_install_reference(self, tmp_path, capsys):
        """No 'gator-install' string anywhere in the summary output."""
        gatorize_post_install.print_summary(tmp_path, 2, "dev")
        out = capsys.readouterr().out
        assert "gator-install" not in out, (
            "print_summary output must not name the retired 'gator-install' branch."
        )

    def test_recovery_messaging_names_safety_branch_pattern(self, tmp_path, capsys):
        """The recovery paragraph names the safety-branch pattern as load-bearing."""
        gatorize_post_install.print_summary(tmp_path, 2, "dev")
        out = capsys.readouterr().out
        assert "safety-branch pattern" in out, (
            "Recovery messaging must name the safety-branch pattern explicitly."
        )
        assert "git checkout -b" in out, (
            "Recovery messaging must show the safety-branch recipe."
        )

    def test_recovery_messaging_does_not_promise_bare_git_checkout_dot(
        self, tmp_path, capsys,
    ):
        """`git checkout .` must not appear as a standalone recovery recipe.

        Codex Round-3 Finding 2 remediation. It's fine for `git checkout -- <path>`
        (double-dash, scoped) to appear — that's a real recipe for a specific
        subcase. But bare `git checkout .` is a glib promise git doesn't keep
        (it does not remove untracked new files, which is most of what gatorize
        installs on a fresh scenario).
        """
        gatorize_post_install.print_summary(tmp_path, 2, "dev")
        out = capsys.readouterr().out
        # Exact-substring check: the plain 'git checkout .' string
        assert "git checkout ." not in out, (
            "Bare `git checkout .` must not appear as a recovery recipe."
        )
        assert "git reset --hard HEAD~" in out, (
            "Scoped `git reset --hard HEAD~<N>` recipe should be listed."
        )

    def test_summary_names_current_branch_placeholder(self, tmp_path, capsys):
        """Fallback placeholder from a failed rev-parse still prints cleanly."""
        gatorize_post_install.print_summary(tmp_path, 1, "(current branch)")
        out = capsys.readouterr().out
        assert "(current branch)" in out
        # No crash, no truncation
        assert "SUCCESS" in out

    def test_summary_finalize_uses_add_and_commit_not_merge(self, tmp_path, capsys):
        """Finalization no longer merges gator-install → dev. Just add + commit
        on the current branch.
        """
        gatorize_post_install.print_summary(tmp_path, 2, "dev")
        out = capsys.readouterr().out
        assert "git add -A" in out
        assert "git checkout dev && git merge" not in out
        assert "git branch -d gator-install" not in out


class TestEntryPointsCancelHint:
    """action_install_entry_points' [x] Cancel branch prints an honest
    partial-cleanup hint. Stage 5 remediation.
    """

    def test_cancel_hint_source_has_no_gator_install_reference(self):
        """The Cancel branch source must not name the retired gator-install branch.

        Comments in the same function may reference the plan by name (that's
        fine — we look only at the print() literals via a targeted check).
        """
        source = (SCRIPTS_DIR / "gatorize" / "entry_points.py").read_text()
        # Locate the Cancel branch block by its distinctive intro.
        idx = source.index('"  Installation cancelled. Cleanup:"')
        # Walk forward until the next `elif`/`sys.exit(0)` — check the
        # bounded region for the old hint text.
        region_end = source.index("sys.exit(0)", idx)
        region = source[idx:region_end]
        assert "gator-install" not in region, (
            "Cancel-branch print() text still references the retired gator-install branch."
        )
        assert "git branch -D gator-install" not in region, (
            "Cancel-branch print() text still uses the obsolete branch-delete recovery."
        )

    def test_cancel_hint_source_names_entry_point_files(self):
        """The Cancel hint enumerates the entry-point files that may be on disk."""
        source = (SCRIPTS_DIR / "gatorize" / "entry_points.py").read_text()
        idx = source.index('"  Installation cancelled. Cleanup:"')
        region_end = source.index("sys.exit(0)", idx)
        region = source[idx:region_end]
        for fname in ("CLAUDE.md", "AGENTS.md", "GEMINI.md"):
            assert fname in region, (
                f"Cancel hint must name {fname} so the user knows what to remove."
            )

    def test_cancel_hint_source_mentions_experiment_branch_discard(self):
        """The Cancel hint tells users about discarding a self-created experiment branch."""
        source = (SCRIPTS_DIR / "gatorize" / "entry_points.py").read_text()
        idx = source.index('"  Installation cancelled. Cleanup:"')
        region_end = source.index("sys.exit(0)", idx)
        region = source[idx:region_end]
        assert "experiment branch" in region
        assert "git checkout <original-branch>" in region

    def test_cancel_hint_source_has_windows_recipe(self):
        """Codex Stage-5 finding: the cleanup recipe must work on Windows too.

        gatorize is cross-platform (Windows CMD/PowerShell, Git Bash, macOS,
        Linux); a bare `rm -f` recipe is unusable on Windows CMD and needs
        different flags in PowerShell. The Cancel branch now branches on
        `sys.platform` and prints a PowerShell recipe on Windows plus the
        bash recipe as an alternative.
        """
        source = (SCRIPTS_DIR / "gatorize" / "entry_points.py").read_text()
        idx = source.index('"  Installation cancelled. Cleanup:"')
        region_end = source.index("sys.exit(0)", idx)
        region = source[idx:region_end]
        # Windows branch
        assert 'sys.platform == "win32"' in region, (
            "Cancel hint must branch on sys.platform for cross-platform recipes."
        )
        assert "Remove-Item" in region, (
            "Windows branch must use PowerShell's Remove-Item, not `rm -f`."
        )
        # Unix branch still present
        assert "rm -f CLAUDE.md AGENTS.md GEMINI.md" in region, (
            "Non-Windows branch must retain the rm -f recipe."
        )


class TestNoUserFacingGatorInstallReferences:
    """Belt-and-suspenders sweep: no user-facing STRING in the installer path
    contains the retired 'gator-install' identifier. Comments and docstrings
    that reference the plan-name are allowed — we scope to print()/quoted
    strings in the fresh output surface.
    """

    def test_print_summary_output_clean(self, tmp_path, capsys):
        gatorize_post_install.print_summary(tmp_path, 2, "main")
        out = capsys.readouterr().out
        assert "gator-install" not in out

    def test_pre_action_summary_output_clean(self, tmp_path, capsys):
        # Scenario 1 fixture uses a fresh dir (no git)
        gatorize.print_pre_action_summary(tmp_path, 1)
        out = capsys.readouterr().out
        assert "gator-install" not in out
