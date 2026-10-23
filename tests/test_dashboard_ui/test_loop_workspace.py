"""Loop workspace Playwright pins — Modules 3, 5, 6 browser-level verification.

Exercises the Loop view navigation, status/timeline rendering,
terminal polling stop, escaped artifact content, Architect control
workflow, and executive summary extraction via the real subprocess
dashboard spun up by the `dashboard_fleet` fixture.

Coverage:

- Navigation: selecting a repo enables the Loop tab; clicking it
  renders the loop workspace layout.
- Loop list: active loops sort before terminal; cards show feature
  name and stage badge.
- Status panel: round info, stage badge, and role state render from
  API data.
- Timeline: events render with labels and timestamps.
- Artifact inspector: collapsible sections load content on click;
  HTML in artifact content is escaped (not rendered as DOM).
- Terminal polling stop: selecting a terminal-stage loop clears the
  poll interval.
- Teardown: navigating away from the Loop view clears the interval
  and nulls `_gatorRepoTeardown`.
"""

import hashlib
import json
import re
from pathlib import Path

import pytest

from ._harness import open_fleet, sole_active_loop_list


def _repo_key(path):
    resolved = str(Path(path).resolve())
    return hashlib.sha256(resolved.encode()).hexdigest()[:12]


def _navigate_to_loop(page, fleet, repo="alpha"):
    origin = fleet["url"].rstrip("/") + "/"
    page.goto(origin + "?repo=" + repo, wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    page.evaluate(
        "() => document.querySelector('.sidebar-item[data-view=\"loop\"]').click()"
    )
    # The list comes from a separate /loops request after the container
    # appears; the mount sets data-loaded once it has landed (Windows CI
    # races, #70). The list pane itself is hidden on the Primary tab.
    page.wait_for_selector('.loop-workspace[data-loaded="1"]', state="attached", timeout=10000)
    return page


# ── navigation ───────────────────────────────────────────────────────────────


def test_loop_tab_enabled_after_repo_selection(page, dashboard_fleet):
    """Selecting a repo un-dims the Loop sidebar tab."""
    origin = dashboard_fleet["url"].rstrip("/") + "/"
    page.goto(origin, wait_until="load")
    page.wait_for_selector("#view-slot", timeout=10000)
    is_dimmed = page.evaluate(
        "() => document.getElementById('loop-tab').classList.contains('dimmed')")
    assert is_dimmed is True, "Loop tab should be dimmed on Fleet view"
    page.goto(origin + "?repo=alpha", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    is_dimmed = page.evaluate(
        "() => document.getElementById('loop-tab').classList.contains('dimmed')")
    assert is_dimmed is False, "Loop tab should be enabled after repo selection"


def test_commits_tab_is_gated_like_loop(page, dashboard_fleet):
    """Commits (#history-tab) is dimmed and inert until a repository is
    selected, exactly like Loop (2026-10-18)."""
    origin = dashboard_fleet["url"].rstrip("/") + "/"
    page.goto(origin, wait_until="load")
    page.wait_for_selector("#view-slot", timeout=10000)
    dimmed = ("() => ['history-tab', 'loop-tab'].map("
              "id => document.getElementById(id).classList.contains('dimmed'))")
    assert page.evaluate(dimmed) == [True, True]
    title = page.evaluate("() => document.getElementById('topbar-title').textContent")
    # Paper: a dimmed item is also aria-disabled, so Playwright's
    # actionability check refuses an ordinary click; force a real mouse
    # click to prove the shell itself ignores it.
    assert page.get_attribute('.sidebar-item[data-view="history"]', "aria-disabled") == "true"
    page.click('.sidebar-item[data-view="history"]', force=True)
    page.wait_for_timeout(300)
    assert page.evaluate(
        "() => document.getElementById('topbar-title').textContent") == title, \
        "clicking a dimmed Commits item must not change the view"

    page.goto(origin + "?repo=alpha", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    assert page.evaluate(dimmed) == [False, False]
    page.click('.sidebar-item[data-view="history"]')
    page.wait_for_function(
        "() => document.querySelector('.sidebar-item[data-view=\"history\"]')"
        ".classList.contains('active')", timeout=10000)


def test_loop_view_renders_workspace_layout(page, dashboard_fleet):
    """Clicking the Loop tab renders the workspace with list and
    main panel sections."""
    _navigate_to_loop(page, dashboard_fleet)
    assert page.locator(".loop-workspace").count() == 1
    assert page.locator("#loop-sidebar-nav").count() == 1
    assert page.locator("#loop-main-content").count() == 1


# ── loop list ────────────────────────────────────────────────────────────────


def test_loop_list_renders_cards(page, dashboard_fleet):
    """The History list shows terminal-loop cards with feature names."""
    _navigate_to_loop(page, dashboard_fleet)
    cards = page.locator(".loop-card")
    assert cards.count() >= 2, "Expected at least 2 loop cards"
    features = page.evaluate("""
        () => Array.from(document.querySelectorAll('.loop-card-feature'))
            .map(el => el.textContent)
    """)
    # Cards are History only (2026-10-21): the active loop is not a card.
    assert "widget-refactor" not in features
    assert "auth-migration" in features


# ── status panel ─────────────────────────────────────────────────────────────


def test_status_panel_renders_on_loop_select(page, dashboard_fleet):
    """Selecting a loop populates the calm header with a stage badge and
    the one-line round counter."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    has_badge = page.locator(".loop-status-header .loop-badge").count() > 0
    assert has_badge, "Status header should contain a stage badge"
    counter = page.evaluate(
        "() => document.querySelector('.loop-counter-line').textContent")
    assert counter.startswith("Round ") and "/" in counter


def test_status_panel_shows_role_state(page, dashboard_fleet):
    """L1: join state lives in Participant recovery (one row per role),
    not in a header ledger."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    page.wait_for_selector(".loop-recovery-row", state="attached", timeout=10000)
    roles = page.evaluate("""
        () => Array.from(document.querySelectorAll('.loop-recovery-row'))
            .map(el => el.querySelector('.loop-recovery-role').textContent)
    """)
    assert roles == ["Draftor", "Reviewer"]
    assert page.locator(".loop-status-grid").count() == 0


# ── timeline ─────────────────────────────────────────────────────────────────


def test_timeline_renders_events(page, dashboard_fleet):
    """Timeline shows event entries with labels."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-event", timeout=10000)
    event_labels = page.evaluate("""
        () => Array.from(document.querySelectorAll('.loop-event-label'))
            .map(el => el.textContent)
    """)
    assert len(event_labels) >= 1, "Expected at least one event"
    assert "Loop started" in event_labels


# ── artifact inspector ───────────────────────────────────────────────────────


def test_artifact_sections_present(page, dashboard_fleet):
    """Artifact inspector shows expected artifact toggle buttons."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-artifact-toggle", timeout=10000)
    names = page.evaluate("""
        () => Array.from(document.querySelectorAll('.loop-artifact-toggle'))
            .map(el => el.textContent)
    """)
    assert "sketch.md" in names
    assert "plan.current.md" in names


def _select_loop_card(page, feature_name):
    """Select a loop by feature name and wait for the status panel to
    reflect the selection (avoids race with async load).

    A terminal loop is a History card; a loop in the conflict state is a
    conflict-list button. The active loop has no card (2026-10-21): it is
    the Primary tab's content, so it is reached through that tab, and it is
    left alone when it is already shown.

    Clears the status header before clicking so wait_for_function
    distinguishes a fresh render from a stale one left by a prior
    loadSelectedLoop that happened to select the same loop.
    """
    page.evaluate("""
        (name) => {
            var h = document.querySelector('.loop-status-header h3');
            var cards = document.querySelectorAll('.loop-card');
            for (var i = 0; i < cards.length; i++) {
                if (cards[i].querySelector('.loop-card-feature').textContent === name) {
                    if (h) h.textContent = '';
                    cards[i].click(); return;
                }
            }
            var btns = document.querySelectorAll('.loop-conflict-open');
            for (var j = 0; j < btns.length; j++) {
                if (btns[j].textContent === name) { btns[j].click(); return; }
            }
            if (h && h.textContent === name) return;
            if (h) h.textContent = '';
            document.querySelector('#loop-tab-create').click();
        }
    """, feature_name)
    page.wait_for_function(
        "(name) => {"
        "  var h = document.querySelector('.loop-status-header h3');"
        "  return h && h.textContent === name;"
        "}",
        arg=feature_name,
        timeout=10000,
    )


def _open_sole_active(page, dashboard_fleet, feature):
    """Open alpha's Loop view with `feature` as the only active loop (the
    Primary tab lands on it). See `_harness.sole_active_loop_list`."""
    sole_active_loop_list(page, feature)
    _navigate_to_loop(page, dashboard_fleet)
    _wait_header(page, feature)


def _open_decision_dialog(page):
    """L1: the blocked alert's Respond button opens the decision dialog,
    where the full request and its artifact link now live."""
    page.wait_for_selector(".loop-blocked-respond", timeout=10000)
    page.evaluate("() => document.querySelector('.loop-blocked-respond').click()")
    page.wait_for_selector('dialog.loop-dialog[data-kind="decision"][open]', timeout=5000)


def test_artifact_toggle_loads_content(page, dashboard_fleet):
    """Clicking an artifact toggle fetches and displays content."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card", state="attached", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_selector(".loop-artifact-toggle", timeout=10000)
    page.evaluate("""
        () => {
            const toggles = document.querySelectorAll('.loop-artifact-toggle');
            for (const t of toggles) {
                if (t.textContent === 'sketch.md') { t.click(); break; }
            }
        }
    """)
    page.wait_for_selector(".loop-artifact-pre", state="attached", timeout=10000)
    content = page.evaluate("""
        () => {
            const pre = document.querySelector('.loop-artifact-pre');
            return pre ? pre.textContent : null;
        }
    """)
    assert content is not None, "Artifact content should load"
    assert "Widget Refactor" in content


def test_artifact_html_is_escaped(page, dashboard_fleet):
    """HTML in artifact content is text-escaped, not rendered as DOM.
    The XSS loop's sketch.md contains script/img tags that must
    appear as visible text, not execute."""
    _open_sole_active(page, dashboard_fleet, "xss-test")
    page.wait_for_selector(".loop-artifact-toggle", timeout=10000)
    page.evaluate("""
        () => {
            const toggles = document.querySelectorAll('.loop-artifact-toggle');
            for (const t of toggles) {
                if (t.textContent === 'sketch.md') { t.click(); break; }
            }
        }
    """)
    page.wait_for_selector(".loop-artifact-pre", state="attached", timeout=10000)
    pre_text = page.evaluate(
        "() => document.querySelector('.loop-artifact-pre').textContent")
    assert '<script>' in pre_text, (
        "Script tag should appear as text content, not be stripped")
    assert 'alert("xss")' in pre_text
    scripts_in_artifact = page.evaluate("""
        () => document.querySelectorAll(
            '.loop-artifact-content script').length
    """)
    assert scripts_in_artifact == 0, (
        "Script tags should be escaped, not rendered as DOM elements")
    # #45: the Rendered pane is built from DOM nodes only.
    assert page.evaluate("""() => document.querySelectorAll(
        '.loop-artifact-content img, .loop-artifact-content iframe, '
        + '.loop-artifact-content style').length""") == 0


# ── terminal polling stop ────────────────────────────────────────────────────


def test_terminal_loop_stops_polling(page, dashboard_fleet):
    """Selecting a terminal-stage loop causes pollLoop to detect the
    terminal stage and clear the interval, reflected by
    data-polling="0" on the workspace element. After polling stops,
    no further loop API requests are made."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    polling_before = page.evaluate(
        "() => document.querySelector('.loop-workspace').dataset.polling")
    assert polling_before == "1", (
        f"Expected data-polling='1' while active; got {polling_before!r}")
    _select_loop_card(page, "auth-migration")
    page.wait_for_selector(
        '.loop-workspace[data-polling="0"]', timeout=10000)
    request_count = [0]
    def _count(route):
        request_count[0] += 1
        route.fallback()
    page.route("**/api/repo-by-key/*/loops/**", _count)
    page.wait_for_timeout(4000)
    page.unroute("**/api/repo-by-key/*/loops/**")
    assert request_count[0] == 0, (
        f"Expected no poll requests after terminal detection, "
        f"but {request_count[0]} requests observed")


# ── teardown ─────────────────────────────────────────────────────────────────


def test_view_teardown_replaces_loop_dom(page, dashboard_fleet):
    """Navigating away from the Loop view calls teardown and replaces
    the Loop workspace DOM with the Repo view."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    has_teardown = page.evaluate(
        "() => typeof window._gatorRepoTeardown === 'function'")
    assert has_teardown is True, (
        "_gatorRepoTeardown should be set after Loop view init completes")
    assert page.locator(".loop-workspace").count() == 1
    page.evaluate(
        "() => document.querySelector('.sidebar-item[data-view=\"repo\"]').click()"
    )
    page.wait_for_selector(".repo-file-item", timeout=15000)
    assert page.locator(".loop-workspace").count() == 0, (
        "Loop workspace DOM should be removed after navigating to Repo")


# ── empty state ──────────────────────────────────────────────────────────────


def test_loop_view_empty_state_for_repo_without_loops(
        page, dashboard_fleet):
    """Beta repo has no loops — Loop view shows empty message."""
    origin = dashboard_fleet["url"].rstrip("/") + "/"
    page.goto(origin + "?repo=beta", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    page.evaluate(
        "() => document.querySelector('.sidebar-item[data-view=\"loop\"]').click()"
    )
    page.wait_for_selector('.loop-workspace[data-loaded="1"]', state="attached", timeout=10000)
    text = page.evaluate(
        "() => document.getElementById('loop-sidebar-nav').textContent")
    assert "No completed loops" in text, (
        "Empty-state message expected for repo with no loops")


# ── repo key propagation ─────────────────────────────────────────────────────


def test_name_only_navigation_resolves_fresh_key(page, dashboard_fleet):
    """Navigating to alpha via fleet (with key), then beta via URL
    (name-only), must re-resolve activeRepoKey to beta's key —
    not retain alpha's stale key. Loop API requests for beta must
    use beta's repo_key, not alpha's."""
    alpha_path = dashboard_fleet["repos"]["alpha"]["path"]
    beta_path = dashboard_fleet["repos"]["beta"]["path"]
    alpha_key = _repo_key(alpha_path)
    beta_key = _repo_key(beta_path)
    origin = dashboard_fleet["url"].rstrip("/") + "/"
    page.goto(origin, wait_until="load")
    page.wait_for_selector("#view-slot", timeout=10000)
    page.evaluate(
        "([name, key]) => window.gatorNavToRepo(name, key)",
        ["alpha", alpha_key],
    )
    page.wait_for_selector(".repo-file-item", timeout=15000)
    page.goto(origin + "?repo=beta", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    requests_made = []
    def _capture(route):
        requests_made.append(route.request.url)
        route.fallback()
    page.route("**/api/repo-by-key/*/loops*", _capture)
    page.evaluate(
        "() => document.querySelector('.sidebar-item[data-view=\"loop\"]').click()"
    )
    page.wait_for_selector('.loop-workspace[data-loaded="1"]', state="attached", timeout=10000)
    page.unroute("**/api/repo-by-key/*/loops*")
    assert len(requests_made) > 0, "Expected at least one Loop API request"
    for url in requests_made:
        assert beta_key in url, (
            f"Loop API request used wrong key: {url} — expected "
            f"beta key {beta_key}, not alpha key {alpha_key}")
        assert alpha_key not in url, (
            f"Loop API request retained stale alpha key: {url}")


# ── mount resurrection ──────────────────────────────────────────────────────


def test_departed_mount_does_not_resurrect_polling(page, dashboard_fleet):
    """Navigating away while the Loop entry point's initial fetch is
    in flight must not resurrect the timer or _gatorRepoTeardown.
    Hold the loops list response, navigate to Repo, release it, then
    verify no Loop API polling occurs afterward."""
    import threading

    origin = dashboard_fleet["url"].rstrip("/") + "/"
    page.goto(origin + "?repo=alpha", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)

    # Diagnostics for an intermittent CI failure (2026-10-23: 3 requests
    # after the departed mount, on Windows and Ubuntu, never reproduced
    # locally). Every repo-by-key request is logged with its time and the
    # test phase, so a failure shows what was called and when.
    import time
    t0 = time.monotonic()
    phase = ["mount"]
    trace = []
    page.on("request", lambda req: trace.append(
        f"{time.monotonic() - t0:6.2f}s [{phase[0]}] {req.method} "
        f"{req.url.split('/api/repo-by-key/', 1)[-1]}")
        if "/api/repo-by-key/" in req.url else None)

    gate = threading.Event()

    def _hold(route):
        gate.wait(timeout=10)
        route.fulfill(
            status=200,
            content_type="application/json",
            body='{"loops":[]}',
        )

    page.route("**/api/repo-by-key/*/loops", _hold)

    page.evaluate(
        "() => document.querySelector("
        "'.sidebar-item[data-view=\"loop\"]').click()"
    )
    # The Loop view has mounted. Do not wait for data-loaded here: the held
    # /loops response can only land after the hold, which races the wait.
    page.wait_for_selector("#loop-sidebar-nav", state="attached", timeout=10000)
    phase[0] = "left-loop"

    page.evaluate(
        "() => document.querySelector("
        "'.sidebar-item[data-view=\"repo\"]').click()"
    )
    page.wait_for_selector(".repo-file-item", timeout=15000)

    phase[0] = "gate-released"
    gate.set()
    page.wait_for_timeout(1500)

    page.unroute("**/api/repo-by-key/*/loops")
    phase[0] = "counting"

    assert page.locator(".loop-workspace").count() == 0, (
        "Loop workspace should not exist after navigating away")

    poll_count = [0]

    def _count(route):
        poll_count[0] += 1
        route.fallback()

    page.route("**/api/repo-by-key/*/loops**", _count)
    page.wait_for_timeout(4000)
    page.unroute("**/api/repo-by-key/*/loops**")
    state = page.evaluate("""() => ({
        view: document.getElementById('topbar-title').textContent,
        loopWorkspace: document.querySelectorAll('.loop-workspace').length,
        teardown: typeof window._gatorRepoTeardown})""")
    assert poll_count[0] == 0, (
        f"Expected zero poll requests after departed mount, "
        f"but {poll_count[0]} observed. Page state: {state}. "
        f"Request trace:\n  " + "\n  ".join(trace))


# ── duplicate-name fleet identity ───────────────────────────────────────────


def test_duplicate_name_fleet_row_uses_clicked_key(page, dashboard_fleet):
    """Two fleet rows with the same display name but different keys —
    clicking the second row must propagate its key to Loop requests,
    not the first-match key from name lookup."""
    import json as _json

    alpha_path = dashboard_fleet["repos"]["alpha"]["path"]
    beta_path = dashboard_fleet["repos"]["beta"]["path"]
    alpha_key = _repo_key(alpha_path)
    beta_key = _repo_key(beta_path)
    origin = dashboard_fleet["url"].rstrip("/") + "/"

    def _inject(route):
        resp = route.fetch()
        body = _json.loads(resp.text())
        for r in body.get("repos", []):
            if r.get("name") == "beta":
                r["name"] = "alpha"
        route.fulfill(
            status=resp.status,
            headers=resp.headers,
            body=_json.dumps(body),
            content_type="application/json",
        )

    page.route("**/api/data", _inject)

    page.goto(origin, wait_until="load")
    open_fleet(page)
    page.wait_for_selector(".link-btn", timeout=10000)

    page.evaluate("""
        (key) => {
            var btns = document.querySelectorAll('.link-btn');
            for (var i = 0; i < btns.length; i++) {
                var attr = btns[i].getAttribute('onclick') || '';
                if (attr.indexOf(key) !== -1) {
                    btns[i].click();
                    break;
                }
            }
        }
    """, beta_key)
    page.wait_for_selector(".repo-file-item", timeout=15000)

    requests_made = []

    def _capture(route):
        requests_made.append(route.request.url)
        route.fallback()

    page.route("**/api/repo-by-key/*/loops*", _capture)

    page.evaluate(
        "() => document.querySelector("
        "'.sidebar-item[data-view=\"loop\"]').click()"
    )
    page.wait_for_selector('.loop-workspace[data-loaded="1"]', state="attached", timeout=10000)
    page.unroute("**/api/repo-by-key/*/loops*")

    assert len(requests_made) > 0, "Expected at least one Loop API request"
    for url in requests_made:
        assert beta_key in url, (
            f"Loop request used wrong key: {url} — expected "
            f"beta key {beta_key}")
        assert alpha_key not in url, (
            f"Loop request used first-match alpha key instead "
            f"of clicked row's key: {url}")


# ── architect controls ─────────────────────────────────────────────────────


def test_active_loop_shows_controls(page, dashboard_fleet):
    """Active loop renders Pause, Interject, and End buttons."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_selector(".loop-ctrl-btn", timeout=10000)
    buttons = page.evaluate("""
        () => Array.from(document.querySelectorAll('.loop-ctrl-btn'))
            .map(el => el.dataset.action)
    """)
    assert "pause" in buttons
    assert "interject" in buttons
    assert "end" in buttons
    assert "unblock" not in buttons


def test_terminal_loop_shows_no_controls(page, dashboard_fleet):
    """Terminal loop renders no control buttons."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card", state="attached", timeout=10000)
    _select_loop_card(page, "auth-migration")
    page.wait_for_timeout(1000)
    count = page.locator(".loop-ctrl-btn").count()
    assert count == 0, (
        f"Terminal loop should show no controls, but found {count}")


def test_control_error_displayed_on_failure(page, dashboard_fleet):
    """Non-2xx control response renders a visible error message
    and preserves the input area for retry."""
    import json as _json

    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_selector(".loop-ctrl-btn", timeout=10000)

    def _reject_pause(route):
        route.fulfill(
            status=409,
            content_type="application/json",
            body=_json.dumps({"error": "loop is terminal"}),
        )

    page.route("**/loops/*/pause", _reject_pause)

    page.evaluate("""
        () => document.querySelector('.loop-ctrl-pause').click()
    """)
    page.wait_for_selector(".loop-ctrl-input-area", timeout=5000)
    page.evaluate("""
        () => document.querySelector('.loop-ctrl-confirm').click()
    """)
    page.wait_for_selector(".loop-ctrl-error", timeout=5000)
    error_text = page.evaluate(
        "() => document.querySelector('.loop-ctrl-error').textContent")
    assert "terminal" in error_text.lower()

    input_visible = page.evaluate("""
        () => document.querySelector('.loop-ctrl-input-area')
            .style.display !== 'none'
    """)
    assert input_visible, "Input area should remain visible after error"
    page.unroute("**/loops/*/pause")


def test_pause_then_shows_unblock_controls(page, dashboard_fleet):
    """After a successful pause, the status refreshes and shows
    Unblock and End controls instead of Pause/Interject."""
    import json as _json

    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_selector(".loop-ctrl-btn", timeout=10000)

    pause_done = [False]

    def _accept_pause(route):
        pause_done[0] = True
        route.fulfill(
            status=200,
            content_type="application/json",
            body=_json.dumps({"ok": True}),
        )

    page.route("**/loops/*/pause", _accept_pause)

    def _status_paused(route):
        if not pause_done[0]:
            route.fallback()
            return
        route.fulfill(
            status=200,
            content_type="application/json",
            body=_json.dumps({
                "loop_id": "active-loop-2026-09-22T10-00-00Z",
                "feature": "widget-refactor",
                "status": {
                    "stage": "paused_by_architect",
                    "next_role": "draftor",
                    "round": 1, "max_rounds": 3,
                    "blocked": True,
                    "resume_stage": "plan_drafting",
                    "resume_next_role": "draftor",
                },
                "roles": {
                    "draftor": {"role": "draftor", "joined": True},
                    "reviewer": {"role": "reviewer", "joined": True},
                },
            }),
        )

    page.route("**/loops/*/status", _status_paused)

    page.evaluate("""
        () => document.querySelector('.loop-ctrl-pause').click()
    """)
    page.wait_for_selector(".loop-ctrl-input-area", timeout=5000)
    page.evaluate("""
        () => document.querySelector('.loop-ctrl-confirm').click()
    """)

    page.wait_for_selector(".loop-ctrl-unblock", timeout=10000)
    buttons = page.evaluate("""
        () => Array.from(document.querySelectorAll('.loop-ctrl-btn'))
            .map(el => el.dataset.action)
    """)
    assert "unblock" in buttons
    assert "end" in buttons
    assert "pause" not in buttons

    page.unroute("**/loops/*/pause")
    page.unroute("**/loops/*/status")


def _route_paused_status(page, stage, pending_decision, turn_timeout=480,
                         pause_reason=None, extra_decisions=()):
    """Serve a paused/blocked status for the selected loop (#40 controls)."""
    import json as _json
    decisions = list(extra_decisions)
    if pending_decision:
        decisions.append({
            "id": "decision-1",
            "request": {"reason": "Need scope decision", "artifact_path": None,
                        "round": 1, "role": "draftor",
                        "ts": "2026-09-22T10:01:00+00:00"},
            "response": None,
        })
    body = _json.dumps({
        "loop_id": "active-loop-2026-09-22T10-00-00Z",
        "feature": "widget-refactor",
        "status": {
            "stage": stage,
            "next_role": None,
            "round": 1, "max_rounds": 3,
            "blocked": True,
            "turn_timeout_seconds": turn_timeout,
            "resume_stage": "plan_drafting",
            "resume_next_role": "draftor",
            "suspended_at": "2026-09-22T10:01:00+00:00",
            "pause_reason": pause_reason,
        },
        "roles": {
            "draftor": {"role": "draftor", "joined": True},
            "reviewer": {"role": "reviewer", "joined": True},
        },
        "decisions": decisions,
    })

    def _serve(route):
        route.fulfill(status=200, content_type="application/json", body=body)

    page.route("**/loops/*/status", _serve)


def _open_unblock(page, dashboard_fleet):
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_selector(".loop-ctrl-unblock", timeout=10000)
    page.evaluate("() => document.querySelector('.loop-ctrl-unblock').click()")
    page.wait_for_selector(".loop-ctrl-input-area", timeout=5000)


def test_unblock_escalation_requires_response(page, dashboard_fleet):
    """Escalation: required label, Confirm disabled until non-blank, no blank POST."""
    _route_paused_status(page, "blocked_on_architect", pending_decision=True)
    posts = []
    page.route("**/loops/*/unblock",
               lambda route: (posts.append(route.request.post_data), route.fulfill(
                   status=200, content_type="application/json", body='{"ok": true}')))
    _open_unblock(page, dashboard_fleet)

    label = page.evaluate("() => document.querySelector('.loop-ctrl-label').textContent")
    # #53: the label names the role that escalated.
    assert label == "Response to Draftor (required)"
    assert page.evaluate("() => document.querySelector('.loop-ctrl-confirm').disabled") is True

    # Whitespace does not enable Confirm; a forced click is refused client-side.
    page.fill(".loop-ctrl-input", "   ")
    assert page.evaluate("() => document.querySelector('.loop-ctrl-confirm').disabled") is True
    page.evaluate("""() => {
        var b = document.querySelector('.loop-ctrl-confirm');
        b.disabled = false; b.click();
    }""")
    page.wait_for_selector(".loop-ctrl-error", timeout=5000)
    assert posts == []

    page.fill(".loop-ctrl-input", "Narrow to #35 only.")
    assert page.evaluate("() => document.querySelector('.loop-ctrl-confirm').disabled") is False
    page.evaluate("() => document.querySelector('.loop-ctrl-confirm').click()")
    page.wait_for_timeout(500)
    assert len(posts) == 1
    import json as _json
    body = _json.loads(posts[0])
    assert body == {"message": "Narrow to #35 only."}, "unchanged timeout must not be sent"

    page.unroute("**/loops/*/unblock")
    page.unroute("**/loops/*/status")


def test_unblock_ordinary_pause_message_optional_and_timeout(page, dashboard_fleet):
    """Ordinary pause: optional label, timeout defaults to session value, changed value sent."""
    import json as _json
    _route_paused_status(page, "paused_by_architect", pending_decision=False,
                         turn_timeout=480)
    posts = []
    page.route("**/loops/*/unblock",
               lambda route: (posts.append(route.request.post_data), route.fulfill(
                   status=200, content_type="application/json", body='{"ok": true}')))
    _open_unblock(page, dashboard_fleet)

    label = page.evaluate("() => document.querySelector('.loop-ctrl-label').textContent")
    assert label == "Message (optional)"
    assert page.evaluate("() => document.querySelector('.loop-ctrl-confirm').disabled") is False
    assert page.evaluate("() => document.querySelector('.loop-ctrl-timeout').value") == "480"

    # Out-of-range timeout is refused before any request.
    page.fill(".loop-ctrl-timeout", "10")
    page.evaluate("() => document.querySelector('.loop-ctrl-confirm').click()")
    page.wait_for_selector(".loop-ctrl-error", timeout=5000)
    assert posts == []

    page.fill(".loop-ctrl-timeout", "900")
    page.evaluate("() => document.querySelector('.loop-ctrl-confirm').click()")
    page.wait_for_timeout(500)
    assert len(posts) == 1
    assert _json.loads(posts[0]) == {"timeout": 900}

    page.unroute("**/loops/*/unblock")
    page.unroute("**/loops/*/status")


def test_poll_does_not_wipe_composed_response(page, dashboard_fleet):
    """The 3 s status poll must not clear a response being typed."""
    _route_paused_status(page, "blocked_on_architect", pending_decision=True)
    _open_unblock(page, dashboard_fleet)
    page.fill(".loop-ctrl-input", "half-typed answer")
    page.wait_for_timeout(4000)  # > POLL_INTERVAL_MS
    value = page.evaluate("() => document.querySelector('.loop-ctrl-input').value")
    assert value == "half-typed answer"
    page.unroute("**/loops/*/status")


# ── timeline artifact links (link-only cards) ─────────────────────────────
#
# Timeline cards are link-only: an event with an artifact renders a
# synchronous "View full artifact" link from its metadata and never fetches
# artifact text. The full rendered document opens in the artifact reader.


def _count_artifact_requests(page):
    """Start counting /artifact/ requests from now; returns a getter."""
    seen = []
    page.on("request", lambda req: seen.append(req.url)
            if "/artifact/" in req.url else None)
    return lambda: list(seen)


_XSS_SUMMARY = ('The plan is sound. <img src=x onerror="window.__xss62=1">'
                ' <b>not bold</b> Address recovery next.')


def _card_facts(page):
    return page.evaluate("""() => Array.from(
        document.querySelectorAll('#loop-timeline .loop-event'))
        .map(c => ({
            event: c.querySelector('.loop-event-label').textContent,
            artifact: c.dataset.artifact || null,
            detail: (c.querySelector('.loop-event-detail') || {}).textContent || null,
            summary: Array.from(c.querySelectorAll('.loop-event-executive'))
                .map(p => ({text: p.textContent,
                            absent: p.classList.contains('loop-event-executive-absent'),
                            elements: p.children.length})),
            links: Array.from(c.querySelectorAll('.loop-timeline-artifact-link'))
                .map(a => ({text: a.textContent, artifact: a.dataset.artifact,
                            href: a.getAttribute('href')})),
            order: Array.from(c.children).map(e => e.className),
        }))""")


def _open_with_events(page, dashboard_fleet, events):
    payload = _live_payload()
    payload["events"] = events
    _serve_mutable_loop(page, payload)
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_selector(".loop-event", timeout=10000)
    return payload


def test_timeline_card_summary_from_event(page, dashboard_fleet):
    """#62: a summary-bearing event shows its escaped paragraph between the
    metadata and exactly one link; participant markup stays text; the
    technical detail gives way to the role; nothing is extracted."""
    events = list(_BASE_EVENTS)
    events[2] = dict(events[2], detail="Findings on staged tree abc123",
                     executive_summary=_XSS_SUMMARY)
    try:
        _open_with_events(page, dashboard_fleet, events)
        page.wait_for_selector(".loop-event-executive:not(.loop-event-executive-absent)",
                               timeout=10000)
        card = [c for c in _card_facts(page)
                if c["artifact"] == "findings.round-1.md"][0]
        assert card["summary"] == [{"text": _XSS_SUMMARY, "absent": False,
                                    "elements": 0}]
        assert card["detail"] == "reviewer"     # not the tree-id detail
        assert card["links"] == [{"text": "View full artifact",
                                  "artifact": "findings.round-1.md",
                                  "href": "#"}]
        names = [n.split()[0] for n in card["order"]]
        assert names.index("loop-event-executive") < names.index("loop-event-link-row")
        assert names.index("loop-event-label") < names.index("loop-event-executive")
        assert page.evaluate("() => window.__xss62") is None
        assert page.evaluate(
            "() => window.GatorViews && window.GatorViews._extractSummary") is None
    finally:
        _unserve_mutable_loop(page)


def test_loop_reading_hierarchy(page, dashboard_fleet):
    """Paper: the Now line, the turn's executive paragraph and the dialog
    explanation are reading prose (--text-base / --leading-prose); event
    metadata stays compact; artifact rows are sans action text; dialog
    labels and inputs are --text-ui. CSS only: the paragraph is styled as
    the card is built, with no reconciliation pass."""
    events = list(_BASE_EVENTS)
    events[2] = dict(events[2], executive_summary="The plan is ready to implement.")
    try:
        _open_with_events(page, dashboard_fleet, events)
        page.wait_for_selector(".loop-event-executive:not(.loop-event-executive-absent)",
                               timeout=10000)
        page.wait_for_selector(".loop-artifact-toggle", timeout=10000)
        facts = page.evaluate("""() => {
            const root = getComputedStyle(document.documentElement);
            const cs = s => getComputedStyle(document.querySelector(s));
            const px = v => parseFloat(v);
            const card = document.querySelector('.loop-event-executive').closest('.loop-event');
            return {
                base: px(root.getPropertyValue('--text-base')),
                ui: px(root.getPropertyValue('--text-ui')),
                prose: parseFloat(root.getPropertyValue('--leading-prose')),
                now: [px(cs('.loop-now').fontSize), px(cs('.loop-now').lineHeight)],
                exec: [px(cs('.loop-event-executive:not(.loop-event-executive-absent)').fontSize),
                       px(cs('.loop-event-executive:not(.loop-event-executive-absent)').lineHeight)],
                time: px(cs('.loop-event-time').fontSize),
                label: px(cs('.loop-event-label').fontSize),
                link: px(cs('.loop-timeline-artifact-link').fontSize),
                cardPad: px(getComputedStyle(card).paddingTop),
                toggle: [px(cs('.loop-artifact-toggle').fontSize),
                         cs('.loop-artifact-toggle').fontFamily],
            };
        }""")
        prose = [facts["base"], round(facts["base"] * facts["prose"], 1)]
        assert facts["now"] == prose and facts["exec"] == prose, facts
        assert facts["time"] <= 13 and facts["label"] <= 13 and facts["link"] == 12, facts
        assert facts["cardPad"] == 12, facts
        assert facts["toggle"][0] == facts["ui"], facts
        assert "Consolas" not in facts["toggle"][1], facts

        page.click('#loop-controls .loop-ctrl-btn[data-action="interject"]')
        page.wait_for_selector("dialog.loop-dialog[open]", timeout=5000)
        dialog = page.evaluate("""() => {
            const cs = s => getComputedStyle(document.querySelector('dialog.loop-dialog[open] ' + s));
            return {note: [parseFloat(cs('.loop-dialog-note').fontSize),
                           parseFloat(cs('.loop-dialog-note').lineHeight)],
                    label: parseFloat(cs('.loop-ctrl-label').fontSize),
                    input: parseFloat(cs('.loop-ctrl-input').fontSize)};
        }""")
        assert dialog["note"] == prose, dialog
        assert dialog["label"] == facts["ui"] and dialog["input"] == facts["ui"], dialog
        page.keyboard.press("Escape")
    finally:
        _unserve_mutable_loop(page)


_MAX = 1200


@pytest.mark.parametrize("value,expect", [
    ("a" * _MAX, "a" * _MAX),
    ("  a\n  b  ", "a b"),
    ("", None),
    ("   \n  ", None),
    (42, None),
    (None, None),
    (["x"], None),
    ("a" * (_MAX + 1), None),
    # Review finding: code points, as the CLI counts (an emoji is one).
    ("\U0001F600" + "a" * (_MAX - 1), "\U0001F600" + "a" * (_MAX - 1)),
    ("\U0001F600" + "a" * _MAX, None),
], ids=["at-limit", "normalized", "empty", "whitespace", "number", "null",
        "list", "over-limit", "astral-at-limit", "astral-over-limit"])
def test_timeline_projection_validity(page, dashboard_fleet, value, expect):
    """#62 bounded display contract: only a 1..1200-character string on an
    artifact event is shown; anything else is the absence line. The link
    stays either way."""
    events = list(_BASE_EVENTS)
    events[1] = dict(events[1], executive_summary=value)
    try:
        _open_with_events(page, dashboard_fleet, events)
        page.wait_for_selector('.loop-event[data-artifact="plan.round-1.md"] '
                               '.loop-event-executive', timeout=10000)
        card = [c for c in _card_facts(page)
                if c["artifact"] == "plan.round-1.md"][0]
        if expect is None:
            assert card["summary"] == [{
                "text": "Executive summary unavailable for this artifact.",
                "absent": True, "elements": 0}]
        else:
            assert card["summary"] == [{"text": expect, "absent": False,
                                        "elements": 0}]
        assert len(card["links"]) == 1
    finally:
        _unserve_mutable_loop(page)


def test_timeline_absence_only_for_artifact_events(page, dashboard_fleet):
    """#62: legacy artifact events show the absence line; non-artifact
    lifecycle events show none (even with a stray summary field) and keep
    their full Architect detail."""
    events = list(_BASE_EVENTS) + [
        {"event": "loop_paused", "ts": "2026-09-22T10:03:00Z", "round": 2,
         "role": "architect", "detail": "Hold for the demo.",
         "executive_summary": "Looks valid but there is no artifact."},
        {"event": "architect_interjection", "ts": "2026-09-22T10:04:00Z",
         "round": 2, "role": "architect", "detail": "Keep scope narrow."},
        {"event": "escalated", "ts": "2026-09-22T10:05:00Z", "round": 2,
         "role": "draftor", "detail": "Need a decision on the API.",
         "decision_request": "decision-request.decision-1.round-2.md"},
    ]
    try:
        _open_with_events(page, dashboard_fleet, events)
        page.wait_for_selector(".loop-event-executive-absent", timeout=10000)
        facts = _card_facts(page)
        for c in facts:
            if c["artifact"]:
                assert [s["absent"] for s in c["summary"]] == [True], c
            else:
                assert c["summary"] == [], c
        details = {c["detail"] for c in facts if not c["artifact"]}
        assert {"Hold for the demo.", "Keep scope narrow.",
                "Need a decision on the API."} <= details
    finally:
        _unserve_mutable_loop(page)


def test_event_without_artifact_has_no_link(page, dashboard_fleet):
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card", state="attached", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_selector(".loop-event", timeout=10000)
    counts = page.evaluate("""() => Array.from(
        document.querySelectorAll('#loop-timeline .loop-event:not([data-artifact])'))
        .map(c => c.querySelectorAll('.loop-timeline-artifact-link').length)""")
    assert counts, "expected at least one event without an artifact"
    assert all(n == 0 for n in counts)


def test_link_present_without_executive_summary(page, dashboard_fleet):
    """The link never depends on an Executive Summary heading: the active
    loop's findings artifact has none, and its event still has the link."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card", state="attached", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_selector(".loop-event[data-artifact]", timeout=10000)
    findings_links = page.evaluate("""() => Array.from(document.querySelectorAll(
        '#loop-timeline .loop-event[data-artifact^="findings"] .loop-timeline-artifact-link'))
        .length""")
    assert findings_links >= 1


def test_timeline_makes_no_artifact_requests_until_link_followed(page, dashboard_fleet):
    """Initial render and appended events fetch nothing; following a link
    fetches exactly that artifact once, via the card's expand path."""
    payload = _live_payload()
    _serve_mutable_loop(page, payload)
    requests = _count_artifact_requests(page)
    try:
        _navigate_to_loop(page, dashboard_fleet)
        page.wait_for_selector(".loop-status-header", timeout=10000)
        _select_loop_card(page, "widget-refactor")
        page.wait_for_selector(".loop-event[data-artifact]", timeout=10000)
        page.wait_for_timeout(1500)
        assert requests() == [], "timeline/initial render must not fetch artifacts"

        payload["events"].append(
            {"event": "draft_submitted", "ts": "2026-09-22T10:06:00Z", "round": 2,
             "role": "draftor", "artifact_path": "plan.round-2.md",
             "executive_summary": "Round two plan, from the event."})
        page.wait_for_selector(
            '.loop-event[data-artifact="plan.round-2.md"] .loop-timeline-artifact-link',
            timeout=10000)
        # #62: the appended card's summary comes from the event, not a fetch.
        assert page.evaluate("""() => document.querySelector(
            '.loop-event[data-artifact="plan.round-2.md"] .loop-event-executive'
            ).textContent""") == "Round two plan, from the event."
        page.wait_for_timeout(1000)
        assert not [u for u in requests() if "plan.round-2.md" in u], \
            "appending a timeline event must not fetch its artifact"

        page.evaluate("""() => document.querySelector(
            '.loop-event[data-artifact="plan.round-2.md"] .loop-timeline-artifact-link').click()""")
        page.wait_for_function("""() => {
            var c = document.querySelector(
                '.loop-artifact-section[data-artifact="plan.round-2.md"] .loop-artifact-content');
            return c && c.style.display !== 'none' && c.dataset.loaded === '1';
        }""", timeout=10000)
        page.wait_for_timeout(300)
        assert len([u for u in requests() if "plan.round-2.md" in u]) == 1
    finally:
        _unserve_mutable_loop(page)


def test_timeline_link_keeps_open_section_open(page, dashboard_fleet):
    """Following a link to an already-expanded artifact leaves it expanded
    (no toggle-close) and does not refetch it."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card", state="attached", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_selector(".loop-timeline-artifact-link", timeout=10000)
    name = page.evaluate(
        "() => document.querySelector('.loop-timeline-artifact-link').dataset.artifact")
    sel = '.loop-artifact-section[data-artifact="%s"] .loop-artifact-content' % name
    page.evaluate("() => document.querySelector('.loop-timeline-artifact-link').click()")
    page.wait_for_function("s => { var c = document.querySelector(s);"
                           " return c && c.dataset.loaded === '1'; }", arg=sel, timeout=10000)
    requests = _count_artifact_requests(page)
    page.evaluate("() => document.querySelector('.loop-timeline-artifact-link').click()")
    page.wait_for_timeout(500)
    assert page.evaluate("s => document.querySelector(s).style.display", sel) != "none"
    assert not [u for u in requests() if name in u]


def test_timeline_link_keyboard_activation(page, dashboard_fleet):
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card", state="attached", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_selector(".loop-timeline-artifact-link", timeout=10000)
    name = page.evaluate(
        "() => document.querySelector('.loop-timeline-artifact-link').dataset.artifact")
    page.focus(".loop-timeline-artifact-link")
    page.keyboard.press("Enter")
    page.wait_for_function(
        "n => { var c = document.querySelector('.loop-artifact-section[data-artifact=\"'"
        " + n + '\"] .loop-artifact-content'); return c && c.style.display !== 'none'; }",
        arg=name, timeout=10000)


def test_timeline_event_shows_artifact_link(page, dashboard_fleet):
    """Submission events in the timeline include a 'View full artifact' link."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card", state="attached", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_function(
        "() => document.querySelector('.loop-timeline-artifact-link') !== null",
        timeout=10000,
    )
    links = page.evaluate("""
        () => Array.from(document.querySelectorAll('.loop-timeline-artifact-link'))
            .map(el => ({ text: el.textContent, artifact: el.dataset.artifact }))
    """)
    assert len(links) > 0, "Expected at least one artifact link in timeline"
    assert any("View full artifact" in l["text"] for l in links)


def test_timeline_artifact_link_opens_inspector(page, dashboard_fleet):
    """Clicking 'View full artifact' in the timeline opens the artifact inspector."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card", state="attached", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_function(
        "() => document.querySelector('.loop-timeline-artifact-link') !== null",
        timeout=10000,
    )
    artifact_name = page.evaluate("""
        () => document.querySelector('.loop-timeline-artifact-link').dataset.artifact
    """)
    page.evaluate("""
        () => document.querySelector('.loop-timeline-artifact-link').click()
    """)
    page.wait_for_function(
        "(name) => {"
        "  var s = document.querySelector("
        "    '.loop-artifact-section[data-artifact=\"' + name + '\"] .loop-artifact-content');"
        "  return s && s.style.display !== 'none';"
        "}",
        arg=artifact_name,
        timeout=10000,
    )


# ── secondary sidebar (Module 1 / B1–B4) ──────────────────────────────────


def test_sidebar_active_and_history_classification(page, dashboard_fleet):
    """B2 (2026-10-21): the list pane holds History only. Terminal loops
    are listed; the active loop is not listed anywhere in it."""
    _navigate_to_loop(page, dashboard_fleet)
    headers = page.evaluate("""
        () => Array.from(document.querySelectorAll(
            '#loop-sidebar-nav .loop-sidebar-section-header')).map(el => el.textContent)
    """)
    assert headers == ["History"]
    listed = _panel_features(page, "loop-sidebar-nav")
    assert "auth-migration" in listed
    assert "widget-refactor" not in listed


def test_sidebar_empty_sections(page, dashboard_fleet):
    """B3: a repo with no loops shows the History empty state, and no
    Active section."""
    origin = dashboard_fleet["url"].rstrip("/") + "/"
    page.goto(origin + "?repo=beta", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    page.evaluate(
        "() => document.querySelector('.sidebar-item[data-view=\"loop\"]').click()"
    )
    page.wait_for_selector('.loop-workspace[data-loaded="1"]', state="attached", timeout=10000)
    page.evaluate("() => document.querySelector('#loop-tab-history').click()")
    assert _tab_state(page)["sidebarHidden"] is False
    text = page.evaluate(
        "() => document.getElementById('loop-sidebar-nav').textContent")
    assert "No active loop" not in text
    assert "No completed loops" in text


# B4 is rewritten for #56 as test_sidebar_create_with_active_loop (below).


# ── state transitions (Module 6 / B5–B7) ──────────────────────────────────


def test_no_loops_shows_create(page, dashboard_fleet):
    """B5: no loops → creation workspace rendered."""
    origin = dashboard_fleet["url"].rstrip("/") + "/"
    page.goto(origin + "?repo=beta", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    page.evaluate(
        "() => document.querySelector('.sidebar-item[data-view=\"loop\"]').click()"
    )
    page.wait_for_selector(".loop-create-workspace", timeout=10000)
    assert page.locator(".loop-create-workspace").count() == 1


def test_active_loop_auto_selects_inspect(page, dashboard_fleet):
    """B7: active loop → auto-selected, live workspace shown on mount."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    has_controls = page.locator(".loop-ctrl-btn").count() > 0
    assert has_controls, "Active loop should show controls on mount"


# ── creation workspace (Module 3 / B8–B12) ────────────────────────────────


def test_creation_form_renders(page, dashboard_fleet):
    """B8: creation workspace renders feature input, sketch picker,
    advanced settings."""
    origin = dashboard_fleet["url"].rstrip("/") + "/"
    page.goto(origin + "?repo=beta", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    page.evaluate(
        "() => document.querySelector('.sidebar-item[data-view=\"loop\"]').click()"
    )
    page.wait_for_selector(".loop-create-workspace", timeout=10000)
    assert page.locator("#loop-feature-input").count() == 1
    assert page.locator("#loop-sketch-picker").count() == 1
    assert page.locator(".loop-create-advanced").count() == 1
    assert page.locator("#loop-create-action").count() == 1


def test_creation_validation_blocks_empty_feature(page, dashboard_fleet):
    """B10: empty feature → client-side validation error."""
    origin = dashboard_fleet["url"].rstrip("/") + "/"
    page.goto(origin + "?repo=beta", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    page.evaluate(
        "() => document.querySelector('.sidebar-item[data-view=\"loop\"]').click()"
    )
    page.wait_for_selector("#loop-create-action", timeout=10000)
    page.evaluate("() => document.querySelector('#loop-create-action').click()")
    page.wait_for_selector("#loop-create-error", timeout=5000)
    error_visible = page.evaluate("""
        () => {
            var el = document.querySelector('#loop-create-error');
            return el && el.style.display !== 'none' && el.textContent;
        }
    """)
    assert error_visible, "Error should be visible for empty feature"
    assert "Feature" in error_visible or "required" in error_visible.lower()


@pytest.mark.parametrize("after", ["active", "none", "failed"])
def test_creation_409_transitions_to_active(page, dashboard_fleet, after):
    """B12 (2026-10-21): a 409 "active loop exists" refetches the loop list.
    With an active loop in it, Primary shows Active with a notice; with none,
    or with a failed list, the form stays with an honest error text. There
    is never an "Open active loop" link or a disabled form."""
    holder = {"loops": [], "fail": None}
    _serve_list(page, holder)
    page.route("**/sketch-sources", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"sources": []})))
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector("#loop-create-action", timeout=10000)
    page.wait_for_selector("#loop-sketch-manual", timeout=5000)

    def conflict(route):
        if after == "active":
            holder["loops"] = [_list_item(_ACTIVE_ID, "widget-refactor", "plan_drafting")]
        elif after == "failed":
            holder["fail"] = "http500"
        route.fulfill(status=409, content_type="application/json",
                      body=json.dumps({"error": "active loop exists",
                                       "loop_id": _ACTIVE_ID}))

    page.route("**/loops/start", conflict)
    length = page.evaluate("() => history.length")
    page.fill("#loop-feature-input", "test-feature")
    page.fill("#loop-sketch-manual", ".gator/artifacts/test.md")
    page.evaluate("() => document.querySelector('#loop-create-action').click()")

    if after == "active":
        _wait_header(page, "widget-refactor")
        page.wait_for_selector(
            '[data-slot="action"] .loop-transition-notice[data-kind="text"]',
            timeout=5000)
        text = page.evaluate("""() => document.querySelector(
            '[data-slot="action"] .loop-transition-notice').textContent""")
        assert "your form was not submitted" in text
        assert _tab_state(page)["create"]["text"] == "Active"
        assert page.evaluate("() => history.length") == length
    else:
        page.wait_for_function(
            "() => document.querySelector('#loop-create-error').style.display !== 'none'",
            timeout=5000)
        error_text = page.evaluate(
            "() => document.querySelector('#loop-create-error').textContent")
        assert "already active elsewhere" in error_text
        assert ("could not be loaded" in error_text) == (after == "failed")
        assert page.input_value("#loop-feature-input") == "test-feature"
        assert not page.evaluate(
            "() => document.querySelector('#loop-create-action').disabled")
    assert page.locator(".loop-create-open-active").count() == 0


# ── live vs history workspace (Module 5 / B18–B23) ────────────────────────


def test_active_loop_shows_controls_and_prompts(page, dashboard_fleet):
    """B18: active loop shows controls and prompt copy."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card", state="attached", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_selector(".loop-ctrl-btn", timeout=10000)
    assert page.locator(".loop-ctrl-btn").count() > 0
    assert page.locator(".loop-prompt-copy").count() == 2


def test_terminal_loop_read_only(page, dashboard_fleet):
    """B19: terminal loop shows outcome badge, no controls, no prompts."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card", state="attached", timeout=10000)
    _select_loop_card(page, "auth-migration")
    page.wait_for_selector(".loop-badge-outcome", timeout=10000)
    assert page.locator(".loop-badge-outcome").count() > 0
    assert page.locator(".loop-ctrl-btn").count() == 0
    assert page.locator(".loop-prompt-copy").count() == 0
    has_outcome_meta = page.locator(".loop-outcome-meta").count() > 0
    assert has_outcome_meta, "Terminal loop should show outcome meta"


def test_blocked_loop_shows_prominent_card(page, dashboard_fleet):
    """B20: blocked loop shows prominent blocked card with decision link."""
    _open_sole_active(page, dashboard_fleet, "blocked-feature")
    page.wait_for_selector(".loop-blocked-card", timeout=10000)
    # L1: the compact alert carries no request text; the dialog does.
    assert page.locator(".loop-blocked-card .loop-blocked-reason").count() == 0
    _open_decision_dialog(page)
    reason = page.evaluate(
        "() => document.querySelector('dialog.loop-dialog .loop-blocked-reason').textContent")
    assert "scope" in reason.lower()
    assert page.locator(".loop-blocked-artifact-link").count() == 1


def test_blocked_card_decision_link_opens_inspector(page, dashboard_fleet):
    """B21: clicking decision link opens inspector section with content."""
    _open_sole_active(page, dashboard_fleet, "blocked-feature")
    _open_decision_dialog(page)
    artifact_name = page.evaluate(
        "() => document.querySelector('.loop-blocked-artifact-link').dataset.artifact")
    assert "decision-request" in artifact_name
    page.evaluate(
        "() => document.querySelector('.loop-blocked-artifact-link').click()")
    # Following the link closes the dialog and opens the artifact row.
    page.wait_for_function(
        "() => !document.querySelector('dialog.loop-dialog')", timeout=5000)
    page.wait_for_function(
        "(name) => {"
        "  var s = document.querySelector("
        "    '.loop-artifact-section[data-artifact=\"' + name + '\"] .loop-artifact-pre');"
        "  return s !== null;"
        "}",
        arg=artifact_name,
        timeout=10000,
    )
    content = page.evaluate("""
        (name) => {
            var s = document.querySelector(
                '.loop-artifact-section[data-artifact="' + name + '"] .loop-artifact-pre');
            return s ? s.textContent : null;
        }
    """, artifact_name)
    assert content is not None, "Decision artifact content should load"
    assert "Resource" in content or "resource" in content.lower()


def test_round_zero_artifact_via_timeline_link(page, dashboard_fleet):
    """B23: round-zero draft event timeline link opens plan.round-0.md
    inspector section with submitted content."""
    _open_sole_active(page, dashboard_fleet, "roundzero-test")
    # Wait for the timeline artifact link for plan.round-0.md
    page.wait_for_function(
        "() => {"
        "  var links = document.querySelectorAll('.loop-timeline-artifact-link');"
        "  for (var i = 0; i < links.length; i++) {"
        "    if (links[i].dataset.artifact === 'plan.round-0.md') return true;"
        "  }"
        "  return false;"
        "}",
        timeout=10000,
    )
    # Click the timeline link
    page.evaluate("""
        () => {
            var links = document.querySelectorAll('.loop-timeline-artifact-link');
            for (var i = 0; i < links.length; i++) {
                if (links[i].dataset.artifact === 'plan.round-0.md') {
                    links[i].click(); break;
                }
            }
        }
    """)
    page.wait_for_function(
        "() => {"
        "  var s = document.querySelector("
        "    '.loop-artifact-section[data-artifact=\"plan.round-0.md\"] .loop-artifact-pre');"
        "  return s !== null;"
        "}",
        timeout=10000,
    )
    content = page.evaluate("""
        () => {
            var pre = document.querySelector(
                '.loop-artifact-section[data-artifact="plan.round-0.md"] .loop-artifact-pre');
            return pre ? pre.textContent : null;
        }
    """)
    assert content is not None, "plan.round-0.md content should load"
    assert "Round zero" in content or "round zero" in content.lower()


def test_pending_decision_selected_over_resolved(page, dashboard_fleet):
    """B22: blocked card with resolved older decision + later pending:
    card links to the pending request artifact, not the resolved one."""
    _open_sole_active(page, dashboard_fleet, "blocked-feature")
    _open_decision_dialog(page)
    artifact_name = page.evaluate(
        "() => document.querySelector('.loop-blocked-artifact-link').dataset.artifact")
    assert artifact_name == "decision-request.decision-2.round-1.md", (
        f"Blocked card should link to the pending decision-2, "
        f"not the resolved decision-1; got: {artifact_name}")


# ── history-only mount (B6) ────────────────────────────────────────────────


def test_history_only_defaults_to_create(page, dashboard_fleet):
    """B6: only history loops → creation workspace shown on mount."""
    import json as _json

    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector('.loop-workspace[data-loaded="1"]', state="attached", timeout=10000)

    # Intercept loops list to return only terminal loops
    page.route("**/api/repo-by-key/*/loops", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=_json.dumps({"loops": [
            {"loop_id": "old-loop", "feature": "old-feature",
             "stage": "plan_approved", "round": 2, "max_rounds": 3,
             "created_at": "2026-09-20T10:00:00Z"},
        ]})))

    # Re-navigate to pick up intercepted data
    page.evaluate(
        "() => document.querySelector('.sidebar-item[data-view=\"loop\"]').click()"
    )
    page.wait_for_selector(".loop-create-workspace", timeout=10000)
    assert page.locator(".loop-create-workspace").count() == 1
    page.unroute("**/api/repo-by-key/*/loops")


# ── sketch picker (B9) ────────────────────────────────────────────────────


def test_sketch_source_dropdown_and_manual_toggle(page, dashboard_fleet):
    """B9: sketch sources populate dropdown; toggle switches to manual."""
    origin = dashboard_fleet["url"].rstrip("/") + "/"
    page.goto(origin + "?repo=alpha", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)

    import json as _json
    # Intercept loops to return empty (enable create)
    page.route("**/api/repo-by-key/*/loops", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=_json.dumps({"loops": []})))
    # Intercept sketch sources to return known files
    page.route("**/sketch-sources", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=_json.dumps({"sources": [
            {"path": ".gator/artifacts/sketch-a.md", "name": "sketch-a.md",
             "size": 100, "modified": 1727200000},
            {"path": ".gator/artifacts/sketch-b.md", "name": "sketch-b.md",
             "size": 200, "modified": 1727100000},
        ]})))

    page.evaluate(
        "() => document.querySelector('.sidebar-item[data-view=\"loop\"]').click()")
    page.wait_for_selector("#loop-sketch-select", timeout=10000)

    options = page.evaluate("""
        () => Array.from(document.querySelectorAll('#loop-sketch-select option'))
            .map(o => o.value).filter(v => v)
    """)
    assert ".gator/artifacts/sketch-a.md" in options
    assert ".gator/artifacts/sketch-b.md" in options

    # Manual input should be hidden
    manual_hidden = page.evaluate(
        "() => document.querySelector('#loop-sketch-manual').style.display === 'none'")
    assert manual_hidden, "Manual input should be hidden when sources exist"

    # Toggle to manual
    page.evaluate("() => document.querySelector('#loop-sketch-toggle').click()")
    manual_visible = page.evaluate(
        "() => document.querySelector('#loop-sketch-manual').style.display !== 'none'")
    assert manual_visible, "Manual input should be visible after toggle"
    select_hidden = page.evaluate(
        "() => document.querySelector('#loop-sketch-select').style.display === 'none'")
    assert select_hidden, "Dropdown should be hidden after toggle"

    page.unroute("**/api/repo-by-key/*/loops")
    page.unroute("**/sketch-sources")


# ── creation → handoff transition (B11) ────────────────────────────────────


def test_successful_creation_transitions_to_handoff(page, dashboard_fleet):
    """B11: successful creation transitions to handoff mode,
    sidebar re-renders with new active loop."""
    import json as _json

    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector('.loop-workspace[data-loaded="1"]', state="attached", timeout=10000)

    # Intercept loops to report no loops (enable create)
    page.route("**/api/repo-by-key/*/loops", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=_json.dumps({"loops": []})))
    page.route("**/sketch-sources", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=_json.dumps({"sources": []})))

    # Re-navigate to get create workspace
    page.evaluate(
        "() => document.querySelector('.sidebar-item[data-view=\"loop\"]').click()")
    page.wait_for_selector("#loop-create-action", timeout=10000)

    # Intercept start to succeed
    page.route("**/loops/start", lambda route: route.fulfill(
        status=201, content_type="application/json",
        body=_json.dumps({"loop_id": "new-test-loop"})))
    # After creation, loops list returns the new loop
    page.unroute("**/api/repo-by-key/*/loops")
    page.route("**/api/repo-by-key/*/loops", lambda route: (
        route.fulfill(
            status=200, content_type="application/json",
            body=_json.dumps({"loops": [
                {"loop_id": "new-test-loop", "feature": "test-feature",
                 "stage": "plan_drafting", "round": 0, "max_rounds": 3,
                 "created_at": "2026-09-24T12:00:00Z"},
            ]}))
        if "/status" not in route.request.url
        and "/events" not in route.request.url
        and "/start" not in route.request.url
        else route.fallback()
    ))
    # Intercept status for the new loop
    page.route("**/loops/new-test-loop/status", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=_json.dumps({
            "loop_id": "new-test-loop", "feature": "test-feature",
            "status": {"stage": "plan_drafting", "round": 0, "max_rounds": 3,
                       "next_role": "draftor", "blocked": False},
            "roles": {"draftor": {"role": "draftor", "joined": False},
                      "reviewer": {"role": "reviewer", "joined": False}},
            "decisions": [],
        })))

    # Fill and submit
    page.wait_for_selector("#loop-sketch-manual", timeout=5000)
    page.fill("#loop-feature-input", "test-feature")
    page.fill("#loop-sketch-manual", ".gator/artifacts/test.md")
    page.evaluate("() => document.querySelector('#loop-create-action').click()")

    # Should transition to handoff
    page.wait_for_selector(".loop-handoff", timeout=10000)
    assert page.locator(".loop-handoff-copy").count() == 2, (
        "Handoff should show two copy buttons")

    page.unroute("**/api/repo-by-key/*/loops")
    page.unroute("**/loops/start")
    page.unroute("**/sketch-sources")
    page.unroute("**/loops/new-test-loop/status")


# ── handoff tests (B13–B17) ──────────────────────────────────────────────


def _enter_handoff(page, dashboard_fleet):
    """Helper: set up a mocked handoff state by intercepting APIs."""
    import json as _json

    _navigate_to_loop(page, dashboard_fleet)

    # Intercept to show no loops → create workspace; once the start call
    # succeeds the list reports the new loop as active, like the server.
    listed = {"loops": [], "fail": False}

    def serve_listed(route):
        if listed["fail"]:
            route.fulfill(status=500, content_type="application/json",
                          body=_json.dumps({"error": "boom"}))
        else:
            route.fulfill(status=200, content_type="application/json",
                          body=_json.dumps({"loops": listed["loops"]}))

    page.route("**/api/repo-by-key/*/loops", serve_listed)
    page.route("**/sketch-sources", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=_json.dumps({"sources": []})))

    def start(route):
        listed["loops"] = [{
            "loop_id": "handoff-loop", "feature": "handoff-test",
            "mode": "planning", "stage": "plan_drafting", "round": 0,
            "max_rounds": 3, "created_at": "2026-10-21T10:00:00Z"}]
        route.fulfill(status=201, content_type="application/json",
                      body=_json.dumps({"loop_id": "handoff-loop"}))

    page.route("**/loops/start", start)
    page.route("**/loops/handoff-loop/status", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=_json.dumps({
            "loop_id": "handoff-loop", "feature": "handoff-test",
            "status": {"stage": "plan_drafting", "round": 0,
                       "max_rounds": 3, "next_role": "draftor",
                       "blocked": False},
            "roles": {"draftor": {"role": "draftor", "joined": False},
                      "reviewer": {"role": "reviewer", "joined": False}},
            "decisions": [],
        })))
    page.route("**/loops/handoff-loop/events", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=_json.dumps({"events": []})))

    page.evaluate(
        "() => document.querySelector('.sidebar-item[data-view=\"loop\"]').click()")
    page.wait_for_selector("#loop-create-action", timeout=10000)
    page.wait_for_selector("#loop-sketch-manual", timeout=5000)
    page.fill("#loop-feature-input", "handoff-test")
    page.fill("#loop-sketch-manual", ".gator/artifacts/test.md")
    page.evaluate("() => document.querySelector('#loop-create-action').click()")
    page.wait_for_selector(".loop-handoff", timeout=10000)
    return listed


def test_handoff_renders_both_cards_with_guidance(page, dashboard_fleet):
    """B13: handoff renders both prompt cards with security guidance."""
    _enter_handoff(page, dashboard_fleet)
    assert page.locator(".loop-handoff-copy").count() == 2
    guidance = page.evaluate(
        "() => document.querySelector('.loop-handoff-guidance').textContent")
    assert "credential" in guidance.lower() or "role" in guidance.lower()


def test_handoff_copy_calls_prompt_endpoint(page, dashboard_fleet):
    """B14: copy calls prompt endpoint with correct role."""
    import json as _json

    _enter_handoff(page, dashboard_fleet)

    prompt_calls = []

    def _capture_prompt(route):
        import json
        body = json.loads(route.request.post_data or "{}")
        prompt_calls.append(body.get("role"))
        route.fulfill(
            status=200, content_type="application/json",
            headers={"Cache-Control": "no-store"},
            body=json.dumps({"prompt": "test prompt for " + body.get("role", "")}))

    page.route("**/loops/handoff-loop/prompt", _capture_prompt)

    # Grant clipboard permissions for the test
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])

    page.evaluate("""
        () => document.querySelector('.loop-handoff-copy[data-role="draftor"]').click()
    """)
    page.wait_for_function(
        "() => document.querySelector('.loop-handoff-copy[data-role=\"draftor\"]').textContent !== 'Fetching…'",
        timeout=10000)
    assert "draftor" in prompt_calls, (
        f"Expected draftor prompt call; got: {prompt_calls}")

    page.unroute("**/loops/handoff-loop/prompt")


def test_handoff_draftor_join_keeps_reviewer_copy(page, dashboard_fleet):
    """B16: Draftor join updates indicator but does NOT remove
    Reviewer copy action."""
    import json as _json

    _enter_handoff(page, dashboard_fleet)

    # Now update status to show draftor joined
    page.unroute("**/loops/handoff-loop/status")
    page.route("**/loops/handoff-loop/status", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=_json.dumps({
            "loop_id": "handoff-loop", "feature": "handoff-test",
            "status": {"stage": "plan_drafting", "round": 0,
                       "max_rounds": 3, "next_role": "draftor",
                       "blocked": False},
            "roles": {"draftor": {"role": "draftor", "joined": True},
                      "reviewer": {"role": "reviewer", "joined": False}},
            "decisions": [],
        })))

    # Wait for poll to update
    page.wait_for_function(
        "() => {"
        "  var el = document.getElementById('loop-handoff-draftor-join');"
        "  return el && el.textContent === 'Joined';"
        "}",
        timeout=10000)

    # Reviewer copy button must still exist and be enabled
    reviewer_btn = page.locator('.loop-handoff-copy[data-role="reviewer"]')
    assert reviewer_btn.count() == 1, "Reviewer copy button should still exist"
    is_disabled = page.evaluate(
        "() => document.querySelector('.loop-handoff-copy[data-role=\"reviewer\"]').disabled")
    assert not is_disabled, "Reviewer copy should not be disabled"


def test_handoff_open_workspace_transitions(page, dashboard_fleet):
    """B17: 'Open loop workspace' transitions to inspect mode."""
    _enter_handoff(page, dashboard_fleet)

    st = _tab_state(page)
    assert st["create"]["text"] == "Active" and st["create"]["selected"] == "true"
    assert st["sidebarHidden"] is True
    page.evaluate("() => document.querySelector('#loop-handoff-open').click()")
    # Should transition to the selected loop workspace
    page.wait_for_selector(".loop-status-header", timeout=10000)
    assert page.locator(".loop-handoff").count() == 0, (
        "Handoff view should be gone after clicking Open workspace")
    st = _tab_state(page)
    assert st["create"]["text"] == "Active" and st["create"]["selected"] == "true"
    assert st["sidebarHidden"] is True


# ── terminal handoff credential removal ──────────────────────────────────


@pytest.mark.parametrize("listing", ["active", "terminal", "failed_then_terminal"])
def test_terminal_handoff_disables_copy_buttons(page, dashboard_fleet, listing):
    """Terminal status during handoff disables copy buttons, removes
    fallback textareas and shows the outcome badge. While the list still
    reports the loop active, or fails (a text-led retry line), the handoff
    stays with the copy buttons disabled and the single timer kept for the
    retry; once a valid list reports it terminal, the Primary tab returns
    to Create with an "ended" notice and polling stops."""
    import json as _json

    listed = _enter_handoff(page, dashboard_fleet)

    # Confirm copy buttons exist and are enabled
    assert page.locator(".loop-handoff-copy").count() == 2
    assert not page.evaluate(
        "() => document.querySelector('.loop-handoff-copy').disabled")

    # Transition to terminal status
    page.unroute("**/loops/handoff-loop/status")
    page.route("**/loops/handoff-loop/status", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=_json.dumps({
            "loop_id": "handoff-loop", "feature": "handoff-test",
            "status": {"stage": "plan_approved", "round": 1,
                       "max_rounds": 3, "next_role": None,
                       "blocked": False},
            "roles": {"draftor": {"role": "draftor", "joined": True},
                      "reviewer": {"role": "reviewer", "joined": True}},
            "decisions": [],
        })))
    if listing == "failed_then_terminal":
        listed["fail"] = True
        page.wait_for_selector(".loop-handoff-refresh", timeout=10000)
        assert "Refresh failed" in page.evaluate(
            "() => document.querySelector('.loop-handoff-refresh').textContent")
        assert page.evaluate("""() => Array.from(document.querySelectorAll(
            '.loop-handoff-copy')).every(b => b.disabled
                && b.textContent === 'Loop ended')""")
        assert page.evaluate(
            "() => document.querySelector('.loop-workspace').dataset.polling") == "1"
        assert _tab_state(page)["create"]["text"] == "Active"
        listed["fail"] = False
    if listing != "active":
        listed["loops"] = [dict(listed["loops"][0], stage="plan_approved")]
        page.wait_for_selector(
            '.loop-create-workspace', timeout=10000)
        page.wait_for_selector(
            '#loop-main-content > .loop-transition-notice[data-kind="ended"]',
            timeout=5000)
        assert page.locator(".loop-handoff-copy").count() == 0
        st = _tab_state(page)
        assert st["create"]["text"] == "Create" and st["create"]["selected"] == "true"
        assert page.evaluate(
            "() => document.querySelector('.loop-workspace').dataset.polling") == "0"
        return

    # Wait for buttons to become disabled
    page.wait_for_function(
        "() => {"
        "  var btns = document.querySelectorAll('.loop-handoff-copy');"
        "  if (btns.length === 0) return false;"
        "  for (var i = 0; i < btns.length; i++) {"
        "    if (!btns[i].disabled) return false;"
        "  }"
        "  return true;"
        "}",
        timeout=10000)

    # Buttons should show "Loop ended"
    btn_text = page.evaluate(
        "() => document.querySelector('.loop-handoff-copy').textContent")
    assert "ended" in btn_text.lower()

    # Fallback textareas should be removed
    assert page.locator(".loop-handoff-fallback").count() == 0

    # Outcome badge should appear
    assert page.locator(".loop-badge-outcome").count() > 0


# ── Escape closes advanced settings ─────────────────────────────────────


def test_escape_closes_advanced_settings(page, dashboard_fleet):
    """Escape key closes the advanced settings disclosure."""
    origin = dashboard_fleet["url"].rstrip("/") + "/"
    page.goto(origin + "?repo=beta", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    page.evaluate(
        "() => document.querySelector('.sidebar-item[data-view=\"loop\"]').click()")
    page.wait_for_selector(".loop-create-workspace", timeout=10000)

    # Open advanced settings
    page.evaluate(
        "() => document.querySelector('.loop-create-advanced').open = true")
    is_open = page.evaluate(
        "() => document.querySelector('.loop-create-advanced').open")
    assert is_open, "Advanced settings should be open"

    # Press Escape
    page.evaluate("""
        () => {
            var details = document.querySelector('.loop-create-advanced');
            details.dispatchEvent(new KeyboardEvent('keydown',
                { key: 'Escape', bubbles: true }));
        }
    """)
    is_closed = page.evaluate(
        "() => !document.querySelector('.loop-create-advanced').open")
    assert is_closed, "Escape should close advanced settings"


# ── prompt-copy race + clipboard assertions (B14/B15) ───────────────────


def test_inflight_copy_blocked_by_terminal_race(page, dashboard_fleet):
    """In-flight prompt copy is discarded when terminal state arrives
    before the response. Clipboard must not receive the credential."""
    import json as _json

    _enter_handoff(page, dashboard_fleet)
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])

    # Write a sentinel to the clipboard so we can verify it isn't overwritten
    page.evaluate("() => navigator.clipboard.writeText('SENTINEL')")

    # Set up a page-level gate: the prompt response won't resolve
    # until we call window.__releasePrompt()
    page.evaluate("""
        () => {
            window.__promptGate = new Promise(resolve => {
                window.__releasePrompt = resolve;
            });
        }
    """)

    # Intercept prompt endpoint — wait on the gate before fulfilling
    def _delayed_prompt(route):
        page.evaluate("() => window.__promptGate")
        route.fulfill(
            status=200, content_type="application/json",
            headers={"Cache-Control": "no-store"},
            body=_json.dumps({"prompt": "SECRET_TOKEN_DO_NOT_LEAK"}))

    page.route("**/loops/handoff-loop/prompt", _delayed_prompt)

    # Click copy — request goes in flight, button shows Fetching
    page.evaluate("""
        () => document.querySelector('.loop-handoff-copy[data-role="draftor"]').click()
    """)
    page.wait_for_function(
        "() => document.querySelector('.loop-handoff-copy[data-role=\"draftor\"]').textContent === 'Fetching…'",
        timeout=5000)

    # While fetch is in flight, transition loop to terminal
    page.unroute("**/loops/handoff-loop/status")
    page.route("**/loops/handoff-loop/status", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=_json.dumps({
            "loop_id": "handoff-loop", "feature": "handoff-test",
            "status": {"stage": "plan_approved", "round": 1,
                       "max_rounds": 3, "next_role": None,
                       "blocked": False},
            "roles": {"draftor": {"role": "draftor", "joined": True},
                      "reviewer": {"role": "reviewer", "joined": True}},
            "decisions": [],
        })))

    # Wait for terminal state to be detected by the poll — buttons
    # that are NOT the in-flight one should show "Loop ended"
    page.wait_for_function(
        "() => {"
        "  var btns = document.querySelectorAll('.loop-handoff-copy');"
        "  for (var i = 0; i < btns.length; i++) {"
        "    if (btns[i].dataset.role === 'reviewer'"
        "        && btns[i].textContent === 'Loop ended') return true;"
        "  }"
        "  return false;"
        "}",
        timeout=10000)

    # Now release the prompt response — copyPrompt should discard it
    page.evaluate("() => window.__releasePrompt()")

    # Give async copyPrompt time to finish processing
    page.wait_for_timeout(500)

    # Verify: no fallback textarea created
    assert page.locator(".loop-handoff-fallback").count() == 0, (
        "No fallback textarea should exist after terminal race")

    # Verify: clipboard still has sentinel, not the secret
    clip = page.evaluate("() => navigator.clipboard.readText()")
    assert "SECRET" not in (clip or ""), (
        f"Clipboard should not contain leaked prompt; got: {clip}")

    # The copy button should also show "Loop ended"
    btn_text = page.evaluate(
        "() => document.querySelector('.loop-handoff-copy[data-role=\"draftor\"]').textContent")
    assert "ended" in btn_text.lower(), (
        f"In-flight copy button should show 'Loop ended'; got: {btn_text}")

    page.unroute("**/loops/handoff-loop/prompt")


def test_copy_writes_prompt_to_clipboard(page, dashboard_fleet):
    """B14 clipboard: prompt text actually reaches the clipboard."""
    import json as _json

    _enter_handoff(page, dashboard_fleet)
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])

    page.route("**/loops/handoff-loop/prompt", lambda route: route.fulfill(
        status=200, content_type="application/json",
        headers={"Cache-Control": "no-store"},
        body=_json.dumps({"prompt": "gator loop join --token TEST_TOKEN"})))

    page.evaluate("""
        () => document.querySelector('.loop-handoff-copy[data-role="draftor"]').click()
    """)
    page.wait_for_function(
        "() => {"
        "  var b = document.querySelector('.loop-handoff-copy[data-role=\"draftor\"]');"
        "  return b && b.textContent === 'Copied';"
        "}",
        timeout=10000)

    clip = page.evaluate("() => navigator.clipboard.readText()")
    assert clip == "gator loop join --token TEST_TOKEN", (
        f"Clipboard should contain the prompt text; got: {clip}")

    page.unroute("**/loops/handoff-loop/prompt")


def test_prompt_not_persisted_after_navigation(page, dashboard_fleet):
    """B15: after copying and navigating away, prompt text is absent from
    localStorage, sessionStorage, and DOM data attributes."""
    import json as _json

    _enter_handoff(page, dashboard_fleet)
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])

    page.route("**/loops/handoff-loop/prompt", lambda route: route.fulfill(
        status=200, content_type="application/json",
        headers={"Cache-Control": "no-store"},
        body=_json.dumps({"prompt": "gator loop join --token PERSIST_CHECK"})))

    page.evaluate("""
        () => document.querySelector('.loop-handoff-copy[data-role="draftor"]').click()
    """)
    page.wait_for_function(
        "() => {"
        "  var b = document.querySelector('.loop-handoff-copy[data-role=\"draftor\"]');"
        "  return b && b.textContent === 'Copied';"
        "}",
        timeout=10000)

    # Navigate away — click Open workspace
    page.evaluate("() => document.querySelector('#loop-handoff-open').click()")
    page.wait_for_selector(".loop-status-header", timeout=10000)

    # Check localStorage
    local_dump = page.evaluate(
        "() => JSON.stringify(localStorage)")
    assert "PERSIST_CHECK" not in (local_dump or ""), (
        "Prompt should not be in localStorage")

    # Check sessionStorage
    session_dump = page.evaluate(
        "() => JSON.stringify(sessionStorage)")
    assert "PERSIST_CHECK" not in (session_dump or ""), (
        "Prompt should not be in sessionStorage")

    # Check all data attributes in the DOM
    data_attrs = page.evaluate("""
        () => {
            var all = document.querySelectorAll('*');
            var vals = [];
            for (var i = 0; i < all.length; i++) {
                var ds = all[i].dataset;
                for (var k in ds) { vals.push(ds[k]); }
            }
            return vals.join('|');
        }
    """)
    assert "PERSIST_CHECK" not in (data_attrs or ""), (
        "Prompt should not be in any DOM data attribute")

    page.unroute("**/loops/handoff-loop/prompt")


# ── live workspace prompt-copy race ──────────────────────────────────────


def test_live_workspace_inflight_copy_blocked_by_terminal(page, dashboard_fleet):
    """In-flight prompt copy from the live inspection workspace is
    discarded when the loop becomes terminal before the response arrives."""
    import json as _json

    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card", state="attached", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    # #56: the copy buttons sit inside the (closed) recovery disclosure.
    page.wait_for_selector(".loop-prompt-copy", state="attached", timeout=10000)

    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    page.evaluate("() => navigator.clipboard.writeText('SENTINEL')")

    # Gate the prompt response so we control when it arrives
    page.evaluate("""
        () => {
            window.__promptGate = new Promise(resolve => {
                window.__releasePrompt = resolve;
            });
        }
    """)

    active_loop_id = "active-loop-2026-09-22T10-00-00Z"

    def _delayed_prompt(route):
        page.evaluate("() => window.__promptGate")
        route.fulfill(
            status=200, content_type="application/json",
            headers={"Cache-Control": "no-store"},
            body=_json.dumps({"prompt": "SECRET_LIVE_TOKEN"}))

    page.route("**/" + active_loop_id + "/prompt", _delayed_prompt)

    # Click copy — request goes in flight
    page.evaluate("""
        () => document.querySelector('.loop-prompt-copy[data-role="draftor"]').click()
    """)
    page.wait_for_function(
        "() => {"
        "  var b = document.querySelector('.loop-prompt-copy[data-role=\"draftor\"]');"
        "  return b && b.textContent === 'Fetching…';"
        "}",
        timeout=5000)

    # While fetch is in flight, make the loop terminal via status poll
    page.route("**/" + active_loop_id + "/status", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=_json.dumps({
            "loop_id": active_loop_id, "feature": "widget-refactor",
            "status": {"stage": "plan_approved", "round": 2,
                       "max_rounds": 3, "next_role": None,
                       "blocked": False},
            "roles": {"draftor": {"role": "draftor", "joined": True},
                      "reviewer": {"role": "reviewer", "joined": True}},
            "decisions": [],
        })))

    # Wait for the view to re-render as terminal (outcome badge appears)
    page.wait_for_selector(".loop-badge-outcome", timeout=10000)

    # Release the prompt response
    page.evaluate("() => window.__releasePrompt()")
    page.wait_for_timeout(500)

    # No fallback textarea
    assert page.locator(".loop-handoff-fallback").count() == 0

    # Clipboard still has sentinel
    clip = page.evaluate("() => navigator.clipboard.readText()")
    assert "SECRET" not in (clip or ""), (
        f"Clipboard should not contain leaked prompt; got: {clip}")

    page.unroute("**/" + active_loop_id + "/prompt")
    page.unroute("**/" + active_loop_id + "/status")


def test_live_delayed_events_does_not_leak_prompt(page, dashboard_fleet):
    """Prompt released after terminal status but before delayed events
    response must not reach the clipboard. Covers the poll-sequence
    window where promptEpoch must be incremented before awaiting events."""
    import json as _json
    import threading

    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card", state="attached", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    # #56: the copy buttons sit inside the (closed) recovery disclosure.
    page.wait_for_selector(".loop-prompt-copy", state="attached", timeout=10000)

    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    page.evaluate("() => navigator.clipboard.writeText('SENTINEL')")

    active_loop_id = "active-loop-2026-09-22T10-00-00Z"

    # Gate the prompt response
    page.evaluate("""
        () => {
            window.__promptGate = new Promise(resolve => {
                window.__releasePrompt = resolve;
            });
        }
    """)

    def _delayed_prompt(route):
        page.evaluate("() => window.__promptGate")
        route.fulfill(
            status=200, content_type="application/json",
            headers={"Cache-Control": "no-store"},
            body=_json.dumps({"prompt": "SECRET_DELAYED_EVENTS"}))

    page.route("**/" + active_loop_id + "/prompt", _delayed_prompt)

    # Click copy — request goes in flight
    page.evaluate("""
        () => document.querySelector('.loop-prompt-copy[data-role="draftor"]').click()
    """)
    page.wait_for_function(
        "() => {"
        "  var b = document.querySelector('.loop-prompt-copy[data-role=\"draftor\"]');"
        "  return b && b.textContent === 'Fetching…';"
        "}",
        timeout=5000)

    # Make status terminal AND gate the events response so it delays
    page.route("**/" + active_loop_id + "/status", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=_json.dumps({
            "loop_id": active_loop_id, "feature": "widget-refactor",
            "status": {"stage": "ended_by_architect", "round": 2,
                       "max_rounds": 3, "next_role": None,
                       "blocked": False},
            "roles": {"draftor": {"role": "draftor", "joined": True},
                      "reviewer": {"role": "reviewer", "joined": True}},
            "decisions": [],
        })))

    events_gate = threading.Event()

    def _delayed_events(route):
        events_gate.wait(timeout=10)
        route.fulfill(
            status=200, content_type="application/json",
            body=_json.dumps({"events": [
                {"event": "loop_started", "ts": "2026-09-22T10:00:00Z",
                 "round": 0},
                {"event": "loop_ended_by_architect",
                 "ts": "2026-09-22T11:00:00Z", "reason": "done"},
            ]}))

    page.route("**/" + active_loop_id + "/events", _delayed_events)

    # Wait for status poll to pick up terminal — promptEpoch should
    # already be incremented even though events are still pending.
    # Give the poll cycle time to fire and fetch status.
    page.wait_for_timeout(4000)

    # Release the prompt while events are still held — the epoch
    # guard in copyPrompt must reject it.
    page.evaluate("() => window.__releasePrompt()")
    page.wait_for_timeout(500)

    # Now release events so the poll cycle completes
    events_gate.set()
    page.wait_for_timeout(1000)

    # Clipboard must still have sentinel
    clip = page.evaluate("() => navigator.clipboard.readText()")
    assert "SECRET" not in (clip or ""), (
        f"Clipboard should not contain leaked prompt; got: {clip}")

    page.unroute("**/" + active_loop_id + "/prompt")
    page.unroute("**/" + active_loop_id + "/status")
    page.unroute("**/" + active_loop_id + "/events")


# ── incremental rendering (#38) ────────────────────────────────────────────

_ACTIVE_ID = "active-loop-2026-09-22T10-00-00Z"
_BASE_EVENTS = [
    {"event": "loop_started", "ts": "2026-09-22T10:00:00Z", "round": 0},
    {"event": "draft_submitted", "ts": "2026-09-22T10:01:00Z", "round": 1,
     "role": "draftor", "artifact_path": "plan.round-1.md"},
    {"event": "revision_requested", "ts": "2026-09-22T10:02:00Z", "round": 2,
     "role": "reviewer", "artifact_path": "findings.round-1.md"},
]


def _live_payload():
    return {
        "status": {
            "loop_id": _ACTIVE_ID, "feature": "widget-refactor",
            "created_at": "2026-09-22T10:00:00+00:00",
            "status": {"stage": "plan_revision", "next_role": "draftor",
                       "round": 2, "max_rounds": 3, "blocked": False,
                       "turn_deadline": "2099-12-31T23:59:59+00:00",
                       "turn_timeout_seconds": 300,
                       "last_updated": "2026-09-22T10:02:00+00:00"},
            "roles": {"draftor": {"role": "draftor", "joined": True},
                      "reviewer": {"role": "reviewer", "joined": True}},
            "decisions": [],
        },
        "events": list(_BASE_EVENTS),
    }


def _serve_mutable_loop(page, payload):
    """Serve status/events from a dict the test mutates between polls."""
    import json as _json
    page.route("**/" + _ACTIVE_ID + "/status", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=_json.dumps(payload["status"])))
    page.route("**/" + _ACTIVE_ID + "/events", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=_json.dumps({"events": payload["events"]})))


def _unserve_mutable_loop(page):
    page.unroute("**/" + _ACTIVE_ID + "/status")
    page.unroute("**/" + _ACTIVE_ID + "/events")


def _open_incremental(page, dashboard_fleet, payload):
    _serve_mutable_loop(page, payload)
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_selector(".loop-artifact-section", timeout=10000)
    page.wait_for_selector(".loop-event", timeout=10000)
    # Timeline cards are link-only (no async fills); let the first render
    # settle so it is not counted as a poll mutation.
    page.wait_for_timeout(500)
    # Remember node identities and count ALL main-panel mutations: L1
    # removed the countdown, the last permitted per-poll write.
    page.evaluate("""() => {
        var q = s => document.querySelector(s);
        window.__nodes = {
            root: q('#loop-main-content .loop-detail'),
            header: q('#loop-region-header').firstElementChild,
            now: q('#loop-region-now').firstElementChild,
            controls: q('#loop-controls').firstElementChild,
            firstEvent: q('#loop-timeline').firstElementChild,
            sketch: q('.loop-artifact-section[data-artifact="sketch.md"]'),
        };
        window.__mutations = 0;
        window.__emptied = false;
        var main = q('#loop-main-content');
        new MutationObserver(function (records) {
            window.__mutations += records.length;
            if (!main.querySelector('.loop-detail')) window.__emptied = true;
        }).observe(main, {childList: true, subtree: true, characterData: true,
                          attributes: true});
    }""")


def _same(page, key):
    return page.evaluate(
        "k => { var n = window.__nodes[k]; return !!n && n.isConnected; }", key)


def _expand_sketch(page):
    page.evaluate("""() => document.querySelector(
        '.loop-artifact-section[data-artifact="sketch.md"] .loop-artifact-toggle').click()""")
    page.wait_for_function("""() => {
        var c = document.querySelector(
            '.loop-artifact-section[data-artifact="sketch.md"] .loop-artifact-content');
        return c && c.dataset.loaded === '1';
    }""", timeout=5000)
    # Baseline after the user's own expansion.
    page.evaluate("() => { window.__mutations = 0; }")


def _sketch_still_expanded(page):
    return page.evaluate("""() => {
        var sec = document.querySelector('.loop-artifact-section[data-artifact="sketch.md"]');
        var c = sec && sec.querySelector('.loop-artifact-content');
        return !!c && c.style.display === 'block'
            && c.textContent.indexOf('Widget Refactor Sketch') !== -1;
    }""")


def test_identical_polls_do_not_touch_main_panel(page, dashboard_fleet):
    payload = _live_payload()
    _open_incremental(page, dashboard_fleet, payload)
    page.evaluate("() => { window.__mutations = 0; }")
    page.wait_for_timeout(7000)  # >= two polls
    for key in ("root", "header", "now", "controls", "firstEvent", "sketch"):
        assert _same(page, key), f"{key} node was replaced by an identical poll"
    assert page.evaluate("() => window.__mutations") == 0
    assert page.evaluate("() => window.__emptied") is False
    _unserve_mutable_loop(page)


def test_workspace_region_order(page, dashboard_fleet):
    """L1: header (with controls) -> resolution -> source -> notices ->
    blocked alert -> Now -> rail/timeline -> lower evidence section."""
    payload = _live_payload()
    _open_incremental(page, dashboard_fleet, payload)
    order = ["#loop-region-header", "#loop-controls", "#loop-region-resolution",
             "#loop-region-source", "#loop-region-notice", "#loop-region-blocked",
             "#loop-region-now", "#loop-region-rail", "#loop-timeline",
             "#loop-artifacts", "#loop-region-prompts", "#loop-region-liveness",
             "#loop-region-decisions"]
    in_order = page.evaluate("""sels => {
        var els = sels.map(s => document.querySelector(s));
        if (els.some(e => !e)) return "missing";
        for (var i = 1; i < els.length; i++) {
            if (!(els[i - 1].compareDocumentPosition(els[i])
                  & Node.DOCUMENT_POSITION_FOLLOWING)) return sels[i];
        }
        return true;
    }""", order)
    assert in_order is True, in_order
    layout = page.evaluate("""() => ({
        controlsInHead: !!document.querySelector('.loop-head #loop-controls'),
        railShown: getComputedStyle(document.querySelector('#loop-region-rail')).display,
        candidateHidden: document.querySelector('#loop-candidate-details').hidden,
    })""")
    assert layout == {"controlsInHead": True, "railShown": "none",
                      "candidateHidden": True}
    _unserve_mutable_loop(page)


_CP_ITEMS = [{"id": "cp1", "index": 1, "title": "One", "state": "approved"},
             {"id": "cp2", "index": 2, "title": "Two", "state": "active",
              "findings_rounds": 1}]


def _now_case(payload, case):
    st = payload["status"]
    s = st["status"]
    if case == "blocked":
        s.update(stage="blocked_on_architect", next_role=None, blocked=True)
        st["decisions"] = [{"id": "decision-2", "request": {
            "reason": "Scope?", "role": "reviewer", "artifact_path": None,
            "ts": "2026-09-22T10:03:00+00:00"}, "response": None}]
    elif case == "paused":
        s.update(stage="paused_by_architect", next_role=None, blocked=True)
    elif case in ("checkpoint", "approved"):
        st["mode"] = "coding"
        st["coding"] = {"source_loop_id": "src", "generations": [],
                        "checkpoints": {"items": _CP_ITEMS, "current": 1,
                                        "count": 2}}
        s.update(stage="implementation_review" if case == "checkpoint"
                 else "implementation_approved", next_role="reviewer")
    elif case == "max_rounds":
        s.update(stage="max_rounds_exceeded", next_role=None)
    elif case == "ended":
        s.update(stage="ended_by_architect", next_role=None)


@pytest.mark.parametrize("case,state,glyph,text", [
    ("planning", "active", "\u25b6",
     "Now: Draftor \u2014 Revision (round 2 of 3). No action needed from you."),
    ("checkpoint", "active", "\u25b6",
     "Now: Reviewer \u2014 Code Review (checkpoint 2 of 2). No action needed from you."),
    ("blocked", "blocked", "\u2691",
     "Now: your decision is required \u2014 Reviewer escalated decision-2. "
     "Use Respond above."),
    ("paused", "paused", "\u23f8",
     "Now: paused by you. No participant is working; Resume or End when ready."),
    ("approved", "approved", "\u2713",
     "Now: implementation approved \u2014 the Draftor makes one normal commit. "
     "The commit state is shown above."),
    ("max_rounds", "max_rounds", "\u25a0",
     "Now: maximum rounds reached. Continue loop to add rounds, or leave it ended."),
    ("ended", "terminal", "\u25a0", "Outcome: Ended by Architect."),
])
def test_now_line_state_matrix(page, dashboard_fleet, case, state, glyph, text):
    """The Now line is status-derived: glyph + words per state (colour is a
    second cue only), and it never shows time."""
    payload = _live_payload()
    _now_case(payload, case)
    try:
        _open_incremental(page, dashboard_fleet, payload)
        now = page.evaluate("""() => {
            var p = document.querySelector('#loop-region-now .loop-now');
            return {state: p.dataset.state,
                    glyph: p.querySelector('.loop-now-glyph').textContent,
                    text: p.querySelector('.loop-now-text').textContent};
        }""")
        assert now == {"state": state, "glyph": glyph, "text": text}
    finally:
        _unserve_mutable_loop(page)


_TL_SHAPE = """() => Array.from(document.querySelectorAll(
    '#loop-timeline > .loop-tl-group')).map(g => [g.dataset.group,
    g.querySelector('.loop-tl-group-label').textContent,
    Array.from(g.querySelectorAll('.loop-event')).map(
        e => e.querySelector('.loop-event-label').textContent)])"""


def test_timeline_newest_first_grouped(page, dashboard_fleet):
    """L1: planning events group by round, newest group and card first;
    cards stay link-only."""
    payload = _live_payload()
    payload["events"].append(
        {"event": "draft_submitted", "ts": "2026-09-22T10:03:00Z", "round": 2,
         "role": "draftor", "artifact_path": "plan.round-2.md"})
    _open_incremental(page, dashboard_fleet, payload)
    assert page.evaluate(_TL_SHAPE) == [
        ["r:2", "Round 2", ["Draft submitted", "Revision requested"]],
        ["r:1", "Round 1", ["Draft submitted"]],
        ["r:0", "Round 0", ["Loop started"]],
    ]
    first = page.evaluate("""() => {
        var c = document.querySelector('#loop-timeline .loop-event');
        return [c.dataset.artifact,
                c.querySelectorAll('.loop-timeline-artifact-link').length];
    }""")
    assert first == ["plan.round-2.md", 1]
    _unserve_mutable_loop(page)


def test_new_event_patches_front_only(page, dashboard_fleet):
    """A new event of the front group is inserted first in that group; a
    new group is inserted first in the timeline; existing nodes survive."""
    payload = _live_payload()
    _open_incremental(page, dashboard_fleet, payload)
    page.evaluate("""() => {
        window.__tl = Array.from(document.querySelectorAll(
            '#loop-timeline .loop-tl-group, #loop-timeline .loop-event'));
    }""")
    payload["events"].append(
        {"event": "draft_submitted", "ts": "2026-09-22T10:03:00Z", "round": 2,
         "role": "draftor", "artifact_path": "plan.round-2.md"})
    page.wait_for_function(
        "() => document.querySelectorAll('#loop-timeline .loop-event').length === 4",
        timeout=8000)
    same = page.evaluate("""() => {
        var front = document.querySelector('#loop-timeline .loop-tl-group');
        return {kept: window.__tl.every(n => n.isConnected),
                frontKept: window.__tl.indexOf(front) !== -1,
                newFirst: front.querySelector('.loop-event').dataset.artifact};
    }""")
    assert same == {"kept": True, "frontKept": True, "newFirst": "plan.round-2.md"}

    payload["events"].append(
        {"event": "review_submitted", "ts": "2026-09-22T10:04:00Z", "round": 3,
         "role": "reviewer"})
    page.wait_for_function(
        "() => document.querySelectorAll('#loop-timeline .loop-event').length === 5",
        timeout=8000)
    shape = page.evaluate(_TL_SHAPE)
    assert [g[0] for g in shape] == ["r:3", "r:2", "r:1", "r:0"]
    assert page.evaluate("() => window.__tl.every(n => n.isConnected)")
    _unserve_mutable_loop(page)


_CP_SEQUENCE = [
    {"event": "loop_started", "ts": "2026-09-22T10:00:00Z", "round": 0},
    {"event": "implementation_submitted", "ts": "2026-09-22T10:01:00Z",
     "round": 0, "role": "draftor", "generation": 0, "checkpoint_id": "cp1",
     "artifact_path": "implementation.round-0.md"},
    {"event": "loop_paused", "ts": "2026-09-22T10:02:00Z", "round": 1,
     "reason": "Hold."},
    {"event": "loop_unblocked", "ts": "2026-09-22T10:03:00Z", "round": 1},
    {"event": "checkpoint_approved", "ts": "2026-09-22T10:04:00Z", "round": 0,
     "role": "reviewer", "generation": 0, "checkpoint_id": "cp1",
     "artifact_path": "findings.round-0.md"},
    {"event": "implementation_submitted", "ts": "2026-09-22T10:05:00Z",
     "round": 0, "role": "draftor", "generation": 1, "checkpoint_id": "cp2",
     "artifact_path": "implementation.round-1.md"},
]


def test_checkpoint_grouping_inherits_untagged_events(page, dashboard_fleet):
    """Declared-checkpoint history: untagged events that carry a round stay
    in the checkpoint they happened in (no Round group). The whole render
    and a one-event-per-poll patch give identical groups and order."""
    expected_groups = ["cp:cp2", "cp:cp1", "start"]

    payload = _live_payload()
    _now_case(payload, "checkpoint")
    payload["events"] = list(_CP_SEQUENCE)
    _open_incremental(page, dashboard_fleet, payload)
    whole = page.evaluate(_TL_SHAPE)
    _unserve_mutable_loop(page)
    assert [g[0] for g in whole] == expected_groups
    assert len(whole[1][2]) == 4  # submitted, paused, unblocked, approved
    assert not any(g[0].startswith("r:") for g in whole)

    page.goto("about:blank")
    payload = _live_payload()
    _now_case(payload, "checkpoint")
    payload["events"] = _CP_SEQUENCE[:1]
    _open_incremental(page, dashboard_fleet, payload)
    for n in range(2, len(_CP_SEQUENCE) + 1):
        payload["events"] = _CP_SEQUENCE[:n]
        page.wait_for_function(
            "n => document.querySelectorAll('#loop-timeline .loop-event').length === n",
            arg=n, timeout=8000)
    assert page.evaluate(_TL_SHAPE) == whole
    _unserve_mutable_loop(page)


def test_status_change_patches_header_preserves_artifacts_and_timeline(page, dashboard_fleet):
    payload = _live_payload()
    _open_incremental(page, dashboard_fleet, payload)
    _expand_sketch(page)

    st = payload["status"]["status"]
    st.update({"stage": "plan_review", "next_role": "reviewer",
               "last_updated": "2026-09-22T10:05:00+00:00"})
    # L1: the stage badge (header) and the Now line both follow the change.
    page.wait_for_function("""() => {
        var h = document.querySelector('#loop-region-header .loop-badge');
        return h && h.textContent === 'Review';
    }""", timeout=8000)

    assert _same(page, "root")
    assert not _same(page, "header"), "header should be re-rendered on a status change"
    assert not _same(page, "now"), "Now line should follow the stage change"
    assert "Now: Reviewer" in page.evaluate(
        "() => document.querySelector('.loop-now-text').textContent")
    assert _same(page, "firstEvent"), "timeline must be preserved on a status-only change"
    assert _same(page, "sketch")
    assert _sketch_still_expanded(page)
    assert page.evaluate("() => window.__emptied") is False
    _unserve_mutable_loop(page)


def test_new_events_append_and_preserve_artifact_expansion(page, dashboard_fleet):
    payload = _live_payload()
    _open_incremental(page, dashboard_fleet, payload)
    _expand_sketch(page)
    before = page.evaluate("() => document.querySelectorAll('#loop-timeline .loop-event').length")

    payload["events"].append(
        {"event": "draft_submitted", "ts": "2026-09-22T10:06:00Z", "round": 2,
         "role": "draftor", "artifact_path": "plan.round-2.md"})
    page.wait_for_selector(
        '.loop-artifact-section[data-artifact="plan.round-2.md"]', timeout=8000)

    after = page.evaluate("() => document.querySelectorAll('#loop-timeline .loop-event').length")
    assert after == before + 1
    assert _same(page, "firstEvent"), "existing timeline cards must not be rebuilt"
    assert _same(page, "sketch")
    assert _sketch_still_expanded(page)
    # New artifact appended after the existing ones.
    names = page.evaluate("""() => Array.from(document.querySelectorAll(
        '#loop-artifacts > .loop-artifact-section')).map(s => s.dataset.artifact)""")
    assert names[-1] == "plan.round-2.md"
    # L1: the plan row comes first.
    assert names[:3] == ["plan.current.md", "sketch.md", "findings.current.md"]
    _unserve_mutable_loop(page)


def test_composed_control_survives_unrelated_status_change(page, dashboard_fleet):
    """No 'skip while composing' rule: controls simply aren't touched."""
    payload = _live_payload()
    _open_incremental(page, dashboard_fleet, payload)
    page.evaluate("() => document.querySelector('.loop-ctrl-interject').click()")
    page.wait_for_selector(".loop-ctrl-input-area", timeout=5000)
    page.fill(".loop-ctrl-input", "half-typed guidance")

    payload["status"]["status"]["last_updated"] = "2026-09-22T10:07:00+00:00"
    payload["events"].append(
        {"event": "architect_interjection", "ts": "2026-09-22T10:07:00Z",
         "round": 2, "detail": "earlier note"})
    page.wait_for_function(
        "() => document.querySelectorAll('#loop-timeline .loop-event').length === 4",
        timeout=8000)

    assert page.evaluate("() => document.querySelector('.loop-ctrl-input').value") \
        == "half-typed guidance"
    # L1: the Interject dialog is still open over the unchanged controls.
    assert page.evaluate(
        "() => document.querySelector('dialog.loop-dialog[data-kind=\"interject\"]').open")
    _unserve_mutable_loop(page)


def test_stale_mutable_artifact_response_cannot_overwrite_newer(page, dashboard_fleet):
    """An older plan.current.md response that resolves after a newer one
    must not overwrite the refreshed expanded body (#45: collapsed cards no
    longer fetch an excerpt, so only the body fetch is held)."""
    old_text = "# Plan v1\n\n## Executive Summary\n\nOLD-SUMMARY\n\n## Body\n\nOLD-BODY\n"
    new_text = "# Plan v2\n\n## Executive Summary\n\nNEW-SUMMARY\n\n## Body\n\nNEW-BODY\n"
    held = []
    mode = {"hold": True}

    def _plan(route):
        if mode["hold"]:
            held.append(route)          # fulfilled later from the test thread
        else:
            route.fulfill(status=200, content_type="text/plain; charset=utf-8",
                          body=new_text)

    payload = _live_payload()
    _serve_mutable_loop(page, payload)
    page.route("**/" + _ACTIVE_ID + "/artifact/plan.current.md", _plan)

    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    sel = '.loop-artifact-section[data-artifact="plan.current.md"]'
    page.wait_for_selector(sel, timeout=10000)
    # Expand: the body fetch is held too.
    page.evaluate("s => document.querySelector(s + ' .loop-artifact-toggle').click()", sel)
    for _ in range(50):                 # held routes accumulate on this thread
        if len(held) >= 1:
            break
        page.wait_for_timeout(100)
    page.wait_for_timeout(300)
    assert len(held) == 1, f"expected exactly the held body fetch, got {len(held)}"

    # A newer submission lands; refresh fetches are served NEW immediately.
    mode["hold"] = False
    payload["events"].append(
        {"event": "draft_submitted", "ts": "2026-09-22T10:06:00Z", "round": 2,
         "role": "draftor", "artifact_path": "plan.round-2.md"})
    page.wait_for_function("""s => {
        var sec = document.querySelector(s);
        var c = sec && sec.querySelector('.loop-artifact-content');
        return c && c.textContent.indexOf('NEW-SUMMARY') !== -1
            && c.textContent.indexOf('NEW-BODY') !== -1;
    }""", arg=sel, timeout=8000)

    # Now the stale responses arrive.
    for route in held:
        route.fulfill(status=200, content_type="text/plain; charset=utf-8", body=old_text)
    page.wait_for_timeout(800)

    body = page.evaluate(
        "s => document.querySelector(s + ' .loop-artifact-content').textContent", sel)
    assert "NEW-SUMMARY" in body and "OLD-SUMMARY" not in body
    assert "NEW-BODY" in body and "OLD-BODY" not in body

    page.unroute("**/" + _ACTIVE_ID + "/artifact/plan.current.md")
    _unserve_mutable_loop(page)


def _view_under_history(page):
    """Keep the inspected loop in the main pane but select the History tab.
    A loop that ends under the Primary tab leaves it (it becomes Create);
    the in-place terminal patch and its polling stop apply under History."""
    page.evaluate("() => document.querySelector('#loop-tab-history').click()")
    assert _tab_state(page)["history"]["selected"] == "true"


def test_terminal_transition_patches_in_place_and_stops_polling(page, dashboard_fleet):
    payload = _live_payload()
    _open_incremental(page, dashboard_fleet, payload)
    _view_under_history(page)
    _expand_sketch(page)

    payload["status"]["status"].update(
        {"stage": "plan_approved", "next_role": None,
         "last_updated": "2026-09-22T10:09:00+00:00"})
    payload["events"].append(
        {"event": "plan_approved", "ts": "2026-09-22T10:09:00Z", "round": 2,
         "artifact_path": "findings.round-2.md"})
    page.wait_for_selector(".loop-badge-outcome", timeout=8000)

    assert _same(page, "root"), "terminal transition must patch, not replace, the panel"
    assert page.evaluate("() => window.__emptied") is False
    assert page.locator(".loop-ctrl-btn").count() == 0
    assert page.locator(".loop-prompt-copy").count() == 0
    assert _sketch_still_expanded(page)
    page.wait_for_function(
        "() => document.querySelector('.loop-workspace').dataset.polling === '0'",
        timeout=5000)
    _unserve_mutable_loop(page)


# ── continue after max rounds (#39 M6) ──────────────────────────────────────

def _max_rounds_payload():
    payload = _live_payload()
    payload["status"]["status"].update({
        "stage": "max_rounds_exceeded", "next_role": None, "round": 3,
        "max_rounds": 3, "blocked": True, "turn_deadline": None,
        "last_updated": "2026-09-22T10:04:00+00:00"})
    # artifact_path must exist in the seed fixture: _open_incremental()
    # waits for every timeline card's executive-summary fetch to settle.
    payload["events"].append(
        {"event": "max_rounds_exceeded", "ts": "2026-09-22T10:04:00Z", "round": 3,
         "role": "reviewer", "artifact_path": "findings.round-1.md"})
    return payload


def _route_extend(page, payload, rounds_added=None, watcher="attached", detail=None):
    """Mock POST /extend: record the body and make the served loop live."""
    import json as _json
    posts = []

    def _extend(route):
        body = _json.loads(route.request.post_data or "{}")
        posts.append(body)
        st = payload["status"]["status"]
        prev = st["max_rounds"]
        new = prev + (rounds_added or body["rounds"])
        st.update({"stage": "plan_revision", "next_role": "draftor", "blocked": False,
                   "max_rounds": new, "turn_deadline": "2099-12-31T23:59:59+00:00",
                   "last_updated": "2026-09-22T10:10:00+00:00"})
        payload["events"].append(
            {"event": "loop_extended", "ts": "2026-09-22T10:10:00Z", "round": st["round"],
             "role": "architect", "detail": f"Extended: {prev} -> {new}"})
        route.fulfill(status=200, content_type="application/json", body=_json.dumps({
            "ok": True, "previous_max_rounds": prev, "max_rounds": new,
            "round": st["round"], "watcher": watcher, "watcher_detail": detail}))

    page.route("**/" + _ACTIVE_ID + "/extend", _extend)
    return posts


@pytest.mark.parametrize("stage,visible", [
    ("max_rounds_exceeded", True),
    ("plan_approved", False),
    ("turn_timed_out", False),
    ("ended_by_architect", False),
])
def test_continue_control_only_for_max_rounds(page, dashboard_fleet, stage, visible):
    payload = _max_rounds_payload()
    payload["status"]["status"]["stage"] = stage
    _open_incremental(page, dashboard_fleet, payload)
    page.wait_for_selector(".loop-badge-outcome", timeout=8000)
    assert (page.locator(".loop-ctrl-continue").count() == 1) is visible
    if not visible:
        assert page.locator(".loop-ctrl-btn").count() == 0
    _unserve_mutable_loop(page)


def test_continue_validation_sends_nothing_until_valid(page, dashboard_fleet):
    payload = _max_rounds_payload()
    posts = _route_extend(page, payload)
    _open_incremental(page, dashboard_fleet, payload)
    page.evaluate("() => document.querySelector('.loop-ctrl-continue').click()")
    page.wait_for_selector(".loop-continue-area", state="visible", timeout=5000)

    assert page.evaluate("() => document.querySelector('.loop-continue-area .loop-ctrl-confirm').disabled")
    # Forced click with a blank reason is refused client-side.
    page.evaluate("""() => { var b = document.querySelector('.loop-continue-area .loop-ctrl-confirm');
                             b.disabled = false; b.click(); }""")
    page.wait_for_selector(".loop-ctrl-error", timeout=5000)
    assert "reason is required" in page.inner_text(".loop-ctrl-error")

    page.fill(".loop-continue-reason", "go on")
    for bad in ("0", "21", "2.5"):
        page.fill(".loop-continue-rounds", bad)
        page.evaluate("() => document.querySelector('.loop-continue-area .loop-ctrl-confirm').click()")
        page.wait_for_timeout(200)
        assert "between 1 and 20" in page.inner_text(".loop-ctrl-error")
    assert posts == []
    page.unroute("**/" + _ACTIVE_ID + "/extend")
    _unserve_mutable_loop(page)


def test_continue_success_goes_live_in_place(page, dashboard_fleet):
    payload = _max_rounds_payload()
    posts = _route_extend(page, payload)
    _open_incremental(page, dashboard_fleet, payload)
    _view_under_history(page)
    page.wait_for_function(
        "() => document.querySelector('.loop-workspace').dataset.polling === '0'", timeout=8000)
    _expand_sketch(page)
    events_before = page.evaluate("() => document.querySelectorAll('#loop-timeline .loop-event').length")

    page.evaluate("() => document.querySelector('.loop-ctrl-continue').click()")
    page.fill(".loop-continue-rounds", "3")
    page.fill(".loop-continue-reason", "Verify the revised boundary behavior.")
    page.evaluate("() => document.querySelector('.loop-continue-area .loop-ctrl-confirm').click()")

    page.wait_for_selector(".loop-ctrl-pause", timeout=8000)
    assert posts == [{"rounds": 3, "message": "Verify the revised boundary behavior."}]
    notice = page.inner_text("#loop-region-notice")
    assert "Extended: max rounds 3 → 6" in notice and "re-engage" in notice
    assert "Warning" not in notice

    # Live again, patched in place (#38): same root, prompts back, polling on.
    assert _same(page, "root")
    assert page.evaluate("() => window.__emptied") is False
    assert page.locator(".loop-prompt-copy").count() == 2
    assert page.locator(".loop-badge-outcome").count() == 0
    assert page.evaluate("() => document.querySelector('.loop-workspace').dataset.polling") == "1"
    assert _sketch_still_expanded(page)
    page.wait_for_function(
        f"() => document.querySelectorAll('#loop-timeline .loop-event').length === {events_before + 1}",
        timeout=8000)
    # L1: newest first -- the Extended card leads the timeline.
    assert "Extended" in page.evaluate(
        "() => document.querySelector('#loop-timeline .loop-event').textContent")
    assert _same(page, "firstEvent")

    # The notice survives subsequent polls (unpatched region).
    page.wait_for_timeout(3500)
    assert "Extended: max rounds 3 → 6" in page.inner_text("#loop-region-notice")
    page.unroute("**/" + _ACTIVE_ID + "/extend")
    _unserve_mutable_loop(page)


def test_continue_reports_watcher_failure_as_text_warning(page, dashboard_fleet):
    payload = _max_rounds_payload()
    _route_extend(page, payload, watcher="failed", detail="open failed: denied")
    _open_incremental(page, dashboard_fleet, payload)
    page.evaluate("() => document.querySelector('.loop-ctrl-continue').click()")
    page.fill(".loop-continue-reason", "continue")
    page.evaluate("() => document.querySelector('.loop-continue-area .loop-ctrl-confirm').click()")
    page.wait_for_selector(".loop-extend-warning", timeout=8000)
    warning = page.inner_text(".loop-extend-warning")
    assert "Warning:" in warning
    assert "not being enforced" in warning and "open failed: denied" in warning
    page.unroute("**/" + _ACTIVE_ID + "/extend")
    _unserve_mutable_loop(page)


def test_continue_server_error_keeps_dialog_for_retry(page, dashboard_fleet):
    import json as _json
    payload = _max_rounds_payload()
    page.route("**/" + _ACTIVE_ID + "/extend", lambda route: route.fulfill(
        status=409, content_type="application/json",
        body=_json.dumps({"error": "An active loop already exists: other-loop"})))
    _open_incremental(page, dashboard_fleet, payload)
    page.evaluate("() => document.querySelector('.loop-ctrl-continue').click()")
    page.fill(".loop-continue-reason", "continue")
    page.evaluate("() => document.querySelector('.loop-continue-area .loop-ctrl-confirm').click()")
    page.wait_for_selector(".loop-ctrl-error", timeout=8000)
    assert "active loop already exists" in page.inner_text(".loop-ctrl-error")
    assert page.evaluate(
        "() => document.querySelector('.loop-continue-area').style.display") == "flex"
    assert page.locator(".loop-badge-outcome").count() == 1
    page.unroute("**/" + _ACTIVE_ID + "/extend")
    _unserve_mutable_loop(page)


# ── #53: Architect workspace for suspension ──────────────────────────────────


def test_blocked_card_shows_request_from_real_fields(page, dashboard_fleet):
    """The blocked card renders from the pending decision (role, time, full
    multi-line reason, request link) and the preserved resume pair."""
    _open_sole_active(page, dashboard_fleet, "blocked-feature")
    page.wait_for_selector(".loop-decision-card", timeout=10000)
    _open_decision_dialog(page)
    card = page.evaluate("""() => {
        var c = document.querySelector('.loop-decision-card');
        var r = document.querySelector('dialog.loop-dialog .loop-blocked-reason');
        return {kind: c.dataset.kind,
                title: c.querySelector('.loop-blocked-title').textContent,
                text: c.textContent,
                reason: r.textContent,
                ws: getComputedStyle(r).whiteSpace};
    }""")
    assert card["kind"] == "architect_decision"
    assert "Blocked" in card["title"]
    assert "awaiting your decision" in card["title"]
    assert "decision-2" in card["text"]
    assert "requested by Reviewer" in card["text"]
    assert card["reason"] == ("Needs Architect input on scope:\n"
                              "resource allocation for the parser work.")
    assert card["ws"] == "pre-wrap"
    assert "Resumes: Reviewer \u00b7 plan_review" in card["text"]
    assert "Architect hold" not in card["text"]
    assert page.locator(".loop-hold-card").count() == 0


def test_decisions_disclosure(page, dashboard_fleet):
    """L1: decision history is a collapsed, skeleton-owned disclosure with a
    count; hidden with no decisions; a manual expansion survives identical
    polls; durable text, labels and artifact links stay inside it."""
    # No decisions: the disclosure is hidden (no empty row).
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_selector("#loop-decisions-details", state="attached", timeout=10000)
    assert page.evaluate(
        "() => document.querySelector('#loop-decisions-details').hidden") is True

    answered = {
        "id": "decision-0",
        "request": {"reason": "Which parser?", "role": "reviewer",
                    "artifact_path": "decision-request.decision-0.round-0.md",
                    "round": 0, "ts": "2026-09-22T09:00:00+00:00"},
        "response": {"message": "Use the fast one.", "kind": "message",
                     "artifact_path": None, "ts": "2026-09-22T09:30:00+00:00"},
    }
    _route_paused_status(page, "blocked_on_architect", pending_decision=True,
                         extra_decisions=[answered])
    # The live loop's next poll (3 s) picks up the routed blocked status.
    page.wait_for_function("""() => {
        var d = document.querySelector('#loop-decisions-details');
        return d && !d.hidden;
    }""", timeout=10000)
    head = page.evaluate("""() => {
        var d = document.querySelector('#loop-decisions-details');
        return {open: d.open, summary: d.querySelector('summary').textContent};
    }""")
    assert head == {"open": False, "summary": "Decisions (2)"}

    page.evaluate("() => document.querySelector('#loop-decisions-details > summary').click()")
    page.wait_for_selector(".loop-decision-item", timeout=5000)
    text = page.evaluate(
        "() => document.querySelector('#loop-region-decisions').textContent")
    assert "Which parser?" in text and "Need scope decision" in text
    assert "Answered" in text and "Use the fast one." in text
    assert "Pending" in text

    page.evaluate("""() => {
        window._dm = 0;
        new MutationObserver(r => { window._dm += r.length; }).observe(
            document.querySelector('#loop-decisions-details'),
            {subtree: true, childList: true, characterData: true, attributes: true});
    }""")
    page.wait_for_timeout(7000)  # >= two identical polls
    assert page.evaluate("() => window._dm") == 0
    assert page.evaluate(
        "() => document.querySelector('#loop-decisions-details').open") is True

    page.evaluate("() => document.querySelector('.loop-decision-artifact-link').click()")
    page.wait_for_function("""() => {
        var c = document.querySelector('.loop-artifact-section[data-artifact='
            + '"decision-request.decision-0.round-0.md"] .loop-artifact-content');
        return c && c.style.display === 'block';
    }""", timeout=5000)
    page.unroute("**/loops/*/status")


@pytest.mark.parametrize("viewport", [(1440, 900), (375, 700)])
def test_loop_dialog_is_centred(page, dashboard_fleet, viewport):
    """The modal dialog is centred in the viewport (the global margin reset
    used to pin it top-left) and fits inside it."""
    page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
    _open_sole_active(page, dashboard_fleet, "blocked-feature")
    _open_decision_dialog(page)
    box = page.evaluate("""() => {
        const r = document.querySelector('dialog.loop-dialog').getBoundingClientRect();
        return {left: r.left, right: innerWidth - r.right,
                top: r.top, bottom: innerHeight - r.bottom};
    }""")
    assert min(box.values()) >= 0, box
    assert abs(box["left"] - box["right"]) <= 1, box
    assert abs(box["top"] - box["bottom"]) <= 1, box


def test_decision_dialog_flow(page, dashboard_fleet):
    """L1: the compact alert's Respond opens one focused dialog holding the
    full request and its link. Escape sends nothing and returns focus; a
    blank response is refused; a valid one posts unblock exactly once."""
    import json as _json
    posts = []
    page.route("**/loops/*/unblock",
               lambda route: (posts.append(route.request.post_data), route.fulfill(
                   status=200, content_type="application/json",
                   body='{"ok": true}')))
    _open_sole_active(page, dashboard_fleet, "blocked-feature")
    _open_decision_dialog(page)
    dlg = page.evaluate("""() => {
        var d = document.querySelector('dialog.loop-dialog');
        return {modal: d.matches(':modal'),
                title: d.querySelector('.loop-dialog-title').textContent,
                reason: d.querySelector('.loop-blocked-reason').textContent,
                link: !!d.querySelector('.loop-blocked-artifact-link'),
                label: d.querySelector('.loop-ctrl-label').textContent,
                focus: document.activeElement === d.querySelector('.loop-ctrl-input'),
                disabled: d.querySelector('.loop-ctrl-confirm').disabled,
                endInstead: !!d.querySelector('.loop-dialog-end-instead')};
    }""")
    assert dlg["modal"] and dlg["link"] and dlg["focus"] and dlg["disabled"]
    assert dlg["endInstead"]
    assert "Decision requested by Reviewer (decision-2)" == dlg["title"]
    assert "scope" in dlg["reason"].lower()
    assert dlg["label"] == "Response to Reviewer (required)"

    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.querySelector('dialog.loop-dialog')",
                           timeout=5000)
    assert page.evaluate("() => document.activeElement.classList"
                         ".contains('loop-blocked-respond')")
    assert posts == []

    _open_decision_dialog(page)
    page.fill(".loop-ctrl-input", "   ")
    page.evaluate("""() => { var b = document.querySelector('.loop-ctrl-confirm');
        b.disabled = false; b.click(); }""")
    page.wait_for_selector("dialog.loop-dialog .loop-ctrl-error", timeout=5000)
    assert posts == []
    page.fill(".loop-ctrl-input", "Narrow it to the parser.")
    page.evaluate("() => document.querySelector('.loop-ctrl-confirm').click()")
    page.wait_for_function("() => !document.querySelector('dialog.loop-dialog')",
                           timeout=5000)
    assert len(posts) == 1
    assert _json.loads(posts[0])["message"] == "Narrow it to the parser."
    page.unroute("**/loops/*/unblock")


@pytest.mark.parametrize("action,consequence,confirm", [
    ("pause", "no participant acts until you resume it", "Pause loop"),
    ("end", "it cannot be resumed", "End loop"),
])
def test_pause_end_confirm(page, dashboard_fleet, action, consequence, confirm):
    """L1: Pause and End are quiet header controls that open a small
    confirmation stating the consequence; Cancel sends nothing; Confirm
    posts once."""
    import json as _json
    posts = []
    page.route("**/" + _ACTIVE_ID + "/" + action,
               lambda route: (posts.append(route.request.post_data), route.fulfill(
                   status=200, content_type="application/json",
                   body='{"ok": true}')))
    payload = _live_payload()
    _open_incremental(page, dashboard_fleet, payload)
    sel = ".loop-ctrl-" + action
    assert page.evaluate(f"() => document.querySelector('{sel}')"
                         ".classList.contains('loop-ctrl-quiet')")
    page.evaluate(f"() => document.querySelector('{sel}').click()")
    page.wait_for_selector(f'dialog.loop-dialog[data-kind="{action}"][open]', timeout=5000)
    text = page.evaluate("() => document.querySelector('dialog.loop-dialog').textContent")
    assert consequence in text
    assert page.evaluate("() => document.querySelector('.loop-ctrl-confirm')"
                         ".textContent") == confirm
    page.evaluate("() => document.querySelector('.loop-ctrl-cancel').click()")
    page.wait_for_function("() => !document.querySelector('dialog.loop-dialog')",
                           timeout=5000)
    assert posts == []

    page.evaluate(f"() => document.querySelector('{sel}').click()")
    page.wait_for_selector(f'dialog.loop-dialog[data-kind="{action}"][open]', timeout=5000)
    page.fill(".loop-ctrl-input", "Done for today.")
    page.evaluate("() => document.querySelector('.loop-ctrl-confirm').click()")
    page.wait_for_function("() => !document.querySelector('dialog.loop-dialog')",
                           timeout=5000)
    assert len(posts) == 1
    key = "reason" if action == "end" else "message"
    assert _json.loads(posts[0]) == {key: "Done for today."}
    page.unroute("**/" + _ACTIVE_ID + "/" + action)
    _unserve_mutable_loop(page)


def test_context_change_closes_dialog(page, dashboard_fleet):
    """L1: a change of control context while a dialog is open closes it
    without sending and says so."""
    posts = []
    page.route("**/" + _ACTIVE_ID + "/interject",
               lambda route: (posts.append(route.request.post_data), route.fulfill(
                   status=200, content_type="application/json", body='{"ok": true}')))
    payload = _live_payload()
    _open_incremental(page, dashboard_fleet, payload)
    page.evaluate("() => document.querySelector('.loop-ctrl-interject').click()")
    page.wait_for_selector('dialog.loop-dialog[data-kind="interject"][open]', timeout=5000)
    page.fill(".loop-ctrl-input", "half-typed guidance")

    payload["status"]["status"].update(stage="paused_by_architect", next_role=None,
                                       blocked=True)
    page.wait_for_function("() => !document.querySelector('dialog.loop-dialog')",
                           timeout=8000)
    notice = page.evaluate("""() => document.querySelector(
        '#loop-region-notice [data-slot="action"]').textContent""")
    assert "nothing was sent" in notice
    assert posts == []
    assert page.locator(".loop-ctrl-unblock").count() == 1
    # Keyboard focus lands on a concrete, current control, never the body.
    assert page.evaluate("""() => {
        var a = document.activeElement;
        return a !== document.body && a.isConnected
            && a.matches('#loop-controls .loop-ctrl-unblock');
    }""")
    page.unroute("**/" + _ACTIVE_ID + "/interject")
    _unserve_mutable_loop(page)


def test_pending_request_allows_one_send(page, dashboard_fleet):
    """While a dialog action is in flight, dismissing or reopening cannot
    start a second request; settling restores usable controls, a failure
    is reported, and a retry then sends exactly one more request."""
    held = []
    page.route("**/" + _ACTIVE_ID + "/interject", lambda route: held.append(route))
    payload = _live_payload()
    _open_incremental(page, dashboard_fleet, payload)
    page.click(".loop-ctrl-interject")
    page.wait_for_selector('dialog.loop-dialog[data-kind="interject"][open]', timeout=5000)
    page.fill(".loop-ctrl-input", "Check the parser.")
    page.click("dialog.loop-dialog .loop-ctrl-confirm")
    for _ in range(50):
        if held:
            break
        page.wait_for_timeout(100)
    assert len(held) == 1
    state = page.evaluate("""() => {
        var d = document.querySelector('dialog.loop-dialog');
        return {confirm: d.querySelector('.loop-ctrl-confirm').textContent,
                cancel: d.querySelector('.loop-ctrl-cancel').disabled,
                header: document.querySelector('.loop-ctrl-interject').disabled};
    }""")
    assert state == {"confirm": "Sending\u2026", "cancel": True, "header": True}

    # Escape cannot dismiss a sending dialog; even a forced reopen of the
    # control is refused while the first request is outstanding.
    page.keyboard.press("Escape")
    page.evaluate("""() => { var b = document.querySelector('.loop-ctrl-interject');
        b.disabled = false; b.click(); }""")
    page.wait_for_timeout(500)
    assert len(held) == 1
    assert page.evaluate("""() => Array.from(document.querySelectorAll(
        'dialog.loop-dialog')).every(d => d.dataset.sending === '1')""")
    assert "still being sent" in page.evaluate("""() => document.querySelector(
        '#loop-region-notice [data-slot="action"]').textContent""")

    held[0].fulfill(status=500, content_type="application/json",
                    body='{"error": "boom"}')
    page.wait_for_function("""() => {
        var b = document.querySelector('.loop-ctrl-interject');
        return b && !b.disabled;
    }""", timeout=5000)
    reported = page.evaluate("""() => {
        var d = document.querySelector('dialog.loop-dialog');
        if (d) return d.querySelector('.loop-ctrl-error').textContent;
        return document.querySelector(
            '#loop-region-notice [data-slot="action"]').textContent;
    }""")
    assert "boom" in reported

    if not page.evaluate("() => !!document.querySelector('dialog.loop-dialog')"):
        page.click(".loop-ctrl-interject")
        page.wait_for_selector('dialog.loop-dialog[open]', timeout=5000)
        page.fill(".loop-ctrl-input", "Check the parser.")
    assert page.evaluate("() => document.querySelector('.loop-ctrl-input').value") \
        == "Check the parser."
    page.click("dialog.loop-dialog .loop-ctrl-confirm")
    for _ in range(50):
        if len(held) == 2:
            break
        page.wait_for_timeout(100)
    assert len(held) == 2
    held[1].fulfill(status=200, content_type="application/json", body='{"ok": true}')
    page.wait_for_function("() => !document.querySelector('dialog.loop-dialog')",
                           timeout=5000)
    assert len(held) == 2
    page.unroute("**/" + _ACTIVE_ID + "/interject")
    _unserve_mutable_loop(page)


def test_paused_card_is_an_architect_hold(page, dashboard_fleet):
    """A pause renders as an Architect hold, never as an escalation."""
    _route_paused_status(page, "paused_by_architect", pending_decision=False,
                         pause_reason="Lunch break.\nBack at 14:00.")
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_selector(".loop-hold-card", timeout=10000)
    text = page.evaluate(
        "() => document.querySelector('.loop-hold-card').textContent")
    assert "Architect hold (paused)" in text
    assert "No participant response is required." in text
    assert "Preserved: Draftor \u00b7 plan_drafting" in text
    assert "Lunch break.\nBack at 14:00." in text
    assert "awaiting your decision" not in text
    assert page.locator(".loop-decision-card").count() == 0
    style = page.evaluate(
        "() => getComputedStyle(document.querySelector('.loop-hold-card'))"
        ".borderTopStyle")
    assert style == "dashed"  # distinct by border style, not colour alone
    page.unroute("**/loops/*/status")


def test_textarea_draft_survives_mutation_free_polls(page, dashboard_fleet):
    """The response box is a labelled multiline textarea; a typed draft
    survives unchanged polls, which make zero DOM mutations."""
    _route_paused_status(page, "blocked_on_architect", pending_decision=True)
    _open_unblock(page, dashboard_fleet)
    info = page.evaluate("""() => {
        var el = document.querySelector('.loop-ctrl-input');
        var lab = document.querySelector('label[for="' + el.id + '"]');
        return {tag: el.tagName, label: lab ? lab.textContent : null};
    }""")
    assert info["tag"] == "TEXTAREA"
    assert info["label"] == "Response to Draftor (required)"
    draft = "First paragraph.\n\nSecond paragraph with detail."
    page.fill(".loop-ctrl-input", draft)
    page.evaluate("""() => {
        window._muts = 0;
        var obs = new MutationObserver(function (m) { window._muts += m.length; });
        ['#loop-controls', '#loop-region-blocked', '#loop-region-decisions']
          .forEach(function (sel) {
            obs.observe(document.querySelector(sel), {subtree: true,
              childList: true, characterData: true, attributes: true});
          });
    }""")
    page.wait_for_timeout(7000)  # more than two POLL_INTERVAL_MS polls
    assert page.evaluate("() => window._muts") == 0
    assert page.evaluate(
        "() => document.querySelector('.loop-ctrl-input').value") == draft
    page.unroute("**/loops/*/status")


def test_decision_history_and_unblock_notice(page, dashboard_fleet):
    """Resolved and cancelled requests stay readable; the unblock notice
    says who resumes and claims no model work."""
    import json as _json
    cancelled = {
        "id": "decision-0",
        "request": {"reason": "Old question", "artifact_path": None,
                    "round": 0, "role": "reviewer",
                    "ts": "2026-09-22T09:00:00+00:00"},
        "response": {"message": "Superseded", "artifact_path": None,
                     "kind": "cancelled_by_end",
                     "ts": "2026-09-22T09:30:00+00:00"},
    }
    _route_paused_status(page, "paused_by_architect", pending_decision=False,
                         extra_decisions=[cancelled])
    posts = []
    page.route("**/loops/*/unblock",
               lambda route: (posts.append(route.request.post_data), route.fulfill(
                   status=200, content_type="application/json",
                   body='{"ok": true}')))
    _open_unblock(page, dashboard_fleet)
    # L1: decision history sits in the collapsed Decisions disclosure.
    page.evaluate("() => document.querySelector("
                  "'#loop-decisions-details > summary').click()")
    page.wait_for_selector(".loop-decision-item", timeout=10000)
    text = page.evaluate(
        "() => document.querySelector('#loop-region-decisions').textContent")
    assert "decision-0" in text and "requested by Reviewer" in text
    assert "Cancelled \u2014 loop ended" in text and "Superseded" in text

    page.fill(".loop-ctrl-input", "Resume.\nFocus on the parser.")
    page.evaluate("() => document.querySelector('.loop-ctrl-confirm').click()")
    page.wait_for_selector(".loop-unblock-notice", timeout=5000)
    notice = page.evaluate(
        "() => document.querySelector('.loop-unblock-notice').textContent")
    assert "Draftor resumes at plan_drafting" in notice
    assert "does not run model work" in notice
    assert _json.loads(posts[0])["message"] == "Resume.\nFocus on the parser."
    page.unroute("**/loops/*/unblock")
    page.unroute("**/loops/*/status")


def test_multiline_pause_history_readable_after_unblock(page, dashboard_fleet):
    """After a hold ends, the full multi-line pause reason and unblock
    response stay readable in the timeline (no single-line truncation);
    unrelated events keep the compact detail."""
    import json as _json
    reason = "Lunch break.\nBack at 14:00 \u2014 then review the parser."
    response = "Resume.\nFocus on the parser tests first."
    status = {
        "loop_id": "active-loop-2026-09-22T10-00-00Z",
        "feature": "widget-refactor",
        "status": {"stage": "plan_drafting", "next_role": "draftor",
                   "round": 1, "max_rounds": 3, "blocked": False},
        "roles": {"draftor": {"role": "draftor", "joined": True},
                  "reviewer": {"role": "reviewer", "joined": True}},
        "decisions": [],
    }
    events = {"events": [
        {"event": "loop_started", "ts": "2026-09-22T10:00:00Z", "round": 0},
        {"event": "draft_submitted", "ts": "2026-09-22T10:01:00Z", "round": 1,
         "role": "draftor", "detail": "a long single-line detail " * 8},
        {"event": "loop_paused", "ts": "2026-09-22T10:02:00Z", "round": 1,
         "role": "architect", "detail": "Loop paused by Architect -- " + reason},
        {"event": "loop_unblocked", "ts": "2026-09-22T10:30:00Z", "round": 1,
         "role": "architect",
         "detail": "Resumed to plan_drafting (next: draftor) -- Architect: "
                   + response},
    ]}
    page.route("**/loops/*/status", lambda route: route.fulfill(
        status=200, content_type="application/json", body=_json.dumps(status)))
    page.route("**/loops/*/events", lambda route: route.fulfill(
        status=200, content_type="application/json", body=_json.dumps(events)))
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_selector(".loop-event-detail-full", timeout=10000)
    details = page.evaluate("""() => Array.from(
        document.querySelectorAll('#loop-timeline .loop-event-detail')).map(
        el => ({text: el.textContent, full: el.classList.contains(
            'loop-event-detail-full'), ws: getComputedStyle(el).whiteSpace,
            clipped: el.scrollWidth > el.clientWidth + 1}))""")
    full = [d for d in details if d["full"]]
    assert len(full) == 2
    # L1: newest first -- the unblock response precedes the pause reason.
    assert full[0]["text"].endswith(response) and full[1]["text"].endswith(reason)
    assert all(d["ws"] == "pre-wrap" and not d["clipped"] for d in full)
    compact = [d for d in details if not d["full"]]
    assert compact and all(d["ws"] == "nowrap" for d in compact)
    page.unroute("**/loops/*/status")
    page.unroute("**/loops/*/events")


# ── #51: planning sources in the Dashboard ───────────────────────────────────


_APPROVED_LIST_51 = {"loops": [{
    "loop_id": "src-loop-2026-09-01T10-00-00Z", "feature": "parser-rework",
    "mode": "planning", "planning_source": "sketch", "stage": "plan_approved",
    "round": 1, "max_rounds": 3, "blocked": False,
    "created_at": "2026-09-01T10:00:00+00:00", "attention_notified": False,
}]}


def _open_create_51(page, dashboard_fleet, posts, approved=False):
    """Open the create form on the loop-less repo; capture start POSTs
    (answered 400 so nothing is created)."""
    import json as _json
    if approved:
        page.route("**/loops", lambda route: route.fulfill(
            status=200, content_type="application/json",
            body=_json.dumps(_APPROVED_LIST_51)))
    page.route("**/loops/start", lambda route: (
        posts.append(_json.loads(route.request.post_data)),
        route.fulfill(status=400, content_type="application/json",
                      body='{"error": "captured"}')))
    origin = dashboard_fleet["url"].rstrip("/") + "/"
    page.goto(origin + "?repo=beta", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    page.evaluate(
        "() => document.querySelector('.sidebar-item[data-view=\"loop\"]').click()")
    page.wait_for_selector(".loop-create-workspace", timeout=10000)


def _pick(page, value):
    page.evaluate("""(v) => {
        var r = document.querySelector('input[name="loop-plan-source"][value="' + v + '"]');
        r.checked = true; r.dispatchEvent(new Event('change'));
    }""", value)


def test_create_architect_plan_posts_only_its_fields(page, dashboard_fleet):
    posts = []
    _open_create_51(page, dashboard_fleet, posts)
    _pick(page, "architect_plan")
    assert page.locator("#loop-plan-field").is_visible()
    assert page.evaluate(
        "() => document.querySelector('#loop-sketch-label').textContent") == \
        "Sketch source (optional)"
    page.fill("#loop-feature-input", "arch-51")
    page.fill("#loop-plan-path", ".gator/artifacts/plan.md")
    page.evaluate("() => document.querySelector('#loop-create-action').click()")
    page.wait_for_function("() => document.querySelector('#loop-create-error')"
                           ".textContent.includes('captured')", timeout=5000)
    assert len(posts) == 1
    body = posts[0]
    assert body["plan_path"] == ".gator/artifacts/plan.md"
    assert "revise_from" not in body and "sketch_path" not in body
    assert "mode" not in body


def test_create_revision_posts_only_its_fields(page, dashboard_fleet):
    posts = []
    _open_create_51(page, dashboard_fleet, posts, approved=True)
    _pick(page, "revision")
    page.wait_for_selector("#loop-revise-select", timeout=5000)
    assert page.evaluate(
        "() => document.querySelector('#loop-sketch-label').textContent") == \
        "Revision sketch"
    page.fill("#loop-feature-input", "rev-51")
    page.evaluate("""() => {
        var m = document.querySelector('#loop-sketch-manual');
        var s = document.querySelector('#loop-sketch-select');
        if (s) s.style.display = 'none';
        m.style.display = ''; m.value = '.gator/artifacts/rev.md';
    }""")
    page.evaluate("() => document.querySelector('#loop-create-action').click()")
    page.wait_for_function("() => document.querySelector('#loop-create-error')"
                           ".textContent.includes('captured')", timeout=5000)
    body = posts[0]
    assert body["revise_from"] == "src-loop-2026-09-01T10-00-00Z"
    assert body["sketch_path"] == ".gator/artifacts/rev.md"
    assert "plan_path" not in body


def test_coding_feature_prefill_is_editable(page, dashboard_fleet):
    posts = []
    _open_create_51(page, dashboard_fleet, posts, approved=True)
    page.route("**/loops/*/status", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body='{"brief_check": "absent", "status": {"stage": "plan_approved"}}'))
    page.evaluate("""() => {
        var r = document.querySelector('input[name="loop-mode"][value="coding"]');
        r.checked = true; r.dispatchEvent(new Event('change'));
    }""")
    page.wait_for_selector("#loop-source-select", timeout=5000)
    assert page.input_value("#loop-feature-input") == "parser-rework"
    assert page.locator("#loop-plan-source-field").is_hidden()
    page.fill("#loop-feature-input", "my-own-name")
    page.evaluate("""() => {
        var s = document.querySelector('#loop-source-select');
        s.dispatchEvent(new Event('change'));
    }""")
    assert page.input_value("#loop-feature-input") == "my-own-name"


def _route_source_status(page, extra, stage="plan_review", turns=None):
    import json as _json
    body = dict({
        "loop_id": "active-loop-2026-09-22T10-00-00Z",
        "feature": "widget-refactor",
        "status": {"stage": stage, "next_role": "reviewer", "round": 0,
                   "max_rounds": 3, "blocked": False},
        "roles": {"draftor": {"role": "draftor", "joined": False},
                  "reviewer": {"role": "reviewer", "joined": True}},
        "turns": turns or [],
        "decisions": [],
    }, **extra)
    page.route("**/loops/*/status", lambda route: route.fulfill(
        status=200, content_type="application/json", body=_json.dumps(body)))


_VIEW = {"artifact": "architect-plan.md", "sha256": "0" * 64, "bytes": 10}


def test_architect_plan_inspection_labels_order_timeline(page, dashboard_fleet):
    import json as _json
    _route_source_status(page, {
        "planning_source": "architect_plan",
        "plan_source": {"view": _VIEW, "check": "ok", "sketch_present": False},
    }, turns=[{"role": "architect", "type": "initial_plan"}])
    page.route("**/loops/*/events", lambda route: route.fulfill(
        status=200, content_type="application/json", body=_json.dumps({"events": [
            {"event": "loop_started", "ts": "2026-09-22T10:00:00Z"},
            {"event": "architect_plan_submitted", "ts": "2026-09-22T10:00:01Z",
             "round": 0, "role": "architect", "artifact_path": "plan.round-0.md",
             "detail": "Architect-originated draft plan -- awaiting Reviewer approval"},
        ]})))
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_selector(".loop-source-line", timeout=10000)
    line = page.evaluate("() => document.querySelector('.loop-source-line').textContent")
    assert line == ("Source: Architect-originated draft \u2014 awaiting Reviewer "
                    "approval (not approved)")
    page.wait_for_selector(".loop-artifact-section", timeout=10000)
    order = page.evaluate("""() => Array.from(document.querySelectorAll(
        '#loop-artifacts > .loop-artifact-section')).map(s => [s.dataset.artifact,
        s.querySelector('.loop-artifact-toggle').textContent])""")
    names = [n for n, _ in order]
    # L1: the plan row comes first; provenance follows it.
    assert names[0] == "plan.current.md"
    assert names[1] == "architect-plan.md"
    assert order[1][1] == "Architect-originated draft plan (provenance, unapproved)"
    assert "sketch.md" not in names  # no sketch for this loop
    labels = page.evaluate("""() => Array.from(document.querySelectorAll(
        '#loop-timeline .loop-event-label')).map(e => e.textContent)""")
    assert "Architect plan \u2014 awaiting Reviewer" in labels
    # Unchanged polls make zero mutations in the source line and artifacts.
    page.evaluate("""() => {
        window._m51 = 0;
        var obs = new MutationObserver(function (m) { window._m51 += m.length; });
        ['#loop-region-source', '#loop-artifacts'].forEach(function (sel) {
          obs.observe(document.querySelector(sel), {subtree: true,
            childList: true, characterData: true, attributes: true});
        });
    }""")
    page.wait_for_timeout(7000)
    assert page.evaluate("() => window._m51") == 0
    page.unroute("**/loops/*/status")
    page.unroute("**/loops/*/events")


def test_revision_inspection_labels_and_integrity(page, dashboard_fleet):
    base = dict(_VIEW, artifact="revision-baseline-plan.md")
    appr = dict(_VIEW, artifact="revision-baseline-approval.md")
    _route_source_status(page, {
        "planning_source": "revision",
        "revision": {"source_loop_id": "src-loop-2026-09-01T10-00-00Z",
                     "baseline": {"view": base, "check": "ok"},
                     "approval": {"view": appr, "check": "mismatch"}},
    }, stage="plan_drafting")
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_selector(".loop-source-line", timeout=10000)
    line = page.evaluate("() => document.querySelector('.loop-source-line').textContent")
    assert line.startswith("Source: Revision of src-loop-2026-09-01T10-00-00Z")
    assert "approval review [!! DIGEST MISMATCH]" in line
    page.wait_for_selector(".loop-artifact-section", timeout=10000)
    order = page.evaluate("""() => Array.from(document.querySelectorAll(
        '#loop-artifacts > .loop-artifact-section')).map(s => [s.dataset.artifact,
        s.querySelector('.loop-artifact-toggle').textContent])""")
    assert order[0][0] == "plan.current.md"  # L1: plan first
    assert order[1] == ["revision-baseline-plan.md",
                        "Baseline: approved plan from src-loop-2026-09-01T10-00-00Z"]
    assert order[2] == ["revision-baseline-approval.md",
                        "Baseline: approving review [!! DIGEST MISMATCH]"]
    assert order[3] == ["sketch.md", "Revision sketch"]
    page.unroute("**/loops/*/status")


# ── #56 mode badges ───────────────────────────────────────────────────────


def _card_mode_badge(page, feature):
    return page.evaluate("""(name) => {
        var cards = document.querySelectorAll('.loop-sidebar-card');
        for (var i = 0; i < cards.length; i++) {
          if (cards[i].querySelector('.loop-card-feature').textContent === name) {
            var b = cards[i].querySelector('.loop-mode-badge');
            return b ? {text: b.textContent, aria: b.getAttribute('aria-label'),
                        mode: b.dataset.mode} : null;
          }
        }
        return null;
    }""", feature)


@pytest.mark.parametrize("feature,label,key", [
    ("coding-finished", "Coding", "coding"),
    ("planning-finished", "Planning", "planning"),
    ("widget-refactor", "Planning · legacy", "legacy"),
])
def test_mode_badges_on_cards_and_headers(page, dashboard_fleet,
                                          feature, label, key):
    """A History card and the selected header (live or outcome) show the
    same mode badge, as text with an accessible name, from recorded mode
    only. The active loop has no card; its header carries the badge."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card", state="attached", timeout=10000)
    card = _card_mode_badge(page, feature)
    if feature == "widget-refactor":
        assert card is None  # the active loop has no card (2026-10-21)
    else:
        assert card == {"text": label, "aria": "Loop mode: " + label, "mode": key}
    _select_loop_card(page, feature)
    header = page.evaluate("""() => {
        var b = document.querySelector('.loop-status-header .loop-mode-badge');
        return b ? {text: b.textContent, aria: b.getAttribute('aria-label'),
                    mode: b.dataset.mode} : null;
    }""")
    assert header == {"text": label, "aria": "Loop mode: " + label, "mode": key}
    # The stage/outcome badge is still present beside it.
    assert page.locator(".loop-status-header .loop-badge").count() == 1


def test_mode_badge_styles_differ_without_colour(page, dashboard_fleet):
    """Coding, planning and legacy badges differ by border style/width,
    not by hue alone."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card .loop-mode-badge", state="attached", timeout=10000)
    styles = page.evaluate("""() => {
        var out = {};
        document.querySelectorAll('.loop-mode-badge').forEach(function (b) {
            var cs = getComputedStyle(b);
            out[b.dataset.mode] = cs.borderTopStyle + ' ' + cs.borderTopWidth;
        });
        return out;
    }""")
    assert set(["coding", "planning", "legacy"]) <= set(styles)
    assert len({styles["coding"], styles["planning"], styles["legacy"]}) == 3


def test_mode_badge_poll_is_mutation_free(page, dashboard_fleet):
    """An identical poll leaves the header region (and its mode badge)
    untouched, apart from the text-only countdown patch."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card", state="attached", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_selector(".loop-status-header .loop-mode-badge",
                           timeout=10000)
    page.wait_for_timeout(500)
    page.evaluate("""() => {
        window._m56 = 0;
        window._m56badge = document.querySelector(
            '.loop-status-header .loop-mode-badge');
        new MutationObserver(function (records) {
            records.forEach(function (r) {
                var t = r.target.nodeType === 3 ? r.target.parentElement : r.target;
                if (t && t.closest && (t.closest('.loop-time-remaining')
                                       || t.closest('.loop-elapsed'))) return;
                window._m56++;
            });
        }).observe(document.querySelector('#loop-region-header'),
                   {childList: true, subtree: true, characterData: true,
                    attributes: true});
    }""")
    page.wait_for_timeout(7000)  # more than two POLL_INTERVAL_MS polls
    assert page.evaluate("() => window._m56") == 0
    assert page.evaluate("() => window._m56badge.isConnected")


# ── #56 loop navigation: tabs, Create explanation, shell history ─────────


def _click_nav(page, view):
    page.evaluate(
        "(v) => document.querySelector('.sidebar-item[data-view=\"' + v + '\"]').click()",
        view)


def _panel_features(page, panel):
    return page.evaluate("""(id) => Array.from(
        document.querySelectorAll('#' + id + ' .loop-card-feature'))
        .map(el => el.textContent)""", panel)


def _tab_state(page):
    return page.evaluate("""() => {
        var out = {controls: []};
        document.querySelectorAll('.loop-subnav [role="tab"]').forEach(function (t) {
            out.controls.push(t.getAttribute('aria-controls'));
            out[t.dataset.tab] = {
                selected: t.getAttribute('aria-selected'),
                tabindex: t.getAttribute('tabindex'),
                text: t.textContent,
                primary: t.dataset.primary || null,
            };
        });
        // One tabpanel (the workspace body) for both tabs; the list pane
        // (History only) is hidden on the Primary tab.
        var body = document.getElementById('loop-tabpanel');
        out.bodyRole = body ? body.getAttribute('role') : null;
        out.labelledBy = body ? body.getAttribute('aria-labelledby') : null;
        var side = document.getElementById('loop-sidebar-nav');
        out.sidebarHidden = side ? side.hidden : null;
        // #72: the tablist sits in the main-pane bar, not in the sidebar.
        out.tablist = !!document.querySelector('#loop-tabbar [role="tablist"]')
            && !document.querySelector('#loop-sidebar-nav [role="tablist"]');
        return out;
    }""")


def _wait_header(page, feature):
    page.wait_for_function(
        "(name) => { var h = document.querySelector('.loop-status-header h3');"
        "  return h && h.textContent === name; }",
        arg=feature, timeout=10000)


def _history_back(page):
    page.evaluate("() => history.back()")


def _history_forward(page):
    page.evaluate("() => history.forward()")


def test_loop_subnav_tabs(page, dashboard_fleet):
    """Primary (Active here) / History tabs: tab roles, one tabpanel body
    labelled by the selected tab, roving tabindex and arrow keys. The list
    pane holds only terminal loops and is shown only on History."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-subnav", timeout=10000)
    st = _tab_state(page)
    assert st["tablist"]
    assert st["bodyRole"] == "tabpanel"
    assert st["controls"] == ["loop-tabpanel", "loop-tabpanel"]
    assert st["create"] == {"selected": "true", "tabindex": "0",
                            "text": "Active", "primary": "active"}
    assert st["history"] == {"selected": "false", "tabindex": "-1",
                             "text": "History", "primary": None}
    assert st["labelledBy"] == "loop-tab-create"
    assert st["sidebarHidden"] is True
    history = _panel_features(page, "loop-sidebar-nav")
    assert set(history) == {"auth-migration", "coding-finished", "planning-finished"}

    # Keyboard: ArrowRight selects and focuses History; End/Home; ArrowLeft wraps.
    page.focus("#loop-tab-create")
    page.keyboard.press("ArrowRight")
    st = _tab_state(page)
    assert st["history"]["selected"] == "true" and st["sidebarHidden"] is False
    assert st["labelledBy"] == "loop-tab-history"
    assert st["create"]["tabindex"] == "-1"
    assert page.evaluate("() => document.activeElement.id") == "loop-tab-history"
    page.keyboard.press("Home")
    assert page.evaluate("() => document.activeElement.id") == "loop-tab-create"
    page.keyboard.press("End")
    assert page.evaluate("() => document.activeElement.id") == "loop-tab-history"
    page.keyboard.press("ArrowRight")  # wraps
    assert page.evaluate("() => document.activeElement.id") == "loop-tab-create"
    st = _tab_state(page)
    assert st["create"]["selected"] == "true" and st["sidebarHidden"] is True


def test_loop_tabs_survive_polls(page, dashboard_fleet):
    """Polls never touch the tab chrome: the tablist node and a focused tab
    survive, and the tab bar, the body's tab attributes and the (hidden)
    History list record zero mutations across unchanged polls."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    page.wait_for_timeout(500)
    page.focus("#loop-tab-create")
    page.evaluate("""() => {
        window._tl56 = document.querySelector('.loop-subnav');
        window._chromeMutations = 0;
        var count = function (r) { window._chromeMutations += r.length; };
        var opts = {childList: true, subtree: true, characterData: true,
                    attributes: true};
        new MutationObserver(count).observe(
            document.getElementById('loop-tabbar'), opts);
        new MutationObserver(count).observe(
            document.getElementById('loop-sidebar-nav'), opts);
        new MutationObserver(count).observe(
            document.getElementById('loop-tabpanel'), {attributes: true});
    }""")
    page.wait_for_timeout(7000)  # more than two polls
    assert page.evaluate("() => window._tl56.isConnected")
    assert page.evaluate("() => document.activeElement.id") == "loop-tab-create"
    assert page.evaluate("() => window._chromeMutations") == 0


def test_loop_tabbar_spans_main_pane(page, dashboard_fleet):
    """#72: Primary / History sit in a full-width bar across the top of the
    Loop main pane; selection is weight plus underline. In Active the live
    workspace spans the bar (no list pane); History shows the list pane
    below the bar. A half-filled creation form survives History -> Create."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    geo = page.evaluate("""() => {
        const r = s => document.querySelector(s).getBoundingClientRect();
        const style = s => getComputedStyle(document.querySelector(s));
        const bar = r('#loop-tabbar'), slot = r('#view-slot');
        const main = r('#loop-main-content');
        const sel = style('#loop-tab-create'), un = style('#loop-tab-history');
        return {
            barLeft: bar.left, barRight: bar.right, barBottom: bar.bottom,
            // the pane's content edge: #view-slot minus its right padding
            slotRight: slot.right - parseFloat(style('#view-slot').paddingRight),
            mainLeft: main.left, mainRight: main.right, mainTop: main.top,
            baseline: style('#loop-tabbar').borderBottomWidth,
            selWeight: parseInt(sel.fontWeight, 10), selBorder: sel.borderBottomWidth,
            selBorderColor: sel.borderBottomColor,
            unWeight: parseInt(un.fontWeight, 10),
            unBorderColor: un.borderBottomColor,
        };
    }""")
    assert abs(geo["barRight"] - geo["slotRight"]) <= 1
    # Active: no list pane, so the live workspace spans the bar's width.
    assert abs(geo["barLeft"] - geo["mainLeft"]) <= 1
    assert abs(geo["barRight"] - geo["mainRight"]) <= 1
    assert geo["barBottom"] <= geo["mainTop"] + 1
    assert geo["baseline"] == "1px"
    # Paper: selected = weight 600 + a 3px teal bottom rule.
    assert geo["selWeight"] >= 600 and geo["selBorder"] == "3px"
    assert geo["selBorderColor"] == "rgb(25, 174, 184)"
    assert geo["unWeight"] == 400
    assert geo["unBorderColor"] in ("rgba(0, 0, 0, 0)", "transparent")

    # History: the list pane appears below the bar, at its left edge.
    page.evaluate("() => document.querySelector('#loop-tab-history').click()")
    side = page.evaluate("""() => {
        const b = document.querySelector('#loop-tabbar').getBoundingClientRect();
        const s = document.querySelector('#loop-sidebar-nav').getBoundingClientRect();
        return {barLeft: b.left, barBottom: b.bottom, sideLeft: s.left,
                sideTop: s.top, sideWidth: s.width};
    }""")
    assert side["sideWidth"] > 0
    assert abs(side["barLeft"] - side["sideLeft"]) <= 1
    assert side["barBottom"] <= side["sideTop"] + 1

    # Half-filled form survives History -> Create (beta has no loops).
    origin = dashboard_fleet["url"].rstrip("/") + "/"
    page.goto(origin + "?repo=beta", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    _click_nav(page, "loop")
    page.wait_for_selector("#loop-feature-input", timeout=10000)
    page.fill("#loop-feature-input", "half-filled-feature")
    page.evaluate("() => document.querySelector('#loop-tab-history').click()")
    assert _tab_state(page)["history"]["selected"] == "true"
    page.evaluate("() => document.querySelector('#loop-tab-create').click()")
    assert _tab_state(page)["create"]["selected"] == "true"
    assert page.input_value("#loop-feature-input") == "half-filled-feature"


def test_loop_tabs_inert_until_loops_load(page, dashboard_fleet):
    """#72: the main-pane tablist exists before /loops resolves; a tab
    click in that window changes nothing (no history entry, no stale
    render) and the mount still lands on its default selection."""
    origin = dashboard_fleet["url"].rstrip("/") + "/"
    page.goto(origin + "?repo=alpha", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    held = []
    page.route("**/api/repo-by-key/*/loops", lambda route: held.append(route))
    _click_nav(page, "loop")
    page.wait_for_selector("#loop-tab-history", timeout=10000)
    assert held, "the /loops request should be in flight"
    length = page.evaluate("() => history.length")
    assert page.evaluate(
        "() => document.querySelector('#loop-tab-create').textContent") == "\u2026"
    page.evaluate("() => document.querySelector('#loop-tab-history').click()")
    assert page.evaluate("() => history.length") == length
    assert page.evaluate(
        "() => document.querySelector('.loop-workspace').dataset.loaded") is None
    for route in held:
        route.fallback()
    page.unroute("**/api/repo-by-key/*/loops")
    page.wait_for_selector(".loop-status-header", timeout=10000)
    st = _tab_state(page)
    assert st["create"]["selected"] == "true" and st["create"]["text"] == "Active"
    assert st["history"]["selected"] == "false"
    assert page.evaluate("() => history.length") == length


@pytest.mark.parametrize("repo", ["alpha", "beta"])
def test_primary_tab_reflects_active_state(page, dashboard_fleet, repo):
    """With an active loop (alpha) the Primary tab reads Active and opens
    the live workspace at full width; with none (beta) it reads Create and
    shows the form. Neither shows a Create Loop action, an Active card, the
    old active-loop explanation or a visible list pane."""
    if repo == "alpha":
        _navigate_to_loop(page, dashboard_fleet)
        _wait_header(page, "widget-refactor")
    else:
        origin = dashboard_fleet["url"].rstrip("/") + "/"
        page.goto(origin + "?repo=beta", wait_until="load")
        page.wait_for_selector(".repo-file-item", timeout=15000)
        _click_nav(page, "loop")
        page.wait_for_selector(".loop-create-workspace", timeout=10000)
    st = _tab_state(page)
    assert st["create"]["selected"] == "true"
    assert st["create"]["text"] == ("Active" if repo == "alpha" else "Create")
    assert st["sidebarHidden"] is True
    for gone in (".loop-sidebar-create", ".loop-create-active",
                 ".loop-sidebar-open-active", ".loop-card-attention"):
        assert page.locator(gone).count() == 0, gone
    assert page.locator("#loop-feature-input").count() == (0 if repo == "alpha" else 1)
    geo = page.evaluate("""() => {
        const b = document.getElementById('loop-tabpanel').getBoundingClientRect();
        const m = document.getElementById('loop-main-content').getBoundingClientRect();
        return {bl: b.left, br: b.right, ml: m.left, mr: m.right};
    }""")
    assert abs(geo["ml"] - geo["bl"]) <= 1 and abs(geo["mr"] - geo["br"]) <= 1


def test_loop_back_forward_within_loop(page, dashboard_fleet):
    """7a: select a history loop -> Active tab -> Back restores History and
    that loop's header without adding entries -> Forward returns to Active
    and the active loop."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    _select_loop_card(page, "auth-migration")
    assert _tab_state(page)["history"]["selected"] == "true"
    page.evaluate("() => document.querySelector('#loop-tab-create').click()")
    _wait_header(page, "widget-refactor")
    assert _tab_state(page)["create"]["selected"] == "true"
    length = page.evaluate("() => history.length")
    _history_back(page)
    _wait_header(page, "auth-migration")
    assert _tab_state(page)["history"]["selected"] == "true"
    assert page.evaluate("() => history.length") == length
    page.wait_for_function(
        "() => document.activeElement && document.activeElement.matches"
        "('.loop-status-header h3')", timeout=5000)
    _history_forward(page)
    _wait_header(page, "widget-refactor")
    assert _tab_state(page)["create"]["selected"] == "true"
    assert page.evaluate("() => history.length") == length


@pytest.mark.parametrize("away", ["history", "fleet"])
def test_back_restores_loop_after_leaving(page, dashboard_fleet, away):
    """7b/7c: select a history loop -> leave to Commits (or Fleet) -> Back
    shows the Loop view with that selection -> Forward leaves again."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    _select_loop_card(page, "coding-finished")
    _click_nav(page, away)
    page.wait_for_function(
        "(v) => document.querySelector('.sidebar-item.active').dataset.view === v",
        arg=away, timeout=5000)
    assert page.locator(".loop-workspace").count() == 0
    _history_back(page)
    _wait_header(page, "coding-finished")
    assert page.evaluate(
        "() => document.querySelector('.sidebar-item.active').dataset.view") == "loop"
    assert _tab_state(page)["history"]["selected"] == "true"
    assert page.evaluate(
        "() => document.querySelector('.loop-status-header .loop-mode-badge').textContent"
    ) == "Coding"
    _history_forward(page)
    page.wait_for_function(
        "(v) => document.querySelector('.sidebar-item.active').dataset.view === v",
        arg=away, timeout=5000)
    assert page.locator(".loop-workspace").count() == 0


def test_back_past_loop_entry_restores_shell_views(page, dashboard_fleet):
    """7c: Back past the Loop entries reaches the Repo entry, then Fleet."""
    origin = dashboard_fleet["url"].rstrip("/") + "/"
    page.goto(origin, wait_until="load")
    open_fleet(page)
    page.wait_for_selector(".link-btn", timeout=10000)
    page.evaluate("""() => {
        var btns = document.querySelectorAll('.link-btn');
        for (var i = 0; i < btns.length; i++) {
            if (btns[i].textContent === 'alpha') { btns[i].click(); break; }
        }
    }""")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    _click_nav(page, "loop")
    page.wait_for_selector(".loop-status-header", timeout=10000)
    _history_back(page)
    page.wait_for_selector(".repo-file-item", timeout=15000)
    assert page.evaluate(
        "() => document.querySelector('.sidebar-item.active').dataset.view") == "repo"
    _history_back(page)
    page.wait_for_selector(".link-btn", timeout=10000)
    assert page.evaluate(
        "() => document.querySelector('.sidebar-item.active').dataset.view") == "fleet"
    # The landing Fleet entry had no repository: the shell restores that.
    assert page.evaluate(
        "() => document.getElementById('loop-tab').classList.contains('dimmed')")


def test_back_restores_loop_in_its_own_repository(page, dashboard_fleet):
    """7e: alpha history loop -> Fleet -> beta -> Back x2 restores alpha's
    Loop (label, card, heading, API key) -> Forward x2 returns to beta."""
    alpha_key = _repo_key(dashboard_fleet["repos"]["alpha"]["path"])
    beta_key = _repo_key(dashboard_fleet["repos"]["beta"]["path"])
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    _select_loop_card(page, "auth-migration")
    _click_nav(page, "fleet")
    page.wait_for_selector(".link-btn", timeout=10000)
    page.evaluate("""() => {
        var btns = document.querySelectorAll('.link-btn');
        for (var i = 0; i < btns.length; i++) {
            if (btns[i].textContent === 'beta') { btns[i].click(); break; }
        }
    }""")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    assert "beta" in page.evaluate("() => document.querySelector('#sidebar-context .ctx-name').textContent")

    loop_requests = []
    page.on("request", lambda req: loop_requests.append(req.url)
            if "/loops" in req.url else None)
    _history_back(page)
    page.wait_for_selector(".link-btn", timeout=10000)
    _history_back(page)
    _wait_header(page, "auth-migration")
    assert "alpha" in page.evaluate("() => document.querySelector('#sidebar-context .ctx-name').textContent")
    assert page.evaluate(
        "() => document.querySelector('.loop-sidebar-card.loop-sidebar-item-selected"
        " .loop-card-feature').textContent") == "auth-migration"
    assert loop_requests, "restoring the Loop view must fetch loop data"
    assert all("/repo-by-key/" + alpha_key + "/" in u for u in loop_requests), loop_requests
    assert not any(beta_key in u for u in loop_requests)

    _history_forward(page)
    page.wait_for_selector(".link-btn", timeout=10000)
    _history_forward(page)
    page.wait_for_selector(".repo-file-item", timeout=15000)
    assert page.evaluate(
        "() => document.querySelector('.sidebar-item.active').dataset.view") == "repo"
    assert "beta" in page.evaluate("() => document.querySelector('#sidebar-context .ctx-name').textContent")


def test_back_to_unregistered_repo_falls_back_to_fleet(page, dashboard_fleet):
    """7f: a recorded repository that is no longer in the fleet shows Fleet
    with a notice and never issues a Loop request for it."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    page.evaluate("""() => history.replaceState({gatorDashboard: 1, view: 'loop',
        repo: 'ghost-repo', repoKey: 'deadbeef', sub: null}, '')""")
    _click_nav(page, "history")
    page.wait_for_function(
        "() => document.querySelector('.sidebar-item.active').dataset.view === 'history'",
        timeout=5000)
    loop_requests = []
    page.on("request", lambda req: loop_requests.append(req.url)
            if "/loops" in req.url else None)
    _history_back(page)
    page.wait_for_selector(".shell-notice", timeout=5000)
    assert page.evaluate(
        "() => document.querySelector('.shell-notice').textContent"
    ) == "That repository is no longer registered."
    assert page.evaluate(
        "() => document.querySelector('.sidebar-item.active').dataset.view") == "fleet"
    assert page.evaluate("() => history.state.view") == "fleet"
    page.wait_for_timeout(500)
    assert loop_requests == []


def test_history_state_never_holds_tokens(page, dashboard_fleet):
    """7d: every recorded and walked history state is a shell entry with no
    token, prompt or artifact text, including after a prompt copy."""
    page.add_init_script("""
        window.__states = [];
        ['pushState', 'replaceState'].forEach(function (fn) {
            var orig = history[fn].bind(history);
            history[fn] = function (st) {
                window.__states.push(JSON.stringify(st));
                return orig.apply(null, arguments);
            };
        });
    """)
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    page.evaluate("() => { var b = document.querySelector('.loop-prompt-copy');"
                  " if (b) b.click(); }")
    page.wait_for_timeout(500)
    _select_loop_card(page, "auth-migration")
    page.evaluate("() => document.querySelector('#loop-tab-create').click()")
    _click_nav(page, "history")
    page.wait_for_timeout(300)
    for _ in range(4):
        _history_back(page)
        page.wait_for_timeout(400)
        page.evaluate("() => window.__states.push(JSON.stringify(history.state))")
    states = page.evaluate("() => window.__states")
    assert len(states) >= 8
    for raw in states:
        assert "glp_" not in raw
        assert "Executive Summary" not in raw and "prompt" not in raw.lower()
        st = json.loads(raw)
        assert st["gatorDashboard"] == 1
        # #80 adds `ctx`: the opaque id of the workspace context shown.
        assert set(st) == {"gatorDashboard", "view", "repo", "repoKey", "sub", "ctx"}
        assert st["ctx"] is None or re.fullmatch(r"[a-z0-9]{1,16}", st["ctx"])
        if st["sub"] is not None:
            assert set(st["sub"]) == {"view", "mode", "loopId"}


def test_commits_nav_label(page, dashboard_fleet):
    """The repository commit view is labelled Commits; route unchanged.
    Commits is enabled only with a repository selected (2026-10-18)."""
    origin = dashboard_fleet["url"].rstrip("/") + "/"
    page.goto(origin + "?repo=alpha", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    label = page.evaluate(
        "() => document.querySelector('.sidebar-item[data-view=\"history\"]').textContent")
    assert "Commits" in label and "History" not in label
    _click_nav(page, "history")
    page.wait_for_function(
        "() => document.getElementById('topbar-title').textContent === 'Commits'",
        timeout=5000)
    assert page.evaluate("() => history.state.view") == "history"


def test_history_tab_with_active_loop_round_trips(page, dashboard_fleet):
    """A History tab chosen while the active loop stays inspected is
    restored as History (not derived from the loop's stage), both within
    the Loop view and after leaving it."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-status-header h3", timeout=10000)
    page.wait_for_function(
        "() => document.querySelector('.loop-status-header h3').textContent !== ''",
        timeout=10000)
    active = page.evaluate(
        "() => document.querySelector('.loop-status-header h3').textContent")
    assert active == "widget-refactor"
    assert active not in _panel_features(page, "loop-sidebar-nav")
    page.evaluate("() => document.querySelector('#loop-tab-history').click()")
    assert _tab_state(page)["history"]["selected"] == "true"
    _wait_header(page, active)  # the main content is untouched

    # Within Loop: Back shows the Create tab, Forward the History tab, and
    # the inspected active loop stays in the main region throughout.
    _history_back(page)
    page.wait_for_function(
        "() => document.querySelector('#loop-tab-create')"
        ".getAttribute('aria-selected') === 'true'", timeout=5000)
    _wait_header(page, active)
    _history_forward(page)
    page.wait_for_function(
        "() => document.querySelector('#loop-tab-history')"
        ".getAttribute('aria-selected') === 'true'", timeout=5000)
    _wait_header(page, active)
    assert _tab_state(page)["sidebarHidden"] is False

    # Leave and come back: the remount restores the same tab and loop.
    _click_nav(page, "history")
    page.wait_for_function(
        "() => document.querySelector('.sidebar-item.active').dataset.view === 'history'",
        timeout=5000)
    _history_back(page)
    _wait_header(page, active)
    page.wait_for_function(
        "() => document.querySelector('#loop-tab-history')"
        ".getAttribute('aria-selected') === 'true'", timeout=5000)
    assert _tab_state(page)["sidebarHidden"] is False


def _loop_id_of(page, feature):
    return page.evaluate("""(name) => {
        var cards = document.querySelectorAll('.loop-sidebar-card');
        for (var i = 0; i < cards.length; i++) {
            if (cards[i].querySelector('.loop-card-feature').textContent === name)
                return cards[i].dataset.loopId;
        }
        return null;
    }""", feature)


@pytest.mark.parametrize("row", ["create_form", "create_inspect_terminal",
                                 "history_missing_loop"])
def test_old_loop_substate_records_restore(page, dashboard_fleet, row):
    """Old Create/History records restore to the current state: Primary
    content is derived from the loop list (never from the record), and a
    History record without a listed loop shows the Primary content beside
    the History list. Nothing sensitive reaches history or storage."""
    _navigate_to_loop(page, dashboard_fleet)
    _wait_header(page, "widget-refactor")
    done_id = _loop_id_of(page, "auth-migration")
    assert done_id
    sub = {
        "create_form": {"view": "create", "mode": "create", "loopId": None},
        "create_inspect_terminal": {"view": "create", "mode": "inspect",
                                    "loopId": done_id},
        "history_missing_loop": {"view": "history", "mode": "inspect",
                                 "loopId": "gone-loop"},
    }[row]
    page.evaluate("""(sub) => {
        var st = history.state; st.sub = sub; history.replaceState(st, '');
    }""", sub)
    page.reload(wait_until="load")
    page.wait_for_selector('.loop-workspace[data-loaded="1"]', state="attached", timeout=15000)
    _wait_header(page, "widget-refactor")
    st = _tab_state(page)
    assert st["create"]["text"] == "Active"
    if row == "history_missing_loop":
        assert st["history"]["selected"] == "true" and st["sidebarHidden"] is False
    else:
        assert st["create"]["selected"] == "true" and st["sidebarHidden"] is True
    raw = page.evaluate("() => JSON.stringify(history.state)")
    stored = page.evaluate(
        "() => JSON.stringify(Object.assign({}, window.sessionStorage))")
    for blob in (raw, stored):
        assert "glp_" not in blob and "prompt" not in blob.lower()


@pytest.mark.raw_loop_list
def test_active_conflict_state(page, dashboard_fleet):
    """Defensive: the raw alpha seed has several live loops. The Primary tab
    reads Active, shows an honest conflict notice and one button per live
    loop (id order), inspects nothing, and opens exactly the loop chosen."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-conflict", timeout=10000)
    st = _tab_state(page)
    assert st["create"]["text"] == "Active" and st["create"]["selected"] == "true"
    assert st["sidebarHidden"] is True
    notice = page.evaluate(
        "() => document.querySelector('.loop-conflict .loop-primary-notice').textContent")
    assert "4 loops are active" in notice and "does not pick one" in notice
    assert page.locator(".loop-status-header").count() == 0
    ids = page.evaluate("""() => Array.from(document.querySelectorAll(
        '.loop-conflict-open')).map(b => b.dataset.loopId)""")
    assert ids == sorted(ids) and len(ids) == 4
    names = page.evaluate("""() => Array.from(document.querySelectorAll(
        '.loop-conflict-open')).map(b => b.textContent)""")
    assert set(names) == {"widget-refactor", "xss-test", "blocked-feature",
                          "roundzero-test"}
    _select_loop_card(page, "blocked-feature")
    assert page.locator(".loop-conflict").count() == 0
    assert _tab_state(page)["create"]["selected"] == "true"
    page.wait_for_function(
        "() => document.activeElement && document.activeElement.matches"
        "('.loop-status-header h3')", timeout=5000)


def _list_item(loop_id, feature, stage, mode="planning"):
    return {"loop_id": loop_id, "feature": feature, "stage": stage,
            "mode": mode, "round": 1, "max_rounds": 3,
            "created_at": "2026-09-22T10:00:00Z"}


_DONE_ITEM = _list_item("done-loop-2026-09-20T10-00-00Z", "auth-migration",
                        "plan_approved")


def _serve_list(page, holder):
    """Serve the loop list from holder["loops"]; holder["fail"] makes it
    fail ("http500", "abort" or "invalid": a body without a loops array)."""
    def handler(route):
        fail = holder.get("fail")
        if fail == "abort":
            route.abort()
        elif fail == "http500":
            route.fulfill(status=500, content_type="application/json",
                          body=json.dumps({"error": "boom"}))
        elif fail == "invalid":
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"items": []}))
        else:
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"loops": holder["loops"]}))
    page.route("**/api/repo-by-key/*/loops", handler)


def _serve_extra_loop(page, loop_id, feature, stage):
    """A live loop that exists only in the mocked list."""
    payload = {
        "loop_id": loop_id, "feature": feature,
        "created_at": "2026-09-23T10:00:00+00:00",
        "status": {"stage": stage, "next_role": "draftor", "round": 1,
                   "max_rounds": 3, "blocked": False},
        "roles": {"draftor": {"role": "draftor", "joined": True},
                  "reviewer": {"role": "reviewer", "joined": True}},
        "decisions": [],
    }
    page.route("**/loops/" + loop_id + "/status", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(payload)))
    page.route("**/loops/" + loop_id + "/events", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"events": []})))


def _end_live_loop(payload, holder, stage="plan_approved"):
    """End the mocked widget-refactor loop in its status and in the list."""
    payload["status"]["status"]["stage"] = stage
    holder["loops"] = [dict(it, stage=stage) if it["loop_id"] == _ACTIVE_ID else it
                       for it in holder["loops"]]


@pytest.mark.parametrize("selected", ["active", "history"])
def test_active_loop_ends_reconciles_primary(page, dashboard_fleet, selected):
    """When the active loop ends: on the Active tab, Primary becomes Create
    with an "ended" notice whose link opens the loop in History, with no
    new history entry; on the History tab, polls never move the Architect
    out of History, and only the Primary label changes."""
    payload = _live_payload()
    _serve_mutable_loop(page, payload)
    holder = {"loops": [_list_item(_ACTIVE_ID, "widget-refactor", "plan_revision"),
                        _DONE_ITEM]}
    _serve_list(page, holder)
    _navigate_to_loop(page, dashboard_fleet)
    _wait_header(page, "widget-refactor")
    if selected == "history":
        page.evaluate("() => document.querySelector('#loop-tab-history').click()")
    length = page.evaluate("() => history.length")

    _end_live_loop(payload, holder)
    page.wait_for_function(
        "() => document.querySelector('#loop-tab-create').dataset.primary === 'create'",
        timeout=10000)
    if selected == "active":
        page.wait_for_selector(".loop-create-workspace", timeout=5000)
        notice = page.wait_for_selector(
            '#loop-main-content > .loop-transition-notice[data-kind="ended"]',
            timeout=5000)
        assert "widget-refactor" in notice.text_content()
        assert "Approved" in notice.text_content()
        st = _tab_state(page)
        assert st["create"]["text"] == "Create" and st["create"]["selected"] == "true"
        assert page.evaluate("() => history.length") == length
        assert page.evaluate("() => history.state.sub.mode") == "create"
        page.evaluate("() => document.querySelector('.loop-ended-history').click()")
        _wait_header(page, "widget-refactor")
        assert _tab_state(page)["history"]["selected"] == "true"
    else:
        page.wait_for_timeout(4000)  # at least one more poll window
        st = _tab_state(page)
        assert st["history"]["selected"] == "true" and st["sidebarHidden"] is False
        assert st["create"]["text"] == "Create"
        assert page.locator(".loop-create-workspace").count() == 0
        _wait_header(page, "widget-refactor")
        assert page.evaluate("() => history.length") == length


@pytest.mark.parametrize("case", ["a_to_b", "one_to_many", "chosen_kept",
                                  "membership_changed",
                                  "chosen_then_sole_then_many", "many_to_none"])
def test_primary_follows_active_identity(page, dashboard_fleet, case):
    """Primary follows a valid list (no case adds a history entry):
    a_to_b inspects B with an "A ended" notice; one_to_many from an ordinary
    inspection shows the conflict state (no pick); a loop chosen from the
    conflict list stays while the conflict is unchanged, and the conflict
    returns when membership changes or after a sole-loop interval;
    many_to_none shows the Create form."""
    payload = _live_payload()
    _serve_mutable_loop(page, payload)
    _serve_extra_loop(page, "loop-b", "beta-feature", "plan_drafting")
    _serve_extra_loop(page, "loop-c", "gamma-feature", "plan_drafting")
    a = _list_item(_ACTIVE_ID, "widget-refactor", "plan_revision")
    b = _list_item("loop-b", "beta-feature", "plan_drafting")
    c = _list_item("loop-c", "gamma-feature", "plan_drafting")
    sole = case in ("a_to_b", "one_to_many")
    holder = {"loops": [a, _DONE_ITEM] if sole else [a, b, _DONE_ITEM]}
    _serve_list(page, holder)
    _navigate_to_loop(page, dashboard_fleet)
    if sole:
        _wait_header(page, "widget-refactor")
    else:
        page.wait_for_selector(".loop-conflict", timeout=10000)
        _select_loop_card(page, "widget-refactor")  # an explicit choice
        assert page.locator(".loop-conflict").count() == 0
    length = page.evaluate("() => history.length")

    if case == "a_to_b":
        _end_live_loop(payload, holder)
        holder["loops"] = holder["loops"] + [b]
        _wait_header(page, "beta-feature")
        notice = page.wait_for_selector(
            '[data-slot="action"] .loop-transition-notice[data-kind="ended"]',
            timeout=5000)
        assert "widget-refactor" in notice.text_content()
        assert _tab_state(page)["create"]["text"] == "Active"
    elif case in ("one_to_many", "membership_changed"):
        holder["loops"] = holder["loops"] + ([b] if case == "one_to_many" else [c])
        page.wait_for_selector(".loop-conflict", timeout=10000)
        n = 2 if case == "one_to_many" else 3
        assert page.locator(".loop-conflict-open").count() == n
        assert page.locator(".loop-status-header").count() == 0
    elif case == "chosen_kept":
        page.wait_for_timeout(7000)  # two unchanged polls
        assert page.locator(".loop-conflict").count() == 0
        _wait_header(page, "widget-refactor")
    elif case == "chosen_then_sole_then_many":
        holder["loops"] = [a, _DONE_ITEM]
        page.wait_for_timeout(3500)  # one poll sees one(A)
        page.evaluate("""() => {
            window._mainMutations = 0;
            new MutationObserver(function (r) { window._mainMutations += r.length; })
                .observe(document.getElementById('loop-main-content'),
                         {childList: true, subtree: true, characterData: true,
                          attributes: true});
        }""")
        page.wait_for_timeout(3500)  # another poll: A kept in place
        assert page.evaluate("() => window._mainMutations") == 0
        _wait_header(page, "widget-refactor")
        holder["loops"] = [a, b, _DONE_ITEM]
        page.wait_for_selector(".loop-conflict", timeout=10000)
    elif case == "many_to_none":
        _end_live_loop(payload, holder)
        holder["loops"] = [dict(it, stage="plan_approved") if it["loop_id"] == "loop-b"
                           else it for it in holder["loops"]]
        page.wait_for_selector(".loop-create-workspace", timeout=10000)
        page.wait_for_selector(
            '#loop-main-content > .loop-transition-notice[data-kind="ended"]',
            timeout=5000)
        assert _tab_state(page)["create"]["text"] == "Create"
    assert page.evaluate("() => history.length") == length


@pytest.mark.parametrize("fail", ["http500", "abort", "invalid"])
def test_list_failure_keeps_primary_workspace(page, dashboard_fleet, fail):
    """A failed loop list (HTTP error, network error, or a body without a
    loops array) is never read as "no active loop": the live workspace and
    label stay, the refresh notice shows, and polling continues; a valid
    list clears the notice. With the loop finished meanwhile, the terminal
    status is shown in place and the timer kept until a valid list
    reconciles Primary to Create."""
    payload = _live_payload()
    _serve_mutable_loop(page, payload)
    holder = {"loops": [_list_item(_ACTIVE_ID, "widget-refactor", "plan_revision"),
                        _DONE_ITEM], "fail": None}
    _serve_list(page, holder)
    _navigate_to_loop(page, dashboard_fleet)
    _wait_header(page, "widget-refactor")

    holder["fail"] = fail
    page.wait_for_selector(".loop-refresh-failed", timeout=10000)
    st = _tab_state(page)
    assert st["create"]["text"] == "Active" and st["create"]["selected"] == "true"
    assert page.locator(".loop-create-workspace").count() == 0
    _wait_header(page, "widget-refactor")
    assert page.evaluate(
        "() => document.querySelector('.loop-workspace').dataset.polling") == "1"
    holder["fail"] = None
    page.wait_for_selector(".loop-refresh-failed", state="detached", timeout=10000)

    # Terminal under Primary while the list fails.
    holder["fail"] = fail
    _end_live_loop(payload, holder)
    page.wait_for_selector(".loop-refresh-failed", timeout=10000)
    page.wait_for_selector(".loop-outcome-badge, .loop-badge-outcome",
                           state="attached", timeout=10000)
    assert page.locator(".loop-create-workspace").count() == 0
    assert page.evaluate(
        "() => document.querySelector('.loop-workspace').dataset.polling") == "1"
    holder["fail"] = None
    page.wait_for_selector(".loop-create-workspace", timeout=10000)
    page.wait_for_selector(
        '#loop-main-content > .loop-transition-notice[data-kind="ended"]',
        timeout=5000)


def test_stale_primary_selection_retries_after_history(page, dashboard_fleet):
    """The active loop ends while a terminal History loop is shown (its
    timer stopped) and the list fails: back on the Active tab, the cached
    list routes to that loop, its terminal status shows in place with the
    refresh notice, and the timer keeps retrying; a valid list then lands
    Primary on Create."""
    payload = _live_payload()
    _serve_mutable_loop(page, payload)
    holder = {"loops": [_list_item(_ACTIVE_ID, "widget-refactor", "plan_revision"),
                        _DONE_ITEM], "fail": None}
    _serve_list(page, holder)
    _navigate_to_loop(page, dashboard_fleet)
    _wait_header(page, "widget-refactor")
    _select_loop_card(page, "auth-migration")
    page.wait_for_function(
        "() => document.querySelector('.loop-workspace').dataset.polling === '0'",
        timeout=10000)

    # The loop ends unobserved; the list cannot be read.
    payload["status"]["status"]["stage"] = "plan_approved"
    holder["fail"] = "http500"
    page.evaluate("() => document.querySelector('#loop-tab-create').click()")
    _wait_header(page, "widget-refactor")
    page.wait_for_selector(".loop-refresh-failed", timeout=10000)
    assert page.evaluate(
        "() => document.querySelector('.loop-workspace').dataset.polling") == "1"
    st = _tab_state(page)
    assert st["create"]["selected"] == "true" and st["create"]["text"] == "Active"
    assert page.locator(".loop-create-workspace").count() == 0

    holder["fail"] = None
    holder["loops"] = [_list_item(_ACTIVE_ID, "widget-refactor", "plan_approved"),
                       _DONE_ITEM]
    page.wait_for_selector(".loop-create-workspace", timeout=10000)
    page.wait_for_selector(
        '#loop-main-content > .loop-transition-notice[data-kind="ended"]',
        timeout=5000)
    assert page.evaluate(
        "() => document.querySelector('.loop-workspace').dataset.polling") == "0"


def test_initial_list_failure_retries(page, dashboard_fleet):
    """A failed first list shows "Loop list unavailable — retrying." with
    the "…" label and inert tabs (nothing claims Create); the next valid
    list lands on the default selection."""
    holder = {"loops": [_list_item(_ACTIVE_ID, "widget-refactor", "plan_revision"),
                        _DONE_ITEM], "fail": "http500"}
    _serve_list(page, holder)
    origin = dashboard_fleet["url"].rstrip("/") + "/"
    page.goto(origin + "?repo=alpha", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    _click_nav(page, "loop")
    notice = page.wait_for_selector(
        '.loop-primary-notice[data-kind="unavailable"]', timeout=10000)
    assert "retrying" in notice.text_content()
    assert page.evaluate(
        "() => document.querySelector('#loop-tab-create').textContent") == "\u2026"
    length = page.evaluate("() => history.length")
    page.evaluate("() => document.querySelector('#loop-tab-history').click()")
    assert _tab_state(page)["history"]["selected"] == "false"
    assert page.evaluate("() => history.length") == length
    assert page.evaluate(
        "() => document.querySelector('.loop-workspace').dataset.loaded") is None

    holder["fail"] = None
    page.wait_for_selector('.loop-workspace[data-loaded="1"]', state="attached",
                           timeout=10000)
    _wait_header(page, "widget-refactor")
    st = _tab_state(page)
    assert st["create"]["text"] == "Active" and st["create"]["selected"] == "true"
    assert page.locator('.loop-primary-notice[data-kind="unavailable"]').count() == 0


# ── #56 participant recovery ──────────────────────────────────────────────


def _lv_role(state):
    # Fixed timestamps: identical polls must render identical text.
    return {
        "state": state,
        "adapter_kind": None if state == "not_registered" else "generic-watcher",
        "last_seen_at": None if state == "not_registered" else "2026-09-22T10:00:00+00:00",
        "pending": 0, "last_notification": None,
        "renotify_eligible": False, "renotify_reason_code": "not_actionable",
    }


def _lv_view(draftor, reviewer):
    return {"schema": "gator-loop-liveness-view-v1", "available": True,
            "degraded": None,
            "roles": {"draftor": _lv_role(draftor), "reviewer": _lv_role(reviewer)},
            "audit": {"renotify_count": 0, "last_at": None, "last_actor": None}}


def _serve_liveness(page, holder):
    """Fulfil /liveness with holder["view"] (mutable between polls)."""
    def handler(route):
        route.fulfill(status=200, content_type="application/json",
                      headers={"Cache-Control": "no-store"},
                      body=json.dumps(holder["view"]))
    page.route("**/loops/*/liveness", handler)


def _serve_status_unjoined(page, role):
    """Pass /status through with one role marked as not joined."""
    def handler(route):
        resp = route.fetch()
        data = resp.json()
        data.setdefault("roles", {}).setdefault(role, {})["joined"] = False
        route.fulfill(status=resp.status, content_type="application/json",
                      headers={"Cache-Control": "no-store"},
                      body=json.dumps(data))
    page.route("**/loops/*/status", handler)


def _recovery(page):
    return page.evaluate("""() => {
        var d = document.querySelector('#loop-recovery');
        if (!d) return null;
        var out = {open: d.open, summary: d.querySelector('summary').textContent,
                   text: d.textContent, rows: {}};
        d.querySelectorAll('.loop-recovery-row').forEach(function (r) {
            var n = r.querySelector('.loop-recovery-need');
            out.rows[r.dataset.role] = {need: n.textContent, flag: n.dataset.need};
        });
        return out;
    }""")


def _open_recovery_loop(page, fleet):
    _navigate_to_loop(page, fleet)
    page.wait_for_selector(".loop-card", state="attached", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_selector("#loop-recovery", state="attached", timeout=10000)


@pytest.mark.parametrize("state", ["connected", "not_registered"])
def test_recovery_hidden_for_healthy_joined(page, dashboard_fleet, state):
    """Joined roles that are connected, or have no watcher at all (#52), need
    no recovery: the disclosure stays closed and the copy buttons exist but
    are not visible."""
    _serve_liveness(page, {"view": _lv_view(state, state)})
    try:
        _open_recovery_loop(page, dashboard_fleet)
        page.wait_for_selector(".loop-liveness-row .loop-liveness-state",
                               timeout=10000)
        page.wait_for_function(
            "() => document.querySelector('.loop-recovery-need').textContent !== ''",
            timeout=5000)
        page.wait_for_timeout(500)
        rec = _recovery(page)
        assert rec["open"] is False
        assert rec["summary"] == "Participant recovery"
        for r in ("draftor", "reviewer"):
            assert rec["rows"][r] == {"need": "Joined — no action needed",
                                      "flag": "0"}
        assert page.locator(".loop-prompt-copy").count() == 2
        assert not page.locator('.loop-prompt-copy[data-role="draftor"]').is_visible()
    finally:
        page.unroute("**/loops/*/liveness")


@pytest.mark.parametrize("case,need", [
    ("not_joined", "Has not joined yet."),
    ("stale", "Watcher is stale — reconnect if the session dropped."),
    ("released", "Watcher exited after a notification — reconnect if the session closed."),
])
def test_recovery_opens_for_need(page, dashboard_fleet, case, need):
    """A role that has not joined, or whose watcher is stale or released,
    opens the disclosure with its need, the guidance and the credential
    warning; Copy writes the clipboard and posts nothing but /prompt."""
    draftor_state = "connected" if case == "not_joined" else case
    _serve_liveness(page, {"view": _lv_view(draftor_state, "connected")})
    if case == "not_joined":
        _serve_status_unjoined(page, "draftor")
    posts = []
    page.on("request", lambda req: posts.append(req.url)
            if req.method == "POST" else None)
    page.route("**/loops/*/prompt", lambda route: route.fulfill(
        status=200, content_type="application/json",
        headers={"Cache-Control": "no-store"},
        body=json.dumps({"prompt": "RECOVERY-PROMPT-TEXT"})))
    try:
        _open_recovery_loop(page, dashboard_fleet)
        page.wait_for_function(
            "() => document.querySelector('#loop-recovery').open === true",
            timeout=10000)
        rec = _recovery(page)
        assert rec["rows"]["draftor"] == {"need": "⚠ " + need, "flag": "1"}
        assert rec["rows"]["reviewer"]["need"] == "Joined — no action needed"
        assert "Do not paste a prompt into a session that has already joined." in rec["text"]
        assert "The copied prompt carries a role credential." in rec["text"]
        assert page.evaluate(
            "() => getComputedStyle(document.querySelector("
            "'.loop-recovery-need[data-need=\"1\"]')).fontWeight") in ("700", "bold")

        page.context.grant_permissions(["clipboard-read", "clipboard-write"])
        page.click('.loop-prompt-copy[data-role="draftor"]')
        page.wait_for_function(
            "() => navigator.clipboard.readText().then(t => t === 'RECOVERY-PROMPT-TEXT')",
            timeout=5000)
        assert posts and all(u.endswith("/prompt") for u in posts), posts
    finally:
        for r in ("**/loops/*/liveness", "**/loops/*/status", "**/loops/*/prompt"):
            try:
                page.unroute(r)
            except Exception:
                pass


def test_recovery_user_toggle_survives_poll(page, dashboard_fleet):
    """The Architect's own toggle holds across polls until the need set
    changes; a change re-applies the automatic state."""
    holder = {"view": _lv_view("stale", "connected")}
    _serve_liveness(page, holder)
    try:
        _open_recovery_loop(page, dashboard_fleet)
        page.wait_for_function(
            "() => document.querySelector('#loop-recovery').open === true",
            timeout=10000)
        page.click("#loop-recovery summary")  # user closes it
        page.wait_for_function(
            "() => document.querySelector('#loop-recovery').open === false",
            timeout=5000)
        page.wait_for_timeout(7000)  # more than two polls, same need set
        assert page.evaluate("() => document.querySelector('#loop-recovery').open") is False
        holder["view"] = _lv_view("stale", "released")  # need set changes
        page.wait_for_function(
            "() => document.querySelector('#loop-recovery').open === true",
            timeout=10000)
        holder["view"] = _lv_view("connected", "connected")  # needs cleared
        page.wait_for_function(
            "() => document.querySelector('#loop-recovery').open === false",
            timeout=10000)
    finally:
        page.unroute("**/loops/*/liveness")


def test_recovery_poll_mutation_free(page, dashboard_fleet):
    """Identical polls make zero mutations in the recovery region, whether
    the disclosure is open or closed."""
    _serve_liveness(page, {"view": _lv_view("stale", "connected")})
    try:
        _open_recovery_loop(page, dashboard_fleet)
        page.wait_for_function(
            "() => document.querySelector('#loop-recovery').open === true",
            timeout=10000)
        page.wait_for_timeout(500)
        page.evaluate("""() => {
            window._m56r = 0;
            window._m56rNode = document.querySelector('#loop-recovery');
            new MutationObserver(function (m) { window._m56r += m.length; })
              .observe(document.querySelector('#loop-region-prompts'),
                       {subtree: true, childList: true, characterData: true,
                        attributes: true});
        }""")
        page.wait_for_timeout(7000)  # more than two polls
        assert page.evaluate("() => window._m56r") == 0
        assert page.evaluate("() => window._m56rNode.isConnected")
    finally:
        page.unroute("**/loops/*/liveness")
