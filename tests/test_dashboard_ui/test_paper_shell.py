"""Dashboard Paper shell Playwright pins (#80, #5).

Each test proves a distinct risk:

- the page header is title-only on every view: #topbar-subtitle stays in
  the DOM, hidden and empty, and the Repo branch-history picker appears in
  #topbar-repo-tools only on the Repo route;
- the Paper frame keeps the shell bounded: strip, sidebar and header have
  their Paper geometry and the page never scrolls, at desktop and narrow
  widths;
- the sidebar context card shows the active repository from its Fleet
  record (or the empty state), as text only, and is hidden when narrow;
- the Welcome sidebar item navigates, and unavailable items carry a
  non-colour cue (aria-disabled and an explanatory title).
"""

import pytest

from ._harness import sole_active_loop_list


def _origin(fleet):
    return fleet["url"].rstrip("/") + "/"


# (query, wait selector, expected #topbar-title)
_VIEWS = [
    ("", ".welcome-workspace", "Welcome to Gator!"),
    ("?view=fleet", "#view-slot table.data-table", "Fleet"),
    ("?repo=alpha", ".repo-file-item", "Repo"),
    ("?repo=alpha&view=history", "#view-slot", "Commits"),
    ("?repo=alpha&view=loop", "#loop-tabbar", "Loop"),
    ("?view=docs", ".docs-sidebar", "Docs"),
    ("?view=updates", "#view-slot", "Updates"),
]


@pytest.mark.parametrize("query,ready,title", _VIEWS)
def test_header_is_title_only(page, dashboard_fleet, query, ready, title):
    """Every view writes only the title. The subtitle is hidden and empty;
    the Repo tools are shown, holding the branch-history picker, on Repo
    only, and are hidden and empty elsewhere."""
    page.goto(_origin(dashboard_fleet) + query, wait_until="load")
    page.wait_for_selector(ready, timeout=15000)
    page.wait_for_function(
        "t => document.getElementById('topbar-title').textContent === t",
        arg=title, timeout=10000)
    head = page.evaluate("""() => {
        const sub = document.getElementById('topbar-subtitle');
        const tools = document.getElementById('topbar-repo-tools');
        return {
            subHidden: sub.hidden, subText: sub.textContent,
            subKids: sub.childElementCount,
            subShown: sub.getBoundingClientRect().height > 0,
            toolsHidden: tools.hidden,
            toolsShown: tools.getBoundingClientRect().width > 0,
            picker: !!tools.querySelector('#branch-history-btn'),
            pickerAnywhere: document.querySelectorAll('#branch-history-btn').length,
        };
    }""")
    assert head["subHidden"] is True and head["subText"] == ""
    assert head["subKids"] == 0 and head["subShown"] is False
    if query == "?repo=alpha":
        assert head["toolsHidden"] is False and head["toolsShown"] is True
        assert head["picker"] is True and head["pickerAnywhere"] == 1
    else:
        assert head["toolsHidden"] is True and head["toolsShown"] is False
        assert head["pickerAnywhere"] == 0


@pytest.mark.parametrize("viewport,header", [((1440, 900), 88), ((375, 700), 64)])
def test_paper_frame_geometry_bounded(page, dashboard_fleet, viewport, header):
    """The 46px strip, the 244px sidebar (desktop) and the Paper header
    height; the title sits in the header; the page never scrolls."""
    page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
    page.goto(_origin(dashboard_fleet) + "?repo=alpha", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    geo = page.evaluate("""() => {
        const r = s => document.querySelector(s).getBoundingClientRect();
        const de = document.documentElement;
        return {
            strip: r('#workspace-strip').height,
            sidebar: r('#sidebar').width,
            header: r('#topbar').height,
            titleTop: r('#topbar-title').top, titleBottom: r('#topbar-title').bottom,
            headerTop: r('#topbar').top, headerBottom: r('#topbar').bottom,
            vw: de.clientWidth,
            docScrollY: de.scrollHeight - de.clientHeight,
            docScrollX: de.scrollWidth - de.clientWidth,
        };
    }""")
    assert geo["strip"] == 46
    assert geo["header"] == header
    assert geo["headerTop"] <= geo["titleTop"] and geo["titleBottom"] <= geo["headerBottom"]
    if viewport[0] == 1440:
        assert geo["sidebar"] == 244
    else:
        assert geo["sidebar"] == geo["vw"]  # the sidebar becomes a full-width row
    assert geo["docScrollY"] == 0 and geo["docScrollX"] == 0


# ── Sidebar context card, Welcome item, unavailable items (checkpoint 3) ──

_CARD_JS = """() => {
    const c = document.getElementById('sidebar-context');
    const q = s => c.querySelector(s);
    return {
        name: q('.ctx-name') && q('.ctx-name').textContent,
        empty: !!q('.ctx-name.ctx-empty'),
        meta: q('.ctx-meta') && q('.ctx-meta').textContent,
        branch: q('.ctx-branch') && q('.ctx-branch').textContent,
        version: q('.ctx-version') && q('.ctx-version').textContent,
        elements: Array.from(c.querySelectorAll('*')).map(e => e.tagName + '.' + e.className),
        shown: c.getBoundingClientRect().height > 0,
    };
}"""


def _fleet_record(page, fleet, name):
    data = page.evaluate("u => fetch(u).then(r => r.json())", _origin(fleet) + "api/data")
    repos = (data.get("fleet") or {}).get("repos") or data.get("repos") or []
    return next(r for r in repos if r["name"] == name)


def test_context_card_shows_repository_and_empty_state(page, dashboard_fleet):
    """With no repository the card shows the empty state; selecting alpha
    shows its name, branch and Gator version from the Fleet record."""
    page.goto(_origin(dashboard_fleet), wait_until="load")
    page.wait_for_selector(".welcome-workspace", timeout=15000)
    card = page.evaluate(_CARD_JS)
    assert card["name"] == "None selected" and card["empty"] is True
    assert card["meta"] == "Choose one in Fleet" and card["shown"] is True

    rec = _fleet_record(page, dashboard_fleet, "alpha")
    assert rec.get("branch"), "the seeded repository is a Git repository with a branch"
    page.goto(_origin(dashboard_fleet) + "?repo=alpha", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    card = page.evaluate(_CARD_JS)
    assert card["name"] == "alpha" and card["empty"] is False
    assert card["branch"] == (rec.get("branch") or None)
    assert card["version"] == (rec.get("cli_version") or None)
    expected_meta = " · ".join(
        p for p in [rec.get("branch") or "",
                    ("Gator " + rec["cli_version"]) if rec.get("cli_version") else ""] if p)
    assert (card["meta"] or "") == expected_meta


def test_context_card_renders_text_literally(page, dashboard_fleet):
    """Fleet values reach the card as text: a branch that looks like markup
    is shown literally and creates no element."""
    hostile = '<b id="injected">dev</b><img src=x>'

    def patch(route):
        resp = route.fetch()
        data = resp.json()
        repos = (data.get("fleet") or {}).get("repos") or data.get("repos") or []
        for r in repos:
            if r["name"] == "alpha":
                r["branch"] = hostile
        route.fulfill(response=resp, json=data)

    page.route("**/api/data", patch)
    page.goto(_origin(dashboard_fleet) + "?repo=alpha", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    card = page.evaluate(_CARD_JS)
    assert card["branch"] == hostile
    assert page.evaluate("() => document.getElementById('injected')") is None
    assert all(e.split(".")[0] in ("DIV", "SPAN") for e in card["elements"]), card["elements"]


def test_context_card_hidden_when_narrow(page, dashboard_fleet):
    page.set_viewport_size({"width": 375, "height": 700})
    page.goto(_origin(dashboard_fleet) + "?repo=alpha", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    assert page.evaluate(_CARD_JS)["shown"] is False
    assert page.evaluate(
        "() => document.documentElement.scrollHeight - document.documentElement.clientHeight") == 0


def test_welcome_sidebar_item_navigates(page, dashboard_fleet):
    """The Welcome item is first under Overview, never dimmed, opens
    Welcome and is marked active; the logo stays a Welcome entry."""
    page.goto(_origin(dashboard_fleet) + "?view=fleet", wait_until="load")
    page.wait_for_selector("#view-slot table.data-table", timeout=15000)
    first = page.evaluate("""() => {
        const items = document.querySelectorAll('#sidebar-nav .sidebar-item');
        return {view: items[0].dataset.view, id: items[0].id,
                text: items[0].textContent.trim(),
                dimmed: items[0].classList.contains('dimmed')};
    }""")
    assert first == {"view": "welcome", "id": "welcome-nav", "text": "⌂ Welcome", "dimmed": False}
    page.click("#welcome-nav")
    page.wait_for_selector(".welcome-workspace", timeout=10000)
    assert page.evaluate("""() => [
        document.getElementById('welcome-nav').classList.contains('active'),
        document.querySelectorAll('.sidebar-item.active').length,
        document.getElementById('brand-home').getAttribute('aria-current'),
        document.getElementById('topbar-title').textContent]""") == [
        True, 1, "page", "Welcome to Gator!"]


def test_unavailable_items_carry_non_colour_cue(page, dashboard_fleet):
    """Without a repository, Repo/Commits/Loop are dimmed with
    aria-disabled and an explanatory title; selecting one clears all three;
    the static Repo label never names the repository."""
    ids = ["repo-tab", "history-tab", "loop-tab"]
    state_js = """ids => ids.map(id => {
        const e = document.getElementById(id);
        return [e.classList.contains('dimmed'), e.getAttribute('aria-disabled'),
                e.getAttribute('title')];
    })"""
    page.goto(_origin(dashboard_fleet), wait_until="load")
    page.wait_for_selector(".welcome-workspace", timeout=15000)
    hint = "Choose a repository in Fleet first"
    assert page.evaluate(state_js, ids) == [[True, "true", hint]] * 3
    page.goto(_origin(dashboard_fleet) + "?repo=alpha", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    assert page.evaluate(state_js, ids) == [[False, None, None]] * 3
    repo = page.evaluate("""() => {
        const e = document.getElementById('repo-tab');
        return {text: e.textContent.trim(), indent: e.style.paddingLeft};
    }""")
    assert repo == {"text": "▸ Repo", "indent": ""}


# ── Selection grammar, contrast, focus and reduced motion (checkpoint 4) ──

def _welcome_beside_alpha(page, fleet):
    """Two workspace contexts: alpha (inactive) and a new repository-less
    Welcome context (active), so every family has a selected and an
    unselected member on one page."""
    page.goto(_origin(fleet) + "?repo=alpha", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    page.evaluate("() => sessionStorage.clear()")
    page.goto(_origin(fleet) + "?repo=alpha", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    page.wait_for_function("() => window.GatorWorkspace.isHydrated()", timeout=10000)
    page.click("#workspace-strip .workspace-new")
    page.wait_for_selector(".welcome-workspace", timeout=10000)
    page.wait_for_selector("#welcome-tab-overview", timeout=10000)


_FAMILY_JS = """() => {
    const cs = e => getComputedStyle(e);
    const one = (sel, part) => {
        const e = document.querySelector(sel);
        const s = cs(e), p = part ? cs(part(e)) : s;
        return {weight: parseInt(s.fontWeight, 10), shadow: p.boxShadow,
                bottomColor: s.borderBottomColor, bottomWidth: s.borderBottomWidth};
    };
    const item = e => e.parentElement;
    return {
        wsSel: one('.workspace-tab[aria-selected="true"]', item),
        wsUn: one('.workspace-tab[aria-selected="false"]', item),
        tabSel: one('.gator-tab[aria-selected="true"]'),
        tabUn: one('.gator-tab[aria-selected="false"]'),
        navSel: one('.sidebar-item.active'),
        navUn: one('.sidebar-item[data-view="fleet"]'),
    };
}"""


def test_selection_families_bar_plus_weight(page, dashboard_fleet):
    """Each family marks selection with weight 600 plus a positioned teal
    bar (workspace: top; in-view: bottom; sidebar: left), and its
    unselected members have weight 400 and no visible bar."""
    _welcome_beside_alpha(page, dashboard_fleet)
    f = page.evaluate(_FAMILY_JS)
    teal = "rgb(25, 174, 184)"
    assert f["wsSel"]["weight"] == 600 and f["wsUn"]["weight"] == 400
    assert f["wsSel"]["shadow"] == teal + " 0px 3px 0px 0px inset"      # top bar
    assert f["wsUn"]["shadow"] == "none"
    assert f["tabSel"]["weight"] == 600 and f["tabUn"]["weight"] == 400
    assert f["tabSel"]["bottomWidth"] == "3px" and f["tabSel"]["bottomColor"] == teal  # bottom rule
    assert f["tabUn"]["bottomColor"] in ("rgba(0, 0, 0, 0)", "transparent")
    assert f["navSel"]["weight"] == 600 and f["navUn"]["weight"] == 400
    assert f["navSel"]["shadow"] == teal + " 4px 0px 0px 0px inset"     # left rail
    assert f["navUn"]["shadow"] == "none"


_CONTRAST_JS = r"""sels => {
    const parse = c => {
        const v = c.match(/rgba?\(([^)]+)\)/)[1].split(',').map(x => parseFloat(x));
        return {r: v[0], g: v[1], b: v[2], a: v.length > 3 ? v[3] : 1};
    };
    const over = (t, b) => ({r: t.r * t.a + b.r * (1 - t.a), g: t.g * t.a + b.g * (1 - t.a),
                             b: t.b * t.a + b.b * (1 - t.a), a: 1});
    const background = el => {
        const chain = [];
        for (let e = el; e; e = e.parentElement) chain.unshift(e);
        let c = {r: 255, g: 255, b: 255, a: 1};
        for (const e of chain) {
            const bg = parse(getComputedStyle(e).backgroundColor);
            if (bg.a > 0) c = over(bg, c);
        }
        return c;
    };
    const lum = c => {
        const ch = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
        return 0.2126 * ch(c.r) + 0.7152 * ch(c.g) + 0.0722 * ch(c.b);
    };
    const out = {};
    for (const s of sels) {
        const el = document.querySelector(s);
        if (!el) { out[s] = null; continue; }
        const bg = background(el);
        const fg = over(parse(getComputedStyle(el).color), bg);
        const [hi, lo] = [lum(fg), lum(bg)].sort((a, b) => b - a);
        out[s] = Math.round(((hi + 0.05) / (lo + 0.05)) * 100) / 100;
    }
    return out;
}"""

_QUIET_TEXT = [
    '.sidebar-item[data-view="fleet"]',          # enabled sidebar item
    '#repo-tab.dimmed',                          # unavailable sidebar item
    '.sidebar-item.active',                      # selected sidebar item
    '.nav-group-label',                          # group label
    '.workspace-tab[aria-selected="true"]',      # selected strip tab
    '.workspace-tab[aria-selected="false"]',     # unselected strip tab
    '#generated-at',                             # strip status
    '#sidebar-context .ctx-meta',                # card metadata
    '.gator-tab[aria-selected="false"]',         # unselected in-view tab
    '#topbar-title',                             # page title
]


def test_shell_text_meets_wcag_aa(page, dashboard_fleet):
    """Every meaningful quiet text in the Paper shell is at least 4.5:1
    against its actual (composited) background, including the dimmed
    sidebar items (never gray-400)."""
    _welcome_beside_alpha(page, dashboard_fleet)
    ratios = page.evaluate(_CONTRAST_JS, _QUIET_TEXT)
    assert all(v is not None for v in ratios.values()), ratios
    low = {s: v for s, v in ratios.items() if v < 4.5}
    assert not low, low


def test_focus_ring_visible_on_shell_controls(page, dashboard_fleet):
    """Keyboard focus draws the 2px teal-dark ring on a workspace tab, a
    sidebar item and an in-view tab."""
    _welcome_beside_alpha(page, dashboard_fleet)
    ring = []
    for sel in ['.workspace-tab[aria-selected="true"]', "#welcome-nav", "#welcome-tab-overview"]:
        page.keyboard.press("Shift")  # keyboard modality, so :focus-visible applies
        page.focus(sel)
        ring.append(page.evaluate("""s => {
            const e = document.querySelector(s), c = getComputedStyle(e);
            return [e.matches(':focus-visible'), c.outlineStyle, c.outlineWidth, c.outlineColor];
        }""", sel))
    assert ring == [[True, "solid", "2px", "rgb(20, 138, 146)"]] * 3, ring


@pytest.mark.parametrize("motion,expect_zero", [("reduce", True), ("no-preference", False)])
def test_reduced_motion_turns_off_shell_transitions(page, dashboard_fleet, motion, expect_zero):
    page.emulate_media(reduced_motion=motion)
    page.goto(_origin(dashboard_fleet) + "?view=fleet", wait_until="load")
    page.wait_for_selector("#view-slot table.data-table", timeout=15000)
    durations = page.evaluate("""() => ['#sidebar', '.sidebar-item', '#refresh-btn'].map(
        s => getComputedStyle(document.querySelector(s)).transitionDuration)""")
    if expect_zero:
        assert all(set(d.replace(" ", "").split(",")) == {"0s"} for d in durations), durations
    else:
        assert all(d != "0s" for d in durations), durations


# ── explicit type roles (Paper final typography, checkpoint 1) ────────────

# Every visible text element (and form control) in the shell and in any
# open dialog: its computed font size and line height.
_TYPE_SNAPSHOT = """() => {
    const roots = [document.getElementById('app-shell'),
                   ...document.querySelectorAll('dialog[open]')];
    const out = [];
    for (const root of roots) {
        for (const el of [root, ...root.querySelectorAll('*')]) {
            if (!el.getClientRects().length) continue;
            const control = ['INPUT', 'SELECT', 'TEXTAREA', 'BUTTON'].includes(el.tagName);
            const text = Array.from(el.childNodes).some(
                n => n.nodeType === 3 && n.textContent.trim());
            if (!control && !text) continue;
            const cs = getComputedStyle(el);
            const cls = Array.from(el.classList).slice(0, 2).join('.');
            out.push({key: el.tagName.toLowerCase() + (el.id ? '#' + el.id : '')
                           + (cls ? '.' + cls : ''),
                      text: (el.textContent || '').trim().slice(0, 40),
                      size: cs.fontSize, leading: cs.lineHeight});
        }
    }
    return out;
}"""

_SENTINEL = """on => {
    for (const el of [document.documentElement, document.body]) {
        el.style.fontSize = on ? '23px' : '';
        el.style.lineHeight = on ? '2.3' : '';
    }
}"""


def _open_loop(page, fleet, feature):
    sole_active_loop_list(page, feature)
    page.goto(_origin(fleet) + "?repo=alpha&view=loop", wait_until="load")
    page.wait_for_selector('.loop-workspace[data-loaded="1"]', state="attached",
                           timeout=15000)
    page.wait_for_selector(".loop-now", timeout=10000)


def _surface_fleet(page, fleet):
    page.goto(_origin(fleet) + "?view=fleet", wait_until="load")
    page.wait_for_selector("#view-slot .fleet-table", timeout=15000)


def _surface_fleet_modal(page, fleet):
    _surface_fleet(page, fleet)
    page.click("#add-repo-btn")
    page.wait_for_selector(".gator-modal #discovered-repos :not(:empty)",
                           state="attached", timeout=10000)
    page.wait_for_timeout(300)


def _surface_repo(page, fleet):
    page.goto(_origin(fleet) + "?repo=alpha", wait_until="load")
    page.wait_for_selector(".repo-markdown", timeout=15000)


def _surface_commits(page, fleet):
    page.goto(_origin(fleet) + "?repo=alpha&view=history", wait_until="load")
    page.wait_for_selector("details.commit-row summary", timeout=15000)
    page.click("details.commit-row summary")


def _surface_updates(page, fleet):
    # The version check reaches PyPI; a fixed answer makes the settled
    # state (both versions and the status text) deterministic offline.
    page.route("**/api/updates/check", lambda route: route.fulfill(
        json={"current_version": "2.30.0", "latest_version": "2.30.0",
              "update_available": False}))
    page.goto(_origin(fleet) + "?view=updates", wait_until="load")
    page.wait_for_function(
        "() => (document.getElementById('upd-status') || {}).textContent === 'Up to date'",
        timeout=15000)


def _surface_settings(page, fleet):
    page.goto(_origin(fleet) + "?repo=alpha&view=settings", wait_until="load")
    page.wait_for_function(
        "() => document.querySelector('#view-slot').textContent.trim().length > 0",
        timeout=15000)
    page.wait_for_timeout(500)


def _surface_docs(page, fleet):
    page.goto(_origin(fleet) + "?view=docs", wait_until="load")
    page.wait_for_selector(".docs-sidebar", timeout=15000)


def _surface_loop_active(page, fleet):
    _open_loop(page, fleet, "widget-refactor")


def _surface_loop_interject(page, fleet):
    _open_loop(page, fleet, "widget-refactor")
    page.click('#loop-controls .loop-ctrl-btn[data-action="interject"]')
    page.wait_for_selector("dialog.loop-dialog[open]", timeout=5000)


def _surface_loop_decision(page, fleet):
    _open_loop(page, fleet, "blocked-feature")
    page.click(".loop-blocked-respond")
    page.wait_for_selector('dialog.loop-dialog[data-kind="decision"][open]',
                           timeout=5000)


def _surface_loop_history(page, fleet):
    _open_loop(page, fleet, "widget-refactor")
    page.click("#loop-tab-history")
    page.wait_for_selector(".loop-sidebar-card", timeout=10000)
    page.click(".loop-sidebar-card")
    page.wait_for_selector(".loop-outcome-header, .loop-badge-outcome", timeout=10000)


_TYPE_SURFACES = {
    "fleet": _surface_fleet,
    "fleet-add-modal": _surface_fleet_modal,
    "repo-markdown": _surface_repo,
    "commits-expanded": _surface_commits,
    "updates": _surface_updates,
    "settings": _surface_settings,
    "docs": _surface_docs,
    "loop-active": _surface_loop_active,
    "loop-interject-dialog": _surface_loop_interject,
    "loop-decision-dialog": _surface_loop_decision,
    "loop-history-terminal": _surface_loop_history,
}


@pytest.mark.parametrize("surface", list(_TYPE_SURFACES))
def test_no_text_inherits_root_type(page, dashboard_fleet, surface):
    """Every Dashboard text role is explicit: no visible text takes its
    size or line height from html/body. The root is set to sentinel values
    (23px / 2.3) without touching the type tokens, so an element that uses a
    token such as --text-base stays put, and only an accidental inheritor
    moves. A new surface needs an explicit role or a compact-leading owner
    (scripts-dashboard-ui.md, Paper tokens)."""
    page.set_viewport_size({"width": 1440, "height": 900})
    _TYPE_SURFACES[surface](page, dashboard_fleet)
    before = page.evaluate(_TYPE_SNAPSHOT)
    assert before, "no visible text measured"
    page.evaluate(_SENTINEL, True)
    after = page.evaluate(_TYPE_SNAPSHOT)
    page.evaluate(_SENTINEL, False)
    assert len(before) == len(after)
    moved = sorted({f"{b['key']} {b['size']}/{b['leading']} -> "
                    f"{a['size']}/{a['leading']} ({b['text']!r})"
                    for b, a in zip(before, after)
                    if (b["size"], b["leading"]) != (a["size"], a["leading"])})
    assert not moved, "text inherits the root type:\n" + "\n".join(moved)


def test_root_reading_baseline(page, dashboard_fleet):
    """The final Paper reading baseline: html and body compute to
    16px / 1.6, and the role tokens keep their sizes (section/action 14,
    navigation 13, metadata 12 and 11)."""
    page.goto(_origin(dashboard_fleet) + "?view=fleet", wait_until="load")
    page.wait_for_selector("#view-slot .fleet-table", timeout=15000)
    facts = page.evaluate("""() => {
        const root = getComputedStyle(document.documentElement);
        const tok = n => root.getPropertyValue(n).trim();
        const css = el => [getComputedStyle(el).fontSize, getComputedStyle(el).lineHeight];
        return {html: css(document.documentElement), body: css(document.body),
                tokens: ['--text-base', '--text-ui', '--text-nav', '--text-sm',
                         '--text-xs'].map(tok)};
    }""")
    assert facts["html"] == ["16px", "25.6px"], facts
    assert facts["body"] == ["16px", "25.6px"], facts
    assert facts["tokens"] == ["16px", "14px", "13px", "12px", "11px"], facts
