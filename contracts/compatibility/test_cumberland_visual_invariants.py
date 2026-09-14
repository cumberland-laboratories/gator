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

import html.parser as _html_parser


# Single-URL resource attributes: {(tag, attr) → applicable to which tag}.
_SINGLE_URL_RESOURCE_ATTRS = {
    ("script", "src"),
    ("img", "src"),
    ("iframe", "src"),
    ("video", "src"),
    ("video", "poster"),          # F2 re-review addition
    ("audio", "src"),
    ("source", "src"),
    ("track", "src"),
    ("embed", "src"),
    ("object", "data"),
    ("input", "src"),             # <input type="image" src="…">
    # SVG resource consumers — Cumberland docs use inline SVG; a
    # regression that referenced an external icon or sprite would
    # slip past a pure-HTML allowlist. Cover both the modern `href`
    # spelling AND the legacy `xlink:href` on each SVG element that
    # actually fetches. F2 round-4 addition (2026-09-13).
    ("image", "href"),
    ("image", "xlink:href"),
    ("use", "href"),
    ("use", "xlink:href"),
    ("feimage", "href"),
    ("feimage", "xlink:href"),
    # SVG <script> uses href / xlink:href (not `src`) — F1 round-5
    # addition (2026-09-14). Codex's Chromium intercept verified
    # `<svg><script href="https://cdn.example/x.js">` triggers a
    # real network fetch; the HTML <script src> allowlist entry
    # above did NOT catch this form because the attribute name is
    # different.
    ("script", "href"),
    ("script", "xlink:href"),
}

# Comma-separated URL-list attributes (srcset syntax).
_SRCSET_ATTRS = {
    ("img", "srcset"),
    ("source", "srcset"),
    ("link", "imagesrcset"),
}

# <link href> is special-cased because <a href> must be scoped-out.


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


def _scan_css_for_externals(css_text: str):
    """Return list of `(kind, url)` for CSS `@import` + `url(...)`
    references that point outside the file. Shared by the `<style>`
    block scan AND the inline `style="…"` attribute scan.

    The `url(...)` regex distinguishes three quoting shapes so a
    QUOTED URL containing whitespace (e.g. `url('a b.png')`) resolves
    correctly — the naive ``[^"')\\s]+`` pattern was breaking on the
    space and missing external references (F2 round-4 finding).
    """
    results = []
    # Unquoted URL character class — escape-aware per CSS spec.
    # Three URL-character shapes:
    #   1. `\<1-6 hex digits>[optional whitespace terminator]` —
    #      standard CSS hex escape (F1 round-6, Chromium-verified:
    #      `\68 ttps://…` decodes to `https://…`). The space in
    #      `\68 ` is the terminator, NOT the URL boundary.
    #   2. `\<any single char>` — the simple char escape (F2
    #      round-5, e.g. `a\ b.png`).
    #   3. Any non-special char.
    # Trailing `\` (bare, no follower) is intentionally not matched
    # — real CSS treats that as invalid; keeping the pattern strict
    # avoids catastrophic backtracking on malformed input.
    _UNQ = r"(?:\\[0-9a-fA-F]{1,6}\s?|\\.|[^\"')\s])+"

    # @import "…" / @import '…' / @import url(…)
    # Three URL shapes: double-quoted, single-quoted, unquoted.
    import_pat = re.compile(
        r'@import\s+'
        r'(?:'
        r'url\s*\(\s*(?:"([^"]*)"|\'([^\']*)\'|(' + _UNQ + r'))\s*\)'
        r'|"([^"]*)"'
        r'|\'([^\']*)\''
        r'|([^"\')\s;]+)'
        r')',
        re.IGNORECASE)
    for m in import_pat.finditer(css_text):
        url = next((g for g in m.groups() if g is not None), None)
        if url is not None and not _url_is_self_contained(_unescape_css(url)):
            results.append(("@import", _unescape_css(url)))
    # url(…) — any property. Three quoting shapes: double-quoted
    # (allow whitespace + parens up to matching quote), single-quoted
    # (same), unquoted (escape-aware — `\ ` is a literal space).
    url_pat = re.compile(
        r'\burl\s*\(\s*'
        r'(?:'
        r'"([^"]*)"'
        r'|\'([^\']*)\''
        r'|(' + _UNQ + r')'
        r')'
        r'\s*\)',
        re.IGNORECASE)
    for m in url_pat.finditer(css_text):
        url = next((g for g in m.groups() if g is not None), None)
        if url is not None and not _url_is_self_contained(_unescape_css(url)):
            results.append(("url()", _unescape_css(url)))
    return results


_CSS_HEX_ESCAPE_RE = re.compile(r'\\([0-9a-fA-F]{1,6})(\s?)')


def _unescape_css(url: str) -> str:
    """Undo CSS backslash-escapes in a URL so `_url_is_self_contained`
    sees the same URL the browser would resolve.

    Two escape forms per CSS spec:
      * `\\<1-6 hex digits>[optional single whitespace terminator]`
        — decodes to the Unicode character with that code point.
        E.g. `\\68 ttps://…` becomes `https://…` (F1 round-6,
        Chromium-verified).
      * `\\<any non-hex-digit char>` — decodes to that char.
        E.g. `a\\ b.png` becomes `a b.png` (F2 round-5).

    Hex escapes are processed FIRST so the trailing whitespace
    terminator (part of the escape) isn't consumed by a naive
    `\\.` pass. Any remaining `\\<char>` is unwrapped by the second
    pass. Runs of hex escapes decode correctly because each
    escape consumes exactly its own digits + optional terminator.
    """
    def _decode_hex(m: re.Match) -> str:
        codepoint = int(m.group(1), 16)
        return chr(codepoint)
    unhexed = _CSS_HEX_ESCAPE_RE.sub(_decode_hex, url)
    return re.sub(r'\\(.)', r'\1', unhexed)


def _parse_srcset(value: str):
    """Parse an HTML `srcset` (or `imagesrcset`) attribute into a list
    of URLs. Follows the WHATWG spec: URL runs to the next whitespace
    (or trailing comma) and commas INSIDE the URL are literal — so a
    `data:image/png;base64,abc 1x, data:image/png;base64,def 2x`
    srcset yields two data URIs, not four comma-split fragments.

    Naive comma-split (the previous shape, 2026-09-13 F1 round-4
    finding) reported `abc` and `def` as external URLs and let the
    meta-pin's data-URI allowance silently contradict itself.
    """
    urls = []
    i = 0
    n = len(value)
    while i < n:
        # Skip leading whitespace and stray candidate separators.
        while i < n and value[i].isspace():
            i += 1
        while i < n and value[i] == ",":
            i += 1
        while i < n and value[i].isspace():
            i += 1
        if i >= n:
            break

        # URL runs from here to next whitespace. Commas inside are
        # part of the URL (data: URIs rely on this).
        url_start = i
        while i < n and not value[i].isspace():
            i += 1
        url = value[url_start:i]

        # A trailing comma is a candidate separator, not part of the
        # URL. Strip repeated trailing commas too.
        trailing_comma_terminated = url.endswith(",")
        while url.endswith(","):
            url = url[:-1]
        if url:
            urls.append(url)

        # If terminated by whitespace (not by trailing comma), skip
        # the descriptor — advance until next comma or EOL. If
        # terminated by trailing comma, we're already at the next
        # candidate boundary; loop back.
        if not trailing_comma_terminated:
            while i < n and value[i] != ",":
                i += 1
    return urls


class _HTMLResourceScanner(_html_parser.HTMLParser):
    """Walk every start tag, examine every attribute, collect
    external resource references.

    Uses stdlib `html.parser.HTMLParser`, which handles single-quoted,
    double-quoted, AND unquoted attribute values correctly (previous
    regex-based scanner missed unquoted attrs — F2 re-review
    finding).

    Emits two violation shapes:
      * `self.html_violations` = `(tag, attr, url, lineno)` — HTML
        resource attribute violations.
      * `self.inline_style_violations` = `(f"{tag}@style", kind, url,
        lineno)` — inline CSS via `style="…"` (kind = `@import` or
        `url()`).

    Also recurses into `<iframe srcdoc>` (F2 round-6): the attribute
    value is a full HTML document embedded as HTML-encoded text. A
    resource inside srcdoc is fetched by the browser — Codex verified
    with Chromium intercept. Scanner decodes entities via
    `html.unescape` and re-feeds the content into a fresh scanner
    instance at `depth+1`, capped at `_MAX_SRCDOC_DEPTH` to prevent
    runaway. Nested `<style>` blocks inside srcdoc are also scanned.
    """

    # F2 round-7 raised the cap from 2 to 5 — real Cumberland docs
    # never nest srcdoc even one level, so 5 is generous for
    # anything a legitimate author would write. Above 5 the scanner
    # fails CLOSED (adds an explicit "unscanned nested srcdoc"
    # violation) rather than silently accepting the unscanned
    # surface. Chromium fetches through nesting regardless of depth,
    # so the earlier silent-skip contradicted the full self-
    # containment guarantee.
    _MAX_SRCDOC_DEPTH = 5

    def __init__(self, depth: int = 0):
        super().__init__(convert_charrefs=False)
        self.html_violations = []
        self.inline_style_violations = []
        self.depth = depth

    def handle_starttag(self, tag, attrs):
        self._scan(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        # Self-closing (<img/>, etc.) — treat identically.
        self._scan(tag, attrs)

    def _scan(self, tag, attrs):
        tag_l = tag.lower()
        lineno = self.getpos()[0]

        # F2 round-6: recursive scan of <iframe srcdoc>. Always call
        # `_recurse_srcdoc` — the depth check + fail-closed logic
        # lives INSIDE that method (F2 round-7 change: pre-check
        # was silently skipping past the cap; now beyond-cap emits
        # an explicit "unscanned" violation instead).
        if tag_l == "iframe":
            for name, value in attrs:
                if name and name.lower() == "srcdoc" and value:
                    self._recurse_srcdoc(value, lineno)

        for name, value in attrs:
            if name is None or value is None:
                continue
            attr_l = name.lower()

            # Single-URL resource attributes.
            if (tag_l, attr_l) in _SINGLE_URL_RESOURCE_ATTRS:
                if not _url_is_self_contained(value):
                    self.html_violations.append(
                        (tag_l, attr_l, value, lineno))
                continue

            # srcset-style comma-separated URL lists.
            if (tag_l, attr_l) in _SRCSET_ATTRS:
                for url in _parse_srcset(value):
                    if not _url_is_self_contained(url):
                        self.html_violations.append(
                            (tag_l, attr_l, url, lineno))
                continue

            # <link href> — no external targets allowed.
            # <a href> is navigation, not resource-loading; scope out.
            if tag_l == "link" and attr_l == "href":
                if not _url_is_self_contained(value):
                    self.html_violations.append(
                        (tag_l, attr_l, value, lineno))
                continue

            # Inline style="…" — treat as CSS. Any tag can carry it.
            if attr_l == "style":
                for kind, url in _scan_css_for_externals(value):
                    self.inline_style_violations.append(
                        (f"{tag_l}@style", kind, url, lineno))

    def _recurse_srcdoc(self, srcdoc_value: str, parent_lineno: int):
        """Feed an `<iframe srcdoc>` value into a fresh scanner at
        `depth+1`. Merge surfaced violations with `iframe@srcdoc>`
        prefix. Also scan any `<style>` blocks inside the srcdoc.

        F1 round-7 (2026-09-14): DO NOT `html.unescape` the value
        before recursion. `html.parser.HTMLParser` already resolves
        character references in attribute values (regardless of
        `convert_charrefs=False`, which only affects the DATA
        callback). A second unescape is a double-decode that turns
        legitimate literal `&lt;img&gt;` inside srcdoc (which
        browsers render as text) into a synthetic `<img>` tag and
        false-positives the scan.

        F2 round-7 (2026-09-14): fail CLOSED at the depth cap. When
        `self.depth >= _MAX_SRCDOC_DEPTH`, record an "unscanned
        nested srcdoc" violation rather than silently skipping —
        Chromium fetches through nesting regardless of depth, so a
        silent skip contradicts the self-containment guarantee.
        """
        if self.depth >= self._MAX_SRCDOC_DEPTH:
            self.html_violations.append(
                (f"iframe@srcdoc>UNSCANNED-AT-DEPTH-{self.depth + 1}",
                 "srcdoc",
                 f"<nested srcdoc exceeds max depth "
                 f"{self._MAX_SRCDOC_DEPTH} — flatten or split the "
                 f"document; scanner refuses to accept unscanned "
                 f"content silently>",
                 parent_lineno))
            return
        inner_html = srcdoc_value
        inner = _HTMLResourceScanner(depth=self.depth + 1)
        try:
            inner.feed(inner_html)
            inner.close()
        except Exception:  # noqa: BLE001 — partial HTML OK
            pass
        for (t, a, u, _ln) in inner.html_violations:
            self.html_violations.append(
                (f"iframe@srcdoc>{t}", a, u, parent_lineno))
        for (t, k, u, _ln) in inner.inline_style_violations:
            # Inline style-inside-srcdoc becomes an
            # `iframe@srcdoc>…@style` scope on the outer collector.
            self.inline_style_violations.append(
                (f"iframe@srcdoc>{t}", k, u, parent_lineno))
        # <style> blocks inside srcdoc are extracted regex-style and
        # scanned through the shared CSS helper.
        style_pat = re.compile(
            r'<style\b[^>]*>(.*?)</style>',
            re.IGNORECASE | re.DOTALL)
        for m in style_pat.finditer(inner_html):
            for kind, url in _scan_css_for_externals(m.group(1)):
                self.inline_style_violations.append(
                    ("iframe@srcdoc><style>", kind, url, parent_lineno))


def _find_external_html_resources(text: str):
    """Return `[(tag, attr, url, position), …]` for every HTML
    resource-loading attribute that references an external target.
    Handles quoted AND unquoted attribute values (F2 re-review).
    Covers `<script>`, `<img>` (src + srcset), `<iframe>`, `<video>`
    (src + poster), `<audio>`, `<source>` (src + srcset), `<track>`,
    `<embed>`, `<object data>`, `<input type=image src>`, and
    `<link href>` on non-`<a>` elements. `<a href>` navigation is
    explicitly excluded. Position is line number from the HTML
    parser (was character offset in the pre-F2-re-review shape).
    """
    scanner = _HTMLResourceScanner()
    try:
        scanner.feed(text)
        scanner.close()
    except Exception:  # noqa: BLE001 — malformed HTML is OK, keep partial hits
        pass
    return list(scanner.html_violations)


def _find_external_css_resources(text: str):
    """Return `[(kind, url, position), …]` for every CSS `@import`
    and every `url(…)` reference to an external target. Scans BOTH
    `<style>…</style>` blocks (via regex) AND inline `style="…"`
    attribute values (via `html.parser` — F2 re-review addition).

    Position for `<style>`-block hits is the character offset within
    `text`; for inline-style hits it is the line number of the
    element carrying the attribute — the two shapes are heterogeneous
    but every consumer includes the value in a diagnostic string, so
    stringifying either is fine.
    """
    violations = []

    # 1. <style>…</style> blocks
    style_pat = re.compile(r'<style\b[^>]*>(.*?)</style>',
                           re.IGNORECASE | re.DOTALL)
    for style_match in style_pat.finditer(text):
        css_body = style_match.group(1)
        style_start = style_match.start(1)
        for kind, url in _scan_css_for_externals(css_body):
            # Best-effort locator — the exact within-block offset is
            # not tracked here; the diagnostic string carries enough
            # context to find the reference by grep.
            violations.append((kind, url, style_start))

    # 2. Inline style="…" attributes
    scanner = _HTMLResourceScanner()
    try:
        scanner.feed(text)
        scanner.close()
    except Exception:  # noqa: BLE001
        pass
    for tag_scope, kind, url, lineno in scanner.inline_style_violations:
        violations.append((f"{tag_scope}:{kind}", url, lineno))

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
    so a bug in the parse or the URL predicate is visible immediately
    (rather than manifesting as a false-negative on a real template).
    Ensures the helper actually detects each violation class the
    contract lists — including the four F2 re-review blind spots
    (unquoted src, inline style url, srcset, poster) that the earlier
    regex-only scanner silently missed.
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
<!-- Quoted attribute forms — pre-F2-re-review coverage -->
<img src="https://example.com/logo.png">
<iframe src="/other.html"></iframe>
<video src="./local.mp4"></video>

<!-- F2 re-review additions: forms the old scanner missed -->
<!-- unquoted src (HTML permits this) -->
<img src=https://cdn.example/x.png>
<!-- srcset comma-list -->
<img srcset="https://cdn.example/x-1x.png 1x, https://cdn.example/x-2x.png 2x">
<!-- <video poster> — resource loaded before play -->
<video poster="https://cdn.example/poster.jpg"></video>
<!-- inline style="…" carrying url(…) -->
<div style="background: url(https://cdn.example/bg.png)"></div>
<!-- inline style="…" carrying @import -->
<span style='@import "https://cdn.example/x.css";'></span>
<!-- <object data> -->
<object data="https://example.com/thing.swf"></object>
<!-- <embed src> -->
<embed src="https://example.com/x.svg">

<!-- Allowed forms — must NOT be flagged -->
<a href="https://example.com/">nav OK</a>
<a href="#anchor">nav OK</a>
<img src="data:image/png;base64,abc">
<img srcset="data:image/png;base64,abc 1x, data:image/png;base64,def 2x">
<div style="background: url(data:image/png;base64,abc)"></div>
</body>
</html>"""
    html_v = _find_external_html_resources(fixture)
    css_v = _find_external_css_resources(fixture)
    detected_html = {(tag, attr, url) for tag, attr, url, _ in html_v}
    detected_css = {(kind, url) for kind, url, _ in css_v}

    # ── Pre-F2-re-review baseline ──
    assert ("link", "href", "https://cdn.example.com/x.css") in detected_html
    assert ("script", "src", "//example.org/foo.js") in detected_html
    assert ("img", "src", "https://example.com/logo.png") in detected_html
    assert ("iframe", "src", "/other.html") in detected_html
    assert ("video", "src", "./local.mp4") in detected_html
    assert ("@import", "https://external.example/lib.css") in detected_css
    assert ("url()", "https://cdn.example/bg.png") in detected_css

    # ── F2 re-review blind spots — MUST be caught now ──
    assert ("img", "src", "https://cdn.example/x.png") in detected_html, (
        f"unquoted src not detected. html_v={html_v!r}")
    assert ("img", "srcset", "https://cdn.example/x-1x.png") in detected_html, (
        f"srcset first candidate not detected. html_v={html_v!r}")
    assert ("img", "srcset", "https://cdn.example/x-2x.png") in detected_html, (
        f"srcset second candidate not detected. html_v={html_v!r}")
    assert ("video", "poster", "https://cdn.example/poster.jpg") in detected_html, (
        f"video poster not detected. html_v={html_v!r}")
    # Inline style="…" — url() and @import both scanned.
    inline_urls = {url for kind, url, _ in css_v if "@style" in kind}
    assert "https://cdn.example/bg.png" in inline_urls, (
        f"inline style url() not detected. css_v={css_v!r}")
    assert "https://cdn.example/x.css" in inline_urls, (
        f"inline style @import not detected. css_v={css_v!r}")
    # <object data> + <embed src>.
    assert ("object", "data", "https://example.com/thing.swf") in detected_html
    assert ("embed", "src", "https://example.com/x.svg") in detected_html

    # ── Allowed forms MUST NOT be flagged ──
    for tag, attr, url, _ in html_v:
        assert not url.strip().startswith("data:"), (
            f"data: URI incorrectly flagged: {tag} {attr}={url!r}")
        assert not url.strip().startswith("#"), (
            f"fragment anchor incorrectly flagged: {tag} {attr}={url!r}")
    # <a href> is scoped-out (navigation, not resource loading).
    assert not any(tag == "a" for tag, _, _, _ in html_v), (
        f"<a href> should be allowed but the helper flagged it: {html_v!r}")


def test_self_containment_helper_catches_svg_and_quoted_css_forms():
    """F2 round-4 additions (2026-09-13). The previous meta-pin
    covered common HTML resource attributes and inline style, but
    left blind spots that Codex verified with direct probes:

      * SVG `<image href>` / `<use href>` (fetch inline-SVG assets)
      * SVG legacy `<image xlink:href>` (SVG 1.1)
      * CSS `url('path with spaces.png')` where whitespace inside
        quoted URL was breaking the naive `[^\\s]+` regex.
      * `srcset` containing ONLY data URIs — the split-on-comma
        parser was reporting base64 tail fragments as external URLs.

    This pin exercises all four so a scanner regression on any
    of them surfaces immediately.
    """
    fixture = """<!DOCTYPE html>
<html>
<body>
<!-- SVG image + use — modern href AND legacy xlink:href -->
<svg>
  <image href="https://cdn.example/icon.png"/>
  <use href="https://cdn.example/sprite.svg#glyph"/>
  <image xlink:href="https://cdn.example/legacy.png"/>
</svg>
<!-- Fragment-only <use> is self-contained — MUST NOT flag -->
<svg><use href="#local-glyph"/></svg>

<!-- CSS url() with whitespace INSIDE a quoted URL — double-quoted
     url() lives inside a single-quoted style="…" attribute so
     HTML parsing doesn't see the inner `"` as attribute terminator. -->
<div style="background: url('https://cdn.example/a b.png')"></div>
<div style='background: url("https://cdn.example/c d.png")'></div>

<!-- srcset containing ONLY data URIs — must produce NO violations -->
<img srcset="data:image/png;base64,AAABBB 1x, data:image/png;base64,CCCDDD 2x">

<!-- Mixed srcset: external URL first, then data URI — external flagged, data allowed -->
<img srcset="https://cdn.example/external.png 1x, data:image/png;base64,XXXX 2x">
</body>
</html>"""
    html_v = _find_external_html_resources(fixture)
    css_v = _find_external_css_resources(fixture)
    detected_html = {(tag, attr, url) for tag, attr, url, _ in html_v}
    detected_css_urls = {url for kind, url, _ in css_v}

    # ── SVG resource consumers flagged when external ──
    assert ("image", "href", "https://cdn.example/icon.png") in detected_html, (
        f"SVG <image href> external not flagged. html_v={html_v!r}")
    assert ("use", "href", "https://cdn.example/sprite.svg#glyph") in detected_html, (
        f"SVG <use href> external not flagged. html_v={html_v!r}")
    assert ("image", "xlink:href", "https://cdn.example/legacy.png") in detected_html, (
        f"SVG <image xlink:href> external not flagged. html_v={html_v!r}")

    # ── Fragment-only <use href="#…"> allowed (self-contained) ──
    for tag, attr, url, _ in html_v:
        assert not (tag == "use" and url == "#local-glyph"), (
            f"fragment-only <use href> incorrectly flagged: {tag} {attr}={url!r}")

    # ── CSS url() with quoted whitespace-containing URLs flagged ──
    assert "https://cdn.example/a b.png" in detected_css_urls, (
        f"quoted-single url() with whitespace not flagged. css_v={css_v!r}")
    assert "https://cdn.example/c d.png" in detected_css_urls, (
        f"quoted-double url() with whitespace not flagged. css_v={css_v!r}")

    # ── srcset with ONLY data URIs produces NO violations ──
    srcset_violations = [(tag, attr, url, ln) for tag, attr, url, ln in html_v
                         if attr == "srcset" and "data:" not in url]
    # Compute what the data-only srcset produced: its content URIs are
    # `data:image/png;base64,AAABBB` and `data:image/png;base64,CCCDDD`.
    # After the parser fix, both should be data:-prefixed and allowed.
    data_only_flags = [
        v for v in html_v
        if v[1] == "srcset" and v[2] in ("AAABBB", "CCCDDD",
                                          "data:image/png;base64",
                                          "image/png;base64,AAABBB",
                                          "image/png;base64,CCCDDD")
    ]
    assert not data_only_flags, (
        f"data-only srcset produced false-positive violations "
        f"(regression on 2026-09-13 F1 round-4 fix): {data_only_flags!r}")

    # ── Mixed srcset: external URL flagged, data URI allowed ──
    assert ("img", "srcset",
            "https://cdn.example/external.png") in detected_html, (
        f"mixed srcset external URL not flagged. html_v={html_v!r}")
    # The data URI in the mixed srcset must NOT appear as a violation.
    mixed_data_flags = [
        v for v in html_v
        if v[1] == "srcset" and v[2].startswith("XXXX")
    ]
    assert not mixed_data_flags, (
        f"mixed srcset data URI incorrectly flagged: {mixed_data_flags!r}")


def test_self_containment_helper_catches_svg_script_and_escaped_css_url():
    """F1 + F2 round-5 additions (2026-09-14). Codex intercepted real
    Chromium fetches for two forms my scanner returned empty on:

      * SVG `<script href="…">` — SVG scripts use `href`
        (not `src`); the HTML <script src> allowlist entry did NOT
        cover the SVG namespace form.
      * CSS `url(a\\ b.png)` — an escaped-space in an unquoted URL
        is a valid CSS URL character; the browser resolves it as
        `a%20b.png`, my scanner stopped at the space.

    Both are now covered. This pin locks the coverage.
    """
    fixture = r"""<!DOCTYPE html>
<html>
<body>
<!-- SVG <script href> — modern spelling -->
<svg><script href="https://cdn.example/svg-script.js"></script></svg>
<!-- SVG <script xlink:href> — legacy spelling -->
<svg><script xlink:href="https://cdn.example/legacy-svg-script.js"></script></svg>
<!-- SVG <script href="#local"> — fragment, allowed -->
<svg><script href="#local-anchor"></script></svg>

<!-- Escaped space in unquoted url() — real browsers fetch this. -->
<div style="background: url(https://cdn.example/a\ b.png)"></div>
<!-- Same idea in a <style> block -->
<style>
.escaped-bg { background-image: url(https://cdn.example/c\ d.png); }
</style>
</body>
</html>"""
    html_v = _find_external_html_resources(fixture)
    css_v = _find_external_css_resources(fixture)
    detected_html = {(tag, attr, url) for tag, attr, url, _ in html_v}
    detected_css_urls = {url for _, url, _ in css_v}

    # SVG <script> flagged (both spellings).
    assert ("script", "href",
            "https://cdn.example/svg-script.js") in detected_html, (
        f"SVG <script href> external not flagged. html_v={html_v!r}")
    assert ("script", "xlink:href",
            "https://cdn.example/legacy-svg-script.js") in detected_html, (
        f"SVG <script xlink:href> external not flagged. html_v={html_v!r}")
    # Fragment-only <script href="#local"> is allowed (self-contained).
    for tag, attr, url, _ in html_v:
        assert not (tag == "script" and url == "#local-anchor"), (
            f"fragment-only <script href> incorrectly flagged: "
            f"{tag} {attr}={url!r}")

    # Escaped-space CSS url() flagged in BOTH inline style and
    # <style> block. After _unescape_css, the URL reads `a b.png` /
    # `c d.png` — that's what the browser would resolve to.
    assert "https://cdn.example/a b.png" in detected_css_urls, (
        f"escaped-space url() in inline style not flagged. "
        f"css_v={css_v!r}")
    assert "https://cdn.example/c d.png" in detected_css_urls, (
        f"escaped-space url() in <style> block not flagged. "
        f"css_v={css_v!r}")


def test_self_containment_helper_catches_css_hex_escape_and_srcdoc():
    """F1 + F2 round-6 additions (2026-09-14). Codex intercepted real
    Chromium fetches for two more forms:

      * CSS hex escapes — `url(\\68 ttps://cdn.example/x.png)` decodes
        to `url(https://cdn.example/x.png)` and is fetched. The
        whitespace after `\\68` is the CSS escape terminator, NOT the
        URL boundary. `_UNQ` now includes `\\<1-6 hex>\\s?` as a URL
        character class; `_unescape_css` decodes hex escapes to
        `chr(int(hex, 16))` before the self-containment check.
      * `<iframe srcdoc>` — the attribute value is an entire
        HTML document embedded as entity-encoded text. Any
        `<img src>`, `<script src>`, `<style>` block, or inline
        `style="…"` inside srcdoc gets fetched by the browser.
        Scanner now decodes srcdoc entities via `html.unescape` and
        recurses at depth+1 (capped at `_MAX_SRCDOC_DEPTH=2` to
        prevent runaway).
    """
    fixture = """<!DOCTYPE html>
<html>
<body>
<!-- CSS hex escape: `\\68` = 'h', trailing space is escape terminator -->
<style>
.hex-in-style { background-image: url(\\68 ttps://cdn.example/hex-in-style.png); }
</style>
<div style="background-image: url(\\68 ttps://cdn.example/hex-inline.png)"></div>

<!-- iframe srcdoc: embedded HTML, external resources inside must be flagged -->
<iframe srcdoc="&lt;img src='https://cdn.example/srcdoc-img.png'&gt;"></iframe>
<iframe srcdoc="&lt;script src='https://cdn.example/srcdoc-script.js'&gt;&lt;/script&gt;"></iframe>
<iframe srcdoc="&lt;style&gt;@import 'https://cdn.example/srcdoc-import.css';&lt;/style&gt;"></iframe>
<iframe srcdoc="&lt;div style='background:url(https://cdn.example/srcdoc-inline-bg.png)'&gt;&lt;/div&gt;"></iframe>

<!-- iframe srcdoc containing only a data-URI image — must NOT flag -->
<iframe srcdoc="&lt;img src='data:image/png;base64,AAA'&gt;"></iframe>
</body>
</html>"""
    html_v = _find_external_html_resources(fixture)
    css_v = _find_external_css_resources(fixture)
    detected_css_urls = {url for _, url, _ in css_v}
    detected_html = {(tag, attr, url) for tag, attr, url, _ in html_v}

    # ── Hex escape in CSS url() flagged in both contexts ──
    assert "https://cdn.example/hex-in-style.png" in detected_css_urls, (
        f"hex-escape url() in <style> block not decoded. css_v={css_v!r}")
    assert "https://cdn.example/hex-inline.png" in detected_css_urls, (
        f"hex-escape url() in inline style not decoded. css_v={css_v!r}")

    # ── iframe srcdoc: HTML resources inside are flagged ──
    srcdoc_html_hits = [(tag, attr, url) for (tag, attr, url) in detected_html
                        if "iframe@srcdoc>" in tag]
    assert any(
        "img" in tag and url == "https://cdn.example/srcdoc-img.png"
        for tag, _attr, url in srcdoc_html_hits), (
        f"<img> inside srcdoc not flagged. srcdoc_html_hits={srcdoc_html_hits!r}")
    assert any(
        "script" in tag and url == "https://cdn.example/srcdoc-script.js"
        for tag, _attr, url in srcdoc_html_hits), (
        f"<script src> inside srcdoc not flagged. "
        f"srcdoc_html_hits={srcdoc_html_hits!r}")

    # ── srcdoc <style> block @import flagged ──
    srcdoc_css_hits = [(kind, url) for kind, url, _ in css_v
                       if "srcdoc" in kind]
    assert any(
        "srcdoc><style>" in kind and "@import" in kind
        and url == "https://cdn.example/srcdoc-import.css"
        for kind, url in srcdoc_css_hits), (
        f"<style> @import inside srcdoc not flagged. "
        f"srcdoc_css_hits={srcdoc_css_hits!r}")

    # ── srcdoc inline style="…" url() flagged ──
    assert any(
        url == "https://cdn.example/srcdoc-inline-bg.png"
        for _kind, url in srcdoc_css_hits), (
        f"inline style url() inside srcdoc not flagged. "
        f"srcdoc_css_hits={srcdoc_css_hits!r}")

    # ── Data-URI-only srcdoc content produces NO violations ──
    data_only_flags = [
        v for v in html_v
        if "iframe@srcdoc>" in v[0] and v[2].startswith("AAA")
    ]
    assert not data_only_flags, (
        f"data-URI content inside srcdoc incorrectly flagged: "
        f"{data_only_flags!r}")


def test_srcdoc_double_encoded_literal_does_not_false_positive():
    """F1 round-7 negative-control. HTMLParser already decodes
    character references in attribute values (Python `html.parser`
    behavior, `convert_charrefs` flag notwithstanding — that flag
    only governs DATA callback decoding, not attribute values).

    A DOUBLE-encoded srcdoc — `&amp;lt;img&amp;gt;` inside a
    srcdoc attribute — is a document that a browser would render
    as LITERAL characters `<img>` (text, not markup). Chromium
    intercept confirms: no fetch. Our scanner must match: no
    violation. Pre-F1-round-7 the scanner double-decoded via
    `html.unescape` and synthetically produced a real `<img>` tag
    to scan, false-positiving on legitimate documents that
    intentionally demonstrate escaped HTML inside srcdoc.
    """
    fixture = (
        '<!DOCTYPE html><html><body>'
        # Double-encoded: HTMLParser decodes ONCE to `&lt;img src=\'X\'&gt;`
        # which browsers render as literal text. Our scanner must
        # NOT decode a second time.
        '<iframe srcdoc="&amp;lt;img src=\'https://cdn.example/literal.png\'&amp;gt;"></iframe>'
        '</body></html>'
    )
    html_v = _find_external_html_resources(fixture)
    literal_hits = [v for v in html_v
                    if "literal.png" in v[2]]
    assert not literal_hits, (
        f"Double-encoded literal in srcdoc false-positived: "
        f"{literal_hits!r}. HTMLParser already decoded once; the "
        f"scanner must not decode again.")


def test_srcdoc_beyond_depth_cap_fails_closed():
    """F2 round-7 fail-closed invariant. Beyond `_MAX_SRCDOC_DEPTH`
    the scanner must emit an explicit UNSCANNED violation rather
    than silently skip. Chromium fetches resources at any nesting
    depth, so silent skipping contradicts the self-containment
    guarantee.

    Constructs a chain of `_MAX_SRCDOC_DEPTH + 1` nested srcdocs
    with a real external at the innermost level. The scanner
    should surface EITHER the external (if within depth) OR the
    UNSCANNED violation (if the innermost sits beyond the cap).
    Either outcome proves the scanner did not silently accept.
    """
    max_depth = _HTMLResourceScanner._MAX_SRCDOC_DEPTH
    # Build a chain of `max_depth + 1` nested srcdocs so the
    # deepest one sits beyond the cap.
    innermost = ('<script src="https://cdn.example/deep-buried.js">'
                 '</script>')
    # Encode one layer of `<iframe srcdoc="...">` `max_depth + 1`
    # times. Each layer's payload becomes the srcdoc value of the
    # next enclosing iframe (HTML-encoded).
    import html as _h
    payload = innermost
    for _ in range(max_depth + 1):
        payload = f'<iframe srcdoc="{_h.escape(payload, quote=True)}"></iframe>'
    fixture = f"<!DOCTYPE html><html><body>{payload}</body></html>"
    html_v = _find_external_html_resources(fixture)
    unscanned_hits = [v for v in html_v if "UNSCANNED" in v[0]]
    external_hits = [v for v in html_v
                     if "deep-buried.js" in v[2]]
    # Either the external must surface (scanner covered the full
    # nesting) OR the UNSCANNED sentinel fired (scanner refused to
    # accept without inspection). Silent skip is the failure mode.
    assert unscanned_hits or external_hits, (
        f"Beyond-cap nested srcdoc silently accepted — neither the "
        f"external nor an UNSCANNED violation was reported. "
        f"html_v={html_v!r}")


def test_srcdoc_within_depth_cap_flags_external():
    """F2 round-7 companion: WITHIN the depth cap, nested srcdocs
    are still recursed. Three-level nesting (which Codex probed
    specifically) must flag the innermost external resource
    provided the cap allows that depth."""
    max_depth = _HTMLResourceScanner._MAX_SRCDOC_DEPTH
    if max_depth < 3:
        import pytest as _p
        _p.skip(
            f"_MAX_SRCDOC_DEPTH={max_depth} < 3 — three-level test "
            f"expects the scanner to recurse at least three levels")
    # Three-level nesting: outer → mid → inner → external <script>.
    inner_body = ('<svg><script href="https://cdn.example/deep-script.js">'
                  '</script></svg>')
    import html as _h
    level_2 = _h.escape(inner_body, quote=True)
    level_1 = _h.escape(f'<iframe srcdoc="{level_2}"></iframe>',
                        quote=True)
    top = f'<iframe srcdoc="{level_1}"></iframe>'
    fixture = f"<!DOCTYPE html><html><body>{top}</body></html>"
    html_v = _find_external_html_resources(fixture)
    deep_hits = [v for v in html_v if "deep-script.js" in v[2]]
    assert deep_hits, (
        f"Three-level nested srcdoc external not flagged. "
        f"html_v={html_v!r}")


def test_css_hex_escape_decoder_handles_full_range():
    """Meta-pin on `_unescape_css` itself. CSS spec allows 1-6 hex
    digits per escape, with an optional whitespace terminator.
    Exercises: single digit, six digits, terminator whitespace
    consumed, plain char escape passthrough.
    """
    # `\68` = 'h' (2 hex digits, no terminator; followed by 't'
    # which is NOT a hex digit, so escape ends after 68).
    assert _unescape_css(r"\68ttp://x") == "http://x"
    # `\68 ` = 'h' with terminator space consumed.
    assert _unescape_css(r"\68 ttp://x") == "http://x"
    # Non-hex boundary: `\002F` = '/' (4 hex digits, followed by
    # 'z' which is not a hex digit, so escape ends).
    assert _unescape_css(r"a\002Fz") == "a/z"
    # Terminator-space form: `\002F b` = '/' + 'b'.
    assert _unescape_css(r"a\002F b") == "a/b"
    # CSS greediness up to 6 hex: `\002Fb` is FIVE hex digits
    # (b is a hex digit), decoded as U+002FB. Not `/b`. This is
    # correct per spec — to get `/b` you must terminate the
    # escape, e.g. `\002F b` (with space) or `\00002Fb` (six
    # digits + literal 'b').
    assert _unescape_css(r"a\002Fb") == "a˻"
    # Six-digit maximum: `\01F600` = smiling face emoji U+1F600.
    assert _unescape_css(r"\01F600") == "\U0001F600"
    # Plain char escape (F2 round-5 path): `\ ` = ' '.
    assert _unescape_css(r"a\ b") == "a b"
    # Mixed: `\68i\ j` = 'h' + 'i' + ' ' + 'j'.
    assert _unescape_css(r"\68i\ j") == "hi j"


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
