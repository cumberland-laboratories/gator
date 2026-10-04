"""#45 — closed display formatter for expanded Loop artifacts (Playwright).

M1/M2: unit-in-page tests of ``window.GatorLoopMarkdown`` (one case per
grammar row and inline rule of plan rev 2), an element/attribute allowlist
walk over an adversarial corpus, the image-before-link guard (no ``img``, no
``a``, no request), the link policy, malformed input, and the size bound.
"""

import json

import pytest

from .test_loop_workspace import _navigate_to_loop

ALLOWED_TAGS = {"h3", "h4", "h5", "h6", "p", "ul", "li", "pre", "code", "strong",
                "a", "table", "thead", "tbody", "tr", "th", "td", "blockquote",
                "hr", "div", "span"}
ALLOWED_CLASSES = {"md-indent-0", "md-indent-1", "md-indent-2", "md-indent-3",
                   "loop-md-tablewrap", "loop-md-link-blocked"}

_RENDER_JS = """md => {
    var host = document.createElement('div');
    host.appendChild(window.GatorLoopMarkdown.render(md));
    var nodes = Array.from(host.querySelectorAll('*')).map(function (n) {
        return {tag: n.tagName.toLowerCase(), cls: n.className,
                attrs: Array.from(n.attributes).map(function (a) { return a.name; }),
                text: n.textContent, href: n.getAttribute('href'),
                target: n.getAttribute('target'), rel: n.getAttribute('rel')};
    });
    return {nodes: nodes, text: host.textContent, html: host.innerHTML};
}"""


@pytest.fixture
def md(page, dashboard_fleet):
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_function("() => !!window.GatorLoopMarkdown", timeout=10000)
    return lambda text: page.evaluate(_RENDER_JS, text)


def _tags(r):
    return [n["tag"] for n in r["nodes"]]


def _assert_allowlisted(r):
    for n in r["nodes"]:
        assert n["tag"] in ALLOWED_TAGS, n
        for a in n["attrs"]:
            if n["tag"] == "a":
                assert a in ("href", "target", "rel"), n
            else:
                assert a == "class", n
        if n["cls"]:
            assert n["cls"] in ALLOWED_CLASSES, n


# ── line rules ───────────────────────────────────────────────────────────

def test_fence_is_literal_and_runs_to_eof(md):
    r = md("```js\n<script>alert(1)</script>\n<b>x</b>\n```\nafter")
    assert _tags(r)[:2] == ["pre", "code"]
    assert "<script>alert(1)</script>" in r["nodes"][1]["text"]
    assert "script" not in _tags(r) and "b" not in _tags(r)
    r2 = md("```\nunclosed\nstill code")
    assert _tags(r2) == ["pre", "code"] and "still code" in r2["text"]


@pytest.mark.parametrize("src,tag", [("# A", "h3"), ("## A", "h4"), ("### A", "h5"),
                                     ("#### A", "h6"), ("###### A", "h6")])
def test_headings_demoted(md, src, tag):
    assert _tags(md(src)) == [tag]


def test_seven_hashes_is_paragraph(md):
    assert _tags(md("####### x")) == ["p"]


@pytest.mark.parametrize("src", ["---", "***", "___", "  ---  "])
def test_hr(md, src):
    assert _tags(md(src)) == ["hr"]


def test_blockquote_one_line(md):
    r = md("> quoted **b**")
    assert _tags(r) == ["blockquote", "strong"]


def test_flat_list_with_indent_classes(md):
    r = md("- a\n  - b\n    * c\n          + d")
    assert _tags(r) == ["ul", "li", "li", "li", "li"]
    assert [n["cls"] for n in r["nodes"][1:]] == [
        "md-indent-0", "md-indent-1", "md-indent-2", "md-indent-3"]


def test_numbered_items_literal_number_no_ol(md):
    r = md("1. one\n2. two")
    assert "ol" not in _tags(r)
    assert [n["text"] for n in r["nodes"] if n["tag"] == "li"] == ["1. one", "2. two"]


def test_table_ragged_and_naive_split(md):
    r = md("| a | b |\n|---|:-:|\n| 1 | 2 | 3 |\n| x |\n| p \\| q |")
    tags = _tags(r)
    assert tags[0] == "div" and r["nodes"][0]["cls"] == "loop-md-tablewrap"
    assert len([n for n in r["nodes"] if n["tag"] == "tr"]) == 4
    cells = [n["text"] for n in r["nodes"] if n["tag"] in ("th", "td")]
    # header 2 wide; extra cell trimmed, short row padded, "\\|" splits.
    assert cells == ["a", "b", "1", "2", "x", "", "p \\", "q"]


def test_table_caps_32_columns(md):
    head = "|" + "|".join(str(i) for i in range(40)) + "|"
    r = md(head + "\n|" + "---|" * 40)
    assert len([n for n in r["nodes"] if n["tag"] == "th"]) == 32


def test_table_without_delimiter_is_paragraph(md):
    assert _tags(md("| a | b |\n| 1 | 2 |")) == ["p"]


def test_paragraph_join_and_blank_split(md):
    r = md("one\ntwo\n\nthree")
    ps = [n["text"] for n in r["nodes"] if n["tag"] == "p"]
    assert ps == ["one two", "three"]


# ── inline rules ─────────────────────────────────────────────────────────

def test_code_span_literal_inside(md):
    r = md("x `**not bold** [a](https://a.example)` y")
    assert _tags(r) == ["p", "code"]
    assert r["nodes"][1]["text"] == "**not bold** [a](https://a.example)"


def test_bold_content_literal(md):
    r = md("**[x](https://a.example)**")
    assert _tags(r) == ["p", "strong"]
    assert r["nodes"][1]["text"] == "[x](https://a.example)"


def test_link_text_literal(md):
    r = md("[**b**](https://a.example)")
    assert _tags(r) == ["p", "a"] and r["nodes"][1]["text"] == "**b**"


@pytest.mark.parametrize("src", ["`unclosed", "**unclosed", "[x](", "![x](", "*em*",
                                 "_x_", "snake_case_name", "__u__", "a \\* b"])
def test_unmatched_and_unsupported_are_literal(md, src):
    r = md(src)
    assert _tags(r) == ["p"] and r["text"] == src


def test_safe_external_link(md):
    r = md("[ok](https://ok.example/path?q=1)")
    a = [n for n in r["nodes"] if n["tag"] == "a"][0]
    assert a["href"] == "https://ok.example/path?q=1"
    assert a["target"] == "_blank"
    assert "noopener" in a["rel"] and "noreferrer" in a["rel"]


@pytest.mark.parametrize("url", [
    "javascript:alert", "JaVaScRiPt:void", "java&#x73;cript:x",
    "data:text/html,x", "vbscript:x", "//evil.example", "relative.md", "#frag",
    "file:///etc/passwd", "mailto:a@b.c", "http://a.example/\\x",
])
def test_unsafe_links_are_inert(md, url):
    r = md("[t](%s)" % url)
    assert "a" not in _tags(r)
    blocked = [n for n in r["nodes"] if n["cls"] == "loop-md-link-blocked"]
    assert blocked and blocked[0]["text"] == "t (%s)" % url


def test_paren_url_is_fully_literal(md):
    # URLs containing parentheses never match the link rule: plain literal.
    r = md("[t](javascript:alert(1))")
    assert "a" not in _tags(r) and r["text"] == "[t](javascript:alert(1))"


@pytest.mark.parametrize("src", ["![x](http://evil.example/beacon)",
                                 "![x](https://ok.example/a.png)"])
def test_image_is_literal_no_img_no_link_no_request(page, md, src):
    requests = []
    page.on("request", lambda req: requests.append(req.url))
    r = md(src)
    page.evaluate("""md => { var d = document.createElement('div');
        d.appendChild(window.GatorLoopMarkdown.render(md));
        document.body.appendChild(d); }""", src)
    page.wait_for_timeout(300)
    assert "img" not in _tags(r) and "a" not in _tags(r)
    assert r["text"] == src
    assert not [u for u in requests if "example" in u]


# ── adversarial corpus + allowlist ───────────────────────────────────────

ADVERSARIAL = "\n".join([
    "<img src=x onerror=alert(1)>", "<svg onload=alert(1)>",
    "<style>body{display:none}</style>", "<iframe src=//evil></iframe>",
    "<!-- comment -->", '<a href="javascript:alert(1)">x</a>',
    "# <script>alert(1)</script>", "- <b onclick=x>b</b>",
    "| <i>a</i> | b |", "|---|---|", "| [x](javascript:1) | ![i](https://e/a.png) |",
    "> <div style='position:fixed'>x</div>", "&lt;script&gt;",
])


def test_adversarial_corpus_allowlisted(md):
    r = md(ADVERSARIAL)
    _assert_allowlisted(r)
    assert not {"img", "svg", "style", "iframe", "script", "b", "i"} & set(_tags(r))
    assert "<script>alert(1)</script>" in r["text"]
    assert "&lt;script&gt;" in r["text"]  # entities never decoded


def test_representative_document_allowlisted(md):
    doc = "\n".join(["# Plan", "", "Intro **bold** and `code`.", "",
                     "- a", "  - b", "1. one", "", "| h | i |", "|---|---|",
                     "| 1 | 2 |", "", "> note", "---", "```", "x < y", "```",
                     "[ok](https://ok.example)"])
    _assert_allowlisted(md(doc))


# ── malformed input + bounds ─────────────────────────────────────────────

@pytest.mark.parametrize("src", ["", "|", "```", "\n\n\n", " " * 50 + "- x",
                                 "[" * 500, "**" * 300, "`" * 301])
def test_malformed_never_throws(md, src):
    md(src)


def test_crlf_normalized(md):
    r = md("# A\r\nline one\r\nline two")
    assert _tags(r) == ["h3", "p"] and r["nodes"][1]["text"] == "line one line two"


def test_too_large_throws_named_error(page, md):
    name = page.evaluate("""() => {
        var big = 'x'.repeat(window.GatorLoopMarkdown.MAX_RENDER_CHARS + 1);
        try { window.GatorLoopMarkdown.render(big); return 'no-throw'; }
        catch (e) { return e.name; }
    }""")
    assert name == "TooLarge"
    ok = page.evaluate("""() => window.GatorLoopMarkdown.render(
        'x'.repeat(window.GatorLoopMarkdown.MAX_RENDER_CHARS)).textContent.length""")
    assert ok == 200000


def test_safe_href_direct(page, md):
    res = page.evaluate("""() => [
        window.GatorLoopMarkdown.safeHref('https://a.example'),
        window.GatorLoopMarkdown.safeHref(' http://a.example/x '),
        window.GatorLoopMarkdown.safeHref('https://a .example'),
        window.GatorLoopMarkdown.safeHref(''),
        window.GatorLoopMarkdown.safeHref(null)]""")
    assert res == ["https://a.example/", "http://a.example/x", None, None, None]


# ═════════════════════════════════════════════════════════════════════════
# M3: expanded artifact body in the Loop workspace
# ═════════════════════════════════════════════════════════════════════════

from .test_loop_workspace import (  # noqa: E402
    _ACTIVE_ID, _live_payload, _select_loop_card, _serve_mutable_loop,
    _unserve_mutable_loop)

PLAN_SEL = '.loop-artifact-section[data-artifact="plan.current.md"]'
PLAN_DOC = "\n".join([
    "# Plan v1", "", "## Executive Summary", "", "- one", "- two", "",
    "| a | b |", "|---|---|", "| 1 | 2 |", "", "```", "<script>x</script>", "```",
    "", "Body text with **bold** and [ok](https://ok.example).", "",
    "## Final Heading Zeta", "", "the end",
])


class _Plan:
    """Serve plan.current.md from a mutable holder and count requests."""

    def __init__(self, page, text):
        self.text = text
        self.count = 0
        self.held = []
        self.hold = False
        self.page = page
        page.route("**/" + _ACTIVE_ID + "/artifact/plan.current.md", self._handle)

    def _handle(self, route):
        self.count += 1
        if self.hold:
            self.held.append(route)
            return
        route.fulfill(status=200, content_type="text/plain; charset=utf-8",
                      body=self.text)

    def close(self):
        try:
            self.page.unroute("**/" + _ACTIVE_ID + "/artifact/plan.current.md")
        except Exception:
            pass


def _open_loop(page, fleet, payload):
    _serve_mutable_loop(page, payload)
    _navigate_to_loop(page, fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_selector(PLAN_SEL, timeout=10000)


_CLICK_TOGGLE = "s => document.querySelector(s + ' .loop-artifact-toggle').click()"
_CLICK_RAW = ("s => document.querySelector(s + ' .loop-artifact-viewbtn"
              "[data-view=raw]').click()")


def _expand_plan(page):
    page.evaluate(_CLICK_TOGGLE, PLAN_SEL)
    page.wait_for_function("""s => {
        var c = document.querySelector(s + ' .loop-artifact-content');
        return c && c.dataset.loaded === '1' && c.querySelector('.loop-artifact-viewbar');
    }""", arg=PLAN_SEL, timeout=10000)


_STATE_JS = """s => {
    var c = document.querySelector(s + ' .loop-artifact-content');
    var btn = function (v) { return c.querySelector('.loop-artifact-viewbtn[data-view=' + v + ']'); };
    return {
        rendered_pressed: btn('rendered').getAttribute('aria-pressed'),
        raw_pressed: btn('raw').getAttribute('aria-pressed'),
        rendered_disabled: btn('rendered').disabled,
        md_hidden: c.querySelector(':scope > .loop-md').hidden,
        raw_hidden: c.querySelector(':scope > .loop-artifact-pre').hidden,
        caption: c.querySelector('.loop-artifact-viewstate').textContent,
        raw_text: c.querySelector(':scope > .loop-artifact-pre').textContent,
        md_text: c.querySelector(':scope > .loop-md').textContent,
        md_tags: Array.from(c.querySelectorAll(':scope > .loop-md *'))
            .map(function (n) { return n.tagName.toLowerCase(); }),
    };
}"""


def _view_state(page):
    return page.evaluate(_STATE_JS, PLAN_SEL)


def _switch_raw(page):
    page.evaluate(_CLICK_RAW, PLAN_SEL)


def _wait_raw_contains(page, needle):
    page.wait_for_function("""a => document.querySelector(a[0] + ' .loop-artifact-pre')
        .textContent.indexOf(a[1]) !== -1""", arg=[PLAN_SEL, needle], timeout=10000)


def test_collapsed_card_has_no_excerpt_and_no_fetch(page, dashboard_fleet):
    plan = _Plan(page, PLAN_DOC)
    try:
        _open_loop(page, dashboard_fleet, _live_payload())
        page.wait_for_timeout(1500)
        assert plan.count == 0, "collapsed plan card must not fetch"
        n = page.evaluate("""s => document.querySelector(s).querySelectorAll(
            '.loop-artifact-summary, .loop-summary-text, .loop-summary-absent').length""",
                          PLAN_SEL)
        assert n == 0
        _expand_plan(page)
        assert plan.count == 1
    finally:
        plan.close()
        _unserve_mutable_loop(page)


def test_expand_renders_full_document_by_default_and_raw_parity(page, dashboard_fleet):
    plan = _Plan(page, PLAN_DOC)
    try:
        _open_loop(page, dashboard_fleet, _live_payload())
        _expand_plan(page)
        st = _view_state(page)
        assert st["rendered_pressed"] == "true" and st["raw_pressed"] == "false"
        assert st["md_hidden"] is False and st["raw_hidden"] is True
        assert st["caption"].startswith("Showing: rendered Markdown")
        assert "Final Heading Zeta" in st["md_text"] and "the end" in st["md_text"]
        assert {"h3", "h4", "ul", "table", "pre", "strong", "a"} <= set(st["md_tags"])
        assert "script" not in st["md_tags"]
        # Raw is the exact fetched string (byte-for-byte with what was served).
        assert st["raw_text"] == PLAN_DOC
    finally:
        plan.close()
        _unserve_mutable_loop(page)


def test_keyboard_switch_without_refetch(page, dashboard_fleet):
    plan = _Plan(page, PLAN_DOC)
    try:
        _open_loop(page, dashboard_fleet, _live_payload())
        _expand_plan(page)
        before = plan.count
        page.focus(PLAN_SEL + " .loop-artifact-viewbtn[data-view=raw]")
        page.keyboard.press("Space")
        st = _view_state(page)
        assert st["raw_pressed"] == "true" and st["rendered_pressed"] == "false"
        assert st["raw_hidden"] is False and st["md_hidden"] is True
        assert st["caption"].startswith("Showing: raw text")
        page.keyboard.press("Shift+Tab")
        page.keyboard.press("Enter")
        assert _view_state(page)["rendered_pressed"] == "true"
        page.wait_for_timeout(300)
        assert plan.count == before, "switching views must not refetch"
    finally:
        plan.close()
        _unserve_mutable_loop(page)


_OBSERVE_JS = """s => {
    window.__mut = 0;
    new MutationObserver(function (r) { window.__mut += r.length; })
      .observe(document.querySelector(s), {childList: true, subtree: true,
               characterData: true, attributes: true});
    window.__renders = 0;
    var orig = window.GatorLoopMarkdown.render;
    window.GatorLoopMarkdown.render = function (t) { window.__renders++; return orig(t); };
}"""


def test_unchanged_polls_zero_mutations_in_raw(page, dashboard_fleet):
    plan = _Plan(page, PLAN_DOC)
    try:
        _open_loop(page, dashboard_fleet, _live_payload())
        _expand_plan(page)
        _switch_raw(page)
        page.wait_for_timeout(500)
        page.evaluate(_OBSERVE_JS, "#loop-artifacts")
        page.wait_for_timeout(7000)  # >= two unchanged polls
        assert page.evaluate("() => window.__mut") == 0
        assert page.evaluate("() => window.__renders") == 0
    finally:
        plan.close()
        _unserve_mutable_loop(page)


def test_changed_artifact_refreshes_both_panes_and_keeps_raw(page, dashboard_fleet):
    payload = _live_payload()
    plan = _Plan(page, PLAN_DOC)
    try:
        _open_loop(page, dashboard_fleet, payload)
        _expand_plan(page)
        _switch_raw(page)
        plan.text = PLAN_DOC.replace("Plan v1", "Plan v2-NEW")
        payload["events"].append(
            {"event": "draft_submitted", "ts": "2026-09-22T10:06:00Z", "round": 2,
             "role": "draftor", "artifact_path": "plan.round-2.md"})
        _wait_raw_contains(page, "Plan v2-NEW")
        st = _view_state(page)
        assert "Plan v2-NEW" in st["md_text"] and "Plan v2-NEW" in st["raw_text"]
        assert st["raw_pressed"] == "true" and st["raw_hidden"] is False
    finally:
        plan.close()
        _unserve_mutable_loop(page)


def test_unchanged_refetch_is_equality_noop(page, dashboard_fleet):
    payload = _live_payload()
    plan = _Plan(page, PLAN_DOC)
    try:
        _open_loop(page, dashboard_fleet, payload)
        _expand_plan(page)
        page.wait_for_timeout(500)
        before = plan.count
        page.evaluate(_OBSERVE_JS, PLAN_SEL + " .loop-artifact-content")
        payload["events"].append(
            {"event": "review_submitted", "ts": "2026-09-22T10:07:00Z", "round": 2,
             "role": "reviewer"})
        for _ in range(80):
            if plan.count > before:
                break
            page.wait_for_timeout(100)
        assert plan.count > before, "the mutable refresh should refetch"
        page.wait_for_timeout(800)
        assert page.evaluate("() => window.__mut") == 0
        assert page.evaluate("() => window.__renders") == 0
    finally:
        plan.close()
        _unserve_mutable_loop(page)


def test_stale_response_cannot_reset_view_or_text(page, dashboard_fleet):
    payload = _live_payload()
    plan = _Plan(page, PLAN_DOC)
    try:
        _open_loop(page, dashboard_fleet, payload)
        _expand_plan(page)
        _switch_raw(page)
        plan.hold = True                      # the next refetch is held (stale)
        payload["events"].append(
            {"event": "draft_submitted", "ts": "2026-09-22T10:06:00Z", "round": 2,
             "role": "draftor", "artifact_path": "plan.round-2.md"})
        for _ in range(80):
            if plan.held:
                break
            page.wait_for_timeout(100)
        assert plan.held
        plan.hold = False                     # a newer refresh is served NEW
        plan.text = PLAN_DOC.replace("Plan v1", "Plan v3-NEWEST")
        payload["events"].append(
            {"event": "review_submitted", "ts": "2026-09-22T10:07:00Z", "round": 2,
             "role": "reviewer"})
        _wait_raw_contains(page, "Plan v3-NEWEST")
        for route in plan.held:               # the stale response arrives late
            route.fulfill(status=200, content_type="text/plain; charset=utf-8",
                          body=PLAN_DOC.replace("Plan v1", "Plan v2-STALE"))
        page.wait_for_timeout(800)
        st = _view_state(page)
        assert "Plan v3-NEWEST" in st["raw_text"] and "STALE" not in st["raw_text"]
        assert "STALE" not in st["md_text"]
        assert st["raw_pressed"] == "true"
    finally:
        plan.close()
        _unserve_mutable_loop(page)


def test_too_large_falls_back_to_raw(page, dashboard_fleet):
    big = "x" * 200001
    plan = _Plan(page, big)
    try:
        _open_loop(page, dashboard_fleet, _live_payload())
        _expand_plan(page)
        st = _view_state(page)
        assert st["rendered_disabled"] is True and st["raw_hidden"] is False
        assert st["caption"] == "Too large to render (200,001 characters); showing raw text"
        assert len(st["raw_text"]) == 200001
        page.evaluate(_CLICK_TOGGLE, PLAN_SEL)   # collapse
        page.evaluate(_CLICK_TOGGLE, PLAN_SEL)   # expand again (still loaded)
        assert _view_state(page)["raw_hidden"] is False
    finally:
        plan.close()
        _unserve_mutable_loop(page)


def test_render_failure_shows_raw_and_keeps_polling(page, dashboard_fleet):
    plan = _Plan(page, PLAN_DOC)
    try:
        _open_loop(page, dashboard_fleet, _live_payload())
        page.evaluate("""() => { window.GatorLoopMarkdown.render = function () {
            throw new Error('boom'); }; }""")
        _expand_plan(page)
        st = _view_state(page)
        assert st["caption"] == "Could not render Markdown; showing raw text"
        assert st["raw_hidden"] is False and st["raw_text"] == PLAN_DOC
        assert st["rendered_disabled"] is True
        assert page.evaluate(
            "() => document.querySelector('.loop-workspace').dataset.polling") == "1"
    finally:
        plan.close()
        _unserve_mutable_loop(page)
