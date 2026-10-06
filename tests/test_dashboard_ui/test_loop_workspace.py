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
from pathlib import Path

import pytest


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
    page.wait_for_selector("#loop-sidebar-nav", timeout=10000)
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


def test_loop_view_renders_workspace_layout(page, dashboard_fleet):
    """Clicking the Loop tab renders the workspace with list and
    main panel sections."""
    _navigate_to_loop(page, dashboard_fleet)
    assert page.locator(".loop-workspace").count() == 1
    assert page.locator("#loop-sidebar-nav").count() == 1
    assert page.locator("#loop-main-content").count() == 1


# ── loop list ────────────────────────────────────────────────────────────────


def test_loop_list_renders_cards(page, dashboard_fleet):
    """Loop list shows cards with feature names."""
    _navigate_to_loop(page, dashboard_fleet)
    cards = page.locator(".loop-card")
    assert cards.count() >= 2, "Expected at least 2 loop cards"
    features = page.evaluate("""
        () => Array.from(document.querySelectorAll('.loop-card-feature'))
            .map(el => el.textContent)
    """)
    assert "widget-refactor" in features
    assert "auth-migration" in features


def test_loop_list_active_first_sort(page, dashboard_fleet):
    """Active/paused loops sort before terminal loops."""
    _navigate_to_loop(page, dashboard_fleet)
    badges = page.evaluate("""
        () => Array.from(document.querySelectorAll('.loop-card .loop-badge'))
            .map(el => el.textContent)
    """)
    assert len(badges) >= 2
    terminal_idx = None
    for i, badge in enumerate(badges):
        if badge == "Approved":
            terminal_idx = i
            break
    if terminal_idx is not None:
        for i in range(terminal_idx):
            assert badges[i] != "Approved", (
                f"Terminal badge at index {i} should not appear before "
                f"active badges")


# ── status panel ─────────────────────────────────────────────────────────────


def test_status_panel_renders_on_loop_select(page, dashboard_fleet):
    """Selecting a loop populates the status panel with stage badge
    and round info."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    has_badge = page.locator(".loop-status-header .loop-badge").count() > 0
    assert has_badge, "Status header should contain a stage badge"
    round_text = page.evaluate("""
        () => {
            const items = document.querySelectorAll('.loop-status-value');
            for (const item of items) {
                if (item.textContent.includes('/')) return item.textContent;
            }
            return null;
        }
    """)
    assert round_text is not None, "Status panel should show round N/M"


def test_status_panel_shows_role_state(page, dashboard_fleet):
    """Status panel shows Draftor/Reviewer joined state."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    labels = page.evaluate("""
        () => Array.from(document.querySelectorAll('.loop-status-label'))
            .map(el => el.textContent)
    """)
    assert "Draftor" in labels
    assert "Reviewer" in labels


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
    """Click a loop card by feature name and wait for the status
    panel to reflect the selection (avoids race with async load).

    Clears the status header before clicking so wait_for_function
    distinguishes a fresh render from a stale one left by a prior
    loadSelectedLoop that happened to select the same loop.
    """
    page.evaluate("""
        (name) => {
            var h = document.querySelector('.loop-status-header h3');
            if (h) h.textContent = '';
            var cards = document.querySelectorAll('.loop-card');
            for (var i = 0; i < cards.length; i++) {
                if (cards[i].querySelector('.loop-card-feature').textContent === name) {
                    cards[i].click(); break;
                }
            }
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


def test_artifact_toggle_loads_content(page, dashboard_fleet):
    """Clicking an artifact toggle fetches and displays content."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card", timeout=10000)
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
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card", timeout=10000)
    _select_loop_card(page, "xss-test")
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
        route.continue_()
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
    page.wait_for_selector("#loop-sidebar-nav", timeout=10000)
    text = page.evaluate(
        "() => document.getElementById('loop-sidebar-nav').textContent")
    assert "No active loop" in text, (
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
        route.continue_()
    page.route("**/api/repo-by-key/*/loops*", _capture)
    page.evaluate(
        "() => document.querySelector('.sidebar-item[data-view=\"loop\"]').click()"
    )
    page.wait_for_selector("#loop-sidebar-nav", timeout=10000)
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
    page.wait_for_selector("#loop-sidebar-nav", timeout=10000)

    page.evaluate(
        "() => document.querySelector("
        "'.sidebar-item[data-view=\"repo\"]').click()"
    )
    page.wait_for_selector(".repo-file-item", timeout=15000)

    gate.set()
    page.wait_for_timeout(1500)

    page.unroute("**/api/repo-by-key/*/loops")

    assert page.locator(".loop-workspace").count() == 0, (
        "Loop workspace should not exist after navigating away")

    poll_count = [0]

    def _count(route):
        poll_count[0] += 1
        route.continue_()

    page.route("**/api/repo-by-key/*/loops**", _count)
    page.wait_for_timeout(4000)
    page.unroute("**/api/repo-by-key/*/loops**")
    assert poll_count[0] == 0, (
        f"Expected zero poll requests after departed mount, "
        f"but {poll_count[0]} observed")


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
        route.continue_()

    page.route("**/api/repo-by-key/*/loops*", _capture)

    page.evaluate(
        "() => document.querySelector("
        "'.sidebar-item[data-view=\"loop\"]').click()"
    )
    page.wait_for_selector("#loop-sidebar-nav", timeout=10000)
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
    page.wait_for_selector(".loop-card", timeout=10000)
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
            route.continue_()
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


def test_timeline_card_is_link_only(page, dashboard_fleet):
    """An event with an artifact shows the link immediately and no excerpt."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_selector(".loop-event[data-artifact]", timeout=10000)
    cards = page.evaluate("""() => Array.from(
        document.querySelectorAll('#loop-timeline .loop-event[data-artifact]'))
        .map(c => ({
            artifact: c.dataset.artifact,
            links: Array.from(c.querySelectorAll('.loop-timeline-artifact-link'))
                .map(a => ({text: a.textContent, artifact: a.dataset.artifact,
                            href: a.getAttribute('href')})),
            excerpt: c.querySelectorAll('.loop-event-summary, '
                + '.loop-timeline-summary-text, .loop-timeline-summary-absent').length,
        }))""")
    assert cards, "expected timeline events with artifacts"
    for c in cards:
        assert len(c["links"]) == 1, c
        link = c["links"][0]
        assert link["text"] == "View full artifact"
        assert link["artifact"] == c["artifact"]
        assert link["href"] == "#"          # keyboard-focusable
        assert c["excerpt"] == 0, c
    assert page.evaluate(
        "() => window.GatorViews && window.GatorViews._extractSummary") is None


def test_event_without_artifact_has_no_link(page, dashboard_fleet):
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card", timeout=10000)
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
    page.wait_for_selector(".loop-card", timeout=10000)
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
             "role": "draftor", "artifact_path": "plan.round-2.md"})
        page.wait_for_selector(
            '.loop-event[data-artifact="plan.round-2.md"] .loop-timeline-artifact-link',
            timeout=10000)
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
    page.wait_for_selector(".loop-card", timeout=10000)
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
    page.wait_for_selector(".loop-card", timeout=10000)
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
    page.wait_for_selector(".loop-card", timeout=10000)
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
    page.wait_for_selector(".loop-card", timeout=10000)
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


def test_sidebar_three_sections(page, dashboard_fleet):
    """B1: sidebar renders Create Loop, Active header, History header."""
    _navigate_to_loop(page, dashboard_fleet)
    headers = page.evaluate("""
        () => Array.from(document.querySelectorAll('.loop-sidebar-section-header'))
            .map(el => el.textContent)
    """)
    assert "Active" in headers
    assert "History" in headers
    has_create = page.locator(".loop-sidebar-create").count() > 0
    assert has_create, "Create Loop action should be present"


def test_sidebar_active_and_history_classification(page, dashboard_fleet):
    """B2: active loops in Active section, terminal in History."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-sidebar-section", timeout=10000)
    sections = page.evaluate("""
        () => {
            var secs = document.querySelectorAll('.loop-sidebar-section');
            var result = [];
            for (var i = 0; i < secs.length; i++) {
                var header = secs[i].querySelector('.loop-sidebar-section-header');
                var features = Array.from(secs[i].querySelectorAll('.loop-card-feature'))
                    .map(el => el.textContent);
                result.push({ header: header ? header.textContent : '', features: features });
            }
            return result;
        }
    """)
    active_sec = [s for s in sections if s["header"] == "Active"][0]
    history_sec = [s for s in sections if s["header"] == "History"][0]
    assert "auth-migration" in history_sec["features"], (
        "Terminal loop should be in History section")
    assert "auth-migration" not in active_sec["features"], (
        "Terminal loop should not be in Active section")


def test_sidebar_empty_sections(page, dashboard_fleet):
    """B3: repo with no loops shows empty-state text in both sections."""
    origin = dashboard_fleet["url"].rstrip("/") + "/"
    page.goto(origin + "?repo=beta", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    page.evaluate(
        "() => document.querySelector('.sidebar-item[data-view=\"loop\"]').click()"
    )
    page.wait_for_selector("#loop-sidebar-nav", timeout=10000)
    text = page.evaluate(
        "() => document.getElementById('loop-sidebar-nav').textContent")
    assert "No active loop" in text
    assert "No completed loops" in text


def test_sidebar_create_disabled_when_active(page, dashboard_fleet):
    """B4: active loop exists → Create shows conflict, Open link works."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-sidebar-create", timeout=10000)
    is_disabled = page.evaluate("""
        () => document.querySelector('.loop-sidebar-create')
            .classList.contains('loop-sidebar-create-disabled')
    """)
    assert is_disabled, "Create should be disabled when active loop exists"
    has_open_link = page.locator(".loop-sidebar-open-active").count() > 0
    assert has_open_link, "Should show 'Open active loop' link"


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


def test_creation_409_shows_open_active(page, dashboard_fleet):
    """B12: 409 race recovery shows 'Open active loop' message."""
    import json as _json

    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-sidebar-create", timeout=10000)

    # Intercept loops list to report no active loop (so Create enables)
    page.route("**/api/repo-by-key/*/loops", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=_json.dumps({"loops": []})))
    # Intercept sketch sources to return empty (so manual input shows)
    page.route("**/sketch-sources", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=_json.dumps({"sources": []})))

    # Re-navigate to get fresh state with empty loops
    page.evaluate(
        "() => document.querySelector('.sidebar-item[data-view=\"loop\"]').click()"
    )
    page.wait_for_selector("#loop-create-action", timeout=10000)

    # Intercept start to return 409
    page.route("**/loops/start", lambda route: route.fulfill(
        status=409, content_type="application/json",
        body=_json.dumps({"error": "active loop exists", "loop_id": "test-loop"})))

    # Wait for manual input to be visible (no sources → shown by default)
    page.wait_for_selector("#loop-sketch-manual", timeout=5000)

    # Fill form and submit
    page.fill("#loop-feature-input", "test-feature")
    page.fill("#loop-sketch-manual", ".gator/artifacts/test.md")
    page.evaluate("() => document.querySelector('#loop-create-action').click()")

    page.wait_for_selector("#loop-create-error", timeout=5000)
    page.wait_for_function(
        "() => document.querySelector('#loop-create-error').style.display !== 'none'",
        timeout=5000)
    error_text = page.evaluate(
        "() => document.querySelector('#loop-create-error').textContent")
    assert "active" in error_text.lower()
    assert page.locator(".loop-create-open-active").count() == 1

    page.unroute("**/api/repo-by-key/*/loops")
    page.unroute("**/loops/start")
    page.unroute("**/sketch-sources")


# ── live vs history workspace (Module 5 / B18–B23) ────────────────────────


def test_active_loop_shows_controls_and_prompts(page, dashboard_fleet):
    """B18: active loop shows controls and prompt copy."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_selector(".loop-ctrl-btn", timeout=10000)
    assert page.locator(".loop-ctrl-btn").count() > 0
    assert page.locator(".loop-prompt-copy").count() == 2


def test_terminal_loop_read_only(page, dashboard_fleet):
    """B19: terminal loop shows outcome badge, no controls, no prompts."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card", timeout=10000)
    _select_loop_card(page, "auth-migration")
    page.wait_for_selector(".loop-badge-outcome", timeout=10000)
    assert page.locator(".loop-badge-outcome").count() > 0
    assert page.locator(".loop-ctrl-btn").count() == 0
    assert page.locator(".loop-prompt-copy").count() == 0
    has_outcome_meta = page.locator(".loop-outcome-meta").count() > 0
    assert has_outcome_meta, "Terminal loop should show outcome meta"


def test_blocked_loop_shows_prominent_card(page, dashboard_fleet):
    """B20: blocked loop shows prominent blocked card with decision link."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card", timeout=10000)
    _select_loop_card(page, "blocked-feature")
    page.wait_for_selector(".loop-blocked-card", timeout=10000)
    reason = page.evaluate(
        "() => document.querySelector('.loop-blocked-reason').textContent")
    assert "scope" in reason.lower()
    assert page.locator(".loop-blocked-artifact-link").count() == 1


def test_blocked_card_decision_link_opens_inspector(page, dashboard_fleet):
    """B21: clicking decision link opens inspector section with content."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card", timeout=10000)
    _select_loop_card(page, "blocked-feature")
    page.wait_for_selector(".loop-blocked-artifact-link", timeout=10000)
    artifact_name = page.evaluate(
        "() => document.querySelector('.loop-blocked-artifact-link').dataset.artifact")
    assert "decision-request" in artifact_name
    page.evaluate(
        "() => document.querySelector('.loop-blocked-artifact-link').click()")
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
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card", timeout=10000)
    _select_loop_card(page, "roundzero-test")
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
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card", timeout=10000)
    _select_loop_card(page, "blocked-feature")
    page.wait_for_selector(".loop-blocked-artifact-link", timeout=10000)
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
    page.wait_for_selector(".loop-sidebar-section", timeout=10000)

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
    page.wait_for_selector(".loop-sidebar-section", timeout=10000)

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
        else route.continue_()
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

    # Intercept to show no loops → create workspace
    page.route("**/api/repo-by-key/*/loops", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=_json.dumps({"loops": []})))
    page.route("**/sketch-sources", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=_json.dumps({"sources": []})))
    page.route("**/loops/start", lambda route: route.fulfill(
        status=201, content_type="application/json",
        body=_json.dumps({"loop_id": "handoff-loop"})))
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

    page.evaluate("() => document.querySelector('#loop-handoff-open').click()")
    # Should transition to the selected loop workspace
    page.wait_for_selector(".loop-status-header", timeout=10000)
    assert page.locator(".loop-handoff").count() == 0, (
        "Handoff view should be gone after clicking Open workspace")


# ── terminal handoff credential removal ──────────────────────────────────


def test_terminal_handoff_disables_copy_buttons(page, dashboard_fleet):
    """Terminal status during handoff disables copy buttons, removes
    fallback textareas, shows outcome badge, stops polling."""
    import json as _json

    _enter_handoff(page, dashboard_fleet)

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
    page.wait_for_selector(".loop-card", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_selector(".loop-prompt-copy", timeout=10000)

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
    page.wait_for_selector(".loop-card", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_selector(".loop-prompt-copy", timeout=10000)

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
    # Remember node identities and count main-panel mutations, ignoring the
    # text-only countdown patch.
    page.evaluate("""() => {
        var q = s => document.querySelector(s);
        window.__nodes = {
            root: q('#loop-main-content .loop-detail'),
            header: q('#loop-region-header').firstElementChild,
            controls: q('#loop-controls').firstElementChild,
            firstEvent: q('#loop-timeline').firstElementChild,
            sketch: q('.loop-artifact-section[data-artifact="sketch.md"]'),
        };
        window.__mutations = 0;
        window.__emptied = false;
        var main = q('#loop-main-content');
        new MutationObserver(function (records) {
            records.forEach(function (r) {
                var t = r.target.nodeType === 3 ? r.target.parentElement : r.target;
                if (t && t.closest && t.closest('.loop-time-remaining')) return;
                window.__mutations++;
            });
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
    for key in ("root", "header", "controls", "firstEvent", "sketch"):
        assert _same(page, key), f"{key} node was replaced by an identical poll"
    assert page.evaluate("() => window.__mutations") == 0
    assert page.evaluate("() => window.__emptied") is False
    _unserve_mutable_loop(page)


def test_status_change_patches_header_preserves_artifacts_and_timeline(page, dashboard_fleet):
    payload = _live_payload()
    _open_incremental(page, dashboard_fleet, payload)
    _expand_sketch(page)

    st = payload["status"]["status"]
    st.update({"stage": "plan_review", "next_role": "reviewer",
               "last_updated": "2026-09-22T10:05:00+00:00"})
    page.wait_for_function("""() => {
        var h = document.querySelector('#loop-region-header');
        return h && h.textContent.indexOf('reviewer') !== -1;
    }""", timeout=8000)

    assert _same(page, "root")
    assert not _same(page, "header"), "header should be re-rendered on a status change"
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
    assert names[:3] == ["sketch.md", "plan.current.md", "findings.current.md"]
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
    assert page.evaluate(
        "() => document.querySelector('.loop-ctrl-input-area').style.display") == "flex"
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


def test_terminal_transition_patches_in_place_and_stops_polling(page, dashboard_fleet):
    payload = _live_payload()
    _open_incremental(page, dashboard_fleet, payload)
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
    assert "Extended" in page.inner_text("#loop-timeline .loop-event:last-child")
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
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card", timeout=10000)
    _select_loop_card(page, "blocked-feature")
    page.wait_for_selector(".loop-decision-card", timeout=10000)
    card = page.evaluate("""() => {
        var c = document.querySelector('.loop-decision-card');
        var r = c.querySelector('.loop-blocked-reason');
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
    assert full[0]["text"].endswith(reason) and full[1]["text"].endswith(response)
    assert all(d["ws"] == "pre-wrap" and not d["clipped"] for d in full)
    compact = [d for d in details if not d["full"]]
    assert compact and all(d["ws"] == "nowrap" for d in compact)
    page.unroute("**/loops/*/status")
    page.unroute("**/loops/*/events")
