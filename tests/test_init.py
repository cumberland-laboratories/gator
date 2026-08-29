"""
Tests for gator-init.py — per-repo boot sequence.

Tests the detection and counting functions that produce the
branded status display at session open.
"""

import json
import os
from pathlib import Path

import pytest

from conftest import load_script

init = load_script("gator-init")
update = load_script("gator-update")

import gator_layout


class TestCountConstitutionRules:
    def test_counts_rules(self, mock_gator_repo):
        """Counts numbered bold items, dash-bold items, and standalone imperatives."""
        repo_root, _ = mock_gator_repo
        paths = gator_layout.get_gator_paths(repo_root)
        count = init.count_constitution_rules(paths)
        # The fixture has:
        #   1. **Before changing code**: ...  (numbered bold)
        #   2. **After changing code**: ...   (numbered bold)
        #   - **BRANCHING**: ...              (dash bold uppercase)
        #   - **COMMITS**: ...                (dash bold uppercase)
        #   **The agent always asks...**      (standalone bold imperative)
        assert count == 5

    def test_missing_constitution(self, tmp_path):
        """Returns 0 when constitution.md doesn't exist."""
        (tmp_path / ".gator").mkdir()
        paths = gator_layout.get_gator_paths(tmp_path)
        assert init.count_constitution_rules(paths) == 0


class TestDetectEnforcer:
    def test_ready(self, mock_gator_repo):
        """Both enforcer files present → 'ready'."""
        repo_root, _ = mock_gator_repo
        paths = gator_layout.get_gator_paths(repo_root)
        assert init.detect_enforcer(paths) == "ready"

    def test_partial(self, mock_gator_repo):
        """Only one enforcer file → 'partial'."""
        repo_root, gator_dir = mock_gator_repo
        (gator_dir / "scripts" / "enforcer-review.py").unlink()
        paths = gator_layout.get_gator_paths(repo_root)
        assert init.detect_enforcer(paths) == "partial"

    def test_not_configured(self, tmp_path):
        """No enforcer files → 'not configured'."""
        gator = tmp_path / ".gator"
        gator.mkdir()
        (gator / "scripts").mkdir()
        paths = gator_layout.get_gator_paths(tmp_path)
        assert init.detect_enforcer(paths) == "not configured"


class TestCountCharters:
    def test_counts_charters_and_functions(self, mock_gator_repo):
        """Counts charter files and ### function() entries."""
        repo_root, _ = mock_gator_repo
        paths = gator_layout.get_gator_paths(repo_root)
        charter_count, func_count, coverage = init.count_charters(paths)
        assert charter_count == 1  # core.md only (README.md and _template.md excluded)
        assert func_count == 3     # parse_config, validate_input, process_data

    def test_no_charters_dir(self, tmp_path):
        """Returns zeros when charters/ doesn't exist."""
        (tmp_path / ".gator").mkdir()
        paths = gator_layout.get_gator_paths(tmp_path)
        count, funcs, coverage = init.count_charters(paths)
        assert count == 0
        assert funcs == 0


class TestPrintJson:
    def test_json_structure(self, mock_gator_repo, capsys):
        """JSON output contains expected top-level keys."""
        repo_root, _ = mock_gator_repo
        paths = gator_layout.get_gator_paths(repo_root)
        hook_status = {"status": "ok", "detail": "ok", "adds": 0, "updates": 0}
        registry_status = {"status": "already_registered", "detail": "already registered"}
        init.print_json(repo_root, paths, hook_status, registry_status)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "version" in data
        assert "repo" in data
        assert "constitution_rules" in data
        assert "charters" in data
        assert "working_set" in data
        assert "enforcer" in data
        assert "hooks" in data
        assert "dashboard_registry" in data
        assert data["constitution_rules"] == 5
        assert data["charters"]["modules"] == 1
        assert data["charters"]["functions_mapped"] == 3
        assert data["enforcer"] == "ready"
        assert data["hooks"]["status"] == "ok"
        assert data["dashboard_registry"]["status"] == "already_registered"


class TestEnsureGitHooks:
    def test_repairs_missing_and_stale_hooks(self, mock_gator_repo):
        """Session start repairs missing and stale git hooks."""
        repo_root, _ = mock_gator_repo
        paths = gator_layout.get_gator_paths(repo_root)

        status = init.ensure_git_hooks(repo_root, paths)

        if os.name == "nt":
            # Windows: managed dir is .git/gator-hooks/ (empty), all 3 are adds
            assert status["status"] == "installed"
            assert status["adds"] == 3
        else:
            # Unix: managed dir is .git/hooks/, stale pre-commit → update, 2 adds
            assert status["status"] == "refreshed"
            assert status["updates"] >= 1
            assert status["adds"] >= 1

        hook_dir = update.get_managed_hook_dir(repo_root)
        for hook_name in ("pre-commit", "commit-msg", "post-commit"):
            hook_file = hook_dir / hook_name
            assert hook_file.exists()
            content = hook_file.read_text(encoding="utf-8")
            assert ".gator/scripts/gator-pre-commit.py" in content

    def test_second_run_reports_ok(self, mock_gator_repo):
        """A repo with healthy hooks is a no-op on the next init run."""
        repo_root, _ = mock_gator_repo
        paths = gator_layout.get_gator_paths(repo_root)

        first = init.ensure_git_hooks(repo_root, paths)
        assert first["status"] == ("installed" if os.name == "nt" else "refreshed")

        second = init.ensure_git_hooks(repo_root, paths)
        assert second["status"] == "ok"
        assert second["adds"] == 0
        assert second["updates"] == 0

    def test_missing_pre_commit_script_reports_degraded(self, mock_gator_repo):
        """Missing gator-pre-commit.py is degraded, not false-green ok."""
        repo_root, gator_dir = mock_gator_repo
        (gator_dir / "scripts" / "gator-pre-commit.py").unlink()
        paths = gator_layout.get_gator_paths(repo_root)

        status = init.ensure_git_hooks(repo_root, paths)
        assert status["status"] == "degraded"
        assert "missing" in status["detail"]

    def test_unresolvable_shebang_reports_degraded_not_ok(self, mock_gator_repo):
        """2026-08-28 whiteboard finding: `_hook_shebang()` raising
        HookShebangUnresolvable must NOT collapse into false-green `ok`
        at session-open on exactly the machines the shebang fix
        protects. plan_hook_updates() swallows the exception and
        returns [] (which is indistinguishable from "no changes
        needed"), so ensure_git_hooks() must probe the resolver
        directly and surface a degraded status.

        Patches init.import_sibling because ensure_git_hooks resolves
        gator-update via a fresh import_sibling() call (no sys.modules
        caching) — patching the test's module-level `update` reference
        wouldn't reach the copy ensure_git_hooks actually uses."""
        from unittest.mock import patch

        repo_root, gator_dir = mock_gator_repo
        paths = gator_layout.get_gator_paths(repo_root)

        real_update = init.import_sibling("gator-update")

        def _raising_shebang():
            raise real_update.HookShebangUnresolvable("no launcher for test")

        real_update._hook_shebang = _raising_shebang

        with patch.object(init, "import_sibling", return_value=real_update):
            status = init.ensure_git_hooks(repo_root, paths)

        assert status["status"] == "degraded", (
            f"session-open must surface shebang refusal, got {status!r}"
        )
        assert "shebang" in status["detail"].lower()
        assert "no launcher for test" in status["detail"]
        assert status["adds"] == 0
        assert status["updates"] == 0


# ---------------------------------------------------------------------------
# Stage 5 — constitution drift suffix in the boot output
# ---------------------------------------------------------------------------

TEMPLATES_DIR = Path(__file__).parent.parent / "src" / "gator_command" / "templates" / "gator-starter"


def _governed_repo_with_pristine_constitution(tmp_path):
    """Fixture: governed repo whose constitution matches the shipped template
    baseline byte-for-byte, wired up so resolve_template_source() finds it."""
    import json as _json
    repo = tmp_path / "repo"
    gator = repo / ".gator"
    gator.mkdir(parents=True)
    (gator / "product-source.json").write_text(_json.dumps({
        "gator_root": str(TEMPLATES_DIR.parent.parent),
        "template_dir": "templates/gator-starter",
        "installed": "2026-07-29",
        "updated": "2026-07-29",
    }), encoding="utf-8")
    (gator / "constitution.md").write_bytes((TEMPLATES_DIR / "constitution.md").read_bytes())
    return repo


class TestConstitutionDriftSuffix:
    """Helper: `_constitution_drift_suffix(repo_root)` returns a string
    suffix (or empty) for `print_boot_sequence()` to append to the
    constitution status line. Best-effort — must never raise."""

    def test_clean_returns_empty_suffix(self, tmp_path):
        repo = _governed_repo_with_pristine_constitution(tmp_path)
        suffix = init._constitution_drift_suffix(repo)
        assert suffix == ""

    def test_modified_returns_drift_suffix(self, tmp_path):
        repo = _governed_repo_with_pristine_constitution(tmp_path)
        (repo / ".gator" / "constitution.md").write_text("locally edited", encoding="utf-8")
        suffix = init._constitution_drift_suffix(repo)
        assert suffix == " · modified from baseline"

    def test_source_repo_returns_empty_suffix(self, tmp_path):
        """Source-repo exemption is handled inside check_constitution_drift;
        _constitution_drift_suffix renders 'source-repo-exempt' as no suffix."""
        (tmp_path / "gator-command").mkdir()
        (tmp_path / "gator-command" / "mission.md").write_text("x")
        (tmp_path / "constitution.md").write_text("y")
        (tmp_path / ".gator").mkdir()
        suffix = init._constitution_drift_suffix(tmp_path)
        assert suffix == ""

    def test_no_baseline_returns_empty_suffix(self, tmp_path):
        """When product-source.json is missing, drift check returns
        'no-baseline' — no suffix (not a warning)."""
        repo = tmp_path / "repo"
        (repo / ".gator").mkdir(parents=True)
        suffix = init._constitution_drift_suffix(repo)
        assert suffix == ""

    def test_never_raises_on_missing_gator_dir(self, tmp_path):
        """Best-effort: gator init must remain fast and non-fatal."""
        suffix = init._constitution_drift_suffix(tmp_path)
        assert suffix == ""


class TestPrintBootSequenceConstitutionLine:
    """The boot output's constitution line carries the drift suffix when
    the repo's constitution diverges from the resolved template baseline."""

    def _run_boot_sequence(self, repo, capsys):
        paths = gator_layout.get_gator_paths(repo)
        # Stub hook status + registry status — we only care about the
        # constitution line for these tests.
        hook_status = {"status": "ok", "detail": "ok"}
        registry_status = {"status": "already_registered", "detail": "already registered"}
        init.print_boot_sequence(repo, paths, hook_status, registry_status)
        return capsys.readouterr().out

    def test_pristine_shows_no_drift_suffix(self, tmp_path, capsys):
        repo = _governed_repo_with_pristine_constitution(tmp_path)
        out = self._run_boot_sequence(repo, capsys)
        assert "constitution" in out
        assert "modified from baseline" not in out

    def test_modified_shows_drift_suffix(self, tmp_path, capsys):
        repo = _governed_repo_with_pristine_constitution(tmp_path)
        (repo / ".gator" / "constitution.md").write_text("locally edited\n", encoding="utf-8")
        out = self._run_boot_sequence(repo, capsys)
        assert "modified from baseline" in out

    def test_source_repo_no_suffix_regardless(self, tmp_path, capsys):
        (tmp_path / "gator-command").mkdir()
        (tmp_path / "gator-command" / "mission.md").write_text("x")
        (tmp_path / "constitution.md").write_text("y")
        (tmp_path / ".gator").mkdir()
        (tmp_path / ".gator" / "constitution.md").write_text("could-be-anything\n", encoding="utf-8")
        out = self._run_boot_sequence(tmp_path, capsys)
        assert "modified from baseline" not in out
