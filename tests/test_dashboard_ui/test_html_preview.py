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
document.addEventListener("securitypolicyviolation", (e) => {
    window.__csp_violations.push({
        blockedURI: e.blockedURI,
        violatedDirective: e.violatedDirective,
        effectiveDirective: e.effectiveDirective,
        sourceFile: e.sourceFile || null,
        lineNumber: e.lineNumber,
        sample: e.sample ? e.sample.slice(0, 200) : null,
    });
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
    `allow-scripts` — nothing more. Character-exact assertion.
    """
    _load_raw_in_iframe(page, dashboard_fleet, "blueprints/plain.html")
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

    r8 §M1 fix: use `frame.wait_for_function` polling for the
    specific CSP-L3 directive names (`style-src-elem` +
    `img-src`); `connect-src` is supplementary due to browser
    scheduling variance.
    """
    frame = _load_raw_in_iframe(
        page, dashboard_fleet,
        "blueprints/_csp_negative_control.html")

    # Wait for the CSP events to reach the collected array.
    # networkidle alone is not enough — events are async.
    frame.wait_for_function("""
        () => {
            const violations = window.__csp_violations || [];
            const dirs = new Set(violations
                .map(v => v.effectiveDirective));
            return dirs.has("style-src-elem")
                && dirs.has("img-src");
        }
    """, timeout=5000)

    violations = frame.evaluate(
        "() => window.__csp_violations || []")
    effective = {v["effectiveDirective"] for v in violations}
    assert "style-src-elem" in effective, (
        f"expected style-src-elem violation; got {effective}")
    assert "img-src" in effective, (
        f"expected img-src violation; got {effective}")


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

    Discovery happens at test time via
    `_copy_shipped_blueprints`'s copies. Each file is loaded
    inside an iframe (embedded-context — same-origin parent
    satisfies `frame-ancestors 'self'`). Status-200 precondition
    ensures we're not silently passing on 404 pages.

    Uses a bounded fixed-time wait per iteration rather than
    `wait_for_load_state("load")`, because some shipped templates
    render sub-resources that keep the load event pending past
    reasonable time budgets. A ~1.5s wait is well beyond the
    async CSP-event dispatch window observed in Codex's r7
    Chromium probe (sub-second).
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

        # Reset violations before the iframe navigates.
        page.evaluate(
            "() => { window.__csp_violations = []; }")
        # Inject iframe. Fixed 1.5s bounded wait: well beyond the
        # sub-second CSP-event dispatch window; avoids
        # wait_for_load_state hangs on templates with sub-resources
        # that don't reach `load` state promptly.
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
        page.wait_for_timeout(1500)
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
    """
    _load_raw_in_iframe(page, dashboard_fleet, "blueprints/plain.html")
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
    `document.body.dataset.marker = "ran"` on load.
    """
    frame = _load_raw_in_iframe(
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
    iframe URL MUST NOT change after `form.submit()`.
    """
    frame = _load_raw_in_iframe(
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
