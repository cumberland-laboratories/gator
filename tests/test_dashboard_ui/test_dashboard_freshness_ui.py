"""Dashboard freshness in the page (#107, #108, #20).

`checkFreshness()` polls `/api/state` every 10 s. These tests stub that
route (and, for the redraw, `/api/data`) with `page.route`, so the real
server is never changed; the server side is pinned by
`tests/test_dashboard_freshness.py`.
"""

import json

POLL_WAIT_MS = 25000   # one 10 s poll interval, plus slack for CI


def _state(build, collection):
    return json.dumps({"collection": collection, "started": collection,
                       "finished": collection, "build": build})


def _page_build(page):
    return page.evaluate(
        "() => document.querySelector('meta[name=\"gator-dashboard-build\"]').content")


def test_served_page_carries_a_build_stamp(page, dashboard_fleet):
    page.goto(dashboard_fleet["url"].rstrip("/") + "/?view=fleet", wait_until="load")
    page.wait_for_selector(".fleet-table", timeout=15000)
    assert len(_page_build(page)) == 12
    # The real server serves the same build: no notice.
    assert page.locator(".build-notice").count() == 0


def test_a_different_server_build_asks_for_a_reload(page, dashboard_fleet):
    page.goto(dashboard_fleet["url"].rstrip("/") + "/?view=fleet", wait_until="load")
    page.wait_for_selector(".fleet-table", timeout=15000)
    page.route("**/api/state", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=_state("ffffffffffff", None)))

    notice = page.locator(".build-notice")
    notice.wait_for(timeout=POLL_WAIT_MS)
    assert notice.get_attribute("role") == "status"
    assert "restarted with a different version" in notice.inner_text()
    assert page.locator(".build-notice-reload").inner_text() == "Reload"
    # It sits outside the view, so a view render does not remove it.
    assert page.evaluate(
        "() => !document.getElementById('view-slot').contains(document.querySelector('.build-notice'))")


def test_a_newer_collection_redraws_fleet(page, dashboard_fleet):
    base = dashboard_fleet["url"].rstrip("/")
    page.goto(base + "/?view=fleet", wait_until="load")
    page.wait_for_selector(".fleet-table", timeout=15000)
    build = _page_build(page)

    data = page.request.get(base + "/api/data").json()
    shown = data.get("collection")
    assert isinstance(shown, int)
    newer = dict(data, collection=shown + 1,
                 repos=list(data["repos"]) + [{"name": "zz-registered-from-terminal",
                                                "path": "/nowhere/zz",
                                                "accessible": False}])
    page.route("**/api/data", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(newer)))
    page.route("**/api/state", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=_state(build, shown + 1)))

    page.locator(".fleet-repo-name", has_text="zz-registered-from-terminal").wait_for(
        timeout=POLL_WAIT_MS)
    assert page.locator(".build-notice").count() == 0
