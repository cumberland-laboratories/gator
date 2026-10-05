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


# ---------------------------------------------------------------------------
# #55 M4: checkpoint counters (header + sidebar), progress list, labels
# ---------------------------------------------------------------------------

import pytest  # noqa: E402

CP_BASE2 = "d" * 40


def checkpoint_status(stage="implementation_revision"):
    """A declared two-checkpoint loop on cp2 with status.round 3 above
    max_rounds 2: the per-checkpoint findings round is 2 of 2."""
    st = coding_status(stage)
    st["status"].update(round=3, max_rounds=2)
    gens = []
    for g, cp in enumerate(["cp1", "cp1", "cp2", "cp2"]):
        gen = copy.deepcopy(st["coding"]["generations"][0])
        gen.update(round=min(g, 3), generation=g, checkpoint_id=cp,
                   artifact_path="implementation.round-%d.md" % g)
        gens.append(gen)
    st["coding"]["generations"] = gens
    st["coding"]["generation"] = 3
    st["coding"]["checkpoints"] = {
        "source": "declared", "current": 1, "count": 2,
        "items": [
            {"id": "cp1", "index": 1, "title": "Widget core",
             "state": "approved", "base_tree": BTREE,
             "accepted_tree": CP_BASE2, "findings_rounds": 1},
            {"id": "cp2", "index": 2, "title": "Widget wiring",
             "state": "active", "base_tree": CP_BASE2,
             "accepted_tree": None, "findings_rounds": 2},
        ]}
    return st


CP_EVENTS = EVENTS[:1] + [
    {"event": "implementation_submitted", "ts": "2026-09-22T10:01:00Z",
     "round": 0, "role": "draftor", "generation": 0, "checkpoint_id": "cp1",
     "artifact_path": "implementation.round-0.md", "detail": "cp1 submitted"},
    {"event": "checkpoint_approved", "ts": "2026-09-22T10:02:00Z",
     "round": 0, "role": "reviewer", "generation": 0, "checkpoint_id": "cp1",
     "artifact_path": "findings.round-0.md", "detail": "cp1 approved"},
]

LIST_SUMMARY = {"index": 2, "count": 2, "findings_round": 2,
                "findings_budget": 2, "generation": 3}


def serve_list(page, mutate):
    """Pass /loops through, letting ``mutate(items)`` add summaries."""
    def handler(route):
        resp = route.fetch()
        data = resp.json()
        mutate(data.get("loops") or [])
        route.fulfill(response=resp, body=json.dumps(data),
                      headers={"Content-Type": "application/json",
                               "Cache-Control": "no-store"})
    page.route("**/loops", handler)


def _add_summaries(items):
    for it in items:
        if it.get("loop_id") == ACTIVE_ID or it.get("feature") == "auth-migration":
            it["round"], it["max_rounds"] = 3, 2
            it["checkpoint_summary"] = dict(LIST_SUMMARY)


def card_counter(page, feature):
    return page.evaluate("""(name) => {
        var cards = document.querySelectorAll('.loop-sidebar-card');
        for (var i = 0; i < cards.length; i++) {
          if (cards[i].querySelector('.loop-card-feature').textContent === name)
            return cards[i].querySelector('.loop-card-meta').textContent;
        }
        return null; }""", feature)


@pytest.mark.parametrize("kind", ["checkpoint-active", "checkpoint-terminal",
                                  "legacy"])
def test_counters_header_and_sidebar(page, dashboard_fleet, kind):
    if kind == "legacy":
        status = coding_status("implementation_revision")
        status["status"].update(round=1, max_rounds=3)
    else:
        status = checkpoint_status("max_rounds_exceeded"
                                   if kind == "checkpoint-terminal"
                                   else "implementation_revision")
    holder = {"status": status, "snapshot": None, "reopen_calls": []}
    try:
        if kind != "legacy":
            serve_list(page, _add_summaries)
        open_view(page, dashboard_fleet, holder)
        header = page.evaluate(
            "() => (document.querySelector('.loop-status-grid') ||"
            " document.querySelector('.loop-outcome-meta')).textContent")
        active_card = card_counter(page, "widget-refactor")
        history_card = card_counter(page, "auth-migration")
        if kind == "legacy":
            assert "Round" in header and "1 / 3" in header
            assert "Checkpoint" not in header
            assert "Round " in active_card
            return
        assert "Checkpoint 2 of 2 · findings round 2 of 2" in header
        assert "Generation" in header and "3" in header
        assert "Checkpoint 2/2 · findings 2/2 · gen 3" in active_card
        assert "Checkpoint 2/2 · findings 2/2 · gen 3" in history_card
        # No checkpoint-loop surface ever shows Round X/Y (here: 3/2).
        for txt in (header, active_card, history_card,
                    text_of(page, ".loop-coding")):
            assert "Round" not in txt and "3/2" not in txt and "3 / 2" not in txt
        # Planning cards keep Round X/Y.
        planning = page.evaluate("""() => Array.from(document.querySelectorAll(
            '.loop-sidebar-card .loop-card-meta')).map(e => e.textContent)""")
        assert any(t.startswith("Round ") for t in planning)
    finally:
        try:
            page.unroute("**/loops")
        except Exception:
            pass
        unserve(page)


def test_checkpoint_progress_and_labels(page, dashboard_fleet):
    holder = {"status": checkpoint_status(), "snapshot": None,
              "reopen_calls": []}
    try:
        serve(page, holder)
        page.unroute("**/" + ACTIVE_ID + "/events")   # swap in checkpoint events
        page.route("**/" + ACTIVE_ID + "/events",
                   lambda r: r.fulfill(status=200,
                                       content_type="application/json",
                                       body=json.dumps({"events": CP_EVENTS})))
        _navigate_to_loop(page, dashboard_fleet)
        page.wait_for_selector(".loop-status-header", timeout=10000)
        _select_loop_card(page, "widget-refactor")
        page.wait_for_selector(".loop-checkpoint-list", timeout=10000)
        items = page.evaluate("""() => Array.from(document.querySelectorAll(
            '.loop-checkpoint-item')).map(e => [e.dataset.state,
              e.querySelector('.loop-checkpoint-glyph').textContent,
              e.textContent])""")
        assert [i[0] for i in items] == ["approved", "active"]
        assert items[0][1] == "✓" and "approved (tree dddddddddddd)" in items[0][2]
        assert items[1][1] == "●" and "cp2 Widget wiring" in items[1][2]
        assert "active" in items[1][2]
        weight = page.evaluate("""() => getComputedStyle(document.querySelector(
            '.loop-checkpoint-item[data-state="active"]')).fontWeight""")
        assert int(weight) >= 600
        coding = text_of(page, ".loop-coding")
        assert "Candidate (cp2 · gen 3)" in coding
        page.wait_for_selector(".loop-event", timeout=10000)
        labels = page.evaluate("""() => Array.from(document.querySelectorAll(
            '.loop-event-label')).map(e => e.textContent)""")
        assert "Checkpoint approved (cp1 · gen 0)" in labels
        assert "Implementation submitted (cp1 · gen 0)" in labels
        toggles = page.evaluate("""() => Array.from(document.querySelectorAll(
            '.loop-artifact-toggle')).map(e => e.textContent)""")
        assert "findings.round-0.md (cp1 · gen 0)" in toggles
        assert "implementation.round-0.md (cp1 · gen 0)" in toggles
    finally:
        unserve(page)


def test_identical_checkpoint_polls_are_mutation_free(page, dashboard_fleet):
    holder = {"status": checkpoint_status(), "snapshot": None,
              "reopen_calls": []}
    try:
        open_view(page, dashboard_fleet, holder)
        page.wait_for_selector(".loop-checkpoint-list", timeout=10000)
        # The header grid's live time fields tick by design; the checkpoint
        # counters must survive identical polls untouched (same nodes).
        page.evaluate("""() => {
            window.__cpMut = 0;
            var obs = new MutationObserver(r => { window.__cpMut += r.length; });
            ['#loop-region-coding', '.loop-checkpoint-counter',
             '.loop-generation-counter'].forEach(s => {
              var el = document.querySelector(s);
              el.__probe = 1;
              obs.observe(el, {childList: true, subtree: true,
                               characterData: true, attributes: true});
            });
        }""")
        page.wait_for_timeout(7000)  # >= two polls
        assert page.evaluate("() => window.__cpMut") == 0
        assert page.evaluate("""() => ['.loop-checkpoint-counter',
            '.loop-generation-counter'].every(s =>
              document.querySelector(s).__probe === 1)""")
    finally:
        unserve(page)
