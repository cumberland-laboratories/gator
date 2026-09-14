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
NARRATIVE = (REPO_ROOT / ".gator" / "blueprints"
             / "_template-narrative.html")


def _file_url(path: Path) -> str:
    return urljoin("file:", pathname2url(str(path.resolve())))


@pytest.fixture(scope="module")
def master_url() -> str:
    if not MASTER.is_file():
        pytest.skip(f"master template not present at {MASTER}")
    return _file_url(MASTER)


# Two canonical Cumberland templates the mobile checks parametrize
# over. Codex enforcer 2026-09-13 F4: existential "any table wrapped"
# on master alone would miss a narrative-body regression that ships
# an unwrapped table (narrative body is outside the parity-checked
# shared CSS region). Both bodies get equal treatment.
_NARROW_VIEWPORT_TARGETS = [
    ("master", MASTER),
    ("narrative", NARRATIVE),
]


def _url_for(name_and_path):
    _, path = name_and_path
    if not path.is_file():
        pytest.skip(f"{path} not present")
    return _file_url(path)


# ── F2 + F4: narrow-viewport overflow safety net ─────────────────

@pytest.mark.parametrize("name, path", _NARROW_VIEWPORT_TARGETS,
                         ids=[t[0] for t in _NARROW_VIEWPORT_TARGETS])
def test_no_horizontal_overflow_at_375px(page, name, path):
    """At the 375×667 mobile viewport (iPhone SE class),
    `documentElement.scrollWidth` must not exceed `window.innerWidth`.
    Codex enforcer 2026-09-13 F2 measured the pre-fix state on the
    master: scrollWidth 491 vs innerWidth 375 (the sample table was
    471px inside a 335px content box; table's `overflow: hidden` gave
    rounded corners but no local scroll container, so the whole page
    scrolled). Fix landed the `.table-wrap` component + wrapped the
    sample tables.

    F4 extension (2026-09-13): parametrize over master AND narrative.
    Narrative body is outside the parity-checked shared region so a
    regression could add or unwrap a narrative table alone.
    """
    if not path.is_file():
        pytest.skip(f"{path} not present")
    page.set_viewport_size({"width": 375, "height": 667})
    page.goto(_file_url(path), wait_until="load")
    metrics = page.evaluate("""
        () => ({
            scrollWidth: document.documentElement.scrollWidth,
            innerWidth: window.innerWidth,
        })
    """)
    assert metrics["scrollWidth"] <= metrics["innerWidth"], (
        f"Horizontal overflow at 375px in {name} template ({path.name}): "
        f"scrollWidth={metrics['scrollWidth']} > "
        f"innerWidth={metrics['innerWidth']}. Check the .table-wrap "
        f"component and every <table> in the body.")


@pytest.mark.parametrize("name, path", _NARROW_VIEWPORT_TARGETS,
                         ids=[t[0] for t in _NARROW_VIEWPORT_TARGETS])
def test_every_table_has_table_wrap_ancestor(page, name, path):
    """UNIVERSAL variant of the wrap-check (Codex enforcer 2026-09-13
    F4). Every `<table>` in the rendered body must have a `.table-wrap`
    ancestor. Existential "any table wrapped" — the prior shape —
    passes when someone adds an UNWRAPPED table alongside a wrapped
    one, silently reintroducing the F2 overflow class.
    """
    if not path.is_file():
        pytest.skip(f"{path} not present")
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(_file_url(path), wait_until="load")
    unwrapped = page.evaluate("""
        () => {
            const tables = document.querySelectorAll('table');
            return Array.from(tables)
                .filter(t => t.closest('.table-wrap') === null)
                .map(t => {
                    // best-effort identifier for the failure message
                    const heading = t.previousElementSibling
                        && /^h[1-6]$/i.test(t.previousElementSibling.tagName)
                        ? t.previousElementSibling.textContent.trim().slice(0, 40)
                        : null;
                    return {
                        totalTables: tables.length,
                        heading: heading,
                        firstCellText: (t.querySelector('td, th')?.textContent
                            || '').trim().slice(0, 40),
                    };
                });
        }
    """)
    assert unwrapped == [], (
        f"{name} template ({path.name}) has {len(unwrapped)} unwrapped "
        f"<table>(s). Every table must live inside a .table-wrap "
        f"ancestor so wide tables scroll locally instead of forcing "
        f"page-level horizontal overflow. Unwrapped tables: {unwrapped!r}")


@pytest.mark.parametrize("name, path", _NARROW_VIEWPORT_TARGETS,
                         ids=[t[0] for t in _NARROW_VIEWPORT_TARGETS])
def test_oversize_tables_have_scrolling_wrapper(page, name, path):
    """When a table's natural width exceeds its wrapper's clientWidth
    (the narrow-viewport case), the `.table-wrap` MUST provide
    horizontal scrolling — `wrap.scrollWidth > wrap.clientWidth`
    with `overflow-x: auto` computed. Any table that meets the
    oversized condition without the scroll affordance is a functional
    regression even if page-level scrollWidth stays contained (a
    truncated-then-clipped table is worse than a scrollable one).

    Codex enforcer 2026-09-13 F4 recommended this positive-behavior
    pin alongside the universal-wrap negative pin: prove the wrap
    actually WORKS on the oversized case, not just that it exists.
    """
    if not path.is_file():
        pytest.skip(f"{path} not present")
    page.set_viewport_size({"width": 375, "height": 667})
    page.goto(_file_url(path), wait_until="load")
    oversized_diagnostics = page.evaluate("""
        () => {
            const wraps = document.querySelectorAll('.table-wrap');
            const diagnostics = [];
            for (const wrap of wraps) {
                const table = wrap.querySelector('table');
                if (!table) continue;
                const isOversized = table.scrollWidth > wrap.clientWidth;
                if (!isOversized) continue;
                const style = window.getComputedStyle(wrap);
                diagnostics.push({
                    tableScrollWidth: table.scrollWidth,
                    wrapClientWidth: wrap.clientWidth,
                    wrapScrollWidth: wrap.scrollWidth,
                    overflowX: style.overflowX,
                    scrolls: wrap.scrollWidth > wrap.clientWidth,
                });
            }
            return diagnostics;
        }
    """)
    for d in oversized_diagnostics:
        assert d["overflowX"] == "auto", (
            f"{name} template ({path.name}): oversize .table-wrap "
            f"has overflow-x={d['overflowX']!r}, expected 'auto'. "
            f"Diagnostic: {d!r}")
        assert d["scrolls"], (
            f"{name} template ({path.name}): oversize .table-wrap "
            f"is not actually scrollable "
            f"(wrap.scrollWidth={d['wrapScrollWidth']} <= "
            f"wrap.clientWidth={d['wrapClientWidth']}). "
            f"Diagnostic: {d!r}")


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


@pytest.mark.parametrize("name, path", _NARROW_VIEWPORT_TARGETS,
                         ids=[t[0] for t in _NARROW_VIEWPORT_TARGETS])
def test_template_makes_no_external_requests_at_load(page, name, path):
    """Browser-level backstop for the self-containment guarantee
    (Codex enforcer 2026-09-14 round-8). The textual scanner in
    `test_cumberland_visual_invariants.py` covers a broad HTML +
    CSS surface, but Codex has repeatedly found narrow browser-
    driven forms the scanner initially missed (unquoted attrs,
    srcset data URIs with commas, SVG hrefs, CSS hex escapes,
    iframe srcdoc, `<base href>`, meta-refresh — seven rounds of
    findings). The scanner is fast and named, but the DEFINITIVE
    check is: does the browser actually make any external request?

    This pin routes every request in Chromium; anything that
    isn't a `file://` URL is recorded as an external fetch and
    aborted. After load, zero external requests must have been
    observed. If a future edit introduces any form the textual
    scanner doesn't yet cover, this pin catches it at the exact
    layer that matters — the layer that would make the shipped
    document actually leak.
    """
    if not path.is_file():
        pytest.skip(f"{path} not present")
    external_urls = []

    def handle_route(route):
        url = route.request.url
        if url.startswith("file:"):
            route.continue_()
        else:
            external_urls.append(url)
            route.abort()

    page.route("**/*", handle_route)
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(_file_url(path), wait_until="networkidle")
    # Grace period for any late/deferred fetches (fonts, lazy
    # images, meta-refresh timers) to fire.
    page.wait_for_timeout(200)

    assert external_urls == [], (
        f"{name} template ({path.name}) made external requests at "
        f"load — self-containment guarantee broken. External URLs:\n"
        + "\n".join(f"  {u}" for u in external_urls))


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
