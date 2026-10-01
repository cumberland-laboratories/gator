"""#41 Module 5 (UI) — coding candidate panel, live resolution banner,
Reopen control, coding artifacts, and polling behavior.

Routes /status, /events, /snapshot, /artifact and /reopen for the seeded
active loop with crafted allowlisted payloads (the seeded fleet has no
real coding loop). Resolution states are asserted as text + glyph +
data-state (never hue alone). Includes the #44 core: selecting a live loop
after a terminal one restarts polling.
"""

import copy
import json

from .test_loop_workspace import _navigate_to_loop, _select_loop_card

ACTIVE_ID = "active-loop-2026-09-22T10-00-00Z"
T1 = "1" * 40
H1 = "a" * 40
BASE = "b" * 40
BTREE = "c" * 40

EVENTS = [
    {"event": "loop_started", "ts": "2026-09-22T10:00:00Z", "round": 0,
     "mode": "coding"},
    {"event": "implementation_submitted", "ts": "2026-09-22T10:01:00Z",
     "round": 0, "role": "draftor",
     "artifact_path": "implementation.round-0.md",
     "detail": "Implementation submitted"},
]


def coding_status(stage="implementation_review", approval=None, review=None,
                  residue_other=0):
    return {
        "loop_id": ACTIVE_ID, "feature": "widget-refactor", "mode": "coding",
        "created_at": "2026-09-22T10:00:00+00:00",
        "status": {"stage": stage,
                   "next_role": {"implementation_review": "reviewer",
                                 "implementation_revision": "draftor",
                                 "implementation_drafting": "draftor"}.get(stage),
                   "round": 0, "max_rounds": 3, "blocked": False,
                   "turn_deadline": "2099-12-31T23:59:59+00:00",
                   "turn_timeout_seconds": 300,
                   "last_updated": "2026-09-22T10:01:00+00:00"},
        "roles": {"draftor": {"role": "draftor", "joined": True},
                  "reviewer": {"role": "reviewer", "joined": True}},
        "decisions": [],
        "coding": {
            "source_loop_id": "source-plan-2026-09-21T10-00-00Z",
            "plan_sha256": "f" * 64, "base_head": BASE, "base_tree": BTREE,
            "generations": [{
                "round": 0, "submitted_at": "2026-09-22T10:01:00+00:00",
                "artifact_path": "implementation.round-0.md",
                "staged_tree": T1, "current_head": H1,
                "branch": "refs/heads/feature", "detached": False,
                "changed_count": 3, "changed_by_status": {"A": 1, "M": 2},
                "residue_other_count": residue_other,
                "residue_loop_count": 7,
                "review": review,
            }],
            "approval": approval,
        },
    }


APPROVED_REVIEW = {"verdict": "approve", "reviewed_tree": T1,
                   "reviewed_head": H1, "candidate_changed": False,
                   "reviewed_at": "2026-09-22T10:02:00+00:00"}
APPROVAL = {"tree": T1, "head": H1, "round": 0, "ts": "x",
            "invalidated_at": None}


def snapshot(state, reason=None, commit=None):
    return {"schema": "gator-loop-coding-snapshot-v1",
            "stage": "implementation_approved",
            "approval_resolution": {"state": state, "reason": reason,
                                    "commit": commit, "approved_tree": T1,
                                    "approved_head": H1},
            "live": {"ok": state != "unknown"}}


def serve(page, holder):
    """holder: {"status":..., "snapshot":..., "reopen_calls": []}."""
    def fulfill(route, body, status=200):
        route.fulfill(status=status, content_type="application/json",
                      headers={"Cache-Control": "no-store"},
                      body=json.dumps(body))
    page.route("**/" + ACTIVE_ID + "/status",
               lambda r: fulfill(r, holder["status"]))
    page.route("**/" + ACTIVE_ID + "/events",
               lambda r: fulfill(r, {"events": EVENTS}))
    page.route("**/" + ACTIVE_ID + "/snapshot",
               lambda r: fulfill(r, holder["snapshot"]))
    page.route("**/" + ACTIVE_ID + "/liveness",
               lambda r: fulfill(r, {"available": False,
                                     "degraded": "unavailable",
                                     "roles": None}))
    page.route("**/" + ACTIVE_ID + "/artifact/**",
               lambda r: r.fulfill(status=200, content_type="text/plain",
                                   body="# Artifact\n\n## Executive Summary\n\n- x\n"))

    def reopen(route):
        holder["reopen_calls"].append(
            (route.request.post_data,
             route.request.headers.get("x-gator-dashboard")))
        fulfill(route, {"ok": True, "stage": "implementation_revision",
                        "round": 0, "watcher": "attached",
                        "watcher_detail": None})
    page.route("**/" + ACTIVE_ID + "/reopen", reopen)


def unserve(page):
    for suffix in ("status", "events", "snapshot", "liveness", "artifact/**",
                   "reopen"):
        try:
            page.unroute("**/" + ACTIVE_ID + "/" + suffix)
        except Exception:
            pass


def open_view(page, fleet, holder):
    serve(page, holder)
    _navigate_to_loop(page, fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    _select_loop_card(page, "widget-refactor")
    page.wait_for_selector(".loop-coding", timeout=10000)


def text_of(page, sel):
    return page.evaluate("(s) => { var e = document.querySelector(s);"
                         " return e ? e.textContent : null; }", sel)


def test_coding_facts_and_artifacts(page, dashboard_fleet):
    holder = {"status": coding_status(residue_other=2), "snapshot": None,
              "reopen_calls": []}
    try:
        open_view(page, dashboard_fleet, holder)
        txt = text_of(page, ".loop-coding")
        assert "source-plan-2026-09-21T10-00-00Z" in txt
        assert T1[:12] in txt and H1[:12] in txt and "(feature)" in txt
        assert "3 (A 1, M 2)" in txt
        assert "Awaiting review" in txt
        assert "2 unstaged/untracked path(s)" in txt
        assert "Code Review" in text_of(page, ".loop-status-header")
        names = page.evaluate("""() => Array.from(document.querySelectorAll(
            '.loop-artifact-section')).map(s => s.dataset.artifact)""")
        assert names[:3] == ["approved-plan.md", "implementation.current.md",
                             "findings.current.md"]
        assert "sketch.md" not in names
        assert page.locator(".loop-coding-resolution").count() == 0
    finally:
        unserve(page)


def test_pending_banner_and_polling_continues(page, dashboard_fleet):
    holder = {"status": coding_status("implementation_approved", APPROVAL,
                                      APPROVED_REVIEW),
              "snapshot": snapshot("pending"), "reopen_calls": []}
    try:
        open_view(page, dashboard_fleet, holder)
        page.wait_for_selector('.loop-coding-resolution[data-state="pending"]',
                               timeout=10000)
        banner = text_of(page, ".loop-coding-resolution")
        assert banner.startswith("● Pending commit")
        assert "one normal commit" in banner and T1[:12] in banner
        assert page.locator(".loop-coding-reopen-btn").count() == 0
        # Approved coding loops keep polling: a commit flips the banner.
        assert page.evaluate(
            "() => document.querySelector('.loop-workspace').dataset.polling") == "1"
        holder["snapshot"] = snapshot("committed", commit="9" * 40)
        page.wait_for_selector('.loop-coding-resolution[data-state="committed"]',
                               timeout=10000)
        banner = text_of(page, ".loop-coding-resolution")
        assert banner.startswith("✓ Committed") and ("9" * 12) in banner
    finally:
        unserve(page)


def test_stale_reopen_flow(page, dashboard_fleet):
    holder = {"status": coding_status("implementation_approved", APPROVAL,
                                      APPROVED_REVIEW),
              "snapshot": snapshot("stale", reason="staged_tree_changed"),
              "reopen_calls": []}
    try:
        open_view(page, dashboard_fleet, holder)
        page.wait_for_selector('.loop-coding-resolution[data-state="stale"]',
                               timeout=10000)
        banner = text_of(page, ".loop-coding-resolution")
        assert banner.startswith("⚠ Stale")
        assert "the staged tree changed after approval" in banner
        page.evaluate(
            "() => document.querySelector('.loop-coding-reopen-btn').click()")
        page.wait_for_selector(".loop-coding-reopen-reason", timeout=5000)
        assert page.evaluate(
            "() => document.querySelector('.loop-coding-reopen-send').disabled") is True
        page.fill(".loop-coding-reopen-reason", "half typed")
        page.wait_for_timeout(4000)  # polls must not wipe the open form
        assert page.evaluate(
            "() => document.querySelector('.loop-coding-reopen-reason').value"
        ) == "half typed"
        page.evaluate(
            "() => document.querySelector('.loop-coding-reopen-send').click()")
        page.wait_for_selector("#loop-region-notice .loop-extend-notice",
                               timeout=5000)
        assert len(holder["reopen_calls"]) == 1
        body, header = holder["reopen_calls"][0]
        assert json.loads(body) == {"message": "half typed"} and header == "1"
        assert "Reopened" in text_of(page, "#loop-region-notice")
    finally:
        unserve(page)


def test_unknown_banner_offers_reopen(page, dashboard_fleet):
    holder = {"status": coding_status("implementation_approved", APPROVAL,
                                      APPROVED_REVIEW),
              "snapshot": snapshot("unknown", reason="conflict"),
              "reopen_calls": []}
    try:
        open_view(page, dashboard_fleet, holder)
        page.wait_for_selector('.loop-coding-resolution[data-state="unknown"]',
                               timeout=10000)
        banner = text_of(page, ".loop-coding-resolution")
        assert banner.startswith("? Unknown") and "never treat as approved" in banner
        assert page.locator(".loop-coding-reopen-btn").count() == 1
    finally:
        unserve(page)


def test_identical_polls_do_not_touch_coding_region(page, dashboard_fleet):
    holder = {"status": coding_status("implementation_approved", APPROVAL,
                                      APPROVED_REVIEW),
              "snapshot": snapshot("pending"), "reopen_calls": []}
    try:
        open_view(page, dashboard_fleet, holder)
        page.wait_for_selector('.loop-coding-resolution[data-state="pending"]',
                               timeout=10000)
        page.evaluate("""() => {
            window.__codingMut = 0;
            document.querySelector('.loop-coding').__probe = 1;
            new MutationObserver(r => { window.__codingMut += r.length; })
              .observe(document.querySelector('#loop-region-coding'),
                       {childList: true, subtree: true, characterData: true,
                        attributes: true});
        }""")
        page.wait_for_timeout(7000)  # >= two polls (status + snapshot)
        assert page.evaluate("() => window.__codingMut") == 0
        assert page.evaluate(
            "() => document.querySelector('.loop-coding').__probe") == 1
    finally:
        unserve(page)


def test_selecting_live_loop_restarts_polling(page, dashboard_fleet):
    """#44 core: a terminal selection stops the timer; selecting a live loop
    must start it again without re-navigating."""
    _navigate_to_loop(page, dashboard_fleet)
    page.wait_for_selector(".loop-status-header", timeout=10000)
    _select_loop_card(page, "auth-migration")  # seeded terminal loop
    page.wait_for_function(
        "() => document.querySelector('.loop-workspace').dataset.polling === '0'",
        timeout=10000)
    _select_loop_card(page, "widget-refactor")  # seeded live loop
    page.wait_for_function(
        "() => document.querySelector('.loop-workspace').dataset.polling === '1'",
        timeout=10000)
