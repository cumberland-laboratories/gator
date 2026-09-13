"""Visual-invariant checks for the Cumberland HTML style (Codex Sketch 2 Slice 4).

The Slice-3 parity check pins the master's CSS core byte-for-byte to the
narrative-Blueprint specialization, but a byte-diff alone would happily
accept a well-formed edit that silently removed (say) the purple palette
or the justified-body rule. This test walks the master's CSS + body and
asserts the load-bearing visual invariants are still present.

Method: string / regex assertions against the raw template text. No
PIXEL SNAPSHOTS — those introduce OS font-rendering variance (Windows
vs macOS vs Linux subpixel-metric differences that vary between browser
versions) and Codex Sketch 2 explicitly ruled them out. Computed-style
checks (values from `getComputedStyle()` in a real browser) live in
`test_cumberland_computed_style.py` — they are NOT pixel snapshots and
are a separate acceptance surface.

Invariants covered:
  - PALETTE: all 6 hue tokens + their `-dark` (for teal/blue) + `-light`
    variants + full gray scale (9 steps).
  - CALLOUTS: all 6 variants (default/note/info/warn/ok/data) styled with
    both background + border-left-color rules AND a label-color rule.
  - PILLS: all 6 variants (ok/info/warn/alt/data/na).
  - STATUS BADGES: 4 status variants (default green, exploratory, generated,
    historical).
  - TYPOGRAPHY: h1 at 1.85rem, letter-spacing -0.01em on h1, body prose
    with `text-align: justify` + `hyphens: auto`, selective left-align
    overrides for figure captions / footer / TOC entries.
  - COMPONENTS: `.figure`, `.diagram-node.purple` (Slice-1 addition),
    `.steps` counter-based numbering, `.toc` block, `pre code` reset.
  - BODY EXAMPLES: master's body has at least one visible example of every
    component so authors can copy-modify.

Skips gracefully when the master is absent (fleet repo before first update).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

MASTER = (REPO_ROOT / "src" / "gator_command" / "templates"
          / "gator-starter" / "reference-notes"
          / "cumberland-html-document-template.html")


REGION_RE = re.compile(
    r'/\*\s*CUMBERLAND-NARRATIVE-STYLE:BEGIN'
    r'.*?'
    r'CUMBERLAND-NARRATIVE-STYLE:END[^*]*\*/',
    re.DOTALL,
)


@pytest.fixture(scope="module")
def master_text() -> str:
    if not MASTER.is_file():
        pytest.skip("Cumberland master not present (fleet repo pre-first-update)")
    return MASTER.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def shared_region(master_text: str) -> str:
    match = REGION_RE.search(master_text)
    assert match is not None, (
        f"{MASTER}: shared region markers not found — parity check "
        f"should catch this first")
    return match.group(0)


# ── Palette ───────────────────────────────────────────────────────

PALETTE_TOKENS = {
    "--teal":         "#19aeb8",
    "--teal-dark":    "#148a92",
    "--red":          "#d94040",
    "--blue":         "#4a72b0",
    "--blue-dark":    "#385a90",
    "--amber":        "#d48b0a",
    "--green":        "#2d8a4e",
    "--purple":       "#6b46c1",
    "--gray-50":      "#f9fafb",
    "--gray-100":     "#f3f4f6",
    "--gray-200":     "#e5e7eb",
    "--gray-300":     "#d1d5db",
    "--gray-400":     "#9ca3af",
    "--gray-600":     "#4b5563",
    "--gray-700":     "#374151",
    "--gray-800":     "#1f2937",
    "--gray-900":     "#111827",
}


@pytest.mark.parametrize("token, value", sorted(PALETTE_TOKENS.items()))
def test_palette_token_defined_with_exact_value(
        shared_region: str, token: str, value: str):
    """Each palette token declares its exact hex value in :root.
    A silent hue drift (e.g., someone brightening teal) would fail here.
    """
    pattern = re.compile(
        rf'{re.escape(token)}\s*:\s*{re.escape(value)}\s*;',
        re.IGNORECASE)
    assert pattern.search(shared_region), (
        f"Palette token {token} missing or drifted from {value!r} "
        f"in the shared region")


LIGHT_WASH_HUES = ("teal", "red", "blue", "amber", "green", "purple")


@pytest.mark.parametrize("hue", LIGHT_WASH_HUES)
def test_light_wash_variant_defined(shared_region: str, hue: str):
    """Every hue has an 8%-alpha `-light` companion for surface fills.
    Missing a `-light` variant breaks the callout / pill / diagram
    background rules downstream.
    """
    pattern = re.compile(
        rf'--{hue}-light\s*:\s*rgba\s*\(',
        re.IGNORECASE)
    assert pattern.search(shared_region), (
        f"--{hue}-light variant missing in the shared region")


# ── Callouts (6 variants) ─────────────────────────────────────────

CALLOUT_VARIANTS = ["warn", "info", "ok", "note", "data"]


def test_callout_default_styled(shared_region: str):
    """The default `.callout` (teal) declares background + border-left."""
    assert re.search(
        r'\.callout\s*\{[^}]*background:\s*var\(--teal-light\)',
        shared_region, re.DOTALL), (
        "default .callout background rule missing")
    assert re.search(
        r'\.callout\s*\{[^}]*border-left:\s*4px\s+solid\s+var\(--teal\)',
        shared_region, re.DOTALL), (
        "default .callout border-left rule missing")


@pytest.mark.parametrize("variant", CALLOUT_VARIANTS)
def test_callout_variant_styled(shared_region: str, variant: str):
    """Each of the 5 non-default callout variants sets background,
    border-left-color, AND a label color."""
    bg = re.search(
        rf'\.callout\.{variant}\s*\{{[^}}]*background:\s*var\(',
        shared_region, re.DOTALL)
    border = re.search(
        rf'\.callout\.{variant}\s*\{{[^}}]*border-left-color:\s*var\(',
        shared_region, re.DOTALL)
    label = re.search(
        rf'\.callout\.{variant}\s+\.label\s*\{{[^}}]*color:\s*var\(',
        shared_region, re.DOTALL)
    assert bg, f".callout.{variant}: background rule missing"
    assert border, f".callout.{variant}: border-left-color rule missing"
    assert label, f".callout.{variant} .label: color rule missing"


def test_callout_data_uses_purple(shared_region: str):
    """The Slice-1 purple insight variant specifically pairs with
    --purple. Regression pin against someone accidentally rewiring
    .callout.data to a different hue."""
    match = re.search(
        r'\.callout\.data\s*\{[^}]*background:\s*var\(--purple-light\)'
        r'[^}]*border-left-color:\s*var\(--purple\)',
        shared_region, re.DOTALL)
    assert match, (
        ".callout.data must pair --purple-light background with "
        "--purple border")


# ── Pills (6 variants) ────────────────────────────────────────────

PILL_VARIANTS = ["ok", "info", "warn", "alt", "data", "na"]


@pytest.mark.parametrize("variant", PILL_VARIANTS)
def test_pill_variant_styled(shared_region: str, variant: str):
    """Each pill variant declares background + color."""
    pattern = re.compile(
        rf'\.pill\.{variant}\s*\{{[^}}]*background:\s*[^;]+;\s*'
        rf'color:\s*var\(',
        re.DOTALL)
    assert pattern.search(shared_region), (
        f".pill.{variant} styling missing")


# ── Status badges ─────────────────────────────────────────────────

STATUS_BADGE_VARIANTS = ["exploratory", "generated", "historical"]


def test_status_badge_default_current(shared_region: str):
    """Default status-badge (no class modifier) is green/current."""
    assert re.search(
        r'\.status-badge\s*\{[^}]*background:\s*var\(--green-light\)',
        shared_region, re.DOTALL), (
        "default .status-badge (current) missing green-light background")


@pytest.mark.parametrize("variant", STATUS_BADGE_VARIANTS)
def test_status_badge_variant_defined(shared_region: str, variant: str):
    """The three non-default status variants each have their own rule."""
    pattern = re.compile(
        rf'\.status-badge\.{variant}\s*\{{[^}}]*background:',
        re.DOTALL)
    assert pattern.search(shared_region), (
        f".status-badge.{variant} rule missing")


# ── Typography (the reference-file decisions) ─────────────────────

def test_h1_size_and_tracking(shared_region: str):
    """h1 renders at 1.85rem with -0.01em tracking (reference-file
    decision, not the narrower template's 1.75rem+no-tracking).
    Regression pin: reverting to the narrower h1 would fail here."""
    match = re.search(
        r'header\.doc-head\s+h1\s*\{[^}]*'
        r'font-size:\s*1\.85rem[^}]*'
        r'letter-spacing:\s*-0\.01em',
        shared_region, re.DOTALL)
    assert match, (
        "header.doc-head h1 must set font-size: 1.85rem AND "
        "letter-spacing: -0.01em")


def test_body_paragraph_is_justified_with_hyphens(shared_region: str):
    """Body prose (paragraph-level) uses justified text with automatic
    hyphenation — the reference file's most load-bearing typographic
    decision. A regression to left-flush prose would fail here."""
    match = re.search(
        r'\bp\s*\{[^}]*text-align:\s*justify[^}]*hyphens:\s*auto',
        shared_region, re.DOTALL)
    assert match, (
        "Body `p` selector must set `text-align: justify` AND "
        "`hyphens: auto`")


def test_subtitle_is_justified_with_hyphens(shared_region: str):
    """Header subtitle uses the same justified + hyphenated typography."""
    match = re.search(
        r'header\.doc-head\s+\.subtitle\s*\{[^}]*'
        r'text-align:\s*justify[^}]*hyphens:\s*auto',
        shared_region, re.DOTALL)
    assert match, (
        "header.doc-head .subtitle must set text-align: justify AND "
        "hyphens: auto")


def test_narrow_context_left_align_overrides(shared_region: str):
    """Figure captions, footer prose, and TOC entries opt out of the
    justified body rule via a single override rule. Missing this
    override causes short-line contexts to justify-stretch across
    three or four words — the reference file explicitly handles this."""
    match = re.search(
        r'\.figure\s+\.caption,\s*'
        r'footer\.doc-foot\s+p,\s*'
        r'\.toc\s+p\s*\{[^}]*'
        r'text-align:\s*left[^}]*'
        r'hyphens:\s*manual',
        shared_region, re.DOTALL)
    assert match, (
        "Selective left-align override for .figure .caption / "
        "footer.doc-foot p / .toc p is missing")


# ── Structural components ────────────────────────────────────────

def test_figure_block_defined(shared_region: str):
    """The `.figure` block for hand-authored SVG diagrams. Reference-
    file addition; not present in the pre-Slice-1 narrative template."""
    assert re.search(r'\.figure\s*\{[^}]*background:\s*white',
                     shared_region, re.DOTALL), (
        ".figure block declaration missing")
    assert re.search(r'\.figure\s+svg\s*\{[^}]*margin:\s*0\s+auto',
                     shared_region, re.DOTALL), (
        ".figure svg centering rule missing")
    assert re.search(
        r'\.figure\s+\.caption\s*\{[^}]*text-align:\s*center'
        r'[^}]*font-style:\s*italic',
        shared_region, re.DOTALL), (
        ".figure .caption: centered italic rule missing")


def test_diagram_node_purple_variant(shared_region: str):
    """Slice-1 extended the diagram-node palette with .purple for
    symmetry with .callout.data / .pill.data. Regression pin against
    someone dropping .purple to keep the palette 'insight-only'."""
    match = re.search(
        r'\.diagram-node\.purple\s*\{[^}]*'
        r'border-color:\s*var\(--purple\)[^}]*'
        r'background:\s*var\(--purple-light\)[^}]*'
        r'color:\s*var\(--purple\)',
        shared_region, re.DOTALL)
    assert match, (
        ".diagram-node.purple must set border-color / background / "
        "color to the purple palette tokens")


def test_steps_counter_and_4_variants(shared_region: str):
    """Numbered steps use CSS counter with 4 color variants (default
    teal + .step-alt blue + .step-warn red + .step-done green)."""
    assert re.search(r'\.steps\s*\{[^}]*counter-reset:\s*step',
                     shared_region, re.DOTALL), (
        ".steps counter-reset missing")
    for variant in ("alt", "warn", "done"):
        pattern = re.compile(
            rf'\.steps\s*>\s*li\.step-{variant}::before\s*\{{[^}}]*'
            rf'background:\s*var\(',
            re.DOTALL)
        assert pattern.search(shared_region), (
            f".steps > li.step-{variant}::before variant missing")


def test_pre_code_reset(shared_region: str):
    """Nested <code> inside <pre> resets background/padding/rounding
    so it doesn't render as double-boxed. Template-file addition;
    reference file omitted this rule."""
    match = re.search(
        r'pre\s+code\s*\{[^}]*background:\s*none[^}]*'
        r'padding:\s*0[^}]*border-radius:\s*0',
        shared_region, re.DOTALL)
    assert match, (
        "pre code reset (background:none + padding:0 + border-radius:0) "
        "missing")


def test_toc_component_defined(shared_region: str):
    """TOC card with blue-left-border + uppercase heading."""
    assert re.search(
        r'\.toc\s*\{[^}]*border-left:\s*3px\s+solid\s+var\(--blue\)',
        shared_region, re.DOTALL), (
        ".toc blue left-border missing")


# ── Delimiter contract (Slice 3 shape) ───────────────────────────

def test_delimiter_markers_line_up_within_style_block(master_text: str):
    """The BEGIN and END markers must live INSIDE a single <style>
    block. If a future edit moves either marker outside the
    <style>...</style> span, the parity check still passes textually
    but the CSS is no longer scoped correctly."""
    style_match = re.search(r'<style>(.*?)</style>', master_text, re.DOTALL)
    assert style_match, "Master: <style> block not found"
    style_body = style_match.group(1)
    assert "CUMBERLAND-NARRATIVE-STYLE:BEGIN" in style_body, (
        "BEGIN marker is outside the <style> block")
    assert "CUMBERLAND-NARRATIVE-STYLE:END" in style_body, (
        "END marker is outside the <style> block")


# ── Body examples (author-facing scaffolding) ────────────────────

def test_body_has_visible_example_of_each_callout_variant(master_text: str):
    """The master's body ships one visible example of each callout
    variant so authors see the vocabulary at hand. Missing an example
    would degrade the template as authoring scaffolding — the whole
    point is 'grab-and-fill', not 'read the CSS to find out what's
    available'."""
    for variant in ("", ".note", ".info", ".warn", ".ok", ".data"):
        if variant:
            selector = f'class="callout {variant[1:]}"'
        else:
            selector = 'class="callout"'
        assert selector in master_text, (
            f"Master body missing visible example of {selector!r}")


def test_table_wrap_component_defined(shared_region: str):
    """`.table-wrap` is the narrow-viewport safety net: wraps a wide
    table in its own overflow-x scroll container so a mobile viewport
    doesn't force the whole page to scroll horizontally. Codex
    enforcer follow-up 2026-09-13 F2 landed this after measuring a
    concrete overflow at 375×667 (documentElement.scrollWidth==491
    vs innerWidth==375; sample table was ~471px inside ~335px
    content box).
    """
    match = re.search(
        r'\.table-wrap\s*\{[^}]*overflow-x:\s*auto',
        shared_region, re.DOTALL)
    assert match, (
        ".table-wrap component missing overflow-x: auto — narrow-viewport "
        "overflow safety net is not in place")
    # Sanity: the wrap must also reset the child table's margin so
    # spacing above/below comes from the wrap, not the table.
    reset = re.search(
        r'\.table-wrap\s+table\s*\{[^}]*margin:\s*0',
        shared_region, re.DOTALL)
    assert reset, (
        ".table-wrap table { margin: 0 } reset missing — child table's "
        "own margin would compound with the wrap's")


def test_master_body_uses_table_wrap(master_text: str):
    """The master's body sample table must be wrapped so authors see
    the wrap-by-default pattern in the shipped scaffolding. Missing
    wrap here means every fleet-repo author who copy-modifies the
    sample gets an unwrapped table and re-exposes the F2 overflow."""
    assert 'class="table-wrap"' in master_text, (
        "Master body sample table is not wrapped in .table-wrap — "
        "authors will inherit the pre-F2 overflow pattern")


# ── Self-containment (F4 + broadened by 2026-09-13 F3) ────────────
#
# The Cumberland contract is broader than "no external stylesheet and
# no external script" — it forbids EVERY resource-fetching reference
# to an outside host or a sibling file. Regression guards must cover:
#
#   HTML resource-loading elements:
#     <link rel="stylesheet" href="…">
#     <link rel="icon"/…>        (any <link> that isn't a nav hint)
#     <script src="…">
#     <img src="…">              (unless src is `data:` or `#`)
#     <iframe src="…">
#     <video src="…">, <audio src="…">, <source src="…">, <track src="…">
#     <object data="…">, <embed src="…">
#
#   CSS references (in <style> blocks OR inline style="…"):
#     @import "…" / @import url(…)
#     url(…) property values referencing anything not `data:`
#
# Allowed forms:
#   * `<a href="…">` navigation (does not fetch at load).
#   * `data:` URIs (self-contained inline).
#   * `#anchor` fragments (in-document nav).
#   * Empty `""` / `#` placeholders.
#
# The two guards below share a helper that scans text for every
# violation and returns a list — a single failure message names
# every remaining hit, so an author sees the whole surface at once.

_RESOURCE_URL_ATTR_ELEMENTS = (
    # (tag, attr) pairs whose value is a URL that IS fetched at load.
    ("script", "src"),
    ("img", "src"),
    ("iframe", "src"),
    ("video", "src"),
    ("audio", "src"),
    ("source", "src"),
    ("track", "src"),
    ("embed", "src"),
    ("object", "data"),
    ("input", "src"),  # <input type="image" src="…">
)


def _url_is_self_contained(url: str) -> bool:
    """True if the URL is safe to keep inside a self-contained
    artifact: data URI, in-document fragment, or empty placeholder.
    Everything else (http, https, //, ftp, file, sibling path, bare
    filename) is external and must be rejected."""
    url = url.strip()
    if not url:
        return True
    if url.startswith("#"):
        return True
    if url.lower().startswith("data:"):
        return True
    return False


def _find_external_html_resources(text: str):
    """Yield (tag, attr, url, position) for every HTML resource-loading
    attribute that references an external target. Case-insensitive tag
    match; attribute value in single or double quotes."""
    violations = []
    for tag, attr in _RESOURCE_URL_ATTR_ELEMENTS:
        pat = re.compile(
            rf'<{tag}\b[^>]*?\b{attr}\s*=\s*["\']([^"\']*)["\']',
            re.IGNORECASE)
        for match in pat.finditer(text):
            url = match.group(1)
            if not _url_is_self_contained(url):
                violations.append((tag, attr, url, match.start()))

    # <link> is a special case — allow ONLY nav-hint rel values that
    # do not fetch resources (e.g. author, help). Reject any <link>
    # with href pointing anywhere external, regardless of rel — the
    # safe posture is "no external <link> at all in self-contained
    # artifacts."
    link_pat = re.compile(
        r'<link\b[^>]*?\bhref\s*=\s*["\']([^"\']*)["\'][^>]*>',
        re.IGNORECASE)
    for match in link_pat.finditer(text):
        url = match.group(1)
        if not _url_is_self_contained(url):
            violations.append(("link", "href", url, match.start()))

    return violations


def _find_external_css_resources(text: str):
    """Yield (kind, url, position) for every CSS `@import` and every
    `url(…)` reference to an external target. Scans <style> blocks;
    ignores inline `style="…"` attributes (they're rare in these
    templates and would need a different quoting escape). Both
    quoted and unquoted url() forms are matched."""
    violations = []
    style_pat = re.compile(r'<style\b[^>]*>(.*?)</style>',
                           re.IGNORECASE | re.DOTALL)
    for style_match in style_pat.finditer(text):
        css_body = style_match.group(1)
        style_start = style_match.start(1)

        # @import "…" / @import '…' / @import url(…)
        import_pat = re.compile(
            r'@import\s+(?:url\s*\(\s*)?["\']?([^"\')\s;]*)["\']?',
            re.IGNORECASE)
        for m in import_pat.finditer(css_body):
            url = m.group(1)
            if not _url_is_self_contained(url):
                violations.append(
                    ("@import", url, style_start + m.start()))

        # url(…) — any property. Skip data:, http-less, and fragment.
        url_pat = re.compile(
            r'\burl\s*\(\s*["\']?([^"\')\s]+)["\']?\s*\)',
            re.IGNORECASE)
        for m in url_pat.finditer(css_body):
            url = m.group(1)
            if not _url_is_self_contained(url):
                violations.append(
                    ("url()", url, style_start + m.start()))

    return violations


@pytest.fixture(scope="module")
def narrative_text() -> str:
    narrative = (REPO_ROOT / ".gator" / "blueprints"
                 / "_template-narrative.html")
    if not narrative.is_file():
        pytest.skip("narrative Blueprint scaffolding-root not present")
    return narrative.read_text(encoding="utf-8")


def test_master_is_fully_self_contained(master_text: str):
    """The master must contain no external resource references —
    stylesheets, scripts, images, iframes, media sources, embeds,
    objects, CSS @import, or CSS url() targeting anything outside
    the file. `<a href>` navigation is explicitly allowed (it does
    not fetch at load); `data:` URIs and `#fragment` anchors are
    self-contained.

    Codex enforcer 2026-09-13 F3 broadened this from the original
    two-attribute check to the full resource surface. The earlier
    narrow guard would pass a template that added `<img
    src="https://…">` or CSS `url(https://cdn.example/font.woff2)`.
    """
    html_violations = _find_external_html_resources(master_text)
    css_violations = _find_external_css_resources(master_text)
    assert not html_violations and not css_violations, (
        f"Master is not fully self-contained.\n"
        f"  HTML resource violations: {html_violations!r}\n"
        f"  CSS resource violations:  {css_violations!r}")


def test_narrative_is_fully_self_contained(narrative_text: str):
    """Same self-containment surface applied to the narrative
    Blueprint. Both anchor templates ship with all CSS inline and no
    external resource references."""
    html_violations = _find_external_html_resources(narrative_text)
    css_violations = _find_external_css_resources(narrative_text)
    assert not html_violations and not css_violations, (
        f"Narrative Blueprint is not fully self-contained.\n"
        f"  HTML resource violations: {html_violations!r}\n"
        f"  CSS resource violations:  {css_violations!r}")


def test_self_containment_helper_catches_known_forms():
    """Meta-pin: exercise the helper against synthesized violations
    so a bug in the pattern regex is visible immediately (rather
    than manifesting as a false-negative on a real template).
    Ensures the helper actually detects each violation class the
    contract lists.
    """
    fixture = """<!DOCTYPE html>
<html>
<head>
<link rel="stylesheet" href="https://cdn.example.com/x.css">
<script src="//example.org/foo.js"></script>
<style>
@import "https://external.example/lib.css";
body { background: url("https://cdn.example/bg.png"); }
</style>
</head>
<body>
<img src="https://example.com/logo.png">
<iframe src="/other.html"></iframe>
<video src="./local.mp4"></video>
<a href="https://example.com/">nav OK</a>
<a href="#anchor">nav OK</a>
<img src="data:image/png;base64,abc">
</body>
</html>"""
    html_v = _find_external_html_resources(fixture)
    css_v = _find_external_css_resources(fixture)
    detected = {(kind, url) for kind, _, url, _ in html_v}
    detected |= {(kind, url) for kind, url, _ in css_v}
    # Expected: link+href, script+src, img+src, iframe+src, video+src,
    # @import, url()
    assert ("link", "https://cdn.example.com/x.css") in detected
    assert ("script", "//example.org/foo.js") in detected
    assert ("img", "https://example.com/logo.png") in detected
    assert ("iframe", "/other.html") in detected
    assert ("video", "./local.mp4") in detected
    assert ("@import", "https://external.example/lib.css") in detected
    assert ("url()", "https://cdn.example/bg.png") in detected
    # Allowed forms must NOT be detected:
    for tag, attr, url, _ in html_v:
        assert not url.startswith("data:"), (
            f"data: URI incorrectly flagged: {tag} {attr}={url!r}")
    # <a href> is not in _RESOURCE_URL_ATTR_ELEMENTS so it's never
    # scanned; if it were, the two `<a>` entries above would appear.
    assert not any("a" == kind for kind, _, _, _ in html_v), (
        "<a href> should be allowed but the helper flagged it")


def test_body_has_figure_diagram_steps_and_table_examples(master_text: str):
    """The master's body has one visible example of each major
    component: figure (SVG), diagram (flexbox flowchart), steps
    (counter list), colored table."""
    assert 'class="figure"' in master_text, (
        "Master body missing .figure example")
    assert 'class="diagram"' in master_text, (
        "Master body missing .diagram example")
    assert 'class="steps"' in master_text, (
        "Master body missing .steps example")
    assert 'class="table-blue"' in master_text or \
           'class="table-red"' in master_text or \
           'class="table-teal"' in master_text, (
        "Master body missing a colored table variant example")
