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


# ── Charter report: Overview, Code and Features (charters-health-section) ──

REPORT = {
    "schema": "gator-charters-report-v1", "status": "complete",
    "generated_at": "2026-11-06T02:00:00Z", "gator_version": "2.36.0",
    "inputs": {"fingerprint": "a" * 64, "head": "b" * 40, "revision": "b" * 12},
    "charters": {"count": 22, "lines": 4819, "documented_functions": 313,
                 "charter_dir": ".gator/charters", "items": [], "items_truncated": False},
    "coverage": {"grammar": "gator-covers-v1", "source_files": 224, "covered_files": 221,
                 "uncovered_files": 3, "percent": 98.7,
                 "uncovered": ["tools/a.py", "tools/b.py"], "uncovered_truncated": True},
    "code": {"product_files": 224, "product_lines": 81995, "charter_to_code_pct": 5.9,
             "target": {"min": 3, "max": 6, "source": "constitution"}, "band": "within",
             "modules": [{"charter": "scripts-dashboard", "files": 12, "lines": 9000},
                         {"charter": "scripts-loop", "files": 9, "lines": 4500}],
             "modules_truncated": False, "uncovered_module": {"files": 3, "lines": 120},
             "largest_files": [{"path": ".gator/mission.md", "lines": 4737,
                                "charters": ["scripts-dashboard"]}]},
    "sync": {"state": "none"},
    "measurement": {"lines": "Physical lines (newline count) of each source file."},
    "problems": [],
}


def _stub_report(page, get_body, post=None, hold=False):
    """Answer the report GET with `get_body`; POST with `post` = (status, body).

    With `hold`, POSTs are held (returned in `held`) instead of answered.
    """
    posts, held = [], []

    def handler(route):
        if route.request.method == "POST":
            posts.append(route.request.headers.get("x-gator-dashboard"))
            if hold:
                held.append(route)
                return
            status, body = post
            route.fulfill(status=status, content_type="application/json", body=json.dumps(body))
        else:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(get_body))
    page.route("**/api/repo/alpha/charters-report", handler)
    return posts, held


def _report(freshness, **changes):
    return {"state": "report", "freshness": freshness, "report": dict(REPORT, **changes)}


def _tiles(page):
    return page.evaluate("""() => Array.from(document.querySelectorAll('.charters-tile'))
        .map(t => t.innerText.replace(/\\s+/g, ' ').trim())""")


def _wait_report(page, state):
    page.wait_for_selector(f".charters-health[data-report='{state}']:not([data-refreshing])",
                           timeout=10000)


def test_cache_hit_paints_tiles_in_words_without_a_refresh(page, dashboard_fleet):
    _stub(page, RESULT)
    posts, _ = _stub_report(page, _report("current"))
    _open_charters(page, dashboard_fleet)
    _wait_report(page, "current")
    assert _tiles(page) == ["Charters 22 4,819 lines · 313 documented functions",
                            "Charter size vs code 5.9% ✓ In range target 3–6%",
                            "Files without a charter 3 of 224 source files"]
    assert "✓ Current From the charter report" in _text(page, ".charters-provenance")
    assert page.evaluate("""() => Array.from(document.querySelectorAll(
        '.charters-mark-symbol, .charters-bar')).every(e => e.getAttribute('aria-hidden') === 'true')""")
    page.wait_for_timeout(500)
    assert posts == []                                    # a current cache is never refreshed
    assert _text(page, ".charters-headline") == RESULT["headline"]   # sync section unchanged


@pytest.mark.parametrize("after", ["current", "stale"])
def test_stale_report_refreshes_exactly_once(page, dashboard_fleet, after):
    _stub(page, RESULT)
    posts, held = _stub_report(page, _report("stale"), hold=True)
    _open_charters(page, dashboard_fleet)
    page.wait_for_selector(".charters-health[data-report='stale']", timeout=10000)
    assert "▲ Stale" in _text(page, ".charters-provenance")       # cached figures, labelled
    assert _tiles(page)[0].startswith("Charters 22")
    page.wait_for_function("() => document.querySelector('.charters-refresh').disabled")
    assert posts == ["1"] and len(held) == 1
    held[0].fulfill(status=200, content_type="application/json",
                    body=json.dumps(dict(_report(after, charters=dict(REPORT["charters"], count=23)),
                                         persisted=True)))
    _wait_report(page, after)
    assert _tiles(page)[0].startswith("Charters 23")
    page.wait_for_timeout(500)
    assert posts == ["1"]                                 # never a second automatic refresh


def test_refresh_failure_keeps_the_cached_figures(page, dashboard_fleet):
    _stub(page, RESULT)
    _stub_report(page, _report("stale"), (500, {"state": "failed", "error": "boom"}))
    _open_charters(page, dashboard_fleet)
    page.wait_for_selector(".charters-health-error:not([hidden])", timeout=10000)
    alert = _text(page, ".charters-health-error")
    assert alert.startswith("Refresh failed: boom.") and "Figures shown are from" in alert
    assert _tiles(page)[0].startswith("Charters 22")
    assert page.locator(".charters-refresh").is_enabled()
    assert page.locator(".charters-error").is_hidden()   # the sync alert is separate


@pytest.mark.parametrize("get_body, refreshes, expect", [
    ({"state": "none"}, 1, "Charters 22"),
    ({"state": "unavailable", "message": "Not gatorized here."}, 0, "Not gatorized here."),
])
def test_first_build_and_unavailable(page, dashboard_fleet, get_body, refreshes, expect):
    _stub(page, RESULT)
    posts, _ = _stub_report(page, get_body, (200, dict(_report("current"), persisted=True)))
    _open_charters(page, dashboard_fleet)
    _wait_report(page, "current" if refreshes else "unavailable")
    page.wait_for_timeout(300)
    assert len(posts) == refreshes
    assert expect in " ".join(_text(page, ".charters-health-area").split())
    assert page.locator(".charters-refresh").is_visible() is bool(refreshes)


def test_tabs_by_keyboard_show_code_and_features(page, dashboard_fleet):
    _stub(page, RESULT)
    _stub_report(page, _report("current"))
    _open_charters(page, dashboard_fleet)
    _wait_report(page, "current")
    page.focus("#charters-view-tab-overview")
    page.keyboard.press("ArrowRight")
    assert page.get_attribute("#charters-view-tab-code", "aria-selected") == "true"
    assert page.locator("#charters-panel-overview").is_hidden()
    code = _text(page, "#charters-panel-code")
    assert "Product code: 81,995 lines in 224 source files." in code
    assert "9,000 lines · 12 files" in code and "No charter" in code
    assert "and 1 more." in code                          # 3 uncovered, 2 listed
    page.keyboard.press("End")
    assert "A feature map is planned for a later release." in _text(page, "#charters-panel-features")
    page.keyboard.press("Home")
    assert page.locator("#charters-panel-overview").is_visible()


def test_a_sync_run_waits_for_an_inflight_refresh(page, dashboard_fleet):
    """Both POSTs take the same repository lock, so the view sends one at a time."""
    sync_posts = _stub(page, RESULT, (200, dict(RESULT, headline="After refresh.", persisted=True)))
    _, held = _stub_report(page, _report("stale"), hold=True)
    _open_charters(page, dashboard_fleet)
    page.wait_for_function("() => document.querySelector('.charters-refresh').disabled")
    page.click(".charters-run")
    page.wait_for_timeout(300)
    assert sync_posts == [] and len(held) == 1
    held[0].fulfill(status=200, content_type="application/json",
                    body=json.dumps(dict(_report("current"), persisted=True)))
    page.wait_for_function(
        "() => document.querySelector('.charters-headline')"
        " && document.querySelector('.charters-headline').textContent === 'After refresh.'",
        timeout=10000)
    assert sync_posts == ["1"]
