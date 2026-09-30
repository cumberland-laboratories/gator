"""M5 Playwright pins — participant liveness panel and Re-notify (#36).

The seeded fleet loops have no role tokens, so the real /liveness route
denies them (404); tests that need data fulfil /liveness and /renotify
with crafted allowlisted views via page.route.

Coverage: the five watcher states render as text + glyph (never hue
alone), the footnote copy, Re-notify only when eligible, the inline reason
form surviving polling, POST shape + anti-CSRF header + notices, refusal
messages, degraded modes, and no full-region rebuild on unchanged polls.
"""

import json
from datetime import datetime, timedelta, timezone

from .test_loop_workspace import _navigate_to_loop, _select_loop_card

LIVENESS_ROUTE = "**/loops/*/liveness"
RENOTIFY_ROUTE = "**/loops/*/renotify"


def _iso(seconds_ago=0):
    return (datetime.now(tz=timezone.utc)
            - timedelta(seconds=seconds_ago)).isoformat()


def _role(state, eligible=False, code="not_actionable", note=None,
          seen_ago=2):
    return {
        "state": state,
        "adapter_kind": None if state == "not_registered" else "generic-watcher",
        "last_seen_at": None if state == "not_registered" else _iso(seen_ago),
        "pending": 0,
        "last_notification": note,
        "renotify_eligible": eligible,
        "renotify_reason_code": None if eligible else code,
    }


def _view(draftor, reviewer, **extra):
    v = {"schema": "gator-loop-liveness-view-v1", "available": True,
         "degraded": None, "roles": {"draftor": draftor, "reviewer": reviewer},
         "audit": {"renotify_count": 0, "last_at": None, "last_actor": None}}
    v.update(extra)
    return v


def _serve(page, factory):
    """Fulfil /liveness from ``factory(call_index)``; returns the counter."""
    calls = {"n": 0}

    def handler(route):
        calls["n"] += 1
        route.fulfill(status=200, content_type="application/json",
                      headers={"Cache-Control": "no-store"},
                      body=json.dumps(factory(calls["n"])))
    page.route(LIVENESS_ROUTE, handler)
    return calls


def _open(page, fleet):
    _navigate_to_loop(page, fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_selector(".loop-liveness", timeout=10000)


def _state_text(page, role):
    return page.evaluate(
        "(r) => document.querySelector("
        "'.loop-liveness-row[data-role=\"' + r + '\"] .loop-liveness-state')"
        ".textContent", role)


def _cleanup(page):
    for r in (LIVENESS_ROUTE, RENOTIFY_ROUTE):
        try:
            page.unroute(r)
        except Exception:
            pass


def test_states_render_as_text_and_glyph(page, dashboard_fleet):
    views = [
        _view(_role("connected"), _role("stale", seen_ago=120)),
        _view(_role("released"), _role("closed")),
        _view(_role("not_registered"), _role("not_registered")),
    ]
    idx = {"i": 0}
    _serve(page, lambda n: views[idx["i"]])
    try:
        _open(page, dashboard_fleet)
        page.wait_for_function(
            "() => document.querySelector('.loop-liveness-state').textContent")
        assert _state_text(page, "draftor").startswith("● Connected")
        stale = _state_text(page, "reviewer")
        assert stale.startswith("◐ Stale") and "last seen " in stale
        assert "ago" not in stale  # absolute time from data, not wall clock
        # Colour is never the only signal: the state is in the text and the
        # data-state hook carries weight/style.
        assert page.evaluate(
            "() => getComputedStyle(document.querySelector("
            "'.loop-liveness-row[data-role=\"reviewer\"] .loop-liveness-state'))"
            ".fontWeight") in ("700", "bold")
        for i, expect in ((1, ("◇ Released", "■ Closed")),
                          (2, ("○ Not registered", "○ Not registered"))):
            idx["i"] = i
            page.wait_for_function(
                "(t) => document.querySelector("
                "'.loop-liveness-row[data-role=\"draftor\"] .loop-liveness-state')"
                ".textContent.startsWith(t)", arg=expect[0], timeout=10000)
            assert _state_text(page, "reviewer").startswith(expect[1])
        foot = page.evaluate(
            "() => document.querySelector('.loop-liveness-footnote').textContent")
        assert "Acknowledged means received" in foot
        assert "gator loop wait" in foot
    finally:
        _cleanup(page)


def test_renotify_button_only_when_eligible(page, dashboard_fleet):
    _serve(page, lambda n: _view(_role("stale", eligible=True),
                                 _role("connected")))
    try:
        _open(page, dashboard_fleet)
        page.wait_for_selector(
            '.loop-liveness-row[data-role="draftor"] .loop-liveness-renotify',
            timeout=10000)
        assert page.locator(
            '.loop-liveness-row[data-role="reviewer"] .loop-liveness-renotify'
        ).count() == 0
    finally:
        _cleanup(page)


def test_reason_survives_polling_and_post_shape(page, dashboard_fleet):
    note = {"kind": "turn-ready", "created_at": _iso(30),
            "created_by": "projection", "delivered_at": None,
            "acked_at": None, "expired_reason": None}
    calls = _serve(page, lambda n: _view(
        _role("stale", eligible=True, note=note, seen_ago=60 + n),
        _role("not_registered")))
    posts = []

    def renotify(route):
        posts.append((route.request.post_data,
                      route.request.headers.get("x-gator-dashboard")))
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"ok": True, "role": "draftor",
                                       "kind": "turn-ready"}))
    page.route(RENOTIFY_ROUTE, renotify)
    try:
        _open(page, dashboard_fleet)
        btn = '.loop-liveness-row[data-role="draftor"] .loop-liveness-renotify'
        page.wait_for_selector(btn, timeout=10000)
        page.evaluate("(s) => document.querySelector(s).click()", btn)
        page.wait_for_selector(".loop-liveness-reason", timeout=5000)
        page.fill(".loop-liveness-reason", "half-typed reason")
        before = calls["n"]
        page.wait_for_timeout(4000)  # > POLL_INTERVAL_MS
        assert calls["n"] > before, "liveness should keep polling"
        assert page.evaluate(
            "() => document.querySelector('.loop-liveness-reason').value"
        ) == "half-typed reason"
        page.evaluate(
            "() => document.querySelector('.loop-liveness-send').click()")
        page.wait_for_selector(".loop-liveness-notice", timeout=5000)
        assert len(posts) == 1
        body, header = posts[0]
        assert json.loads(body) == {"role": "draftor",
                                    "reason": "half-typed reason"}
        assert header == "1"
        notice = page.evaluate(
            "() => document.querySelector('.loop-liveness-notice').textContent")
        assert "Re-notify sent" in notice and "does not change the loop" in notice
        assert page.locator(".loop-liveness-reason").count() == 0
    finally:
        _cleanup(page)


def test_refusal_message(page, dashboard_fleet):
    _serve(page, lambda n: _view(_role("stale", eligible=True),
                                 _role("connected")))
    page.route(RENOTIFY_ROUTE, lambda route: route.fulfill(
        status=429, content_type="application/json",
        body=json.dumps({"error": "re-notify rate limited",
                         "code": "rate_limited"})))
    try:
        _open(page, dashboard_fleet)
        btn = '.loop-liveness-row[data-role="draftor"] .loop-liveness-renotify'
        page.wait_for_selector(btn, timeout=10000)
        page.evaluate("(s) => document.querySelector(s).click()", btn)
        page.wait_for_selector(".loop-liveness-send", timeout=5000)
        page.evaluate(
            "() => document.querySelector('.loop-liveness-send').click()")
        page.wait_for_selector(".loop-liveness-notice-error", timeout=5000)
        text = page.evaluate(
            "() => document.querySelector('.loop-liveness-notice').textContent")
        assert "Re-notify not sent" in text and "wait a few seconds" in text
        # The form stays open (with the Send button re-enabled) for a retry.
        assert page.evaluate(
            "() => document.querySelector('.loop-liveness-send').disabled") is False
    finally:
        _cleanup(page)


def _observe_region(page):
    page.evaluate("""() => {
        window.__livMutations = 0;
        document.querySelector('.loop-liveness').__probe = 1;
        document.querySelector('.loop-liveness-row').__probe = 1;
        new MutationObserver(function (records) {
            window.__livMutations += records.length;
        }).observe(document.querySelector('#loop-region-liveness'),
                   {childList: true, subtree: true, characterData: true,
                    attributes: true});
    }""")


def test_unchanged_poll_does_not_touch_region(page, dashboard_fleet):
    """Identical data -> zero DOM mutations (#38), including a connected
    row whose last_seen_at is unchanged."""
    fixed = _view(_role("connected", seen_ago=5), _role("closed"))
    calls = _serve(page, lambda n: fixed)
    try:
        _open(page, dashboard_fleet)
        page.wait_for_function(
            "() => document.querySelector('.loop-liveness-state').textContent")
        _observe_region(page)
        before = calls["n"]
        page.wait_for_timeout(7000)  # >= two polls
        assert calls["n"] >= before + 2
        assert page.evaluate("() => window.__livMutations") == 0
        assert page.evaluate("""() =>
            document.querySelector('.loop-liveness').__probe === 1 &&
            document.querySelector('.loop-liveness-row').__probe === 1""")
    finally:
        _cleanup(page)


def test_denied_poll_does_not_touch_region(page, dashboard_fleet):
    """Repeated identical denials (real 404 route) also mutate nothing."""
    _open(page, dashboard_fleet)
    page.wait_for_function(
        "() => !document.querySelector('.loop-liveness-degraded').hidden",
        timeout=10000)
    _observe_region(page)
    page.wait_for_timeout(7000)
    assert page.evaluate("() => window.__livMutations") == 0


def test_unavailable_and_denied_modes(page, dashboard_fleet):
    _serve(page, lambda n: {"schema": "gator-loop-liveness-view-v1",
                            "available": False, "degraded": "unavailable",
                            "roles": None, "audit": None})
    try:
        _open(page, dashboard_fleet)
        page.wait_for_function(
            "() => !document.querySelector('.loop-liveness-degraded').hidden",
            timeout=10000)
        text = page.evaluate(
            "() => document.querySelector('.loop-liveness-degraded').textContent")
        assert "Delivery unavailable" in text and "runs normally" in text
    finally:
        _cleanup(page)


def test_real_route_denied_for_tokenless_seed(page, dashboard_fleet):
    """Seeded loops have no .tokens.json -> the real route denies (404)."""
    _open(page, dashboard_fleet)
    page.wait_for_function(
        "() => !document.querySelector('.loop-liveness-degraded').hidden",
        timeout=10000)
    text = page.evaluate(
        "() => document.querySelector('.loop-liveness-degraded').textContent")
    assert "no Architect authority" in text
    assert page.locator(".loop-liveness-renotify").count() == 0
