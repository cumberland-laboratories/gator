"""#43 M2 (UI) — Architect brief visibility in the loop view and the create
form's UTF-8 byte counter.

Status payloads are routed for the seeded active loop with crafted strict
brief projections. Integrity is asserted as text, never hue. Linked brief
entries use the fixed artifact names; invalid references and a dropped
planning brief are text-only notes with no link and no fetch.
"""

import copy
import json

from .test_loop_workspace import (
    _ACTIVE_ID, _live_payload, _navigate_to_loop, _select_loop_card)

SHA = "a" * 64
BRIEF_VIEW = {"artifact": "architect-brief.md", "sha256": SHA, "bytes": 120}
SRC_VIEW = {"artifact": "source-architect-brief.md", "sha256": SHA, "bytes": 99}


def serve(page, status, events, fetched):
    def fulfill(route, body):
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(body))

    def artifact(route):
        fetched.append(route.request.url.rsplit("/", 1)[-1])
        route.fulfill(status=200, content_type="text/plain",
                      body="# Artifact\n\n## Executive Summary\n\n- x\n")
    page.route("**/" + _ACTIVE_ID + "/status", lambda r: fulfill(r, status))
    page.route("**/" + _ACTIVE_ID + "/events",
               lambda r: fulfill(r, {"events": events}))
    page.route("**/" + _ACTIVE_ID + "/artifact/**", artifact)


def unserve(page):
    for s in ("status", "events", "artifact/**"):
        try:
            page.unroute("**/" + _ACTIVE_ID + "/" + s)
        except Exception:
            pass


def open_view(page, fleet, status):
    fetched = []
    payload = _live_payload()
    serve(page, status, payload["events"], fetched)
    _navigate_to_loop(page, fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_selector(".loop-artifact-section", timeout=10000)
    return fetched


def planning_status(**brief):
    s = _live_payload()["status"]
    s.update(brief)
    return s


def coding_status(**coding_extra):
    s = _live_payload()["status"]
    s["mode"] = "coding"
    s["status"]["stage"] = "implementation_drafting"
    s["brief"] = None
    s["brief_check"] = "absent"
    c = {"source_loop_id": "src-2026-09-21T10-00-00Z", "plan_sha256": SHA,
         "base_head": "b" * 40, "base_tree": "c" * 40, "generations": [],
         "approval": None, "source_brief": None,
         "source_brief_check": "absent",
         "source_brief_decision": "none_available"}
    c.update(coding_extra)
    s["coding"] = c
    return s


def artifacts(page):
    return page.evaluate("""() => Array.from(document.querySelectorAll(
        '.loop-artifact-section')).map(s => [s.dataset.artifact,
        s.querySelector('.loop-artifact-toggle').textContent])""")


def notes(page):
    return page.evaluate("""() => Array.from(document.querySelectorAll(
        '.loop-brief-note')).map(n => n.textContent)""")


def test_planning_brief_ok_listed_first(page, dashboard_fleet):
    try:
        open_view(page, dashboard_fleet,
                  planning_status(brief=BRIEF_VIEW, brief_check="ok"))
        a = artifacts(page)
        assert a[0] == ["architect-brief.md", "Architect brief (required reading)"]
        assert notes(page) == []
    finally:
        unserve(page)


def test_mismatch_marker_is_text(page, dashboard_fleet):
    try:
        open_view(page, dashboard_fleet,
                  planning_status(brief=BRIEF_VIEW, brief_check="mismatch"))
        assert artifacts(page)[0][1] == "Architect brief [!! DIGEST MISMATCH]"
    finally:
        unserve(page)


def test_invalid_ref_is_unlinked_note(page, dashboard_fleet):
    try:
        fetched = open_view(page, dashboard_fleet,
                            planning_status(brief=None, brief_check="invalid_ref"))
        page.wait_for_timeout(1000)
        assert all(n != "architect-brief.md" for n, _ in artifacts(page))
        assert notes(page) == [
            "Architect brief: INVALID REFERENCE — escalate to the Architect"]
        assert "architect-brief.md" not in fetched
    finally:
        unserve(page)


def test_absent_shows_nothing(page, dashboard_fleet):
    try:
        fetched = open_view(page, dashboard_fleet,
                            planning_status(brief=None, brief_check="absent"))
        page.wait_for_timeout(1000)
        assert all("brief" not in n for n, _ in artifacts(page))
        assert notes(page) == []
        assert not any("brief" in f for f in fetched)
    finally:
        unserve(page)


def test_coding_kept_and_dropped(page, dashboard_fleet):
    try:
        open_view(page, dashboard_fleet, coding_status(
            source_brief=SRC_VIEW, source_brief_check="ok",
            source_brief_decision="kept"))
        a = artifacts(page)
        assert a[0] == ["source-architect-brief.md",
                        "Architect brief — from approved plan (required reading)"]
    finally:
        unserve(page)
    try:
        open_view(page, dashboard_fleet, coding_status(
            source_brief_decision="dropped"))
        assert notes(page) == [
            "Planning brief: not carried forward (Architect’s choice at coding start)"]
        assert all("brief" not in n for n, _ in artifacts(page))
    finally:
        unserve(page)


def test_identical_polls_do_not_touch_brief_entries(page, dashboard_fleet):
    try:
        open_view(page, dashboard_fleet,
                  planning_status(brief=BRIEF_VIEW, brief_check="ok"))
        page.wait_for_timeout(1000)  # let summary fills settle
        page.evaluate("""() => {
            window.__mut = 0;
            new MutationObserver(r => { window.__mut += r.length; })
              .observe(document.querySelector('#loop-artifacts'),
                       {childList: true, subtree: true, characterData: true,
                        attributes: true});
        }""")
        page.wait_for_timeout(7000)
        assert page.evaluate("() => window.__mut") == 0
    finally:
        unserve(page)


# ── create form ──────────────────────────────────────────────────────────


def open_create(page, fleet, starts):
    _navigate_to_loop(page, fleet)
    page.wait_for_selector(".loop-sidebar-section", timeout=10000)
    page.route("**/api/repo-by-key/*/loops", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"loops": []})))
    page.route("**/sketch-sources", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"sources": [{"path": ".gator/artifacts/s.md",
                                      "name": "s.md", "size": 10,
                                      "modified": "2026-10-01T00:00:00Z"}]})))

    def start(route):
        starts.append(json.loads(route.request.post_data))
        route.fulfill(status=400, content_type="application/json",
                      body=json.dumps({"error": "stop here"}))
    page.route("**/loops/start", start)
    page.evaluate(
        "() => document.querySelector('.sidebar-item[data-view=\"loop\"]').click()")
    page.wait_for_selector("#loop-brief-input", timeout=10000)


def unroute_create(page):
    for r in ("**/api/repo-by-key/*/loops", "**/sketch-sources", "**/loops/start"):
        try:
            page.unroute(r)
        except Exception:
            pass


def test_byte_counter_and_post(page, dashboard_fleet):
    starts = []
    try:
        open_create(page, dashboard_fleet, starts)
        count = lambda: page.inner_text("#loop-brief-count")
        disabled = lambda: page.evaluate(
            "() => document.querySelector('#loop-create-action').disabled")
        page.fill("#loop-brief-input", "é" * 16384)  # 32,768 bytes
        assert count() == "32,768 / 32,768 bytes"
        assert disabled() is False
        page.fill("#loop-brief-input", "é" * 16384 + "x")  # one over
        assert count().startswith("32,769 / 32,768 bytes")
        assert "over the limit" in count()
        assert disabled() is True
        # Valid brief is posted; blank brief is omitted.
        page.fill("#loop-feature-input", "feat")
        page.fill("#loop-brief-input", "Prioritize Windows paths.")
        page.wait_for_selector("#loop-sketch-select", timeout=10000)
        page.select_option("#loop-sketch-select", ".gator/artifacts/s.md")
        page.evaluate("() => document.querySelector('#loop-create-action').click()")
        page.wait_for_timeout(500)
        page.fill("#loop-brief-input", "   ")
        page.evaluate("() => document.querySelector('#loop-create-action').click()")
        page.wait_for_timeout(500)
        assert len(starts) == 2
        assert starts[0]["brief"] == "Prioritize Windows paths."
        assert "brief" not in starts[1]
    finally:
        unroute_create(page)


# ── M2a: coding-loop creation ───────────────────────────────────────────────

SRC_A = "plan-a-2026-09-30T10-00-00Z"
SRC_B = "plan-b-2026-09-30T11-00-00Z"
LIST = [
    {"loop_id": SRC_A, "feature": "plan-a", "mode": "planning",
     "stage": "plan_approved", "round": 1, "max_rounds": 3, "blocked": False,
     "created_at": "2026-09-30T10:00:00Z"},
    {"loop_id": SRC_B, "feature": "plan-b", "mode": "planning",
     "stage": "plan_approved", "round": 1, "max_rounds": 3, "blocked": False,
     "created_at": "2026-09-30T11:00:00Z"},
    {"loop_id": "coded-2026-09-30T12-00-00Z", "feature": "coded",
     "mode": "coding", "stage": "implementation_approved", "round": 0,
     "max_rounds": 3, "blocked": False, "created_at": "2026-09-30T12:00:00Z"},
    {"loop_id": "review-2026-09-30T13-00-00Z", "feature": "in-review",
     "mode": "planning", "stage": "plan_review", "round": 0, "max_rounds": 3,
     "blocked": False, "created_at": "2026-09-30T13:00:00Z"},
]


def open_coding_create(page, fleet, list_after, checks, starts, gates=None,
                       start_reply=None):
    """Create form with routed /loops (empty first so create shows), source
    /status per id with a given brief_check, and a captured /start."""
    gates = gates or {}
    _navigate_to_loop(page, fleet)
    page.wait_for_selector(".loop-sidebar-section", timeout=10000)
    state = {"list": []}
    page.route("**/api/repo-by-key/*/loops", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"loops": state["list"]})))
    page.route("**/sketch-sources", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"sources": []})))

    def body_for(lid):
        return json.dumps({"loop_id": lid, "brief_check": checks[lid],
                           "brief": None, "mode": "planning",
                           "status": {"stage": "plan_approved"}})

    def src_status(route):
        lid = route.request.url.split("/loops/")[1].split("/")[0]
        if lid in gates:
            # Hold the response WITHOUT blocking Playwright's event loop;
            # the test fulfills it later via gates[lid]["release"]().
            gates[lid]["route"] = route
            gates[lid]["release"] = lambda: route.fulfill(
                status=200, content_type="application/json", body=body_for(lid))
            return
        route.fulfill(status=200, content_type="application/json",
                      body=body_for(lid))
    for lid in checks:
        page.route("**/loops/" + lid + "/status", src_status)

    def start(route):
        starts.append(json.loads(route.request.post_data))
        status, body = start_reply or (400, {"error": "stop here"})
        route.fulfill(status=status, content_type="application/json",
                      body=json.dumps(body))
    page.route("**/loops/start", start)
    page.evaluate(
        "() => document.querySelector('.sidebar-item[data-view=\"loop\"]').click()")
    page.wait_for_selector("#loop-brief-input", timeout=10000)
    state["list"] = list_after
    page.fill("#loop-feature-input", "code")
    page.evaluate("""() => {
        var r = document.querySelector('input[name="loop-mode"][value="coding"]');
        r.checked = true; r.dispatchEvent(new Event('change'));
    }""")
    return state


def unroute_coding(page, checks):
    for r in ["**/api/repo-by-key/*/loops", "**/sketch-sources",
              "**/loops/start"] + ["**/loops/" + l + "/status" for l in checks]:
        try:
            page.unroute(r)
        except Exception:
            pass


def create_disabled(page):
    return page.evaluate(
        "() => document.querySelector('#loop-create-action').disabled")


def click_create(page):
    page.evaluate("() => document.querySelector('#loop-create-action').click()")
    page.wait_for_timeout(500)


def test_mode_toggle_and_filtered_sources(page, dashboard_fleet):
    checks = {SRC_A: "ok", SRC_B: "absent"}
    try:
        open_coding_create(page, dashboard_fleet, LIST, checks, [])
        page.wait_for_selector("#loop-source-select", timeout=10000)
        assert page.evaluate(
            "() => document.querySelector('#loop-sketch-field').hidden") is True
        opts = page.evaluate("""() => Array.from(document.querySelectorAll(
            '#loop-source-select option')).map(o => o.value)""")
        assert opts == [SRC_A, SRC_B]  # only approved planning loops
    finally:
        unroute_coding(page, checks)


def test_no_approved_sources_disables_create(page, dashboard_fleet):
    try:
        open_coding_create(page, dashboard_fleet, LIST[2:], {}, [])
        page.wait_for_function("""() => document.querySelector('#loop-source-picker')
            .textContent.indexOf('No approved planning loops') !== -1""",
            timeout=10000)
        assert create_disabled(page) is True
    finally:
        unroute_coding(page, {})


def test_keep_drop_and_absent_post_shapes(page, dashboard_fleet):
    starts = []
    checks = {SRC_A: "ok", SRC_B: "absent"}
    try:
        open_coding_create(page, dashboard_fleet, LIST, checks, starts)
        page.wait_for_selector("#loop-keep-source-brief", timeout=10000)
        assert page.evaluate(
            "() => document.querySelector('#loop-keep-source-brief').checked") is True
        assert page.locator(".loop-source-brief-warning").count() == 0
        click_create(page)  # keep
        page.evaluate("() => document.querySelector('#loop-keep-source-brief').click()")
        click_create(page)  # drop
        page.select_option("#loop-source-select", SRC_B)
        page.wait_for_function("""() => !document.querySelector('#loop-keep-source-brief')
            && document.querySelector('#loop-source-brief').textContent === ''""",
            timeout=10000)
        click_create(page)  # absent -> no source_brief
        assert [s.get("source_brief") for s in starts] == ["keep", "drop", None]
        assert all(s["mode"] == "coding" and "sketch_path" not in s for s in starts)
        assert [s["from_loop"] for s in starts] == [SRC_A, SRC_A, SRC_B]
    finally:
        unroute_coding(page, checks)


def test_corrupt_source_warns_keeps_default_and_allows_drop(page, dashboard_fleet):
    starts = []
    checks = {SRC_A: "mismatch", SRC_B: "absent"}
    reply = (400, {"error": "The approved plan's Architect brief failed its "
                            "integrity check (mismatch); start with "
                            "--source-brief drop"})
    try:
        open_coding_create(page, dashboard_fleet, LIST, checks, starts,
                           start_reply=reply)
        page.wait_for_selector(".loop-source-brief-warning", timeout=10000)
        warn = page.inner_text(".loop-source-brief-warning")
        assert "DIGEST MISMATCH" in warn and "uncheck to start without it" in warn
        assert page.evaluate(
            "() => document.querySelector('#loop-keep-source-brief').checked") is True
        click_create(page)
        err = page.inner_text("#loop-create-error")
        assert "integrity check" in err  # honest server error shown
        page.evaluate("() => document.querySelector('#loop-keep-source-brief').click()")
        click_create(page)
        assert [s["source_brief"] for s in starts] == ["keep", "drop"]
    finally:
        unroute_coding(page, checks)


def test_stale_source_status_is_ignored(page, dashboard_fleet):
    """A slow /status for source A, superseded by selecting B, never
    updates the control."""
    held = {SRC_A: {}}
    checks = {SRC_A: "mismatch", SRC_B: "ok"}
    try:
        open_coding_create(page, dashboard_fleet, LIST, checks, [], gates=held)
        page.wait_for_selector("#loop-source-select", timeout=10000)
        for _ in range(50):  # A's /status request is now held, unanswered
            if "release" in held[SRC_A]:
                break
            page.wait_for_timeout(100)
        assert "release" in held[SRC_A]
        assert "Checking" in page.inner_text("#loop-source-brief")
        assert create_disabled(page) is True  # pending source state
        page.select_option("#loop-source-select", SRC_B)
        page.wait_for_selector("#loop-keep-source-brief", timeout=10000)
        held[SRC_A]["release"]()  # A's stale "mismatch" arrives late
        page.wait_for_timeout(1000)
        assert page.locator(".loop-source-brief-warning").count() == 0
        assert create_disabled(page) is False
    finally:
        unroute_coding(page, checks)
