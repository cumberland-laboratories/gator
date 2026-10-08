"""
Package/template sync backstop for gator-update.py.

Two layers of assertion:

  1. JSON-schema parity: both copies emit `"schema": "gator-update-v1"` and
     keep the `entry_point_actions` key (top level and summary) for v1
     compatibility. It is always empty: Gator no longer manages native
     agent files (gator-native entry point, 2026-10-08).

  2. Native-file neutrality: running either copy's `gator update` against a
     governed repository leaves CLAUDE.md / AGENTS.md / GEMINI.md and
     `*.local.md` byte-for-byte unchanged, with no backup siblings.

The retired Stage 4b layers (entry-point plan/execute parity and the AST
equivalence of the template's inlined managed-block helpers) went away with
the code they pinned.
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent
PACKAGE_ROOT = REPO_ROOT / "src" / "gator_command"
PACKAGE_UPDATE = PACKAGE_ROOT / "scripts" / "gator-update.py"
TEMPLATE_UPDATE = PACKAGE_ROOT / "templates" / "gator-starter" / "scripts" / "gator-update.py"


def _load_module(path, module_name):
    """Load a Python file as a fresh module, bypassing any cached import."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def package_update():
    """Load the PACKAGE copy of gator-update.py."""
    scripts_dir = str(PACKAGE_UPDATE.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    return _load_module(PACKAGE_UPDATE, "package_gator_update")


@pytest.fixture
def template_update():
    """Load the TEMPLATE copy of gator-update.py."""
    return _load_module(TEMPLATE_UPDATE, "template_gator_update")


# ---------------------------------------------------------------------------
# Layer 1 — JSON schema parity
# ---------------------------------------------------------------------------

class TestJSONSchemaParity:
    """Both copies emit `"schema": "gator-update-v1"` and an always-empty
    `entry_point_actions` (kept for v1 compatibility)."""

    @pytest.mark.parametrize("copy", ["package_update", "template_update"])
    def test_json_shape_keeps_empty_entry_point_actions(self, tmp_path, request, copy, capsys):
        mod = request.getfixturevalue(copy)
        templates_dir = tmp_path / "t"
        templates_dir.mkdir()
        mod.print_json_plan(plan=[], templates_dir=templates_dir, hooks=[])
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["schema"] == "gator-update-v1"
        assert parsed["entry_point_actions"] == []
        assert parsed["summary"]["entry_point_actions"] == 0

    def test_both_copies_produce_identical_top_level_keys(
        self, tmp_path, package_update, template_update, capsys
    ):
        templates_dir = tmp_path / "t"
        templates_dir.mkdir()
        package_update.print_json_plan(plan=[], templates_dir=templates_dir, hooks=[])
        pkg = json.loads(capsys.readouterr().out)
        template_update.print_json_plan(plan=[], templates_dir=templates_dir, hooks=[])
        tpl = json.loads(capsys.readouterr().out)
        assert set(pkg.keys()) == set(tpl.keys())
        assert set(pkg["summary"].keys()) == set(tpl["summary"].keys())


# ---------------------------------------------------------------------------
# Layer 2 — native agent files are repository-owned
# ---------------------------------------------------------------------------

# Every state the retired Stage 4b refresh used to act on (clean/modified
# sentinel block, legacy fingerprint, absent) plus a companion file.
_NATIVE_BYTES = {
    "CLAUDE.md": b"# Claude Code Entry Point\r\n\r\n<!-- GATOR:BEGIN -->\r\nstale block\r\n<!-- GATOR:END -->\r\n\r\nteam text\r\n",
    "AGENTS.md": b"# Codex Entry Point\n\n# --- Gator Navigation Coding ---\nRead .gator/constitution.md\n",
    "CLAUDE.local.md": b"personal notes\n",
}


def _governed_repo(tmp_path):
    gatorize = _load_module(PACKAGE_ROOT / "scripts" / "gatorize.py", "sync_gatorize")
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True, timeout=10)
    gatorize.action_install_gator(repo)
    for name, data in _NATIVE_BYTES.items():
        (repo / name).write_bytes(data)
    return repo


class TestUpdateLeavesNativeFilesUntouched:
    """`gator update` (either copy) never reads, creates, refreshes, backs up
    or edits native agent files. GEMINI.md is absent and must stay absent
    (the retired refresh would have created it)."""

    @pytest.mark.parametrize("update_script", [PACKAGE_UPDATE, TEMPLATE_UPDATE],
                             ids=["package", "template"])
    def test_update_preserves_native_bytes(self, tmp_path, update_script):
        repo = _governed_repo(tmp_path)
        home = tmp_path / "home"
        home.mkdir()
        env = dict(os.environ, HOME=str(home), USERPROFILE=str(home),
                   PYTHONIOENCODING="utf-8")
        result = subprocess.run(
            [sys.executable, str(update_script), "--path", str(repo),
             "--source", str(PACKAGE_ROOT)],
            cwd=str(repo), env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        for name, data in _NATIVE_BYTES.items():
            assert (repo / name).read_bytes() == data, name
        assert not (repo / "GEMINI.md").exists()
        siblings = sorted(p.name for p in repo.iterdir()
                          if p.name.endswith((".pre-gator-update", "_ROLLBACK.md")))
        assert siblings == []
        assert "Entry-point" not in result.stdout
