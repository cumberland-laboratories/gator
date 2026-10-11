"""Welcome workspace Playwright pins (#72; Welcome HTML documents).

The Gator logo opens a repository-independent Welcome view with four
ARIA topics in the shared main-pane tab bar. Each topic body is a shipped
standalone HTML document in an iframe sandboxed exactly "allow-scripts".

Each test proves a distinct risk:

- routing from Fleet / Repo / Loop without touching repository context,
  with only the four allowlisted document GETs as requests;
- the ARIA tab contract, keyboard, selected-state styling and the
  full-width bar;
- frames that are lazy, persistent (no reload on revisit) and exactly
  sandboxed, with no document markup in the Dashboard DOM;
- the closed four-name route: exact headers and bodies, everything else
  404;
- snapshot frames: srcdoc, the same sandbox, the injected CSP meta;
- the narrow-width layout;
- shell-owned Back/Forward, and the default topic on a fresh load.
"""

import sys
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
LABELS = {
    "how": "How Gator works",
    "can": "What Gator can do",
    "gatorize": "Gatorize a repo",
    "session": "Start a session with Gator",
}
DOC_NAMES = {
    "how": "how-gator-works.html",
    "can": "what-gator-can-do.html",
    "gatorize": "gatorize-a-repo.html",
    "session": "start-a-session.html",
}
DOC_ROUTE = "/api/welcome/docs/"

_SRC = Path(__file__).resolve().parents[2] / "src" / "gator_command"
DOCS_DIR = _SRC / "templates" / "gator-starter" / "docs"
_SCRIPTS = _SRC / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from dashboard.content_policy import HTML_CSP_DIRECTIVES  # noqa: E402

EXPECTED_CSP = "sandbox allow-scripts; " + HTML_CSP_DIRECTIVES


def _doc_requests(urls):
    """Welcome document names requested, in order."""
    return [u.split(DOC_ROUTE, 1)[1] for u in urls if DOC_ROUTE in u]



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
    """The logo opens Welcome from any view; repository context is
    untouched, and visiting every topic requests only the four allowlisted
    documents, once each, all GET."""
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
    page.wait_for_function(
        "() => document.querySelectorAll('iframe.welcome-frame').length === 4",
        timeout=5000)
    page.wait_for_load_state("load")

    assert _repo_context(page) == before
    api = [u for _, u in requests if "/api/" in u]
    assert sorted(_doc_requests(api)) == sorted(DOC_NAMES.values())
    assert len(api) == 4
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


def _frames(page):
    return page.evaluate("""() => Array.from(
        document.querySelectorAll('.welcome-panel')).map(p => {
            const f = p.querySelector('iframe');
            return {
                panel: p.id,
                count: p.querySelectorAll('iframe').length,
                children: p.children.length,
                sandbox: f && f.getAttribute('sandbox'),
                title: f && f.title,
                src: f && f.getAttribute('src'),
                srcdoc: f ? f.hasAttribute('srcdoc') : null,
            };
        })""")


def test_welcome_frames_lazy_persistent_sandboxed(page, dashboard_fleet):
    """Opening Welcome creates and loads only the selected topic's frame.
    Each topic's first selection adds exactly one frame, sandboxed exactly
    "allow-scripts", titled with the tab label. A revisit neither reloads
    nor re-requests it, and no document markup enters the Dashboard DOM."""
    _goto_fleet(page, dashboard_fleet)
    requests = []
    page.on("request", lambda r: requests.append(r.url))
    _open_welcome(page)
    page.wait_for_function(
        "() => document.querySelector('#welcome-panel-how iframe')", timeout=5000)
    frames = {f["panel"]: f for f in _frames(page)}
    assert frames["welcome-panel-how"]["count"] == 1
    assert all(frames["welcome-panel-" + k]["count"] == 0
               for k in ("can", "gatorize", "session"))

    for key in TOPICS:
        page.click("#welcome-tab-" + key)
    page.wait_for_load_state("load")
    for f in _frames(page):
        key = f["panel"].replace("welcome-panel-", "")
        assert f["count"] == 1 and f["children"] == 1
        assert f["sandbox"] == "allow-scripts"
        assert f["title"] == LABELS[key]
        assert f["src"] == DOC_ROUTE + DOC_NAMES[key]
        assert f["srcdoc"] is False

    # A marker set inside a frame survives switching away and back.
    how = next(fr for fr in page.frames if fr.url.endswith(DOC_NAMES["how"]))
    how.evaluate("() => { window.__welcomeMarker = 'kept'; }")
    page.click("#welcome-tab-can")
    page.click("#welcome-tab-how")
    assert how.evaluate("() => window.__welcomeMarker") == "kept"
    assert how.evaluate("() => document.title") == LABELS["how"]
    assert sorted(_doc_requests(requests)) == sorted(DOC_NAMES.values())

    leaked = page.evaluate("""() => document.querySelector('.welcome-workspace')
        .querySelectorAll('.doc-head, .meta-grid, #session-prompt').length""")
    assert leaked == 0

    # The selected frame spans the full main-pane width, like the tab bar.
    geo = page.evaluate("""() => {
        const bar = document.querySelector('.welcome-tabbar').getBoundingClientRect();
        const f = document.querySelector('#welcome-panel-how iframe').getBoundingClientRect();
        return {barLeft: bar.left, barRight: bar.right, left: f.left, right: f.right};
    }""")
    assert abs(geo["left"] - geo["barLeft"]) <= 1
    assert abs(geo["right"] - geo["barRight"]) <= 1


@pytest.mark.parametrize("key", TOPICS)
def test_welcome_route_serves_the_four(page, dashboard_fleet, key):
    """Each allowlisted name returns its shipped document as HTML with the
    fixed sandboxing CSP and nosniff; a query string selects nothing."""
    base = _origin(dashboard_fleet).rstrip("/")
    name = DOC_NAMES[key]
    shipped = (DOCS_DIR / name).read_text(encoding="utf-8").encode("utf-8")
    for suffix in ("", "?name=../../README.md"):
        r = page.request.get(base + DOC_ROUTE + name + suffix)
        assert r.status == 200
        assert r.headers["content-type"] == "text/html; charset=utf-8"
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["content-security-policy"] == EXPECTED_CSP
        assert r.body() == shipped


@pytest.mark.parametrize("path", [
    DOC_ROUTE + "unknown.html",
    DOC_ROUTE + "how-gator-works.md",
    DOC_ROUTE + "How-Gator-Works.html",
    DOC_ROUTE + "..%2fREADME.md",
    DOC_ROUTE + "%2e%2e/README.md",
    DOC_ROUTE + "how-gator-works.html/extra",
    DOC_ROUTE + "how-gator-works.html%00",
    DOC_ROUTE,
    "/api/welcome/how-gator-works",
])
def test_welcome_route_rejects_everything_else(page, dashboard_fleet, path):
    """Anything but an exact allowlisted name is a 404 that carries no
    shipped document. An encoded separator is already refused with 400 by
    the shared request parser, before any route runs."""
    base = _origin(dashboard_fleet).rstrip("/")
    r = page.request.get(base + path)
    assert r.status == (400 if "%2f" in path.lower() else 404)
    assert b"CUMBERLAND-NARRATIVE-STYLE" not in r.body()


def test_welcome_snapshot_frames(page, tmp_path):
    """In an offline snapshot, each topic frame gets its document through
    srcdoc, with the same exact sandbox and the injected CSP meta."""
    from dashboard.content_policy import html_csp_meta_policy
    from dashboard.snapshot import build_snapshot
    out = tmp_path / "snapshot.html"
    out.write_text(build_snapshot({
        "generated_at": "2026-10-10T00:00:00Z",
        "fleet": {"summary": {"total": 0, "accessible": 0}},
        "repos": [],
    }), encoding="utf-8")
    page.goto(out.as_uri(), wait_until="load")
    _open_welcome(page)
    page.click("#welcome-tab-session")
    page.wait_for_function(
        "() => document.querySelector('#welcome-panel-session iframe')", timeout=5000)
    f = page.evaluate("""() => {
        const f = document.querySelector('#welcome-panel-session iframe');
        return {sandbox: f.getAttribute('sandbox'), src: f.getAttribute('src'),
                srcdoc: f.srcdoc, title: f.title};
    }""")
    assert f["sandbox"] == "allow-scripts" and f["src"] is None
    assert f["title"] == LABELS["session"]
    assert ('<meta http-equiv="Content-Security-Policy" content="'
            + html_csp_meta_policy() + '">') in f["srcdoc"]
    frame = next(fr for fr in page.frames if fr.url == "about:srcdoc"
                 and fr.evaluate("() => document.title") == LABELS["session"])
    assert frame.evaluate(
        "() => document.getElementById('session-prompt').textContent") == SESSION_PROMPT


# ── Copy action (checkpoint 2) ────────────────────────────────────────────

COPY_REQUEST = {"type": "gator-welcome", "v": 1, "action": "copy-session-prompt"}


def _open_session_frame(page, fleet):
    """Open Welcome on the Start-a-session topic; return its live frame."""
    _goto_fleet(page, fleet)
    _open_welcome(page)
    page.click("#welcome-tab-session")
    page.wait_for_function(
        "() => document.querySelector('#welcome-panel-session iframe')", timeout=5000)
    page.wait_for_load_state("load")
    frame = _frame_for(page, "#welcome-panel-session iframe")
    frame.wait_for_selector("#copy-session-prompt", timeout=5000)
    return frame


def _frame_for(page, selector):
    """The Playwright frame whose <iframe> element matches `selector`."""
    return page.locator(selector).element_handle().content_frame()


def _frame_state(frame):
    return frame.evaluate("""() => ({
        status: document.getElementById('copy-status').textContent,
        role: document.getElementById('copy-status').getAttribute('role'),
        live: document.getElementById('copy-status').getAttribute('aria-live'),
        manual: !document.getElementById('copy-manual').hidden,
        selection: String(window.getSelection()),
    })""")


def test_welcome_copy_success(page, dashboard_fleet):
    """Keyboard activation of the in-document button copies exactly the
    Dashboard's one-line prompt; the document announces "Copied" politely;
    the prompt stays out of history and storage."""
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    frame = _open_session_frame(page, dashboard_fleet)
    frame.focus("#copy-session-prompt")
    page.keyboard.press("Enter")
    frame.wait_for_function(
        "() => document.getElementById('copy-status').textContent === 'Copied'",
        timeout=5000)
    state = _frame_state(frame)
    assert state["role"] == "status" and state["live"] == "polite"
    assert state["manual"] is False
    copied = page.evaluate("() => navigator.clipboard.readText()")
    assert copied == SESSION_PROMPT
    assert "\n" not in copied and "\r" not in copied
    leaked = page.evaluate("""(needle) => {
        const hay = [JSON.stringify(history.state)];
        for (const st of [localStorage, sessionStorage]) {
            for (let i = 0; i < st.length; i++) hay.push(st.getItem(st.key(i)));
        }
        return hay.some(h => h && h.indexOf(needle) !== -1);
    }""", "Run gator init")
    assert leaked is False


@pytest.mark.parametrize("mode", ["missing", "rejects", "toplevel"])
def test_welcome_copy_manual_state(page, dashboard_fleet, mode):
    """A missing or failing parent Clipboard API, or no Dashboard parent at
    all, gives the honest manual state: instruction shown, announced, and
    the prompt selected. "Copied" never appears."""
    if mode == "missing":
        page.add_init_script(
            "if (window === window.top) Object.defineProperty(navigator,"
            " 'clipboard', {value: undefined, configurable: true});")
    elif mode == "rejects":
        page.add_init_script(
            "if (window === window.top) Object.defineProperty(navigator,"
            " 'clipboard', {configurable: true, value: {writeText:"
            " () => Promise.reject(new Error('denied'))}});")
    if mode == "toplevel":
        page.goto(_origin(dashboard_fleet).rstrip("/") + DOC_ROUTE
                  + DOC_NAMES["session"], wait_until="load")
        frame = page.main_frame
    else:
        frame = _open_session_frame(page, dashboard_fleet)
    frame.click("#copy-session-prompt")
    frame.wait_for_function(
        "() => !document.getElementById('copy-manual').hidden", timeout=5000)
    state = _frame_state(frame)
    assert state["status"] == "Copy did not work here. Copy the prompt manually."
    assert state["selection"] == SESSION_PROMPT
    page.wait_for_timeout(1700)  # past the document's reply timeout
    assert _frame_state(frame)["status"] != "Copied"


# The Dashboard must ignore every one of these; "control" proves the
# harness would see a write and a reply.
_IGNORED = {
    "page": ("page", COPY_REQUEST),
    "unrelated-frame": ("unrelated", COPY_REQUEST),
    "how-frame": ("how", COPY_REQUEST),
    "stale-frame": ("stale", COPY_REQUEST),
    "version-2": ("session", {**COPY_REQUEST, "v": 2}),
    "unknown-action": ("session", {**COPY_REQUEST, "action": "switch-tab"}),
    "extra-key": ("session", {**COPY_REQUEST, "text": "x"}),
    "array": ("session", ["gator-welcome", 1, "copy-session-prompt"]),
    "string": ("session", "copy-session-prompt"),
}

_RECORD_AND_POST = """(d) => {
    window.__replies = [];
    window.addEventListener('message', e => window.__replies.push(e.data));
    window.parent.postMessage(d, '*');
}"""


@pytest.mark.parametrize("case", ["control", *_IGNORED])
def test_welcome_copy_ignores_everything_else(page, dashboard_fleet, case):
    """Only the exact request from the current Start-a-session frame causes
    a clipboard write and a reply; every other sender or shape causes no
    write, no reply, no topic/URL/history change, and no request."""
    page.add_init_script("""if (window === window.top) {
        window.__writes = [];
        Object.defineProperty(navigator, 'clipboard', {configurable: true,
            value: {writeText: t => { window.__writes.push(t); return Promise.resolve(); }}});
    }""")
    _open_session_frame(page, dashboard_fleet)
    sender, data = ("session", COPY_REQUEST) if case == "control" else _IGNORED[case]

    if sender == "how":
        page.click("#welcome-tab-how")
        page.wait_for_function(
            "() => document.querySelector('#welcome-panel-how iframe')", timeout=5000)
        page.wait_for_load_state("load")
        page.click("#welcome-tab-session")
    elif sender == "unrelated":
        page.evaluate("""() => {
            const f = document.createElement('iframe');
            f.id = 'unrelated-frame';
            f.setAttribute('sandbox', 'allow-scripts');
            f.srcdoc = '<p>unrelated</p>';
            document.body.appendChild(f);
        }""")
        page.wait_for_load_state("load")
    elif sender == "stale":
        # Keep the first mount's session iframe, remount Welcome, then
        # re-attach the old node: a stale frame of the session document.
        page.evaluate("() => { window.__old ="
                      " document.querySelector('#welcome-panel-session iframe'); }")
        page.evaluate("() => document.querySelector("
                      "'.sidebar-item[data-view=\"fleet\"]').click()")
        _open_welcome(page)
        page.wait_for_function(
            "() => document.querySelector('#welcome-panel-session iframe')", timeout=5000)
        page.evaluate("() => { window.__old.id = 'stale-frame';"
                      " document.body.appendChild(window.__old); }")
        page.wait_for_load_state("load")

    before = page.evaluate("() => ({url: location.href, len: history.length})")
    topic_before = _selected(page)
    requests = []
    page.on("request", lambda r: requests.append(r.url))

    if sender == "page":
        page.evaluate("""(d) => {
            window.__pageReplies = [];
            window.addEventListener('message', e => {
                if (e.data && e.data.action === 'copy-session-prompt-result')
                    window.__pageReplies.push(e.data);
            });
            window.postMessage(d, '*');
        }""", data)
        target = None
    else:
        selector = {"session": "#welcome-panel-session iframe",
                    "how": "#welcome-panel-how iframe",
                    "unrelated": "#unrelated-frame",
                    "stale": "#stale-frame"}[sender]
        target = _frame_for(page, selector)
        if sender == "stale":
            target.wait_for_selector("#copy-session-prompt", timeout=5000)
        target.evaluate(_RECORD_AND_POST, data)
    page.wait_for_timeout(400)

    writes = page.evaluate("() => window.__writes")
    replies = (page.evaluate("() => window.__pageReplies") if target is None
               else target.evaluate("() => window.__replies"))
    if case == "control":
        assert writes == [SESSION_PROMPT]
        assert replies == [{"type": "gator-welcome", "v": 1,
                            "action": "copy-session-prompt-result", "ok": True}]
    else:
        assert writes == []
        assert replies == []
    assert _selected(page) == topic_before
    assert page.evaluate("() => ({url: location.href, len: history.length})") == before
    assert requests == []
