"""
Tests for gator_layout.py — layout resolver and content classification.

Covers: v1/v2/mixed/invalid detection, GatorPaths resolution, content
family classification, and template-derived shipped file enumeration.
"""

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "src" / "gator_command" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import gator_layout


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def v1_repo(tmp_path):
    """Create a minimal v1 layout (flat, no .includes/)."""
    gator = tmp_path / ".gator"
    gator.mkdir()
    # Shipped content at root (v1 style)
    (gator / "constitution.md").write_text("# Constitution\n")
    (gator / "gator-start-up.md").write_text("# Startup\n")
    (gator / "scripts").mkdir()
    (gator / "scripts" / "gator_core.py").write_text("# core\n")
    (gator / "reference-notes").mkdir()
    (gator / "reference-notes" / "example.md").write_text("# example\n")
    # User content at root
    (gator / "mission.md").write_text("# Mission\n")
    (gator / "roadmap.md").write_text("# Roadmap\n")
    (gator / "charters").mkdir()
    (gator / "charters" / "core.md").write_text("# Core\n")
    (gator / "charters" / "README.md").write_text("# Charters\n")
    (gator / "charters" / "_template.md").write_text("# Template\n")
    (gator / "procedures").mkdir()
    (gator / "procedures" / "charter-alignment.md").write_text("# shipped\n")
    (gator / "procedures" / "my-custom-procedure.md").write_text("# user\n")
    (gator / "blueprints").mkdir()
    (gator / "blueprints" / "README.md").write_text("# shipped\n")
    # Runtime
    (gator / "whiteboard.md").write_text("# Whiteboard\n")
    (gator / "commit_draft.md").write_text("---\nmessage: \"\"\n---\n")
    (gator / "loops").mkdir()
    return tmp_path


@pytest.fixture
def v2_repo(tmp_path):
    """Create a minimal v2 layout (.includes/ for shipped content)."""
    gator = tmp_path / ".gator"
    gator.mkdir()
    includes = gator / ".includes"
    includes.mkdir()
    # Shipped content in .includes/
    (includes / "constitution.md").write_text("# Constitution\n")
    (includes / "gator-start-up.md").write_text("# Startup\n")
    (includes / "scripts").mkdir()
    (includes / "scripts" / "gator_core.py").write_text("# core\n")
    (includes / "reference-notes").mkdir()
    (includes / "reference-notes" / "example.md").write_text("# example\n")
    (includes / "procedures").mkdir()
    (includes / "procedures" / "charter-alignment.md").write_text("# shipped\n")
    (includes / "charters").mkdir()
    (includes / "charters" / "README.md").write_text("# Charters\n")
    (includes / "charters" / "_template.md").write_text("# Template\n")
    (includes / "blueprints").mkdir()
    (includes / "blueprints" / "README.md").write_text("# shipped\n")
    # User content at root
    (gator / "mission.md").write_text("# Mission\n")
    (gator / "roadmap.md").write_text("# Roadmap\n")
    (gator / "charters").mkdir()
    (gator / "charters" / "core.md").write_text("# Core\n")
    (gator / "procedures").mkdir()
    (gator / "procedures" / "my-custom-procedure.md").write_text("# user\n")
    (gator / "blueprints").mkdir()
    # Runtime
    (gator / "whiteboard.md").write_text("# Whiteboard\n")
    (gator / "commit_draft.md").write_text("---\nmessage: \"\"\n---\n")
    (gator / "loops").mkdir()
    # Layout version marker
    (gator / "layout-version.json").write_text(
        json.dumps({"layout": "v2"}) + "\n"
    )
    return tmp_path


@pytest.fixture
def mixed_repo(tmp_path):
    """Create a mixed layout (both flat and .includes/ locations)."""
    gator = tmp_path / ".gator"
    gator.mkdir()
    includes = gator / ".includes"
    includes.mkdir()
    # Shipped content in BOTH locations (mixed)
    (gator / "constitution.md").write_text("# Constitution (old)\n")
    (includes / "constitution.md").write_text("# Constitution (new)\n")
    (includes / "scripts").mkdir()
    (gator / "scripts").mkdir()  # legacy scripts still present
    # Version file says v2 but legacy content remains
    (gator / "layout-version.json").write_text(
        json.dumps({"layout": "v2"}) + "\n"
    )
    (gator / "mission.md").write_text("# Mission\n")
    return tmp_path


# ===========================================================================
# Layout detection
# ===========================================================================

class TestLayoutDetection:
    def test_v1_detected(self, v1_repo):
        """v1 layout detected when no .includes/ exists."""
        assert gator_layout.resolve_gator_layout(v1_repo) == "v1"

    def test_v2_detected(self, v2_repo):
        """v2 layout detected with .includes/ and version file."""
        assert gator_layout.resolve_gator_layout(v2_repo) == "v2"

    def test_mixed_detected(self, mixed_repo):
        """Mixed layout detected when both locations have shipped content."""
        assert gator_layout.resolve_gator_layout(mixed_repo) == "mixed"

    def test_invalid_no_gator_dir(self, tmp_path):
        """Invalid when .gator/ doesn't exist."""
        assert gator_layout.resolve_gator_layout(tmp_path) == "invalid"

    def test_invalid_v2_claimed_no_includes(self, tmp_path):
        """Invalid when version file claims v2 but .includes/ missing."""
        gator = tmp_path / ".gator"
        gator.mkdir()
        (gator / "layout-version.json").write_text('{"layout": "v2"}\n')
        assert gator_layout.resolve_gator_layout(tmp_path) == "invalid"

    def test_invalid_v2_empty_includes(self, tmp_path):
        """Invalid when v2 claimed but .includes/ is empty."""
        gator = tmp_path / ".gator"
        gator.mkdir()
        (gator / ".includes").mkdir()
        (gator / "layout-version.json").write_text('{"layout": "v2"}\n')
        assert gator_layout.resolve_gator_layout(tmp_path) == "invalid"

    def test_invalid_v2_no_scripts_in_includes(self, tmp_path):
        """Invalid when v2 claimed but .includes/ has no scripts/."""
        gator = tmp_path / ".gator"
        gator.mkdir()
        includes = gator / ".includes"
        includes.mkdir()
        (includes / "constitution.md").write_text("# c\n")
        # No scripts/ directory
        (gator / "layout-version.json").write_text('{"layout": "v2"}\n')
        assert gator_layout.resolve_gator_layout(tmp_path) == "invalid"

    def test_includes_without_version_is_mixed(self, tmp_path):
        """Mixed when .includes/ exists but no version file."""
        gator = tmp_path / ".gator"
        gator.mkdir()
        (gator / ".includes").mkdir()
        assert gator_layout.resolve_gator_layout(tmp_path) == "mixed"

    def test_mixed_detected_for_stale_shipped_procedures(self, tmp_path):
        """Mixed when shipped procedure exists in both flat root and .includes/."""
        gator = tmp_path / ".gator"
        gator.mkdir()
        includes = gator / ".includes"
        includes.mkdir()
        # Shipped procedure in both locations
        (gator / "procedures").mkdir()
        (gator / "procedures" / "charter-alignment.md").write_text("# old\n")
        (includes / "procedures").mkdir()
        (includes / "procedures" / "charter-alignment.md").write_text("# new\n")
        # Version file says v2
        (gator / "layout-version.json").write_text('{"layout": "v2"}\n')
        assert gator_layout.resolve_gator_layout(tmp_path) == "mixed"

    def test_mixed_when_shipped_at_root_only(self, tmp_path):
        """Mixed when shipped file at root but NOT in .includes/ (incomplete migration)."""
        gator = tmp_path / ".gator"
        gator.mkdir()
        includes = gator / ".includes"
        includes.mkdir()
        # Shipped procedure at root only — not migrated to .includes/
        (gator / "procedures").mkdir()
        (gator / "procedures" / "charter-alignment.md").write_text("# stale\n")
        # .includes/procedures/ doesn't exist or doesn't have this file
        (gator / "layout-version.json").write_text('{"layout": "v2"}\n')
        assert gator_layout.resolve_gator_layout(tmp_path) == "mixed"

    def test_v2_clean_when_user_files_remain_in_mixed_dirs(self, tmp_path):
        """v2 is clean when only user files remain in mixed directory roots."""
        gator = tmp_path / ".gator"
        gator.mkdir()
        includes = gator / ".includes"
        includes.mkdir()
        # Required .includes/ content
        (includes / "scripts").mkdir()
        (includes / "constitution.md").write_text("# Constitution\n")
        # User procedure at root (not shipped)
        (gator / "procedures").mkdir()
        (gator / "procedures" / "my-custom.md").write_text("# user\n")
        # Shipped procedures only in .includes/
        (includes / "procedures").mkdir()
        (includes / "procedures" / "charter-alignment.md").write_text("# shipped\n")
        # Version file
        (gator / "layout-version.json").write_text('{"layout": "v2"}\n')
        assert gator_layout.resolve_gator_layout(tmp_path) == "v2"

    def test_v2_clean_when_shipped_dir_has_only_scaffolding(self, tmp_path):
        """v2 is clean when a shipped directory at root holds ONLY scaffolding.

        Regression for the mixed-layout deadlock: `gator update` writes
        `reference-notes/{README.md,_template.md}` at the user-visible root
        (USER_VISIBLE_SCAFFOLDING), and the resolver then misread that as
        'mixed' — blocking every future update, with `--migrate-layout` unable
        to converge because it re-creates the same scaffolding.
        """
        gator = tmp_path / ".gator"
        gator.mkdir()
        includes = gator / ".includes"
        includes.mkdir()
        (includes / "scripts").mkdir()
        (includes / "constitution.md").write_text("# Constitution\n")
        (includes / "reference-notes").mkdir()
        (includes / "reference-notes" / "example.md").write_text("# shipped\n")
        # reference-notes/ at root holds ONLY scaffolding — must NOT trigger mixed
        (gator / "reference-notes").mkdir()
        (gator / "reference-notes" / "README.md").write_text("# readme\n")
        (gator / "reference-notes" / "_template.md").write_text("# tpl\n")
        (gator / "layout-version.json").write_text('{"layout": "v2"}\n')
        assert gator_layout.resolve_gator_layout(tmp_path) == "v2"

    def test_mixed_when_shipped_dir_has_real_content_at_root(self, tmp_path):
        """The scaffolding-only exemption must not mask a real mixed state.

        A shipped directory at root that holds a real (non-scaffolding) shipped
        file is still an incomplete migration → mixed.
        """
        gator = tmp_path / ".gator"
        gator.mkdir()
        includes = gator / ".includes"
        includes.mkdir()
        (includes / "scripts").mkdir()
        (includes / "constitution.md").write_text("# Constitution\n")
        # reference-notes/ at root has a REAL shipped note alongside scaffolding
        (gator / "reference-notes").mkdir()
        (gator / "reference-notes" / "README.md").write_text("# readme\n")
        (gator / "reference-notes" / "dangerous-patterns.md").write_text("# shipped\n")
        (gator / "layout-version.json").write_text('{"layout": "v2"}\n')
        assert gator_layout.resolve_gator_layout(tmp_path) == "mixed"


# ===========================================================================
# GatorPaths resolution
# ===========================================================================

class TestGatorPathsV1:
    def test_user_paths_at_root(self, v1_repo):
        """v1: user content resolves to .gator/ root."""
        paths = gator_layout.get_gator_paths(v1_repo)
        assert paths.layout == "v1"
        assert paths.mission == v1_repo / ".gator" / "mission.md"
        assert paths.charters_dir == v1_repo / ".gator" / "charters"
        assert paths.artifacts_dir == v1_repo / ".gator" / "artifacts"

    def test_shipped_paths_at_root(self, v1_repo):
        """v1: shipped content also at .gator/ root."""
        paths = gator_layout.get_gator_paths(v1_repo)
        assert paths.constitution == v1_repo / ".gator" / "constitution.md"
        assert paths.scripts_dir == v1_repo / ".gator" / "scripts"
        assert paths.reference_notes_dir == v1_repo / ".gator" / "reference-notes"

    def test_runtime_paths_at_root(self, v1_repo):
        """v1: runtime files at .gator/ root."""
        paths = gator_layout.get_gator_paths(v1_repo)
        assert paths.whiteboard == v1_repo / ".gator" / "whiteboard.md"
        assert paths.loops_dir == v1_repo / ".gator" / "loops"

    def test_convenience_properties(self, v1_repo):
        """v1: convenience properties correct."""
        paths = gator_layout.get_gator_paths(v1_repo)
        assert paths.is_v1_readable
        assert not paths.is_v2_readable
        assert paths.writes_allowed
        assert paths.migration_required
        assert not paths.mixed_paths


class TestGatorPathsV2:
    def test_user_paths_at_root(self, v2_repo):
        """v2: user content still at .gator/ root."""
        paths = gator_layout.get_gator_paths(v2_repo)
        assert paths.layout == "v2"
        assert paths.mission == v2_repo / ".gator" / "mission.md"
        assert paths.charters_dir == v2_repo / ".gator" / "charters"

    def test_shipped_paths_in_includes(self, v2_repo):
        """v2: shipped content resolves to .gator/.includes/."""
        paths = gator_layout.get_gator_paths(v2_repo)
        assert paths.constitution == v2_repo / ".gator" / ".includes" / "constitution.md"
        assert paths.scripts_dir == v2_repo / ".gator" / ".includes" / "scripts"
        assert paths.reference_notes_dir == v2_repo / ".gator" / ".includes" / "reference-notes"

    def test_runtime_stays_at_root(self, v2_repo):
        """v2: runtime files still at .gator/ root."""
        paths = gator_layout.get_gator_paths(v2_repo)
        assert paths.whiteboard == v2_repo / ".gator" / "whiteboard.md"
        assert paths.loops_dir == v2_repo / ".gator" / "loops"

    def test_convenience_properties(self, v2_repo):
        """v2: convenience properties correct."""
        paths = gator_layout.get_gator_paths(v2_repo)
        assert not paths.is_v1_readable
        assert paths.is_v2_readable
        assert paths.writes_allowed
        assert not paths.migration_required

    def test_includes_dir_set(self, v2_repo):
        """v2: includes_dir is populated."""
        paths = gator_layout.get_gator_paths(v2_repo)
        assert paths.includes_dir == v2_repo / ".gator" / ".includes"


class TestGatorPathsMixed:
    def test_shipped_prefers_includes(self, mixed_repo):
        """Mixed: shipped content prefers .includes/ when available."""
        paths = gator_layout.get_gator_paths(mixed_repo)
        assert paths.layout == "mixed"
        assert paths.constitution == mixed_repo / ".gator" / ".includes" / "constitution.md"

    def test_mixed_falls_back_per_path(self, tmp_path):
        """Mixed: each shipped path falls back individually to root."""
        gator = tmp_path / ".gator"
        gator.mkdir()
        includes = gator / ".includes"
        includes.mkdir()
        # constitution.md only at root (not in .includes/)
        (gator / "constitution.md").write_text("# root copy\n")
        # scripts/ only in .includes/
        (includes / "scripts").mkdir()
        (includes / "scripts" / "gator_core.py").write_text("# inc\n")
        # version file
        (gator / "layout-version.json").write_text('{"layout": "v2"}\n')

        paths = gator_layout.get_gator_paths(tmp_path)
        assert paths.layout == "mixed"
        # constitution falls back to root (not in .includes/)
        assert paths.constitution == gator / "constitution.md"
        # scripts resolves to .includes/ (exists there)
        assert paths.scripts_dir == includes / "scripts"

    def test_mixed_properties(self, mixed_repo):
        """Mixed: properties reflect diagnostic state."""
        paths = gator_layout.get_gator_paths(mixed_repo)
        assert paths.is_v1_readable
        assert paths.is_v2_readable
        assert not paths.writes_allowed
        assert paths.mixed_paths


# ===========================================================================
# Content classification
# ===========================================================================

class TestShippedFileClassification:
    def test_bootstrap_defaults(self):
        """Bootstrap defaults return known shipped files (not scaffolding)."""
        procs = gator_layout.get_shipped_files_for_directory("procedures")
        assert "charter-alignment.md" in procs
        assert "gator-loop-protocol.md" in procs
        # Scaffolding stays at root — not in shipped defaults
        assert "README.md" not in procs
        assert "_template.md" not in procs

    def test_template_derived(self, tmp_path):
        """Template-derived classification reads actual template directory."""
        template = tmp_path / "procedures"
        template.mkdir()
        (template / "shipped-a.md").write_text("# a\n")
        (template / "shipped-b.md").write_text("# b\n")

        result = gator_layout.get_shipped_files_for_directory(
            "procedures", template_source=tmp_path
        )
        assert result == frozenset({"shipped-a.md", "shipped-b.md"})

    def test_template_derived_overrides_defaults(self, tmp_path):
        """Template source takes precedence over bootstrap defaults."""
        template = tmp_path / "procedures"
        template.mkdir()
        (template / "only-this.md").write_text("# only\n")

        result = gator_layout.get_shipped_files_for_directory(
            "procedures", template_source=tmp_path
        )
        assert result == frozenset({"only-this.md"})
        assert "charter-alignment.md" not in result

    def test_missing_template_dir_falls_back(self):
        """Missing template directory falls back to bootstrap defaults."""
        result = gator_layout.get_shipped_files_for_directory(
            "procedures", template_source=Path("/nonexistent")
        )
        assert "charter-alignment.md" in result

    def test_unknown_directory_returns_empty(self):
        """Unknown directory name returns empty set."""
        result = gator_layout.get_shipped_files_for_directory("unknown_dir")
        assert result == frozenset()


class TestTemplateSourceResolution:
    def test_reads_product_source_with_gator_root(self, tmp_path):
        """Resolves template directory using gator_root + template_dir contract."""
        # Simulate real layout: gator_root points to a package dir,
        # template_dir is relative within it
        pkg_root = tmp_path / "src" / "gator_command"
        template_dir = pkg_root / "templates" / "gator-starter"
        template_dir.mkdir(parents=True)

        gator = tmp_path / ".gator"
        gator.mkdir()
        (gator / "product-source.json").write_text(
            json.dumps({
                "gator_root": str(pkg_root),
                "template_dir": "templates/gator-starter",
            }) + "\n"
        )

        result = gator_layout.resolve_template_source_for_layout(gator)
        assert result == template_dir

    def test_missing_product_source(self, tmp_path):
        """Returns None when product-source.json is missing."""
        gator = tmp_path / ".gator"
        gator.mkdir()
        result = gator_layout.resolve_template_source_for_layout(gator)
        assert result is None

    def test_invalid_json(self, tmp_path):
        """Returns None on corrupt product-source.json."""
        gator = tmp_path / ".gator"
        gator.mkdir()
        (gator / "product-source.json").write_text("not json")
        result = gator_layout.resolve_template_source_for_layout(gator)
        assert result is None

    def test_missing_gator_root_returns_none(self, tmp_path):
        """Returns None when gator_root is missing from product-source.json."""
        gator = tmp_path / ".gator"
        gator.mkdir()
        (gator / "product-source.json").write_text(
            json.dumps({"template_dir": "templates/gator-starter"}) + "\n"
        )
        result = gator_layout.resolve_template_source_for_layout(gator)
        assert result is None

    def test_nonexistent_template_dir_returns_none(self, tmp_path):
        """Returns None when resolved template directory doesn't exist."""
        gator = tmp_path / ".gator"
        gator.mkdir()
        (gator / "product-source.json").write_text(
            json.dumps({
                "gator_root": str(tmp_path),
                "template_dir": "nonexistent/path",
            }) + "\n"
        )
        result = gator_layout.resolve_template_source_for_layout(gator)
        assert result is None


# ===========================================================================
# Runtime files not classified as shipped
# ===========================================================================

class TestRuntimeNotShipped:
    def test_runtime_files_not_in_shipped(self):
        """Runtime files are not in the shipped sets."""
        for f in gator_layout.RUNTIME_FILES:
            assert f not in gator_layout.SHIPPED_ROOT_FILES
            assert f not in gator_layout.USER_ROOT_FILES

    def test_runtime_dirs_not_in_shipped(self):
        """Runtime directories are not in shipped or user directory sets."""
        for d in gator_layout.RUNTIME_DIRECTORIES:
            assert d not in gator_layout.SHIPPED_DIRECTORIES
            assert d not in gator_layout.USER_DIRECTORIES


# ===========================================================================
# Migration tests
# ===========================================================================

# Import gator-update via conftest helper
from conftest import load_script
_update = load_script("gator-update")


class TestMigration:
    def test_v1_to_v2(self, v1_repo):
        """Migrating a v1 repo yields a valid v2 repo."""
        report = _update.migrate_layout(v1_repo, v1_repo / ".gator", None)
        assert report["final_layout"] == "v2"
        assert report["source_layout"] == "v1"
        # Shipped content moved
        assert (v1_repo / ".gator" / ".includes" / "constitution.md").exists()
        assert (v1_repo / ".gator" / ".includes" / "scripts").is_dir()
        assert (v1_repo / ".gator" / ".includes" / "reference-notes").is_dir()
        # User content stays at root
        assert (v1_repo / ".gator" / "mission.md").exists()
        assert (v1_repo / ".gator" / "charters" / "core.md").exists()
        # Shipped root files no longer at root
        assert not (v1_repo / ".gator" / "constitution.md").exists()
        # Layout version marker written
        vf = v1_repo / ".gator" / "layout-version.json"
        assert vf.exists()
        assert json.loads(vf.read_text())["layout"] == "v2"

    def test_migration_idempotent(self, v1_repo):
        """Re-running migration on a v2 repo is a no-op."""
        _update.migrate_layout(v1_repo, v1_repo / ".gator", None)
        assert gator_layout.resolve_gator_layout(v1_repo) == "v2"
        # Run again
        report = _update.migrate_layout(v1_repo, v1_repo / ".gator", None)
        assert report["final_layout"] == "v2"
        assert len(report["moved"]) == 0

    def test_mixed_directory_splits(self, v1_repo):
        """Migration moves shipped files from mixed dirs, leaves user files."""
        report = _update.migrate_layout(v1_repo, v1_repo / ".gator", None)
        # User procedure stays at root
        assert (v1_repo / ".gator" / "procedures" / "my-custom-procedure.md").exists()
        # Shipped procedure moved to .includes/
        assert (v1_repo / ".gator" / ".includes" / "procedures" / "charter-alignment.md").exists()
        assert not (v1_repo / ".gator" / "procedures" / "charter-alignment.md").exists()

    def test_runtime_files_not_migrated(self, v1_repo):
        """Runtime files stay at root, never moved to .includes/."""
        _update.migrate_layout(v1_repo, v1_repo / ".gator", None)
        assert (v1_repo / ".gator" / "whiteboard.md").exists()
        assert (v1_repo / ".gator" / "commit_draft.md").exists()
        assert (v1_repo / ".gator" / "loops").is_dir()

    def test_v2_is_noop(self, v2_repo):
        """Migration on a v2 repo does nothing."""
        report = _update.migrate_layout(v2_repo, v2_repo / ".gator", None)
        assert report["final_layout"] == "v2"
        assert len(report["moved"]) == 0
