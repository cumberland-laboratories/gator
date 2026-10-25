"""Commits view (Paper) Playwright pins.

Each test proves a distinct risk:

- rows are collapsed by default and open by click or keyboard, grouped
  under local-day headings;
- the opened row shows the description without trailer lines, the Gator
  record (type, significance, charters, issues, tags, knowledge layer), and
  the override note only on an override commit;
- model-authored commit text renders as text: no element is created from
  a hostile subject or description;
- filter chips and search change the visible rows, and the chip counts are
  right;
- the stale-render guard (#56) still drops a late response;
- an older commit without Gator trailers renders cleanly from the real
  server;
- the view's change-type table covers the pre-commit producer's
  vocabulary (shared contract).
"""

import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCER = REPO_ROOT / "src/gator_command/templates/gator-starter/scripts/gator-pre-commit.py"


def _origin(fleet):
    return fleet["url"].rstrip("/") + "/"


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def _trailers(**kw):
    names = {
        "type": "Gator-Change-Type", "sig": "Gator-Significance",
        "changed": "Gator-Charter-Changed", "tags": "Gator-Decision-Tags",
        "issues": "Gator-Issues", "charters": "Gator-Charters",
        "functions": "Gator-Functions", "threads": "Gator-Threads",
        "by": "Gator-Override-Approved-By", "block": "Gator-Override-Block",
        "rules": "Gator-Override-Rules", "reason": "Gator-Override-Reason",
        "machine": "Gator-Machine-Id",
    }
    return [{"key": names[k], "value": v} for k, v in kw.items()]


def _commit(n, when, subject, description, trailers, agent="claude-opus-5-5",
            architect="Alan Gillette"):
    h = "abc%04d" % n + "f" * 33
    return {"hash": h, "short_hash": h[:7], "date": _iso(when), "author": "test",
            "subject": subject, "body": description, "description": description,
            "trailers": trailers, "agent": agent, "architect": architect}


HOSTILE = '<img src=x onerror="window.__pwned=1"><script>window.__pwned=2</script>'


def _fixture_commits():
    now = datetime.now().astimezone().replace(hour=12, minute=0, second=0, microsecond=0)
    return [
        _commit(1, now, "Dashboard: Paper shell",
                "- Paper tokens.\n- A light frame.",
                _trailers(type="feature", sig="notable", changed="yes",
                          tags="dashboard,paper", issues="80, #5",
                          charters="22", functions="301", threads="2",
                          machine="c5c707f5-machine")),
        _commit(2, now - timedelta(hours=1), "Fix: strip status",
                "Fixed the strip.",
                _trailers(type="fix", sig="routine", changed="override-skip",
                          tags="dashboard", by="Alan Gillette", block="332e9562",
                          rules="charter-index-gap", reason="routine")),
        _commit(3, now - timedelta(days=1), "Roadmap: released",
                "", _trailers(type="docs", sig="routine", changed="no", tags="roadmap")),
        _commit(4, now - timedelta(days=1, hours=2), HOSTILE,
                "Before " + HOSTILE + " after.\n\n- **bold** and `code`",
                _trailers(type="maintenance", sig="routine", tags="housekeeping,loop")),
        _commit(5, now - timedelta(days=3), "Bump to 2.27.0", "Version bump.",
                _trailers(type="release", sig="routine", tags="release")),
        _commit(6, now - timedelta(days=3, hours=1), "Old commit", "Plain body.", [],
                agent="", architect=""),
    ]


@pytest.fixture
def commits_page(page, dashboard_fleet):
    data = {"commits": _fixture_commits(), "repo": "alpha"}
    page.route("**/api/repo/alpha/history*",
               lambda route: route.fulfill(status=200, content_type="application/json",
                                           body=json.dumps(data)))
    page.goto(_origin(dashboard_fleet) + "?repo=alpha&view=history", wait_until="load")
    page.wait_for_selector(".commit-row", timeout=15000)
    return page


def _rows(page):
    return page.evaluate("""() => Array.from(document.querySelectorAll('.commit-row')).map(r => ({
        hash: r.dataset.hash.slice(0, 7), kind: r.dataset.kind, open: r.open,
        subject: r.querySelector('.commit-subject').textContent,
        label: r.querySelector('.commit-kind').textContent,
        flags: r.querySelector('.commit-flags').textContent,
    }))""")


def test_rows_collapsed_and_grouped_by_day(commits_page):
    page = commits_page
    rows = _rows(page)
    assert len(rows) == 6 and not any(r["open"] for r in rows)
    days = page.eval_on_selector_all(".commit-day", "els => els.map(e => e.textContent)")
    assert days[0].startswith("Today · ") and days[1].startswith("Yesterday · ")
    assert len(days) == 3
    assert [r["label"] for r in rows] == [
        "✦ Feature", "✚ Fix", "▤ Docs", "↺ Housekeeping", "⬆ Release", "• Commit"]
    assert "★ Notable" in rows[0]["flags"] and "⚑ Override" not in rows[0]["flags"]
    assert "⚑ Override" in rows[1]["flags"] and "★ Notable" not in rows[1]["flags"]
    meta = page.text_content('.commit-row[data-hash^="abc0001"] .commit-meta')
    assert "claude-opus-5-5 with Alan Gillette" in meta


def test_open_by_click_and_keyboard(commits_page):
    page = commits_page
    page.click(".commit-row >> nth=0 >> summary")
    assert _rows(page)[0]["open"] is True
    page.focus(".commit-row >> nth=1 >> summary")
    page.keyboard.press("Enter")
    assert _rows(page)[1]["open"] is True


def test_record_description_and_override(commits_page):
    page = commits_page
    page.click(".commit-row >> nth=0 >> summary")
    page.click(".commit-row >> nth=1 >> summary")
    rec = page.evaluate("""() => {
        const r = document.querySelectorAll('.commit-row');
        const one = (row) => ({
            desc: row.querySelector('.commit-desc').textContent,
            dl: Array.from(row.querySelectorAll('.commit-dl dt')).map(
                dt => dt.textContent + '=' + dt.nextElementSibling.textContent),
            chips: Array.from(row.querySelectorAll('.commit-chip-inline')).map(c => c.textContent),
            override: row.querySelector('.commit-override')
                && row.querySelector('.commit-override').textContent,
        });
        return [one(r[0]), one(r[1])];
    }""")
    first, second = rec
    assert first["desc"] == "Paper tokens.A light frame." and "Gator-" not in first["desc"]
    assert first["dl"] == ["Type=feature", "Significance=notable", "Charters=✓ Updated with the code",
                           "Charters=22", "Functions=301", "Threads=2"]
    assert first["chips"] == ["#80", "#5", "dashboard", "paper"]
    assert first["override"] is None
    assert "Charters=⚑ Skipped by approved override" in second["dl"]
    assert second["override"] == ("⚑ Override approved by Alan Gillette. Rule charter-index-gap "
                                  "blocked the commit; block 332e9562; reason: routine.")


def test_acknowledgement_note_is_distinct_from_override(page, dashboard_fleet):
    """#75: `Gator-Dangerous-Pattern-*` trailers render as an Architect
    acknowledgement (label and glyph), never as an override."""
    now = datetime.now().astimezone()
    trailers = [
        {"key": "Gator-Change-Type", "value": "feature"},
        {"key": "Gator-Charter-Changed", "value": "no"},
        {"key": "Gator-Dangerous-Patterns",
         "value": "SQL-001@migrate.txt:1,HYG-002@.env:0,SQL-001@one  space.txt:3"},
        {"key": "Gator-Dangerous-Pattern-Acknowledged-By", "value": "Alan Gillette"},
    ]
    data = {"commits": [_commit(1, now, "Keep fixture", "Kept.", trailers)], "repo": "alpha"}
    page.route("**/api/repo/alpha/history*",
               lambda route: route.fulfill(status=200, content_type="application/json",
                                           body=json.dumps(data)))
    page.goto(_origin(dashboard_fleet) + "?repo=alpha&view=history", wait_until="load")
    page.wait_for_selector(".commit-row", timeout=15000)
    flags = page.text_content(".commit-row .commit-flags")
    assert "✓ Acknowledged" in flags and "⚑ Override" not in flags
    page.click(".commit-row >> summary")
    out = page.evaluate("""() => ({
        ack: document.querySelector('.commit-acknowledgement')
            && document.querySelector('.commit-acknowledgement').textContent,
        override: document.querySelectorAll('.commit-override').length,
    })""")
    assert out["override"] == 0
    assert out["ack"] == ("✓ Architect acknowledgement by Alan Gillette. Kept on the "
                          "Architect's direction: SQL-001@migrate.txt:1, HYG-002@.env:0, "
                          "SQL-001@one  space.txt:3. "
                          "The decision is in the description.")


def test_unacknowledged_note_is_distinct(page, dashboard_fleet):
    """#75: a recorded skip renders as "! Unacknowledged", never as an
    acknowledgement or an override."""
    now = datetime.now().astimezone()
    trailers = [
        {"key": "Gator-Change-Type", "value": "feature"},
        {"key": "Gator-Dangerous-Patterns-Unacknowledged", "value": "SQL-001@one  space.txt:1"},
    ]
    data = {"commits": [_commit(1, now, "Skip", "Skipped.", trailers)], "repo": "alpha"}
    page.route("**/api/repo/alpha/history*",
               lambda route: route.fulfill(status=200, content_type="application/json",
                                           body=json.dumps(data)))
    page.goto(_origin(dashboard_fleet) + "?repo=alpha&view=history", wait_until="load")
    page.wait_for_selector(".commit-row", timeout=15000)
    flags = page.text_content(".commit-row .commit-flags")
    assert "! Unacknowledged" in flags
    assert "✓ Acknowledged" not in flags and "⚑ Override" not in flags
    page.click(".commit-row >> summary")
    out = page.evaluate("""() => ({
        note: document.querySelector('.commit-unacknowledged').textContent,
        ack: document.querySelectorAll('.commit-acknowledgement').length,
        override: document.querySelectorAll('.commit-override').length,
    })""")
    assert out == {"note": "! Unacknowledged dangerous pattern. Committed without an "
                           "Architect decision: SQL-001@one  space.txt:1.",
                   "ack": 0, "override": 0}


def test_hostile_commit_text_renders_as_text(commits_page):
    page = commits_page
    page.click(".commit-row >> nth=3 >> summary")
    out = page.evaluate("""() => {
        const row = document.querySelectorAll('.commit-row')[3];
        return {
            subject: row.querySelector('.commit-subject').textContent,
            injected: row.querySelectorAll('img, script, iframe').length,
            desc: row.querySelector('.commit-desc').textContent,
            strong: row.querySelectorAll('.commit-desc strong').length,
            code: row.querySelectorAll('.commit-desc code').length,
            pwned: window.__pwned || 0,
        };
    }""")
    assert out["subject"] == HOSTILE
    assert out["injected"] == 0 and out["pwned"] == 0
    assert HOSTILE in out["desc"]
    assert out["strong"] == 1 and out["code"] == 1  # the closed grammar still formats


def test_filters_and_search(commits_page):
    page = commits_page
    counts = page.evaluate("""() => Array.from(document.querySelectorAll('.commit-filter')).map(
        b => [b.dataset.filter, b.querySelector('.commit-filter-count').textContent,
              b.getAttribute('aria-pressed')])""")
    assert counts == [["all", "6", "true"], ["feature", "1", "false"], ["fix", "1", "false"],
                      ["docs", "1", "false"], ["housekeeping", "1", "false"],
                      ["release", "1", "false"]]
    page.click('.commit-filter[data-filter="fix"]')
    assert [r["subject"] for r in _rows(page)] == ["Fix: strip status"]
    assert page.get_attribute('.commit-filter[data-filter="fix"]', "aria-pressed") == "true"
    page.click('.commit-filter[data-filter="all"]')
    page.fill(".commit-search", "PAPER")          # subject and tag, case-insensitive
    assert [r["subject"] for r in _rows(page)] == ["Dashboard: Paper shell"]
    page.fill(".commit-search", "abc0005")        # hash
    assert [r["subject"] for r in _rows(page)] == ["Bump to 2.27.0"]
    page.fill(".commit-search", "loop")           # decision tag
    assert [r["subject"] for r in _rows(page)] == [HOSTILE]
    page.fill(".commit-search", "no such commit")
    assert _rows(page) == [] and page.text_content(".commit-empty") == "No commits match."


def test_open_rows_survive_refilter_and_raw_trailers(commits_page):
    page = commits_page
    page.click(".commit-row >> nth=0 >> summary")
    page.click('.commit-filter[data-filter="feature"]')
    page.click('.commit-filter[data-filter="all"]')
    assert _rows(page)[0]["open"] is True
    raw = page.locator(".commit-row >> nth=0 >> .commit-raw")
    assert raw.is_hidden()
    page.click(".commit-row >> nth=0 >> .commit-raw-toggle")
    assert raw.is_visible()
    assert raw.text_content().splitlines()[0] == "Gator-Change-Type: feature"
    # Machine identity appears in Raw trailers only, never in the record.
    assert "Gator-Machine-Id: c5c707f5-machine" in raw.text_content()
    record = page.text_content(".commit-row >> nth=0 >> .commit-record")
    assert "c5c707f5" not in record and "Machine" not in record


def test_stale_response_is_dropped(page, dashboard_fleet):
    held = []
    page.route("**/api/repo/alpha/history*", lambda route: held.append(route))
    page.goto(_origin(dashboard_fleet) + "?repo=alpha&view=history", wait_until="load")
    page.wait_for_function("() => document.getElementById('view-slot').textContent"
                           ".includes('Loading history')", timeout=15000)
    page.evaluate("() => document.querySelector('.sidebar-item[data-view=\"docs\"]').click()")
    page.wait_for_selector(".docs-sidebar", timeout=10000)
    data = {"commits": _fixture_commits(), "repo": "alpha"}
    for route in held:
        route.fulfill(status=200, content_type="application/json", body=json.dumps(data))
    page.wait_for_timeout(500)
    assert page.locator(".commits-view").count() == 0
    assert page.locator(".docs-sidebar").count() == 1


def test_real_commit_without_trailers_renders_cleanly(page, dashboard_fleet):
    """The seeded repository's commits have no Gator trailers."""
    page.goto(_origin(dashboard_fleet) + "?repo=alpha&view=history", wait_until="load")
    page.wait_for_selector(".commit-row", timeout=15000)
    page.click(".commit-row >> nth=0 >> summary")
    text = page.text_content(".commit-row >> nth=0")
    assert "undefined" not in text and "null" not in text
    assert page.text_content(".commit-row >> nth=0 >> .commit-kind") == "• Commit"
    assert page.locator(".commit-row >> nth=0 >> .commit-raw-toggle").count() == 0


def test_change_types_cover_the_producer_vocabulary(page, dashboard_fleet):
    tree = ast.parse(PRODUCER.read_text(encoding="utf-8"))
    producer = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == "VALID_CHANGE_TYPES" for t in node.targets):
            producer = {e.value for e in node.value.args[0].elts}
    assert producer, "VALID_CHANGE_TYPES not found in the pre-commit producer"
    page.goto(_origin(dashboard_fleet) + "?view=fleet", wait_until="load")
    page.wait_for_function("() => window.GatorViews && window.GatorViews.history", timeout=10000)
    view = set(page.evaluate("() => window.GatorViews.history.changeTypes"))
    assert view == producer - {""}
