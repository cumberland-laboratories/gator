"""
Tests for gator-state.py — Stage 4 of the local-agent-overrides + managed-state
plan (2026-07-28).

Covers status collection (six-state matrix per file + constitution drift +
source-repo exemption + version diagnostic) and repair actions (state → outcome
per file, dry-run non-mutation, and the *.local.md untouched invariant).
"""

import json
import shutil
import types
from pathlib import Path

import pytest

from conftest import load_script

SCRIPTS_DIR = Path(__file__).parent.parent / "src" / "gator_command" / "scripts"
TEMPLATES_DIR = Path(__file__).parent.parent / "src" / "gator_command" / "templates" / "gator-starter"

state_mod = load_script("gator-state", search_dir=SCRIPTS_DIR)

from gatorize.entry_points import render_entry_content
from gatorize.managed_block import (
    GATOR_BEGIN, GATOR_END,
    BlockState,
    render_managed_region,
)


# ---------------------------------------------------------------------------
# Fixture builder
# ---------------------------------------------------------------------------

def _build_managed_block(agent_type):
    baseline = render_entry_content(has_command_post=False, agent_type=agent_type)
    return f"{GATOR_BEGIN}{render_managed_region(baseline)}{GATOR_END}"


def _make_governed_repo(tmp_path, layout="v1"):
    """Create a minimal .gator/ tree so find_gator_root() works and
    resolve_template_source() finds the shipped templates."""
    repo = tmp_path / "repo"
    gator = repo / ".gator"
    gator.mkdir(parents=True)

    # product-source.json → points at our real shipped templates so baseline
    # resolution matches production.
    ps = {
        "gator_root": str(TEMPLATES_DIR.parent.parent),  # …/src/gator_command
        "template_dir": "templates/gator-starter",
        "installed": "2026-07-29",
        "updated": "2026-07-29",
    }
    (gator / "product-source.json").write_text(json.dumps(ps), encoding="utf-8")

    # constitution.md at the layout-appropriate path (defaults to v1 — flat root)
    constitution_src = TEMPLATES_DIR / "constitution.md"
    if layout == "v2":
        (gator / ".includes").mkdir()
        (gator / ".includes" / "constitution.md").write_bytes(constitution_src.read_bytes())
    else:
        (gator / "constitution.md").write_bytes(constitution_src.read_bytes())

    return repo


def _write_clean_entry_point(repo, filename, agent_type):
    """Write a file whose managed block matches the current baseline exactly."""
    (repo / filename).write_text(
        f"# Header\n\nintro\n\n{_build_managed_block(agent_type)}\n\ntail\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

class TestSourceRepoDetection:
    def test_true_when_both_files_present(self, tmp_path):
        (tmp_path / "gator-command").mkdir()
        (tmp_path / "gator-command" / "mission.md").write_text("x")
        (tmp_path / "constitution.md").write_text("y")
        assert state_mod.is_source_repo(tmp_path) is True

    def test_false_when_only_mission_present(self, tmp_path):
        (tmp_path / "gator-command").mkdir()
        (tmp_path / "gator-command" / "mission.md").write_text("x")
        assert state_mod.is_source_repo(tmp_path) is False

    def test_false_when_only_constitution_present(self, tmp_path):
        (tmp_path / "constitution.md").write_text("y")
        assert state_mod.is_source_repo(tmp_path) is False

    def test_false_on_empty_repo(self, tmp_path):
        assert state_mod.is_source_repo(tmp_path) is False


class TestLocalCompanionPresent:
    def test_true_when_file_exists(self, tmp_path):
        (tmp_path / "CLAUDE.local.md").write_text("private notes")
        assert state_mod.local_companion_present(tmp_path, "CLAUDE.md") is True

    def test_false_when_missing(self, tmp_path):
        assert state_mod.local_companion_present(tmp_path, "CLAUDE.md") is False

    def test_derives_stem_from_filename(self, tmp_path):
        (tmp_path / "AGENTS.local.md").write_text("x")
        assert state_mod.local_companion_present(tmp_path, "AGENTS.md") is True
        assert state_mod.local_companion_present(tmp_path, "GEMINI.md") is False


class TestReadRepoGatorVersion:
    def test_reads_cli_version(self, tmp_path):
        (tmp_path / ".gator").mkdir()
        (tmp_path / ".gator" / ".gator-version").write_text(
            "generation: 2\ninstalled: 2026-07-01\ncli-version: 2.1.0\n"
        )
        assert state_mod.read_repo_gator_version(tmp_path) == "2.1.0"

    def test_none_when_file_missing(self, tmp_path):
        assert state_mod.read_repo_gator_version(tmp_path) is None

    def test_none_when_key_missing(self, tmp_path):
        (tmp_path / ".gator").mkdir()
        (tmp_path / ".gator" / ".gator-version").write_text("generation: 2\n")
        assert state_mod.read_repo_gator_version(tmp_path) is None


# ---------------------------------------------------------------------------
# Status — six-state matrix
# ---------------------------------------------------------------------------

class TestClassifyEntryPointStates:
    def test_absent(self, tmp_path):
        state, text = state_mod.classify_entry_point(tmp_path, "CLAUDE.md", "claude")
        assert state is BlockState.ABSENT
        assert text is None

    def test_clean(self, tmp_path):
        _write_clean_entry_point(tmp_path, "CLAUDE.md", "claude")
        state, _ = state_mod.classify_entry_point(tmp_path, "CLAUDE.md", "claude")
        assert state is BlockState.CLEAN

    def test_modified(self, tmp_path):
        (tmp_path / "AGENTS.md").write_text(
            f"# Header\n\n{GATOR_BEGIN}\ndrifted content\n{GATOR_END}\n",
            encoding="utf-8",
        )
        state, _ = state_mod.classify_entry_point(tmp_path, "AGENTS.md", "agents")
        assert state is BlockState.MODIFIED

    def test_legacy(self, tmp_path):
        (tmp_path / "GEMINI.md").write_text(
            "# --- Gator Navigation Coding ---\n\nlegacy prose\n",
            encoding="utf-8",
        )
        state, _ = state_mod.classify_entry_point(tmp_path, "GEMINI.md", "gemini")
        assert state is BlockState.LEGACY

    def test_corrupted(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text(
            f"lead\n{GATOR_BEGIN}\ncontent with no end sentinel",
            encoding="utf-8",
        )
        state, _ = state_mod.classify_entry_point(tmp_path, "CLAUDE.md", "claude")
        assert state is BlockState.CORRUPTED

    def test_foreign(self, tmp_path):
        (tmp_path / "AGENTS.md").write_text("# My Project\n\nJust a plain readme.\n", encoding="utf-8")
        state, _ = state_mod.classify_entry_point(tmp_path, "AGENTS.md", "agents")
        assert state is BlockState.FOREIGN


# ---------------------------------------------------------------------------
# Status — constitution drift
# ---------------------------------------------------------------------------

class TestCheckConstitution:
    def test_source_repo_exemption_short_circuits(self, tmp_path):
        (tmp_path / "gator-command").mkdir()
        (tmp_path / "gator-command" / "mission.md").write_text("x")
        (tmp_path / "constitution.md").write_text("y")
        # Even with no templates_dir, source-repo exemption wins
        result = state_mod.check_constitution(tmp_path, None)
        assert result == {"status": "source-repo-exempt"}

    def test_no_baseline_when_templates_dir_none(self, tmp_path):
        result = state_mod.check_constitution(tmp_path, None)
        assert result == {"status": "no-baseline"}

    def test_no_baseline_when_template_constitution_missing(self, tmp_path):
        empty_templates = tmp_path / "empty-templates"
        empty_templates.mkdir()
        result = state_mod.check_constitution(tmp_path, empty_templates)
        assert result == {"status": "no-baseline"}

    def test_no_repo_constitution(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        # remove the constitution we just wrote
        (repo / ".gator" / "constitution.md").unlink()
        result = state_mod.check_constitution(repo, TEMPLATES_DIR)
        assert result == {"status": "no-repo-constitution"}

    def test_clean_when_bytes_match(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        result = state_mod.check_constitution(repo, TEMPLATES_DIR)
        assert result == {"status": "clean"}

    def test_modified_when_bytes_differ(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        (repo / ".gator" / "constitution.md").write_text("locally edited", encoding="utf-8")
        result = state_mod.check_constitution(repo, TEMPLATES_DIR)
        assert result == {"status": "modified"}


# ---------------------------------------------------------------------------
# Status — end-to-end collect + render
# ---------------------------------------------------------------------------

class TestCollectStatus:
    def test_schema_and_shape(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        report = state_mod.collect_status(repo)
        assert report["schema"] == "gator-state-v1"
        assert report["repo_root"] == str(repo)
        assert isinstance(report["host_cli_version"], str)
        # v1 layout — no `.gator-version` yet in this fixture
        assert report["repo_gator_version"] is None
        # Two independent baselines with different lifecycles (Round 9 fix):
        assert report["entry_point_baseline_kind"] == "installed-package-code"
        assert report["constitution_baseline_source"] is not None
        assert len(report["entry_points"]) == 3
        assert {ep["filename"] for ep in report["entry_points"]} == {"CLAUDE.md", "AGENTS.md", "GEMINI.md"}

    def test_all_absent_when_no_entry_points_written(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        report = state_mod.collect_status(repo)
        for ep in report["entry_points"]:
            assert ep["state"] == "absent"

    def test_local_companion_present_reported(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        (repo / "CLAUDE.local.md").write_text("private")
        report = state_mod.collect_status(repo)
        claude = next(ep for ep in report["entry_points"] if ep["filename"] == "CLAUDE.md")
        assert claude["local_companion"] == "present"

    def test_constitution_clean_on_pristine_fixture(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        report = state_mod.collect_status(repo)
        assert report["constitution"]["status"] == "clean"

    def test_json_and_text_render(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        report = state_mod.collect_status(repo)
        j = state_mod.render_status_json(report)
        parsed = json.loads(j)
        assert parsed["schema"] == "gator-state-v1"
        t = state_mod.render_status_text(report)
        assert "entry points:" in t
        assert "constitution:" in t
        assert "host: gator" in t


class TestVersionDiagnostic:
    def test_no_repo_version_only_host(self):
        line = state_mod._format_version_diagnostic("2.2.2", None)
        assert line == "host: gator 2.2.2"

    def test_matching_versions_suppresses_repo_half(self):
        line = state_mod._format_version_diagnostic("2.2.2", "2.2.2")
        assert line == "host: gator 2.2.2"

    def test_mismatched_versions_shows_both(self):
        line = state_mod._format_version_diagnostic("2.2.2", "2.1.0")
        assert "host: gator 2.2.2" in line
        assert "repo: gatorized with gator 2.1.0" in line


# ---------------------------------------------------------------------------
# Repair — per-state dispatch
# ---------------------------------------------------------------------------

class TestPlanRepair:
    def test_all_six_states_get_correct_action(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        # CLAUDE.md → CLEAN
        _write_clean_entry_point(repo, "CLAUDE.md", "claude")
        # AGENTS.md → MODIFIED
        (repo / "AGENTS.md").write_text(
            f"lead\n{GATOR_BEGIN}\ndrifted\n{GATOR_END}\ntail\n", encoding="utf-8"
        )
        # GEMINI.md → LEGACY (fingerprint, no sentinels)
        (repo / "GEMINI.md").write_text("# --- Gator Navigation Coding ---\nold\n", encoding="utf-8")

        plan = state_mod.plan_repair(repo)
        actions = {p["filename"]: p["action"] for p in plan}
        assert actions["CLAUDE.md"] == "noop"
        assert actions["AGENTS.md"] == "restore-block"
        assert actions["GEMINI.md"] == "upgrade-legacy"

    def test_absent_action(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        plan = state_mod.plan_repair(repo)
        for p in plan:
            assert p["action"] == "create-fresh"

    def test_corrupted_action(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        (repo / "CLAUDE.md").write_text(f"{GATOR_BEGIN}\nno end", encoding="utf-8")
        plan = state_mod.plan_repair(repo, only_filename="CLAUDE.md")
        assert plan[0]["action"].startswith("backup-to-CLAUDE_ROLLBACK.md")

    def test_foreign_action(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        (repo / "AGENTS.md").write_text("# My Project\n\nplain readme\n", encoding="utf-8")
        plan = state_mod.plan_repair(repo, only_filename="AGENTS.md")
        assert plan[0]["action"] == "skip-refer-to-gatorize"

    def test_only_filename_narrows(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        plan = state_mod.plan_repair(repo, only_filename="AGENTS.md")
        assert len(plan) == 1
        assert plan[0]["filename"] == "AGENTS.md"


class TestExecuteRepair:
    def test_clean_no_op(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        _write_clean_entry_point(repo, "CLAUDE.md", "claude")
        original = (repo / "CLAUDE.md").read_bytes()
        plan = state_mod.plan_repair(repo, only_filename="CLAUDE.md")
        state_mod.execute_repair(repo, plan)
        assert (repo / "CLAUDE.md").read_bytes() == original
        assert plan[0]["outcome"] == "unchanged"

    def test_modified_restores_block_but_preserves_outer(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        (repo / "CLAUDE.md").write_text(
            f"# Custom Header\n\nintro\n\n{GATOR_BEGIN}\ndrifted content\n{GATOR_END}\n\ntrailer\n",
            encoding="utf-8",
        )
        plan = state_mod.plan_repair(repo, only_filename="CLAUDE.md")
        state_mod.execute_repair(repo, plan)
        result = (repo / "CLAUDE.md").read_text(encoding="utf-8")
        # Outer content byte-preserved
        assert result.startswith("# Custom Header\n\nintro\n\n")
        assert result.endswith("\n\ntrailer\n")
        # Block replaced with baseline
        baseline = render_entry_content(has_command_post=False, agent_type="claude")
        assert baseline in result
        assert "drifted content" not in result
        assert plan[0]["outcome"] == "restored"

    def test_legacy_routes_to_upgrade_helper(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        (repo / "GEMINI.md").write_text(
            "# Legacy Custom\n\nintro\n\n# --- Gator Navigation Coding ---\nold body\n\n"
            "## Pre-Gator Instructions\n\nKept notes.\n",
            encoding="utf-8",
        )
        plan = state_mod.plan_repair(repo, only_filename="GEMINI.md")
        state_mod.execute_repair(repo, plan)
        result = (repo / "GEMINI.md").read_text(encoding="utf-8")
        # Sentinel-wrapped block present
        assert GATOR_BEGIN in result
        assert GATOR_END in result
        # Pre-Gator section preserved
        assert "## Pre-Gator Instructions" in result
        assert "Kept notes." in result
        assert plan[0]["outcome"] == "upgraded"

    def test_absent_creates_fresh(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        plan = state_mod.plan_repair(repo, only_filename="CLAUDE.md")
        state_mod.execute_repair(repo, plan)
        assert (repo / "CLAUDE.md").exists()
        content = (repo / "CLAUDE.md").read_text(encoding="utf-8")
        assert content.startswith("# Claude Code Entry Point\n")
        assert GATOR_BEGIN in content
        assert plan[0]["outcome"] == "created"

    def test_corrupted_backs_up_and_recreates(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        original = f"{GATOR_BEGIN}\nno end sentinel present"
        (repo / "AGENTS.md").write_text(original, encoding="utf-8")
        plan = state_mod.plan_repair(repo, only_filename="AGENTS.md")
        state_mod.execute_repair(repo, plan)
        # Rollback preserves the original bytes exactly
        assert (repo / "AGENTS_ROLLBACK.md").read_text(encoding="utf-8") == original
        # AGENTS.md is a fresh sentinel-wrapped file
        new_content = (repo / "AGENTS.md").read_text(encoding="utf-8")
        assert new_content.startswith("# Codex Entry Point\n")
        assert GATOR_BEGIN in new_content
        assert GATOR_END in new_content
        assert plan[0]["outcome"].startswith("backed-up-to-AGENTS_ROLLBACK.md")

    def test_foreign_leaves_file_untouched(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        original = "# My Project\n\nUnrelated content.\n"
        (repo / "AGENTS.md").write_text(original, encoding="utf-8")
        plan = state_mod.plan_repair(repo, only_filename="AGENTS.md")
        state_mod.execute_repair(repo, plan)
        # File untouched
        assert (repo / "AGENTS.md").read_text(encoding="utf-8") == original
        # No rollback created
        assert not (repo / "AGENTS_ROLLBACK.md").exists()
        assert plan[0]["outcome"] == "skipped-foreign"


class TestDryRunNoMutation:
    def test_dry_run_does_not_write(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        # Set up all six states in one fixture
        _write_clean_entry_point(repo, "CLAUDE.md", "claude")
        (repo / "AGENTS.md").write_text(
            f"{GATOR_BEGIN}\ndrifted\n{GATOR_END}\n", encoding="utf-8"
        )
        # GEMINI.md left absent
        # Snapshot before
        snapshot = {
            "CLAUDE.md": (repo / "CLAUDE.md").read_bytes(),
            "AGENTS.md": (repo / "AGENTS.md").read_bytes(),
        }
        # Dry-run "repair" via the CLI-level main_repair with args-like namespace
        args = types.SimpleNamespace(
            path=str(repo), dry_run=True, json=False, filename=None,
        )
        rc = state_mod.main_repair(args)
        assert rc == 0
        # Files untouched
        assert (repo / "CLAUDE.md").read_bytes() == snapshot["CLAUDE.md"]
        assert (repo / "AGENTS.md").read_bytes() == snapshot["AGENTS.md"]
        # GEMINI.md was absent — still absent
        assert not (repo / "GEMINI.md").exists()


class TestLocalCompanionUntouchedThroughout:
    """Invariant #7 — no gator-state code path may read, write, create, or
    delete a *.local.md file. This test exercises every repair state and
    asserts that pre-existing companion files are byte-preserved."""

    def test_all_states_preserve_local_companion(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        # Local companions for each vendor with distinctive content
        (repo / "CLAUDE.local.md").write_text("personal-claude", encoding="utf-8")
        (repo / "AGENTS.local.md").write_text("personal-agents", encoding="utf-8")
        (repo / "GEMINI.local.md").write_text("personal-gemini", encoding="utf-8")

        # State setup:
        _write_clean_entry_point(repo, "CLAUDE.md", "claude")     # clean → noop
        (repo / "AGENTS.md").write_text(                          # modified → restore-block
            f"lead\n{GATOR_BEGIN}\ndrifted\n{GATOR_END}\ntail\n", encoding="utf-8"
        )
        (repo / "GEMINI.md").write_text(                          # corrupted → backup+recreate
            f"{GATOR_BEGIN}\nno end", encoding="utf-8"
        )

        plan = state_mod.plan_repair(repo)
        state_mod.execute_repair(repo, plan)

        # Companion files untouched byte-for-byte
        assert (repo / "CLAUDE.local.md").read_text(encoding="utf-8") == "personal-claude"
        assert (repo / "AGENTS.local.md").read_text(encoding="utf-8") == "personal-agents"
        assert (repo / "GEMINI.local.md").read_text(encoding="utf-8") == "personal-gemini"


# ---------------------------------------------------------------------------
# Source-repo exemption at the collect_status level
# ---------------------------------------------------------------------------

class TestSourceRepoExemption:
    def test_constitution_reports_exempt(self, tmp_path):
        # A repo that IS a source repo (both signature files) + a .gator/ so
        # find_gator_root() succeeds. Templates_dir intentionally left None.
        (tmp_path / "gator-command").mkdir()
        (tmp_path / "gator-command" / "mission.md").write_text("x")
        (tmp_path / "constitution.md").write_text("y")
        (tmp_path / ".gator").mkdir()

        report = state_mod.collect_status(tmp_path)
        assert report["constitution"]["status"] == "source-repo-exempt"


# ---------------------------------------------------------------------------
# Stage 5 — check_constitution_drift wrapper (resolves template source
# internally so callers like gator init don't need to)
# ---------------------------------------------------------------------------

class TestCheckConstitutionDrift:
    def test_returns_clean_on_pristine_governed_repo(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        result = state_mod.check_constitution_drift(repo)
        assert result == {"status": "clean"}

    def test_returns_modified_when_repo_constitution_edited(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        (repo / ".gator" / "constitution.md").write_text("locally edited", encoding="utf-8")
        result = state_mod.check_constitution_drift(repo)
        assert result == {"status": "modified"}

    def test_returns_source_repo_exempt_on_source_repo(self, tmp_path):
        (tmp_path / "gator-command").mkdir()
        (tmp_path / "gator-command" / "mission.md").write_text("x")
        (tmp_path / "constitution.md").write_text("y")
        (tmp_path / ".gator").mkdir()
        result = state_mod.check_constitution_drift(tmp_path)
        assert result == {"status": "source-repo-exempt"}

    def test_returns_no_baseline_when_product_source_missing(self, tmp_path):
        # .gator/ exists but no product-source.json and no template source
        (tmp_path / ".gator").mkdir()
        result = state_mod.check_constitution_drift(tmp_path)
        assert result == {"status": "no-baseline"}

    def test_never_raises_on_broken_gator_dir(self, tmp_path):
        """Best-effort — no .gator/ at all should still return a status dict,
        not raise. gator init calls this on every session open."""
        result = state_mod.check_constitution_drift(tmp_path)
        assert isinstance(result, dict)
        assert "status" in result

    def test_signature_takes_only_repo_root(self):
        """The wrapper's API is deliberately flat — one positional arg.
        Callers must not need to know about template-source resolution."""
        import inspect
        sig = inspect.signature(state_mod.check_constitution_drift)
        assert list(sig.parameters.keys()) == ["repo_root"]


# ---------------------------------------------------------------------------
# Round 9 regression guard — entry-point baseline is package-code, not
# resolvable via any template-source override
# ---------------------------------------------------------------------------

class TestEntryPointBaselineIsPackageCode:
    """Codex Round 9 finding: the plan claimed entry-point baseline flowed
    through resolve_template_source(), but render_entry_content() is a Python
    function in the installed package with no file-based override path. Fixed
    by (a) removing the --source flag from `gator state status` and (b)
    clarifying the JSON shape. This test pins the invariant."""

    def test_status_subparser_has_no_source_flag(self):
        parser = state_mod._build_parser()
        # Extract the 'status' subparser action
        sub_action = next(a for a in parser._actions if hasattr(a, "choices") and a.choices)
        p_status = sub_action.choices["status"]
        flags = {opt for a in p_status._actions for opt in a.option_strings}
        assert "--source" not in flags
        # --path and --json still present
        assert "--path" in flags
        assert "--json" in flags

    def test_collect_status_no_source_override_parameter(self):
        import inspect
        sig = inspect.signature(state_mod.collect_status)
        assert list(sig.parameters.keys()) == ["repo_root"]

    def test_entry_point_baseline_kind_field_present(self, tmp_path):
        """The JSON shape carries entry_point_baseline_kind explicitly so
        downstream consumers can distinguish package-code baseline from the
        file-based constitution baseline."""
        repo = _make_governed_repo(tmp_path)
        report = state_mod.collect_status(repo)
        assert report["entry_point_baseline_kind"] == "installed-package-code"

    def test_constitution_baseline_source_field_renamed_from_baseline_source(self, tmp_path):
        """Old field name `baseline_source` is gone; the honest name
        `constitution_baseline_source` replaces it."""
        repo = _make_governed_repo(tmp_path)
        report = state_mod.collect_status(repo)
        assert "constitution_baseline_source" in report
        assert "baseline_source" not in report
