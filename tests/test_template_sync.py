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


# ---------------------------------------------------------------------------
# Layer 3 — #78 transient migration: predicted, exact, reported once
# ---------------------------------------------------------------------------

_EPHEMERA = (".gator/status.json", ".gator/whiteboard.md",
             ".gator/commit_draft.md", ".gator/commit_issues.md")


def _git_out(repo, *args):
    return subprocess.run(["git", *args], cwd=str(repo), capture_output=True,
                          text=True, encoding="utf-8", errors="replace").stdout


def _legacy_governed_repo(tmp_path):
    repo = _governed_repo(tmp_path)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=str(repo), check=True)
    for rel in _EPHEMERA:
        (repo / rel).write_text("legacy\n", encoding="utf-8")
    subprocess.run(["git", "add", "-f", "-A"], cwd=str(repo), check=True)
    subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "commit", "-q",
                    "--no-verify", "-m", "legacy"], cwd=str(repo), check=True)
    return repo


def _update(tmp_path, script, repo, *flags, source=True):
    """`source=False` relies on the product source an earlier call bound;
    a `--source` rebind prints a notice before any JSON output."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home),
               PYTHONIOENCODING="utf-8")
    src = ["--source", str(PACKAGE_ROOT)] if source else []
    return subprocess.run(
        [sys.executable, str(script), "--path", str(repo), *src, *flags],
        cwd=str(repo), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180,
    )


class TestTransientMigration:
    """The installed `gator update` runs the package copy, which imports
    gatorize. The template copy has no gatorize sibling and degrades to no
    prediction and no untracking, exactly as before #78."""

    update_script = PACKAGE_UPDATE

    def test_template_copy_degrades_quietly(self, tmp_path):
        repo = _legacy_governed_repo(tmp_path)
        r = _update(tmp_path, TEMPLATE_UPDATE, repo, "--result-json")
        assert r.returncode == 0, r.stdout + r.stderr
        assert json.loads(r.stdout)["transient_untracked"] is None
        assert ".gator/status.json" in _git_out(repo, "ls-files").splitlines()

    def test_dry_run_and_json_predict_without_changing(self, tmp_path):
        update_script = self.update_script
        repo = _legacy_governed_repo(tmp_path)
        index = _git_out(repo, "ls-files", "--stage")
        r = _update(tmp_path, update_script, repo, "--dry-run")
        assert r.returncode == 0, r.stdout + r.stderr
        assert "Hook-ephemera paths to remove from the Git index (4):" in r.stdout
        for rel in _EPHEMERA:
            assert f"    - {rel}" in r.stdout
        r = _update(tmp_path, update_script, repo, "--json", source=False)
        assert r.returncode == 0, r.stdout + r.stderr
        plan = json.loads(r.stdout)
        assert plan["transient_untrack"] == {"paths": list(_EPHEMERA), "count": 4}
        assert plan["summary"]["transient_untrack"] == 4
        assert _git_out(repo, "ls-files", "--stage") == index

    def test_execution_reports_then_is_quiet(self, tmp_path):
        update_script = self.update_script
        repo = _legacy_governed_repo(tmp_path)
        r = _update(tmp_path, update_script, repo, "--result-json")
        assert r.returncode == 0, r.stdout + r.stderr
        result = json.loads(r.stdout)
        assert result["schema"] == "gator-update-result-v1"
        assert result["exit_code"] == 0
        t = result["transient_untracked"]
        assert t["paths"] == list(_EPHEMERA) and t["count"] == 4
        assert t["message"].startswith("Gator removed 4 hook-ephemera paths from the Git index.")
        assert t["message"] in result["output"]
        tracked = _git_out(repo, "ls-files").splitlines()
        staged = _git_out(repo, "diff", "--cached", "--name-status").splitlines()
        for rel in _EPHEMERA:
            assert rel not in tracked and (repo / rel).is_file()
            assert f"D\t{rel}" in staged
        # Second run: nothing to untrack, nothing reported.
        r = _update(tmp_path, update_script, repo)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "hook-ephemera" not in r.stdout
        r = _update(tmp_path, update_script, repo, "--result-json")
        assert json.loads(r.stdout)["transient_untracked"] is None

    @pytest.mark.parametrize("update_script", [PACKAGE_UPDATE, TEMPLATE_UPDATE],
                             ids=["package", "template"])
    def test_result_json_rejects_plan_modes(self, tmp_path, update_script):
        repo = _governed_repo(tmp_path)
        r = _update(tmp_path, update_script, repo, "--result-json", "--dry-run")
        assert r.returncode == 2 and "--result-json executes" in r.stderr
