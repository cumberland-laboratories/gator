"""#47 M5 — Architect attention interval in the Loop workspace (Playwright).

Attention-mode loops show elapsed turn time (not a countdown) and a
text-led, non-error "Attention" notice in its own notice slot once the
durable notice exists. Legacy loops keep their countdown. Identical polls
stay mutation-free apart from the single permitted elapsed-text patch; the
notice never erases an action notice or an open Architect control. The
unblock control offers no turn-window field, and the create form posts
``attention_interval``.
"""

import json

import pytest
from datetime import datetime, timedelta, timezone

from .test_loop_workspace import (
    _ACTIVE_ID, _live_payload, _navigate_to_loop, _open_incremental,
    _serve_mutable_loop, _unserve_mutable_loop)
from .test_loop_brief_ui import open_create, unroute_create


def _attention_payload(elapsed=420, notified=False, due=None, host=None):
    payload = _live_payload()
    st = payload["status"]["status"]
    started = (datetime.now(tz=timezone.utc) - timedelta(seconds=elapsed)).isoformat()
    st["turn_deadline"] = None
    st["turn_started_at"] = started
    st["attention_notified_turn"] = started if notified else None
    payload["status"]["attention"] = {
        "interval_seconds": 300, "turn_started_at": started,
        "notified_turn": started if notified else None,
        "notified": notified,
        "due": (elapsed >= 300) if due is None else due,
        "host": host,
    }
    return payload


def _slot(page, name):
    return page.evaluate("""n => {
        var s = document.querySelector('#loop-region-notice [data-slot="' + n + '"]');
        return s ? s.textContent : null;
    }""", name)


def _count_non_elapsed_mutations(page):
    page.evaluate("""() => {
        window.__m2 = 0;
        new MutationObserver(function (records) {
            records.forEach(function (r) {
                var t = r.target.nodeType === 3 ? r.target.parentElement : r.target;
                if (t && t.closest && (t.closest('.loop-elapsed')
                                       || t.closest('.loop-time-remaining'))) return;
                window.__m2++;
            });
        }).observe(document.querySelector('#loop-main-content'),
                   {childList: true, subtree: true, characterData: true, attributes: true});
    }""")


def test_elapsed_header_replaces_countdown(page, dashboard_fleet):
    payload = _attention_payload(elapsed=90)
    try:
        _open_incremental(page, dashboard_fleet, payload)
        header = page.evaluate("() => document.querySelector('#loop-region-header').textContent")
        assert "Elapsed this turn" in header
        assert "attention after 5 min" in header
        assert "Time Remaining" not in header
        assert _slot(page, "attention") == ""  # not due yet
    finally:
        _unserve_mutable_loop(page)


def test_notice_appears_once_and_polls_stay_quiet(page, dashboard_fleet):
    payload = _attention_payload(elapsed=420, notified=True)
    try:
        _open_incremental(page, dashboard_fleet, payload)
        page.wait_for_function("""() => {
            var s = document.querySelector('#loop-region-notice [data-slot="attention"]');
            return s && s.textContent.indexOf('Attention:') !== -1;
        }""", timeout=8000)
        text = _slot(page, "attention")
        assert "Draftor has been active for at least 5 min in revision" in text
        assert "no action is required" in text and "◷" in text
        assert page.evaluate("""() => document.querySelector(
            '.loop-attention-notice').getAttribute('role')""") == "status"
        _count_non_elapsed_mutations(page)
        page.wait_for_timeout(7000)  # >= two identical polls
        assert page.evaluate("() => window.__m2") == 0
    finally:
        _unserve_mutable_loop(page)


@pytest.mark.parametrize("host,expect,forbid", [
    ("none", "no loop host is running for this loop", "pending"),
    ("attached", "notice pending", "no loop host"),
    (None, "no notice has been recorded for this turn yet", "no loop host"),
], ids=["no-host", "attached", "unknown"])
def test_unrecorded_text_follows_authoritative_host_state(page, dashboard_fleet,
                                                          host, expect, forbid):
    payload = _attention_payload(elapsed=420, notified=False, host=host)
    try:
        _open_incremental(page, dashboard_fleet, payload)
        page.wait_for_function("""() => {
            var s = document.querySelector('#loop-region-notice [data-slot="attention"]');
            return s && s.textContent.indexOf('Attention interval passed') !== -1;
        }""", timeout=8000)
        text = _slot(page, "attention")
        assert expect in text and forbid not in text
        assert "is a loop host running" not in text
    finally:
        _unserve_mutable_loop(page)


def test_host_state_change_updates_notice(page, dashboard_fleet):
    payload = _attention_payload(elapsed=420, notified=False, host="none")
    try:
        _open_incremental(page, dashboard_fleet, payload)
        page.wait_for_function("""() => {
            var s = document.querySelector('#loop-region-notice [data-slot="attention"]');
            return s && s.textContent.indexOf('no loop host is running') !== -1;
        }""", timeout=8000)
        payload["status"]["attention"]["host"] = "attached"
        page.wait_for_function("""() => {
            var s = document.querySelector('#loop-region-notice [data-slot="attention"]');
            return s && s.textContent.indexOf('notice pending') !== -1;
        }""", timeout=8000)
    finally:
        _unserve_mutable_loop(page)


def test_notice_coexists_with_action_notice_and_open_control(page, dashboard_fleet):
    payload = _attention_payload(elapsed=90)
    try:
        _open_incremental(page, dashboard_fleet, payload)
        # An Architect action notice and an open interject control.
        page.evaluate("""() => {
            document.querySelector('#loop-region-notice [data-slot="action"]')
              .innerHTML = '<div class="probe-action">Re-notified draftor</div>';
            document.querySelector('.loop-ctrl-btn[data-action="interject"]').click();
            document.querySelector('.loop-ctrl-input').value = 'half-typed guidance';
        }""")
        att = payload["status"]["attention"]
        att.update(notified=True, due=True, notified_turn=att["turn_started_at"])
        page.wait_for_function("""() => {
            var s = document.querySelector('#loop-region-notice [data-slot="attention"]');
            return s && s.textContent.indexOf('Attention:') !== -1;
        }""", timeout=8000)
        assert "Re-notified draftor" in _slot(page, "action")
        assert page.evaluate(
            "() => document.querySelector('.loop-ctrl-input').value") == "half-typed guidance"
    finally:
        _unserve_mutable_loop(page)


def test_turn_change_clears_notice(page, dashboard_fleet):
    payload = _attention_payload(elapsed=420, notified=True)
    try:
        _open_incremental(page, dashboard_fleet, payload)
        page.wait_for_function("""() => {
            var s = document.querySelector('#loop-region-notice [data-slot="attention"]');
            return s && s.textContent.indexOf('Attention:') !== -1;
        }""", timeout=8000)
        fresh = _attention_payload(elapsed=5)
        st = payload["status"]["status"]
        st.update(stage="plan_review", next_role="reviewer",
                  turn_started_at=fresh["status"]["status"]["turn_started_at"],
                  attention_notified_turn=None,
                  last_updated="2026-09-22T10:09:00+00:00")
        payload["status"]["attention"] = fresh["status"]["attention"]
        page.wait_for_function("""() => {
            var s = document.querySelector('#loop-region-notice [data-slot="attention"]');
            return s && s.textContent === '';
        }""", timeout=8000)
    finally:
        _unserve_mutable_loop(page)


def test_legacy_loop_keeps_countdown(page, dashboard_fleet):
    payload = _live_payload()
    try:
        _open_incremental(page, dashboard_fleet, payload)
        header = page.evaluate("() => document.querySelector('#loop-region-header').textContent")
        assert "Time Remaining" in header and "Elapsed this turn" not in header
        assert _slot(page, "attention") == ""
    finally:
        _unserve_mutable_loop(page)


def test_sidebar_marker_tracks_selected_loop(page, dashboard_fleet):
    payload = _attention_payload(elapsed=420, notified=True)
    try:
        _open_incremental(page, dashboard_fleet, payload)
        page.wait_for_function("""id => {
            var c = document.querySelector(
                '.loop-sidebar-card[data-loop-id="' + id + '"] .loop-card-attention');
            return c && c.textContent.indexOf('attention') !== -1;
        }""", arg=_ACTIVE_ID, timeout=8000)
        assert "◷" in page.evaluate("""id => document.querySelector(
            '.loop-sidebar-card[data-loop-id="' + id + '"] .loop-card-attention').textContent""",
            _ACTIVE_ID)
    finally:
        _unserve_mutable_loop(page)


def test_unblock_has_no_turn_window_for_attention_loop(page, dashboard_fleet):
    payload = _attention_payload(elapsed=30)
    st = payload["status"]["status"]
    st.update(stage="paused_by_architect", next_role=None, blocked=True,
              turn_started_at=None)
    payload["status"]["attention"].update(turn_started_at=None, due=False)
    posts = []

    def unblock(route):
        posts.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(status=200, content_type="application/json", body='{"ok": true}')
    try:
        _serve_mutable_loop(page, payload)
        page.route("**/" + _ACTIVE_ID + "/unblock", unblock)
        _open_incremental(page, dashboard_fleet, payload)
        page.evaluate("""() => document.querySelector(
            '.loop-ctrl-btn[data-action="unblock"]').click()""")
        assert page.evaluate("""() => document.querySelector(
            '.loop-ctrl-timeout-label').style.display""") == "none"
        page.evaluate("() => document.querySelector('.loop-ctrl-confirm').click()")
        page.wait_for_timeout(500)
        assert posts and "timeout" not in posts[0]
    finally:
        try:
            page.unroute("**/" + _ACTIVE_ID + "/unblock")
        except Exception:
            pass
        _unserve_mutable_loop(page)


def test_create_form_posts_attention_interval(page, dashboard_fleet):
    starts = []
    try:
        open_create(page, dashboard_fleet, starts)
        label = page.evaluate("""() => document.querySelector(
            'label[for="loop-turn-timeout"]').textContent""")
        assert label == "Architect attention interval (seconds)"
        assert "participants never see it" in page.evaluate(
            "() => document.querySelector('.loop-attention-hint').textContent")
        page.fill("#loop-feature-input", "feat")
        page.wait_for_selector("#loop-sketch-select", timeout=10000)
        page.select_option("#loop-sketch-select", ".gator/artifacts/s.md")
        page.evaluate("() => document.querySelector('#loop-create-action').click()")
        page.wait_for_timeout(500)
        assert starts and starts[0]["attention_interval"] == 300
        assert "turn_timeout" not in starts[0]
    finally:
        unroute_create(page)
