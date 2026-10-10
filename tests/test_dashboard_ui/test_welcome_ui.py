"""Welcome workspace Playwright pins (#72).

The Gator logo opens a repository-independent Welcome view with four
ARIA topics in the shared main-pane tab bar and one transient copy of
the vendor-neutral session-opening prompt.

Each test proves a distinct risk:

- routing from Fleet / Repo / Loop without touching repository context
  or making any request;
- the ARIA tab contract, keyboard, selected-state styling and the
  full-width bar;
- the exact prompt on a successful copy, kept out of history and storage;
- the honest fallback when the Clipboard API is missing or rejects;
- the narrow-width layout;
- shell-owned Back/Forward, and the default topic on a fresh load.
"""

from pathlib import Path

import pytest


# One line by Architect direction (2026-10-10): a pasted newline can
# submit early in terminal agent UIs.
SESSION_PROMPT = (
    "Run gator init in this repository. Treat its output, including the required "
    "session-opening reads, as binding. Do not provide a substantive response until "
    "those reads are complete."
)

TOPICS = ["how", "can", "gatorize", "session"]

DOC_API = "/api/welcome/how-gator-works"
SHIPPED_DOC = (Path(__file__).resolve().parents[2] / "src" / "gator_command"
               / "templates" / "gator-starter" / "docs" / "how-gator-works.md")


def _origin(fleet):
    return fleet["url"].rstrip("/") + "/"


def _open_welcome(page):
    page.evaluate("() => document.getElementById('brand-home').click()")
    page.wait_for_selector(".welcome-workspace", timeout=10000)


def _goto_fleet(page, fleet):
    page.goto(_origin(fleet), wait_until="load")
    page.wait_for_selector("#view-slot .fleet-table, #view-slot table", timeout=15000)


def _tabs(page):
    return page.evaluate("""() => {
        const out = {};
        document.querySelectorAll('.welcome-tablist [role="tab"]').forEach(t => {
            const panel = document.getElementById(t.getAttribute('aria-controls'));
            out[t.dataset.topic] = {
                selected: t.getAttribute('aria-selected'),
                tabindex: t.getAttribute('tabindex'),
                panelRole: panel ? panel.getAttribute('role') : null,
                panelLabelledBy: panel ? panel.getAttribute('aria-labelledby') : null,
                panelHidden: panel ? panel.hidden : null,
                id: t.id,
            };
        });
        return out;
    }""")


def _selected(page):
    return [k for k, v in _tabs(page).items() if v["selected"] == "true"]


def _repo_context(page):
    return page.evaluate("""() => ({
        label: document.getElementById('repo-tab').textContent.trim(),
        repo: document.getElementById('repo-tab').classList.contains('dimmed'),
        docs: document.getElementById('docs-tab').classList.contains('dimmed'),
        loop: document.getElementById('loop-tab').classList.contains('dimmed'),
    })""")


@pytest.mark.parametrize("start", ["fleet", "repo", "loop"])
def test_logo_opens_welcome_without_repo_mutation(page, dashboard_fleet, start):
    """Verification 1, 2 (default topic) and 5: the logo opens Welcome from
    any view; repository context is untouched, and the only request is
    the one fixed How-Gator-works document fetch."""
    origin = _origin(dashboard_fleet)
    if start == "fleet":
        _goto_fleet(page, dashboard_fleet)
    else:
        page.goto(origin + "?repo=alpha", wait_until="load")
        page.wait_for_selector(".repo-file-item", timeout=15000)
        if start == "loop":
            page.evaluate(
                "() => document.querySelector('.sidebar-item[data-view=\"loop\"]').click()")
            page.wait_for_selector(".loop-status-header", timeout=10000)
    before = _repo_context(page)

    # Capture from the logo click itself (setup requests excluded).
    requests = []
    page.on("request", lambda r: requests.append((r.method, r.url)))
    _open_welcome(page)
    assert page.text_content("#topbar-title") == "Welcome to Gator!"
    assert page.get_attribute("#brand-home", "aria-current") == "page"
    assert _selected(page) == ["how"]

    for topic in TOPICS:
        page.click("#welcome-tab-" + topic)
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    page.click(".welcome-copy")
    page.wait_for_selector(".welcome-copy-status:has-text('copied')", timeout=5000)

    assert _repo_context(page) == before
    # The only request is the one fixed document fetch (first open).
    api = [u for _, u in requests if "/api/" in u]
    assert len(api) == 1 and api[0].endswith(DOC_API)
    assert all(m == "GET" for m, _ in requests)


def test_welcome_tabs_aria_and_keyboard(page, dashboard_fleet):
    """Verification 2 and 3: tab roles and relationships, roving tabindex,
    click and Left/Right/Home/End; selection is weight plus underline; the
    bar spans the main pane's content width."""
    _goto_fleet(page, dashboard_fleet)
    _open_welcome(page)
    tabs = _tabs(page)
    assert list(tabs) == TOPICS
    for key, t in tabs.items():
        assert t["panelRole"] == "tabpanel"
        assert t["panelLabelledBy"] == t["id"]
        selected = key == "how"
        assert t["selected"] == ("true" if selected else "false")
        assert t["tabindex"] == ("0" if selected else "-1")
        assert t["panelHidden"] is (not selected)

    page.click("#welcome-tab-gatorize")
    assert _selected(page) == ["gatorize"]
    page.keyboard.press("ArrowRight")
    assert _selected(page) == ["session"]
    assert page.evaluate("() => document.activeElement.id") == "welcome-tab-session"
    page.keyboard.press("ArrowRight")  # wraps
    assert _selected(page) == ["how"]
    page.keyboard.press("ArrowLeft")  # wraps back
    assert _selected(page) == ["session"]
    page.keyboard.press("Home")
    assert page.evaluate("() => document.activeElement.id") == "welcome-tab-how"
    page.keyboard.press("End")
    assert page.evaluate("() => document.activeElement.id") == "welcome-tab-session"
    tabs = _tabs(page)
    assert [k for k, t in tabs.items() if not t["panelHidden"]] == ["session"]
    assert [k for k, t in tabs.items() if t["tabindex"] == "0"] == ["session"]

    geo = page.evaluate("""() => {
        const cs = s => getComputedStyle(document.querySelector(s));
        const bar = document.querySelector('.welcome-tabbar').getBoundingClientRect();
        const slot = document.getElementById('view-slot').getBoundingClientRect();
        const pad = cs('#view-slot');
        return {
            barLeft: bar.left, barRight: bar.right,
            contentLeft: slot.left + parseFloat(pad.paddingLeft),
            contentRight: slot.right - parseFloat(pad.paddingRight),
            baseline: cs('.welcome-tabbar').borderBottomWidth,
            selWeight: parseInt(cs('#welcome-tab-session').fontWeight, 10),
            selBorder: cs('#welcome-tab-session').borderBottomWidth,
            unWeight: parseInt(cs('#welcome-tab-how').fontWeight, 10),
            unBorderColor: cs('#welcome-tab-how').borderBottomColor,
        };
    }""")
    assert abs(geo["barLeft"] - geo["contentLeft"]) <= 1
    assert abs(geo["barRight"] - geo["contentRight"]) <= 1
    assert geo["baseline"] == "1px"
    assert geo["selWeight"] >= 700 and geo["selBorder"] == "3px"
    assert geo["unWeight"] == 400
    assert geo["unBorderColor"] in ("rgba(0, 0, 0, 0)", "transparent")


def test_welcome_copy_success(page, dashboard_fleet):
    """Verification 4 and 6: the exact prompt is copied, confirmed visibly
    and politely, and kept out of history and storage."""
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    _goto_fleet(page, dashboard_fleet)
    _open_welcome(page)
    page.click("#welcome-tab-session")
    assert page.text_content(".welcome-prompt") == SESSION_PROMPT
    page.click(".welcome-copy")
    page.wait_for_function(
        "() => document.querySelector('.welcome-copy').textContent === 'Copied'",
        timeout=5000)
    copied = page.evaluate("() => navigator.clipboard.readText()")
    assert copied == SESSION_PROMPT
    assert "\n" not in copied and "\r" not in copied
    status = page.locator(".welcome-copy-status")
    assert status.get_attribute("role") == "status"
    assert status.get_attribute("aria-live") == "polite"
    assert status.text_content() == "Session-opening prompt copied."
    leaked = page.evaluate("""(needle) => {
        const hay = [JSON.stringify(history.state)];
        for (const st of [localStorage, sessionStorage]) {
            for (let i = 0; i < st.length; i++) hay.push(st.getItem(st.key(i)));
        }
        return hay.some(h => h && h.indexOf(needle) !== -1);
    }""", "Run gator init")
    assert leaked is False
    page.wait_for_function(
        "() => document.querySelector('.welcome-copy').textContent"
        " === 'Copy session-opening prompt'", timeout=5000)


@pytest.mark.parametrize("mode", ["missing", "rejects"])
def test_welcome_copy_fallback(page, dashboard_fleet, mode):
    """An unavailable or failing Clipboard API never fails silently: the
    Loop-pattern fallback holds the exact prompt, selected, and Dismiss
    removes it."""
    if mode == "missing":
        page.add_init_script(
            "Object.defineProperty(navigator, 'clipboard',"
            " {value: undefined, configurable: true});")
    else:
        page.add_init_script(
            "Object.defineProperty(navigator, 'clipboard', {configurable: true,"
            " value: {writeText: () => Promise.reject(new Error('denied'))}});")
    _goto_fleet(page, dashboard_fleet)
    _open_welcome(page)
    page.click("#welcome-tab-session")
    page.click(".welcome-copy")
    page.wait_for_selector(".welcome-copy-fallback", timeout=5000)
    fb = page.evaluate("""() => {
        const ta = document.querySelector('.welcome-copy-fallback-text');
        return {
            value: ta.value, readOnly: ta.readOnly,
            selected: ta.selectionStart === 0 && ta.selectionEnd === ta.value.length,
            hint: document.querySelector('.welcome-copy-fallback-hint').textContent,
            status: document.querySelector('.welcome-copy-status').textContent,
            button: document.querySelector('.welcome-copy').textContent,
        };
    }""")
    assert fb["value"] == SESSION_PROMPT
    assert fb["readOnly"] is True and fb["selected"] is True
    assert fb["hint"] == "Select all and copy manually."
    assert fb["status"] == "Clipboard unavailable — copy the prompt manually."
    assert fb["button"] == "Copy session-opening prompt"
    page.click(".welcome-copy-fallback-dismiss")
    assert page.locator(".welcome-copy-fallback").count() == 0


def test_welcome_narrow_width(page, dashboard_fleet):
    """At ~400px every topic label stays readable and unclipped: the bar
    wraps instead of shrinking or cutting off the session tab."""
    _goto_fleet(page, dashboard_fleet)
    _open_welcome(page)
    desktop_size = page.evaluate(
        "() => getComputedStyle(document.getElementById('welcome-tab-session')).fontSize")
    page.set_viewport_size({"width": 400, "height": 800})
    rects = page.evaluate("""() => Array.from(
        document.querySelectorAll('.welcome-tablist [role="tab"]')).map(t => {
            const r = t.getBoundingClientRect();
            return {left: r.left, right: r.right, width: r.width,
                    scroll: t.scrollWidth, client: t.clientWidth,
                    size: getComputedStyle(t).fontSize};
        })""")
    width = page.evaluate("() => document.documentElement.clientWidth")
    assert len(rects) == 4
    for r in rects:
        assert r["left"] >= 0 and r["right"] <= width + 0.5
        assert r["scroll"] <= r["client"] + 1  # label not clipped
        assert r["size"] == desktop_size


def test_welcome_back_forward_and_topic_reset(page, dashboard_fleet):
    """Back/Forward stay shell-owned and keep the topic while the page is
    loaded; a fresh load starts on How Gator works."""
    _goto_fleet(page, dashboard_fleet)
    length = page.evaluate("() => history.length")
    _open_welcome(page)
    assert page.evaluate("() => history.length") == length + 1
    assert page.evaluate("() => history.state && history.state.view") == "welcome"
    assert page.evaluate("() => history.state.sub") is None
    page.click("#welcome-tab-gatorize")
    assert page.evaluate("() => history.length") == length + 1  # topics push nothing

    page.evaluate("() => history.back()")
    page.wait_for_function(
        "() => document.getElementById('topbar-title').textContent === 'Fleet'",
        timeout=5000)
    assert page.get_attribute("#brand-home", "aria-current") is None
    page.evaluate("() => history.forward()")
    page.wait_for_selector(".welcome-workspace", timeout=5000)
    assert _selected(page) == ["gatorize"]

    page.reload(wait_until="load")
    page.wait_for_selector("#view-slot table", timeout=15000)
    _open_welcome(page)
    assert _selected(page) == ["how"]


def _doc_ready(page):
    page.wait_for_function(
        "() => { const d = document.querySelector('.welcome-doc');"
        "  return d && !d.querySelector('.welcome-doc-status'); }", timeout=10000)


def test_how_gator_works_renders_shipped_doc_once(page, dashboard_fleet):
    """The first topic renders the shipped how-gator-works.md through the
    closed Markdown formatter, and the document is fetched once per page
    load (reopening Welcome uses the cache)."""
    shipped = SHIPPED_DOC.read_text(encoding="utf-8")
    requests = []
    page.on("request", lambda r: requests.append(r.url))
    _goto_fleet(page, dashboard_fleet)
    _open_welcome(page)
    _doc_ready(page)
    out = page.evaluate("""() => {
        const d = document.querySelector('.welcome-doc');
        return {
            h3: d.querySelector('h3') && d.querySelector('h3').textContent,
            h4: Array.from(d.querySelectorAll('h4')).map(h => h.textContent),
            text: d.textContent,
            scripts: d.querySelectorAll('script, img, iframe').length,
        };
    }""")
    assert out["h3"] == "How Gator Works"
    assert "The Short Version" in out["h4"] and "The Charters" in out["h4"]
    last = [l for l in shipped.splitlines() if l.strip()][-1]
    assert last[:60] in out["text"]
    assert out["scripts"] == 0

    page.evaluate("() => document.querySelector('.sidebar-item[data-view=\"fleet\"]').click()")
    _open_welcome(page)
    _doc_ready(page)
    assert sum(1 for u in requests if u.endswith(DOC_API)) == 1


def test_how_gator_works_unavailable_is_explained(page, dashboard_fleet):
    """A failed document fetch shows a text notice naming the in-repo copy,
    never an empty panel."""
    page.route("**" + DOC_API, lambda route: route.fulfill(
        status=404, content_type="application/json",
        body='{"error": "x", "code": 404}'))
    _goto_fleet(page, dashboard_fleet)
    _open_welcome(page)
    page.wait_for_selector(".welcome-doc .welcome-doc-status:has-text('Could not load')",
                           timeout=10000)
    assert ".gator/docs/how-gator-works.md" in page.text_content(".welcome-doc")


def test_how_gator_works_endpoint_is_fixed(page, dashboard_fleet):
    """The endpoint serves exactly the shipped file and ignores any request
    input; nothing else is reachable through it."""
    base = _origin(dashboard_fleet).rstrip("/")
    shipped = SHIPPED_DOC.read_text(encoding="utf-8")
    for suffix in ["", "?path=../../README.md", "?repo=alpha"]:
        r = page.request.get(base + DOC_API + suffix)
        assert r.status == 200
        assert r.json() == {"text": shipped}
    assert page.request.get(base + DOC_API + "/../README.md").status == 404

