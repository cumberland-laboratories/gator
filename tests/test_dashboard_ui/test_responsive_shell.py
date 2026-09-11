"""Plan C Slice 3 Playwright pins — responsive shell + sidebar.

Hits the actual subprocess dashboard spun up by Plan A's
`dashboard_fleet` fixture. Every pin here takes the plain
pytest-playwright `page` fixture (function-scoped, fresh context
per test) plus `dashboard_fleet` (session-scoped) — no
`gator_page_readonly` / `gator_page_mutable` shortcuts because
several pins need to mutate localStorage or set explicit viewport
sizes before navigating. Tests call `page.goto(fleet["url"] +
"?repo=<name>")` themselves.

Live coverage:

- §7.1 Scroll-ownership contract (`.route-repo` class management
  on Repo + Docs, desktop `#app-shell` bounded, no viewport-math
  on `.repo-browser`): pins
  `test_showview_adds_and_removes_route_repo_class`,
  `test_docs_view_also_gets_route_repo_class`,
  `test_desktop_app_shell_bounded_prevents_page_scroll`,
  `test_repo_browser_no_longer_uses_viewport_calc`.
- §7.2 Non-Repo routes preserve default `#view-slot { overflow-y:
  auto }` (partial — Fleet no-.route-repo class; mobile Repo
  overflow visible): pins
  `test_fleet_view_does_not_get_route_repo_class`,
  `test_mobile_repo_route_uses_visible_overflow`.
- §7.3 Mobile 400px iframe floor (R3 F2 named pin — the 250px
  minimum-usable-size contract is a DIFFERENT contract, deferred):
  `test_iframe_sizing_floor_400px_on_mobile_viewports`.
- §7.4 Markdown scroll + search-results class attachment (R1 F1):
  `test_markdown_view_scrolls_vertically_when_long`,
  `test_search_results_container_has_scroll_owner_class`.
- §7.5 Sidebar collapse (SUBSET — the "every re-render path"
  claim from Plan C §7.5 is NOT met by the shipped pins; only
  initial-mount and docs-filter render paths have dedicated
  behavioral pins; initial-load-error and polling-refresh
  re-render paths are DEFERRED and covered only structurally by
  the source-grep pin). Live pins:
  `test_sidebar_collapse_button_present_before_files_fetch_completes`
  (initial-mount, R1 F3 rewrite — hangs the /files fetch to
  isolate the pre-fetch first-paint render),
  `test_click_collapse_shrinks_sidebar_to_32px`,
  `test_resize_then_collapse_actually_collapses_to_32px`,
  `test_collapse_in_docs_mode_preserves_button` (docs-filter path),
  `test_resize_handle_hidden_while_collapsed`,
  `test_sidebar_collapse_state_persists_per_repo`.
- §7.6 Sidebar overflow (80-file expanded tree scrolls):
  `test_expanded_sidebar_scrolls_long_file_tree`.
- Slice 2 canonical-wrapper grep invariant (SOURCE-based; alias
  renames are the behavioral pins' responsibility):
  `test_no_sidebar_innerHTML_writes_outside_renderSidebarShell`.
- Slice 3 R1 regression pins:
  `test_mobile_collapse_expand_button_remains_clickable` (R1 F1
  min-height: 32px reachability at 375×667),
  `test_sidebar_width_does_not_leak_between_repos_on_spa_nav`
  (R1 F2 SPA-nav width leak via `window.gatorNavToRepo`).
- Slice 3 R2/R3 storage-fallback pins:
  `test_sidebar_state_falls_back_to_defaults_when_storage_throws`
  (R2 HIGH + R3 F2 — seeds alpha collapsed pre-throw so both
  defaults are meaningfully asserted),
  `test_sidebar_state_atomic_when_second_read_throws` (R3 HIGH
  atomic-commit — stubs first getItem to succeed with "1" and
  second to throw).

**Deferred coverage** (charter TRIPWIREs name the invariant but
no dedicated live pin exists yet): initial-load-error re-render
path, polling-refresh re-render path, mobile bounded-shell
(`#main-shell` scrolls while `documentElement` does not at
375×667), invalid-persisted-width fallback (parseInt + range
check exists in source but is not exercised), `test_fleet_view_scrolls_at_900_400`,
`test_iframe_layout_at_375_667` (250px minimum-usable-size).
Total shipped pin count: 23.
"""

import re
from pathlib import Path

import pytest


# ── shared helpers ────────────────────────────────────────────────


def _navigate_to_repo(page, fleet, repo="alpha"):
    """Navigate the page to the Repo view for the given fleet repo
    and wait for the sidebar to be populated with at least one file
    item. Returns the fully-loaded page.
    """
    origin = fleet["url"].rstrip("/") + "/"
    page.goto(origin + "?repo=" + repo, wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    return page


def _navigate_to_docs(page, fleet, repo="alpha"):
    """Navigate to the Docs view for the repo — Docs is a Repo view
    with `filter="docs"`. Uses the sidebar 'Docs' nav item.
    """
    origin = fleet["url"].rstrip("/") + "/"
    page.goto(origin + "?repo=" + repo, wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    # Click the Docs sidebar-nav item.
    page.evaluate(
        "() => document.querySelector('.sidebar-item[data-view=\"docs\"]').click()"
    )
    page.wait_for_selector(".repo-file-item", timeout=15000)
    return page


def _click_file_via_repo_view(page, fleet, filepath, *, repo="alpha"):
    """Slice-2-aware production-path helper. Drives the real
    Dashboard shell to `?repo=<name>`, expands ancestor dirs so the
    target file item is clickable, clicks it, and waits for the
    production iframe or markdown pane to render. Returns the page.

    Kept local to this module (rather than imported from
    test_html_preview) so responsive-shell pins can evolve without
    coupling to B2's test surface.
    """
    origin = fleet["url"].rstrip("/") + "/"
    page.goto(origin + "?repo=" + repo, wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    if "/" in filepath:
        parts = filepath.split("/")[:-1]
        for i in range(len(parts)):
            dir_path = "/".join(parts[:i + 1])
            page.evaluate(
                "(selector) => {"
                "  const btn = document.querySelector(selector);"
                "  if (btn) {"
                "    const contents = btn.nextElementSibling;"
                "    if (contents && contents.style.display === 'none') {"
                "      btn.click();"
                "    }"
                "  }"
                "}",
                f'.repo-tree-dir[data-dir="{dir_path}"]',
            )
    sel = f'.repo-file-item[data-path="{filepath}"]'
    page.wait_for_selector(sel, state="attached", timeout=10000)
    page.evaluate(
        "(sel) => document.querySelector(sel).click()", sel)
    return page


# ── §7.1 Scroll-ownership contract ────────────────────────────────


def test_showview_adds_and_removes_route_repo_class(
        page, dashboard_fleet):
    """`.route-repo` is on `#view-slot` for Repo and Docs, absent
    for Fleet and History. Pins the class-management contract in
    `showView` at `dashboard.js:97-108`.
    """
    origin = dashboard_fleet["url"].rstrip("/") + "/"
    page.goto(origin, wait_until="load")
    # Fleet mount (default view): no .route-repo.
    page.wait_for_selector("#view-slot", timeout=10000)
    assert page.evaluate(
        "() => document.getElementById('view-slot').classList"
        ".contains('route-repo')") is False

    # Navigate to Repo — .route-repo appears.
    page.goto(origin + "?repo=alpha", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    assert page.evaluate(
        "() => document.getElementById('view-slot').classList"
        ".contains('route-repo')") is True

    # Click History — .route-repo goes.
    page.evaluate(
        "() => document.querySelector('.sidebar-item[data-view=\"history\"]').click()"
    )
    # History renders whatever it renders; the class contract is the
    # invariant.
    page.wait_for_function(
        "() => !document.getElementById('view-slot').classList"
        ".contains('route-repo')",
        timeout=5000,
    )


def test_docs_view_also_gets_route_repo_class(
        page, dashboard_fleet):
    """Both `"repo"` AND `"docs"` route names must add `.route-repo`
    per the R1 TRIPWIRE. Pins the second half of the contract.
    """
    _navigate_to_docs(page, dashboard_fleet, "alpha")
    assert page.evaluate(
        "() => document.getElementById('view-slot').classList"
        ".contains('route-repo')") is True


def test_desktop_app_shell_bounded_prevents_page_scroll(
        page, dashboard_fleet):
    """At desktop viewport with long markdown loaded, the document
    element MUST NOT scroll — `#app-shell { height: 100vh; overflow:
    hidden }` bounds the shell and the flex chain delegates scroll
    to `.repo-markdown` inside `.repo-content`.
    """
    page.set_viewport_size({"width": 1440, "height": 900})
    _click_file_via_repo_view(
        page, dashboard_fleet, "artifacts/long.md", repo="alpha")
    # Wait for the markdown pane to render the long body.
    page.wait_for_selector(".repo-markdown", timeout=10000)
    doc_scroll = page.evaluate(
        "() => document.documentElement.scrollHeight"
        " - document.documentElement.clientHeight")
    assert doc_scroll == 0, (
        f"Page-level scroll present: doc.scrollHeight - clientHeight = "
        f"{doc_scroll} (expected 0)")


def test_repo_browser_no_longer_uses_viewport_calc(
        page, dashboard_fleet):
    """`.repo-browser` height tracks `#view-slot`'s clientHeight,
    NOT `calc(100vh - 80px)`. Pins the R1 remediation of the
    v2.11.1 80%-zoom regression: no viewport-math sizing.
    """
    page.set_viewport_size({"width": 1440, "height": 900})
    _navigate_to_repo(page, dashboard_fleet, "alpha")
    heights = page.evaluate("""
        () => {
            const browser = document.querySelector('.repo-browser');
            const slot = document.getElementById('view-slot');
            return {
                browser: browser.getBoundingClientRect().height,
                slot: slot.getBoundingClientRect().height,
                viewportMath: window.innerHeight - 80,
            };
        }
    """)
    # Browser height tracks slot, not viewport-math.
    assert abs(heights["browser"] - heights["slot"]) < 2, (
        f".repo-browser height {heights['browser']} does not track "
        f"#view-slot {heights['slot']}")
    # Resize the viewport — a viewport-math rule would keep
    # `browser` at (newHeight - 80); a flex-chain rule tracks slot.
    page.set_viewport_size({"width": 1440, "height": 600})
    heights2 = page.evaluate("""
        () => {
            const browser = document.querySelector('.repo-browser');
            const slot = document.getElementById('view-slot');
            return {
                browser: browser.getBoundingClientRect().height,
                slot: slot.getBoundingClientRect().height,
            };
        }
    """)
    assert abs(heights2["browser"] - heights2["slot"]) < 2, (
        f"After resize: .repo-browser {heights2['browser']} does not "
        f"track #view-slot {heights2['slot']}")


# ── §7.2 Non-Repo routes preserve default ─────────────────────────


def test_fleet_view_does_not_get_route_repo_class(
        page, dashboard_fleet):
    """Fleet view has `#view-slot` with default `overflow-y: auto`
    (no `.route-repo`). Long Fleet lists scroll normally at the slot
    level, not inside a leaf.
    """
    origin = dashboard_fleet["url"].rstrip("/") + "/"
    page.set_viewport_size({"width": 900, "height": 400})
    page.goto(origin, wait_until="load")
    page.wait_for_selector("#view-slot", timeout=10000)
    has_class = page.evaluate(
        "() => document.getElementById('view-slot').classList"
        ".contains('route-repo')")
    assert has_class is False
    overflow_y = page.evaluate(
        "() => getComputedStyle(document.getElementById('view-slot'))"
        ".overflowY")
    assert overflow_y == "auto", (
        f"Expected #view-slot overflow-y: auto on Fleet route; got "
        f"{overflow_y!r}")


def test_mobile_repo_route_uses_visible_overflow(
        page, dashboard_fleet):
    """On mobile viewport, `#view-slot.route-repo` computes
    `overflow: visible` (both axes). Pins the R1 F2 fix: the mobile
    rules live at end-of-file after all `.repo-*` base declarations,
    and use the `overflow: visible` shorthand — not `overflow-y`.
    """
    page.set_viewport_size({"width": 375, "height": 667})
    _navigate_to_repo(page, dashboard_fleet, "alpha")
    overflow = page.evaluate("""
        () => {
            const slot = document.getElementById('view-slot');
            const cs = getComputedStyle(slot);
            return {
                overflowX: cs.overflowX,
                overflowY: cs.overflowY,
            };
        }
    """)
    assert overflow["overflowY"] == "visible", (
        f"Expected mobile #view-slot.route-repo overflow-y: visible; "
        f"got {overflow['overflowY']!r}")
    assert overflow["overflowX"] == "visible", (
        f"Expected mobile #view-slot.route-repo overflow-x: visible; "
        f"got {overflow['overflowX']!r} — CSS overflow-axis "
        "normalization would promote mixed hidden/visible to auto")


# ── §7.3 Mobile 400px iframe floor (R3 F2 named pin) ──────────────


@pytest.mark.parametrize("viewport_h", [667, 500, 400])
def test_iframe_sizing_floor_400px_on_mobile_viewports(
        page, dashboard_fleet, viewport_h):
    """The B1-ratified 400px iframe floor holds on every mobile
    viewport height, including short ones (375×400). Pins the R3 F2
    contract: dedicated automated protection distinct from the
    Plan C §7.3 250px minimum-usable-size pins.

    Rendered-pixel primary + computed-style diagnostic — both
    assertions from B2 R2 F3 preserved across mobile parametrization.
    """
    page.set_viewport_size({"width": 375, "height": viewport_h})
    _click_file_via_repo_view(
        page, dashboard_fleet, "blueprints/plain.html", repo="alpha")
    page.wait_for_selector("iframe.repo-iframe", timeout=10000)
    measurements = page.evaluate("""
        () => {
            const wrapper = document.querySelector('.repo-iframe-wrapper');
            const iframe = document.querySelector('.repo-iframe');
            return {
                wrapperRendered: wrapper.getBoundingClientRect().height,
                wrapperComputed: getComputedStyle(wrapper).minHeight,
                iframeRendered: iframe.getBoundingClientRect().height,
                iframeComputed: getComputedStyle(iframe).minHeight,
            };
        }
    """)
    # Rendered-pixel primary (catches layout-collapse regressions).
    assert measurements["wrapperRendered"] >= 400, (
        f"iframe wrapper rendered height {measurements['wrapperRendered']} "
        f"< 400px at viewport 375×{viewport_h}")
    assert measurements["iframeRendered"] >= 400, (
        f"iframe rendered height {measurements['iframeRendered']} < 400px "
        f"at viewport 375×{viewport_h}")
    # Computed-style diagnostic (catches "someone removed the CSS
    # rule" regressions cleaner than layout-collapse alone).
    assert measurements["wrapperComputed"] == "400px", (
        f"iframe wrapper computed min-height {measurements['wrapperComputed']} "
        f"!= '400px' at viewport 375×{viewport_h}")
    assert measurements["iframeComputed"] == "400px", (
        f"iframe computed min-height {measurements['iframeComputed']} != "
        f"'400px' at viewport 375×{viewport_h}")


# ── §7.4 Markdown + search regression ─────────────────────────────


def test_markdown_view_scrolls_vertically_when_long(
        page, dashboard_fleet):
    """`.repo-markdown` is the scroll owner for long markdown
    content — parent `.repo-content` has `overflow: hidden`.
    """
    page.set_viewport_size({"width": 1440, "height": 900})
    _click_file_via_repo_view(
        page, dashboard_fleet, "artifacts/long.md", repo="alpha")
    page.wait_for_selector(".repo-markdown", timeout=10000)
    measurements = page.evaluate("""
        () => {
            const md = document.querySelector('.repo-markdown');
            const content = document.querySelector('.repo-content');
            return {
                mdScroll: md.scrollHeight,
                mdClient: md.clientHeight,
                contentScroll: content.scrollHeight,
                contentClient: content.clientHeight,
                contentOverflow: getComputedStyle(content).overflowY,
                mdOverflow: getComputedStyle(md).overflowY,
            };
        }
    """)
    assert measurements["mdScroll"] > measurements["mdClient"], (
        f".repo-markdown does not overflow: scrollHeight="
        f"{measurements['mdScroll']} clientHeight={measurements['mdClient']}")
    assert measurements["contentOverflow"] == "hidden", (
        f".repo-content overflow-y should be hidden (parent); got "
        f"{measurements['contentOverflow']!r}")
    assert measurements["mdOverflow"] == "auto", (
        f".repo-markdown overflow-y should be auto (scroll owner); got "
        f"{measurements['mdOverflow']!r}")


def test_search_results_container_has_scroll_owner_class(
        page, dashboard_fleet):
    """The search-results outer container renders with class
    `.repo-search-results` so the scroll-owner CSS rule attaches.
    Pins the R1 F1 remediation.
    """
    _navigate_to_repo(page, dashboard_fleet, "alpha")
    # Fire a cross-doc search that yields many results (every seed
    # `artifacts/many/f*.md` contains the string "entry").
    search = page.locator("#repo-search-input")
    search.fill("entry")
    # Server search is debounced 300ms; wait for the results DOM.
    page.wait_for_selector(".repo-search-results", timeout=10000)
    styles = page.evaluate("""
        () => {
            const res = document.querySelector('.repo-search-results');
            const cs = getComputedStyle(res);
            return {
                overflowY: cs.overflowY,
                flexGrow: cs.flexGrow,
                minHeight: cs.minHeight,
            };
        }
    """)
    assert styles["overflowY"] == "auto", (
        f".repo-search-results overflow-y expected 'auto'; got "
        f"{styles['overflowY']!r}")


# ── §7.5 Sidebar collapse ─────────────────────────────────────────


def test_sidebar_collapse_button_present_before_files_fetch_completes(
        page, dashboard_fleet):
    """R1 F3 (2026-09-11 Codex MEDIUM): pin the pre-fetch first-
    paint contract, not the post-success sidebar render. The
    initial-mount `renderSidebarShell(initialSidebar, ...Loading...)`
    call at `views/repo.js` runs synchronously at container
    `innerHTML` setup — BEFORE `loadFileList`'s fetch resolves.
    Removing that pre-fetch call would leave the previous
    `test_sidebar_collapse_button_present_on_initial_render` pin
    green (it waited for `.repo-file-item`, which only appears
    AFTER fetch success) while violating the first-paint contract.

    This pin intercepts the `/files` request and never fulfills
    it — the fetch hangs indefinitely, so the SECOND
    `renderSidebarShell` call (via `renderSidebarInto` on fetch
    success OR the catch branch on failure) never runs. Any
    collapse button we observe is guaranteed to be from the
    initial-mount render.
    """
    origin = dashboard_fleet["url"].rstrip("/") + "/"
    # Intercept and hang the /files request. Do not fulfill,
    # continue, or abort — Playwright will keep it pending until
    # page close.
    page.route("**/api/repo/alpha/files*", lambda route: None)
    try:
        page.goto(origin + "?repo=alpha", wait_until="load")
        # Button appears from the initial-mount renderSidebarShell.
        page.wait_for_selector(
            ".repo-sidebar-collapse-btn", timeout=10000)
        # Verify we are in the pre-fetch state — the "Loading
        # files..." message is still visible, which would be
        # replaced by either the tree render or an error render
        # once the fetch resolves. Its presence proves the fetch
        # hasn't completed.
        loading_visible = page.evaluate("""
            () => {
                const el = document.querySelector(
                    '.repo-sidebar-inner .muted');
                return el ? el.textContent.includes('Loading files') : false;
            }
        """)
        assert loading_visible, (
            "Sidebar-inner 'Loading files...' text not present; the "
            "/files fetch may have already resolved and re-rendered "
            "the sidebar. The pre-fetch first-paint state was not "
            "captured.")
    finally:
        page.unroute("**/api/repo/alpha/files*")


def test_click_collapse_shrinks_sidebar_to_32px(page, dashboard_fleet):
    """Clicking the collapse button applies `.collapsed`, and the
    CSS class rule shrinks the sidebar to 32px width.
    """
    _navigate_to_repo(page, dashboard_fleet, "alpha")
    # Ensure not collapsed initially (previous tests may have
    # persisted state).
    page.evaluate("""
        () => {
            localStorage.removeItem('gator-sidebar-collapsed:alpha');
        }
    """)
    page.reload()
    page.wait_for_selector(".repo-file-item", timeout=15000)
    sidebar = page.locator(".repo-sidebar")
    initial_width = sidebar.evaluate(
        "el => el.getBoundingClientRect().width")
    assert initial_width > 100, (
        f"Sidebar unexpectedly narrow pre-collapse: {initial_width}")
    page.locator(".repo-sidebar-collapse-btn").click()
    collapsed_width = sidebar.evaluate(
        "el => el.getBoundingClientRect().width")
    assert 30 <= collapsed_width <= 34, (
        f"Expected collapsed sidebar ~32px; got {collapsed_width}")
    has_class = sidebar.evaluate(
        "el => el.classList.contains('collapsed')")
    assert has_class is True


def test_resize_then_collapse_actually_collapses_to_32px(
        page, dashboard_fleet):
    """Regression pin for the CSS-var + class-specificity design:
    even after `initResizeHandle` sets `--repo-sidebar-width` to a
    large value, `.repo-sidebar.collapsed` wins and shrinks to 32px.
    (Pre-Slice-2 design would have needed !important to beat inline
    style.width.)
    """
    _navigate_to_repo(page, dashboard_fleet, "alpha")
    # Clear persisted state to avoid interference.
    page.evaluate("""
        () => {
            localStorage.removeItem('gator-sidebar-collapsed:alpha');
            localStorage.removeItem('gator-sidebar-width:alpha');
        }
    """)
    page.reload()
    page.wait_for_selector(".repo-file-item", timeout=15000)
    # Simulate a resize by setting the CSS variable directly (what
    # initResizeHandle does on drag).
    page.evaluate(
        "() => document.documentElement.style.setProperty("
        "'--repo-sidebar-width', '400px')")
    # Sanity: expanded sidebar is at 400px.
    expanded_width = page.locator(".repo-sidebar").evaluate(
        "el => el.getBoundingClientRect().width")
    assert 395 <= expanded_width <= 405, (
        f"Expected expanded sidebar ~400px after var set; got "
        f"{expanded_width}")
    # Now collapse.
    page.locator(".repo-sidebar-collapse-btn").click()
    collapsed_width = page.locator(".repo-sidebar").evaluate(
        "el => el.getBoundingClientRect().width")
    assert 30 <= collapsed_width <= 34, (
        f".repo-sidebar.collapsed rule failed to beat --repo-sidebar-width; "
        f"got {collapsed_width} (expected ~32px)")


def test_collapse_in_docs_mode_preserves_button(page, dashboard_fleet):
    """Docs filter re-renders the sidebar innerHTML — collapse
    button must survive because the docs render path routes through
    `renderSidebarShell` (Slice 2 F1).
    """
    _navigate_to_docs(page, dashboard_fleet, "alpha")
    btn = page.locator(".repo-sidebar-collapse-btn")
    assert btn.is_visible(), (
        "Collapse button clobbered by Docs render path")
    # And it's clickable.
    btn.click()
    assert page.locator(".repo-sidebar.collapsed").count() == 1


def test_resize_handle_hidden_while_collapsed(page, dashboard_fleet):
    """Adjacent-sibling CSS rule `.repo-sidebar.collapsed +
    #repo-resize-handle { display: none }` hides the sibling resize
    handle while the sidebar is collapsed.
    """
    _navigate_to_repo(page, dashboard_fleet, "alpha")
    page.evaluate(
        "() => localStorage.removeItem('gator-sidebar-collapsed:alpha')")
    page.reload()
    page.wait_for_selector(".repo-file-item", timeout=15000)
    handle = page.locator("#repo-resize-handle")
    assert handle.is_visible(), (
        "Resize handle should be visible when sidebar is expanded")
    page.locator(".repo-sidebar-collapse-btn").click()
    # Give the DOM a moment to reflect the class change.
    page.wait_for_function(
        "() => getComputedStyle(document.getElementById('repo-resize-handle'))"
        ".display === 'none'",
        timeout=3000,
    )


def test_mobile_collapse_expand_button_remains_clickable(
        page, dashboard_fleet):
    """R1 F1 regression pin (2026-09-11 Codex HIGH): on mobile
    viewport, collapsing the sidebar MUST NOT strand the expand
    control. Without `min-height: 32px` on `.repo-sidebar.collapsed`,
    mobile `.repo-browser { display: block }` sizes the sidebar to
    its content height (0 when `.repo-sidebar-inner` is display:none),
    and `overflow: hidden` clips the absolute-positioned collapse
    button — user cannot un-collapse.
    """
    page.set_viewport_size({"width": 375, "height": 667})
    _navigate_to_repo(page, dashboard_fleet, "alpha")
    page.evaluate(
        "() => localStorage.removeItem('gator-sidebar-collapsed:alpha')")
    page.reload()
    page.wait_for_selector(".repo-file-item", timeout=15000)
    # Collapse.
    page.locator(".repo-sidebar-collapse-btn").click()
    # Sidebar height MUST be at least 32px so the button is not
    # clipped by overflow:hidden.
    sidebar_h = page.locator(".repo-sidebar").evaluate(
        "el => el.getBoundingClientRect().height")
    assert sidebar_h >= 32, (
        f"Mobile collapsed sidebar height {sidebar_h} < 32px — the "
        f"collapse button box (top:4px + height:24px = 28px) is clipped "
        f"by overflow:hidden. R1 F1 regression.")
    # And the button center is hittable — clicking it toggles state.
    btn = page.locator(".repo-sidebar-collapse-btn")
    box = btn.bounding_box()
    assert box is not None, "Collapse button has no bounding box"
    hit_element = page.evaluate(
        "(pt) => {"
        "  const el = document.elementFromPoint(pt.x, pt.y);"
        "  return el ? el.className : null;"
        "}",
        {"x": box["x"] + box["width"] / 2,
         "y": box["y"] + box["height"] / 2},
    )
    assert hit_element is not None and "repo-sidebar-collapse-btn" in (hit_element or ""), (
        f"elementFromPoint at button center returned {hit_element!r}; "
        f"expected .repo-sidebar-collapse-btn. Button click target "
        f"is masked by another element.")
    # Actual click un-collapses (round-trip).
    btn.click()
    page.wait_for_function(
        "() => !document.querySelector('.repo-sidebar').classList.contains('collapsed')",
        timeout=3000,
    )


def test_sidebar_width_does_not_leak_between_repos_on_spa_nav(
        page, dashboard_fleet):
    """R1 F2 regression pin (2026-09-11 Codex HIGH): SPA navigation
    from repo A (with a saved width) to repo B (no saved width)
    MUST NOT leak A's width into B. `restoreSidebarState` clears
    `--repo-sidebar-width` on the document root before consulting
    B's storage; without that clear, B renders at A's persisted
    width. The pre-existing persistence pin used `page.goto()` (full
    reload) which incidentally cleared the CSS var — this pin uses
    `window.gatorNavToRepo` (the real SPA entry point) to catch the
    same-page regression.
    """
    origin = dashboard_fleet["url"].rstrip("/") + "/"
    page.goto(origin + "?repo=alpha", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    # Set alpha's saved width to 400px, clear beta's.
    page.evaluate("""
        () => {
            localStorage.setItem('gator-sidebar-width:alpha', '400');
            localStorage.removeItem('gator-sidebar-width:beta');
            localStorage.removeItem('gator-sidebar-collapsed:alpha');
            localStorage.removeItem('gator-sidebar-collapsed:beta');
        }
    """)
    page.reload()
    page.wait_for_selector(".repo-file-item", timeout=15000)
    # Alpha renders at 400px (restored from localStorage).
    alpha_w = page.locator(".repo-sidebar").evaluate(
        "el => el.getBoundingClientRect().width")
    assert 395 <= alpha_w <= 405, (
        f"alpha did not restore to 400px; got {alpha_w}")
    # Same-page navigation to beta via window.gatorNavToRepo (the
    # production SPA entry point).
    page.evaluate("() => window.gatorNavToRepo('beta')")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    beta_w = page.locator(".repo-sidebar").evaluate(
        "el => el.getBoundingClientRect().width")
    # Beta has no saved width → should render at base 220px, NOT
    # inherit alpha's 400px.
    assert 215 <= beta_w <= 225, (
        f"beta rendered at width {beta_w} after SPA nav from alpha; "
        f"expected ~220px (base). Alpha's --repo-sidebar-width leaked "
        f"across the same-page navigation. R1 F2 regression.")


def test_sidebar_state_falls_back_to_defaults_when_storage_throws(
        page, dashboard_fleet):
    """R2 HIGH + R3 F2 regression pin (2026-09-11 Codex): if
    `localStorage.getItem` throws on the FIRST read (e.g.,
    `SecurityError` when storage is unavailable), `restoreSidebarState`
    MUST leave `_sidebarCollapsed = false` AND `--repo-sidebar-width`
    UNSET so the CSS base rule's 220px fallback applies.

    R3 F2 tightening (2026-09-11): the R2 first-cut of this pin
    had alpha EXPANDED with collapsed keys removed pre-throw,
    which meant `_sidebarCollapsed` was already `false` at the
    throw — the collapsed-reset assertion was vacuous. This pin
    now seeds alpha COLLAPSED (with saved width 400) before
    stubbing, so both defaults must be freshly restored on beta
    for the assertions to hold.
    """
    origin = dashboard_fleet["url"].rstrip("/") + "/"
    page.goto(origin + "?repo=alpha", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    # Seed alpha COLLAPSED with a saved width. Both branches of
    # restore state must be reset for beta.
    page.evaluate("""
        () => {
            localStorage.setItem('gator-sidebar-collapsed:alpha', '1');
            localStorage.setItem('gator-sidebar-width:alpha', '400');
            localStorage.removeItem('gator-sidebar-collapsed:beta');
            localStorage.removeItem('gator-sidebar-width:beta');
        }
    """)
    page.reload()
    # Alpha renders with sidebar collapsed → `.repo-file-item` is
    # display:none. Wait for the collapse button instead.
    page.wait_for_selector(".repo-sidebar-collapse-btn", timeout=15000)
    # Precondition: alpha IS collapsed (proves the seed took).
    assert page.locator(".repo-sidebar.collapsed").count() == 1, (
        "Precondition failed: alpha should render collapsed after "
        "seeding collapsed=1 + reload")
    # And the root CSS variable IS set to alpha's saved width.
    root_width = page.evaluate(
        "() => document.documentElement.style"
        ".getPropertyValue('--repo-sidebar-width')")
    assert root_width == "400px", (
        f"Precondition failed: --repo-sidebar-width should be 400px "
        f"after alpha restore; got {root_width!r}")
    # Stub Storage.prototype.getItem to throw a SecurityError-shaped
    # exception for the NEXT restoreSidebarState call.
    page.evaluate("""
        () => {
            const err = new Error('SecurityError: storage disabled');
            err.name = 'SecurityError';
            Storage.prototype.getItem = function () { throw err; };
        }
    """)
    # SPA navigation to beta.
    page.evaluate("() => window.gatorNavToRepo('beta')")
    page.wait_for_selector(".repo-sidebar-collapse-btn", timeout=15000)
    # Both defaults must be restored:
    # - `.repo-sidebar.collapsed` count == 0 (collapsed-reset ran)
    assert page.locator(".repo-sidebar.collapsed").count() == 0, (
        "beta appears collapsed after SPA nav under storage-throw; "
        "alpha's collapsed=1 leaked because `_sidebarCollapsed = false` "
        "was not executed before the getItem throw.")
    # - CSS var absent, sidebar renders at base ~220px
    beta_w = page.locator(".repo-sidebar").evaluate(
        "el => el.getBoundingClientRect().width")
    assert 215 <= beta_w <= 225, (
        f"beta rendered at width {beta_w} after SPA nav under "
        f"storage-throw; expected ~220px (base). alpha's 400px "
        f"leaked because --repo-sidebar-width was not cleared before "
        f"the getItem throw.")


def test_sidebar_state_atomic_when_second_read_throws(
        page, dashboard_fleet):
    """R3 HIGH regression pin (2026-09-11 Codex): `restoreSidebarState`
    MUST commit atomically — either both stored values commit or
    neither does. If the FIRST getItem (collapsed) succeeds but the
    SECOND getItem (width) throws, the intermediate state must NOT
    persist. The R2 shape mutated `_sidebarCollapsed` immediately
    after the first successful read, then read width — a throw on
    the second read left `_sidebarCollapsed` overlaid while
    `--repo-sidebar-width` was still cleared. R3 fix: read both
    into locals, validate, then commit both only after all reads
    succeeded.

    This pin stubs `getItem` to return "1" for the collapsed key
    and throw on the width key, exercising the exact partial-
    overlay path.
    """
    origin = dashboard_fleet["url"].rstrip("/") + "/"
    page.goto(origin + "?repo=alpha", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    # Seed alpha with a saved width so `--repo-sidebar-width` is
    # non-default going into beta's restore.
    page.evaluate("""
        () => {
            localStorage.setItem('gator-sidebar-width:alpha', '400');
            localStorage.removeItem('gator-sidebar-collapsed:alpha');
        }
    """)
    page.reload()
    page.wait_for_selector(".repo-file-item", timeout=15000)
    # Precondition: alpha at 400px, expanded.
    alpha_w = page.locator(".repo-sidebar").evaluate(
        "el => el.getBoundingClientRect().width")
    assert 395 <= alpha_w <= 405, (
        f"Precondition failed: alpha should render at 400px; got "
        f"{alpha_w}")
    # Stub: first getItem returns "1" (collapsed=true), second
    # throws on the width key. Exactly the partial-overlay case.
    page.evaluate("""
        () => {
            const err = new Error('SecurityError: storage disabled');
            err.name = 'SecurityError';
            Storage.prototype.getItem = function (key) {
                if (typeof key === 'string' &&
                    key.startsWith('gator-sidebar-collapsed:')) {
                    return '1';
                }
                throw err;
            };
        }
    """)
    # SPA-navigate to beta. restoreSidebarState will read collapsed
    # successfully as "1", then throw on width.
    page.evaluate("() => window.gatorNavToRepo('beta')")
    page.wait_for_selector(".repo-sidebar-collapse-btn", timeout=15000)
    # Atomic commit: because width read threw, collapsed must NOT
    # have been applied either. beta stays expanded at 220px.
    assert page.locator(".repo-sidebar.collapsed").count() == 0, (
        "beta appears collapsed after SPA nav where the width read "
        "threw. The first-read succeeded and applied collapsed=true "
        "before the second read failed — partial overlay violating "
        "the atomic-commit contract. R3 HIGH regression.")
    beta_w = page.locator(".repo-sidebar").evaluate(
        "el => el.getBoundingClientRect().width")
    assert 215 <= beta_w <= 225, (
        f"beta width {beta_w} after partial-overlay throw; expected "
        f"~220px (base). alpha's 400px should have been cleared by "
        f"the pre-try removeProperty.")


def test_sidebar_collapse_state_persists_per_repo(page, dashboard_fleet):
    """localStorage keys are repo-namespaced. Collapse `alpha`,
    reload `alpha` → still collapsed. Navigate to `beta` fresh →
    NOT collapsed (unless `beta` has its own state).
    """
    origin = dashboard_fleet["url"].rstrip("/") + "/"
    # Start clean.
    page.goto(origin + "?repo=alpha", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    page.evaluate("""
        () => {
            localStorage.removeItem('gator-sidebar-collapsed:alpha');
            localStorage.removeItem('gator-sidebar-collapsed:beta');
        }
    """)
    page.reload()
    page.wait_for_selector(".repo-file-item", timeout=15000)
    # Collapse alpha.
    page.locator(".repo-sidebar-collapse-btn").click()
    assert page.locator(".repo-sidebar.collapsed").count() == 1
    # Reload alpha: still collapsed. After reload with persisted
    # collapse state, `.repo-file-item` descendants are hidden by
    # `.collapsed .repo-sidebar-inner { display: none }`; wait for
    # the collapse button which stays visible when collapsed.
    page.reload()
    page.wait_for_selector(".repo-sidebar-collapse-btn", timeout=15000)
    assert page.locator(".repo-sidebar.collapsed").count() == 1, (
        "alpha collapse state did not persist across reload")
    # Navigate to beta: not collapsed (no state for beta). `beta`'s
    # sidebar file items ARE visible so the standard wait works.
    page.goto(origin + "?repo=beta", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    assert page.locator(".repo-sidebar.collapsed").count() == 0, (
        "beta appears collapsed but should have its own (empty) state")


# ── §7.6 Sidebar overflow ─────────────────────────────────────────


def test_expanded_sidebar_scrolls_long_file_tree(page, dashboard_fleet):
    """80-file fixture: expanding both nested dirs
    (`.gator/artifacts/` and `.gator/artifacts/many/`) surfaces 80
    file rows; the sidebar's own scroll area handles the overflow.
    """
    _navigate_to_repo(page, dashboard_fleet, "alpha")
    # Ensure not collapsed.
    page.evaluate(
        "() => localStorage.removeItem('gator-sidebar-collapsed:alpha')")
    page.reload()
    page.wait_for_selector(".repo-file-item", timeout=15000)
    # Expand `artifacts/`.
    page.evaluate(
        "() => document.querySelector"
        "('.repo-tree-dir[data-dir=\"artifacts\"]').click()")
    # Then `artifacts/many/`.
    page.evaluate(
        "() => document.querySelector"
        "('.repo-tree-dir[data-dir=\"artifacts/many\"]').click()")
    # All 80 f-files should be attached now (may still overflow
    # visible area).
    page.wait_for_selector(
        '.repo-file-item[data-path="artifacts/many/f79.md"]',
        state="attached", timeout=5000)
    measurements = page.evaluate("""
        () => {
            const s = document.querySelector('.repo-sidebar');
            return {
                scrollHeight: s.scrollHeight,
                clientHeight: s.clientHeight,
                overflowY: getComputedStyle(s).overflowY,
            };
        }
    """)
    assert measurements["scrollHeight"] > measurements["clientHeight"], (
        f".repo-sidebar did not overflow: scrollHeight="
        f"{measurements['scrollHeight']} clientHeight="
        f"{measurements['clientHeight']}")
    assert measurements["overflowY"] == "auto", (
        f".repo-sidebar overflow-y expected 'auto'; got "
        f"{measurements['overflowY']!r}")


# ── Slice 2 canonical-wrapper grep invariant ──────────────────────


def test_no_sidebar_innerHTML_writes_outside_renderSidebarShell():
    """The Slice 2 canonical-wrapper TRIPWIRE asserts that every
    write to the sidebar's innerHTML in `views/repo.js` routes
    through `renderSidebarShell`. This pin implements a NAME-BASED
    source-grep check: it detects direct `innerHTML=` writes where
    the receiver is named `sidebar` or `sidebarEl` (the two names
    used by the shipped sites) and asserts the sole surviving hit
    lives inside `renderSidebarShell`'s function body.

    **Coverage limitation (R1 F4, 2026-09-11 Codex MEDIUM)**: this
    pin cannot catch a regression that introduces a DIFFERENTLY-
    NAMED sidebar alias — e.g., `fileList.innerHTML = ...` after
    `const fileList = container.querySelector('#repo-file-list')`.
    The pin would still see one hit (inside `renderSidebarShell`)
    and pass. Alias regressions are covered BEHAVIORALLY by the
    live re-render pins:
    - `test_sidebar_collapse_button_present_before_files_fetch_completes`
      (initial mount path)
    - `test_collapse_in_docs_mode_preserves_button` (Docs render path)
    A future PR that introduces a new sidebar-write alias AND
    bypasses `renderSidebarShell` would remove the collapse button
    from its render path; the corresponding live pin fails
    behaviorally even though the grep pin passes. Together the
    grep pin + the live pins bracket the contract from both source
    and behavior.
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    js_path = (repo_root / "src" / "gator_command" / "scripts"
               / "dashboard" / "views" / "repo.js")
    assert js_path.is_file(), f"views/repo.js not found at {js_path}"
    src = js_path.read_text(encoding="utf-8")
    # Match `sidebar.innerHTML = ...` or `sidebarEl.innerHTML = ...`
    # — the two names used by every current call site and the
    # wrapper. Alias-rename regressions are the runtime pins'
    # responsibility per the coverage-limitation docstring above.
    hits = re.findall(
        r"\b(?:sidebar|sidebarEl)\.innerHTML\s*=", src)
    # Exactly one hit expected: inside `renderSidebarShell` itself.
    assert len(hits) == 1, (
        f"Expected exactly 1 (sidebar|sidebarEl).innerHTML= write "
        f"(inside renderSidebarShell); found {len(hits)}. Any "
        f"additional write via those specific variable names is a "
        f"canonical-wrapper contract violation. Different-named "
        f"aliases are the runtime pins' responsibility — see the "
        f"docstring above.")
    # Verify the surviving hit is in renderSidebarShell (by function
    # proximity).
    fn_start = src.find("function renderSidebarShell(")
    assert fn_start != -1, "renderSidebarShell function not found"
    # Find the matching close brace via naive bracket-balance.
    depth = 0
    fn_end = fn_start
    for i, ch in enumerate(src[fn_start:], start=fn_start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                fn_end = i
                break
    fn_body = src[fn_start:fn_end]
    inner_hits = re.findall(
        r"\b(?:sidebar|sidebarEl)\.innerHTML\s*=", fn_body)
    assert len(inner_hits) == 1, (
        f"The sole sidebar.innerHTML= write must live inside "
        f"renderSidebarShell; got {len(inner_hits)} hits inside its body")
