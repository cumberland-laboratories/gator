"""Charters view (charters-sidebar-sync): the charter sync page.

Each test proves one risk named by the approved plan:

- placement and gating: Charters sits directly below Loop and above the
  Knowledge label, gated exactly like Loop;
- the page paints only what the server returned: the first-visit text,
  then a completed result in words and labelled counts;
- a failed run keeps the displayed result and shows an alert;
- "Open charter" lands on Repo with that file selected;
- the new-report regression: with Repo's listing already cached, "Open
  report" for a just-created report selects and loads that report, never
  the default document;
- Back returns to Charters with its title; the page fits 375px.

Stubbed tests use the shared fleet; the real-run test uses a mutable fleet,
because a real run writes a report into the repository.
"""

import json

import pytest

GROUP = {"kind": "function-gap", "label": "mod", "charter_path": ".gator/mission.md",
         "message": "Public function is not represented in its charter.", "count": 3}
RESULT = {
    "schema": "gator-charter-sync-v1", "state": "needs-review",
    "checked_at": "2026-10-29T12:00:00Z", "revision": "0123456789ab", "dirty": False,
    "headline": "12 findings in 3 charters; 1 source file without a charter.",
    "counts": {"current": 5, "needs_review": 3, "missing": 1},
    "recent_commits": {"examined": 3, "without_charter_update": 1, "reason": None},
    "findings_total": 12, "groups_total": 10,
    "findings": [dict(GROUP, label=f"group-{i}") for i in range(10)],
    "artifact_path": ".gator/artifacts/2026-10-29-charter-sync-report.md",
}


def _origin(fleet):
    return fleet["url"].rstrip("/") + "/"


def _stub(page, get_body, post=None):
    """Answer GET with `get_body`; POST with `post` = (status, body), recorded."""
    posts = []

    def handler(route):
        if route.request.method == "POST":
            posts.append(route.request.headers.get("x-gator-dashboard"))
            status, body = post
            route.fulfill(status=status, content_type="application/json", body=json.dumps(body))
        else:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(get_body))
    page.route("**/api/repo/alpha/charter-sync", handler)
    return posts


def _open_charters(page, fleet, repo="alpha"):
    page.goto(_origin(fleet) + f"?repo={repo}&view=charters", wait_until="load")
    page.wait_for_selector(".charters-view[data-loaded='true']", timeout=15000)


def _text(page, selector):
    return page.locator(selector).first.inner_text(timeout=5000)


def test_sidebar_placement_and_gating(page, dashboard_fleet):
    page.goto(_origin(dashboard_fleet), wait_until="load")
    page.wait_for_selector(".welcome-workspace", timeout=15000)
    order = page.evaluate("""() => Array.from(document.querySelectorAll(
        '#sidebar-nav > *')).map(e => e.id || e.textContent.trim())""")
    i = order.index("loop-tab")
    assert order[i + 1] == "charters-tab" and order[i + 2] == "Knowledge"
    tab = page.locator("#charters-tab")
    assert " ".join(tab.text_content().split()) == "§ Charters"
    tab.click(force=True)   # dimmed: the click handler ignores it
    assert page.evaluate("() => document.getElementById('topbar-title').textContent") \
        == "Welcome to Gator!"
    page.goto(_origin(dashboard_fleet) + "?repo=alpha", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    assert tab.get_attribute("aria-disabled") is None
    tab.click()
    page.wait_for_selector(".charters-view", timeout=15000)
    assert page.evaluate("() => document.getElementById('topbar-title').textContent") == "Charters"


def test_first_visit_then_completed_result(page, dashboard_fleet):
    posts = _stub(page, {"state": "none"}, (200, dict(RESULT, persisted=True)))
    _open_charters(page, dashboard_fleet)
    body = _text(page, ".charters-body")
    assert "No charter sync check has been recorded for this checkout." in body
    assert "It does not edit code or charters." in body
    assert posts == []                                  # nothing runs on its own
    page.click(".charters-run")
    page.wait_for_selector(".charters-band", timeout=10000)
    assert posts == ["1"]                               # the Dashboard header
    assert _text(page, ".charters-state-word") == "Needs review"
    assert _text(page, ".charters-headline") == RESULT["headline"]
    counts = page.evaluate("""() => Array.from(document.querySelectorAll('.charters-count'))
        .map(c => c.innerText.replace(/\\s+/g, ' ').trim())""")
    assert counts == ["5 current", "3 needs review", "1 missing charter source files"]
    assert "3 commits examined · 1 changed governed code without a charter update" \
        in _text(page, ".charters-commits")
    assert page.locator(".charters-attention > .charters-findings > li").count() == 8
    assert _text(page, ".charters-more-summary") == "Show all (10)"
    assert _text(page, ".charters-report-path") == RESULT["artifact_path"]
    assert page.evaluate("""() => Array.from(document.querySelectorAll('.charters-dot'))
        .every(d => d.getAttribute('aria-hidden') === 'true')""")


def test_failed_run_keeps_the_previous_result(page, dashboard_fleet):
    _stub(page, RESULT, (500, {"state": "failed", "error": "charter verifier failed: boom"}))
    _open_charters(page, dashboard_fleet)
    assert _text(page, ".charters-headline") == RESULT["headline"]
    page.click(".charters-run")
    page.wait_for_selector(".charters-error:not([hidden])", timeout=10000)
    assert "charter verifier failed: boom" in _text(page, ".charters-error")
    assert "The previous result is unchanged." in _text(page, ".charters-error")
    assert _text(page, ".charters-headline") == RESULT["headline"]
    assert page.locator(".charters-run").is_enabled()


@pytest.mark.parametrize("late", ["none", "stale", "failure"])
def test_late_initial_read_never_replaces_a_run(page, dashboard_fleet, late):
    """A run started while the initial read is still pending owns the page:
    the late read (no record, an older result, or a failure) changes
    nothing and shows no error."""
    held = []
    fresh = dict(RESULT, headline="Fresh successful check.", persisted=True)

    def handler(route):
        if route.request.method == "POST":
            route.fulfill(status=200, content_type="application/json", body=json.dumps(fresh))
        else:
            held.append(route)          # hold the initial read
    page.route("**/api/repo/alpha/charter-sync", handler)
    page.goto(_origin(dashboard_fleet) + "?repo=alpha&view=charters", wait_until="load")
    page.wait_for_selector(".charters-view[data-loaded='pending']", timeout=15000)
    for _ in range(100):               # the read was issued and is now held
        if held:
            break
        page.wait_for_timeout(50)
    page.click(".charters-run")
    page.wait_for_selector(".charters-band", timeout=10000)
    assert _text(page, ".charters-headline") == "Fresh successful check."

    assert len(held) == 1
    if late == "failure":
        held[0].fulfill(status=500, content_type="application/json", body="{}")
    else:
        body = {"state": "none"} if late == "none" else dict(RESULT, headline="Old result.")
        held[0].fulfill(status=200, content_type="application/json", body=json.dumps(body))
    page.wait_for_selector(".charters-view[data-loaded='true']", timeout=10000)
    assert _text(page, ".charters-headline") == "Fresh successful check."
    assert page.locator(".charters-error").is_hidden()
    assert "No charter sync check has been recorded" not in _text(page, ".charters-body")


def _keys(page, fleet):
    data = page.request.get(_origin(fleet) + "api/data").json()
    return {r["name"]: r.get("repo_key") for r in (data.get("repos") or [])}


def _wait_selected(page, logical):
    page.wait_for_function(
        "p => { const s = window.__gator_debug && window.__gator_debug.sidebar;"
        " return !!s && s.selectedFile === p; }", arg=logical, timeout=15000)


def test_open_charter_selects_that_file(page, dashboard_fleet):
    _stub(page, dict(RESULT, findings=[GROUP], groups_total=1))
    _open_charters(page, dashboard_fleet)
    page.click(".charters-finding .charters-action:has-text('Open charter')")
    _wait_selected(page, "mission.md")
    assert page.evaluate("() => document.getElementById('topbar-title').textContent") == "Repo"


def test_new_report_opens_over_a_cached_listing(page, dashboard_fleet_mutable):
    fleet = dashboard_fleet_mutable
    keys = _keys(page, fleet)
    page.goto(_origin(fleet), wait_until="load")
    page.evaluate("([n, k]) => window.gatorNavToRepo(n, k)", ["alpha", keys["alpha"]])
    page.wait_for_function(
        "() => { const s = window.__gator_debug && window.__gator_debug.sidebar;"
        " return !!s && !!s.selectedFile; }", timeout=15000)
    assert page.evaluate("() => window.__gator_debug.listingCache.some(e => e.repoKey)")

    page.click("#charters-tab")
    page.wait_for_selector(".charters-view[data-loaded='true']", timeout=15000)
    page.click(".charters-run")
    page.wait_for_selector(".charters-report-path", timeout=60000)
    report = _text(page, ".charters-report-path")
    assert report.startswith(".gator/artifacts/") and report.endswith(".md")

    requested = []
    page.on("request", lambda r: requested.append(r.url))
    page.click(".charters-report .charters-action")
    logical = report[len(".gator/"):]
    _wait_selected(page, logical)
    page.wait_for_function(
        "() => (document.getElementById('repo-file-content') || {}).textContent"
        "  && document.getElementById('repo-file-content').textContent.includes('Charter sync report')",
        timeout=15000)
    assert page.locator(f'#repo-file-list .repo-file-item.active[data-path="{logical}"]').count() == 1
    files = [u for u in requested if "/file/" in u]
    assert files and all(logical.split("/")[-1] in u for u in files), files

    page.go_back()
    page.wait_for_selector(".charters-view", timeout=15000)
    assert page.title() == "Gator · alpha · Charters"


def test_page_fits_a_narrow_screen(page, dashboard_fleet):
    page.set_viewport_size({"width": 375, "height": 800})
    _stub(page, RESULT)
    _open_charters(page, dashboard_fleet)
    assert page.evaluate("""() => {
        const v = document.querySelector('.charters-view');
        const slot = document.getElementById('view-slot');
        return v.scrollWidth <= v.clientWidth + 1
            && slot.scrollWidth <= slot.clientWidth + 1
            && document.documentElement.scrollWidth <= window.innerWidth; }""")
