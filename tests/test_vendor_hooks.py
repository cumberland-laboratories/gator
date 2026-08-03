"""Tests for vendor hook config merge and propagation."""

import json
from pathlib import Path

import pytest

import sys
import importlib.util

# Import from gator-update.py
_update_path = Path(__file__).resolve().parent.parent / "src" / "gator_command" / "scripts" / "gator-update.py"
_spec = importlib.util.spec_from_file_location("gator_update", _update_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

merge_hooks_into_settings = _mod.merge_hooks_into_settings
install_vendor_hooks = _mod.install_vendor_hooks
VENDOR_HOOK_CONFIGS = _mod.VENDOR_HOOK_CONFIGS

# Import from gatorize.py for parity testing
_gatorize_path = Path(__file__).resolve().parent.parent / "src" / "gator_command" / "scripts" / "gatorize.py"
_gz_spec = importlib.util.spec_from_file_location("gatorize", _gatorize_path)
_gz_mod = importlib.util.module_from_spec(_gz_spec)
_gz_spec.loader.exec_module(_gz_mod)

merge_hooks_gatorize = _gz_mod.merge_hooks_into_settings


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _make_hooks_template(tmp_path, name="claude-settings.json"):
    """Create a hooks template file matching the current two-hook layout."""
    template = tmp_path / "templates" / name
    _write_json(template, {
        "hooks": {
            "SessionStart": [{
                "hooks": [
                    {
                        "type": "command",
                        "command": "python .gator/scripts/gator-session-open.py",
                        "timeout": 5
                    },
                    {
                        "type": "command",
                        "command": "python .gator/scripts/gator-session-start.py",
                        "timeout": 5
                    }
                ]
            }]
        }
    })
    return template


class TestMergeHooksIntoSettings:
    def test_creates_new_file(self, tmp_path):
        template = _make_hooks_template(tmp_path)
        dest = tmp_path / ".claude" / "settings.json"

        result = merge_hooks_into_settings(dest, template)

        assert result == "add"
        assert dest.exists()
        data = _read_json(dest)
        assert "hooks" in data
        assert "SessionStart" in data["hooks"]

    def test_merges_into_existing_without_hooks(self, tmp_path):
        template = _make_hooks_template(tmp_path)
        dest = tmp_path / ".claude" / "settings.json"
        _write_json(dest, {
            "permissions": {"allow": ["Bash(git:*)"]},
            "env": {"MY_KEY": "secret"}
        })

        result = merge_hooks_into_settings(dest, template)

        assert result == "update"
        data = _read_json(dest)
        # Hooks added
        assert "SessionStart" in data["hooks"]
        # Existing content preserved
        assert data["permissions"]["allow"] == ["Bash(git:*)"]
        assert data["env"]["MY_KEY"] == "secret"

    def test_skips_when_gator_hooks_already_present(self, tmp_path):
        template = _make_hooks_template(tmp_path)
        dest = tmp_path / ".claude" / "settings.json"
        _write_json(dest, {
            "hooks": {
                "SessionStart": [{
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python .gator/scripts/gator-session-open.py",
                            "timeout": 5
                        },
                        {
                            "type": "command",
                            "command": "python .gator/scripts/gator-session-start.py",
                            "timeout": 5
                        }
                    ]
                }]
            }
        })

        result = merge_hooks_into_settings(dest, template)

        assert result == "unchanged"

    def test_appends_to_existing_hooks_for_same_event(self, tmp_path):
        template = _make_hooks_template(tmp_path)
        dest = tmp_path / ".claude" / "settings.json"
        _write_json(dest, {
            "hooks": {
                "SessionStart": [{
                    "hooks": [{
                        "type": "command",
                        "command": "my-custom-hook.sh",
                        "timeout": 10
                    }]
                }]
            }
        })

        result = merge_hooks_into_settings(dest, template)

        assert result == "update"
        data = _read_json(dest)
        groups = data["hooks"]["SessionStart"]
        assert len(groups) == 2
        # Custom hook preserved
        assert "my-custom-hook.sh" in json.dumps(groups[0])
        # Gator hooks appended (both session-open and session-start)
        gator_group_json = json.dumps(groups[1])
        assert "gator-session-open.py" in gator_group_json
        assert "gator-session-start.py" in gator_group_json

    def test_adds_new_event_to_existing_hooks(self, tmp_path):
        template = _make_hooks_template(tmp_path)
        dest = tmp_path / ".claude" / "settings.json"
        _write_json(dest, {
            "hooks": {
                "PreToolUse": [{
                    "hooks": [{"type": "command", "command": "lint.sh"}]
                }]
            }
        })

        result = merge_hooks_into_settings(dest, template)

        assert result == "update"
        data = _read_json(dest)
        assert "PreToolUse" in data["hooks"]
        assert "SessionStart" in data["hooks"]

    def test_skips_corrupt_json(self, tmp_path):
        template = _make_hooks_template(tmp_path)
        dest = tmp_path / ".claude" / "settings.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("{not valid", encoding="utf-8")

        result = merge_hooks_into_settings(dest, template)

        assert result == "unchanged"
        # File not clobbered
        assert dest.read_text(encoding="utf-8") == "{not valid"

    def test_skips_non_dict_json(self, tmp_path):
        template = _make_hooks_template(tmp_path)
        dest = tmp_path / ".claude" / "settings.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text('"just a string"', encoding="utf-8")

        result = merge_hooks_into_settings(dest, template)

        assert result == "unchanged"

    def test_skips_hooks_as_list(self, tmp_path):
        """User has hooks as a list instead of dict — don't crash."""
        template = _make_hooks_template(tmp_path)
        dest = tmp_path / ".claude" / "settings.json"
        _write_json(dest, {"hooks": []})

        result = merge_hooks_into_settings(dest, template)

        assert result == "unchanged"
        # File not corrupted
        assert _read_json(dest) == {"hooks": []}

    def test_skips_event_value_not_list(self, tmp_path):
        """User has SessionStart as a dict instead of list — skip that event."""
        template = _make_hooks_template(tmp_path)
        dest = tmp_path / ".claude" / "settings.json"
        _write_json(dest, {"hooks": {"SessionStart": {"bad": "shape"}}})

        result = merge_hooks_into_settings(dest, template)

        assert result == "unchanged"

    def test_handles_hooks_as_string(self, tmp_path):
        """hooks key is a string — don't crash."""
        template = _make_hooks_template(tmp_path)
        dest = tmp_path / ".claude" / "settings.json"
        _write_json(dest, {"hooks": "not a dict"})

        result = merge_hooks_into_settings(dest, template)

        assert result == "unchanged"


class TestMergeHooksGatorizeParity:
    """Verify gatorize.py's copy behaves identically on key cases."""

    def test_creates_new_file(self, tmp_path):
        template = _make_hooks_template(tmp_path)
        dest = tmp_path / ".claude" / "settings.json"
        assert merge_hooks_gatorize(dest, template) == "add"
        assert "SessionStart" in _read_json(dest)["hooks"]

    def test_preserves_existing_content(self, tmp_path):
        template = _make_hooks_template(tmp_path)
        dest = tmp_path / ".claude" / "settings.json"
        _write_json(dest, {"env": {"KEY": "val"}})
        assert merge_hooks_gatorize(dest, template) == "update"
        data = _read_json(dest)
        assert data["env"]["KEY"] == "val"
        assert "SessionStart" in data["hooks"]

    def test_skips_hooks_as_list(self, tmp_path):
        template = _make_hooks_template(tmp_path)
        dest = tmp_path / ".claude" / "settings.json"
        _write_json(dest, {"hooks": []})
        assert merge_hooks_gatorize(dest, template) == "unchanged"

    def test_skips_event_value_not_list(self, tmp_path):
        template = _make_hooks_template(tmp_path)
        dest = tmp_path / ".claude" / "settings.json"
        _write_json(dest, {"hooks": {"SessionStart": "bad"}})
        assert merge_hooks_gatorize(dest, template) == "unchanged"


class TestUpgradeFromSingleHook:
    """Verify that repos with the old single-hook config (session-start only)
    get the new session-open hook added via merge."""

    def test_gator_update_adds_session_open_to_existing_session_start(self, tmp_path):
        """Core upgrade path: existing settings have session-start, template
        now has both session-open and session-start. Merge must add session-open."""
        template = _make_hooks_template(tmp_path)
        dest = tmp_path / ".claude" / "settings.json"
        # Simulate old installed state: only session-start
        _write_json(dest, {
            "hooks": {
                "SessionStart": [{
                    "hooks": [{
                        "type": "command",
                        "command": "python .gator/scripts/gator-session-start.py",
                        "timeout": 5
                    }]
                }]
            }
        })

        result = merge_hooks_into_settings(dest, template)

        assert result == "update"
        data = _read_json(dest)
        hooks_list = data["hooks"]["SessionStart"][0]["hooks"]
        commands = [h["command"] for h in hooks_list]
        assert "python .gator/scripts/gator-session-open.py" in commands
        assert "python .gator/scripts/gator-session-start.py" in commands

    def test_gatorize_adds_session_open_to_existing_session_start(self, tmp_path):
        """Same upgrade path through gatorize.py's merge."""
        template = _make_hooks_template(tmp_path)
        dest = tmp_path / ".claude" / "settings.json"
        _write_json(dest, {
            "hooks": {
                "SessionStart": [{
                    "hooks": [{
                        "type": "command",
                        "command": "python .gator/scripts/gator-session-start.py",
                        "timeout": 5
                    }]
                }]
            }
        })

        result = merge_hooks_gatorize(dest, template)

        assert result == "update"
        data = _read_json(dest)
        hooks_list = data["hooks"]["SessionStart"][0]["hooks"]
        commands = [h["command"] for h in hooks_list]
        assert "python .gator/scripts/gator-session-open.py" in commands
        assert "python .gator/scripts/gator-session-start.py" in commands

    def test_idempotent_after_upgrade(self, tmp_path):
        """After upgrade, a second merge returns unchanged."""
        template = _make_hooks_template(tmp_path)
        dest = tmp_path / ".claude" / "settings.json"
        _write_json(dest, {
            "hooks": {
                "SessionStart": [{
                    "hooks": [{
                        "type": "command",
                        "command": "python .gator/scripts/gator-session-start.py",
                        "timeout": 5
                    }]
                }]
            }
        })

        assert merge_hooks_into_settings(dest, template) == "update"
        assert merge_hooks_into_settings(dest, template) == "unchanged"

    def test_preserves_user_hooks_during_upgrade(self, tmp_path):
        """User's custom hooks are preserved when adding session-open."""
        template = _make_hooks_template(tmp_path)
        dest = tmp_path / ".claude" / "settings.json"
        _write_json(dest, {
            "hooks": {
                "SessionStart": [
                    {
                        "hooks": [{
                            "type": "command",
                            "command": "my-custom-hook.sh",
                            "timeout": 10
                        }]
                    },
                    {
                        "hooks": [{
                            "type": "command",
                            "command": "python .gator/scripts/gator-session-start.py",
                            "timeout": 5
                        }]
                    }
                ]
            }
        })

        result = merge_hooks_into_settings(dest, template)

        assert result == "update"
        data = _read_json(dest)
        groups = data["hooks"]["SessionStart"]
        # User hook group preserved
        assert "my-custom-hook.sh" in json.dumps(groups[0])
        # Gator group now has both hooks
        gator_group = groups[1]
        commands = [h["command"] for h in gator_group["hooks"]]
        assert "python .gator/scripts/gator-session-open.py" in commands
        assert "python .gator/scripts/gator-session-start.py" in commands


    def test_preserves_user_hooks_mixed_into_gator_group(self, tmp_path):
        """User hooks mixed into the Gator group are preserved during upgrade."""
        template = _make_hooks_template(tmp_path)
        dest = tmp_path / ".claude" / "settings.json"
        # User added a custom hook inside the same group as Gator hooks
        _write_json(dest, {
            "hooks": {
                "SessionStart": [{
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python .gator/scripts/gator-session-start.py",
                            "timeout": 5
                        },
                        {
                            "type": "command",
                            "command": "my-linter.sh",
                            "timeout": 3
                        }
                    ]
                }]
            }
        })

        result = merge_hooks_into_settings(dest, template)

        assert result == "update"
        data = _read_json(dest)
        hooks_list = data["hooks"]["SessionStart"][0]["hooks"]
        commands = [h["command"] for h in hooks_list]
        # All Gator hooks present
        assert "python .gator/scripts/gator-session-open.py" in commands
        assert "python .gator/scripts/gator-session-start.py" in commands
        # User hook preserved
        assert "my-linter.sh" in commands

    def test_mixed_group_user_hooks_after_gator_hooks(self, tmp_path):
        """User hooks appear after Gator hooks in rebuilt group."""
        template = _make_hooks_template(tmp_path)
        dest = tmp_path / ".claude" / "settings.json"
        _write_json(dest, {
            "hooks": {
                "SessionStart": [{
                    "hooks": [
                        {
                            "type": "command",
                            "command": "my-setup.sh",
                            "timeout": 3
                        },
                        {
                            "type": "command",
                            "command": "python .gator/scripts/gator-session-start.py",
                            "timeout": 5
                        }
                    ]
                }]
            }
        })

        result = merge_hooks_into_settings(dest, template)

        assert result == "update"
        data = _read_json(dest)
        hooks_list = data["hooks"]["SessionStart"][0]["hooks"]
        commands = [h["command"] for h in hooks_list]
        # Gator hooks come first (from template), user hook appended
        gator_end = commands.index("python .gator/scripts/gator-session-start.py")
        user_idx = commands.index("my-setup.sh")
        assert user_idx > gator_end


class TestTemplateHookEntries:
    """Verify the canonical vendor hook templates include both session-open and session-start."""

    TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "src" / "gator_command" / "templates" / "gator-starter" / "vendor-hooks"

    @pytest.mark.parametrize("filename", [
        "claude-settings.json",
        "codex-hooks.json",
        "gemini-settings.json",
    ])
    def test_template_has_session_open_and_session_start(self, filename):
        """Vendor-hook templates ship v2 layout paths (`.gator/.includes/scripts/…`).
        Reverting to v1 (`.gator/scripts/…`) silently breaks every v2 fleet repo
        because merge_hooks_into_settings compares template-vs-existing and only
        rewrites on mismatch. See scripts-installer.md::install_vendor_hooks
        tripwire, and 2026-08-03 fix commit `a532851`."""
        template = self.TEMPLATE_DIR / filename
        data = _read_json(template)
        hooks_list = data["hooks"]["SessionStart"][0]["hooks"]
        commands = [h["command"] for h in hooks_list]
        assert "python .gator/.includes/scripts/gator-session-open.py" in commands
        assert "python .gator/.includes/scripts/gator-session-start.py" in commands
        assert len(hooks_list) == 2

    @pytest.mark.parametrize("filename", [
        "claude-settings.json",
        "codex-hooks.json",
        "gemini-settings.json",
    ])
    def test_session_open_runs_before_session_start(self, filename):
        """session-open should be listed before session-start."""
        template = self.TEMPLATE_DIR / filename
        data = _read_json(template)
        hooks_list = data["hooks"]["SessionStart"][0]["hooks"]
        commands = [h["command"] for h in hooks_list]
        open_idx = commands.index(
            "python .gator/.includes/scripts/gator-session-open.py"
        )
        start_idx = commands.index(
            "python .gator/.includes/scripts/gator-session-start.py"
        )
        assert open_idx < start_idx

    def test_marker_detection_works_with_both_hooks(self):
        """GATOR_HOOK_MARKER ('gator-session-start.py') still detects Gator hooks
        when both session-open and session-start are present."""
        import json as json_mod
        marker = "gator-session-start.py"
        for filename in ["claude-settings.json", "codex-hooks.json", "gemini-settings.json"]:
            data = _read_json(self.TEMPLATE_DIR / filename)
            serialized = json_mod.dumps(data)
            assert marker in serialized, f"Marker not found in {filename}"


class TestInstallVendorHooks:
    def test_installs_all_three_vendors(self, tmp_path):
        templates_dir = tmp_path / "templates"

        # Create template files for all vendors
        for template_file, _, _ in VENDOR_HOOK_CONFIGS:
            _write_json(templates_dir / template_file, {
                "hooks": {
                    "SessionStart": [{
                        "hooks": [{
                            "type": "command",
                            "command": "python .gator/scripts/gator-session-start.py"
                        }]
                    }]
                }
            })

        repo = tmp_path / "repo"
        repo.mkdir()

        changed = install_vendor_hooks(templates_dir, repo)

        assert changed == 3
        assert (repo / ".claude" / "settings.json").exists()
        assert (repo / ".codex" / "hooks.json").exists()
        assert (repo / ".gemini" / "settings.json").exists()

    def test_idempotent(self, tmp_path):
        templates_dir = tmp_path / "templates"
        for template_file, _, _ in VENDOR_HOOK_CONFIGS:
            _write_json(templates_dir / template_file, {
                "hooks": {
                    "SessionStart": [{
                        "hooks": [{
                            "type": "command",
                            "command": "python .gator/scripts/gator-session-start.py"
                        }]
                    }]
                }
            })

        repo = tmp_path / "repo"
        repo.mkdir()

        # First install
        assert install_vendor_hooks(templates_dir, repo) == 3
        # Second install — no changes
        assert install_vendor_hooks(templates_dir, repo) == 0

    def test_skips_missing_templates(self, tmp_path):
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        repo = tmp_path / "repo"
        repo.mkdir()

        changed = install_vendor_hooks(templates_dir, repo)
        assert changed == 0
