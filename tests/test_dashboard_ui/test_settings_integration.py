"""Settings → Connected AI tools (machine-level vendor integration, CP3).

`/api/integration` and the dismiss POST are stubbed with `page.route`, so
the test never reads or writes the real machine's AI-tool settings. The
route tests in `tests/test_dashboard_integration.py` cover the server.
"""

import json


def _report(codex_due, codex_connected=True):
    def vendor(display, present, connected, problem=None):
        return {"display": display, "present": present, "connected": connected,
                "config_path": f"/home/u/{display}.json", "problem": problem,
                "connected_at": None}
    return {
        "state": "ok",
        "state_path": "/home/u/.gator/vendor-integration.json",
        "vendors": {
            "claude": vendor("Claude Code", True, True),
            "codex": vendor("Codex", True, codex_connected),
            "gemini": vendor("Gemini CLI", True, False, problem="malformed"),
        },
        "codex_reminder_due": codex_due,
    }


def _rows(page):
    return page.evaluate("""() => Object.fromEntries(Array.from(
        document.querySelectorAll('.settings-integration-table tbody tr'))
        .map(tr => [tr.dataset.vendor,
                    tr.querySelector('.settings-integration-state').textContent.trim()]))""")


def test_connected_tools_and_codex_reminder(page, dashboard_fleet):
    posts = []
    page.route("**/api/integration", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps(_report(codex_due=True))))

    def dismiss(route):
        posts.append(route.request.headers.get("x-gator-dashboard"))
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(_report(codex_due=False)))
    page.route("**/api/integration/dismiss-codex-reminder", dismiss)

    page.goto(dashboard_fleet["url"].rstrip("/") + "/?view=settings", wait_until="load")
    page.wait_for_selector(".settings-integration-table", timeout=15000)

    # Every state is a word, never colour alone.
    assert _rows(page) == {
        "Claude Code": "Connected",
        "Codex": "Connected",
        "Gemini CLI": "Problem: Gator could not read this settings file",
    }
    reminder = page.locator(".settings-integration-reminder")
    assert "/hooks" in reminder.inner_text()

    page.click(".settings-integration-done")
    page.wait_for_selector(".settings-integration-reminder", state="detached",
                           timeout=15000)
    assert posts == ["1"]
    # The commit-policy section is untouched.
    assert page.locator(".settings-policy-table").count() == 1


def test_unreachable_status_still_renders_settings(page, dashboard_fleet):
    page.route("**/api/integration", lambda route: route.fulfill(
        status=500, content_type="application/json", body="not json"))
    page.goto(dashboard_fleet["url"].rstrip("/") + "/?view=settings", wait_until="load")
    page.wait_for_selector(".settings-repo-table", timeout=15000)
    page.wait_for_function(
        "() => !document.querySelector('.settings-integration').textContent.includes('Loading')",
        timeout=15000)
    text = page.locator(".settings-integration").inner_text()
    assert "could not read" in text
