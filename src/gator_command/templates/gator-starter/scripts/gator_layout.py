"""
Gator layout resolver — single source of truth for .gator/ path resolution.

Detects the repo's layout version (v1 flat, v2 .includes/, mixed, invalid)
and provides a GatorPaths object that resolves all paths correctly for the
detected layout. Every script that reads or writes .gator/ files should use
this resolver instead of hardcoding paths.

Layout versions:
  v1: flat — all content (user + shipped) under .gator/ root
  v2: split — user content at .gator/ root, shipped content in .gator/.includes/
  mixed: both old and new shipped locations exist (diagnostic only)
  invalid: .gator/ structure cannot be resolved
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Track whether v1 deprecation warning has been emitted this process
_v1_warning_emitted = False


# ---------------------------------------------------------------------------
# Content family classification (bootstrap defaults)
# ---------------------------------------------------------------------------

# These constants serve as bootstrap defaults when a template source is
# unavailable. The migration prefers template-derived lists when available.

SHIPPED_ROOT_FILES = frozenset({
    "constitution.md",
    "gator-start-up.md",
    ".charterignore",
})

# reference-notes moved to MIXED_DIRECTORY_SHIPPED_DEFAULTS 2026-08-23:
# the docs present root .gator/reference-notes/ as a USER content dir
# ("cognitive aids and vocabulary"), and treating it as fully-shipped made
# any user-authored note at root resolve the repo as "mixed" — which
# gator update refuses, permanently bricking updates for repos that did
# the documented thing (field case: cl-strategy). Per-filename shipped
# detection (like procedures/) is the correct model.
SHIPPED_DIRECTORIES = frozenset({
    "scripts",
})

# Scaffolding files that stay at the user-visible root even on v2.
# These are shipped by templates but serve as user-facing reference —
# agents look for _template.md and README.md when creating new content.
# v2.12.0: added _template.html + _template-narrative.html for the
# gator-blueprint-html-v1 protocol (interactive + narrative HTML templates
# under blueprints/). TRIPWIRE: additions must be filename-exact + paired
# with a tests/test_layout.py fixture. See scripts-layout.md charter.
USER_VISIBLE_SCAFFOLDING = frozenset({
    "README.md", "_template.md",
    "_template.html", "_template-narrative.html",
})

MIXED_DIRECTORY_SHIPPED_DEFAULTS = {
    "procedures": frozenset({
        "charter-alignment.md", "enforcer-review.md",
        "field-guide-generation.md", "knowledge-capture.md",
        "significance-check.md", "gator-loop-protocol.md",
        "architect-override.md",
    }),
    "charters": frozenset(),  # only scaffolding — stays at root
    "blueprints": frozenset(),  # only scaffolding — stays at root
    # Bootstrap fallback only — get_shipped_files_for_directory() prefers
    # the live template listing when a template source resolves. Keep in
    # sync with templates/gator-starter/reference-notes/ (scaffolding
    # README.md/_template.md excluded; USER_VISIBLE_SCAFFOLDING covers those).
    "reference-notes": frozenset({
        "concierge-responses.md", "dangerous-patterns.md",
        "dashboard-operations.md", "enforcer-configuration.md",
        "enforcer-prompt.md", "example-project.md",
        "expected-governance-residue.md",
        "failure-modes-and-self-correction.md", "git-workflow.md",
        "identity-and-ownership.md", "local-agent-skills.md",
        "loop-artifact-formats.md", "refactor-approach.md",
        "what-gator-requires-from-a-model.md",
        "why-navigation-coding-feels-different.md", "workflow-profiles.md",
    }),
}

USER_ROOT_FILES = frozenset({
    "mission.md", "roadmap.md", "inbox.md", "issues.md",
    "identity.md", "patterns.md", "pulse.md",
})

USER_DIRECTORIES = frozenset({
    "threads", "active-threads", "artifacts", "docs",
    "field-guides", "policies", "vault",
})

RUNTIME_FILES = frozenset({
    "whiteboard.md", "commit_draft.md", "status.json",
    "config.json", "product-source.json", "layout-version.json",
    "commit_issues.md", "lint-allow.json",
    ".gator-version", "active-vendor-session.json",
})

RUNTIME_DIRECTORIES = frozenset({
    "loops", "session-snippets", "session-blocks", "sessions",
})

LAYOUT_VERSION_FILE = "layout-version.json"
INCLUDES_DIR = ".includes"


# ---------------------------------------------------------------------------
# Layout detection
# ---------------------------------------------------------------------------

def resolve_gator_layout(repo_root):
    """Detect the layout version of a .gator/ directory.

    Returns one of: "v1", "v2", "mixed", "invalid".

    Detection rules (from the sketch):
      v1: .gator/ exists, .gator/.includes/ does not exist
      v2: .gator/.includes/ exists AND layout-version.json declares v2
      mixed: both old and new shipped locations exist for the same family
      invalid: structure cannot be resolved
    """
    repo_root = Path(repo_root)
    gator_dir = repo_root / ".gator"

    if not gator_dir.is_dir():
        return "invalid"

    includes_dir = gator_dir / INCLUDES_DIR
    version_file = gator_dir / LAYOUT_VERSION_FILE

    has_includes = includes_dir.is_dir()
    has_version = version_file.is_file()

    # Check version file content
    version_declared = None
    if has_version:
        try:
            data = json.loads(version_file.read_text(encoding="utf-8"))
            version_declared = data.get("layout")
        except (json.JSONDecodeError, OSError):
            pass

    # v2: .includes/ exists AND version file declares v2
    if has_includes and version_declared == "v2":
        # Check for mixed state: shipped content still in flat root
        if _has_legacy_shipped_content(gator_dir):
            return "mixed"
        # Check that required .includes/ content is present
        if not _has_required_includes_content(includes_dir):
            return "invalid"  # claims v2 but .includes/ is empty/incomplete
        return "v2"

    # v1: no .includes/ directory
    if not has_includes:
        if version_declared == "v2":
            return "invalid"  # claims v2 but no .includes/
        return "v1"

    # .includes/ exists but no version file or wrong version
    if has_includes and version_declared != "v2":
        return "mixed"  # partial migration

    return "invalid"


def _has_legacy_shipped_content(gator_dir):
    """Check if shipped content still exists in flat root locations.

    Used to detect mixed state on v2 repos. On a clean v2 repo, NO
    shipped content should exist at the flat .gator/ root — it should
    all be in .gator/.includes/. Any shipped content at root indicates
    either incomplete migration (mixed) or a broken state.

    Checks three categories:
    1. Shipped root files (constitution.md, gator-start-up.md, etc.)
    2. Fully shipped directories (scripts/, reference-notes/)
    3. Shipped files in mixed directories (procedures/, charters/, blueprints/)
       — any shipped default file at the flat root, regardless of whether
       it also exists in .includes/
    """
    # Root shipped files
    for fname in SHIPPED_ROOT_FILES:
        if (gator_dir / fname).is_file():
            return True
    # Fully shipped directories — but a directory that holds ONLY user-visible
    # scaffolding (README.md, _template.md) is NOT legacy content. gator update
    # and migrate_layout intentionally keep scaffolding at the user-visible root
    # (see USER_VISIBLE_SCAFFOLDING). Without this exemption a v2 repo whose
    # reference-notes/ contains only scaffolding is misclassified as "mixed" and
    # can never be updated again — the updater refuses mixed, and
    # --migrate-layout re-creates the same scaffolding, so it never converges.
    for dname in SHIPPED_DIRECTORIES:
        d = gator_dir / dname
        if d.is_dir() and not _dir_is_scaffolding_only(d):
            return True
    # Mixed directories: any shipped default file at the flat root
    # is legacy content that should have been moved to .includes/
    for dname, shipped_files in MIXED_DIRECTORY_SHIPPED_DEFAULTS.items():
        flat_dir = gator_dir / dname
        if not flat_dir.is_dir():
            continue
        for fname in shipped_files:
            if (flat_dir / fname).is_file():
                return True
    return False


def _dir_is_scaffolding_only(directory):
    """True if a directory contains only user-visible scaffolding (or is empty).

    A shipped directory at the flat .gator/ root that holds nothing but
    README.md / _template.md is not "legacy shipped content" — the migration
    deliberately keeps scaffolding at the user-visible root. Any other file, or
    any subdirectory, means real shipped/user content is present at root.
    """
    try:
        for entry in directory.iterdir():
            if entry.is_file() and entry.name in USER_VISIBLE_SCAFFOLDING:
                continue
            return False
    except OSError:
        return False
    return True


def _has_required_includes_content(includes_dir):
    """Check that .includes/ has minimum required shipped content.

    A valid v2 repo must have at least the scripts directory in .includes/.
    An empty or near-empty .includes/ indicates a broken install or
    incomplete migration.
    """
    if not includes_dir.is_dir():
        return False
    # Minimum: scripts/ dir (pre-Phase-4 repos: contains the pre-commit
    # hook) OR a runtime pin at the gator root (runtime-split Phase 4,
    # 2026-08-19: pinned repos run the machine-side runtime and
    # legitimately carry no repo-resident scripts).
    if not (includes_dir / "scripts").is_dir() and             not (includes_dir.parent / "runtime-pin.json").is_file():
        return False
    # Minimum: at least one shipped root file (constitution or startup)
    has_root_file = (
        (includes_dir / "constitution.md").is_file()
        or (includes_dir / "gator-start-up.md").is_file()
    )
    return has_root_file


# ---------------------------------------------------------------------------
# GatorPaths dataclass
# ---------------------------------------------------------------------------

@dataclass
class GatorPaths:
    """Resolved paths for all .gator/ content families.

    Constructed by get_gator_paths(). All path attributes are Path objects.
    The layout field indicates which version was detected.
    """
    # Metadata
    gator_root: Path
    layout: str  # "v1", "v2", "mixed", "invalid"
    includes_dir: Optional[Path]

    # User-authored root files (always at .gator/ root)
    mission: Path
    roadmap: Path
    inbox: Path
    issues: Path
    identity: Path
    patterns: Path
    pulse: Path

    # User-authored directories (always at .gator/ root)
    charters_dir: Path
    blueprints_dir: Path
    procedures_dir_user: Path
    threads_dir: Path
    active_threads_dir: Path
    artifacts_dir: Path
    docs_dir: Path
    field_guides_dir: Path
    policies_dir: Path
    vault_dir: Path

    # Shipped content (location depends on layout)
    constitution: Path
    startup_guide: Path
    charterignore: Path
    scripts_dir: Path
    procedures_dir_shipped: Path
    reference_notes_dir: Path
    charter_templates_dir: Path
    blueprint_templates_dir: Path

    # Runtime files (always at .gator/ root)
    whiteboard: Path
    commit_draft: Path
    status_json: Path
    config_json: Path
    product_source_json: Path
    layout_version_file: Path
    loops_dir: Path

    # Convenience helpers
    @property
    def is_v1_readable(self):
        return self.layout in ("v1", "mixed")

    @property
    def is_v2_readable(self):
        return self.layout in ("v2", "mixed")

    @property
    def writes_allowed(self):
        return self.layout in ("v1", "v2")

    @property
    def migration_required(self):
        return self.layout == "v1"

    @property
    def mixed_paths(self):
        return self.layout == "mixed"


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def get_gator_paths(repo_root):
    """Resolve all .gator/ paths for the detected layout.

    Returns a GatorPaths object. On v1, shipped content resolves to flat
    .gator/ root. On v2, shipped content resolves to .gator/.includes/.
    On mixed, each shipped path is resolved individually: prefer .includes/
    if the specific file or directory exists there, fall back to root.
    """
    repo_root = Path(repo_root)
    gator_dir = repo_root / ".gator"
    layout = resolve_gator_layout(repo_root)

    includes_dir = gator_dir / INCLUDES_DIR if layout in ("v2", "mixed") else None

    def _shipped_file(name):
        """Resolve a shipped file path based on layout."""
        if layout == "v2":
            return gator_dir / INCLUDES_DIR / name
        if layout == "mixed":
            inc_path = gator_dir / INCLUDES_DIR / name
            if inc_path.exists():
                return inc_path
            return gator_dir / name  # fall back to root
        return gator_dir / name  # v1 or invalid

    def _shipped_dir(name):
        """Resolve a shipped directory path based on layout."""
        if layout == "v2":
            return gator_dir / INCLUDES_DIR / name
        if layout == "mixed":
            inc_path = gator_dir / INCLUDES_DIR / name
            if inc_path.is_dir():
                return inc_path
            return gator_dir / name  # fall back to root
        return gator_dir / name  # v1 or invalid

    paths = GatorPaths(
        # Metadata
        gator_root=gator_dir,
        layout=layout,
        includes_dir=includes_dir,

        # User-authored root files (always at .gator/ root)
        mission=gator_dir / "mission.md",
        roadmap=gator_dir / "roadmap.md",
        inbox=gator_dir / "inbox.md",
        issues=gator_dir / "issues.md",
        identity=gator_dir / "identity.md",
        patterns=gator_dir / "patterns.md",
        pulse=gator_dir / "pulse.md",

        # User-authored directories (always at .gator/ root)
        charters_dir=gator_dir / "charters",
        blueprints_dir=gator_dir / "blueprints",
        procedures_dir_user=gator_dir / "procedures",
        threads_dir=gator_dir / "threads",
        active_threads_dir=gator_dir / "active-threads",
        artifacts_dir=gator_dir / "artifacts",
        docs_dir=gator_dir / "docs",
        field_guides_dir=gator_dir / "field-guides",
        policies_dir=gator_dir / "policies",
        vault_dir=gator_dir / "vault",

        # Shipped content (layout-dependent, per-path fallback on mixed)
        constitution=_shipped_file("constitution.md"),
        startup_guide=_shipped_file("gator-start-up.md"),
        charterignore=_shipped_file(".charterignore"),
        scripts_dir=_shipped_dir("scripts"),
        procedures_dir_shipped=_shipped_dir("procedures"),
        reference_notes_dir=_shipped_dir("reference-notes"),
        charter_templates_dir=_shipped_dir("charters"),
        blueprint_templates_dir=_shipped_dir("blueprints"),

        # Runtime files (always at .gator/ root)
        whiteboard=gator_dir / "whiteboard.md",
        commit_draft=gator_dir / "commit_draft.md",
        status_json=gator_dir / "status.json",
        config_json=gator_dir / "config.json",
        product_source_json=gator_dir / "product-source.json",
        layout_version_file=gator_dir / LAYOUT_VERSION_FILE,
        loops_dir=gator_dir / "loops",
    )

    # Emit one-time v1 deprecation warning per process
    global _v1_warning_emitted
    if layout == "v1" and not _v1_warning_emitted:
        _v1_warning_emitted = True
        print(
            "  Note: this repo uses the legacy v1 layout. "
            "Run 'gator update --migrate-layout' to upgrade to v2.",
            file=sys.stderr,
        )

    return paths


# ---------------------------------------------------------------------------
# Template-derived shipped file classification
# ---------------------------------------------------------------------------

def get_shipped_files_for_directory(dir_name, template_source=None):
    """Determine which files in a mixed directory are shipped.

    If template_source is provided (path to the gator-starter template
    directory), enumerates the actual template files. Otherwise falls
    back to MIXED_DIRECTORY_SHIPPED_DEFAULTS.

    Returns a frozenset of filenames.
    """
    if template_source:
        template_dir = Path(template_source) / dir_name
        if template_dir.is_dir():
            return frozenset(
                f.name for f in template_dir.iterdir()
                if f.is_file()
            )

    # Bootstrap default
    return MIXED_DIRECTORY_SHIPPED_DEFAULTS.get(dir_name, frozenset())


def resolve_template_source_for_layout(gator_dir):
    """Resolve the template source directory for migration classification.

    Reads product-source.json and follows the existing contract:
    the template path is gator_root + template_dir (template_dir is
    relative to gator_root). Returns the template directory path or
    None if unavailable.
    """
    ps_file = Path(gator_dir) / "product-source.json"
    if not ps_file.is_file():
        return None

    try:
        data = json.loads(ps_file.read_text(encoding="utf-8"))
        gator_root = data.get("gator_root")
        template_dir = data.get("template_dir")
        if not gator_root or not template_dir:
            return None
        # Contract: template path = gator_root / template_dir
        resolved = Path(gator_root) / template_dir
        if resolved.is_dir():
            return resolved
    except (json.JSONDecodeError, OSError):
        pass

    return None
