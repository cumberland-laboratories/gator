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
                 branch: tr.dataset.sortBranch, policy: tr.dataset.sortPolicy,
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
    the read-only commit policy stay compact. The page never scrolls."""
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
            policy: px(slot.querySelector('td.fleet-policy-cell')),
            selects: Array.from(slot.querySelectorAll('.fleet-table select')).map(s =>
                s.className + ':' + Array.from(s.options).map(o => o.value).join('/')),
            pageScrolled: se.scrollTop !== 0 || se.scrollHeight > window.innerHeight,
        };
    }""")
    assert shape["children"] == ["fleet-header", "section"], shape
    assert shape["headerKids"] == ["add-repo-btn"], shape
    assert shape["tables"] == 1 and shape["cards"] == 0 and shape["prose"] == 0, shape
    assert shape["name"] == shape["base"], shape
    assert max(shape["branch"], shape["version"], shape["policy"]) <= 13, shape
    # The only selects are the machine-local commit-policy dropdowns, and
    # each offers exactly Strict and Warn (the old strict/warn/off selector
    # stays retired: there is no local Off).
    assert all(s == "fleet-policy-select:strict/warn" for s in shape["selects"]), shape
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


def _route_policies(page, overrides=None):
    """Rewrite /api/data so the rows show every posture (#75; machine-local
    policy 2026-10-28). Returns {name: (label, has_select, select_value)}.
    `overrides` ({name: level}, mutable) is applied after the fixture
    settings, so a test can show what the server holds after a write."""
    expected = {}
    overrides = overrides if overrides is not None else {}

    def handle(route):
        resp = route.fetch()
        data = resp.json()
        if overrides:
            data["generated_at"] = "after-write-" + str(len(overrides))
        repos = data.get("repos") or (data.get("fleet") or {}).get("repos", [])
        # The first four rows become gatorized, accessible repositories. The
        # second commits "warn" in config.json but has no local level: the
        # tracked value is not the policy, so it shows Strict.
        settings = [("warn", {"enforcement_level": "strict"}, False, ("Warn", True, "warn")),
                    ("strict", {"enforcement_level": "warn"}, False, ("Strict", True, "strict")),
                    ("warn", {}, True, ("Managed by Enterprise", False, None)),
                    ("strict", {"enforcement_level": "strict"}, False, ("Strict", True, "strict"))]
        for repo, (level, config, enterprise, want) in zip(repos, settings):
            repo.update(gatorized=True, accessible=True, config=config,
                        commit_policy=level, enterprise_managed=enterprise)
            expected[repo["name"]] = want
        not_gatorized, unreadable = repos[4], repos[5]
        not_gatorized.update(gatorized=False, accessible=True, config={})
        unreadable.update(accessible=False, config={})
        unreadable.pop("gatorized", None)
        expected[not_gatorized["name"]] = ("Not gatorized", False, None)
        expected[unreadable["name"]] = ("Unknown", False, None)
        for repo in repos:
            if repo["name"] in overrides:
                repo["commit_policy"] = overrides[repo["name"]]
        route.fulfill(response=resp, json=data)

    page.route("**/api/data", handle)
    return expected


# For a dropdown row, `text` is the selected option's label and `title` the
# dropdown's; other rows report the posture span.
_POLICY_ROWS = """() => Array.from(document.querySelectorAll(
    '.fleet-table tbody tr[data-row-index]')).map(tr => {
        const sel = tr.querySelector('.fleet-policy-select');
        const span = tr.querySelector('.fleet-policy');
        return {
            name: tr.querySelector('.fleet-repo-name').textContent.trim(),
            text: sel ? sel.options[sel.selectedIndex].text : span.textContent.trim(),
            title: sel ? sel.title : (span && span.title),
            select: !!sel, value: sel ? sel.value : null,
            options: sel ? Array.from(sel.options).map(o => [o.value, o.text]) : null,
            label: sel ? sel.getAttribute('aria-label') : null,
        };
    })"""


def _open_policy_fleet(page, dashboard_fleet, overrides=None):
    expected = _route_policies(page, overrides)
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(dashboard_fleet["url"], wait_until="load")
    open_fleet(page)
    _wait_for_fleet_render(page)
    return expected


def _sel(name):
    return f'.fleet-policy-select[data-repo-name="{name}"]'


def _row_error(page, name):
    return page.evaluate(f"() => document.querySelector('{_sel(name)}').closest('td')"
                         ".querySelector('.fleet-policy-error').textContent")


def test_fleet_commit_policy_postures(page, dashboard_fleet):
    """Each row shows its posture from the machine-local level (never the
    tracked config.json); Enterprise wins; an editable row shows a
    Strict/Warn dropdown in the Commit policy cell (no extra column, no
    Off); other rows show text with the meaning in the title; Commit policy
    sorts like any other column."""
    expected = _open_policy_fleet(page, dashboard_fleet)
    rows = {r["name"]: r for r in page.evaluate(_POLICY_ROWS) if r["name"] in expected}
    assert {n: (r["text"], r["select"], r["value"]) for n, r in rows.items()} == expected
    assert page.evaluate("() => document.querySelectorAll('.fleet-table thead th').length") == 6
    assert page.evaluate("() => Array.from(document.querySelectorAll('.fleet-table select'))"
                         ".every(s => s.classList.contains('fleet-policy-select')"
                         " && s.closest('td').classList.contains('fleet-policy-cell'))")
    for r in rows.values():
        assert "Off" not in r["text"] and "Legacy" not in r["text"] and "Default" not in r["text"]
        if r["select"]:
            assert r["options"] == [["strict", "Strict"], ["warn", "Warn"]]
            assert r["label"] == f"Commit policy for {r['name']} on this machine"
        if r["text"] == "Warn":
            assert "On this machine only" in r["title"] and "Gator-Commit-Policy: warn" in r["title"]
        if r["text"] == "Managed by Enterprise":
            assert "Enterprise hook mode" in r["title"]

    inactive = {n for n, want in expected.items() if want[0] in ("Not gatorized", "Unknown")}
    for name in inactive:
        assert "Charter updates block" not in rows[name]["title"] and rows[name]["title"]

    page.click('.fleet-sort[data-sort-key="policy"]')
    _assert_header(page, "policy", "ascending")
    sorted_rows = page.evaluate(_ROWS)
    assert all(r["policy"] == "" for r in sorted_rows if r["name"] in inactive), sorted_rows
    policies = [r["policy"] for r in sorted_rows]
    present = [v for v in policies if v]
    assert policies[:len(present)] == present, policies    # missing last
    assert present == _natural(present), present


def test_fleet_policy_dropdown(page, dashboard_fleet):
    """Choosing Warn asks first (Cancel writes nothing and leaves Strict);
    confirming posts {level: "warn"} to /commit-policy and a failure keeps
    Strict with a row error; choosing Strict posts {level: "strict"} with no
    dialog, and a failure keeps Warn."""
    expected = _open_policy_fleet(page, dashboard_fleet)
    names = list(expected)
    warn_name, strict_name = names[0], names[1]
    posts = []
    reply = {"status": 500, "body": {"error": "disk full"}}

    def handle(route):
        posts.append((route.request.url, route.request.post_data_json))
        route.fulfill(status=reply["status"], json=reply["body"])

    page.route("**/commit-policy", handle)

    page.select_option(_sel(strict_name), "warn")
    page.wait_for_selector(".fleet-warn-dialog", timeout=5000)
    dialog = page.inner_text(".fleet-warn-dialog")
    assert strict_name in dialog and "on this machine" in dialog
    assert "not stored in the repository" in dialog and "Gator-Commit-Policy: warn" in dialog
    assert "Choose Strict to restore" in dialog
    assert page.input_value(_sel(strict_name)) == "strict"
    page.click(".fleet-warn-dialog .modal-cancel-btn")
    assert page.query_selector(".fleet-warn-dialog") is None and posts == []
    assert page.input_value(_sel(strict_name)) == "strict"
    assert page.evaluate("() => document.activeElement.classList.contains('fleet-policy-select')")

    page.select_option(_sel(strict_name), "warn")
    page.click(".fleet-warn-dialog .warn-confirm-btn")
    page.wait_for_function(
        f"() => document.querySelector('{_sel(strict_name)}').closest('td')"
        ".querySelector('.fleet-policy-error').textContent.length > 0", timeout=5000)
    url, body = posts[-1]
    assert url.endswith(f"/api/repo/{strict_name}/commit-policy") and body == {"level": "warn"}
    assert page.input_value(_sel(strict_name)) == "strict" and page.is_enabled(_sel(strict_name))
    assert _row_error(page, strict_name) == "Not changed: disk full"

    reply.update(status=500, body={"error": "nope"})
    page.select_option(_sel(warn_name), "strict")
    page.wait_for_function(f"() => !document.querySelector('{_sel(warn_name)}').disabled",
                           timeout=5000)
    assert page.query_selector(".fleet-warn-dialog") is None
    assert posts[-1][1] == {"level": "strict"}
    assert page.input_value(_sel(warn_name)) == "warn"    # the server still holds Warn
    assert _row_error(page, warn_name) == "Not changed: nope"


def test_fleet_warn_success_rerenders_from_the_server(page, dashboard_fleet):
    """Confirming Warn posts {level: "warn"}; on success Fleet re-renders
    from the server, so the row's dropdown shows Warn."""
    overrides = {}
    expected = _open_policy_fleet(page, dashboard_fleet, overrides)
    name = list(expected)[1]                       # a Strict row
    posts = []

    def accept(route):
        posts.append(route.request.post_data_json)
        overrides[name] = "warn"                   # what the server now holds
        route.fulfill(status=200, json={"status": "ok", "commit_policy": "warn"})

    page.route("**/commit-policy", accept)
    page.route("**/api/refresh", lambda route: route.fulfill(status=200, json={"status": "ok"}))
    page.select_option(_sel(name), "warn")
    page.click(".fleet-warn-dialog .warn-confirm-btn")
    page.wait_for_function(
        f"() => {{ const s = document.querySelector('{_sel(name)}');"
        " return s && s.value === 'warn' && !s.disabled; }", timeout=15000)
    assert posts == [{"level": "warn"}]
    row = {r["name"]: r for r in page.evaluate(_POLICY_ROWS)}[name]
    assert row["text"] == "Warn" and row["value"] == "warn"
    assert _row_error(page, name) == ""


def test_settings_commit_policy_is_read_only(page, dashboard_fleet):
    """#75: Settings shows the two-category policy and each repository's
    posture with its note; there is no control."""
    expected = _route_policies(page)
    page.goto(dashboard_fleet["url"].rstrip("/") + "/?view=settings", wait_until="load")
    page.wait_for_selector(".settings-repo-table", timeout=15000)
    out = page.evaluate("""() => ({
        controls: document.querySelectorAll('#view-slot select, #view-slot input').length,
        categories: Array.from(document.querySelectorAll('.settings-policy-table tbody tr'))
            .map(tr => Array.from(tr.cells).map(td => td.textContent.trim())),
        repos: Object.fromEntries(Array.from(document.querySelectorAll(
            '.settings-repo-table tbody tr')).map(tr => [tr.dataset.repo,
            [tr.querySelector('.settings-policy').textContent.trim(),
             tr.querySelector('.settings-policy-note').textContent.trim()]])),
    })""")
    assert out["controls"] == 0
    assert out["categories"] == [
        ["Charter integrity", "Block", "Code needs its required charter update. When no "
         "charter edit is warranted, only the Architect may approve the exact staged change."],
        ["Dangerous patterns", "Pause",
         "HIGH/CRITICAL findings pause the commit until the Architect's decision is "
         "recorded; a skip without one is recorded as unacknowledged."],
    ]
    for name, want in expected.items():
        assert out["repos"][name][0] == want[0], (name, out["repos"][name])
    notes = {out["repos"][n][0]: out["repos"][n][1] for n in expected}
    assert "On this machine only" in notes["Warn"]
    assert "Enterprise hook mode" in notes["Managed by Enterprise"]
    assert notes["Not gatorized"] == "No Gator pre-commit checks run in this repository."
    assert notes["Unknown"] == "Not accessible: the commit policy cannot be read."
