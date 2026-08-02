"""
Tests for Stage 4b — `gator update`'s new entry-point managed-block refresh.

Covers:
- `plan_entry_point_updates`: six-state dispatch → correct action (or skip)
- `execute_entry_point_updates`: per-state outcome + `.pre-gator-update`
  backup written ONLY for `refresh-block` on modified files
- `print_json_plan` JSON shape: `"schema": "gator-update-v1"` and
  `entry_point_actions` field
- `*.local.md` files untouched throughout

Companion `tests/test_template_sync.py` covers the package/template parity
backstop (behavioral + JSON schema + AST equivalence of inlined helpers).
"""

from pathlib import Path

import pytest

from conftest import load_script

SCRIPTS_DIR = Path(__file__).parent.parent / "src" / "gator_command" / "scripts"

update_mod = load_script("gator-update", search_dir=SCRIPTS_DIR)

from gatorize.entry_points import render_entry_content
from gatorize.managed_block import (
    GATOR_BEGIN, GATOR_END,
    BlockState,
    render_managed_region,
)


def _build_managed_block(agent_type):
    baseline = render_entry_content(has_command_post=False, agent_type=agent_type)
    return f"{GATOR_BEGIN}{render_managed_region(baseline)}{GATOR_END}"


class TestPlanEntryPointUpdatesDispatch:
    """Each of the six states resolves to the correct planned action."""

    def test_clean_produces_no_plan_entry(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text(
            f"header\n{_build_managed_block('claude')}\nfooter\n", encoding="utf-8"
        )
        plan = update_mod.plan_entry_point_updates(tmp_path)
        filenames = {p["filename"] for p in plan}
        assert "CLAUDE.md" not in filenames

    def test_modified_planned_as_refresh_block(self, tmp_path):
        (tmp_path / "AGENTS.md").write_text(
            f"lead\n{GATOR_BEGIN}\ndrifted content\n{GATOR_END}\ntail\n", encoding="utf-8"
        )
        plan = update_mod.plan_entry_point_updates(tmp_path)
        entry = next(p for p in plan if p["filename"] == "AGENTS.md")
        assert entry["state"] == "modified"
        assert entry["action"] == "refresh-block"

    def test_legacy_planned_as_upgrade_legacy(self, tmp_path):
        (tmp_path / "GEMINI.md").write_text(
            "# --- Gator Navigation Coding ---\n\nold body\n", encoding="utf-8"
        )
        plan = update_mod.plan_entry_point_updates(tmp_path)
        entry = next(p for p in plan if p["filename"] == "GEMINI.md")
        assert entry["state"] == "legacy"
        assert entry["action"] == "upgrade-legacy"

    def test_absent_planned_as_create_fresh(self, tmp_path):
        # No entry-point files present
        plan = update_mod.plan_entry_point_updates(tmp_path)
        assert len(plan) == 3
        for entry in plan:
            assert entry["state"] == "absent"
            assert entry["action"] == "create-fresh"

    def test_corrupted_skipped_entirely(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text(
            f"{GATOR_BEGIN}\nno end sentinel", encoding="utf-8"
        )
        plan = update_mod.plan_entry_point_updates(tmp_path)
        filenames = {p["filename"] for p in plan}
        assert "CLAUDE.md" not in filenames

    def test_foreign_skipped_entirely(self, tmp_path):
        (tmp_path / "AGENTS.md").write_text(
            "# My Project\n\nPlain readme.\n", encoding="utf-8"
        )
        plan = update_mod.plan_entry_point_updates(tmp_path)
        filenames = {p["filename"] for p in plan}
        assert "AGENTS.md" not in filenames

    def test_mixed_states_across_three_files(self, tmp_path):
        # CLAUDE clean, AGENTS modified, GEMINI legacy
        (tmp_path / "CLAUDE.md").write_text(
            f"{_build_managed_block('claude')}\n", encoding="utf-8"
        )
        (tmp_path / "AGENTS.md").write_text(
            f"{GATOR_BEGIN}\ndrift\n{GATOR_END}\n", encoding="utf-8"
        )
        (tmp_path / "GEMINI.md").write_text(
            "# --- Gator Command Post ---\n", encoding="utf-8"
        )
        plan = update_mod.plan_entry_point_updates(tmp_path)
        actions = {p["filename"]: p["action"] for p in plan}
        assert "CLAUDE.md" not in actions  # clean → skipped
        assert actions["AGENTS.md"] == "refresh-block"
        assert actions["GEMINI.md"] == "upgrade-legacy"


class TestExecuteEntryPointUpdatesOutcomes:
    """Executor writes .pre-gator-update backup ONLY for refresh-block on
    modified files. Other actions do not backup. Content byte-preserved
    outside the sentinel region on refresh-block."""

    def test_refresh_block_writes_backup_and_restores_baseline(self, tmp_path):
        original = f"# Custom Header\n\nintro\n\n{GATOR_BEGIN}\ndrifted\n{GATOR_END}\n\ntrailer\n"
        (tmp_path / "CLAUDE.md").write_text(original, encoding="utf-8")

        plan = update_mod.plan_entry_point_updates(tmp_path)
        update_mod.execute_entry_point_updates(tmp_path, plan)

        # Backup preserves the pre-refresh bytes exactly
        backup = tmp_path / "CLAUDE.md.pre-gator-update"
        assert backup.exists()
        assert backup.read_text(encoding="utf-8") == original

        # File now carries the baseline block; outer content byte-preserved
        result = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        assert result.startswith("# Custom Header\n\nintro\n\n")
        assert result.endswith("\n\ntrailer\n")
        assert render_entry_content(has_command_post=False, agent_type="claude") in result
        assert "drifted" not in result

        entry = next(p for p in plan if p["filename"] == "CLAUDE.md")
        assert entry["outcome"] == "refreshed-with-backup"

    def test_create_fresh_writes_no_backup(self, tmp_path):
        plan = update_mod.plan_entry_point_updates(tmp_path)
        update_mod.execute_entry_point_updates(tmp_path, plan)
        for filename in ("CLAUDE.md", "AGENTS.md", "GEMINI.md"):
            assert (tmp_path / filename).exists()
            assert not (tmp_path / f"{filename}.pre-gator-update").exists()
        for entry in plan:
            assert entry["outcome"] == "created"

    def test_upgrade_legacy_preserves_pre_gator_section(self, tmp_path):
        (tmp_path / "GEMINI.md").write_text(
            "# Custom Header\n\nprose\n\n# --- Gator Navigation Coding ---\nold body\n\n"
            "## Pre-Gator Instructions\n\nKept notes.\n",
            encoding="utf-8",
        )
        plan = update_mod.plan_entry_point_updates(tmp_path)
        update_mod.execute_entry_point_updates(tmp_path, plan)
        result = (tmp_path / "GEMINI.md").read_text(encoding="utf-8")
        assert GATOR_BEGIN in result
        assert GATOR_END in result
        assert "## Pre-Gator Instructions" in result
        assert "Kept notes." in result
        # No .pre-gator-update backup for legacy upgrade
        assert not (tmp_path / "GEMINI.md.pre-gator-update").exists()
        entry = next(p for p in plan if p["filename"] == "GEMINI.md")
        assert entry["outcome"] == "upgraded"

    def test_clean_files_are_not_touched(self, tmp_path):
        original = f"header\n{_build_managed_block('claude')}\nfooter\n"
        (tmp_path / "CLAUDE.md").write_text(original, encoding="utf-8")
        plan = update_mod.plan_entry_point_updates(tmp_path)
        # Clean → no plan entry, so no execution
        update_mod.execute_entry_point_updates(tmp_path, plan)
        assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == original
        assert not (tmp_path / "CLAUDE.md.pre-gator-update").exists()

    def test_corrupted_and_foreign_never_touched(self, tmp_path):
        """Both states are absent from the plan, so execute is a no-op on them."""
        corrupted = f"{GATOR_BEGIN}\nno end"
        foreign = "# My Project\n\nplain readme\n"
        (tmp_path / "CLAUDE.md").write_text(corrupted, encoding="utf-8")
        (tmp_path / "AGENTS.md").write_text(foreign, encoding="utf-8")
        plan = update_mod.plan_entry_point_updates(tmp_path)
        update_mod.execute_entry_point_updates(tmp_path, plan)
        assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == corrupted
        assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == foreign
        # No backups written for these skipped states
        assert not (tmp_path / "CLAUDE.md.pre-gator-update").exists()
        assert not (tmp_path / "AGENTS.md.pre-gator-update").exists()


class TestLocalCompanionUntouchedByUpdate:
    """Invariant #7 — `gator update`'s block refresh must never touch
    `*.local.md` companion files across any state."""

    def test_all_states_preserve_local_companions(self, tmp_path):
        (tmp_path / "CLAUDE.local.md").write_text("personal-claude", encoding="utf-8")
        (tmp_path / "AGENTS.local.md").write_text("personal-agents", encoding="utf-8")
        (tmp_path / "GEMINI.local.md").write_text("personal-gemini", encoding="utf-8")

        # Mixed states: modified, legacy, absent
        (tmp_path / "CLAUDE.md").write_text(
            f"{GATOR_BEGIN}\ndrift\n{GATOR_END}\n", encoding="utf-8"
        )
        (tmp_path / "AGENTS.md").write_text(
            "# --- Gator Navigation Coding ---\n", encoding="utf-8"
        )
        # GEMINI.md absent

        plan = update_mod.plan_entry_point_updates(tmp_path)
        update_mod.execute_entry_point_updates(tmp_path, plan)

        assert (tmp_path / "CLAUDE.local.md").read_text(encoding="utf-8") == "personal-claude"
        assert (tmp_path / "AGENTS.local.md").read_text(encoding="utf-8") == "personal-agents"
        assert (tmp_path / "GEMINI.local.md").read_text(encoding="utf-8") == "personal-gemini"


class TestJSONPlanSchema:
    """Stage 4b JSON output must carry `"schema": "gator-update-v1"` at top
    level and `entry_point_actions` alongside the existing `hooks` list."""

    def test_json_plan_includes_schema_and_entry_point_actions(self, tmp_path, capsys):
        # Minimal templates_dir stub (only needs to be a Path — no reading happens)
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        entry_actions = [
            {"filename": "CLAUDE.md", "agent_type": "claude", "state": "modified", "action": "refresh-block"}
        ]
        update_mod.print_json_plan(plan=[], templates_dir=templates_dir, hooks=[], entry_point_actions=entry_actions)
        out = capsys.readouterr().out
        import json as _json
        parsed = _json.loads(out)
        assert parsed["schema"] == "gator-update-v1"
        assert parsed["entry_point_actions"] == entry_actions
        assert parsed["summary"]["entry_point_actions"] == 1
        # Existing fields preserved (additive-only within v1)
        assert "version" in parsed
        assert "templates" in parsed
        assert "plan" in parsed
        assert "hooks" in parsed
        assert "summary" in parsed

    def test_json_plan_omits_none_becomes_empty_list(self, tmp_path, capsys):
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        update_mod.print_json_plan(plan=[], templates_dir=templates_dir, hooks=[])
        out = capsys.readouterr().out
        import json as _json
        parsed = _json.loads(out)
        assert parsed["entry_point_actions"] == []
        assert parsed["summary"]["entry_point_actions"] == 0


class TestGracefulDegradationFlag:
    """The module exports `_ENTRY_POINT_REFRESH_AVAILABLE` so callers can
    tell when block-refresh is disabled (fleet-repo template copy without
    the gatorize sub-package)."""

    def test_flag_is_true_when_package_imports_available(self):
        # In this test context, the gatorize sub-package IS available.
        assert update_mod._ENTRY_POINT_REFRESH_AVAILABLE is True


# ---------------------------------------------------------------------------
# Round 10 finding #1 regression guards — executor must return counts that
# feed print_result() completion accounting AND the .gator-version stamp
# gate in main(). An entry-point-only update run must no longer show
# "Done: 0 added, 0 updated" and leave .gator-version stale.
# ---------------------------------------------------------------------------

class TestExecuteReturnsCounts:
    """`execute_entry_point_updates` returns
    `(refreshed, upgraded, created, skipped)` — mirrors the shape of
    `execute_updates`'s `(added, updated, unchanged)` triple."""

    def test_refresh_block_increments_refreshed(self, tmp_path):
        # CLAUDE modified; AGENTS + GEMINI clean so they don't enter the plan
        (tmp_path / "CLAUDE.md").write_text(
            f"lead\n{GATOR_BEGIN}\ndrift\n{GATOR_END}\ntail\n", encoding="utf-8"
        )
        (tmp_path / "AGENTS.md").write_text(_build_managed_block("agents") + "\n", encoding="utf-8")
        (tmp_path / "GEMINI.md").write_text(_build_managed_block("gemini") + "\n", encoding="utf-8")
        plan = update_mod.plan_entry_point_updates(tmp_path)
        counts = update_mod.execute_entry_point_updates(tmp_path, plan)
        refreshed, upgraded, created, skipped = counts
        assert refreshed == 1
        assert upgraded == 0
        assert created == 0
        assert skipped == 0

    def test_create_fresh_increments_created(self, tmp_path):
        # All three absent
        plan = update_mod.plan_entry_point_updates(tmp_path)
        counts = update_mod.execute_entry_point_updates(tmp_path, plan)
        refreshed, upgraded, created, skipped = counts
        assert refreshed == 0
        assert upgraded == 0
        assert created == 3
        assert skipped == 0

    def test_upgrade_legacy_increments_upgraded(self, tmp_path):
        (tmp_path / "GEMINI.md").write_text(
            "# --- Gator Navigation Coding ---\nold\n", encoding="utf-8"
        )
        plan = update_mod.plan_entry_point_updates(tmp_path)
        counts = update_mod.execute_entry_point_updates(tmp_path, plan)
        refreshed, upgraded, created, skipped = counts
        # 1 upgraded (GEMINI legacy); CLAUDE + AGENTS absent → 2 created
        assert refreshed == 0
        assert upgraded == 1
        assert created == 2
        assert skipped == 0

    def test_mixed_states_produce_mixed_counts(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text(
            f"lead\n{GATOR_BEGIN}\ndrift\n{GATOR_END}\ntail\n", encoding="utf-8"
        )
        (tmp_path / "AGENTS.md").write_text(
            "# --- Gator Command Post ---\n", encoding="utf-8"
        )
        # GEMINI absent
        plan = update_mod.plan_entry_point_updates(tmp_path)
        counts = update_mod.execute_entry_point_updates(tmp_path, plan)
        refreshed, upgraded, created, skipped = counts
        assert refreshed == 1
        assert upgraded == 1
        assert created == 1
        assert skipped == 0

    def test_empty_plan_returns_all_zeros(self, tmp_path):
        counts = update_mod.execute_entry_point_updates(tmp_path, [])
        assert counts == (0, 0, 0, 0)


class TestPrintResultShowsEntryPointCounts:
    """`print_result` must surface entry-point work so users don't see
    'Done: 0 added, 0 updated' after an entry-point-only run."""

    def test_prints_entry_point_line_when_any_change(self, capsys):
        update_mod.print_result(0, 0, 43, entry_point_counts=(2, 1, 0, 0))
        out = capsys.readouterr().out
        assert "Done: 0 added, 0 updated, 43 unchanged" in out
        assert "Entry-point blocks:" in out
        assert "2 refreshed" in out
        assert "1 upgraded" in out
        assert "created" not in out  # zero — omitted from the line

    def test_omits_entry_point_line_when_all_zero(self, capsys):
        update_mod.print_result(2, 1, 43, entry_point_counts=(0, 0, 0, 0))
        out = capsys.readouterr().out
        assert "Done: 2 added, 1 updated, 43 unchanged" in out
        assert "Entry-point blocks:" not in out

    def test_omits_entry_point_line_when_only_skipped(self, capsys):
        """Skipped-only means the planner scoped items but none advanced state
        (e.g., corrupted/foreign never plan; race-losers count as skipped)."""
        update_mod.print_result(0, 0, 43, entry_point_counts=(0, 0, 0, 2))
        out = capsys.readouterr().out
        assert "Entry-point blocks:" not in out

    def test_backward_compatible_with_no_entry_point_counts(self, capsys):
        """Old callers can still call print_result(added, updated, unchanged)
        without the new kwarg."""
        update_mod.print_result(2, 1, 43)
        out = capsys.readouterr().out
        assert "Done: 2 added, 1 updated, 43 unchanged" in out
        assert "Entry-point blocks:" not in out


class TestUpdatedTimestampGateExpression:
    """As of v2.4.2, `updated:` in .gator-version still gates on file
    changes — the historic "last modification" semantic is preserved. This
    is separate from `cli-version:`, which stamps on every run (see
    TestCliVersionAlwaysStamps below).

    The gate expression for the `updated:` timestamp is
    `if added > 0 or updated > 0 or ep_changed`
    where `ep_changed = ep_refreshed + ep_upgraded + ep_created > 0`.
    This test pins the counter-derived boolean so refactors that change
    the counter tuple order (or forget the create/upgrade branches) break loudly.
    """

    def _gate(self, counts, added=0, updated=0):
        refreshed, upgraded, created, _ = counts
        ep_changed = refreshed + upgraded + created > 0
        return added > 0 or updated > 0 or ep_changed

    def test_gate_fires_on_refreshed_only(self):
        assert self._gate((1, 0, 0, 0)) is True

    def test_gate_fires_on_upgraded_only(self):
        assert self._gate((0, 1, 0, 0)) is True

    def test_gate_fires_on_created_only(self):
        assert self._gate((0, 0, 1, 0)) is True

    def test_gate_does_not_fire_on_skipped_only(self):
        """Skipped is bookkeeping — didn't change repo state, so no stamp."""
        assert self._gate((0, 0, 0, 2)) is False

    def test_gate_does_not_fire_on_all_zeros_without_file_overlay(self):
        assert self._gate((0, 0, 0, 0)) is False

    def test_gate_still_fires_on_file_overlay_alone(self):
        assert self._gate((0, 0, 0, 0), added=1) is True
        assert self._gate((0, 0, 0, 0), updated=1) is True


class TestCliVersionAlwaysStamps:
    """v2.4.2 semantic split: `cli-version` in .gator-version stamps on
    EVERY successful gator-update run — regardless of whether files changed.
    Rationale: cli-version records "which CLI last verified this repo,"
    driving the Dashboard Fleet Version column and its Update-button
    enable/disable logic. Under the pre-2.4.2 gate, an already-current repo
    never re-stamped cli-version after a CLI upgrade, so the Update button
    stayed falsely enabled forever (v2.4.1 → v2.4.2 fleet-wide bug).

    Uses subprocess invocations so the running CLI's version is what stamps.
    """

    def _make_gatorized_repo(self, tmp_path, gator_root, cli_version):
        """Build a minimal .gator/ with a specific stale cli-version stamp.
        Returns repo path.
        """
        import json
        import subprocess
        repo = tmp_path / "repo"
        (repo / ".gator").mkdir(parents=True)
        (repo / ".gator" / ".gator-version").write_text(
            f"generation: 2\n"
            f"installed: 2026-01-01\n"
            f"updated: 2026-01-01T00:00:00\n"
            f"action: install\n"
            f"cli-version: {cli_version}\n",
            encoding="utf-8",
        )
        (repo / ".gator" / "product-source.json").write_text(
            json.dumps({
                "gator_root": str(gator_root),
                "template_dir": "templates/gator-starter",
                "installed": "2026-01-01",
                "updated": "2026-01-01",
            }, indent=2),
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-q", str(repo)], check=True, timeout=10)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True, timeout=10)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True, timeout=10)
        (repo / "README.md").write_text("seed")
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, timeout=10)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "seed"], check=True, timeout=10)
        return repo

    def _read_cli_version(self, repo):
        for line in (repo / ".gator" / ".gator-version").read_text(
            encoding="utf-8"
        ).splitlines():
            if line.startswith("cli-version:"):
                return line.split(":", 1)[1].strip()
        return None

    def _running_cli_version(self):
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, r'{}'); "
             "from gator_core import get_version; print(get_version())".format(
                 SCRIPTS_DIR)],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip()

    def test_cli_version_stamps_when_no_files_change(self, tmp_path):
        """Regression guard for the v2.4.1 fleet-wide bug: an already-current
        repo must still re-stamp cli-version after a CLI upgrade.
        """
        import subprocess
        import sys
        # Point at the real running install — repo is genuinely current
        good_root = SCRIPTS_DIR.parent
        repo = self._make_gatorized_repo(tmp_path, good_root, "0.0.1-stale")

        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "gator-update.py"),
             "--path", str(repo)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, (
            f"gator-update failed:\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
        )
        stamped = self._read_cli_version(repo)
        expected = self._running_cli_version()
        assert stamped == expected, (
            f"cli-version should be {expected!r} after any successful update, "
            f"got {stamped!r}"
        )
        # Also verify it's NOT the stale value
        assert stamped != "0.0.1-stale"

    def test_updated_gate_still_only_fires_on_change_in_source(self):
        """Regression guard for the semantic split: the `and made_changes`
        clause on the `updated:` refresh line must remain in gator-update.py
        source. A subprocess-level test would require a fully-current fixture
        (heavy); grep is sufficient to catch regressions since the guard is
        one clause.
        """
        source = (SCRIPTS_DIR / "gator-update.py").read_text()
        assert 'line.startswith("updated:") and made_changes' in source, (
            "The updated: refresh clause must still gate on made_changes. "
            "Removing this guard would break the last-modification semantic."
        )


class TestProductSourceSelfHeal:
    """v2.4.1 hotfix: when product-source.json points at a nonexistent path,
    gator-update self-heals to the running install's own location (parent of
    scripts/) instead of hard-erroring. Root cause: gatorized repos capture
    the install location at install time; a pipx reinstall as editable (or
    a venv rebuild) invalidates the absolute path. Under v2.3.0 the Dashboard
    Update button ran `gatorize` which doesn't read product-source.json, so
    the stale path never surfaced. Stage 1 of v2.4.0 swapped to `gator-update`
    and exposed the latent bug fleet-wide.

    Uses a subprocess invocation of `gator-update.py --path <target>` so the
    running install's file-based fallback is what the code sees.
    """

    def _make_gatorized_repo(self, tmp_path, stale_gator_root):
        """Build a minimal .gator/ with stale product-source.json pointing at
        `stale_gator_root`. Returns the repo path.
        """
        import json
        import subprocess
        repo = tmp_path / "repo"
        (repo / ".gator").mkdir(parents=True)
        (repo / ".gator" / "product-source.json").write_text(
            json.dumps({
                "gator_root": str(stale_gator_root),
                "template_dir": "templates/gator-starter",
                "installed": "2026-01-01",
                "updated": "2026-01-01",
            }, indent=2),
            encoding="utf-8",
        )
        # Real git repo so gator-update can call git status
        subprocess.run(["git", "init", "-q", str(repo)], check=True, timeout=10)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True, timeout=10)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True, timeout=10)
        (repo / "README.md").write_text("seed")
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, timeout=10)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "seed"], check=True, timeout=10)
        return repo

    def test_self_heal_rewrites_stale_product_source(self, tmp_path):
        """Running gator-update against a repo with a stale product-source.json
        rewrites it to point at the running install's location.
        """
        import json
        import subprocess
        import sys
        # Stale path that categorically does not exist
        stale = tmp_path / "nonexistent" / "path" / "gator_command"
        repo = self._make_gatorized_repo(tmp_path, stale)

        # Invoke gator-update via subprocess (so Path(__file__).parent.parent
        # inside the script resolves to the real running install)
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "gator-update.py"),
             "--path", str(repo), "--dry-run"],
            capture_output=True, text=True, timeout=30,
        )
        # Self-heal warning should appear in stdout
        assert "self-healing" in result.stdout.lower() or "Self-healing" in result.stdout, (
            f"Expected self-heal warning; got:\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
        )
        # product-source.json should now point at the actual running install,
        # NOT the stale path.
        ps_new = json.loads(
            (repo / ".gator" / "product-source.json").read_text(encoding="utf-8")
        )
        assert ps_new["gator_root"] != str(stale)
        assert Path(ps_new["gator_root"]).is_dir()
        assert (Path(ps_new["gator_root"]) / "templates" / "gator-starter").is_dir()

    def test_self_heal_preserves_installed_date(self, tmp_path):
        """The original installed date survives self-heal — only updated is refreshed."""
        import json
        import subprocess
        import sys
        stale = tmp_path / "nonexistent"
        repo = self._make_gatorized_repo(tmp_path, stale)

        subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "gator-update.py"),
             "--path", str(repo), "--dry-run"],
            capture_output=True, text=True, timeout=30,
        )
        ps_new = json.loads(
            (repo / ".gator" / "product-source.json").read_text(encoding="utf-8")
        )
        assert ps_new["installed"] == "2026-01-01"

    def test_current_product_source_no_self_heal(self, tmp_path):
        """When product-source.json is already valid, self-heal must not fire."""
        import json
        import subprocess
        import sys
        # Point at the real running install
        good_root = SCRIPTS_DIR.parent
        repo = self._make_gatorized_repo(tmp_path, good_root)

        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "gator-update.py"),
             "--path", str(repo), "--dry-run"],
            capture_output=True, text=True, timeout=30,
        )
        assert "self-healing" not in result.stdout.lower()

