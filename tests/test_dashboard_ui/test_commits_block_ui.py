"""Commits view: the blocked-commit alert and dialog (#76).

The override routes are stubbed with `page.route`; the relay and the CLI
behind it are covered by tests/test_dashboard_override.py and
tests/test_precommit_override.py. Each test proves a distinct risk:

- no alert (and no repeated request) without a block: there is no poller;
- every alert state maps to its label, and Approve appears only for an
  uncovered external-approval rule (never for pause, fix, mixed pause+fix,
  approved, refresh or unavailable states);
- a partial approval keeps the uncovered rule visible and approvable;
- the approval flow: prefill, delay countdown, required reason, a refusal
  keeping the fields with role=alert, and the mixed-state honesty string;
- a state that changed after the dialog opened is never approved unseen;
- Escape cannot close the dialog while a request is in flight;
- Discard needs confirmation and re-reads the state first (malformed
  recovery included);
- the dialog is centred and fits at 1440px and 375px.
"""

import copy
import json
from datetime import datetime, timezone

import pytest

REV = "0123456789abcdef"
REV2 = "fedcba9876543210"
BLOCK = "a1b2c3d4"


def _origin(fleet):
    return fleet["url"].rstrip("/") + "/"


def _history():
    now = datetime.now(timezone.utc).isoformat()
    h = "abc0001" + "f" * 33
    return {"repo": "alpha", "commits": [{
        "hash": h, "short_hash": h[:7], "date": now, "author": "test",
        "subject": "Feature: something", "body": "", "description": "",
        "trailers": [], "agent": "", "architect": ""}]}


def _finding(rule, resolution, covered=False, message="Rule message."):
    return {"rule": rule, "resolution": resolution, "message": message,
            "covered": covered, "legacy": False}


EXT = _finding("charter-alongside-code", "external-approval")
PAUSE = _finding("dangerous-pattern-pause", "pause")
FIX = _finding("invalid-change-type", "fix-required")


def _status(state="blocked", findings=(EXT,), **over):
    findings = [dict(f) for f in findings]
    uncovered = [f["rule"] for f in findings
                 if f["resolution"] == "external-approval" and not f["covered"]]
    covered = [f["rule"] for f in findings if f["covered"]]
    s = {
        "schema": "gator-override-status-v1", "state": state, "revision": REV,
        "malformed": [],
        "block": {"block_id": BLOCK, "created_at": "t", "created_epoch": 1,
                  "expires_at": "t", "expires_epoch": 4102444800, "age_seconds": 42,
                  "tree_matches": True, "files": ["foo.py"], "files_total": 1},
        "findings": findings,
        "approval": {"state": "absent", "detail": "", "approval_id": None,
                     "approved_by": None, "approved_at": None, "approved_rules": []},
        "approvable_rules": [f["rule"] for f in findings
                             if f["resolution"] == "external-approval"],
        "covered_rules": covered, "uncovered_external_rules": uncovered,
        "can_approve": bool(uncovered), "approve_refusal": None if uncovered else
        "nothing-approvable", "approve_wait_seconds": 0, "min_approval_delay_seconds": 10,
        "architect_default": "Test Architect",
    }
    s.update(over)
    return s


class Stub:
    """Serve a sequence of override statuses (the last repeats) and record
    every override request."""

    def __init__(self, page, statuses, post=None, history=None):
        self.statuses = [copy.deepcopy(s) for s in statuses]
        self.gets = 0
        self.posts = []
        self.held = []
        self.post = post or (lambda action, body: (200, {"ok": True, "message": "ok",
                                                         "remaining": {"fix_required": [],
                                                                       "paused": []}}))
        page.route("**/api/repo/alpha/history*", history or (lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(_history()))))
        page.route("**/api/repo/alpha/override", self._get)
        page.route("**/api/repo/alpha/override/*", self._post)

    def _get(self, route):
        s = self.statuses[min(self.gets, len(self.statuses) - 1)]
        self.gets += 1
        if s == "fail":
            route.fulfill(status=500, content_type="application/json",
                          body='{"error": "boom"}')
            return
        route.fulfill(status=200, content_type="application/json", body=json.dumps(s))

    def _post(self, route):
        action = route.request.url.rsplit("/", 1)[1]
        body = json.loads(route.request.post_data or "{}")
        self.posts.append((action, body, route.request.headers.get("x-gator-dashboard")))
        result = self.post(action, body)
        if result == "hold":
            self.held.append(route)
            return
        status, data = result
        route.fulfill(status=status, content_type="application/json", body=json.dumps(data))


def _open(page, fleet, stub, alert=True):
    page.goto(_origin(fleet) + "?repo=alpha&view=history", wait_until="load")
    page.wait_for_selector(".commit-row", timeout=15000)
    if alert:
        page.wait_for_selector(".commit-block-alert", timeout=10000)
    return stub


def _open_dialog(page):
    page.click(".commit-block-alert")
    page.wait_for_selector("dialog.commit-block-dialog[open]", timeout=5000)


def test_no_alert_and_no_poll_without_block(page, dashboard_fleet):
    stub = Stub(page, [_status("none", findings=(), revision=None, block=None)])
    _open(page, dashboard_fleet, stub, alert=False)
    page.wait_for_timeout(3000)
    assert page.locator(".commit-block-alert").count() == 0
    assert stub.gets == 1, "fetched once; no poller"


CASES = {
    "blocked": (_status(), "⚑ Commit blocked", True),
    "pause": (_status(findings=(PAUSE,)), "⚑ Architect decision needed", False),
    "fix": (_status(findings=(FIX,)), "⚑ Commit fix needed", False),
    "pause+fix": (_status(findings=(PAUSE, FIX)), "⚑ Commit blocked", False),
    "approved": (_status("approved", findings=(dict(EXT, covered=True),)),
                 "✓ Approved — retry commit", False),
    "stale": (_status("stale", approve_refusal="tree-changed"),
              "⚑ Commit block needs refresh", False),
    "malformed": (_status("malformed", findings=(), block=None, malformed=["block"]),
                  "⚑ Commit block needs refresh", False),
    "incomplete": (_status("incomplete", can_approve=False, uncovered_external_rules=[],
                           approve_refusal="too-many-findings", findings_total=250,
                           message="Too many findings.", command="gator hook override status"),
                   "⚑ Commit block needs refresh", False),
    "unsupported": ({"schema": "gator-override-status-v1", "state": "unsupported",
                     "message": "Run gator update.", "command": "gator hook override status"},
                    "⚑ Commit status unavailable", False),
}


@pytest.mark.parametrize("case", list(CASES))
def test_alert_label_and_actions_per_state(page, dashboard_fleet, case):
    status, label, approve = CASES[case]
    stub = Stub(page, [status])
    _open(page, dashboard_fleet, stub)
    assert page.text_content(".commit-block-alert") == label
    order = page.evaluate("""() => Array.from(document.querySelector('.commit-toolbar').children)
        .map(e => e.className.split(' ')[0])""")
    assert order == ["commit-filters", "commit-block-alert", "commit-search"]
    _open_dialog(page)
    assert page.locator(".commit-block-approve").count() == (1 if approve else 0)
    if case == "malformed":
        assert page.locator(".commit-block-discard").count() == 1
    if case in ("unsupported", "incomplete"):
        assert "gator hook override status" in page.text_content(".commit-block-command")


def test_partial_approval_keeps_uncovered_rule_actionable(page, dashboard_fleet):
    gap = _finding("charter-index-gap", "external-approval")
    s = _status(findings=(dict(EXT, covered=True), gap))
    s["approval"].update({"state": "valid", "approved_by": "Alan", "approval_id": "ap01"})
    stub = Stub(page, [s])
    _open(page, dashboard_fleet, stub)
    assert page.text_content(".commit-block-alert") == "⚑ Commit blocked"
    _open_dialog(page)
    tags = page.evaluate("""() => Array.from(document.querySelectorAll('.commit-block-finding'))
        .map(li => [li.dataset.rule, li.querySelector('.commit-block-tag').textContent])""")
    assert tags == [["charter-alongside-code", "✓ Approved by Alan"],
                    ["charter-index-gap", "Needs approval"]]
    assert "Still needs approval: charter-index-gap." in page.text_content("dialog")
    assert page.locator(".commit-block-approve").count() == 1


def test_approve_flow(page, dashboard_fleet):
    answers = [
        (409, {"ok": False, "refusal": "write-failed", "message": "Disk is full.",
               "remaining": {"fix_required": [], "paused": []}}),
        (200, {"ok": True, "message": "Override approved.",
               "remaining": {"fix_required": [], "paused": ["dangerous-pattern-pause"]}}),
    ]
    stub = Stub(page, [_status(findings=(EXT, PAUSE), approve_wait_seconds=2)],
                post=lambda action, body: answers.pop(0))
    _open(page, dashboard_fleet, stub)
    _open_dialog(page)
    assert page.input_value("#commit-block-name") == "Test Architect"
    btn = page.locator(".commit-block-approve")
    assert btn.is_disabled() and "available in" in btn.text_content()
    page.fill("#commit-block-reason", "No charter edit is warranted.")
    assert page.text_content(".commit-block-count") == "29 / 500"
    page.wait_for_function(
        "() => !document.querySelector('.commit-block-approve').disabled", timeout=5000)
    assert btn.text_content() == "Approve"

    btn.click()
    page.wait_for_selector(".commit-block-error:not([hidden])", timeout=5000)
    assert page.get_attribute(".commit-block-error", "role") == "alert"
    assert page.text_content(".commit-block-error") == "Disk is full."
    assert page.input_value("#commit-block-reason") == "No charter edit is warranted."

    page.click(".commit-block-approve")
    page.wait_for_selector(".commit-block-success", timeout=5000)
    assert page.text_content(".commit-block-success") == (
        "External approval recorded. This commit is still blocked until the "
        "remaining findings are resolved.")
    action, body, header = stub.posts[-1]
    assert action == "approve" and header == "1"
    assert body == {"block_id": BLOCK, "revision": REV, "name": "Test Architect",
                    "reason": "No charter edit is warranted."}


def test_reason_paste_length_and_resize(page, dashboard_fleet):
    """A reason pasted from a terminal (line breaks, tabs) counts and is sent
    as one line; over 500 characters Approve stays disabled and the counter
    says so, with nothing silently cut; the textarea resizes vertically."""
    stub = Stub(page, [_status(findings=(EXT,), approve_wait_seconds=0)],
                post=lambda action, body: (200, {"ok": True, "message": "Override approved.",
                                                 "remaining": {"fix_required": [], "paused": []}}))
    _open(page, dashboard_fleet, stub)
    _open_dialog(page)
    btn = page.locator(".commit-block-approve")

    page.fill("#commit-block-reason", "x" * 501)
    assert page.input_value("#commit-block-reason") == "x" * 501      # not cut
    assert page.text_content(".commit-block-count") == "501 / 500 (too long)"
    assert btn.is_disabled()

    one_line = "Reviewed in the terminal: no charter edit needed."
    page.fill("#commit-block-reason", "  Reviewed in the terminal:\r\n\tno charter edit\nneeded.  ")
    assert page.text_content(".commit-block-count") == f"{len(one_line)} / 500"
    page.wait_for_function(
        "() => !document.querySelector('.commit-block-approve').disabled", timeout=5000)
    btn.click()
    page.wait_for_selector(".commit-block-success", timeout=5000)
    assert stub.posts[-1][1]["reason"] == one_line


def test_reason_textarea_resizes_vertically(page, dashboard_fleet):
    stub = Stub(page, [_status(findings=(EXT,))])
    _open(page, dashboard_fleet, stub)
    _open_dialog(page)
    style = page.evaluate("""() => { const t = document.querySelector('#commit-block-reason');
        const s = getComputedStyle(t); return {resize: s.resize, flex: s.flexGrow + ' ' + s.flexShrink,
        before: t.getBoundingClientRect().height}; }""")
    assert style["resize"] == "vertical" and style["flex"] == "0 0", style
    after = page.evaluate("""() => { const t = document.querySelector('#commit-block-reason');
        t.style.height = '220px'; return t.getBoundingClientRect().height; }""")
    assert abs(after - 220) < 2 and after > style["before"] + 50, (style, after)


@pytest.mark.parametrize("case", ["new-block", "same-id-new-rule", "post-refused"])
def test_changed_block_is_not_approved_unseen(page, dashboard_fleet, case):
    first = _status()
    if case == "new-block":
        fresh = _status(revision=REV2)
        fresh["block"]["block_id"] = "e5f6a7b8"
    else:
        fresh = _status(findings=(EXT, _finding("charter-index-gap", "external-approval")),
                        revision=REV2)
    if case == "post-refused":
        statuses = [first, first, fresh]
        post = lambda a, b: (409, {"ok": False, "refusal": "findings-changed",
                                   "message": "The findings changed.",
                                   "remaining": {"fix_required": [], "paused": []}})
    else:
        statuses = [first, fresh]
        post = None
    stub = Stub(page, statuses, post=post)
    _open(page, dashboard_fleet, stub)
    _open_dialog(page)
    page.fill("#commit-block-reason", "Reviewed.")
    page.click(".commit-block-approve")
    page.wait_for_selector(".commit-block-notice", timeout=5000)
    assert page.text_content(".commit-block-notice") == (
        "The blocked commit changed. Review it again before approving.")
    assert len(stub.posts) == (1 if case == "post-refused" else 0)
    assert page.input_value("#commit-block-reason") == "Reviewed."
    if case == "same-id-new-rule":
        assert page.locator('.commit-block-finding[data-rule="charter-index-gap"]').count() == 1


def test_in_flight_request_blocks_escape(page, dashboard_fleet):
    stub = Stub(page, [_status()], post=lambda a, b: "hold")
    _open(page, dashboard_fleet, stub)
    _open_dialog(page)
    page.fill("#commit-block-reason", "Reviewed.")
    page.click(".commit-block-approve")
    page.wait_for_function("() => document.querySelector('dialog.commit-block-dialog')"
                           ".dataset.sending === '1'", timeout=5000)
    for _ in range(50):
        if stub.held:
            break
        page.wait_for_timeout(100)
    assert stub.held, "the approve POST is in flight"
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    assert page.locator("dialog.commit-block-dialog[open]").count() == 1
    disabled = page.evaluate("""() => Array.from(document.querySelectorAll(
        'dialog.commit-block-dialog button')).every(b => b.disabled)""")
    assert disabled
    assert page.text_content(".commit-block-approve") == "Sending…"
    stub.held[0].fulfill(status=200, content_type="application/json", body=json.dumps(
        {"ok": True, "message": "ok", "remaining": {"fix_required": [], "paused": []}}))
    page.wait_for_selector(".commit-block-success", timeout=5000)


@pytest.mark.parametrize("case", ["unchanged", "changed", "refresh-fails", "malformed",
                                  "malformed-now-readable"])
def test_discard_requires_confirmation(page, dashboard_fleet, case):
    readable = _status()
    malformed = _status("malformed", findings=(), block=None, malformed=["block"],
                        revision=REV2)
    none = _status("none", findings=(), block=None, revision=None)
    statuses = {
        "unchanged": [readable, readable, none],
        "changed": [readable, _status(revision=REV2)],
        "refresh-fails": [readable, "fail"],
        "malformed": [malformed, malformed, none],
        "malformed-now-readable": [malformed, readable],
    }[case]
    stub = Stub(page, statuses, post=lambda a, b: (200, {
        "ok": True, "message": "Cancelled.", "removed": ["block.json"],
        "remaining": {"fix_required": [], "paused": []}}))
    _open(page, dashboard_fleet, stub)
    _open_dialog(page)
    page.click(".commit-block-discard")
    assert "Nothing is committed" in page.text_content(".commit-block-confirm")
    assert stub.posts == [], "no request before confirmation"
    page.click(".commit-block-discard-confirm")
    if case in ("unchanged", "malformed"):
        page.wait_for_selector(".commit-block-success", timeout=5000)
        assert stub.posts[0][0] == "cancel"
        expected_id = BLOCK if case == "unchanged" else None
        assert stub.posts[0][1] == {"block_id": expected_id,
                                    "revision": REV if case == "unchanged" else REV2}
        page.wait_for_function("() => !document.querySelector('.commit-block-alert')",
                               timeout=5000)
        return
    if case == "refresh-fails":
        page.wait_for_selector(".commit-block-error:not([hidden])", timeout=5000)
        assert "Nothing was sent" in page.text_content(".commit-block-error")
    else:
        page.wait_for_selector(".commit-block-notice", timeout=5000)
        assert page.text_content(".commit-block-notice") == (
            "The blocked commit changed. Review it, then confirm again.")
    assert stub.posts == []
    if case == "malformed-now-readable":
        assert page.locator('.commit-block-finding[data-rule="charter-alongside-code"]').count() == 1


@pytest.mark.parametrize("viewport", [(1440, 900), (375, 740)])
def test_block_dialog_layout(page, dashboard_fleet, viewport):
    page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
    stub = Stub(page, [_status(findings=(EXT, PAUSE, FIX))])
    _open(page, dashboard_fleet, stub)
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert overflow <= 0, overflow
    _open_dialog(page)
    box = page.evaluate("""() => {
        const r = document.querySelector('dialog.commit-block-dialog').getBoundingClientRect();
        return {left: r.left, right: innerWidth - r.right};
    }""")
    assert min(box.values()) >= 0, box
    assert abs(box["left"] - box["right"]) <= 1, box
    assert page.evaluate("() => document.querySelector('dialog.commit-block-dialog')"
                         ".matches(':modal')")


HISTORY_CASES = {
    "empty": (lambda r: r.fulfill(status=200, content_type="application/json",
                                  body=json.dumps({"repo": "alpha", "commits": []})),
              "No commits found."),
    "error-payload": (lambda r: r.fulfill(status=200, content_type="application/json",
                                          body=json.dumps({"error": "repo not accessible"})),
                      "repo not accessible"),
    "request-failed": (lambda r: r.abort(), "Error loading history"),
}


@pytest.mark.parametrize("case", list(HISTORY_CASES))
def test_alert_survives_empty_or_failed_history(page, dashboard_fleet, case):
    """Round 1 review: a repository can block its very first commit, and a
    history failure must not hide a recorded block."""
    history, message = HISTORY_CASES[case]
    stub = Stub(page, [_status()], history=history)
    page.goto(_origin(dashboard_fleet) + "?repo=alpha&view=history", wait_until="load")
    page.wait_for_selector(".commit-block-alert", timeout=15000)
    assert message in page.text_content("#view-slot")
    assert page.text_content(".commit-block-alert") == "⚑ Commit blocked"
    _open_dialog(page)
    page.fill("#commit-block-reason", "First commit; no charter yet.")
    page.click(".commit-block-approve")
    page.wait_for_selector(".commit-block-success", timeout=5000)
    assert stub.posts[0][0] == "approve"
    page.click(".commit-block-close")
    page.wait_for_selector("dialog.commit-block-dialog", state="detached", timeout=5000)
    assert stub.gets >= 2 and page.locator(".commit-row").count() == 0
