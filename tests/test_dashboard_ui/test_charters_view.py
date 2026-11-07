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

GROUP = {"kind": "stale-structure", "label": "mod", "charter_path": ".gator/mission.md",
         "message": "Charter names code that no longer exists.", "count": 3}
# An advisory-only group (#105): shown, but never named in the repair prompt.
ADVISORY_GROUP = dict(GROUP, kind="function-gap", label="advisory-only",
                      message="Public seam is not represented in its charter (advisory).")
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
    def legend(key):
        return [" ".join(t.split()) for t in
                page.locator(f".charters-donut[data-donut='{key}'] .charters-donut-item").all_inner_texts()]
    def center(key):
        return page.locator(f".charters-donut[data-donut='{key}'] .charters-donut-value").text_content()
    assert legend("sync") == ["5 charters current", "3 charters need review"]
    assert center("sync") == "63%"
    assert _text(page, ".charters-missing") == "1 source file has no charter."
    assert legend("commits") == ["2 commits kept charters in step",
                                 "1 commit changed governed code without a charter update"]
    assert center("commits") == "67%"
    assert page.locator(".charters-attention, .charters-finding").count() == 0   # no per-group list
    assert page.locator(".charters-report").count() == 0      # no saved-report line or button
    assert page.evaluate("""() => Array.from(document.querySelectorAll('.charters-dot'))
        .every(d => d.getAttribute('aria-hidden') === 'true')""")


@pytest.mark.parametrize("state", ["needs-review", "current"])
def test_repair_prompt_hands_off_to_the_agent(page, dashboard_fleet, state):
    """A check that needs review shows one copyable line naming the report and
    the flagged charters (at most 8, then a count); a current check shows none."""
    page.add_init_script("""Object.defineProperty(navigator, 'clipboard', { value: {
        writeText: t => { window.__copied = t; return Promise.resolve(); } } });""")
    _stub(page, dict(RESULT, state=state,
                     findings=[ADVISORY_GROUP] + RESULT["findings"]))
    _open_charters(page, dashboard_fleet)
    if state == "current":
        assert page.locator(".charters-prompt").count() == 0
        return
    text = _text(page, ".charters-prompt-text")
    assert text == ("Read the charter sync report at " + RESULT["artifact_path"] + ". For the "
                    "flagged charters (group-0, group-1, group-2, group-3, group-4, group-5, "
                    "group-6, group-7 and 2 more), compare each charter with its code and follow "
                    "the report's repair sketch so the charter matches the code, and move dated "
                    "history (release notes, review rounds, resolved findings) out of the charter, "
                    "per the charter README. Do not add one heading per function; document "
                    "seams, group related helpers, or use the Internal line. Change charters "
                    "only, not code. Show me the charter changes before you commit.")
    assert "advisory-only" not in text
    assert "\n" not in text
    page.click(".charters-copy")
    page.wait_for_function("() => window.__copied !== undefined")
    assert page.evaluate("() => window.__copied") == text
    assert _text(page, ".charters-copy-status") == "✓ Copied"
    heading = page.locator(".charters-commits > h2")
    assert heading.text_content() == "Recent commit coverage"
    assert "charters-doc-title" in heading.get_attribute("class")


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


@pytest.mark.parametrize("path, logical", [
    (".gator/mission.md", "mission.md"),                         # governance: no prefix
    ("src/app/widget.py", "source/src/app/widget.py"),           # source files: source/
    ("gator-command/notes.md", "gator-command/notes.md"),        # its own namespace
])
def test_open_file_hands_repo_the_right_namespace(page, dashboard_fleet, path, logical):
    _stub(page, RESULT)
    largest = [{"path": path, "lines": 4737, "charters": ["scripts-dashboard"]}]
    _stub_report(page, _report("current", code=dict(REPORT["code"], largest_files=largest)))
    _open_charters(page, dashboard_fleet)
    _wait_report(page, "current")
    page.click("#charters-view-tab-code")
    page.click(".charters-file-row")        # the chart row is the link
    _wait_selected(page, logical)
    assert page.evaluate("() => document.getElementById('topbar-title').textContent") == "Repo"


def test_real_run_then_open_file_over_a_cached_listing(page, dashboard_fleet_mutable):
    """A real sync run paints its saved report path, and a chart row opens its
    file in Repo even when Repo's listing is already cached (explicit open)."""
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
    page.wait_for_selector(".charters-band", timeout=60000)     # the real run painted its result

    page.wait_for_selector(".charters-health[data-report='current']:not([data-refreshing])",
                           timeout=60000)
    page.click("#charters-view-tab-code")
    row = page.locator(".charters-file-row").first
    path = row.get_attribute("aria-label")[len("Open "):].split(",")[0]
    logical = path[len(".gator/"):] if path.startswith(".gator/") else "source/" + path
    row.click()
    _wait_selected(page, logical)
    # The file itself opens: selected in the tree and shown, not the default document.
    page.wait_for_selector(f'#repo-file-list .repo-file-item.active[data-path="{logical}"]', timeout=15000)
    assert page.evaluate("() => document.getElementById('topbar-title').textContent") == "Repo"

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
                 "charter_dir": ".gator/charters", "items_truncated": False,
                 "items": [{"name": "scripts-layout", "path": ".gator/mission.md", "lines": 96,
                            "documented_functions": 4, "covers_entries": 1,
                            "covered_files": 1, "covered_lines": 499},
                           {"name": "scripts-loop", "path": ".gator/roadmap.md", "lines": 1134,
                            "documented_functions": 60, "covers_entries": 2,
                            "covered_files": 11, "covered_lines": 10252}]},
    "coverage": {"grammar": "gator-covers-v1", "source_files": 224, "covered_files": 221,
                 "uncovered_files": 3, "percent": 98.7,
                 "uncovered": ["tools/a.py", "tools/b.py"], "uncovered_truncated": True},
    "code": {"product_files": 224, "product_lines": 81995, "charter_to_code_pct": 5.9,
             "target": {"min": 3, "max": 6, "source": "constitution"}, "band": "within",
             "modules": [{"charter": "scripts-dashboard", "files": 12, "lines": 9000,
                          "paths": [f"src/app/dashboard/m{i}.py" for i in range(9)]
                          + ["src/app/views/a.js", "src/app/views/b.js", "src/gator.py"],
                          "paths_truncated": False},
                         {"charter": "scripts-loop", "files": 2, "lines": 4500,
                          "paths": ["src/loop/cli.py", "src/loop/host.py"], "paths_truncated": False}],
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


def _lede(page):
    return " ".join(_text(page, "#charters-panel-overview .charters-doc-lede").split())


def _caption(page, key):
    return " ".join(_text(page, f".charters-figure[data-figure='{key}'] .charters-caption").split())


def _wait_report(page, state):
    page.wait_for_selector(f".charters-health[data-report='{state}']:not([data-refreshing])",
                           timeout=10000)


def test_cache_hit_paints_the_report_in_words_without_a_refresh(page, dashboard_fleet):
    _stub(page, RESULT)
    posts, _ = _stub_report(page, _report("current"))
    _open_charters(page, dashboard_fleet)
    _wait_report(page, "current")
    assert _lede(page) == "22 charters describe 221 of 224 source files; 3 have no charter yet."
    assert _caption(page, "size") == ("4,819 charter lines are 5.9% of 81,995 lines of product code. "
                                      "✓ In range Target 3–6%. The charters document 313 functions.")
    assert _caption(page, "coverage") == "221 covered · 3 without a charter · 98.7% covered."
    assert "✓ Current From the charter report" in _text(page, ".charters-provenance")
    # Every figure is an image with a text alternative and hover text; symbols are hidden.
    assert page.evaluate("""() => Array.from(document.querySelectorAll('.charters-chart'))
        .every(s => ['img', 'group'].includes(s.getAttribute('role')) && s.getAttribute('aria-label'))""")
    assert page.locator(".charters-figure[data-figure='size'] title").count() >= 2
    assert page.evaluate("""() => Array.from(document.querySelectorAll('.charters-mark-symbol'))
        .every(e => e.getAttribute('aria-hidden') === 'true')""")
    # Coverage donut: the percent in the middle, both counts in words beside it.
    assert page.locator(".charters-donut[data-donut='coverage'] .charters-donut-value").text_content() == "98.7%"
    assert [" ".join(t.split()) for t in page.locator(".charters-donut[data-donut='coverage'] .charters-donut-item").all_inner_texts()] ==         ["221 covered by a charter", "3 without a charter"]
    # Charters by size: largest first, oversize in words, each row opens its charter.
    rows = page.locator(".charters-charter-row")
    assert [rows.nth(i).get_attribute("aria-label") for i in range(rows.count())] == [
        "Open .gator/roadmap.md, 1,134 lines, over 600 lines",
        "Open .gator/mission.md, 96 lines"]
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
    assert _lede(page).startswith("22 charters")
    page.wait_for_function("() => document.querySelector('.charters-refresh').disabled")
    assert posts == ["1"] and len(held) == 1
    held[0].fulfill(status=200, content_type="application/json",
                    body=json.dumps(dict(_report(after, charters=dict(REPORT["charters"], count=23)),
                                         persisted=True)))
    _wait_report(page, after)
    assert _lede(page).startswith("23 charters")
    page.wait_for_timeout(500)
    assert posts == ["1"]                                 # never a second automatic refresh


def test_refresh_failure_keeps_the_cached_figures(page, dashboard_fleet):
    _stub(page, RESULT)
    _stub_report(page, _report("stale"), (500, {"state": "failed", "error": "boom"}))
    _open_charters(page, dashboard_fleet)
    page.wait_for_selector(".charters-health-error:not([hidden])", timeout=10000)
    alert = _text(page, ".charters-health-error")
    assert alert.startswith("Refresh failed: boom.") and "Figures shown are from" in alert
    assert _lede(page).startswith("22 charters")
    assert page.locator(".charters-refresh").is_enabled()
    assert page.locator(".charters-error").is_hidden()   # the sync alert is separate


@pytest.mark.parametrize("get_body, refreshes, expect", [
    ({"state": "none"}, 1, "22 charters describe"),
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
    assert "81,995 lines of product code in 224 source files." in code
    sections = page.evaluate("""() => Array.from(document.querySelectorAll(
        '#charters-panel-code h2')).map(h => h.textContent)""")
    assert sections == ["Largest files", "Lines of code covered by each charter"]
    rows = page.evaluate("""() => Array.from(document.querySelectorAll(
        '.charters-figure[data-figure="modules"] .charters-row')).map(g =>
        [g.querySelector('.charters-chart-label').textContent,
         g.querySelector('.charters-chart-value').textContent,
         (g.querySelector('.charters-chart-sub') || {}).textContent || null])""")
    assert rows == [
        ["scripts-dashboard", "9,000", "app/dashboard/ (9), app/views/ (2), src/ (1)"],
        ["scripts-loop", "4,500", "loop/cli.py, loop/host.py"],
        ["No charter", "120", "tools/ (2) (first 2 files)"]]   # truncated: grouped by folder
    title = page.locator(".charters-figure[data-figure='modules'] .charters-row title").first.text_content()
    assert title.startswith("scripts-dashboard: 9,000 lines in 12 files\nsrc/app/dashboard/m0.py")
    largest = page.locator(".charters-file-row").first
    assert largest.get_attribute("role") == "link" and largest.get_attribute("tabindex") == "0"
    assert largest.get_attribute("aria-label") == "Open .gator/mission.md, 4,737 lines, over 4,000 lines"
    assert largest.locator(".charters-chart-symbol").text_content() == "■"   # size band also as a symbol
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
