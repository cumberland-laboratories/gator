"""Validate `.gator/blueprints/*.html` files against gator-blueprint-html-v1.

The gator-blueprint-html-v1 protocol (shipped v2.12.0) defines the metadata
block, doc classes, and status vocabulary for HTML artifacts. This compat
test walks `.gator/blueprints/*.html` in the current repo and validates that
every real artifact carries:

    - the schema meta tag with the exact value "gator-blueprint-html-v1"
    - a legal doc-class value (charter-map | feature-blueprint | procedure-visual | reference-explainer)
    - a legal status value (current | historical | exploratory | generated)
    - a well-formed updated-at (ISO-8601 UTC, seconds precision, Z suffix)
    - all required <meta> tags present

Scaffolding files are excluded from validation. The `USER_VISIBLE_SCAFFOLDING`
set in `gator_layout.py` lands `_template.html` and `_template-narrative.html`
at `.gator/blueprints/` on v2 repos so agents find them when authoring — those
files ship with `==TODO==` placeholders and illegal placeholder meta values
by design. Discovery filters them out (see `SCAFFOLDING_FILENAMES`) so the
compat check runs against real published artifacts only.

The test does NOT walk `.gator/vault/artifacts/*.html` (D6, r4-r5 pin): vault
is exploratory-by-design; artifacts there may be intentionally non-conformant
sketches. Manual review handles vault conformance.

Skips gracefully when the current repo has no non-scaffolding
`.gator/blueprints/*.html` (the default state for fleet repos in Release A —
only the Gator source repo ships `charter-map.html`).

No jsonschema dependency; the protocol is HTML-defined so regex + string
matching is the natural check.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BLUEPRINTS_DIR = REPO_ROOT / ".gator" / "blueprints"

SCHEMA_TAG = "gator-blueprint-html-v1"

LEGAL_DOC_CLASSES = {
    "charter-map",
    "feature-blueprint",
    "procedure-visual",
    "reference-explainer",
}

LEGAL_STATUSES = {
    "current",
    "historical",
    "exploratory",
    "generated",
}

SCAFFOLDING_FILENAMES = frozenset({
    "_template.html",
    "_template-narrative.html",
})

REQUIRED_META = (
    "gator-schema",
    "gator-title",
    "gator-repo",
    "gator-doc-class",
    "gator-status",
    "gator-updated-at",
    "gator-generated-by",
    "gator-question",
)

ISO8601_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

META_TAG_RE = re.compile(
    r'<meta\s+name=["\']gator-([a-z-]+)["\']\s+content=["\']([^"\']*)["\']\s*/?>',
    re.IGNORECASE,
)


def _extract_meta(html: str) -> dict:
    """Return a dict of gator-* meta name → content value."""
    out = {}
    for match in META_TAG_RE.finditer(html):
        name = "gator-" + match.group(1).lower()
        out[name] = match.group(2)
    return out


def _discover_blueprints(root: Path | None = None):
    """Discover real .html artifacts under .gator/blueprints/ (non-recursive).

    Blueprints don't nest into subdirectories today; keep the check shallow
    to avoid accidentally validating vaulted or unrelated HTML.

    Filenames in `SCAFFOLDING_FILENAMES` are excluded — those are authoring
    templates that live at the user-visible root by design (see
    `USER_VISIBLE_SCAFFOLDING` in `gator_layout.py`) and carry `==TODO==`
    placeholders + illegal placeholder meta values that a real artifact must
    replace. Validating them would fail every fleet repo the moment it
    scaffolded, before any real artifact exists.

    `root` defaults to the module-level `BLUEPRINTS_DIR` (the current repo's
    `.gator/blueprints/`). Tests pass a temporary directory to exercise
    discovery in isolation.
    """
    target = root if root is not None else BLUEPRINTS_DIR
    if not target.is_dir():
        return []
    return sorted(
        p for p in target.glob("*.html")
        if p.name not in SCAFFOLDING_FILENAMES
    )


def _load(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# ── fixtures ────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def blueprint_files():
    files = _discover_blueprints()
    if not files:
        pytest.skip(
            "no non-scaffolding .gator/blueprints/*.html in this repo — the "
            "default state for fleet repos in v2.12.0 Release A (only the "
            "Gator source repo ships charter-map.html; scaffolding templates "
            "are excluded from the compat check by design)"
        )
    return files


# ── structural tests ────────────────────────────────────────────────────


class TestBlueprintHtmlSchemaConformance:
    """Every .gator/blueprints/*.html file must satisfy gator-blueprint-html-v1."""

    def test_files_carry_schema_tag(self, blueprint_files):
        for path in blueprint_files:
            meta = _extract_meta(_load(path))
            assert meta.get("gator-schema") == SCHEMA_TAG, (
                f"{path.name} missing or wrong schema tag; got "
                f"{meta.get('gator-schema')!r}, expected {SCHEMA_TAG!r}"
            )

    def test_files_carry_all_required_meta(self, blueprint_files):
        for path in blueprint_files:
            meta = _extract_meta(_load(path))
            missing = [name for name in REQUIRED_META if name not in meta]
            assert not missing, (
                f"{path.name} missing required <meta> tags: {missing}"
            )

    def test_doc_class_is_legal(self, blueprint_files):
        for path in blueprint_files:
            meta = _extract_meta(_load(path))
            got = meta.get("gator-doc-class")
            assert got in LEGAL_DOC_CLASSES, (
                f"{path.name} has illegal doc-class {got!r}; "
                f"legal values: {sorted(LEGAL_DOC_CLASSES)}"
            )

    def test_status_is_legal(self, blueprint_files):
        for path in blueprint_files:
            meta = _extract_meta(_load(path))
            got = meta.get("gator-status")
            assert got in LEGAL_STATUSES, (
                f"{path.name} has illegal status {got!r}; "
                f"legal values: {sorted(LEGAL_STATUSES)}"
            )

    def test_updated_at_is_iso8601_z(self, blueprint_files):
        for path in blueprint_files:
            meta = _extract_meta(_load(path))
            got = meta.get("gator-updated-at", "")
            assert ISO8601_Z.match(got), (
                f"{path.name} has malformed gator-updated-at {got!r}; "
                "expected ISO-8601 UTC seconds-precision Z-suffix "
                "(e.g. 2026-09-02T14:00:00Z)"
            )

    def test_no_todo_placeholders_remain(self, blueprint_files):
        """Authors must fill every ==TODO== marker before publishing to
        `.gator/blueprints/`. The templates ship with placeholders; if any
        survive in a shipped file, the artifact isn't ready."""
        for path in blueprint_files:
            html = _load(path)
            assert "==TODO==" not in html, (
                f"{path.name} still contains ==TODO== placeholders; "
                "fill or delete them before publishing"
            )


class TestBlueprintHtmlSelfContained:
    """gator-blueprint-html-v1 protocol §Styling invariants: self-contained."""

    def test_no_external_stylesheets(self, blueprint_files):
        # Reject <link rel="stylesheet" href="http[s]://..."> or any http(s):// href
        # in a stylesheet link. Allow relative refs (there shouldn't be any).
        pattern = re.compile(
            r'<link\s+[^>]*rel=["\']stylesheet["\'][^>]*href=["\']https?://',
            re.IGNORECASE,
        )
        for path in blueprint_files:
            html = _load(path)
            assert not pattern.search(html), (
                f"{path.name} pulls a stylesheet from an external URL; "
                "gator-blueprint-html-v1 requires self-contained artifacts"
            )

    def test_no_external_scripts(self, blueprint_files):
        # Reject <script src="http[s]://...">
        pattern = re.compile(
            r'<script\s+[^>]*src=["\']https?://',
            re.IGNORECASE,
        )
        for path in blueprint_files:
            html = _load(path)
            assert not pattern.search(html), (
                f"{path.name} loads a script from an external URL; "
                "gator-blueprint-html-v1 requires self-contained artifacts"
            )


class TestBlueprintHtmlDiscovery:
    """Regression pin against silently losing the discovery surface."""

    def test_gator_source_repo_ships_charter_map(self):
        """The Gator source repo carries `charter-map.html` under the new
        protocol (v2.12.0 reference implementation). Fleet repos won't have
        this file — the test only asserts when we're running in the Gator
        source repo (detected by presence of the file itself, i.e. this test
        is a "if you ship it, it must exist" pin, not a "you must ship it" pin)."""
        charter_map = BLUEPRINTS_DIR / "charter-map.html"
        if not charter_map.is_file():
            pytest.skip(
                "no charter-map.html in this repo — fleet repos hand-author "
                "their own via _template.html + authoring procedure"
            )
        # Sanity: it must be discovered by _discover_blueprints
        assert charter_map in _discover_blueprints()


class TestBlueprintHtmlScaffoldingExclusion:
    """Scaffolding templates (`_template.html`, `_template-narrative.html`)
    land at `.gator/blueprints/` on v2 repos as USER_VISIBLE_SCAFFOLDING. They
    carry `==TODO==` placeholders and illegal placeholder meta values by
    design. Discovery MUST exclude them, or every gatorized fleet repo would
    fail the compat check the moment `gator update` scaffolds those files.

    This class pins the exclusion contract — a regression would surface here
    before it broke every fleet repo's compat run."""

    def test_scaffolding_filenames_set_matches_layout_contract(self):
        """`SCAFFOLDING_FILENAMES` here must cover every HTML entry in
        `USER_VISIBLE_SCAFFOLDING` from `gator_layout.py`. If the layout set
        grows with a new HTML template, this test also grows — the
        cross-module rule is: any HTML scaffolding filename must be excluded
        from the compat walk."""
        assert "_template.html" in SCAFFOLDING_FILENAMES
        assert "_template-narrative.html" in SCAFFOLDING_FILENAMES

    def test_discovery_excludes_scaffolding_when_present(self, tmp_path):
        """Simulated fleet-repo layout: scaffolding templates present, no
        real artifact. Discovery must return empty (which causes the fixture
        to skip cleanly)."""
        fake_blueprints = tmp_path / ".gator" / "blueprints"
        fake_blueprints.mkdir(parents=True)
        (fake_blueprints / "_template.html").write_text(
            "<html><meta name='gator-doc-class' content='==TODO=='></html>",
            encoding="utf-8",
        )
        (fake_blueprints / "_template-narrative.html").write_text(
            "<html><meta name='gator-doc-class' content='==TODO=='></html>",
            encoding="utf-8",
        )
        assert _discover_blueprints(root=fake_blueprints) == []

    def test_discovery_includes_real_artifact_alongside_scaffolding(self, tmp_path):
        """Simulated fleet-repo layout after the user authors a real
        blueprint: scaffolding still present, plus one hand-authored artifact.
        Discovery must return only the real artifact."""
        fake_blueprints = tmp_path / ".gator" / "blueprints"
        fake_blueprints.mkdir(parents=True)
        (fake_blueprints / "_template.html").write_text("<html></html>", encoding="utf-8")
        (fake_blueprints / "_template-narrative.html").write_text(
            "<html></html>", encoding="utf-8"
        )
        real = fake_blueprints / "my-charter-map.html"
        real.write_text("<html></html>", encoding="utf-8")
        assert _discover_blueprints(root=fake_blueprints) == [real]
