"""Computed-style + rendered-layout checks for the Cumberland master.

Codex enforcer follow-up 2026-09-13 F2 + F4: the Slice-4
`test_cumberland_visual_invariants.py` module asserts CSS source
text — regex against the raw template bytes — which does NOT catch:

    - Layout regressions the browser's rendering engine surfaces
      (e.g., the 375×667 horizontal overflow Codex measured: sample
      table 471px inside 335px content box → whole page scrolls).
    - Cascade / specificity mistakes that leave a rule in the source
      but overridden at compute time.
    - Font-metric-derived values that depend on `rem` resolution
      (h1 at 1.85rem is only ~29.6px if the root font-size is the
      browser default).

These are computed-style / rendered-layout assertions, NOT pixel
snapshots. Pixel snapshots (full-page image diffs) are the surface
Codex Sketch 2 explicitly ruled out for OS font-rendering variance;
computed-style is a numeric/string invariant that stays stable across
platforms because the browser normalizes the values before returning
them to `getComputedStyle()`.

Coverage:
    - 375×667 (narrow viewport): the wrapped-table safety net holds —
      `documentElement.scrollWidth <= innerWidth`.
    - 1440×900 (wide viewport): computed anchor values match the
      reference-file typographic decisions — h1 fontSize ≈ 29.6px,
      body maxWidth 1120px, body padding "32px 20px", header
      border-bottom color rgb(25, 174, 184) [= #19aeb8 teal].

The test navigates via `file://` — no HTTP server needed. Playwright's
`page` fixture is provided by pytest-playwright (already a dev
dependency).
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urljoin
from urllib.request import pathname2url

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

REPO_ROOT = Path(__file__).resolve().parents[2]

MASTER = (REPO_ROOT / "src" / "gator_command" / "templates"
          / "gator-starter" / "reference-notes"
          / "cumberland-html-document-template.html")


def _file_url(path: Path) -> str:
    return urljoin("file:", pathname2url(str(path.resolve())))


@pytest.fixture(scope="module")
def master_url() -> str:
    if not MASTER.is_file():
        pytest.skip(f"master template not present at {MASTER}")
    return _file_url(MASTER)


# ── F2: narrow-viewport overflow safety net ──────────────────────

def test_no_horizontal_overflow_at_375px(page, master_url):
    """At the 375×667 mobile viewport (iPhone SE class),
    `documentElement.scrollWidth` must not exceed `window.innerWidth`.
    Codex enforcer 2026-09-13 F2 measured the pre-fix state:
    scrollWidth 491 vs innerWidth 375 (the sample table was 471px
    inside a 335px content box; table's `overflow: hidden` gave rounded
    corners but no local scroll container, so the whole page scrolled).
    Fix landed the `.table-wrap` component + wrapped the sample tables.
    """
    page.set_viewport_size({"width": 375, "height": 667})
    page.goto(master_url, wait_until="load")
    metrics = page.evaluate("""
        () => ({
            scrollWidth: document.documentElement.scrollWidth,
            innerWidth: window.innerWidth,
        })
    """)
    assert metrics["scrollWidth"] <= metrics["innerWidth"], (
        f"Horizontal overflow at 375px: "
        f"scrollWidth={metrics['scrollWidth']} > "
        f"innerWidth={metrics['innerWidth']}. Slice-4 F2 fix "
        f"regressed — check the .table-wrap component and the body "
        f"sample tables.")


def test_sample_table_is_wrapped_in_table_wrap(page, master_url):
    """At any viewport, the sample table in the master body must have
    a `.table-wrap` ancestor. Companion to the invariant pin — this
    catches an HTML-level regression (someone unwraps the sample)
    that would still pass the CSS-source assertion in
    `test_cumberland_visual_invariants.py::test_master_body_uses_table_wrap`
    if that pin were removed."""
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(master_url, wait_until="load")
    has_wrapped_table = page.evaluate("""
        () => {
            const tables = document.querySelectorAll('table');
            return Array.from(tables).some(
                t => t.closest('.table-wrap') !== null);
        }
    """)
    assert has_wrapped_table, (
        "Master body has no <table> inside .table-wrap — the sample "
        "table lost its wrap")


# ── F4: computed-style anchors at wide viewport ──────────────────

def test_computed_h1_font_size_at_1440px(page, master_url):
    """h1 at 1.85rem should compute to ~29.6px with the default root
    font-size (16px). This locks the reference-file decision (Slice 1
    bumped from the pre-Cumberland 1.75rem/28px) at RENDER time, not
    just in CSS source."""
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(master_url, wait_until="load")
    h1_size = page.evaluate("""
        () => {
            const h1 = document.querySelector('header.doc-head h1');
            return window.getComputedStyle(h1).fontSize;
        }
    """)
    # 1.85rem @ 16px root = 29.6px. Browsers return "29.6px" as a string.
    assert h1_size == "29.6px", (
        f"h1 fontSize computed to {h1_size!r}, expected '29.6px' "
        f"(1.85rem @ 16px root)")


def test_computed_body_padding_and_max_width_at_1440px(page, master_url):
    """Body computed padding should be 32px 20px (2rem 1.25rem);
    max-width 1120px. These pin the layout envelope the reference file
    established."""
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(master_url, wait_until="load")
    body_style = page.evaluate("""
        () => {
            const s = window.getComputedStyle(document.body);
            return {
                paddingTop: s.paddingTop,
                paddingRight: s.paddingRight,
                paddingBottom: s.paddingBottom,
                paddingLeft: s.paddingLeft,
                maxWidth: s.maxWidth,
            };
        }
    """)
    assert body_style["paddingTop"] == "32px", (
        f"body padding-top: {body_style['paddingTop']!r}, expected '32px'")
    assert body_style["paddingRight"] == "20px", (
        f"body padding-right: {body_style['paddingRight']!r}, expected '20px'")
    assert body_style["paddingBottom"] == "32px", (
        f"body padding-bottom: {body_style['paddingBottom']!r}, expected '32px'")
    assert body_style["paddingLeft"] == "20px", (
        f"body padding-left: {body_style['paddingLeft']!r}, expected '20px'")
    assert body_style["maxWidth"] == "1120px", (
        f"body max-width: {body_style['maxWidth']!r}, expected '1120px'")


def test_computed_header_border_bottom_is_teal(page, master_url):
    """The header's 3px bottom border must resolve to the teal palette
    token (#19aeb8 = rgb(25, 174, 184)). Regression pin against a
    silent palette rewire in the header rule."""
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(master_url, wait_until="load")
    border = page.evaluate("""
        () => {
            const h = document.querySelector('header.doc-head');
            const s = window.getComputedStyle(h);
            return {
                width: s.borderBottomWidth,
                style: s.borderBottomStyle,
                color: s.borderBottomColor,
            };
        }
    """)
    assert border["width"] == "3px", (
        f"header border-bottom-width: {border['width']!r}, expected '3px'")
    assert border["style"] == "solid", (
        f"header border-bottom-style: {border['style']!r}, expected 'solid'")
    assert border["color"] == "rgb(25, 174, 184)", (
        f"header border-bottom-color: {border['color']!r}, "
        f"expected 'rgb(25, 174, 184)' (teal #19aeb8)")


def test_computed_paragraph_text_align_is_justify(page, master_url):
    """Body prose renders justified — the reference-file typographic
    decision. Verify at RENDER time, not just in CSS source (a cascade
    override in a future style rule would slip past the source-text
    pin)."""
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(master_url, wait_until="load")
    text_align = page.evaluate("""
        () => {
            // Grab a paragraph inside a section (not inside a callout,
            // TOC, or figure — those are the override contexts).
            const p = document.querySelector('section > p');
            return p ? window.getComputedStyle(p).textAlign : null;
        }
    """)
    assert text_align == "justify", (
        f"section > p text-align computed to {text_align!r}, "
        f"expected 'justify'")
