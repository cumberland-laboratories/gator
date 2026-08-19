"""
Tests for template-only session-hook scripts and their diagnostic helper.

Covers:
- `gator_diagnostics.log_hook_event` — write, rotate, never-raise contract.
- `gator-session-open.py` — wire-up between `ensure_git_hooks` return
  statuses and the diagnostic log.

These scripts ship ONLY in `src/gator_command/templates/gator-starter/scripts/`
(they run inside governed repos, not from the wheel), so the tests load them
via `load_script(name, search_dir=<template scripts dir>)`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from conftest import load_script

TEMPLATE_SCRIPTS_DIR = (
    Path(__file__).parent.parent
    / "src" / "gator_command" / "templates" / "gator-starter" / "scripts"
)

# Ensure the template dir is on sys.path so gator-session-open's
# `from gator_diagnostics import ...` resolves during the test.
if str(TEMPLATE_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATE_SCRIPTS_DIR))

_diag = load_script("gator_diagnostics", search_dir=TEMPLATE_SCRIPTS_DIR)


# ---------------------------------------------------------------------------
# gator_diagnostics
# ---------------------------------------------------------------------------

class TestDiagnosticsLog:
    def test_writes_a_line_on_first_call(self, tmp_path):
        gator = tmp_path / ".gator"
        gator.mkdir()
        _diag.log_hook_event(gator, "gator-session-open", "DEGRADED",
                             "gator-pre-commit.py missing")

        log = gator / "diagnostics" / "hooks.log"
        assert log.is_file()
        contents = log.read_text(encoding="utf-8")
        assert "gator-session-open DEGRADED" in contents
        assert "gator-pre-commit.py missing" in contents
        # One entry → one line
        assert contents.count("\n") == 1

    def test_uppercases_status(self, tmp_path):
        gator = tmp_path / ".gator"
        gator.mkdir()
        _diag.log_hook_event(gator, "gator-session-open", "degraded", "")
        contents = (gator / "diagnostics" / "hooks.log").read_text()
        assert " DEGRADED " in contents

    def test_strips_newlines_from_detail(self, tmp_path):
        gator = tmp_path / ".gator"
        gator.mkdir()
        _diag.log_hook_event(
            gator, "gator-session-open", "ERROR",
            "multi\nline\r\ndetail with breaks",
        )
        contents = (gator / "diagnostics" / "hooks.log").read_text()
        # Still exactly one log line
        assert contents.count("\n") == 1
        # Newlines collapsed to spaces
        assert "multi line" in contents

    def test_rotation_keeps_last_max_lines(self, tmp_path):
        gator = tmp_path / ".gator"
        gator.mkdir()
        # Pre-populate the log to just OVER the cap
        diag_dir = gator / "diagnostics"
        diag_dir.mkdir()
        log_path = diag_dir / "hooks.log"
        pre_lines = [f"seed-line-{i}" for i in range(_diag.MAX_LINES + 5)]
        log_path.write_text("\n".join(pre_lines) + "\n", encoding="utf-8")

        _diag.log_hook_event(gator, "gator-session-open", "ERROR", "new event")

        after = log_path.read_text(encoding="utf-8").splitlines()
        assert len(after) == _diag.MAX_LINES, (
            f"Expected exactly {_diag.MAX_LINES} lines after rotation, got {len(after)}"
        )
        # Newest event is the last line
        assert "new event" in after[-1]
        # Oldest seeds are gone
        assert "seed-line-0" not in after

    def test_never_raises_on_bad_gator_dir(self, tmp_path):
        # Nonexistent gator_dir with a nonexistent parent path — mkdir will
        # try to create it, but even if it fails the function must not raise.
        weird = tmp_path / "does" / "not" / "exist" / ".gator"
        # Should not raise
        _diag.log_hook_event(weird, "gator-session-open", "ERROR", "boom")

    def test_never_raises_on_permission_error(self, tmp_path, monkeypatch):
        gator = tmp_path / ".gator"
        gator.mkdir()

        def _explode(*a, **kw):
            raise PermissionError("simulated")

        monkeypatch.setattr("builtins.open", _explode)
        # Even with open() raising, the function must not raise
        _diag.log_hook_event(gator, "gator-session-open", "ERROR", "boom")


# ---------------------------------------------------------------------------
# gator-session-open wire-up
# ---------------------------------------------------------------------------

_session_open = load_script("gator-session-open", search_dir=TEMPLATE_SCRIPTS_DIR)


class TestSessionOpenDiagnosticsWiring:
    def test_degraded_return_writes_log_entry(self, tmp_path, monkeypatch):
        """When ensure_git_hooks returns a `degraded` status, session-open's
        main() logs a corresponding entry via gator_diagnostics."""
        repo = tmp_path
        gator = repo / ".gator"
        (gator / ".includes" / "scripts").mkdir(parents=True)
        (repo / ".git").mkdir()

        # Fake ensure_git_hooks to return a degraded status
        class FakeGatorInit:
            @staticmethod
            def ensure_git_hooks(repo_root, paths):
                return {
                    "status": "degraded",
                    "detail": "gator-pre-commit.py missing",
                    "adds": 0,
                    "updates": 0,
                }

        # Make import_sibling return our fake and skip the real hook-repair machinery
        monkeypatch.setattr(
            _session_open, "find_gator_dir", lambda: gator
        )
        # Stub the imports that main() does dynamically
        import gator_core  # loaded from template dir per sys.path setup at top

        monkeypatch.setattr(gator_core, "import_sibling", lambda name: FakeGatorInit)

        rc = _session_open.main()
        assert rc == 0
        log = gator / "diagnostics" / "hooks.log"
        assert log.is_file(), "Diagnostic log was not created on degraded status"
        contents = log.read_text(encoding="utf-8")
        assert "DEGRADED" in contents
        assert "gator-pre-commit.py missing" in contents

    def test_ok_return_writes_no_log_entry(self, tmp_path, monkeypatch):
        """Happy-path `ok` return must NOT create a diagnostic log entry."""
        repo = tmp_path
        gator = repo / ".gator"
        (gator / ".includes" / "scripts").mkdir(parents=True)
        (repo / ".git").mkdir()

        class FakeGatorInit:
            @staticmethod
            def ensure_git_hooks(repo_root, paths):
                return {"status": "ok", "detail": "ok", "adds": 0, "updates": 0}

        monkeypatch.setattr(_session_open, "find_gator_dir", lambda: gator)
        import gator_core
        monkeypatch.setattr(gator_core, "import_sibling", lambda name: FakeGatorInit)

        rc = _session_open.main()
        assert rc == 0
        log = gator / "diagnostics" / "hooks.log"
        # Log may exist (from a prior test) but should have NO new entry
        # for this repo since gator_dir is fresh in tmp_path — it must not
        # have been created here.
        assert not log.exists()


class TestVendorHookMigration:
    """Runtime-split Phase 3b: base-side merge logic must migrate
    pre-Phase-3 repo-script commands to the CLI route in place."""

    def test_predicate_recognizes_both_generations(self):
        from conftest import load_script
        vh_mod = load_script("gator-update")
        assert vh_mod._is_gator_hook_command("python .gator/.includes/scripts/gator-session-open.py")
        assert vh_mod._is_gator_hook_command("gator hook session-start")
        assert not vh_mod._is_gator_hook_command("python user-hook.py")

    def test_old_style_migrates_in_place_preserving_user_hooks(self, tmp_path):
        import json
        from conftest import load_script
        upd = load_script("gator-update")
        settings = tmp_path / "settings.json"
        settings.write_text(json.dumps({
            "hooks": {"SessionStart": [{"hooks": [
                {"type": "command",
                 "command": "python .gator/.includes/scripts/gator-session-open.py",
                 "timeout": 5},
                {"type": "command", "command": "python user-hook.py"},
            ]}]}
        }), encoding="utf-8")
        template = tmp_path / "template.json"
        template.write_text(json.dumps({
            "hooks": {"SessionStart": [{"hooks": [
                {"type": "command", "command": "gator hook session-open", "timeout": 5},
                {"type": "command", "command": "gator hook session-start", "timeout": 5},
            ]}]}
        }), encoding="utf-8")
        result = upd.merge_hooks_into_settings(settings, template)
        assert result == "update"
        data = json.loads(settings.read_text(encoding="utf-8"))
        groups = data["hooks"]["SessionStart"]
        assert len(groups) == 1, "migrate in place, never duplicate"
        cmds = [h["command"] for h in groups[0]["hooks"]]
        assert "gator hook session-open" in cmds
        assert "gator hook session-start" in cmds
        assert "python user-hook.py" in cmds
        assert not any(".gator/" in c for c in cmds if "user-hook" not in c)
