"""Loop workspace seed extension.

Registers `seed_loop_fixtures` on the harness so every repo built
via `build_dashboard_fleet` gains the `.gator/loops/` fixtures the
Loop Playwright pins exercise. Imported at module scope from
`conftest.py` so the reassignment lands BEFORE any fixture builds
the fleet.

Fixtures landed (alpha repo only):

- `.gator/loops/active-loop-2026-09-22T10-00-00Z/` — an active
  loop in `plan_drafting` stage, round 1, with events, sketch, and
  plan artifacts. Exercises list rendering, status panel, timeline,
  and artifact inspector.
- `.gator/loops/done-loop-2026-09-20T10-00-00Z/` — a terminal loop
  in `plan_approved` stage. Exercises terminal badge rendering and
  active-first sort order.
- `.gator/loops/xss-loop-2026-09-21T10-00-00Z/` — an active loop
  whose artifact contains HTML/script content. Exercises escaped
  artifact rendering.
"""

import json

from . import _harness as _h


_ACTIVE_LOOP_ID = "active-loop-2026-09-22T10-00-00Z"
_DONE_LOOP_ID = "done-loop-2026-09-20T10-00-00Z"
_XSS_LOOP_ID = "xss-loop-2026-09-21T10-00-00Z"


def _make_session(loop_id, feature, stage, round_num, max_rounds,
                  blocked=False, escalation_reason=None):
    s = {
        "schema": "gator-loop-session-v1",
        "loop_id": loop_id,
        "feature": feature,
        "created_at": "2026-09-22T10:00:00+00:00",
        "roles": {
            "draftor": {"role": "draftor", "joined": True},
            "reviewer": {"role": "reviewer", "joined": True},
            "architect": {"role": "architect"},
        },
        "status": {
            "stage": stage,
            "next_role": "draftor",
            "round": round_num,
            "max_rounds": max_rounds,
            "blocked": blocked,
            "turn_deadline": "2099-12-31T23:59:59+00:00",
            "turn_timeout_seconds": 300,
            "last_updated": "2026-09-22T10:00:00+00:00",
        },
        "current": {"draft": None, "findings": None},
        "turns": [],
        "decisions": [],
    }
    if escalation_reason:
        s["status"]["escalation_reason"] = escalation_reason
    return s


def _make_events(events):
    lines = [json.dumps(e, separators=(",", ":")) for e in events]
    return "\n".join(lines) + "\n"


def seed_loop_fixtures(repo):
    if repo.name != "alpha":
        return
    loops = repo / ".gator" / "loops"
    loops.mkdir(exist_ok=True)

    # Active loop
    active = loops / _ACTIVE_LOOP_ID
    active.mkdir()
    (active / "session.json").write_text(
        json.dumps(_make_session(
            _ACTIVE_LOOP_ID, "widget-refactor", "plan_drafting",
            round_num=1, max_rounds=3,
        ), indent=2), encoding="utf-8")
    (active / "events.jsonl").write_text(
        _make_events([
            {"event": "loop_started", "ts": "2026-09-22T10:00:00Z",
             "round": 0},
            {"event": "draft_submitted", "ts": "2026-09-22T10:01:00Z",
             "round": 1, "role": "draftor",
             "artifact_path": "plan.round-1.md"},
            {"event": "revision_requested", "ts": "2026-09-22T10:02:00Z",
             "round": 2, "role": "reviewer",
             "artifact_path": "findings.round-1.md"},
        ]), encoding="utf-8")
    (active / "sketch.md").write_text(
        "# Widget Refactor Sketch\n\nRefactor the widget layer.\n",
        encoding="utf-8")
    _plan_text = (
        "# Plan v1\n\n## Executive Summary\n\n"
        "- Refactor widget layer into composable units\n"
        "- Key decision: event-driven over polling\n"
        "- Risk: backward compat with v1 consumers\n"
        "- Verify via integration test suite\n\n"
        "## Summary\n\n- Step 1\n- Step 2\n")
    (active / "plan.current.md").write_text(_plan_text, encoding="utf-8")
    (active / "plan.round-1.md").write_text(_plan_text, encoding="utf-8")
    _findings_text = (
        "# Review: Widget Refactor\n\n## Verdict\n\n"
        "REVISE\n\n## Findings\n\n### Finding 1: Missing error path\n"
        "**Severity**: High\n**Issue**: No fallback for widget load failure\n")
    (active / "findings.current.md").write_text(_findings_text, encoding="utf-8")
    (active / "findings.round-1.md").write_text(_findings_text, encoding="utf-8")

    # Terminal (approved) loop
    done = loops / _DONE_LOOP_ID
    done.mkdir()
    (done / "session.json").write_text(
        json.dumps(_make_session(
            _DONE_LOOP_ID, "auth-migration", "plan_approved",
            round_num=2, max_rounds=3,
        ), indent=2), encoding="utf-8")
    (done / "events.jsonl").write_text(
        _make_events([
            {"event": "loop_started", "ts": "2026-09-20T10:00:00Z",
             "round": 0},
            {"event": "plan_approved", "ts": "2026-09-20T10:10:00Z",
             "round": 2},
        ]), encoding="utf-8")

    # XSS-exercise loop — artifact content has HTML tags
    xss = loops / _XSS_LOOP_ID
    xss.mkdir()
    (xss / "session.json").write_text(
        json.dumps(_make_session(
            _XSS_LOOP_ID, "xss-test", "plan_review",
            round_num=1, max_rounds=3,
        ), indent=2), encoding="utf-8")
    (xss / "events.jsonl").write_text(
        _make_events([
            {"event": "loop_started", "ts": "2026-09-21T10:00:00Z",
             "round": 0},
        ]), encoding="utf-8")
    (xss / "sketch.md").write_text(
        '<script>alert("xss")</script><img src=x onerror=alert(1)>',
        encoding="utf-8")


_h.seed_loop_fixtures = seed_loop_fixtures  # noqa: reassign stub
