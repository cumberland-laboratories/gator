"""Validate `.gator/blueprints/*.html` files against gator-blueprint-html-v1.

The gator-blueprint-html-v1 protocol (shipped v2.12.0) defines the metadata
block, doc classes, and status vocabulary for HTML artifacts. This compat
test walks `.gator/blueprints/*.html` in the current repo and validates that
every file carries:

    - the schema meta tag with the exact value "gator-blueprint-html-v1"
    - a legal doc-class value (charter-map | feature-blueprint | procedure-visual | reference-explainer)
    - a legal status value (current | historical | exploratory | generated)
    - a well-formed updated-at (ISO-8601 UTC, seconds precision, Z suffix)
    - all required <meta> tags present

The test does NOT walk `.gator/vault/artifacts/*.html` (D6, r4-r5 pin): vault
is exploratory-by-design; artifacts there may be intentionally non-conformant
sketches. Manual review handles vault conformance.

Skips gracefully when the current repo has no `.gator/blueprints/*.html`
(the default state for fleet repos in Release A — only the Gator source
repo ships `charter-map.html`).

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


def _discover_blueprints():
    """Discover .html files under .gator/blueprints/ (non-recursive).

    Blueprints don't nest into subdirectories today; keep the check shallow
    to avoid accidentally validating vaulted or unrelated HTML.
    """
    if not BLUEPRINTS_DIR.is_dir():
        return []
    return sorted(BLUEPRINTS_DIR.glob("*.html"))


def _load(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# ── fixtures ────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def blueprint_files():
    files = _discover_blueprints()
    if not files:
        pytest.skip(
            "no .gator/blueprints/*.html in this repo — the default state "
            "for fleet repos in v2.12.0 Release A (only the Gator source "
            "repo ships charter-map.html)"
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
