"""B2 Slice 3 Playwright pins — sandboxed HTML preview.

Hits the actual subprocess dashboard spun up by Plan A's
`dashboard_fleet` fixture. Covers:

- Server-side CSP + Vary header emit (via urllib direct + Playwright
  interception).
- `Sec-Fetch-Dest`-driven embedded/external CSP selection.
- Iframe sandbox exact-string invariant.
- Detector-liveness pin (mandatory — negative-control fixture
  triggers three real CSP violations).
- Shipped-template compat matrix (parameterized over every HTML
  file `_copy_shipped_blueprints` seeded).
- Parent-isolation opaque-origin invariant.
- Refresh cache-buster reissues HTTP request.
- Copy path writes clipboard.
- Iframe base sizing floor (400px).
- Open-externally UX contract (button label, no-opener, CSP
  sandbox header on top-level response).

Fixtures per r14 §M2: function-scoped `csp_violation_listener`
installs the `securitypolicyviolation` DOM event listener on the
per-test context BEFORE any page navigates. Both the mandatory
liveness pin and every compat pin consume the same fixture so the
listener is guaranteed on the exact context each test uses.
"""

import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest


# ── B2 Slice 3 (v2.13.0): CSP violation listener + helpers ────────

_CSP_VIOLATION_INIT_SCRIPT = """
window.__csp_violations = [];
// Cross-frame relay: a sandboxed child raises CSP violations
// against ITS OWN `window.__csp_violations`, so a parent-side
// `page.evaluate(...)` read against the parent's array returns
// [] regardless of what the child produced. The compat matrix
// needs a parent-side aggregate to avoid a per-iteration
// `frame.evaluate(...)` — which has no default Playwright
// timeout and hangs indefinitely on shipped templates whose
// documents don't reach a stable execution context. Each
// document posts its violations UP to the parent; the parent
// aggregates. Liveness reads the CHILD's local array directly
// (unchanged) so the frame-side read invariant remains pinned;
// compat reads the PARENT's aggregated array (fast + robust).
window.addEventListener("message", (e) => {
    if (e && e.data && e.data.__csp_violation) {
        window.__csp_violations.push(e.data.__csp_violation);
    }
});
document.addEventListener("securitypolicyviolation", (e) => {
    const violation = {
        blockedURI: e.blockedURI,
        violatedDirective: e.violatedDirective,
        effectiveDirective: e.effectiveDirective,
        sourceFile: e.sourceFile || null,
        lineNumber: e.lineNumber,
        sample: e.sample ? e.sample.slice(0, 200) : null,
    };
    window.__csp_violations.push(violation);
    if (window.parent !== window) {
        try {
            window.parent.postMessage(
                {__csp_violation: violation}, "*");
        } catch (_) { /* noop */ }
    }
});
"""

# Bounded event-loop settling barrier per r8 §M1. `networkidle`
# alone is not enough — CSP violation events dispatch on the event
# loop, not as network activity. Double `requestAnimationFrame` +
# `setTimeout(0)` flushes queued events before the compat pin
# reads `window.__csp_violations`.
_CSP_SETTLE_BARRIER = """
() => new Promise(resolve => {
    requestAnimationFrame(() => {
        requestAnimationFrame(() => setTimeout(resolve, 0));
    });
})
"""


@pytest.fixture
def csp_violation_listener(context):
    """Function-scoped per r8 §M2. Installs the CSP violation
    listener on the per-test Playwright context BEFORE any page
    navigates. Consumed by both the liveness pin and every compat
    pin so the listener is guaranteed on the exact context.
    """
    context.add_init_script(_CSP_VIOLATION_INIT_SCRIPT)
    return None


# ── Direct URL helpers (no Dashboard shell involvement) ───────────

def _raw_url(fleet, path, *, repo="alpha"):
    """Build a `/raw/` URL against the running dashboard fleet.
    Defaults to `alpha`; pass `repo="beta"` for `gator-command/…`
    paths (alpha deletes `gator-command/` in the seed history).
    """
    return (fleet["url"].rstrip("/")
            + f"/api/repo/{repo}/raw/" + path)


def _urllib_get(fleet, path, *, extra_headers=None):
    """GET via `urllib.request` — does NOT send `Sec-Fetch-Dest`,
    so this shape hits the external-CSP fallback branch. Returns
    `(status, body_bytes, headers_dict)`. Never raises on non-2xx.
    """
    req = urllib.request.Request(_raw_url(fleet, path))
    if extra_headers:
        for k, v in extra_headers.items():
            req.add_header(k, v)
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return (resp.status, resp.read(), dict(resp.headers))
    except urllib.error.HTTPError as exc:
        return (exc.code, exc.read(), dict(exc.headers))


def _load_raw_in_iframe(page, fleet, path, *, repo="alpha"):
    """Navigate the page to the DASHBOARD ORIGIN, then inject an
    iframe with the shipped sandbox attribute pointing at the
    given `/raw/` URL. Returns the child Playwright `Frame`.

    Why the parent MUST be same-origin with the dashboard: B2's
    CSP includes `frame-ancestors 'self'`, which rejects framing
    by an opaque-origin document (`about:blank`, `data:` URLs).
    `page.set_content(...)` alone leaves the top-level page on
    an opaque origin, and Chromium responds with
    `chrome-error://chromewebdata/` inside the iframe instead of
    the real content. That failure mode was silently making the
    compat pin pass (an empty iframe has no CSP violations).

    Navigating first to `<dashboard>/` (which returns the shell
    HTML without any CSP header) makes the parent same-origin so
    `frame-ancestors 'self'` permits the iframe load.
    """
    raw = _raw_url(fleet, path, repo=repo)
    origin = fleet["url"].rstrip("/") + "/"
    # If the page is not already on the dashboard origin, navigate
    # there once so `frame-ancestors 'self'` allows the iframe.
    # Subsequent same-origin loads reuse the shell — the compat
    # matrix iterates 9+ times and would otherwise incur a full
    # dashboard re-render (Tier-1 data collection etc.) per file.
    if not page.url.startswith(origin):
        page.goto(origin, wait_until="load")
    # Remove any pre-existing iframe from a prior iteration.
    page.evaluate("""
        () => {
            const prev = document.querySelector("iframe.repo-iframe");
            if (prev) prev.remove();
        }
    """)
    # Inject the iframe programmatically so the src load fires
    # under the same-origin parent.
    page.evaluate(f"""
        () => {{
            const iframe = document.createElement("iframe");
            iframe.className = "repo-iframe";
            iframe.setAttribute("sandbox", "allow-scripts");
            iframe.src = {json.dumps(raw)};
            document.body.appendChild(iframe);
        }}
    """)
    handle = page.locator("iframe.repo-iframe").element_handle()
    frame = handle.content_frame()
    if frame is None:
        raise RuntimeError(
            f"iframe.content_frame() returned None for {raw!r}")
    # "load" fires when synchronous resources have loaded — faster
    # and more reliable than "networkidle" for sandboxed opaque-
    # origin iframes, which sometimes don't propagate networkidle
    # to the parent's Playwright tracking. The CSP settling barrier
    # (double-rAF + setTimeout(0)) afterwards flushes any queued
    # `securitypolicyviolation` events.
    frame.wait_for_load_state("load", timeout=10000)
    return frame


# ── Production-path helper (2026-09-10 Codex R1 F2) ───────────────

def _click_file_via_repo_view(page, fleet, filepath, *, repo="alpha"):
    """Drive the real Dashboard shell to open the repo and click
    the sidebar file item that would produce the production HTML
    iframe. Returns the child `Frame`.

    Exercises the full production trust boundary: URL routing in
    `dashboard.js` (`?repo=` param → `showView("repo", …)`), sidebar
    tree construction in `views/repo.js` (`buildTree` /
    `renderSidebarInto`), click handler wiring, and `loadFile()`'s
    HTML branch that renders `<iframe class="repo-iframe"
    sandbox="allow-scripts">` and the three shipped control buttons
    (Copy path / Refresh / Open in new tab). A regression in any of
    those layers fails these pins — a low-level helper (like
    `_load_raw_in_iframe`) would let them pass while the production
    surface silently broke. `_load_raw_in_iframe` remains for CSP
    corpus probing where the production sidebar walk would add
    unnecessary cost per iteration (see r14 §M2).

    `filepath` is the sidebar `data-path` — the repo-relative path
    from the namespace root. For a file under `.gator/blueprints/`
    the value is `blueprints/plain.html` (the `.gator` prefix is
    the implicit namespace).
    """
    origin = fleet["url"].rstrip("/") + "/"
    page.goto(origin + "?repo=" + repo, wait_until="load")
    # Wait for the Repo view to mount and populate at least one
    # file item before touching the sidebar DOM.
    page.wait_for_selector(".repo-file-item", timeout=15000)

    # Expand each ancestor directory so the target file item is in
    # a visible container. `renderSidebarInto` renders every file
    # into the DOM, but collapsed dirs have `display:none` on their
    # child containers — clicking a hidden button doesn't fire the
    # production listener.
    if "/" in filepath:
        parts = filepath.split("/")[:-1]
        for i in range(len(parts)):
            dir_path = "/".join(parts[:i + 1])
            page.evaluate(
                "(selector) => {"
                "  const btn = document.querySelector(selector);"
                "  if (btn) {"
                "    const contents = btn.nextElementSibling;"
                "    if (contents && contents.style.display === 'none') {"
                "      btn.click();"
                "    }"
                "  }"
                "}",
                f'.repo-tree-dir[data-dir="{dir_path}"]',
            )

    selector = f'.repo-file-item[data-path="{filepath}"]'
    page.wait_for_selector(selector, state="attached", timeout=10000)
    # Dispatch the click through JS so residual visibility state
    # from collapsed ancestors doesn't affect Playwright's
    # actionability check — the production listener runs whether
    # or not the row is visible.
    page.evaluate(
        "(sel) => document.querySelector(sel).click()", selector)
    # `loadFile()`'s HTML branch attaches the iframe synchronously
    # via `innerHTML`; wait for it to appear.
    page.wait_for_selector("iframe.repo-iframe", timeout=5000)
    handle = page.locator("iframe.repo-iframe").element_handle()
    frame = handle.content_frame()
    if frame is None:
        raise RuntimeError(
            f"iframe.content_frame() returned None for {filepath!r}")
    frame.wait_for_load_state("load", timeout=10000)
    return frame


# ── H1: `apply_response_headers` byte-exact preservation ──────────

def test_apply_response_headers_unchanged_by_b2():
    """r2 §H1 seam-guard invariant: B1's `apply_response_headers`
    body must stay byte-exact across the B2 landing. B2 is
    additive-only via `apply_html_csp_headers`.
    """
    src = (Path(__file__).resolve().parents[2]
           / "src" / "gator_command" / "scripts"
           / "gator-dashboard.py").read_text(encoding="utf-8")
    idx = src.find("def apply_response_headers(")
    assert idx >= 0, "apply_response_headers definition missing"
    # Slice to the next top-level def or a bounded window.
    body = src[idx:idx + 2000]
    # Assert the shipped four-header body is present and intact.
    for expected in (
        'handler.send_header("Content-Type", mime)',
        'handler.send_header("Content-Length", str(body_len))',
        'handler.send_header("X-Content-Type-Options", "nosniff")',
        'if cache_control:',
        'handler.send_header("Cache-Control", cache_control)',
    ):
        assert expected in body, (
            f"apply_response_headers byte-diff regression: "
            f"missing {expected!r}")
    # Guard against Content-Security-Policy leaking in — MUST
    # come from apply_html_csp_headers only.
    csp_idx = body.find("Content-Security-Policy")
    # Allow "Content-Security-Policy" to appear in the docstring
    # comment (which references it). But not inside a
    # `handler.send_header(...)` call.
    if csp_idx >= 0:
        # Ensure it is not inside a send_header call within
        # apply_response_headers.
        pre = body[max(0, csp_idx - 40):csp_idx]
        assert "send_header" not in pre, (
            "apply_response_headers must not emit CSP header — "
            "the seam is `apply_html_csp_headers`")


# ── Server-side CSP + Vary (urllib, no browser) ───────────────────

def test_html_response_missing_sec_fetch_dest_gets_external_csp(
        dashboard_fleet):
    """r4 §L2 pin: a non-browser client (urllib does not send
    `Sec-Fetch-Dest`) MUST receive the external CSP — the safer
    fallback per r1 §3.2 shipped in Slice 1.
    """
    status, body, headers = _urllib_get(
        dashboard_fleet, "blueprints/plain.html")
    assert status == 200
    csp = headers.get("Content-Security-Policy", "")
    assert csp.startswith("sandbox allow-scripts;"), (
        f"expected external CSP with leading sandbox directive; "
        f"got {csp!r}")


def test_html_response_vary_header(dashboard_fleet):
    """r4 §M1 pin: every HTML response — embedded or external —
    carries `Vary: Sec-Fetch-Dest` UNCONDITIONALLY so
    intermediaries cache correctly. Test both branches.
    """
    # External (no Sec-Fetch-Dest sent).
    _, _, headers_ext = _urllib_get(
        dashboard_fleet, "blueprints/plain.html")
    assert "Vary" in headers_ext
    assert "Sec-Fetch-Dest" in headers_ext["Vary"]

    # Embedded (Sec-Fetch-Dest: iframe).
    _, _, headers_emb = _urllib_get(
        dashboard_fleet, "blueprints/plain.html",
        extra_headers={"Sec-Fetch-Dest": "iframe"})
    assert "Vary" in headers_emb
    assert "Sec-Fetch-Dest" in headers_emb["Vary"]


def test_html_response_embedded_csp_variant(dashboard_fleet):
    """r7 §M5 pin: an iframe-context request (Sec-Fetch-Dest:
    iframe) gets the embedded CSP variant — NO leading `sandbox
    allow-scripts;` prepend. The response still carries
    `default-src 'none'`, `script-src 'unsafe-inline'` (NO
    `'unsafe-eval'` per r5), `form-action 'none'`,
    `frame-ancestors 'self'`.
    """
    _, _, headers = _urllib_get(
        dashboard_fleet, "blueprints/plain.html",
        extra_headers={"Sec-Fetch-Dest": "iframe"})
    csp = headers.get("Content-Security-Policy", "")
    assert not csp.startswith("sandbox "), (
        f"embedded CSP must not have sandbox prefix; got {csp!r}")
    assert "default-src 'none'" in csp
    assert "script-src 'unsafe-inline'" in csp
    assert "'unsafe-eval'" not in csp, (
        "CSP must not permit 'unsafe-eval'")
    assert "form-action 'none'" in csp
    assert "frame-ancestors 'self'" in csp


def test_html_response_external_csp_variant(dashboard_fleet):
    """External-open response carries the leading `sandbox
    allow-scripts;` directive plus the same base directives —
    the top-level document runs opaque-origin.
    """
    _, _, headers = _urllib_get(
        dashboard_fleet, "blueprints/plain.html",
        extra_headers={"Sec-Fetch-Dest": "document"})
    csp = headers.get("Content-Security-Policy", "")
    assert csp.startswith("sandbox allow-scripts;")
    assert "default-src 'none'" in csp
    assert "'unsafe-eval'" not in csp


def test_non_html_response_has_no_csp(dashboard_fleet):
    """Complementary invariant: non-HTML `/raw/` responses (e.g.
    image, JSON) do NOT get CSP or Vary — they are B1-only.
    """
    # blueprints/hero.png is seeded by content_transport_seed.
    _, _, headers = _urllib_get(
        dashboard_fleet, "blueprints/hero.png")
    assert "Content-Security-Policy" not in headers
    # Vary header comes from B2 only — should be absent for
    # non-HTML paths.
    assert "Vary" not in headers or (
        "Sec-Fetch-Dest" not in headers.get("Vary", ""))


# ── L2: URL canonical-prefix guard (static) ───────────────────────

def test_compat_urls_use_canonical_namespace_prefixes():
    """r14 §M1 static guard: NO test URL in this module uses a
    forbidden alias prefix — B1's governance-root TRIPWIRE
    rejects `source/` prepended to a governance namespace. Guards
    test-authoring at the point where a future compat pin might
    mistakenly hardcode the wrong URL.

    Constructs the forbidden literals at runtime so the guard is
    not self-referential (the test module's own SOURCE contains
    these strings inside this docstring / concatenation — the
    check must scan the raw URL data, not the source text).
    """
    forbidden_a = "source" + "/" + "gator-command" + "/"
    forbidden_b = "source" + "/" + ".gator" + "/"
    # Enumerate every string literal that looks like a `/raw/`
    # path in the discover helper.
    src_lines = Path(__file__).read_text(
        encoding="utf-8").splitlines()
    offenders = []
    for lineno, line in enumerate(src_lines, start=1):
        # Ignore this test's own docstring and the forbidden-
        # literal construction lines.
        if "forbidden_a" in line or "forbidden_b" in line:
            continue
        if "docstring" in line.lower():
            continue
        if forbidden_a in line or forbidden_b in line:
            offenders.append(f"line {lineno}: {line.rstrip()!r}")
    assert not offenders, (
        "URL uses a forbidden namespace alias prefix — the "
        "canonical prefix is `gator-command/` (or implicit for "
        ".gator/) per B1's governance-root TRIPWIRE:\n"
        + "\n".join("  " + o for o in offenders))


# ── Iframe sandbox exact-string invariant (r7 §H2) ────────────────

def test_embedded_iframe_sandbox_exact_string(page, dashboard_fleet):
    """r7 §H2 charter TRIPWIRE: iframe sandbox is EXACTLY
    `allow-scripts` — nothing more. Character-exact assertion
    against the iframe rendered by production `views/repo.js`
    (2026-09-10 Codex R1 F2 — retargeted from `_load_raw_in_iframe`
    so the shipped `loadFile()` HTML branch is on the test path).
    """
    _click_file_via_repo_view(page, dashboard_fleet, "blueprints/plain.html")
    attr = page.locator("iframe.repo-iframe").get_attribute(
        "sandbox")
    assert attr == "allow-scripts", (
        f"sandbox attribute MUST be exactly 'allow-scripts'; "
        f"got {attr!r}")


# ── Detector-liveness pin (r7 §M5 mandatory) ──────────────────────

def test_csp_violation_detector_flags_negative_control(
        page, dashboard_fleet, csp_violation_listener):
    """MANDATORY liveness pin: the negative-control fixture
    `_csp_negative_control.html` deliberately violates
    `style-src-elem` (external stylesheet), `img-src`
    (cross-origin image), and `connect-src` (cross-origin fetch).
    A working detector MUST collect these events. If this pin
    fails, the entire compat suite is untrustworthy.

    Two-lane liveness (2026-09-10 Codex R2 F1): asserts BOTH
    lanes of the detector plumbing that the compat matrix
    depends on:

    1. **Child-side lane**: `frame.evaluate` reads the child's
       local `window.__csp_violations`. Proves the CSP listener
       runs INSIDE the sandboxed child frame — this is what the
       liveness contract has always claimed to pin, and what a
       stripped-down single-lane assertion would cover.

    2. **Relay lane**: `page.evaluate` reads the parent's
       aggregate. Proves the child-side `window.parent.postMessage`
       fired AND the parent's `message` listener appended to the
       parent's array. The compat matrix reads ONLY this parent
       aggregate — if either side of the postMessage relay
       regresses, the compat matrix silently reports every
       template as clean. Without this second assertion the R1
       remediation's silent-false-pass hole reopens.

    r8 §M1 fix (retained): use `wait_for_function` polling for
    the specific CSP-L3 directive names (`style-src-elem` +
    `img-src`); `connect-src` is supplementary due to browser
    scheduling variance.
    """
    frame = _load_raw_in_iframe(
        page, dashboard_fleet,
        "blueprints/_csp_negative_control.html")

    # ── Lane 1: child-side listener collected the violations ──
    frame.wait_for_function("""
        () => {
            const violations = window.__csp_violations || [];
            const dirs = new Set(violations
                .map(v => v.effectiveDirective));
            return dirs.has("style-src-elem")
                && dirs.has("img-src");
        }
    """, timeout=5000)
    child_violations = frame.evaluate(
        "() => window.__csp_violations || []")
    child_effective = {
        v["effectiveDirective"] for v in child_violations}
    assert "style-src-elem" in child_effective, (
        f"child frame missing style-src-elem violation — "
        f"listener not installed in child? got {child_effective}")
    assert "img-src" in child_effective, (
        f"child frame missing img-src violation — listener not "
        f"installed in child? got {child_effective}")

    # ── Lane 2: postMessage relay landed those events in the
    # parent's aggregate ────────────────────────────────────────
    #
    # The compat matrix reads this parent-side array only. A
    # regression that broke either the child-side
    # `window.parent.postMessage` call or the parent-side
    # `message` listener would leave the compat matrix reading
    # `[]` and passing every template as clean. This
    # assertion IS the compat detector's liveness contract.
    page.wait_for_function("""
        () => {
            const violations = window.__csp_violations || [];
            const dirs = new Set(violations
                .map(v => v.effectiveDirective));
            return dirs.has("style-src-elem")
                && dirs.has("img-src");
        }
    """, timeout=5000)
    parent_violations = page.evaluate(
        "() => window.__csp_violations || []")
    parent_effective = {
        v["effectiveDirective"] for v in parent_violations}
    assert "style-src-elem" in parent_effective, (
        f"parent aggregate missing style-src-elem — postMessage "
        f"relay may be broken. child had {child_effective}, "
        f"parent had {parent_effective}")
    assert "img-src" in parent_effective, (
        f"parent aggregate missing img-src — postMessage relay "
        f"may be broken. child had {child_effective}, parent had "
        f"{parent_effective}")


# ── Shipped-template compat matrix (r4 §M2 → r14 §M1) ─────────────

def _discover_shipped_html(dashboard_fleet):
    """Enumerate the shipped HTML files present in the test repo
    (as copied by `_copy_shipped_blueprints`). Returns a list of
    `(html_file_url_path, target_repo)` tuples.
    """
    alpha_root = Path(dashboard_fleet["repos"]["alpha"]["path"])
    beta_root = Path(dashboard_fleet["repos"]["beta"]["path"])

    pairs = []
    # `.gator/blueprints/shipped/*.html` visible on both repos.
    for html in sorted((alpha_root / ".gator" / "blueprints"
                        / "shipped").glob("*.html")):
        pairs.append((
            f"blueprints/shipped/{html.name}", "alpha"))
    # `gator-command/shipped-templates/*.html` ONLY on beta (alpha
    # deletes gator-command in seed_history_commits).
    gc_shipped = beta_root / "gator-command" / "shipped-templates"
    if gc_shipped.is_dir():
        for html in sorted(gc_shipped.glob("*.html")):
            pairs.append((
                f"gator-command/shipped-templates/{html.name}",
                "beta"))
    return pairs


def test_shipped_template_csp_compat(
        page, dashboard_fleet, csp_violation_listener):
    """r4 §M2 → r14 §M1 pin: every shipped HTML file loads under
    the B2 CSP without any `securitypolicyviolation` events.

    Discovery happens at test time via `_copy_shipped_blueprints`'s
    copies. Each file is loaded inside a sandboxed iframe (embedded
    context — same-origin parent satisfies `frame-ancestors 'self'`).
    Status-200 precondition ensures we're not silently passing on
    404 pages.

    Parent-side aggregate read (2026-09-10 Codex R1 F1 fix): CSP
    violations raised inside a sandboxed child frame populate the
    CHILD frame's `window.__csp_violations` array — NOT the
    parent's. The prior implementation reset and read via
    `page.evaluate(...)` on the parent's array (always empty)
    without any cross-frame relay, so it returned `[]` regardless
    of what the child produced. The fix is architectural: the
    context init script (`_CSP_VIOLATION_INIT_SCRIPT`) now
    postMessage-relays every child-side violation up to
    `window.parent`, and the parent's `message` listener appends
    to its own `window.__csp_violations`. postMessage crosses the
    `sandbox="allow-scripts"` boundary — that flag gates
    `window.parent.location` and `window.parent.document`, not
    postMessage. Parent-side aggregation restores the fast path
    (`page.evaluate` returns quickly regardless of child load
    state) while the CORRECT data flow is preserved.

    Why not per-iteration `frame.evaluate` on the child directly:
    `frame.evaluate` has NO default Playwright timeout. On shipped
    templates whose documents don't reach a stable execution
    context, `evaluate` blocks indefinitely — observed as a 40+
    minute hang on Windows with the 9-file compat matrix. The
    liveness pin STILL reads the child's array directly (its
    contract is "prove the listener runs inside the child"); a
    frame that's healthy enough for the liveness pin's known-good
    fixture is fine, but arbitrary shipped templates aren't
    guaranteed to be.
    """
    pairs = _discover_shipped_html(dashboard_fleet)
    assert pairs, (
        "no shipped HTML files discovered in test repo — "
        "`_copy_shipped_blueprints` may have skipped silently. "
        "This is a hard failure: the compat pin cannot vouch "
        "for anything without templates.")

    origin = dashboard_fleet["url"].rstrip("/") + "/"
    if not page.url.startswith(origin):
        page.goto(origin, wait_until="load")

    findings = []
    for path, repo in pairs:
        # Status precondition — a 404 page loading in Playwright
        # would silently pass the CSP-empty assertion.
        url = _raw_url(dashboard_fleet, path, repo=repo)
        try:
            resp = urllib.request.urlopen(url, timeout=10)
            status = resp.status
        except urllib.error.HTTPError as exc:
            status = exc.code
        if status != 200:
            findings.append(
                f"{path}: /raw returned {status} (must be 200 "
                f"before CSP compat can be asserted)")
            continue

        # Reset the parent's aggregator before injecting the new
        # child. Each new iframe injection starts the child with
        # its own fresh `window.__csp_violations = []` (via the
        # init script), and its postMessage relay will populate
        # the parent's array during the wait window.
        page.evaluate(
            "() => { window.__csp_violations = []; }")
        page.evaluate(f"""
            () => {{
                const prev = document.querySelector(
                    "iframe.repo-iframe-compat");
                if (prev) prev.remove();
                const iframe = document.createElement("iframe");
                iframe.className = "repo-iframe-compat";
                iframe.setAttribute("sandbox", "allow-scripts");
                iframe.src = {json.dumps(url)};
                document.body.appendChild(iframe);
            }}
        """)
        # Fixed bounded wait — the child raises CSP events during
        # document parsing / resource fetching; postMessage relay
        # runs on the parent's task queue and arrives within a
        # tick or two of each violation. 1.5s is well beyond the
        # sub-second dispatch window observed in Codex's r7
        # Chromium probe.
        page.wait_for_timeout(1500)
        # Flush the parent's task queue so any in-flight message
        # handlers complete before the read.
        page.evaluate(_CSP_SETTLE_BARRIER)
        violations = page.evaluate(
            "() => window.__csp_violations || []")
        if violations:
            findings.append(
                f"{path}: {len(violations)} CSP violation(s) — "
                f"{[v['effectiveDirective'] for v in violations]}")

    assert not findings, (
        "shipped template CSP-compat failures:\n"
        + "\n".join("  " + f for f in findings))


# ── Parent isolation (r7 §M3 → r8 §M1 shape) ──────────────────────

def test_parent_document_cannot_reach_child_via_dom_api(
        page, dashboard_fleet):
    """r8 §M1 opaque-origin invariant: parent-side access to
    `iframe.contentDocument` MUST fail — either `null` (Chromium's
    opaque-origin shape) or `SecurityError`. Explicitly rejects
    "reachable" (any success path is a boundary violation).
    Retargeted at the production iframe (2026-09-10 Codex R1 F2)
    so the pin covers `loadFile()`'s rendered attributes, not the
    test helper's.
    """
    _click_file_via_repo_view(page, dashboard_fleet, "blueprints/plain.html")
    result = page.evaluate("""
        () => {
            const iframe = document.querySelector("iframe.repo-iframe");
            if (iframe.contentDocument === null) return "opaque-origin";
            try {
                const _ = iframe.contentDocument.body;
                return "reachable";
            } catch (e) { return e.name; }
        }
    """)
    assert result in ("opaque-origin", "SecurityError"), (
        f"parent-isolation invariant broken; got {result!r}")


# ── Inline script runs inside the sandbox (r7 §M3) ────────────────

def test_embedded_html_iframe_runs_inline_script(
        page, dashboard_fleet):
    """r7 §M3: `sandbox="allow-scripts"` permits inline `<script>`
    inside the iframe. The `inline-script.html` fixture sets
    `document.body.dataset.marker = "ran"` on load. Retargeted
    (2026-09-10 Codex R1 F2) at the production iframe emitted by
    `loadFile()` so a regression that dropped `sandbox="allow-
    scripts"` from the shipped attribute set (or that broke the
    iframe wiring outright) fails here.
    """
    frame = _click_file_via_repo_view(
        page, dashboard_fleet, "blueprints/inline-script.html")
    marker = frame.evaluate(
        "() => document.body && document.body.dataset.marker")
    assert marker == "ran", (
        f"expected inline script to set body.dataset.marker; "
        f"got {marker!r} in frame at {frame.url!r}")


# ── Form submission blocked by CSP (r1 §7.3) ──────────────────────

def test_embedded_html_form_submission_blocked(
        page, dashboard_fleet):
    """`form-action 'none'` blocks the submission target. The
    iframe URL MUST NOT change after `form.submit()`. Retargeted
    (2026-09-10 Codex R1 F2) at the production iframe so the pin
    covers the shipped CSP+iframe combination, not a test-side
    replica.
    """
    frame = _click_file_via_repo_view(
        page, dashboard_fleet, "blueprints/with-form.html")
    initial_url = frame.url
    frame.evaluate("""
        () => {
            const form = document.querySelector("form");
            if (form) form.submit();
        }
    """)
    # Small settle to give the browser a chance to attempt (and
    # be blocked from) the submission.
    page.wait_for_timeout(500)
    assert frame.url == initial_url, (
        f"form submission navigated the iframe from "
        f"{initial_url!r} to {frame.url!r} — form-action 'none' "
        f"should have blocked it")


# ── r14 §M1 production-path pins (2026-09-10 Codex R1 F2) ─────────
#
# These five pins fill the r14 gap: the shipped iframe branch
# (`.repo-file-header` buttons + `.repo-iframe`) rendered by
# `views/repo.js::loadFile()` is now covered end-to-end. Prior to
# this round the r14-named pins existed in name only — the four
# tests above exercised a test-side helper that hardcoded the
# sandbox attribute and never went through production wiring.


def test_open_externally_button_label_matches_shipped_policy(
        page, dashboard_fleet):
    """r10 §M1 charter TRIPWIRE: the Open-externally button
    caption MUST NOT contain the phrase "same-origin" or "grants
    same-origin access". The `sandbox allow-scripts` CSP on the
    top-level response makes the popup document opaque-origin —
    no same-origin escalation is granted. The caption reads
    "Open in new tab (full-screen, sandboxed)".
    """
    _click_file_via_repo_view(
        page, dashboard_fleet, "blueprints/plain.html")
    btn_text = page.locator(".open-external-btn").inner_text()
    lowered = btn_text.lower()
    assert "same-origin" not in lowered, (
        f"Open-externally button must not claim same-origin "
        f"access; got {btn_text!r}")
    assert "grants same-origin" not in lowered, (
        f"Open-externally button must not claim to grant same-"
        f"origin access; got {btn_text!r}")
    assert "Open in new tab (full-screen, sandboxed)" in btn_text, (
        f"Open-externally caption regressed; expected the "
        f"shipped label; got {btn_text!r}")


def test_open_externally_popup_noopener_target_and_response_csp(
        page, dashboard_fleet):
    """r13 §M1 pin: clicking Open-externally opens the raw URL in
    a new tab with `noopener,noreferrer`. Assert (1) the popup URL
    matches the `/raw/` URL for the file, (2) `window.opener`
    inside the popup is null (noopener honored), and (3) the
    ACTUAL BROWSER navigation Response carries
    `Content-Security-Policy: sandbox allow-scripts` — the
    opaque-origin escalation guard.

    Browser-Response capture (2026-09-10 Codex R2 F2): register
    `page.context.on("response", ...)` BEFORE the click and
    filter by `response.url == expected_url` so we assert against
    the exact Response object the browser produced for the popup
    navigation. A separate synthetic `urllib.request` GET can
    return the expected CSP while the browser's actual navigation
    takes a different code path (different connection reuse,
    different headers, different CSP-context) — the pin's
    contract is "the popup navigation gets the right CSP", not
    "any document-context request does."
    """
    _click_file_via_repo_view(
        page, dashboard_fleet, "blueprints/plain.html")
    expected_url = (dashboard_fleet["url"].rstrip("/")
                    + "/api/repo/alpha/raw/blueprints/plain.html")

    # Register the response listener BEFORE the click so we can
    # capture the popup's initial navigation Response (which
    # fires before `popup = popup_info.value` returns).
    matching_responses = []

    def _capture(response):
        if response.url == expected_url:
            matching_responses.append(response)

    page.context.on("response", _capture)
    try:
        with page.expect_popup() as popup_info:
            page.locator(".open-external-btn").click()
        popup = popup_info.value
        popup.wait_for_load_state("load", timeout=10000)
        try:
            # (1) Popup navigated to the raw URL.
            assert popup.url == expected_url, (
                f"Open-externally popup went to {popup.url!r}; "
                f"expected {expected_url!r}")
            # (2) window.opener is null under `noopener`.
            opener_state = popup.evaluate("() => window.opener")
            assert opener_state is None, (
                f"popup.window.opener must be null under "
                f"`noopener`; got {opener_state!r}")
            # (3) The actual browser navigation Response — not a
            # separately-issued urllib request — carries the
            # external CSP.
            assert matching_responses, (
                f"no browser Response captured for popup URL "
                f"{expected_url!r} (listener may have registered "
                f"too late or URL diverged)")
            nav_response = matching_responses[-1]
            csp = nav_response.header_value(
                "content-security-policy") or ""
            assert csp.startswith("sandbox allow-scripts;"), (
                f"popup navigation Response CSP regressed; "
                f"expected leading `sandbox allow-scripts;`; "
                f"got {csp!r}")
            assert "'unsafe-eval'" not in csp, (
                f"popup navigation Response CSP must not permit "
                f"'unsafe-eval'; got {csp!r}")
        finally:
            popup.close()
    finally:
        page.context.remove_listener("response", _capture)


def test_refresh_reissues_http_request_preserving_version(
        page, dashboard_fleet):
    """r1 §5 pin (r14 §M1): Refresh reseats `iframe.src` with a
    `_r=<epoch-ms>` cache-buster QUERY parameter (not a fragment).
    Asserts (1) initial src has no `_r=`, (2) post-refresh src
    contains `_r=`, (3) the child document was actually reloaded
    (its epoch-ms marker changed), and (4) a `?version=<sha>`
    embedded in `data-base-url` survives across Refresh.
    """
    frame = _click_file_via_repo_view(
        page, dashboard_fleet, "blueprints/refresh-marker.html")
    initial_mark = frame.evaluate(
        "() => document.body && document.body.dataset.mark")
    assert initial_mark, (
        "refresh-marker fixture failed to set body.dataset.mark "
        "on initial load — the pin cannot compare against an "
        "empty baseline")
    initial_src = page.evaluate(
        "() => document.querySelector('iframe.repo-iframe').src")
    assert "_r=" not in initial_src, (
        f"initial src must not carry a cache-buster; "
        f"got {initial_src!r}")

    # Small delay so the child's `Date.now()` differs between
    # loads (millisecond resolution — 20ms is plenty).
    page.wait_for_timeout(20)
    page.locator(".refresh-file-btn").click()
    # The iframe's src change reloads it — wait for the new load.
    page.wait_for_function(
        "() => document.querySelector('iframe.repo-iframe')"
        ".src.includes('_r=')",
        timeout=5000)
    handle = page.locator("iframe.repo-iframe").element_handle()
    frame2 = handle.content_frame()
    assert frame2 is not None
    frame2.wait_for_load_state("load", timeout=10000)

    new_src = page.evaluate(
        "() => document.querySelector('iframe.repo-iframe').src")
    new_mark = frame2.evaluate(
        "() => document.body && document.body.dataset.mark")
    assert "_r=" in new_src, (
        f"Refresh must add `_r=` cache-buster; got {new_src!r}")
    assert new_mark and new_mark != initial_mark, (
        f"Refresh must reload the child document (marker "
        f"unchanged); initial={initial_mark!r} new={new_mark!r}")

    # (4) `?version=` preservation. Seed `data-base-url` with a
    # fake version param and click Refresh — the resulting src
    # must retain the version alongside a fresh `_r=`.
    page.evaluate("""
        () => {
            const iframe = document.querySelector(
                "iframe.repo-iframe");
            iframe.dataset.baseUrl =
                iframe.dataset.baseUrl + "?version=abc123";
        }
    """)
    page.locator(".refresh-file-btn").click()
    page.wait_for_function(
        "() => document.querySelector('iframe.repo-iframe')"
        ".src.includes('version=abc123')",
        timeout=5000)
    versioned_src = page.evaluate(
        "() => document.querySelector('iframe.repo-iframe').src")
    assert "version=abc123" in versioned_src, (
        f"Refresh must preserve `?version=`; "
        f"got {versioned_src!r}")
    assert "_r=" in versioned_src, (
        f"Refresh must add `_r=` even alongside `?version=`; "
        f"got {versioned_src!r}")
    assert "?_r=" not in versioned_src, (
        f"Refresh must append `_r=` with `&` when a version "
        f"query is already present; got {versioned_src!r}")


def test_copy_path_writes_repo_relative_string(
        page, context, dashboard_fleet):
    """r14 §M1 pin: Copy path writes the REPO-RELATIVE path (with
    `.gator/` prefix for implicit-namespace files) to the
    clipboard — NOT the logical/URL path. `copyPathFor(filePath)`
    adds `.gator/` for implicit-namespace files, preserves
    `gator-command/`, strips `source/` for repo code.

    Also pins the button-ref capture async pattern (r14 §M2 →
    charter `B2 button-ref capture TRIPWIRE`, 2026-09-10 Codex R1
    F4 + R3 F1): the button MUST (1) show a transient ✓ checkmark
    inside the Promise `.then` microtask, then (2) restore the
    original icon inside the `setTimeout(1500)` callback WITHOUT
    throwing. Regressing to the pre-R1 `e.currentTarget.*` shape
    would leave the button stuck on ✓ (timer fires against `null`
    and throws `TypeError: Cannot set properties of null`) — the
    `page.on("pageerror", …)` listener + the restored-icon
    assertion catch that.
    """
    # Chromium blocks clipboard writes without an explicit grant.
    context.grant_permissions(
        ["clipboard-write", "clipboard-read"])
    # Register pageerror listener BEFORE the click so the R1 F4
    # `TypeError: Cannot set properties of null` (which the fix
    # eliminates) is captured if a regression reintroduces it.
    page_errors = []

    def _capture_error(err):
        page_errors.append(str(err))

    page.on("pageerror", _capture_error)
    try:
        _click_file_via_repo_view(
            page, dashboard_fleet, "blueprints/plain.html")
        copy_btn = page.locator(".copy-path-btn")
        # Snapshot the original icon so we can assert restoration
        # once the setTimeout(1500) callback runs. The original
        # is set by `loadFile()` via `&#9112;` HTML entity —
        # innerHTML returns the parsed character.
        original_html = copy_btn.inner_html()
        assert original_html and "✓" not in original_html, (
            f"copy button did not have a non-checkmark original "
            f"icon at click time; got {original_html!r}")

        copy_btn.click()
        # (A) Clipboard write is a Promise microtask — resolves
        # within ~one tick. 200ms is well beyond that.
        page.wait_for_timeout(200)
        clipboard = page.evaluate(
            "() => navigator.clipboard.readText()")
        assert clipboard == ".gator/blueprints/plain.html", (
            f"Copy path wrote {clipboard!r}; expected the repo-"
            f"relative `.gator/blueprints/plain.html`")

        # (B) Transient checkmark visible — proves the Promise
        # `.then` callback fired against a live button reference.
        transient = copy_btn.inner_html()
        assert transient == "✓", (
            f"expected transient ✓ on copy button after write; "
            f"got {transient!r}")

        # (C) Wait through the 1.5s restoration timer + buffer,
        # then assert the original icon is back. This is the
        # assertion that would FAIL under the pre-R1 F4 code,
        # because the setTimeout callback would throw against
        # `null` and never run `button.innerHTML = original`.
        page.wait_for_timeout(1600)
        restored = copy_btn.inner_html()
        assert restored == original_html, (
            f"copy button did not restore its original icon "
            f"after 1.5s — the R1 F4 async-target bug may have "
            f"regressed. got {restored!r}, "
            f"expected {original_html!r}")

        # (D) No page errors during the full async flow — a
        # regression to `e.currentTarget.innerHTML = original`
        # inside the setTimeout would emit `TypeError: Cannot
        # set properties of null` at t≈1500ms and land here.
        assert not page_errors, (
            f"page errors during copy-button async flow — the "
            f"R1 F4 Cannot-set-null bug may have regressed: "
            f"{page_errors}")
    finally:
        page.remove_listener("pageerror", _capture_error)


def test_iframe_sizing_floor_400px(page, dashboard_fleet):
    """r14 §M2 pin: the iframe wrapper AND the iframe itself
    RENDER at least 400px tall so the sandboxed HTML preview has
    usable vertical space. Plan C amends the flex chain for
    responsive behavior; B2 alone ships this floor.

    Rendered-pixel primary + CSS-rule diagnostic (2026-09-10
    Codex R2 F3): the plan's contract is `iframe.getBoundingClientRect().height >= 400`,
    not `getComputedStyle().minHeight == "400px"`. A CSS
    `min-height: 400px` rule can be superseded when the
    surrounding layout has `overflow: hidden` or a smaller
    `flex-basis` — the rule is still declared, but the rendered
    pixels are fewer. Bounding-box assertions are the truthful
    signal; computed-style checks remain as a clearer signal
    when the failure mode is "someone dropped the CSS rule
    entirely" rather than "layout collapsed the container."
    """
    _click_file_via_repo_view(
        page, dashboard_fleet, "blueprints/plain.html")

    # ── Primary: rendered pixel heights (getBoundingClientRect) ──
    wrapper_rendered = page.evaluate("""
        () => document.querySelector(".repo-iframe-wrapper")
                .getBoundingClientRect().height
    """)
    iframe_rendered = page.evaluate("""
        () => document.querySelector(".repo-iframe")
                .getBoundingClientRect().height
    """)
    assert wrapper_rendered >= 400, (
        f"iframe wrapper rendered height {wrapper_rendered}px "
        f"< 400px floor — layout may have collapsed the "
        f"container even though the CSS rule is intact")
    assert iframe_rendered >= 400, (
        f"iframe rendered height {iframe_rendered}px < 400px "
        f"floor")

    # ── Diagnostic: computed-style min-height CSS rule ──
    # A regression that DROPS the rule (not one that renders it
    # smaller through layout) fails here with a clearer message.
    wrapper_min = page.evaluate("""
        () => window.getComputedStyle(
            document.querySelector(".repo-iframe-wrapper")).minHeight
    """)
    iframe_min = page.evaluate("""
        () => window.getComputedStyle(
            document.querySelector(".repo-iframe")).minHeight
    """)
    assert wrapper_min == "400px", (
        f"iframe wrapper min-height CSS rule regressed; "
        f"got {wrapper_min!r}")
    assert iframe_min == "400px", (
        f"iframe min-height CSS rule regressed; got {iframe_min!r}")
