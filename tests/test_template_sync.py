"""
Package/template sync backstop for gator-update.py — Stage 4b.

Three layers of assertion, stated behaviorally (not by symbol name so
implementation-time renames don't invalidate the contract):

  1. Behavioral parity: fixture-driven invocation of the template's
     plan_entry_point_updates + execute_entry_point_updates against every
     Stage 4b state transition, asserting observable outputs — not internal
     function names.

  2. JSON-schema parity: both copies emit `"schema": "gator-update-v1"` and
     `entry_point_actions` at top level (additive within v1).

  3. AST-equivalence for the inlined managed-block helpers: parse both
     `src/gator_command/scripts/gatorize/managed_block.py` (canonical) and
     `src/gator_command/templates/gator-starter/scripts/gator-update.py`
     (which inlines find_managed_block, classify_managed_block,
     detect_legacy_gator_content per Stage 4b option 2). Compare bodies
     via ast.dump.

Documented in the "Individual/Enterprise Product Boundary" section of
`gator-command/charters/scripts-cross-cutting.md`.
"""

import ast
import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent
PACKAGE_UPDATE = REPO_ROOT / "src" / "gator_command" / "scripts" / "gator-update.py"
TEMPLATE_UPDATE = REPO_ROOT / "src" / "gator_command" / "templates" / "gator-starter" / "scripts" / "gator-update.py"
CANONICAL_MANAGED_BLOCK = REPO_ROOT / "src" / "gator_command" / "scripts" / "gatorize" / "managed_block.py"


def _load_module(path, module_name):
    """Load a Python file as a fresh module, bypassing any cached import."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def package_update():
    """Load the PACKAGE copy of gator-update.py."""
    import sys
    # scripts/ must be on sys.path for gator_core, gatorize.entry_points, etc.
    scripts_dir = str(PACKAGE_UPDATE.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    return _load_module(PACKAGE_UPDATE, "package_gator_update")


@pytest.fixture
def template_update():
    """Load the TEMPLATE copy of gator-update.py.

    The template dir has no gatorize/ sub-package. But the package scripts/
    IS on sys.path (from conftest), so the guarded try-import for
    render_entry_content succeeds. That's fine — it exercises the executor
    fully. The important thing is that the *parsing helpers* (which are
    inlined in the template file) come from the template's own definitions.
    """
    return _load_module(TEMPLATE_UPDATE, "template_gator_update")


# ---------------------------------------------------------------------------
# Layer 1 — Behavioral parity for the update pipeline
# ---------------------------------------------------------------------------

def _build_managed_block(pkg_mod, agent_type):
    baseline = pkg_mod.render_entry_content(has_command_post=False, agent_type=agent_type)
    return f"{pkg_mod.GATOR_BEGIN}{pkg_mod.render_managed_region(baseline)}{pkg_mod.GATOR_END}"


class TestBehavioralParityPlan:
    """The template's plan_entry_point_updates must produce the same plan
    shape as the package's copy for every Stage 4b state transition."""

    @pytest.mark.parametrize("state_setup,expected_action_by_filename", [
        (
            # All absent
            lambda tmp: None,
            {"CLAUDE.md": "create-fresh", "AGENTS.md": "create-fresh", "GEMINI.md": "create-fresh"},
        ),
    ])
    def test_absent_all_three_produces_create_fresh_in_both(
        self, tmp_path, package_update, template_update, state_setup, expected_action_by_filename
    ):
        state_setup(tmp_path)
        pkg_plan = package_update.plan_entry_point_updates(tmp_path)
        tpl_plan = template_update.plan_entry_point_updates(tmp_path)
        pkg_actions = {p["filename"]: p["action"] for p in pkg_plan}
        tpl_actions = {p["filename"]: p["action"] for p in tpl_plan}
        assert pkg_actions == expected_action_by_filename
        assert tpl_actions == expected_action_by_filename

    def test_modified_fixture_yields_refresh_block_in_both(
        self, tmp_path, package_update, template_update
    ):
        (tmp_path / "CLAUDE.md").write_text(
            f"{package_update.GATOR_BEGIN}\ndrift\n{package_update.GATOR_END}\n", encoding="utf-8"
        )
        pkg_plan = package_update.plan_entry_point_updates(tmp_path)
        tpl_plan = template_update.plan_entry_point_updates(tmp_path)
        pkg_entry = next(p for p in pkg_plan if p["filename"] == "CLAUDE.md")
        tpl_entry = next(p for p in tpl_plan if p["filename"] == "CLAUDE.md")
        assert pkg_entry["state"] == tpl_entry["state"] == "modified"
        assert pkg_entry["action"] == tpl_entry["action"] == "refresh-block"

    def test_legacy_fixture_yields_upgrade_legacy_in_both(
        self, tmp_path, package_update, template_update
    ):
        (tmp_path / "AGENTS.md").write_text(
            "# --- Gator Navigation Coding ---\nold\n", encoding="utf-8"
        )
        pkg_plan = package_update.plan_entry_point_updates(tmp_path)
        tpl_plan = template_update.plan_entry_point_updates(tmp_path)
        pkg_entry = next(p for p in pkg_plan if p["filename"] == "AGENTS.md")
        tpl_entry = next(p for p in tpl_plan if p["filename"] == "AGENTS.md")
        assert pkg_entry["state"] == tpl_entry["state"] == "legacy"
        assert pkg_entry["action"] == tpl_entry["action"] == "upgrade-legacy"

    def test_clean_fixture_absent_from_plan_in_both(
        self, tmp_path, package_update, template_update
    ):
        (tmp_path / "GEMINI.md").write_text(
            _build_managed_block(package_update, "gemini") + "\n", encoding="utf-8"
        )
        pkg_plan = package_update.plan_entry_point_updates(tmp_path)
        tpl_plan = template_update.plan_entry_point_updates(tmp_path)
        pkg_names = {p["filename"] for p in pkg_plan}
        tpl_names = {p["filename"] for p in tpl_plan}
        assert "GEMINI.md" not in pkg_names
        assert "GEMINI.md" not in tpl_names

    def test_corrupted_and_foreign_skipped_in_both(
        self, tmp_path, package_update, template_update
    ):
        (tmp_path / "CLAUDE.md").write_text(
            f"{package_update.GATOR_BEGIN}\nno end sentinel", encoding="utf-8"
        )
        (tmp_path / "AGENTS.md").write_text(
            "# My Project\n\nplain readme\n", encoding="utf-8"
        )
        pkg_plan = package_update.plan_entry_point_updates(tmp_path)
        tpl_plan = template_update.plan_entry_point_updates(tmp_path)
        pkg_names = {p["filename"] for p in pkg_plan}
        tpl_names = {p["filename"] for p in tpl_plan}
        assert "CLAUDE.md" not in pkg_names and "CLAUDE.md" not in tpl_names
        assert "AGENTS.md" not in pkg_names and "AGENTS.md" not in tpl_names


class TestBehavioralParityExecute:
    """The template's execute_entry_point_updates must produce byte-identical
    observable outputs to the package copy for every Stage 4b state."""

    def test_modified_executes_with_backup_in_both(
        self, tmp_path, package_update, template_update
    ):
        # Run the package copy on a fresh dir, snapshot outputs
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        original = f"lead\n{package_update.GATOR_BEGIN}\ndrift\n{package_update.GATOR_END}\ntail\n"
        (pkg_dir / "CLAUDE.md").write_text(original, encoding="utf-8")
        pkg_plan = package_update.plan_entry_point_updates(pkg_dir)
        package_update.execute_entry_point_updates(pkg_dir, pkg_plan)
        pkg_result = (pkg_dir / "CLAUDE.md").read_text(encoding="utf-8")
        pkg_backup = (pkg_dir / "CLAUDE.md.pre-gator-update").read_text(encoding="utf-8")

        # Run the template copy on an identically-shaped fresh dir
        tpl_dir = tmp_path / "tpl"
        tpl_dir.mkdir()
        (tpl_dir / "CLAUDE.md").write_text(original, encoding="utf-8")
        tpl_plan = template_update.plan_entry_point_updates(tpl_dir)
        template_update.execute_entry_point_updates(tpl_dir, tpl_plan)
        tpl_result = (tpl_dir / "CLAUDE.md").read_text(encoding="utf-8")
        tpl_backup = (tpl_dir / "CLAUDE.md.pre-gator-update").read_text(encoding="utf-8")

        # Byte-identical outputs
        assert pkg_result == tpl_result
        assert pkg_backup == tpl_backup == original

    def test_absent_creates_identical_bytes_in_both(
        self, tmp_path, package_update, template_update
    ):
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        pkg_plan = package_update.plan_entry_point_updates(pkg_dir)
        package_update.execute_entry_point_updates(pkg_dir, pkg_plan)

        tpl_dir = tmp_path / "tpl"
        tpl_dir.mkdir()
        tpl_plan = template_update.plan_entry_point_updates(tpl_dir)
        template_update.execute_entry_point_updates(tpl_dir, tpl_plan)

        for filename in ("CLAUDE.md", "AGENTS.md", "GEMINI.md"):
            assert (pkg_dir / filename).read_bytes() == (tpl_dir / filename).read_bytes()
            # No backup for create-fresh
            assert not (pkg_dir / f"{filename}.pre-gator-update").exists()
            assert not (tpl_dir / f"{filename}.pre-gator-update").exists()

    def test_legacy_preserves_pre_gator_section_in_both(
        self, tmp_path, package_update, template_update
    ):
        original = (
            "# --- Gator Navigation Coding ---\nold\n\n"
            "## Pre-Gator Instructions\n\nKept.\n"
        )
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        (pkg_dir / "GEMINI.md").write_text(original, encoding="utf-8")
        pkg_plan = package_update.plan_entry_point_updates(pkg_dir)
        package_update.execute_entry_point_updates(pkg_dir, pkg_plan)

        tpl_dir = tmp_path / "tpl"
        tpl_dir.mkdir()
        (tpl_dir / "GEMINI.md").write_text(original, encoding="utf-8")
        tpl_plan = template_update.plan_entry_point_updates(tpl_dir)
        template_update.execute_entry_point_updates(tpl_dir, tpl_plan)

        assert (pkg_dir / "GEMINI.md").read_text(encoding="utf-8") == (tpl_dir / "GEMINI.md").read_text(encoding="utf-8")

    def test_executor_return_tuple_matches_between_copies(
        self, tmp_path, package_update, template_update
    ):
        """Round 10 finding #1 remediation: both copies must return the
        same (refreshed, upgraded, created, skipped) tuple for the same
        input fixture — the version-stamp gate in main() depends on this."""
        original_modified = (
            f"lead\n{package_update.GATOR_BEGIN}\ndrift\n{package_update.GATOR_END}\ntail\n"
        )
        original_legacy = "# --- Gator Navigation Coding ---\nold\n"

        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        (pkg_dir / "CLAUDE.md").write_text(original_modified, encoding="utf-8")
        (pkg_dir / "AGENTS.md").write_text(original_legacy, encoding="utf-8")
        # GEMINI.md absent
        pkg_plan = package_update.plan_entry_point_updates(pkg_dir)
        pkg_counts = package_update.execute_entry_point_updates(pkg_dir, pkg_plan)

        tpl_dir = tmp_path / "tpl"
        tpl_dir.mkdir()
        (tpl_dir / "CLAUDE.md").write_text(original_modified, encoding="utf-8")
        (tpl_dir / "AGENTS.md").write_text(original_legacy, encoding="utf-8")
        tpl_plan = template_update.plan_entry_point_updates(tpl_dir)
        tpl_counts = template_update.execute_entry_point_updates(tpl_dir, tpl_plan)

        assert pkg_counts == tpl_counts
        # Sanity: 1 refreshed (CLAUDE), 1 upgraded (AGENTS), 1 created (GEMINI)
        assert pkg_counts == (1, 1, 1, 0)


# ---------------------------------------------------------------------------
# Layer 2 — JSON schema parity
# ---------------------------------------------------------------------------

class TestJSONSchemaParity:
    """Both copies must emit `"schema": "gator-update-v1"` and
    `entry_point_actions` at top level."""

    def test_package_json_shape(self, tmp_path, package_update, capsys):
        templates_dir = tmp_path / "t"
        templates_dir.mkdir()
        package_update.print_json_plan(plan=[], templates_dir=templates_dir, hooks=[], entry_point_actions=[])
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["schema"] == "gator-update-v1"
        assert "entry_point_actions" in parsed
        assert "summary" in parsed
        assert "entry_point_actions" in parsed["summary"]

    def test_template_json_shape(self, tmp_path, template_update, capsys):
        templates_dir = tmp_path / "t"
        templates_dir.mkdir()
        template_update.print_json_plan(plan=[], templates_dir=templates_dir, hooks=[], entry_point_actions=[])
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["schema"] == "gator-update-v1"
        assert "entry_point_actions" in parsed
        assert "summary" in parsed
        assert "entry_point_actions" in parsed["summary"]

    def test_both_copies_produce_identical_top_level_keys(
        self, tmp_path, package_update, template_update, capsys
    ):
        templates_dir = tmp_path / "t"
        templates_dir.mkdir()
        package_update.print_json_plan(plan=[], templates_dir=templates_dir, hooks=[], entry_point_actions=[])
        pkg_out = capsys.readouterr().out
        template_update.print_json_plan(plan=[], templates_dir=templates_dir, hooks=[], entry_point_actions=[])
        tpl_out = capsys.readouterr().out
        pkg = json.loads(pkg_out)
        tpl = json.loads(tpl_out)
        assert set(pkg.keys()) == set(tpl.keys())
        assert set(pkg["summary"].keys()) == set(tpl["summary"].keys())


# ---------------------------------------------------------------------------
# Layer 3 — AST-equivalence for inlined managed-block helpers
# ---------------------------------------------------------------------------

# The three functions whose bodies must byte-match between the canonical
# managed_block.py and the template gator-update.py that inlines them.
# Discovery is by function name — the plan permits this if implementation
# commits to keeping the names identical between copies (which we do —
# they are public API in managed_block.py and referenced by name in
# every caller).
_HELPERS_TO_COMPARE = ("find_managed_block", "classify_managed_block", "detect_legacy_gator_content")


def _find_function_body_dump(source_text, func_name):
    """Return `ast.dump()` of the function body, or None if not found."""
    tree = ast.parse(source_text)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            # Compare bodies only — arguments/decorators may differ across
            # copies without changing behavior of the helper.
            body_module = ast.Module(body=node.body, type_ignores=[])
            return ast.dump(body_module)
    return None


class TestASTEquivalenceOfInlinedHelpers:
    """The three parsing helpers inlined in the template gator-update.py
    must have byte-equivalent bodies (post-AST-dump) to the canonical
    definitions in gatorize/managed_block.py.

    Whitespace/comment changes are absorbed by ast.dump; real behavioral
    differences are not.
    """

    def setup_method(self):
        self.canonical_src = CANONICAL_MANAGED_BLOCK.read_text(encoding="utf-8")
        self.template_src = TEMPLATE_UPDATE.read_text(encoding="utf-8")

    @pytest.mark.parametrize("func_name", _HELPERS_TO_COMPARE)
    def test_body_matches_canonical(self, func_name):
        canonical_dump = _find_function_body_dump(self.canonical_src, func_name)
        template_dump = _find_function_body_dump(self.template_src, func_name)
        assert canonical_dump is not None, f"canonical missing {func_name}"
        assert template_dump is not None, f"template missing {func_name}"
        assert canonical_dump == template_dump, (
            f"{func_name} body drifted between canonical and template — "
            "AST-equivalence broken. Re-sync the inlined helper in "
            "src/gator_command/templates/gator-starter/scripts/gator-update.py."
        )
