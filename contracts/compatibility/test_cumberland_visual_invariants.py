"""Visual invariants + bounded self-containment for the Cumberland
HTML templates.

## Two concerns, one module

**Visual invariants** — palette hex values, callout/pill/status
variants, typography (justified body, `.figure`, `.steps`,
`.diagram-node.purple`, `.toc`, `.table-wrap`, etc.). These
regression-guard the reference-file typography decisions against a
well-formed edit that silently rewired a token. Method: regex
assertions against the source text of the shared CSS region;
computed-style checks live in the companion module.

**Bounded self-containment** — a small POSITIVE policy that
validates the shipped templates use only approved passive markup,
plus a pinned Content-Security-Policy `<meta>` in both templates.
This replaces eleven rounds of parser-based blacklist scanners
(2026-09-13 through 2026-09-14) — Codex's round-12 whiteboard
recommended closure via a bounded guarantee rather than continued
whack-a-mole on browser-input shapes. See the block comment
starting `── Bounded self-containment guarantee ──` below for the
exact scoped claim and the three-layer defense composition.

Skips gracefully when the master is absent (fleet repo pre-first-
update).
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


# ── Bounded self-containment guarantee (Codex closure, round-12) ──
#
# Eleven parser-focused enforcer rounds converged on a partial
# reimplementation of browser HTML/CSS/URL semantics. Codex round-12
# recommended CLOSURE via three moves:
#
#   1. Narrow the guarantee to a bounded claim about the SHIPPED
#      Cumberland templates, not arbitrary user-edited HTML.
#   2. Replace the expanding blacklist scanner with a small POSITIVE
#      policy — only the tags and attributes the templates actually
#      use are allowed; everything else is rejected.
#   3. Add a Content-Security-Policy `<meta>` tag as browser-enforced
#      defense in depth.
#
# THE GUARANTEE (round-13 F1 refined):
#
#     The two checked-in Cumberland templates contain only approved
#     passive HTML, carry the pinned CSP that denies external
#     resource loading, and produce no non-template network
#     requests during Chromium's initial load.
#
# The round-12 whiteboard's draft used "use no external resource
# references"; Codex round-13 flagged that as inconsistent with
# the enforcement split: Layer 1 (this module) is HTML-only after
# round-13 F2 and does NOT scan CSS content, so a template with a
# `background-image: image-set("https://…")` inside `<style>`
# would pass Layer 1 while carrying an external reference. The
# CSP denies that reference at the browser (Layer 2) and the
# initial-load smoke test observes no request (Layer 3), so all
# three layers stay green — but the source-text sentence would
# be false. The refined sentence above matches what the layers
# actually enforce.
#
# WHAT THIS GUARANTEE DOES NOT CLAIM:
#   * Arbitrary user-edited HTML remains self-contained. The
#     validator here checks the SHIPPED templates; author-added
#     content is out of scope.
#   * Every possible encoded or malformed browser input is safe.
#     Confining that class requires runtime confinement, not
#     repository tests. The pinned CSP is defense in depth against
#     accidental future edits.
#   * A short browser observation is "definitive". The Chromium
#     smoke test observes the initial-load interval only.
#
# HOW THE THREE-LAYER DEFENSE COMPOSES:
#
#   Layer 1 · Positive policy (this module) — source-text HTMLParser
#     walk against a small allowlist of passive tags and attributes.
#     Fails closed on parse error.
#   Layer 2 · Pinned CSP `<meta>` in the templates — browser-
#     enforced denial of `script-src`, `img-src`, `font-src`,
#     `frame-src`, `object-src`, `base-uri`, `form-action`. Catches
#     future edits that slip past Layer 1.
#   Layer 3 · Chromium initial-load network smoke test
#     (`test_cumberland_computed_style.py`) — observes real browser
#     behavior at load. Scoped to the observed interval; not
#     definitive on its own.
#
# The three layers are INDEPENDENT and CUMULATIVE. No single layer
# is "the" guarantee.
#
# ── Round-12 replacement of round-1..11 machinery ────────────────
# The prior blacklist scanners (`_HTMLResourceScanner`,
# `_ExecutableScriptScanner`, WHATWG meta-refresh parser, srcset
# parser, CSS hex-escape decoder, active-data-document guard, etc.)
# are DELETED. Their meta-pins are DELETED. Any browser-input shape
# they were parsing (srcdoc recursion, entity-encoded schemes,
# meta-refresh grammar, data:text/html) is now moot: the enclosing
# tag is forbidden by the positive policy, so the parser detail
# below it does not matter. This is the "material net reduction in
# self-containment test complexity" the round-12 whiteboard asked
# for.

import html.parser as _html_parser


# ── The positive policy ──────────────────────────────────────────

# Tags that appear in the master and/or narrative templates as
# shipped. Any tag NOT in this set is a violation — even
# structurally-harmless ones (`<mark>`, `<em>`, `<figure>`, …) —
# because the policy is scoped to the actual template surface, not
# a general HTML subset. Adding a tag requires (a) demonstrating a
# template need and (b) extending this allowlist plus the attribute
# allowlist in the same commit.
_ALLOWED_TAGS = frozenset({
    # Document skeleton
    "html", "head", "body", "title", "meta", "style",
    # Semantic sections
    "header", "footer", "nav", "section",
    # Text
    "h1", "h2", "h3", "p", "span", "div", "code", "pre",
    # Lists
    "ol", "ul", "li",
    # Tables
    "table", "thead", "tbody", "tr", "th", "td",
    # Fragment navigation
    "a",
    # Inline SVG (the subset actually used in the shipped
    # templates: `<svg>`, `<line>`, `<rect>`, `<text>`). SVG
    # `<script>`, `<image>`, `<use>`, `<feImage>`, `<foreignObject>`,
    # and animation elements are intentionally excluded — none of
    # them appear in the templates and every one carries an
    # external-resource or execution surface.
    "svg", "line", "rect", "text",
})

# Attributes allowed on every tag. `class` and `id` are the two
# Cumberland uses everywhere for styling and TOC anchors.
_GLOBAL_ATTRS = frozenset({"class", "id"})

# Per-tag attribute allowlist. Merged with `_GLOBAL_ATTRS`. Any
# attribute not in the union is a violation.
_ATTR_ALLOWLIST = {
    "html":    frozenset({"lang"}),
    "head":    frozenset(),
    "body":    frozenset(),
    "title":   frozenset(),
    # `<meta>` allows `charset`, `name`, `content`, `http-equiv`.
    # Values are validated below: `http-equiv` must be
    # `Content-Security-Policy`; `name` must be an approved key.
    "meta":    frozenset({"charset", "name", "content", "http-equiv"}),
    "style":   frozenset(),
    "header":  frozenset(),
    "footer":  frozenset(),
    "nav":     frozenset(),
    "section": frozenset(),
    "h1":      frozenset(),
    "h2":      frozenset(),
    "h3":      frozenset(),
    "p":       frozenset(),
    "span":    frozenset(),
    "div":     frozenset(),
    "code":    frozenset(),
    "pre":     frozenset(),
    "ol":      frozenset(),
    "ul":      frozenset(),
    "li":      frozenset(),
    "table":   frozenset(),
    "thead":   frozenset(),
    "tbody":   frozenset(),
    "tr":      frozenset(),
    "th":      frozenset(),
    "td":      frozenset(),
    # `<a href>` values are further constrained to fragment-only
    # by `_href_is_allowed` — no external URLs, no `javascript:`,
    # no `data:`.
    "a":       frozenset({"href"}),
    # SVG: standard geometry/presentation attributes actually used
    # by the shipped templates plus a small margin for legitimate
    # neighbours. Attribute names lowercased because HTMLParser
    # lowercases them before delivery — `viewBox` in source arrives
    # as `viewbox` here. Notably ABSENT: `href`, `xlink:href`,
    # `filter`, `style`. Those carry external resources or scripts
    # in browsers that support them.
    "svg":  frozenset({
        "viewbox", "width", "height", "xmlns", "fill",
        "stroke", "stroke-width", "preserveaspectratio",
        "role", "aria-label", "aria-hidden",
        "font-family", "font-size",
    }),
    "line": frozenset({
        "x1", "y1", "x2", "y2", "stroke", "stroke-width",
        "stroke-linecap", "stroke-dasharray", "fill", "opacity",
    }),
    "rect": frozenset({
        "x", "y", "width", "height", "rx", "ry", "fill",
        "stroke", "stroke-width", "opacity",
    }),
    "text": frozenset({
        "x", "y", "dx", "dy", "text-anchor", "font-family",
        "font-size", "font-weight", "fill", "opacity",
    }),
}


# `<meta http-equiv>` — only Content-Security-Policy is allowed.
# `refresh` is forbidden (triggers a navigation, breaks
# self-containment).
_ALLOWED_META_HTTP_EQUIV = frozenset({"content-security-policy"})


# `<meta name>` — an explicit set of known-safe keys plus the
# Blueprint-protocol `gator-*` prefix. Anything else is a
# violation; the templates use only viewport (master + narrative)
# and gator-* (narrative Blueprint only).
_ALLOWED_META_NAMES = frozenset({
    "viewport", "generator", "description", "author",
    "keywords", "referrer", "color-scheme", "theme-color",
})


def _href_is_allowed(value):
    """`<a href>` values that are safe in a self-contained
    document: empty, `#`, or `#fragment`. Everything else is a
    violation — including `javascript:`, `data:`, external
    schemes, and anything with whitespace."""
    if value is None:
        return True
    v = value.strip()
    if v == "" or v == "#":
        return True
    if not v.startswith("#"):
        return False
    if " " in v or "\t" in v or "\n" in v or "\r" in v:
        return False
    return True


def _meta_name_is_allowed(value):
    if value is None:
        return False
    v = value.lower().strip()
    if v in _ALLOWED_META_NAMES:
        return True
    if v.startswith("gator-"):
        return True
    return False


class _PositivePolicyScanner(_html_parser.HTMLParser):
    """HTMLParser walk implementing the positive policy. Every
    start tag and start/end tag is checked against `_ALLOWED_TAGS`;
    every attribute is checked against the per-tag allowlist plus
    `_GLOBAL_ATTRS`.

    **Layer 1 boundary (round-13 F2 closure)**: HTML capabilities
    only. CSS content inside `<style>` blocks is NOT scanned here —
    Chromium recognizes CSS reference shapes that a source-text
    scanner would need a full CSS tokenizer to catch (uppercase
    `@IMPORT`, `image-set("…")`, CSS-escaped `\75rl(...)`, etc.).
    Delegating CSS to Layer 2 (the pinned CSP declaration blocks
    every external CSS reference under `style-src 'unsafe-inline'`
    + `img-src 'none'` + `font-src 'none'`) and Layer 3 (the
    browser initial-load smoke test) is the cleaner closure than
    maintaining a CSS parser here. A dedicated browser-side test
    in `test_cumberland_computed_style.py` exercises the CSP
    boundary against those exact shapes so the boundary is
    executable and documented.

    Alongside policy findings, the scanner also RECORDS every
    active `<meta http-equiv="Content-Security-Policy">` it sees
    with its position relative to `<head>` / `<title>` / `<style>`.
    Round-13 F1: replaces the earlier raw-substring CSP checker,
    which was fooled by a commented-out `<!-- <meta ... > -->` —
    HTMLParser routes comment content to `handle_comment`, not
    `handle_starttag`, so only ACTIVE tags reach the recorder.

    Deliberately NOT tracked: nesting rules, DOCTYPE, entity
    references. Those are Chromium's job.
    """

    def __init__(self, findings):
        super().__init__(convert_charrefs=False)
        self.findings = findings
        # CSP tracking (round-13 F1).
        self.csp_metas = []  # list of dicts, one per active CSP <meta>
        self._in_head = False
        self._seen_title = False
        self._seen_style = False

    def handle_starttag(self, tag, attrs):
        self._track_position(tag)
        self._maybe_record_csp(tag, attrs)
        self._check_tag(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        self._track_position(tag)
        self._maybe_record_csp(tag, attrs)
        self._check_tag(tag, attrs)

    def handle_endtag(self, tag):
        if tag.lower() == "head":
            self._in_head = False

    def _track_position(self, tag):
        t = tag.lower()
        if t == "head":
            self._in_head = True
        elif t == "title":
            self._seen_title = True
        elif t == "style":
            self._seen_style = True

    def _maybe_record_csp(self, tag, attrs):
        if tag.lower() != "meta":
            return
        attr_map = {(n.lower() if n else ""): v
                    for n, v in attrs if v is not None}
        if attr_map.get("http-equiv", "").lower().strip() != \
                "content-security-policy":
            return
        self.csp_metas.append({
            "content": attr_map.get("content", ""),
            "in_head": self._in_head,
            "seen_title": self._seen_title,
            "seen_style": self._seen_style,
            "lineno": self.getpos()[0],
        })

    def _check_tag(self, tag, attrs):
        tag_l = tag.lower()
        lineno = self.getpos()[0]
        if tag_l not in _ALLOWED_TAGS:
            self.findings.append((
                "forbidden-tag", f"<{tag_l}>", lineno))
            return
        allowed_attrs = _ATTR_ALLOWLIST.get(tag_l, frozenset()) | \
            _GLOBAL_ATTRS
        for name, value in attrs:
            if name is None:
                continue
            name_l = name.lower()
            # Event handlers — a single global rule (all `on*=` are
            # forbidden). Reported as its own class so the failure
            # message is legible.
            if name_l.startswith("on") and len(name_l) > 2:
                self.findings.append((
                    "event-handler-attr",
                    f"{tag_l}@{name_l}", lineno))
                continue
            if name_l not in allowed_attrs:
                self.findings.append((
                    "forbidden-attr",
                    f"{tag_l}@{name_l}", lineno))
                continue
            # Value-level validation for the attributes the policy
            # admits.
            if tag_l == "a" and name_l == "href":
                if not _href_is_allowed(value):
                    self.findings.append((
                        "external-a-href",
                        f"a@href={value!r}", lineno))
            elif tag_l == "meta" and name_l == "http-equiv":
                v = (value or "").lower().strip()
                if v not in _ALLOWED_META_HTTP_EQUIV:
                    self.findings.append((
                        "forbidden-meta-http-equiv",
                        f"meta@http-equiv={value!r}", lineno))
            elif tag_l == "meta" and name_l == "name":
                if not _meta_name_is_allowed(value):
                    self.findings.append((
                        "forbidden-meta-name",
                        f"meta@name={value!r}", lineno))


def _validate_cumberland_document(text):
    """Return a list of `(kind, detail, lineno)` findings from
    walking `text` under the positive policy. Empty list ⇒ the
    document is valid.

    Fails CLOSED on parse errors — any HTMLParser exception
    produces a `parse-error` finding rather than being swallowed.
    A template that can't be parsed cannot be trusted to be safe.
    """
    findings = []
    scanner = _PositivePolicyScanner(findings)
    try:
        scanner.feed(text)
        scanner.close()
    except Exception as exc:  # noqa: BLE001
        findings.append(("parse-error", repr(exc), -1))
    return findings


# ── The pinned CSP ────────────────────────────────────────────────

# The exact policy CONTENT the two templates carry inside their
# `<meta http-equiv="Content-Security-Policy" content="...">` tag.
# Deviation from this string (spacing, directive order, added or
# removed directives) fails the pin — CSP is defense in depth; a
# hand-edited variant is not trusted.
#
# Shared with `test_cumberland_computed_style.py` via `_helpers` so
# the browser-side CSS-egress fixtures exercise the SAME policy the
# templates carry (round-14 F2). Two hand-copies would let the
# fixture drift into a phantom policy while the templates and this
# module updated to a new one.
from ._helpers import PINNED_CSP_CONTENT as _PINNED_CSP_CONTENT


def _find_csp_status(text):
    """Round-13 F1 structural CSP validator. Walks `text` with the
    positive-policy HTMLParser and returns `(verdict, detail)`:

      "ok"                        — exactly one active CSP meta in
                                    <head> before <title> and
                                    <style>, content matches pin.
      "missing"                   — no active CSP meta.
      "duplicate"                 — more than one active CSP meta.
      "csp-outside-head"          — CSP meta is not inside <head>.
      "csp-after-title"           — CSP meta appears after <title>.
      "csp-after-style"           — CSP meta appears after <style>.
      "csp-content-mismatch"      — content differs from
                                    `_PINNED_CSP_CONTENT`.
      "parse-error"               — HTMLParser raised.

    Uses HTMLParser (via the same walk as
    `_validate_cumberland_document`) so a commented-out
    `<!-- <meta http-equiv="Content-Security-Policy" …> -->`
    correctly counts as MISSING — HTMLParser dispatches comment
    content to `handle_comment`, so an inert commented-out CSP
    never reaches `handle_starttag`.
    """
    findings = []
    scanner = _PositivePolicyScanner(findings)
    try:
        scanner.feed(text)
        scanner.close()
    except Exception as exc:  # noqa: BLE001
        return ("parse-error", repr(exc))
    if not scanner.csp_metas:
        return ("missing", "no active CSP <meta> tag")
    if len(scanner.csp_metas) > 1:
        lines = ", ".join(str(m["lineno"]) for m in scanner.csp_metas)
        return ("duplicate", f"{len(scanner.csp_metas)} CSP metas "
                             f"(lines {lines})")
    meta = scanner.csp_metas[0]
    if not meta["in_head"]:
        return ("csp-outside-head",
                f"CSP meta outside <head> (line {meta['lineno']})")
    if meta["seen_title"]:
        return ("csp-after-title",
                f"CSP meta after <title> (line {meta['lineno']})")
    if meta["seen_style"]:
        return ("csp-after-style",
                f"CSP meta after <style> (line {meta['lineno']})")
    if meta["content"].strip() != _PINNED_CSP_CONTENT:
        return ("csp-content-mismatch",
                f"CSP content differs from pinned "
                f"(line {meta['lineno']})")
    return ("ok", f"line {meta['lineno']}")


def _pinned_csp_meta_string():
    """Compose the full `<meta http-equiv=...>` string authors
    paste into templates. Kept in ONE place so the pinned content
    and the meta-string never drift."""
    return (
        '<meta http-equiv="Content-Security-Policy" '
        f'content="{_PINNED_CSP_CONTENT}">'
    )


@pytest.fixture(scope="module")
def narrative_text():
    narrative = (REPO_ROOT / ".gator" / "blueprints"
                 / "_template-narrative.html")
    if not narrative.is_file():
        pytest.skip("narrative Blueprint scaffolding-root not present")
    return narrative.read_text(encoding="utf-8")


# ── Positive policy on shipped templates ─────────────────────────

def test_master_passes_positive_policy(master_text):
    findings = _validate_cumberland_document(master_text)
    assert findings == [], (
        "Cumberland master violates the positive policy — the "
        "shipped template must use only approved passive markup.\n"
        + "\n".join(f"  line {ln}: {kind} — {detail}"
                    for kind, detail, ln in findings))


def test_narrative_passes_positive_policy(narrative_text):
    findings = _validate_cumberland_document(narrative_text)
    assert findings == [], (
        "Cumberland narrative Blueprint violates the positive "
        "policy.\n"
        + "\n".join(f"  line {ln}: {kind} — {detail}"
                    for kind, detail, ln in findings))


# ── CSP presence + placement pins ────────────────────────────────

def test_master_carries_pinned_csp(master_text):
    verdict, detail = _find_csp_status(master_text)
    assert verdict == "ok", (
        f"Master CSP check failed: {verdict} — {detail}. Required "
        f"CSP content:\n  {_PINNED_CSP_CONTENT}")


def test_narrative_carries_pinned_csp(narrative_text):
    verdict, detail = _find_csp_status(narrative_text)
    assert verdict == "ok", (
        f"Narrative CSP check failed: {verdict} — {detail}. "
        f"Required CSP content:\n  {_PINNED_CSP_CONTENT}")


def test_csp_status_rejects_commented_out_meta():
    """Round-13 F1 negative control. A commented-out CSP `<meta>`
    is browser-inert — Chromium ignores everything inside
    `<!-- ... -->`. The structural validator must report the
    document as MISSING CSP, not "ok".

    Codex's Chromium probe walked exactly this shape: substituting
    the real CSP with `<!-- <meta http-equiv=... > -->` left Layer 2
    unenforced while the earlier raw-substring `text.find(...)`
    reported "ok". HTMLParser dispatches comment content to
    `handle_comment`, so the round-13 walker only sees ACTIVE
    tags. The fixture below is the exact liveness form Codex
    recommended for the meta-pin.
    """
    commented_out = (
        '<!DOCTYPE html><html lang="en"><head>'
        '<meta charset="utf-8">'
        '<!-- ' + _pinned_csp_meta_string() + ' -->'
        '<title>x</title></head><body>hi</body></html>'
    )
    verdict, detail = _find_csp_status(commented_out)
    assert verdict == "missing", (
        f"Commented-out CSP incorrectly reported as {verdict!r} — "
        f"HTMLParser routes comment content away from starttag "
        f"handlers, so the inert form must count as missing. "
        f"detail={detail!r}")

    # Duplicate CSP metas — reject.
    two_metas = (
        '<!DOCTYPE html><html lang="en"><head>'
        '<meta charset="utf-8">'
        + _pinned_csp_meta_string()
        + _pinned_csp_meta_string() +
        '<title>x</title></head><body>hi</body></html>'
    )
    verdict, detail = _find_csp_status(two_metas)
    assert verdict == "duplicate", (
        f"Duplicate CSP metas reported as {verdict!r}, expected "
        f"'duplicate'. detail={detail!r}")

    # CSP after <title> — reject.
    late_csp = (
        '<!DOCTYPE html><html lang="en"><head>'
        '<meta charset="utf-8">'
        '<title>x</title>'
        + _pinned_csp_meta_string() +
        '</head><body>hi</body></html>'
    )
    verdict, detail = _find_csp_status(late_csp)
    assert verdict == "csp-after-title", (
        f"CSP after <title> reported as {verdict!r}, expected "
        f"'csp-after-title'. detail={detail!r}")

    # CSP with wrong content — reject.
    weak_csp = (
        '<!DOCTYPE html><html lang="en"><head>'
        '<meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" '
        'content="default-src *">'
        '<title>x</title></head><body>hi</body></html>'
    )
    verdict, detail = _find_csp_status(weak_csp)
    assert verdict == "csp-content-mismatch", (
        f"Weakened CSP content reported as {verdict!r}, expected "
        f"'csp-content-mismatch'. detail={detail!r}")


# ── Positive control + forbidden-class rejection matrix ──────────

_MINIMAL_ALLOWED_DOCUMENT = (
    '<!DOCTYPE html>\n'
    '<html lang="en">\n'
    '<head>\n'
    '<meta charset="utf-8">\n'
    + _pinned_csp_meta_string() + '\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
    '<title>ok</title>\n'
    '<style>\n'
    'body { color: black; }\n'
    '</style>\n'
    '</head>\n'
    '<body>\n'
    '<header><h1>Hi</h1></header>\n'
    '<section><p>Text <a href="#top">jump</a>.</p></section>\n'
    '</body>\n'
    '</html>\n'
)


def test_positive_policy_accepts_minimal_allowed_document():
    """Positive control. A minimal document using ONLY the
    tags/attributes the policy admits must produce zero findings —
    otherwise the validator is over-strict (and the shipped
    templates would falsely fail)."""
    findings = _validate_cumberland_document(_MINIMAL_ALLOWED_DOCUMENT)
    assert findings == [], (
        f"Positive control failed — a minimal allowed document was "
        f"flagged:\n"
        + "\n".join(f"  line {ln}: {kind} — {detail}"
                    for kind, detail, ln in findings))


# One entry per forbidden HTML capability class. Layer 1 policy
# scope (round-13 F2 closure): HTML tags and attributes only. CSS
# CONTENT inside `<style>` blocks is NOT this layer's concern —
# see `test_cumberland_computed_style.py::test_csp_blocks_forbidden_css_shapes`
# for Layer 2 (CSP) + Layer 3 (browser observation) coverage of
# the CSS shapes a source-text scanner cannot reliably match
# (uppercase `@IMPORT`, `image-set("…")`, CSS-escaped
# `\75rl(...)`, etc.).
#
# The validator must produce at least one finding for every
# fixture. The specific `kind` a finding uses is intentionally NOT
# asserted — the class survives the round-1..11 whack-a-mole
# precisely because the validator's job is REJECTION, not
# classification.
_FORBIDDEN_FIXTURES = [
    ("script-tag",
     "<script>fetch('https://cdn.example/x')</script>"),
    ("iframe-tag",
     "<iframe src=\"data:text/html,<b>hi</b>\"></iframe>"),
    ("iframe-with-srcdoc",
     '<iframe srcdoc="&lt;script&gt;fetch(1)&lt;/script&gt;"></iframe>'),
    ("iframe-src-data-html",
     "<iframe src=\"data:text/html,%3Cscript%3Efetch(1)%3C/script%3E\"></iframe>"),
    ("frame-tag",
     "<frame src=\"about:blank\">"),
    ("object-tag",
     "<object data=\"x.svg\"></object>"),
    ("embed-tag",
     "<embed src=\"x.pdf\">"),
    ("base-tag",
     "<base href=\"https://cdn.example/\">"),
    ("form-tag",
     "<form action=\"javascript:1\"></form>"),
    ("input-tag",
     "<input type=\"text\">"),
    ("button-tag",
     "<button>go</button>"),
    ("meta-refresh",
     '<meta http-equiv="refresh" content="0;url=https://cdn.example/">'),
    ("meta-refresh-unlabeled",
     '<meta http-equiv="refresh" content="0; https://cdn.example/">'),
    ("event-handler-onclick",
     '<a href="#" onclick="fetch(1)">x</a>'),
    ("event-handler-onload",
     "<div onload=\"fetch(2)\">x</div>"),
    ("event-handler-onerror",
     "<span onerror=\"fetch(3)\">x</span>"),
    ("external-a-href",
     '<a href="https://cdn.example/x">go</a>'),
    ("javascript-a-href",
     '<a href="javascript:1">x</a>'),
    ("data-a-href",
     '<a href="data:text/plain,x">x</a>'),
    ("protocol-relative-a-href",
     '<a href="//cdn.example/x">x</a>'),
    ("img-tag",
     "<img src=\"x.png\">"),
    ("svg-with-script",
     "<svg><script>fetch(1)</script></svg>"),
    ("svg-use-xlink",
     "<svg><use xlink:href=\"#foo\"></use></svg>"),
    ("link-tag",
     "<link rel=\"stylesheet\" href=\"https://cdn.example/x.css\">"),
    ("style-attr",
     '<div style="background: url(https://cdn.example/x.png)">x</div>'),
    ("video-tag",
     "<video src=\"x.mp4\"></video>"),
    ("audio-tag",
     "<audio src=\"x.mp3\"></audio>"),
]


@pytest.mark.parametrize(
    "class_name, fixture", _FORBIDDEN_FIXTURES,
    ids=[c for c, _ in _FORBIDDEN_FIXTURES],
)
def test_positive_policy_rejects_forbidden_class(class_name, fixture):
    """Every forbidden capability class produces at least one
    policy finding. The point of round-12 closure: a class-level
    rejection subsumes the previous rounds of parser-detail
    findings (`iframe[srcdoc]`, `data:text/html`, entity-encoded
    `javascript:`, meta-refresh grammar shapes, etc.). Rejecting
    `<iframe>` outright makes every `<iframe src=...>` variant
    moot, because the enclosing tag is already refused.
    """
    doc = (
        '<!DOCTYPE html><html lang="en"><head>'
        '<meta charset="utf-8">'
        + _pinned_csp_meta_string() +
        '<title>x</title></head><body>' + fixture + '</body></html>'
    )
    findings = _validate_cumberland_document(doc)
    assert findings, (
        f"Forbidden class {class_name!r} produced no findings — "
        f"the positive policy failed to reject it. Fixture: "
        f"{fixture!r}")



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
