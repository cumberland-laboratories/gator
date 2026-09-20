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

import pytest


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
