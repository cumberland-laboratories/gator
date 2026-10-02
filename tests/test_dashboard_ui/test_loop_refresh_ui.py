"""#44 — selected-loop refresh-failure visibility (Playwright).

A failed background poll of /status or /events keeps the last valid
workspace (content, artifacts, open Architect controls, expanded sections)
and shows a text-led "Refresh failed — retrying" notice in the poll-owned
notice slot. The next successful refresh clears only that notice. Stale
in-flight responses cannot touch a newer selection, initial-load failure
keeps its existing behavior, and repeated failures cause no mutations.
"""

import json
import threading

from .test_loop_workspace import (
    _ACTIVE_ID, _live_payload, _navigate_to_loop, _select_loop_card)


def serve(page, holder):
    """Serve status/events for the active loop; flags force failures."""
    def status(route):
        gate = holder.get("status_gate")
        if gate is not None:
            holder["status_waiting"].set()
            gate.wait(10)
        if holder.get("fail_status"):
            route.fulfill(status=500, content_type="application/json",
                          body='{"error": "boom"}')
        else:
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps(holder["payload"]["status"]))

    def events(route):
        if holder.get("fail_events"):
            route.fulfill(status=500, content_type="application/json",
                          body='{"error": "boom"}')
        else:
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"events": holder["payload"]["events"]}))
    page.route("**/" + _ACTIVE_ID + "/status", status)
    page.route("**/" + _ACTIVE_ID + "/events", events)


def unserve(page):
    for s in ("status", "events"):
        try:
            page.unroute("**/" + _ACTIVE_ID + "/" + s)
        except Exception:
            pass


def open_view(page, fleet, holder):
    serve(page, holder)
    _navigate_to_loop(page, fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_selector(".loop-artifact-section", timeout=10000)
    page.wait_for_selector(".loop-event", timeout=10000)


def snapshot_view(page):
    return page.evaluate("""() => ({
        header: document.querySelector('#loop-region-header').textContent,
        events: document.querySelectorAll('#loop-timeline .loop-event').length,
        artifacts: Array.from(document.querySelectorAll(
            '.loop-artifact-section')).map(s => s.dataset.artifact),
    })""")


def refresh_notice(page):
    return page.evaluate("""() => {
        var s = document.querySelector('#loop-region-notice [data-slot="refresh"]');
        return s ? s.textContent : null;
    }""")


def test_status_failure_keeps_workspace_and_recovers(page, dashboard_fleet):
    holder = {"payload": _live_payload()}
    try:
        open_view(page, dashboard_fleet, holder)
        # Open an Architect control and expand an artifact before failing.
        page.evaluate("""() => document.querySelector(
            '.loop-ctrl-btn[data-action="interject"]').click()""")
        page.wait_for_selector(".loop-ctrl-input", timeout=5000)
        page.fill(".loop-ctrl-input", "half-typed guidance")
        page.evaluate("""() => document.querySelector(
            '.loop-artifact-section[data-artifact="sketch.md"] .loop-artifact-toggle').click()""")
        page.wait_for_function("""() => {
            var c = document.querySelector(
              '.loop-artifact-section[data-artifact="sketch.md"] .loop-artifact-content');
            return c && c.dataset.loaded === '1';
        }""", timeout=5000)
        before = snapshot_view(page)
        assert refresh_notice(page) == ""

        holder["fail_status"] = True
        page.wait_for_selector(".loop-refresh-failed", timeout=10000)
        assert refresh_notice(page).startswith("Refresh failed — retrying.")
        assert snapshot_view(page) == before
        assert page.evaluate(
            "() => document.querySelector('.loop-ctrl-input').value") == \
            "half-typed guidance"
        assert page.evaluate("""() => document.querySelector(
            '.loop-artifact-section[data-artifact="sketch.md"] .loop-artifact-content')
            .style.display""") == "block"
        assert page.evaluate(
            "() => document.querySelector('.loop-workspace').dataset.polling") == "1"

        holder["fail_status"] = False
        page.wait_for_function("""() => !document.querySelector(
            '#loop-region-notice .loop-refresh-failed')""", timeout=10000)
        assert refresh_notice(page) == ""
        assert page.evaluate(
            "() => document.querySelector('.loop-ctrl-input').value") == \
            "half-typed guidance"

        # A later failure shows it again.
        holder["fail_status"] = True
        page.wait_for_selector(".loop-refresh-failed", timeout=10000)
    finally:
        unserve(page)


def test_events_failure_never_prunes_artifacts(page, dashboard_fleet):
    """A failed /events poll must not be rendered as an empty history
    (which would drop event-derived artifact sections)."""
    holder = {"payload": _live_payload()}
    try:
        open_view(page, dashboard_fleet, holder)
        before = snapshot_view(page)
        assert "plan.round-1.md" in before["artifacts"]
        holder["fail_events"] = True
        page.wait_for_selector(".loop-refresh-failed", timeout=10000)
        page.wait_for_timeout(3500)  # another failing poll
        assert snapshot_view(page) == before
        holder["fail_events"] = False
        page.wait_for_function("""() => !document.querySelector(
            '#loop-region-notice .loop-refresh-failed')""", timeout=10000)
        after = snapshot_view(page)
        # The live countdown in the header resumes ticking after recovery;
        # history and artifacts are exactly as before.
        assert after["events"] == before["events"]
        assert after["artifacts"] == before["artifacts"]
    finally:
        unserve(page)


def test_recovery_keeps_architect_action_notice(page, dashboard_fleet):
    holder = {"payload": _live_payload()}
    try:
        open_view(page, dashboard_fleet, holder)
        page.evaluate("""() => {
            document.querySelector('#loop-region-notice [data-slot="action"]')
              .innerHTML = '<div class="loop-extend-notice">Extended: keep me</div>';
        }""")
        holder["fail_status"] = True
        page.wait_for_selector(".loop-refresh-failed", timeout=10000)
        holder["fail_status"] = False
        page.wait_for_function("""() => !document.querySelector(
            '#loop-region-notice .loop-refresh-failed')""", timeout=10000)
        assert "Extended: keep me" in page.inner_text("#loop-region-notice")
    finally:
        unserve(page)


def test_repeated_failures_cause_no_mutations(page, dashboard_fleet):
    holder = {"payload": _live_payload()}
    try:
        open_view(page, dashboard_fleet, holder)
        holder["fail_status"] = True
        page.wait_for_selector(".loop-refresh-failed", timeout=10000)
        page.evaluate("""() => {
            window.__mut = 0;
            new MutationObserver(r => { window.__mut += r.length; })
              .observe(document.querySelector('#loop-main-content'),
                       {childList: true, subtree: true, characterData: true,
                        attributes: true});
        }""")
        page.wait_for_timeout(7000)  # >= two failing polls
        assert page.evaluate("() => window.__mut") == 0
    finally:
        unserve(page)


def test_stale_failure_cannot_touch_new_selection(page, dashboard_fleet):
    """A poll for selection A that fails after the Architect selected B must
    not set a refresh notice on B."""
    holder = {"payload": _live_payload()}
    try:
        open_view(page, dashboard_fleet, holder)
        holder["status_waiting"] = threading.Event()
        holder["status_gate"] = threading.Event()
        holder["fail_status"] = True
        # Wait until A's poll is blocked in flight, then switch to B.
        for _ in range(100):
            if holder["status_waiting"].is_set():
                break
            page.wait_for_timeout(100)
        assert holder["status_waiting"].is_set()
        _select_loop_card(page, "auth-migration")
        holder["status_gate"].set()
        page.wait_for_timeout(1500)
        assert page.locator(".loop-refresh-failed").count() == 0
        assert refresh_notice(page) in ("", None)
    finally:
        holder.get("status_gate", threading.Event()).set()
        unserve(page)


def test_initial_load_failure_keeps_existing_behavior(page, dashboard_fleet):
    holder = {"payload": _live_payload(), "fail_status": True}
    try:
        serve(page, holder)
        _navigate_to_loop(page, dashboard_fleet)
        page.wait_for_selector("#loop-main-content", timeout=10000)
        page.wait_for_timeout(4000)
        assert page.locator(".loop-refresh-failed").count() == 0
    finally:
        unserve(page)
