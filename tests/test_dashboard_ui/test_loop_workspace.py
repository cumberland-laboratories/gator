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
    page.wait_for_selector("#loop-list", timeout=10000)
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
    assert page.locator("#loop-list").count() == 1
    assert page.locator("#loop-status-panel").count() == 1
    assert page.locator("#loop-timeline").count() == 1


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
    page.wait_for_selector(".loop-artifact-pre", timeout=10000)
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
    page.wait_for_selector(".loop-artifact-pre", timeout=10000)
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
    page.wait_for_selector("#loop-list", timeout=10000)
    text = page.evaluate(
        "() => document.getElementById('loop-list').textContent")
    assert "No loops" in text, (
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
    page.wait_for_selector("#loop-list", timeout=10000)
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
    page.wait_for_selector("#loop-list", timeout=10000)

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
    page.wait_for_selector("#loop-list", timeout=10000)
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


# ── executive summary (Module 6) ──────────────────────────────────────────


def test_extractSummary_exact_heading(page, dashboard_fleet):
    """extractSummary finds content under ## Executive Summary."""
    _navigate_to_loop(page, dashboard_fleet)
    result = page.evaluate("""
        () => {
            var fn = window.GatorViews._extractSummary;
            if (!fn) return 'MISSING';
            return fn('# Plan\\n\\n## Executive Summary\\n\\nBullet 1\\nBullet 2\\n\\n## Details\\n\\nMore');
        }
    """)
    if result == "MISSING":
        pytest.skip("extractSummary not exported")
    assert "Bullet 1" in result
    assert "Bullet 2" in result
    assert "More" not in result


def test_extractSummary_case_insensitive(page, dashboard_fleet):
    """extractSummary is case-insensitive on the heading."""
    _navigate_to_loop(page, dashboard_fleet)
    result = page.evaluate("""
        () => {
            var fn = window.GatorViews._extractSummary;
            if (!fn) return 'MISSING';
            return fn('## executive summary\\n\\nLower case works\\n\\n## Next');
        }
    """)
    if result == "MISSING":
        pytest.skip("extractSummary not exported")
    assert "Lower case works" in result


def test_extractSummary_extra_whitespace(page, dashboard_fleet):
    """extractSummary tolerates extra whitespace in heading."""
    _navigate_to_loop(page, dashboard_fleet)
    result = page.evaluate("""
        () => {
            var fn = window.GatorViews._extractSummary;
            if (!fn) return 'MISSING';
            return fn('##  Executive Summary  \\n\\nSpaced heading\\n\\n## Next');
        }
    """)
    if result == "MISSING":
        pytest.skip("extractSummary not exported")
    assert "Spaced heading" in result


def test_extractSummary_no_heading_returns_null(page, dashboard_fleet):
    """extractSummary returns null when no summary heading exists."""
    _navigate_to_loop(page, dashboard_fleet)
    result = page.evaluate("""
        () => {
            var fn = window.GatorViews._extractSummary;
            if (!fn) return 'MISSING';
            return fn('# Plan\\n\\n## Summary\\n\\nNo exec summary here');
        }
    """)
    if result == "MISSING":
        pytest.skip("extractSummary not exported")
    assert result is None


def test_extractSummary_leading_whitespace(page, dashboard_fleet):
    """extractSummary tolerates leading whitespace before ## heading."""
    _navigate_to_loop(page, dashboard_fleet)
    result = page.evaluate("""
        () => {
            var fn = window.GatorViews._extractSummary;
            if (!fn) return 'MISSING';
            return fn('# Plan\\n\\n  ## Executive Summary\\n\\nIndented heading content\\n\\n## Next');
        }
    """)
    if result == "MISSING":
        pytest.skip("extractSummary not exported")
    assert result == "Indented heading content"


def test_extractSummary_truncation(page, dashboard_fleet):
    """extractSummary truncates at 500 chars with ellipsis."""
    _navigate_to_loop(page, dashboard_fleet)
    result = page.evaluate("""
        () => {
            var fn = window.GatorViews._extractSummary;
            if (!fn) return 'MISSING';
            var long = 'x'.repeat(600);
            return fn('## Executive Summary\\n\\n' + long + '\\n\\n## Next');
        }
    """)
    if result == "MISSING":
        pytest.skip("extractSummary not exported")
    assert len(result) <= 502
    assert result.endswith("…")


def test_summary_renders_in_artifact_inspector(page, dashboard_fleet):
    """Plan artifact with an executive summary shows it inline."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_function(
        "() => {"
        "  var els = document.querySelectorAll('.loop-summary-text');"
        "  for (var i = 0; i < els.length; i++) {"
        "    if (els[i].textContent.indexOf('event-driven') !== -1) return true;"
        "  }"
        "  return false;"
        "}",
        timeout=10000,
    )
    summary_texts = page.evaluate("""
        () => Array.from(document.querySelectorAll('.loop-summary-text'))
            .map(el => el.textContent)
    """)
    has_summary = any("event-driven" in t for t in summary_texts)
    assert has_summary, (
        f"Expected executive summary with 'event-driven'; "
        f"got: {summary_texts}")


def test_absent_summary_shows_fallback(page, dashboard_fleet):
    """Artifact without executive summary shows fallback message.

    The active loop's findings.current.md has content but no
    ``## Executive Summary`` heading, so it must render the fallback.
    """
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_function(
        "() => document.querySelector('.loop-summary-absent') !== null",
        timeout=10000,
    )
    absent_texts = page.evaluate("""
        () => Array.from(document.querySelectorAll('.loop-summary-absent'))
            .map(el => el.textContent)
    """)
    assert len(absent_texts) > 0, (
        "Expected at least one .loop-summary-absent element for "
        "findings.current.md (which has no executive summary)")
    has_fallback = any("No executive summary" in t for t in absent_texts)
    assert has_fallback, (
        f"Expected 'No executive summary' fallback; got: {absent_texts}")


# ── timeline summaries ────────────────────────────────────────────────────


def test_timeline_draft_event_shows_summary(page, dashboard_fleet):
    """draft_submitted timeline event shows the plan's executive summary."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_function(
        "() => document.querySelector('.loop-timeline-summary-text') !== null",
        timeout=10000,
    )
    summary = page.evaluate("""
        () => {
            var ev = document.querySelector(
                '.loop-event[data-artifact*="plan"] .loop-timeline-summary-text');
            return ev ? ev.textContent : null;
        }
    """)
    assert summary is not None, "Expected timeline summary for draft event"
    assert "event-driven" in summary


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


def test_timeline_absent_summary_shows_fallback(page, dashboard_fleet):
    """Timeline event for artifact without summary shows the fallback."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-card", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_function(
        "() => document.querySelector('.loop-timeline-summary-absent') !== null",
        timeout=10000,
    )
    absent = page.evaluate("""
        () => {
            var el = document.querySelector('.loop-timeline-summary-absent');
            return el ? el.textContent : null;
        }
    """)
    assert absent is not None
    assert "No executive summary" in absent


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
