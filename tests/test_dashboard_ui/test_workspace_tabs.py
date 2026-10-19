"""Workspace tabs and browser-tab identity Playwright pins (#80).

Each test proves a distinct risk:

- the browser-tab title follows the shell's view and repository on every
  path (landing, sidebar navigation, Back), never from content;
- two pages on one Dashboard server keep distinct titles and URLs;
- the URL names the active view, and a reload restores it (including
  the Loop sub-tab, from the kept history entry) with no private cache;
- landing URL forms: the legacy ?repo= link, ?view=, an unknown view
  ignored, and an unregistered repository falling back to Fleet.
"""

import json

import pytest

from ._harness import open_fleet


def _origin(fleet):
    return fleet["url"].rstrip("/") + "/"


def _click_sidebar(page, view):
    page.evaluate(
        "v => document.querySelector(`.sidebar-item[data-view=\"${v}\"]`).click()",
        view)


def _wait_title(page, expected):
    page.wait_for_function("t => document.title === t", arg=expected, timeout=10000)


@pytest.mark.parametrize("target,expected", [
    ("welcome", "Gator · Welcome"),
    ("fleet", "Gator · Fleet"),
    ("repo", "Gator · alpha · Repo"),
    ("docs", "Gator · alpha · Docs"),
    ("loop", "Gator · alpha · Loop"),
])
def test_document_title_follows_view(page, dashboard_fleet, target, expected):
    """The title is set on landing, after sidebar navigation, and again
    on Back. Fleet and Welcome never name the repository, even with one
    active."""
    origin = _origin(dashboard_fleet)
    page.goto(origin, wait_until="load")
    page.wait_for_selector(".welcome-workspace", timeout=15000)
    _wait_title(page, "Gator · Welcome")

    page.goto(origin + "?repo=alpha", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    _wait_title(page, "Gator · alpha · Repo")

    if target == "welcome":
        page.evaluate("() => document.getElementById('brand-home').click()")
    elif target == "fleet":
        open_fleet(page)
    elif target != "repo":
        _click_sidebar(page, target)
    _wait_title(page, expected)

    if target != "repo":
        page.go_back()
        _wait_title(page, "Gator · alpha · Repo")


def test_two_pages_distinct_titles_and_urls(page, dashboard_fleet):
    """Two browser pages on the same Dashboard server keep their own
    selected repository, URL and title."""
    origin = _origin(dashboard_fleet)
    other = page.context.new_page()
    try:
        page.goto(origin + "?repo=alpha", wait_until="load")
        other.goto(origin + "?repo=beta", wait_until="load")
        page.wait_for_selector(".repo-file-item", timeout=15000)
        other.wait_for_selector(".repo-file-item", timeout=15000)
        _click_sidebar(other, "loop")
        _wait_title(page, "Gator · alpha · Repo")
        _wait_title(other, "Gator · beta · Loop")
        assert "repo=alpha" in page.url
        assert "repo=beta" in other.url
        assert page.title() != other.title()
    finally:
        other.close()


def _search(page):
    return page.evaluate("() => location.search")


def test_active_view_in_url_and_reload(page, dashboard_fleet):
    """Navigation writes the active view into the URL; a reload lands on
    the same view and repository, and the kept history entry restores the
    Loop History tab. Nothing is read from storage."""
    page.goto(_origin(dashboard_fleet) + "?repo=alpha", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    _click_sidebar(page, "loop")
    page.wait_for_selector("#loop-panel-create", timeout=15000)
    page.click("#loop-tab-history")
    page.wait_for_function(
        "() => document.getElementById('loop-tab-history')"
        ".getAttribute('aria-selected') === 'true'", timeout=10000)
    assert _search(page) == "?repo=alpha&view=loop"

    page.evaluate("() => sessionStorage.clear()")
    page.reload(wait_until="load")
    page.wait_for_selector("#loop-panel-history", timeout=15000)
    page.wait_for_function(
        "() => document.getElementById('loop-tab-history')"
        ".getAttribute('aria-selected') === 'true'", timeout=10000)
    _wait_title(page, "Gator · alpha · Loop")
    assert _search(page) == "?repo=alpha&view=loop"

    open_fleet(page)
    assert _search(page) == "?repo=alpha&view=fleet"
    page.evaluate("() => document.getElementById('brand-home').click()")
    page.wait_for_selector(".welcome-workspace", timeout=10000)
    assert _search(page) == "?repo=alpha&view=welcome"


@pytest.mark.parametrize("query,selector,title,canonical", [
    ("?repo=alpha", ".repo-file-item", "Gator · alpha · Repo", "?repo=alpha"),
    ("?repo=alpha&view=docs", ".docs-sidebar", "Gator · alpha · Docs",
     "?repo=alpha&view=docs"),
    ("?view=fleet", "#view-slot table.data-table", "Gator · Fleet", "?view=fleet"),
    ("?view=bogus", ".welcome-workspace", "Gator · Welcome", ""),
    ("?repo=ghost", "#view-slot .shell-notice", "Gator · Fleet", "?view=fleet"),
])
def test_landing_url_forms(page, dashboard_fleet, query, selector, title, canonical):
    """Legacy ?repo= links still open Repo; ?view= lands on that view; an
    unknown view is ignored; an unregistered repository lands on Fleet
    with the visible notice, never a failing Repo view. The landing entry
    is rewritten to the canonical URL."""
    page.goto(_origin(dashboard_fleet) + query, wait_until="load")
    page.wait_for_selector(selector, timeout=15000)
    _wait_title(page, title)
    assert _search(page) == canonical
    if query == "?repo=ghost":
        assert page.text_content("#view-slot .shell-notice") == (
            "That repository is no longer registered.")
        assert page.locator(".repo-file-item").count() == 0


# ── workspace model and session cache (checkpoint 3) ─────────────────────

WS_KEY = "gator.dashboard.workspace"
_THROWING_STORAGE = """() => {
    Object.defineProperty(window, 'sessionStorage', {
        configurable: true,
        get() { throw new DOMException('blocked', 'SecurityError'); },
    });
}"""


def _fleet_repos(page, fleet):
    data = page.request.get(_origin(fleet) + "api/data").json()
    return {r["name"]: r for r in (data.get("repos") or [])}


def _seed(page, value):
    """Put `value` (a string) into the workspace cache before page scripts run."""
    page.add_init_script(
        script="(() => { try { sessionStorage.setItem(%s, %s); } catch (e) {} })()"
        % (json.dumps(WS_KEY), json.dumps(value)))


def _land_alpha(page, fleet):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(_origin(fleet) + "?repo=alpha", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    page.wait_for_function("() => window.GatorWorkspace.isHydrated()", timeout=10000)
    return errors


def _ctx(i, repo=None, key=None, view="welcome", sub=None):
    return {"id": i, "repo": repo, "repoKey": key, "view": view, "sub": sub}


def _bad_cache_cases(keys):
    beta = _ctx("b1", "beta", keys["beta"], "docs")
    return {
        "not-json": "{",
        "wrong-version": json.dumps({"v": 2, "activeId": "b1", "contexts": [beta]}),
        "oversize": json.dumps({"v": 1, "activeId": "b1", "contexts": [beta],
                                "pad": "x" * 17000}),
        # Under 16,384 characters but over 16,384 UTF-8 bytes (9,000 "é").
        "oversize-bytes": json.dumps({"v": 1, "activeId": "b1", "contexts": [beta],
                                      "pad": "é" * 9000}, ensure_ascii=False),
        "too-many": json.dumps({"v": 1, "activeId": "w0", "contexts": [
            _ctx("w%d" % i) for i in range(13)]}),
        "invalid-fields": json.dumps({"v": 1, "activeId": "w1", "contexts": [
            _ctx("BAD!", "beta", keys["beta"], "docs"),
            _ctx("b2", "beta", "../escape", "loop"),
            _ctx("b3", None, None, "nope"),
            _ctx("b4", None, keys["beta"], "fleet"),
        ]}),
        "unregistered": json.dumps({"v": 1, "activeId": "g1", "contexts": [
            _ctx("g1", "ghost", None, "repo")]}),
    }


@pytest.mark.parametrize("case", [
    "not-json", "wrong-version", "oversize", "oversize-bytes", "too-many",
    "invalid-fields",
    "unregistered", "storage-throws",
])
def test_workspace_cache_rejects_bad_records(page, dashboard_fleet, case):
    """Corrupt, foreign-version, oversized, over-count, invalid, stale and
    unavailable caches never break the page: exactly the URL's context
    remains, with no page error."""
    page.goto(_origin(dashboard_fleet), wait_until="load")
    keys = {n: r.get("repo_key") for n, r in _fleet_repos(page, dashboard_fleet).items()}
    if case == "storage-throws":
        page.add_init_script(script="(" + _THROWING_STORAGE + ")()")
    else:
        _seed(page, _bad_cache_cases(keys)[case])
    errors = _land_alpha(page, dashboard_fleet)
    ws = page.evaluate("() => window.GatorWorkspace.list()")
    assert len(ws["contexts"]) == 1, ws
    active = ws["contexts"][0]
    assert ws["activeId"] == active["id"]
    assert (active["repo"], active["repoKey"], active["view"]) == (
        "alpha", keys["alpha"], "repo")
    assert errors == []


def test_workspace_cache_keeps_valid_contexts(page, dashboard_fleet):
    """A valid cache keeps its order and contexts; the URL's repository
    reuses its cached context (adopting the registry key) and becomes
    active with the on-screen view."""
    page.goto(_origin(dashboard_fleet), wait_until="load")
    keys = {n: r.get("repo_key") for n, r in _fleet_repos(page, dashboard_fleet).items()}
    sub = {"view": "history", "mode": "create", "loopId": None}
    _seed(page, json.dumps({"v": 1, "activeId": "w1", "contexts": [
        _ctx("b1", "beta", keys["beta"], "loop", sub),
        _ctx("w1", None, None, "fleet"),
        _ctx("a1", "alpha", None, "docs"),
    ]}))
    _land_alpha(page, dashboard_fleet)
    ws = page.evaluate("() => window.GatorWorkspace.list()")
    assert [c["id"] for c in ws["contexts"]] == ["b1", "w1", "a1"]
    assert ws["activeId"] == "a1"
    by_id = {c["id"]: c for c in ws["contexts"]}
    assert (by_id["a1"]["repoKey"], by_id["a1"]["view"]) == (keys["alpha"], "repo")
    assert by_id["b1"]["sub"] == sub
    stored = json.loads(page.evaluate("k => sessionStorage.getItem(k)", WS_KEY))
    assert stored["activeId"] == "a1"


def test_workspace_cache_holds_only_bounded_fields(page, dashboard_fleet):
    """After Loop navigation the stored record holds exactly the bounded
    fields: no token, prompt, path or API response."""
    page.goto(_origin(dashboard_fleet), wait_until="load")
    repos = _fleet_repos(page, dashboard_fleet)
    _land_alpha(page, dashboard_fleet)
    _click_sidebar(page, "loop")
    page.wait_for_selector("#loop-panel-create", timeout=15000)
    page.click("#loop-tab-history")
    page.wait_for_function(
        "k => (sessionStorage.getItem(k) || '').includes('\"history\"')",
        arg=WS_KEY, timeout=10000)
    raw = page.evaluate("k => sessionStorage.getItem(k)", WS_KEY)
    stored = json.loads(raw)
    assert set(stored) == {"v", "activeId", "contexts"}
    for ctx in stored["contexts"]:
        assert set(ctx) == {"id", "repo", "repoKey", "view", "sub"}
        if ctx["sub"] is not None:
            assert set(ctx["sub"]) == {"view", "mode", "loopId"}
    # The first visit to `/` already stored a Welcome context (same tab).
    alpha = [c for c in stored["contexts"] if c["repo"] == "alpha"]
    assert len(alpha) == 1 and alpha[0]["view"] == "loop"
    assert alpha[0]["id"] == stored["activeId"]
    assert alpha[0]["sub"]["view"] == "history"
    assert "glp_" not in raw
    for repo in repos.values():
        if repo.get("path"):
            assert repo["path"] not in raw
            assert repo["path"].replace("\\", "\\\\") not in raw


# ── workspace strip and context switching (checkpoint 4) ─────────────────


def _keys(page, fleet):
    page.goto(_origin(fleet), wait_until="load")
    # Let this landing page finish hydrating before returning: hydration
    # (and the re-render after its first data load) saves the workspace,
    # so a late save could undo a caller's sessionStorage.clear() and leave
    # an extra repository-less context (seen on Windows CI, 2026-10-18).
    page.wait_for_function("() => window.GatorWorkspace && window.GatorWorkspace.isHydrated()",
                           timeout=10000)
    page.wait_for_load_state("networkidle", timeout=15000)
    return {n: r.get("repo_key") for n, r in _fleet_repos(page, fleet).items()}


def _seed_contexts(page, contexts, active_id):
    _seed(page, json.dumps({"v": 1, "activeId": active_id, "contexts": contexts}))


_STRIP_JS = """() => {
    const tabs = Array.from(document.querySelectorAll('#workspace-strip .workspace-tab'));
    return tabs.map(t => {
        const c = t.parentElement.querySelector('.workspace-tab-close');
        return {
            id: t.dataset.ctx,
            label: t.textContent,
            selected: t.getAttribute('aria-selected'),
            tabindex: t.getAttribute('tabindex'),
            role: t.getAttribute('role'),
            controls: t.getAttribute('aria-controls'),
            elId: t.id,
            weight: getComputedStyle(t).fontWeight,
            underline: getComputedStyle(t).borderBottomWidth,
            bar: getComputedStyle(t.parentElement).boxShadow,
            itemActive: t.parentElement.classList.contains('workspace-item-active'),
            closeLabel: c.getAttribute('aria-label'),
            closeTabindex: c.getAttribute('tabindex'),
        };
    });
}"""


def _strip(page):
    return page.evaluate(_STRIP_JS)


def _active_tab(page):
    return [t["id"] for t in _strip(page) if t["selected"] == "true"]


def _click_tab(page, ctx_id):
    page.click('#workspace-strip .workspace-tab[data-ctx="%s"]' % ctx_id)


def _focused(page):
    return page.evaluate("""() => {
        const a = document.activeElement;
        return a ? {cls: a.className, ctx: (a.dataset && a.dataset.ctx) || null} : null;
    }""")


def _sidebar_active(page):
    return page.evaluate(
        "() => document.querySelector('.sidebar-item.active').dataset.view")


def _history_tab_selected(page):
    page.wait_for_function(
        "() => { const t = document.getElementById('loop-tab-history');"
        " return !!t && t.getAttribute('aria-selected') === 'true'; }",
        timeout=15000)


_GEOMETRY_JS = """() => {
    const r = s => document.querySelector(s).getBoundingClientRect();
    const strip = document.getElementById('workspace-strip');
    const tops = Array.from(strip.querySelectorAll('.workspace-tab'))
        .map(t => Math.round(t.getBoundingClientRect().top));
    return {
        strip: r('#workspace-strip'), sidebar: r('#sidebar'),
        main: r('#main-shell'), toggle: r('#sidebar-toggle'),
        tabs: tops.length, rows: new Set(tops).size,
        scrollW: strip.scrollWidth, clientW: strip.clientWidth,
        vw: document.documentElement.clientWidth,
        docScrollY: document.documentElement.scrollHeight - document.documentElement.clientHeight,
        docScrollX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        newDisabled: strip.querySelector('.workspace-new').disabled,
    };
}"""


@pytest.mark.parametrize("viewport", [(1440, 900), (375, 700)])
def test_strip_spans_shell_above_sidebar(page, dashboard_fleet, viewport):
    """The strip spans the full width above the sidebar and the main pane;
    the page never scrolls; the sidebar toggle sits below the strip. With
    12 contexts it stays one row (scrolling horizontally at 375px) and +
    is disabled at the limit."""
    page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
    _keys(page, dashboard_fleet)
    _seed_contexts(page, [_ctx("w%d" % i) for i in range(11)], "w0")
    _land_alpha(page, dashboard_fleet)
    page.wait_for_selector("#workspace-strip .workspace-tab", timeout=10000)
    geo = page.evaluate(_GEOMETRY_JS)
    assert geo["tabs"] == 12
    assert geo["newDisabled"] is True
    assert geo["strip"]["top"] == 0 and geo["strip"]["left"] == 0
    assert geo["strip"]["width"] == geo["vw"]
    assert geo["strip"]["height"] == 46  # Paper strip (36px before)
    assert geo["sidebar"]["top"] >= geo["strip"]["bottom"]
    assert geo["main"]["top"] >= geo["strip"]["bottom"]
    assert geo["toggle"]["top"] >= geo["strip"]["bottom"]
    assert geo["rows"] == 1
    assert geo["docScrollY"] == 0 and geo["docScrollX"] == 0
    if viewport[0] == 375:
        assert geo["scrollW"] > geo["clientW"]


def test_strip_aria_keyboard_and_close_labels(page, dashboard_fleet):
    """Roles, roving tabindex, the tab-panel link, labelled close buttons,
    weight-plus-top-bar selection, and manual activation: arrows move
    focus only; Enter selects."""
    keys = _keys(page, dashboard_fleet)
    _seed_contexts(page, [
        _ctx("a1", "alpha", keys["alpha"], "repo"),
        _ctx("b1", "beta", keys["beta"], "docs"),
        _ctx("w1"),
    ], "a1")
    _land_alpha(page, dashboard_fleet)
    page.wait_for_selector("#workspace-strip .workspace-tab", timeout=10000)
    tabs = _strip(page)
    assert [t["label"] for t in tabs] == ["alpha", "beta", "Gator"]
    # The repository-less tab shows the white Gator mark (loaded, decorative)
    # with "Gator" kept as hidden text; repository tabs show text only.
    marks = page.evaluate("""() => Array.from(
        document.querySelectorAll('#workspace-strip .workspace-tab')).map(t => {
            const img = t.querySelector('img.workspace-tab-logo');
            const text = t.querySelector('.workspace-tab-text');
            return img ? {src: img.getAttribute('src'), alt: img.getAttribute('alt'),
                          loaded: img.complete && img.naturalWidth > 0,
                          height: img.getBoundingClientRect().height,
                          textWidth: text ? text.getBoundingClientRect().width : null,
                          title: t.title} : null;
        })""")
    assert marks[0] is None and marks[1] is None
    assert marks[2]["src"] == "gator-logo.png" and marks[2]["alt"] == ""
    assert marks[2]["loaded"] and marks[2]["height"] == 18
    assert marks[2]["textWidth"] <= 1 and marks[2]["title"] == "No repository"
    assert [t["selected"] for t in tabs] == ["true", "false", "false"]
    assert [t["tabindex"] for t in tabs] == ["0", "-1", "-1"]
    assert all(t["role"] == "tab" and t["controls"] == "app-shell" for t in tabs)
    assert [t["closeLabel"] for t in tabs] == [
        "Close alpha workspace", "Close beta workspace",
        "Close workspace without repository"]
    assert [t["closeTabindex"] for t in tabs] == ["0", "-1", "-1"]
    # Paper: selected = weight 600 + a 3px teal TOP bar on its item (no
    # underline); unselected = 400 with no bar.
    assert tabs[0]["weight"] == "600" and tabs[1]["weight"] == "400"
    assert [t["underline"] for t in tabs] == ["0px", "0px", "0px"]
    assert [t["itemActive"] for t in tabs] == [True, False, False]
    assert tabs[0]["bar"] == "rgb(25, 174, 184) 0px 3px 0px 0px inset"
    assert tabs[1]["bar"] == "none" and tabs[2]["bar"] == "none"
    assert page.evaluate("""() => {
        const s = document.getElementById('app-shell');
        const l = document.querySelector('#workspace-strip [role=tablist]');
        return [s.getAttribute('role'), s.getAttribute('aria-labelledby'),
                l.getAttribute('aria-label'),
                document.querySelector('.workspace-new').getAttribute('aria-label')];
    }""") == ["tabpanel", tabs[0]["elId"], "Open workspaces", "New workspace"]

    before = page.url
    page.focus('#workspace-strip .workspace-tab[data-ctx="a1"]')
    page.keyboard.press("ArrowRight")
    assert _focused(page)["ctx"] == "b1"
    assert _active_tab(page) == ["a1"] and page.url == before  # manual activation
    page.keyboard.press("End")
    assert _focused(page)["ctx"] == "w1"
    page.keyboard.press("ArrowRight")
    assert _focused(page)["ctx"] == "a1"  # wraps
    page.keyboard.press("ArrowLeft")
    assert _focused(page)["ctx"] == "w1"
    page.keyboard.press("Home")
    assert _focused(page)["ctx"] == "a1"
    page.keyboard.press("ArrowRight")
    page.keyboard.press("Enter")
    page.wait_for_selector(".docs-sidebar", timeout=10000)
    _wait_title(page, "Gator · beta · Docs")
    assert _active_tab(page) == ["b1"]
    assert _focused(page)["ctx"] == "b1"


def test_strip_status_outside_tablist(page, dashboard_fleet):
    """Paper: the strip holds #workspace-tabs (renderStrip's container),
    a spacer and #strip-status (timestamp, Refresh). The status region is
    outside the tablist, survives a strip rebuild as the same nodes, and
    arrow keys never reach it."""
    keys = _keys(page, dashboard_fleet)
    _seed_contexts(page, [_ctx("a1", "alpha", keys["alpha"], "repo"), _ctx("w1")], "a1")
    _land_alpha(page, dashboard_fleet)
    page.wait_for_selector("#workspace-strip .workspace-tab", timeout=10000)
    layout = page.evaluate("""() => {
        const strip = document.getElementById('workspace-strip');
        const status = document.getElementById('strip-status');
        window.__stripStatus = status;
        window.__stripRefresh = document.getElementById('refresh-btn');
        return {
            children: Array.from(strip.children).map(c => c.id || c.className),
            inTablist: !!status.closest('[role=tablist]'),
            inTabs: document.getElementById('workspace-tabs').contains(status),
            tablistInTabs: !!document.querySelector('#workspace-tabs > [role=tablist]'),
            refresh: status.contains(window.__stripRefresh),
            time: status.querySelector('#generated-at').textContent,
            label: status.getAttribute('aria-label'),
        };
    }""")
    assert layout["children"] == ["workspace-tabs", "strip-spacer", "strip-status"]
    assert layout["inTablist"] is False and layout["inTabs"] is False
    assert layout["tablistInTabs"] is True and layout["refresh"] is True
    assert layout["time"].startswith("Updated ")
    assert layout["label"] == "Dashboard status"

    # + adds a context, which rebuilds the strip; the status nodes stay.
    page.click("#workspace-strip .workspace-new")
    page.wait_for_selector(".welcome-workspace", timeout=10000)
    tabs = _strip(page)
    assert len(tabs) == 3
    assert page.evaluate("""() => window.__stripStatus.isConnected
        && document.getElementById('strip-status') === window.__stripStatus
        && document.getElementById('refresh-btn') === window.__stripRefresh""")

    # Arrow keys move among the tabs only: End reaches the last tab, and
    # Right from it wraps to the first, never into the status region.
    page.focus('#workspace-strip .workspace-tab[data-ctx="%s"]' % tabs[0]["id"])
    page.keyboard.press("End")
    assert _focused(page)["ctx"] == tabs[-1]["id"]
    page.keyboard.press("ArrowRight")
    assert _focused(page)["ctx"] == tabs[0]["id"]
    assert "workspace-tab" in _focused(page)["cls"].split()


def test_switch_restores_each_context(page, dashboard_fleet):
    """Each context restores its own repository, view, sidebar selection
    and Loop sub-tab; + opens a repository-less context; Back undoes a
    strip selection."""
    _keys(page, dashboard_fleet)
    page.evaluate("() => sessionStorage.clear()")
    _land_alpha(page, dashboard_fleet)
    _click_sidebar(page, "loop")
    page.wait_for_selector("#loop-panel-create", timeout=15000)
    page.click("#loop-tab-history")
    _history_tab_selected(page)

    page.click("#workspace-strip .workspace-new")
    page.wait_for_selector(".welcome-workspace", timeout=10000)
    assert _strip(page)[-1]["label"] == "Gator"
    assert "workspace-tab" in _focused(page)["cls"].split()
    open_fleet(page)
    page.evaluate("() => window.gatorNavToRepo('beta')")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    _click_sidebar(page, "docs")
    page.wait_for_selector(".docs-sidebar", timeout=10000)
    tabs = _strip(page)
    assert [t["label"] for t in tabs] == ["alpha", "beta"]
    alpha_id, beta_id = tabs[0]["id"], tabs[1]["id"]

    _click_tab(page, alpha_id)
    _history_tab_selected(page)
    _wait_title(page, "Gator · alpha · Loop")
    assert _sidebar_active(page) == "loop"
    assert page.evaluate("() => location.search") == "?repo=alpha&view=loop"

    _click_tab(page, beta_id)
    page.wait_for_selector(".docs-sidebar", timeout=10000)
    _wait_title(page, "Gator · beta · Docs")
    assert _sidebar_active(page) == "docs"
    assert _active_tab(page) == [beta_id]

    page.go_back()
    _wait_title(page, "Gator · alpha · Loop")
    _history_tab_selected(page)
    assert _active_tab(page) == [alpha_id]


def test_only_active_loop_context_polls(page, dashboard_fleet):
    """Switching away from a polling Loop context stops its polling;
    switching back resumes exactly one interval."""
    keys = _keys(page, dashboard_fleet)
    _seed_contexts(page, [
        _ctx("a1", "alpha", keys["alpha"], "loop"),
        _ctx("b1", "beta", keys["beta"], "docs"),
    ], "a1")
    page.goto(_origin(dashboard_fleet) + "?repo=alpha&view=loop", wait_until="load")
    page.wait_for_selector(".loop-status-header", timeout=15000)
    page.wait_for_function(
        "() => document.querySelector('.loop-workspace').dataset.polling === '1'",
        timeout=10000)

    statuses = []

    def _on_request(r):
        if "/loops/" in r.url and r.url.split("?")[0].endswith("/status"):
            statuses.append(r.url)

    page.on("request", _on_request)
    _click_tab(page, "b1")
    page.wait_for_selector(".docs-sidebar", timeout=10000)
    statuses.clear()
    page.wait_for_timeout(4000)
    assert statuses == [], "an inactive Loop context must not poll"

    _click_tab(page, "a1")
    page.wait_for_selector(".loop-status-header", timeout=15000)
    page.wait_for_timeout(500)
    statuses.clear()
    page.wait_for_timeout(6500)
    # 3 s interval: two polls (three at a boundary) in 6.5 s; a leaked
    # second interval would double that.
    assert 1 <= len(statuses) <= 3, statuses


def test_close_changes_navigation_only(page, dashboard_fleet):
    """Closing an inactive context changes nothing on screen; closing the
    active one selects its neighbour and focuses it; closing the last opens
    a new repository-less Welcome context. No request mutates anything,
    the registry is unchanged and the active loop keeps its stage."""
    keys = _keys(page, dashboard_fleet)
    origin = _origin(dashboard_fleet)

    def loop_stages():
        data = page.request.get(
            origin + "api/repo-by-key/%s/loops" % keys["alpha"]).json()
        return {l["loop_id"]: l["stage"] for l in data["loops"]}

    stages = loop_stages()
    repo_count = len(_fleet_repos(page, dashboard_fleet))
    _seed_contexts(page, [
        _ctx("a1", "alpha", keys["alpha"], "loop"),
        _ctx("b1", "beta", keys["beta"], "docs"),
        _ctx("w1", None, None, "fleet"),
    ], "b1")
    page.goto(origin + "?repo=beta&view=docs", wait_until="load")
    page.wait_for_selector(".docs-sidebar", timeout=15000)
    page.wait_for_selector("#workspace-strip .workspace-tab", timeout=10000)
    methods = []
    page.on("request", lambda r: methods.append(r.method))

    url = page.url
    page.click('#workspace-strip .workspace-tab-close[data-ctx="w1"]')
    assert [t["id"] for t in _strip(page)] == ["a1", "b1"]
    assert page.url == url and _active_tab(page) == ["b1"]

    page.click('#workspace-strip .workspace-tab-close[data-ctx="b1"]')
    page.wait_for_selector(".loop-workspace", timeout=15000)
    _wait_title(page, "Gator · alpha · Loop")
    assert _active_tab(page) == ["a1"]
    assert _focused(page) == {"cls": "workspace-tab", "ctx": "a1"}

    page.click('#workspace-strip .workspace-tab-close[data-ctx="a1"]')
    page.wait_for_selector(".welcome-workspace", timeout=10000)
    tabs = _strip(page)
    assert len(tabs) == 1 and tabs[0]["label"] == "Gator"
    assert page.evaluate("() => location.search") == ""

    assert set(methods) <= {"GET"}, methods
    assert len(_fleet_repos(page, dashboard_fleet)) == repo_count
    assert loop_stages() == stages


# ── Fleet cross-context opening (checkpoint 5) ───────────────────────────


def _fleet_menu(page, repo, item):
    page.click('.overflow-menu-btn[aria-label="Actions for %s"]' % repo)
    page.click('.overflow-menu.open .%s' % item)


def _labels(page):
    return [t["label"] for t in _strip(page)]


def test_fleet_open_actions(page, dashboard_fleet):
    """Fleet opens a repository in a new workspace context (once: repeating
    selects it), the row link selects an existing context instead of
    duplicating it, and the browser-tab link is a plain same-origin link
    that opens an independent page."""
    page.goto(_origin(dashboard_fleet), wait_until="load")
    page.evaluate("() => sessionStorage.clear()")
    page.reload(wait_until="load")
    page.wait_for_function("() => window.GatorWorkspace.isHydrated()", timeout=10000)
    open_fleet(page)
    assert _labels(page) == ["Gator"]
    blank_id = _strip(page)[0]["id"]

    _fleet_menu(page, "alpha", "menu-open-workspace")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    _wait_title(page, "Gator · alpha · Repo")
    assert _labels(page) == ["Gator", "alpha"]
    alpha_id = _strip(page)[1]["id"]
    assert _active_tab(page) == [alpha_id]
    assert _focused(page) == {"cls": "workspace-tab", "ctx": alpha_id}

    # Repeating from the blank context selects the same alpha context.
    _click_tab(page, blank_id)
    page.wait_for_selector("#view-slot table.data-table", timeout=10000)
    _fleet_menu(page, "alpha", "menu-open-workspace")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    assert _labels(page) == ["Gator", "alpha"] and _active_tab(page) == [alpha_id]

    # The row link from the blank context also selects it, not a duplicate.
    _click_tab(page, blank_id)
    page.wait_for_selector("#view-slot table.data-table", timeout=10000)
    page.click('#view-slot .link-btn:text-is("alpha")')
    page.wait_for_selector(".repo-file-item", timeout=15000)
    assert _labels(page) == ["Gator", "alpha"] and _active_tab(page) == [alpha_id]

    # The row link for a repository with no context opens it in the
    # current context.
    _click_tab(page, blank_id)
    page.wait_for_selector("#view-slot table.data-table", timeout=10000)
    page.click('#view-slot .link-btn:text-is("beta")')
    page.wait_for_selector(".repo-file-item", timeout=15000)
    assert _labels(page) == ["beta", "alpha"] and _active_tab(page) == [blank_id]

    # New browser tab: a native same-origin link to the legacy URL.
    open_fleet(page)
    link = page.locator('.menu-open-browser-tab[href="?repo=alpha"]')
    assert link.get_attribute("target") == "_blank"
    assert link.get_attribute("rel") == "noopener"
    page.click('.overflow-menu-btn[aria-label="Actions for alpha"]')
    with page.context.expect_page() as info:
        page.click('.overflow-menu.open .menu-open-browser-tab')
    other = info.value
    try:
        other.wait_for_load_state("load")
        other.wait_for_selector(".repo-file-item", timeout=15000)
        _wait_title(other, "Gator · alpha · Repo")
        assert "?repo=alpha" in other.url
        assert _labels(other) == ["alpha"]  # its own workspace strip
    finally:
        other.close()
    assert _labels(page) == ["beta", "alpha"]


def test_fleet_open_workspace_at_limit(page, dashboard_fleet):
    """At 12 contexts, opening a repository in a new workspace shows the
    limit notice and changes nothing."""
    _keys(page, dashboard_fleet)
    _seed_contexts(page, [_ctx("w%d" % i, None, None, "fleet") for i in range(12)], "w0")
    page.goto(_origin(dashboard_fleet) + "?view=fleet", wait_until="load")
    page.wait_for_selector("#view-slot table.data-table", timeout=15000)
    page.wait_for_function("() => window.GatorWorkspace.isHydrated()", timeout=10000)
    assert len(_strip(page)) == 12
    url = page.url
    _fleet_menu(page, "alpha", "menu-open-workspace")
    page.wait_for_selector("#view-slot .shell-notice", timeout=5000)
    assert page.text_content("#view-slot .shell-notice") == (
        "Workspace limit reached (12). Close a workspace first.")
    assert len(_strip(page)) == 12 and "alpha" not in _labels(page)
    assert page.url == url
