"""Unit tests for enterprise/enterprise-cli/gator_enterprise_cli/vendor_hooks.py
(Phase 4c-B, consolidated into enterprise/ in Phase 4e).

Covers the MACHINE-scoped Enterprise variant of vendor SessionStart hook
install — writes to ~/.claude/settings.json, ~/.codex/hooks.json,
~/.gemini/settings.json. Distinct from the REPO-scoped variant in
gator-update.py/gatorize.py which writes to `<repo>/.claude/settings.json`
and is covered by tests/test_vendor_hooks.py.

All tests use `tmp_path` as the fake home directory via the `home`
parameter on `install_enterprise_vendor_hooks()`. Nothing in these
tests touches the real ~/.claude/, ~/.codex/, or ~/.gemini/ files.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure gator_enterprise_cli is importable — enterprise-cli source layout
# without needing pip install first. Adds enterprise/enterprise-cli/ to
# sys.path so `from gator_enterprise_cli import vendor_hooks` resolves.
ENTERPRISE_CLI_ROOT = Path(__file__).resolve().parent.parent / "enterprise-cli"
if str(ENTERPRISE_CLI_ROOT) not in sys.path:
    sys.path.insert(0, str(ENTERPRISE_CLI_ROOT))

from gator_enterprise_cli import vendor_hooks as enterprise_vendor_hooks


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class TestInstallEnterpriseVendorHooks:
    """The public entry point — end-to-end merge behavior."""

    def test_first_install_creates_all_three_settings_files(self, tmp_path):
        results = enterprise_vendor_hooks.install_enterprise_vendor_hooks(home=tmp_path)

        assert results == {
            "Claude Code": "installed",
            "Codex CLI": "installed",
            "Gemini CLI": "installed",
        }
        assert (tmp_path / ".claude" / "settings.json").exists()
        assert (tmp_path / ".codex" / "hooks.json").exists()
        assert (tmp_path / ".gemini" / "settings.json").exists()

    def test_installed_file_contains_expected_commands(self, tmp_path):
        enterprise_vendor_hooks.install_enterprise_vendor_hooks(home=tmp_path)
        data = _read(tmp_path / ".claude" / "settings.json")

        hooks = data["hooks"]["SessionStart"][0]["hooks"]
        commands = [h["command"] for h in hooks]
        assert "python .gator/scripts/gator-session-open.py" in commands
        assert "python .gator/scripts/gator-session-start.py" in commands

    def test_second_invocation_is_unchanged(self, tmp_path):
        enterprise_vendor_hooks.install_enterprise_vendor_hooks(home=tmp_path)
        second = enterprise_vendor_hooks.install_enterprise_vendor_hooks(home=tmp_path)

        assert second == {
            "Claude Code": "unchanged",
            "Codex CLI": "unchanged",
            "Gemini CLI": "unchanged",
        }

    def test_force_reapplies_even_when_unchanged(self, tmp_path):
        enterprise_vendor_hooks.install_enterprise_vendor_hooks(home=tmp_path)
        result = enterprise_vendor_hooks.install_enterprise_vendor_hooks(
            home=tmp_path, force=True,
        )

        for vendor, status in result.items():
            assert status == "updated", f"{vendor}: expected updated, got {status}"

    def test_returns_dict_never_raises(self, tmp_path):
        """Public entry point MUST NOT raise for expected error modes."""
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "settings.json").write_text(
            "{ not json", encoding="utf-8",
        )
        (tmp_path / ".codex").mkdir()
        (tmp_path / ".codex" / "hooks.json").write_text("[]", encoding="utf-8")

        result = enterprise_vendor_hooks.install_enterprise_vendor_hooks(home=tmp_path)
        assert result["Claude Code"] == "unchanged"
        assert result["Codex CLI"] == "unchanged"
        assert result["Gemini CLI"] == "installed"


class TestMergeSafety:
    """Existing user hooks MUST survive Gator install."""

    def test_preserves_pre_existing_user_hooks_in_other_events(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings = claude_dir / "settings.json"
        settings.write_text(json.dumps({
            "hooks": {
                "UserPromptSubmit": [
                    {"hooks": [{"type": "command", "command": "python my-linter.py", "timeout": 3}]}
                ]
            }
        }, indent=2), encoding="utf-8")

        enterprise_vendor_hooks.install_enterprise_vendor_hooks(home=tmp_path)

        data = _read(settings)
        user_prompt = data["hooks"]["UserPromptSubmit"][0]["hooks"][0]
        assert user_prompt["command"] == "python my-linter.py"
        assert "SessionStart" in data["hooks"]

    def test_preserves_user_hooks_alongside_gator_hooks_in_same_event(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings = claude_dir / "settings.json"
        settings.write_text(json.dumps({
            "hooks": {
                "SessionStart": [
                    {"hooks": [{"type": "command", "command": "python user-tracker.py", "timeout": 2}]}
                ]
            }
        }, indent=2), encoding="utf-8")

        enterprise_vendor_hooks.install_enterprise_vendor_hooks(home=tmp_path)

        data = _read(settings)
        session_groups = data["hooks"]["SessionStart"]
        all_commands = []
        for group in session_groups:
            all_commands.extend(h["command"] for h in group["hooks"])
        assert "python user-tracker.py" in all_commands
        assert "python .gator/scripts/gator-session-open.py" in all_commands
        assert "python .gator/scripts/gator-session-start.py" in all_commands

    def test_updates_drifted_gator_hooks_in_place(self, tmp_path):
        """When existing Gator commands differ from template, re-apply."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings = claude_dir / "settings.json"
        settings.write_text(json.dumps({
            "hooks": {
                "SessionStart": [
                    {"hooks": [{"type": "command", "command": "python .gator/scripts/OLD-NAME.py", "timeout": 5}]}
                ]
            }
        }, indent=2), encoding="utf-8")

        result = enterprise_vendor_hooks.install_enterprise_vendor_hooks(home=tmp_path)
        assert result["Claude Code"] == "updated"

        data = _read(settings)
        commands = [
            h["command"]
            for group in data["hooks"]["SessionStart"]
            for h in group["hooks"]
        ]
        assert "python .gator/scripts/OLD-NAME.py" not in commands
        assert "python .gator/scripts/gator-session-open.py" in commands
        assert "python .gator/scripts/gator-session-start.py" in commands


class TestFailClosedOnBadInput:
    """Malformed / wrong-shape settings MUST NOT be clobbered."""

    def test_malformed_json_returns_unchanged_and_preserves_file(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings = claude_dir / "settings.json"
        original = "{ this is not valid json"
        settings.write_text(original, encoding="utf-8")

        result = enterprise_vendor_hooks.install_enterprise_vendor_hooks(home=tmp_path)
        assert result["Claude Code"] == "unchanged"
        assert settings.read_text(encoding="utf-8") == original

    @pytest.mark.parametrize("non_object", ["[]", '["hook"]', "42", "true", '"foo"', "null"])
    def test_non_object_root_returns_unchanged_and_preserves_file(self, tmp_path, non_object):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings = claude_dir / "settings.json"
        settings.write_text(non_object, encoding="utf-8")

        result = enterprise_vendor_hooks.install_enterprise_vendor_hooks(home=tmp_path)
        assert result["Claude Code"] == "unchanged"
        assert settings.read_text(encoding="utf-8") == non_object

    @pytest.mark.parametrize("wrong_shape_hooks", [
        '{"hooks": "bad-shape"}',
        '{"hooks": [1, 2, 3]}',
        '{"hooks": 42}',
        '{"hooks": null}',
        '{"hooks": true}',
    ])
    def test_wrong_shape_hooks_key_returns_unchanged_and_preserves_file(self, tmp_path, wrong_shape_hooks):
        """The `hooks` key is present but wrong-type — MUST fail closed.

        Codex Phase 4c-B review caught that the earlier port replaced
        the bad value with `{}` and rewrote the file — silently
        clobbering whatever the user had there. Base Gator's variant
        already fails closed correctly; the Enterprise variant now
        matches.
        """
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings = claude_dir / "settings.json"
        settings.write_text(wrong_shape_hooks, encoding="utf-8")

        result = enterprise_vendor_hooks.install_enterprise_vendor_hooks(home=tmp_path)
        assert result["Claude Code"] == "unchanged"
        assert settings.read_text(encoding="utf-8") == wrong_shape_hooks


class TestDirectoryCreation:
    def test_creates_parent_dir_when_absent(self, tmp_path):
        enterprise_vendor_hooks.install_enterprise_vendor_hooks(home=tmp_path)
        assert (tmp_path / ".claude").is_dir()
        assert (tmp_path / ".codex").is_dir()
        assert (tmp_path / ".gemini").is_dir()


class TestScopeDistinction:
    """The MACHINE scope vs base Gator's REPO scope — regression guard.

    If someone refactors to consolidate the two impls, they should preserve
    the distinct default targets. Base's install_vendor_hooks(templates_dir,
    repo_root) writes to `repo_root/.claude/...`; this variant writes to
    `home/.claude/...`. Confusing them would silently install machine-wide
    hooks when a repo-scoped install was intended (or vice versa).
    """

    def test_defaults_to_path_home_not_cwd(self, tmp_path, monkeypatch):
        """When `home` is not provided, uses Path.home() — never CWD."""
        monkeypatch.chdir(tmp_path)
        fake_home = tmp_path / "fake-home"
        fake_home.mkdir()
        monkeypatch.setattr(
            enterprise_vendor_hooks.Path, "home", classmethod(lambda cls: fake_home),
        )
        try:
            monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)
        except (TypeError, AttributeError):
            pass

        result = enterprise_vendor_hooks.install_enterprise_vendor_hooks()
        assert (fake_home / ".claude" / "settings.json").exists()
        assert not (tmp_path / ".claude" / "settings.json").exists()
        assert result["Claude Code"] == "installed"
