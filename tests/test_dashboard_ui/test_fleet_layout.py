"""Fleet-table column-stability pins (2026-09-12, updated 2026-09-20).

Fleet-column-stability sketch remediation: the previously-empty
`.activity-cell` used to grow by 20px on the idle → busy transition
when `<span class="dot-pulse"></span>` was inserted on Update /
Gatorize click. Because `.data-table` uses browser-default automatic
table-layout, every column width recomputed and preceding columns
shrank — visibly "jumping." The fix is a permanent
`<span class="activity-indicator">` rendered in every activity cell
at initial paint (`renderStandaloneRepos`), with a 20px CSS
reservation (`.activity-indicator { display: inline-block; width:
20px; min-width: 20px }`), and `performLifecycleAction` (via the
overflow menu) retargeted to mutate content INSIDE that reserved slot.

These pins exercise the Update action through the overflow menu
(the shipped `views/fleet.js` interaction path) rather than injecting
the pulse directly, so a future handler regression that goes back to
mutating `.activity-cell` fails.

`fetch` is stubbed to a never-resolving Promise so the busy state
persists — the request is never actually issued against a repo.
"""

import re

import pytest

from ._harness import open_fleet


def _wait_for_fleet_render(page):
    """Wait for the Fleet table's overflow menu to attach — proves
    `renderStandaloneRepos` has run and `bindOverflowMenus` has
    wired the click handler."""
    page.wait_for_selector(".overflow-menu-btn", timeout=15000)


def _measure_header_geometry(page):
    """Capture width + x-coordinate for every Fleet header cell.
    Returns a list of `{name, width, x}` dicts in document order.
    """
    return page.evaluate("""
        () => {
            const headers = document.querySelectorAll(
                '.data-table thead th');
            return Array.from(headers).map(h => {
                const r = h.getBoundingClientRect();
                return {
                    name: (h.textContent || '').trim(),
                    width: r.width,
                    x: r.x,
                };
            });
        }
    """)


@pytest.mark.parametrize("viewport_w", [1440, 800])
def test_fleet_update_click_preserves_column_geometry(
        page, dashboard_fleet, viewport_w):
    """Clicking Fleet Update MUST NOT shift any column width or
    x-coordinate. The permanent `.activity-indicator` reserves 20px
    from initial render; the click handler mutates inside that
    reserved slot rather than the enclosing `.activity-cell`. A
    regression to the pre-fix "mutate the cell" shape would shift
    the first five columns by 20px total at any viewport (measured
    by Codex's Chromium probe at 1440/1200/1000/800px).
    """
    page.set_viewport_size({"width": viewport_w, "height": 900})
    page.goto(dashboard_fleet["url"], wait_until="load")
    open_fleet(page)
    _wait_for_fleet_render(page)

    # Stub fetch so the request never resolves — sidebar stays in the
    # busy state for the duration of the assertion. Install AFTER
    # initial Fleet render so the data load itself is not intercepted.
    page.evaluate("""
        () => {
            window.fetch = function () {
                return new Promise(function () { /* never resolves */ });
            };
        }
    """)

    # Baseline geometry BEFORE the busy transition.
    before = _measure_header_geometry(page)
    assert len(before) == 6, (
        f"Expected 6 Fleet columns; got {len(before)}: {before}")

    # Trigger Update through the overflow menu — the shipped interaction
    # path in `views/fleet.js`. Open the first overflow menu, then click
    # the Update item. Some fleet fixtures may have all-disabled Update
    # items; temporarily enable the first one so we can exercise the
    # click path.
    page.locator(".overflow-menu-btn").first.click()
    page.wait_for_selector(".overflow-menu.open", timeout=3000)
    page.evaluate("""
        () => {
            const b = document.querySelector('.overflow-menu.open .menu-lifecycle');
            if (b) b.removeAttribute('disabled');
        }
    """)
    page.locator(".overflow-menu.open .menu-lifecycle").first.click()

    # Wait for the busy indicator to appear inside the reserved slot.
    page.wait_for_selector(
        ".activity-indicator .dot-pulse", timeout=5000)

    # Geometry AFTER the busy transition.
    after = _measure_header_geometry(page)
    assert len(after) == 6

    # Every column's width AND x-coordinate must be unchanged within
    # 0.5px subpixel tolerance.
    for i, (b, a) in enumerate(zip(before, after)):
        assert abs(b["width"] - a["width"]) < 0.5, (
            f"Column {i} ({b['name']!r}) width shifted at viewport "
            f"{viewport_w}px: {b['width']:.2f} → {a['width']:.2f}. "
            f"Fleet activity-column stability regression — busy-state "
            f"content is not confined to the reserved .activity-indicator "
            f"slot.")
        assert abs(b["x"] - a["x"]) < 0.5, (
            f"Column {i} ({b['name']!r}) x-coordinate shifted at "
            f"viewport {viewport_w}px: {b['x']:.2f} → {a['x']:.2f}. "
            f"Preceding columns are being pushed by the busy-state "
            f"insertion — activity-indicator reservation is not "
            f"holding.")


def test_every_fleet_activity_cell_contains_indicator_at_initial_render(
        page, dashboard_fleet):
    """Structural companion to the geometry pin: every populated
    Fleet row MUST render exactly one `.activity-indicator` inside
    its `.activity-cell` at initial paint. A regression that stops
    emitting the indicator would look correct at rest but re-open
    the column-jump on click — the geometry pin catches that too,
    but this lightweight structural check gives a clearer failure
    signal.
    """
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(dashboard_fleet["url"], wait_until="load")
    open_fleet(page)
    _wait_for_fleet_render(page)

    counts = page.evaluate("""
        () => {
            const cells = document.querySelectorAll('.activity-cell');
            return {
                cells: cells.length,
                indicators: Array.from(cells).map(c =>
                    c.querySelectorAll('.activity-indicator').length),
            };
        }
    """)
    assert counts["cells"] >= 1, (
        "Expected at least one .activity-cell in the Fleet table")
    for i, n in enumerate(counts["indicators"]):
        assert n == 1, (
            f"Fleet row {i}: .activity-cell contains {n} "
            f"`.activity-indicator` children; expected exactly 1 "
            f"(the permanent reservation slot)")


_MENU_PROBE = """i => {
    const btns = document.querySelectorAll('#view-slot .data-table .overflow-menu-btn');
    const btn = btns[i < 0 ? btns.length + i : i];
    btn.scrollIntoView({block: 'nearest'});
    btn.click();
    const menu = btn.nextElementSibling;
    const items = Array.from(menu.querySelectorAll('.menu-item')).map(item => {
        const r = item.getBoundingClientRect();
        const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        return {text: item.textContent.trim(), top: r.top, bottom: r.bottom,
                left: r.left, right: r.right, repo: item.dataset.repoName || null,
                usable: !!hit && (hit === item || item.contains(hit))};
    });
    // The pane that owns scrolling: #view-slot on desktop, #main-shell at
    // <=768px (the shell's narrow rule).
    let pane = btn.parentElement;
    while (pane && !/(auto|scroll)/.test(getComputedStyle(pane).overflowX)) pane = pane.parentElement;
    const slot = (pane || document.documentElement).getBoundingClientRect();
    const se = document.scrollingElement;
    return {up: menu.classList.contains('open-up'), open: menu.classList.contains('open'),
            vh: window.innerHeight, vw: window.innerWidth, items,
            slot: {left: slot.left, right: slot.right},
            rowName: btn.closest('tr').querySelector('.fleet-repo-name').textContent.trim(),
            pageScrolled: se.scrollTop !== 0 || se.scrollLeft !== 0
                          || se.scrollHeight > window.innerHeight};
}"""


def _assert_menu_usable(probe):
    """Every item is inside the viewport and the scrolling pane, and is the
    element under its own centre (so it can be clicked). The page itself
    never scrolls."""
    assert not probe["pageScrolled"], probe
    for item in probe["items"]:
        assert 0 <= item["top"] and item["bottom"] <= probe["vh"], item
        assert 0 <= item["left"] and item["right"] <= probe["vw"], item
        assert probe["slot"]["left"] <= item["left"], item
        assert item["right"] <= probe["slot"]["right"], item
        assert item["usable"], item


@pytest.mark.parametrize("viewport", [(1280, 900), (1280, 420), (375, 700)])
def test_last_row_menu_is_fully_visible(page, dashboard_fleet, viewport):
    """#74: the last row's menu is never clipped by the table or the
    window, including at a 375px phone width, where the table may scroll
    sideways inside #view-slot (the probe scrolls the action column into
    view first). In a tall window a top row still opens downward."""
    page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
    page.goto(dashboard_fleet["url"], wait_until="load")
    open_fleet(page)
    _wait_for_fleet_render(page)
    count = page.locator("#view-slot .data-table .overflow-menu-btn").count()
    assert count >= 3, "the fleet fixture needs several rows"

    last = page.evaluate(_MENU_PROBE, -1)
    assert last["open"] and last["up"], last
    texts = [i["text"] for i in last["items"]]
    assert any("Remove" in t for t in texts), texts
    assert any(("Update" in t) or ("Gatorize" in t) for t in texts), texts
    _assert_menu_usable(last)

    page.keyboard.press("Escape")
    page.evaluate("() => document.getElementById('view-slot').scrollTo(0, 0)")
    first = page.evaluate(_MENU_PROBE, 0)
    assert first["open"], first
    # In a 420px window the first row sits too low for the four-item menu
    # to fit below it (Paper rows are taller), so placeMenu() correctly
    # opens it upward; the downward case is pinned in the taller windows.
    if viewport[1] >= 700:
        assert not first["up"], first
    _assert_menu_usable(first)


def test_sorted_last_row_menu_targets_its_row(page, dashboard_fleet):
    """At 375px, after a sort, the last row's menu is still usable and its
    actions name that row's repository: rows move with their menus."""
    page.set_viewport_size({"width": 375, "height": 700})
    page.goto(dashboard_fleet["url"], wait_until="load")
    open_fleet(page)
    _wait_for_fleet_render(page)
    page.click('.fleet-sort[data-sort-key="name"]')
    page.click('.fleet-sort[data-sort-key="name"]')
    assert page.get_attribute('th[data-sort-key="name"]', "aria-sort") == "descending"
    last = page.evaluate(_MENU_PROBE, -1)
    assert last["open"], last
    _assert_menu_usable(last)
    named = {i["repo"] for i in last["items"] if i["repo"]}
    assert named == {last["rowName"]}, last


# ── Paper inventory and sorting ──────────────────────────────────────────

_ROWS = """() => Array.from(document.querySelectorAll('.fleet-table tbody tr[data-row-index]'))
    .map(tr => ({name: tr.querySelector('.fleet-repo-name').textContent.trim(),
                 branch: tr.dataset.sortBranch, enforcement: tr.dataset.enforcement,
                 menuRepo: tr.querySelector('.menu-lifecycle').dataset.repoName}))"""

_HEADERS = """() => Array.from(document.querySelectorAll('.fleet-table th[data-sort-key]'))
    .map(th => ({key: th.dataset.sortKey, sort: th.getAttribute('aria-sort'),
                 mark: th.querySelector('.fleet-sort-mark').textContent,
                 weight: getComputedStyle(th.querySelector('.fleet-sort')).fontWeight}))"""

_UP, _DOWN = "▲", "▼"


def _natural(values):
    """The view's comparison: case-insensitive and numeric-aware."""
    return sorted(values, key=lambda v: [int(t) if t.isdigit() else t.lower()
                                         for t in re.split(r"(\d+)", v)])


def _assert_header(page, key, direction):
    """Only the sorted header has aria-sort, a mark and weight 600."""
    for h in page.evaluate(_HEADERS):
        if h["key"] == key:
            assert h["sort"] == direction, h
            assert h["mark"] == (_UP if direction == "ascending" else _DOWN), h
            assert h["weight"] == "600", h
        else:
            assert h["sort"] is None and h["mark"] == "", h
            assert h["weight"] != "600", h


@pytest.mark.parametrize("viewport", [(1440, 900), (375, 700)])
def test_fleet_title_only_inventory(page, dashboard_fleet, viewport):
    """Fleet is the title, one Add action and one table: no summary text
    and no cards. The repository name is reading-size; branch, version and
    the enforcement select stay compact. The page never scrolls."""
    page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
    page.goto(dashboard_fleet["url"], wait_until="load")
    open_fleet(page)
    _wait_for_fleet_render(page)
    shape = page.evaluate("""() => {
        const slot = document.getElementById('view-slot');
        const px = el => parseFloat(getComputedStyle(el).fontSize);
        const se = document.scrollingElement;
        return {
            children: Array.from(slot.children).map(c => c.className),
            headerKids: Array.from(slot.querySelector('.fleet-header').children).map(c => c.id),
            tables: slot.querySelectorAll('table').length,
            cards: slot.querySelectorAll('.card-row, .card').length,
            prose: slot.querySelectorAll(':scope > p, .section > p').length,
            base: parseFloat(getComputedStyle(document.documentElement)
                             .getPropertyValue('--text-base')),
            name: px(slot.querySelector('.fleet-repo-name')),
            branch: px(slot.querySelector('td.fleet-branch')),
            version: px(slot.querySelector('td.fleet-version')),
            select: px(slot.querySelector('.enforcement-select')),
            pageScrolled: se.scrollTop !== 0 || se.scrollHeight > window.innerHeight,
        };
    }""")
    assert shape["children"] == ["fleet-header", "section"], shape
    assert shape["headerKids"] == ["add-repo-btn"], shape
    assert shape["tables"] == 1 and shape["cards"] == 0 and shape["prose"] == 0, shape
    assert shape["name"] == shape["base"], shape
    assert max(shape["branch"], shape["version"], shape["select"]) <= 13, shape
    assert not shape["pageScrolled"], shape


def test_fleet_sort_one_column(page, dashboard_fleet):
    """One column at a time: registry order by default; a column sorts
    ascending, then descending; another column clears the first. Enter on
    a focused header sorts and keeps focus; a refresh keeps the order; a
    missing value sorts last; each row keeps its own menu."""
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(dashboard_fleet["url"], wait_until="load")
    open_fleet(page)
    _wait_for_fleet_render(page)
    registry = [r["name"] for r in page.evaluate(_ROWS)]
    assert all(h["sort"] is None and h["mark"] == "" for h in page.evaluate(_HEADERS))

    page.click('.fleet-sort[data-sort-key="name"]')
    assert [r["name"] for r in page.evaluate(_ROWS)] == _natural(registry)
    _assert_header(page, "name", "ascending")
    page.click('.fleet-sort[data-sort-key="name"]')
    assert [r["name"] for r in page.evaluate(_ROWS)] == _natural(registry)[::-1]
    _assert_header(page, "name", "descending")

    for direction in ("ascending", "descending"):
        page.click('.fleet-sort[data-sort-key="branch"]')
        _assert_header(page, "branch", direction)
        branches = [r["branch"] for r in page.evaluate(_ROWS)]
        present = [b for b in branches if b]
        assert present and len(present) < len(branches), branches
        assert branches[:len(present)] == present, branches   # missing last

    page.focus('.fleet-sort[data-sort-key="version"]')
    page.keyboard.press("Enter")
    _assert_header(page, "version", "ascending")
    assert page.evaluate("() => document.activeElement.dataset.sortKey") == "version"

    before = page.evaluate(_ROWS)
    page.evaluate("() => { document.querySelector('.fleet-table').dataset.stale = '1';"
                  " window.gatorRefreshFleet(); }")
    page.wait_for_function("() => document.querySelector('.fleet-table')"
                           " && !document.querySelector('.fleet-table').dataset.stale",
                           timeout=10000)
    assert page.evaluate(_ROWS) == before
    _assert_header(page, "version", "ascending")
    assert all(r["menuRepo"] == r["name"] for r in before)


@pytest.mark.parametrize("case", ["edit_then_sort", "edit_during_sort", "failed_edit"])
def test_fleet_sort_follows_saved_enforcement(page, dashboard_fleet, case):
    """Enforcement sorts by the SAVED level. A successful save (the level
    that request sent) re-sorts an active Enforcement sort at once and
    keeps focus on the select; a failed save never changes the order."""
    ok = case != "failed_edit"
    body = {"status": "ok"} if ok else {"status": "error", "error": "denied"}
    page.route("**/api/repo/*/config", lambda route: route.fulfill(json=body))
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(dashboard_fleet["url"], wait_until="load")
    open_fleet(page)
    _wait_for_fleet_render(page)
    beta = 'select.enforcement-select[data-repo="beta"]'
    beta_row = "tr:has(" + beta + ")"
    assert page.get_attribute(beta_row, "data-enforcement") == "strict"

    if case != "edit_then_sort":
        page.click('.fleet-sort[data-sort-key="enforcement"]')
        assert page.evaluate(_ROWS)[0]["name"] != "beta"
    page.select_option(beta, "off")
    page.wait_for_function(
        "s => document.querySelector('.save-check') || document.querySelector(s).style.outline",
        arg=beta, timeout=5000)
    if case == "edit_then_sort":
        page.click('.fleet-sort[data-sort-key="enforcement"]')

    rows = page.evaluate(_ROWS)
    if ok:
        assert page.get_attribute(beta_row, "data-enforcement") == "off"
        assert rows[0]["name"] == "beta" and rows[0]["enforcement"] == "off", rows[:3]
    else:
        assert page.get_attribute(beta_row, "data-enforcement") == "strict"
        assert rows[0]["name"] != "beta", rows[:3]
    if case == "edit_during_sort":
        assert page.evaluate("() => document.activeElement.dataset.repo") == "beta"
    _assert_header(page, "enforcement", "ascending")
    assert all(r["menuRepo"] == r["name"] for r in rows)
