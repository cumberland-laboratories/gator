# Implementation Plan: Welcome HTML Documents

## Executive Summary

- Replace the four hand-written Welcome panels with four shipped, standalone placeholder HTML documents (`templates/gator-starter/docs/*.html`). Each is shown in an iframe whose sandbox is exactly `allow-scripts`, loaded lazily under the unchanged #72 tab bar.
- Serving goes through one closed, four-name route, `GET /api/welcome/docs/<name>`. It sends the existing B2 HTML CSP and replaces `/api/welcome/how-gator-works`. The snapshot inlines the four documents as script-safe JSON, each with a CSP `<meta>`, and assigns them through the `iframe.srcdoc` property.
- The Start-a-session document asks the parent for a copy with exactly `{type:"gator-welcome", v:1, action:"copy-session-prompt"}`. The parent checks the frame identity, the `"null"` origin, and the exact message shape, then writes its own `SESSION_PROMPT`. If anything fails, the document shows a manual-copy state beside the visible prompt.
- Main risk: clipboard activation across `postMessage`. A real-clipboard Chromium test proves the success path. The manual state is the honest fallback. Two checkpoints: (1) serving and display, (2) the copy protocol.

## Summary

This plan implements the revised Welcome HTML Documents sketch. Welcome keeps its #72 shell: logo entry, the full-width main-pane tab bar, the four labels, repository independence, and the Dashboard-owned prompt. Each topic body becomes an isolated, shipped HTML document. The work proves the serving, sandbox, snapshot, and bounded copy-action mechanism with placeholder content only. The content pass and any fleet release are later work.

## Context Checked

- Architect brief: none listed by `gator loop status` for this loop.
- Loop `sketch.md`, the scope contract. It differs from `.gator/artifacts/2026-10-10-welcome-html-documents-sketch.md`, and the loop copy governs.
- `.gator/procedures/writing-implementation-plans.md` (planning path, module/checkpoint rules, verification ladder) and `.gator/.includes/reference-notes/loop-artifact-formats.md`.
- Charters: `.gator/charters/INDEX.md`. `scripts-cross-cutting.md`: Package surface, the `templates/**/*` package-data glob, and the runtime-read-of-a-starter-template note. `scripts-dashboard.md`: `read_welcome_doc()` / route TRIPWIRE, `apply_response_headers()` / `apply_html_csp_headers()`, `is_browsable()` / `content_policy.py`, and `build_snapshot()` TRIPWIREs. `scripts-dashboard-ui.md`: the Welcome entry and its `SESSION_PROMPT` TRIPWIRE, plus `buildRawUrl()` / `bindHtmlPreviewControls()` (sandbox exactly `allow-scripts`).
- Code: `src/gator_command/scripts/dashboard/views/welcome.js` (whole file). `dashboard/helpers.py` (`WELCOME_DOC_PATH`, `read_welcome_doc`). `dashboard/snapshot.py` (`_json_script`, `build_snapshot`). `dashboard/content_policy.py`. `gator-dashboard.py`: `_B2_CSP_*`, `apply_html_csp_headers`, the `_handle_raw` HTML branch, `do_GET` path normalization (`self.path.split("?")[0].rstrip("/")`), and the current Welcome route. `dashboard/views/repo.js` `loadFile()` HTML iframe branch.
- Shipping: `gatorize.py` `action_install_gator()` copies `TEMPLATES/docs` wholesale into `.gator/docs/` through `copy_tree_overlay`. `gator-update.py` `USER_TEMPLATE_DIRS["docs"]` with `_plan_dir_overlay()` plans top-level docs files. `pyproject.toml` `[tool.setuptools.package-data]` `templates/**/*`. `templates/gator-starter/docs/` currently holds four `.md` files.
- Reference: `templates/gator-starter/reference-notes/cumberland-html-document-template.html`. It is self-contained, with no external links, fonts, or scripts.
- Tests: `tests/test_dashboard_ui/test_welcome_ui.py` (all current pins), `tests/test_snapshot.py`, `tests/test_packaging.py` (`built_wheel`, `test_wheel_has_templates`), `tests/test_layout.py` (`v2_repo`, `plan_updates` routing tests), `tests/test_gatorize.py` (`action_install_gator` usage), and `test_html_preview.py` as the existing B2 CSP pin.

## Approach

**Planning path: full planning loop.** This is the sketch's recommendation. The change crosses a content-serving boundary and an iframe trust boundary, adds a cross-frame message protocol, and changes what starter templates ship.

**Module map (four responsibilities, two checkpoints).**

1. **Shipped Welcome documents.** Four standalone placeholder HTML files are the content contract.
   - Invariant: no external resource, request, or telemetry. Diagrams carry text equivalents. The session document shows the exact prompt, and no `.includes` path appears anywhere.
   - Shipping needs no installer code. The existing `templates/**/*` package glob, the `gatorize` docs overlay, and `gator update`'s `USER_TEMPLATE_DIRS["docs"]` already deliver every top-level file in `docs/`. Tests pin that delivery so a future change cannot silently break it.
2. **Allowlisted serving and snapshot embedding** (server side of the trust boundary).
   - Invariant: request input selects only one of four fixed names. Each response carries the B2 HTML CSP. Snapshot text cannot escape its inline script, and each snapshot document carries an equivalent CSP `<meta>`.
3. **Welcome frame host** (`welcome.js`).
   - Invariant: Welcome inserts no document HTML into the Dashboard DOM. The sandbox is exactly `allow-scripts`. Frames load lazily, stay mounted for the life of the view, and keep the #72 tab, keyboard, and focus contract unchanged.
4. **Copy-action protocol** (parent listener plus in-document script).
   - Invariant: one exact message from the current session frame causes one clipboard write of the Dashboard constant. Everything else has no effect. The document never claims a copy it did not get confirmed.

Modules 1–3 are checkpoint 1, because together they form the first working increment: the Welcome workspace renders four shipped, sandboxed documents live and in a snapshot. Module 4 is checkpoint 2. This matches the sketch's delivery guidance: (1) serving, snapshot, and placeholder documents, then (2) the bounded copy protocol and fallback.

**Key design decisions.**

- **Route shape:** `GET /api/welcome/docs/<name>`, where `<name>` must be exactly one of `how-gator-works.html`, `what-gator-can-do.html`, `gatorize-a-repo.html`, `start-a-session.html`.
  - The handler takes `<name>` from the already-normalized `path` and tests membership in a closed `frozenset`. It never joins request text onto a filesystem path. The file path comes from the matched constant.
  - Percent-encoded, cased, traversal, extra-segment, and `.md` variants are not members, so they get 404. The query string is already stripped by `do_GET` and cannot select anything.
  - The old `/api/welcome/how-gator-works` route is deleted, so it falls through to the default 404.
- **Response headers:** `apply_response_headers(handler, "text/html; charset=utf-8", len(body), cache_control="no-cache")` (`nosniff` included), plus one `Content-Security-Policy: _B2_CSP_EXTERNAL`.
  - `_B2_CSP_EXTERNAL` is the existing B2 policy with `sandbox allow-scripts;` prepended. Inside the already-sandboxed iframe the extra token changes nothing. If someone opens the route top-level, it keeps the document opaque-origin. One fixed policy also removes the need for `Vary: Sec-Fetch-Dest`.
  - `frame-ancestors 'self'` is kept. Nothing is relaxed.
  - Rejected alternative: a new Welcome-specific CSP (for example, dropping `'self'` from `img-src`). That would be a second policy to maintain. The no-request guarantee is pinned by the documents' content tests and by Playwright request capture instead.
- **Error body:** a known name whose file cannot be read, or an unknown name under the prefix, returns a minimal `text/plain; charset=utf-8` 404 (`nosniff`): "This Welcome document is not available." The iframe can only show the response body, and a JSON error would render as raw JSON.
- **One CSP source of truth:**
  - The B2 directive string moves verbatim from `gator-dashboard.py` into `dashboard/content_policy.py` (its existing "shared content-transport policy" home) as `HTML_CSP_DIRECTIVES`. `gator-dashboard.py` keeps `_B2_CSP_DIRECTIVES = HTML_CSP_DIRECTIVES`, so the `_B2_CSP_EMBEDDED` / `_B2_CSP_EXTERNAL` derivations and the B2 seam stay byte-identical. The existing `test_html_preview.py` header pins guard this.
  - `content_policy.html_csp_meta_policy()` returns the same directives without `frame-ancestors`, because browsers ignore that directive in `<meta>`. The snapshot uses it.
- **Snapshot embedding:** `window.GATOR_WELCOME_DOCS = {<name>: text-or-null, ...}` in the existing data block.
  - Each text gets one CSP `<meta http-equiv="Content-Security-Policy" content="…">` inserted immediately after the first `<head…>` tag (case-insensitive `<head(\s[^>]*)?>`). A document without a `<head>` becomes `null`, never an unprotected document.
  - `_json_script()` is hardened to escape every `<`, `>`, `&` as `<` / `>` / `&` (non-ASCII, including U+2028/2029, is already `\uXXXX` under `json.dumps` defaults). Neither `</script>` nor `<!--` can appear in the inline script.
  - `welcome.js` assigns each text through the `iframe.srcdoc` DOM property. The document never passes through an HTML attribute string, so attribute escaping cannot fail.
  - `window.GATOR_WELCOME_DOC` (singular) is removed.
- **Frame host:** a per-topic iframe with `sandbox="allow-scripts"`, `title` set to the tab label, and class `welcome-frame`. It is created on first selection of its topic in a mount, with `src = "/api/welcome/docs/" + name`, or `srcdoc` in a snapshot.
  - It is never re-created or re-pointed while the mount lives, so returning to a topic does not reload it.
  - A snapshot entry that is `null` renders a `textContent` notice instead of a frame.
  - Welcome no longer needs `GatorLoopMarkdown`, the `howDoc` cache, `PANELS`, `DOCS` links, or the "next" buttons. Documents are not navigation controllers.
- **Copy protocol (parent):** `welcome.js` keeps `SESSION_PROMPT` and the Clipboard API check.
  - On each mount it removes any previous `message` listener and installs one bound to that mount.
  - The listener first drops itself if its root is detached.
  - It acts only when all of these hold: `event.source === <this mount's session iframe>.contentWindow`, with the frame connected; `event.origin === "null"`; and `isCopyRequest(event.data)`. `isCopyRequest` requires a non-null object whose prototype is `Object.prototype`, exactly three own keys, `type === "gator-welcome"`, `v === 1` (number), and `action === "copy-session-prompt"`.
  - It then calls `navigator.clipboard.writeText(SESSION_PROMPT)` and replies only to `event.source` with `{type:"gator-welcome", v:1, action:"copy-session-prompt-result", ok:true}`, or `ok:false` with `reason` set to `"unavailable"` (no Clipboard API) or `"denied"` (rejected).
  - `targetOrigin` is `"*"`: an opaque origin cannot be named, and the reply carries no secret.
  - Anything else returns before any side effect: no write, reply, focus, topic, history, or network change.
- **Copy protocol (document):** an inline script in `start-a-session.html` (allowed by the B2 `script-src 'unsafe-inline'`).
  - The button posts the request to `window.parent` (`"*"`) and arms a 1500 ms timer.
  - It accepts only a reply whose `event.source === window.parent` and whose data is a plain object with exactly the result shape. `ok:true` sets the polite live region to "Copied".
  - Every other outcome shows a manual-copy instruction next to the visible prompt and selects the prompt text inside the document with a `Range`. This covers `ok:false`, the timeout, and no parent (`window.parent === window`: opened directly). The instruction reads, for example: "Copy did not work here. Select the prompt above and copy it." It is announced, and "Copied" is never shown.
  - The same manual state applies in the Docs HTML preview, where no Welcome listener exists.

**Simplicity boundary.**
- No new framework, message bus, auto-height channel, deep link, or Docs-view change.
- No new server policy beyond the four-name set.
- No Markdown complements for the three new topics. The sketch asks for none, and `how-gator-works.md` stays as it is.
- No change to `gatorize.py` or `gator-update.py`.

## Changes

Changes are ordered by dependency.

### 1. Four placeholder documents (checkpoint 1)
- Files: `src/gator_command/templates/gator-starter/docs/how-gator-works.html`, `what-gator-can-do.html`, `gatorize-a-repo.html`, `start-a-session.html` (new).
- What: each is `<!doctype html>`, `lang="en"`, `<head>` with `charset`, `viewport`, a `<title>` that matches the tab label, and an inline `<style>` drawn from the Cumberland master (neutral scale plus one accent; no font imports). The body is short, direct STE-style prose.
  - `how`: one small inline SVG (charter → change → commit evidence) with `role="img"`, `<title>`, `<desc>`, and an adjacent text paragraph that says the same thing.
  - `can`: the four capabilities from today's panel.
  - `gatorize`: `gator gatorize <target-directory>` as a code sample, and the statement that `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` stay as they are and belong to the repository.
  - `session`: the steps (paste the prompt; the agent runs `gator init`; that output names the resolved `GATOR_INIT.md` and the required reads; the agent completes them before substantive work). The exact one-line prompt goes in `<pre id="session-prompt">`, then a static manual-copy line. Checkpoint 2 adds the button, live region, and script.
  - No meaning is carried by colour alone. No external links (an outward link would only fail inside the sandbox without popups), no `<link>`, `<script src>`, `@import`, `<img>`, `<iframe>`, `<object>`, or URL other than the SVG `xmlns`.
- Why: Scope §Content and shipping model. The release is held (see Risks).

### 2. CSP source of truth (checkpoint 1)
- Files: `dashboard/content_policy.py` and `gator-dashboard.py`.
- What: move the directive string verbatim to `HTML_CSP_DIRECTIVES` and add `html_csp_meta_policy()`. In `gator-dashboard.py`, import it and keep `_B2_CSP_DIRECTIVES = HTML_CSP_DIRECTIVES`. Every existing name and header byte stays the same.
- Why: the snapshot meta policy and the served header must not drift.

### 3. Allowlisted reader and route (checkpoint 1)
- Files: `dashboard/helpers.py` and `gator-dashboard.py`.
- What:
  - In `helpers.py`, replace `WELCOME_DOC_PATH` / `read_welcome_doc()` with `WELCOME_DOCS_DIR`, `WELCOME_DOC_NAMES = frozenset({...four names})`, and `read_welcome_html(name)`. It returns `None` unless `name in WELCOME_DOC_NAMES`; otherwise it reads `WELCOME_DOCS_DIR / name` as UTF-8, and returns `None` on `OSError` / `UnicodeDecodeError`.
  - In `do_GET`, replace the `/api/welcome/how-gator-works` branch with a `path.startswith("/api/welcome/docs/")` branch. It serves `read_welcome_html(path[len(prefix):])` with the headers above, or the plain-text 404. The branch never falls through.
- Why: Scope §Serving and isolation, Requirement 2.

### 4. Snapshot embedding (checkpoint 1)
- File: `dashboard/snapshot.py`.
- What: harden `_json_script()`; add `_welcome_docs_for_snapshot()`, which builds `{name: _with_csp_meta(read_welcome_html(name))}` for the four names (`_with_csp_meta` returns `None` for `None` or a document without `<head>`); emit `window.GATOR_WELCOME_DOCS`; drop `GATOR_WELCOME_DOC`. The script-tag regex and inline order are unchanged, because no view file is added.
- Why: Scope §Serving and isolation (snapshot bullet), Requirement 6.

### 5. Frame host (checkpoint 1)
- File: `dashboard/views/welcome.js`.
- What: `TOPICS` gains `doc` (file name) per key.
  - Each tabpanel keeps its #72 id, role, `aria-labelledby`, and `tabindex=0`, and starts empty. `applyTopic()` keeps writing only differing attributes, then calls `ensureFrame(key)` for the selected topic.
  - `ensureFrame()` creates the iframe once per mount: `src` from the route in live mode, or `srcdoc` from `GATOR_WELCOME_DOCS[doc]` when `window.GATOR_SNAPSHOT` is set (a `null` or absent entry gives a `p.welcome-doc-status` text notice naming `.gator/docs/<doc>`).
  - Remove `PANELS`, `DOCS`, `docLink`, `nextButton`, `fetchHowDoc` / `loadHowDoc` / `renderHowDoc`, the parent copy button, and `showCopyFallback`.
  - Keep the tab click and keyboard handlers, the topic state, and `SESSION_PROMPT` (still referenced only by the copy path, which checkpoint 1 leaves unused).
  - Update the module header contract: requests are only the lazily loaded allowlisted documents; no storage, console output, or history calls.
- Why: Scope §Serving and isolation (iframe bullets), Requirement 1.

### 6. Frame styling (checkpoint 1)
- File: `dashboard/dashboard.css`.
- What: add `.welcome-frame { display:block; width:100%; border:0; height:max(480px, calc(100vh - 220px)); }` and a narrow-width rule. Remove the now-dead `.welcome-next*`, `.welcome-copy*`, `.welcome-doc.loop-md`, `.welcome-list`/`.welcome-steps`, `.welcome-heading`, `.welcome-more`, `.welcome-code`/`.welcome-prompt` rules. Keep `.welcome-doc-status` for the snapshot notice. `.welcome-body` and the shared `.gator-tabbar` rules stay unchanged.

### 7. Copy protocol (checkpoint 2)
- Files: `dashboard/views/welcome.js` and `templates/gator-starter/docs/start-a-session.html`.
- What:
  - Parent: add `isCopyRequest()`, `bindCopyListener(mount)` / teardown-on-detach, and `handleCopyRequest()`, as specified in Approach.
  - Document: add `button#copy-session-prompt[type=button]` ("Copy session-opening prompt"), `div#copy-status[role=status][aria-live=polite]`, `p#copy-manual[hidden]`, and the inline script described in Approach (a single pending request, the 1500 ms timeout, strict reply validation, `Range` selection in the manual state).
  - The static manual line from checkpoint 1 becomes the `#copy-manual` fallback.
- Why: Scope §Narrow copy-action protocol and §Start-a-session document, Requirements 3–4.

### 8. Charters and knowledge layer (with each checkpoint)
- Charters are updated right after each code file edit, per the constitution (see Charter Impact).
- `commit_draft.md` collects the change log and the significance steelman.
- `inbox.md` gets one short line: "Welcome placeholder HTML documents are on `dev`; hold any fleet release until the content pass replaces them."

## Dependencies and Ordering

- Change 2 comes before change 3, because the route uses `_B2_CSP_EXTERNAL`, which must stay identical. Change 2 also comes before change 4, which uses `html_csp_meta_policy()`.
- Change 1 comes before changes 3–5: the reader and the tests need the files.
- Changes 3 and 4 come before change 5: the frame host needs the route and the snapshot data.
- Change 6 goes with change 5.
- Checkpoint 1 is complete and working on its own. The session document shows the prompt and a static manual-copy line, so no topic loses function except the one-click copy, which checkpoint 2 restores.
- Change 7 depends on checkpoint 1's frame identity (the session iframe of the current mount).
- Nothing is parallel across checkpoints. Nothing is committed between checkpoints. One normal commit follows final approval.

## Assumptions, Risks, and Required Architect Decisions

Non-blocking assumptions (reversible; the Architect can correct them without pausing):

1. **Only the session frame may request a copy.** The sketch allows "a currently mounted Welcome frame". This plan accepts only the current mount's Start-a-session frame. That is a strict narrowing of the same rule, and no other document has a copy action.
2. **The "clipboard fallback" kept in `welcome.js` is the parent's failure classification.** The parent detects a missing Clipboard API (`unavailable`) or a rejected write (`denied`) and reports it. The visible manual copy moves into the document, beside the already visible prompt. The parent cannot place UI inside the frame, and a second parent-side textarea would duplicate it.
3. **`_B2_CSP_EXTERNAL` serves every request to the Welcome route,** as justified in Approach. The embedded policy plus a sandbox token is no weaker than the embedded policy alone.
4. **`.welcome-body` keeps its 760 px maximum width,** so the documents are designed for that column. The content pass may revisit this.
5. **No `.gator/docs/*.html` copies are committed to this repository in this change.** Gatorize/update delivers them to governed repos, and this repository receives them through its normal `gator update` after release. That avoids a second, drifting copy during the placeholder phase.
6. **The release is held.** No version bump and no CHANGELOG release entry. The inbox line records the hold, as the sketch requires.

Risks:

- **Clipboard user activation across `postMessage`.** Chromium may or may not allow the parent's `writeText` after an in-frame click; HTML user activation does propagate to ancestor documents. The real-clipboard Playwright test decides this. If Chromium denies the write, the shipped behavior is still correct (`ok:false` → manual state), but that test becomes the documented manual-state case and the coding-loop artifact must say so. Other browsers may differ. The manual state covers them honestly.
- **Inline document scripts depend on `script-src 'unsafe-inline'`.** This is the existing B2 allowance. Tightening B2 later would break the in-document copy, so the charter TRIPWIRE names that dependency.
- **The CSP constant move touches the B2 seam.** It is mitigated by moving the text verbatim and by the existing header-byte pins in `test_html_preview.py`.
- **Docs preview of `start-a-session.html` in a governed repo** shows the button. After 1500 ms it falls to the manual state. This is intentional behavior from the sketch.
- **Placeholder documents reach every repo on the next `gator update`** once released. This is why the release is held.

No blocking Architect decision is needed.

## Testing

Focused checks are listed per responsibility. Equivalent rejections are parameterized.

**A. Document contract and delivery:** new `tests/test_welcome_docs.py`.
1. *Standalone and accessible* (parameterized over four documents). Has `<head>` and a `<title>`. No `<link`, `<script src`, `@import`, `<img`, `<iframe`, `<object`, or `http(s)://` except the SVG `xmlns`. Every `<svg` has `role="img"` and a `<title>`. Risk covered: an external request or telemetry, and missing text equivalents.
2. *Session document content.* It contains the exact one-line prompt, which must equal `welcome.js`'s `SESSION_PROMPT` (read from source), and contains no `.includes` and no `GATOR_INIT.md` path prefix. Risk covered: prompt drift and a layout-dependent path.
3. *Delivery.* `gatorize.action_install_gator(tmp)` places all four in `.gator/docs/`. `gator-update` `plan_updates()` on the `v2_repo` fixture plans all four to `.gator/docs/` as `add`. Risk covered: a future installer or update change silently dropping them. This is one test with two assertions, reusing existing fixtures and patterns.

**B. Wheel:** extend `tests/test_packaging.py::test_wheel_has_templates` with the four `templates/gator-starter/docs/*.html` members. Risk covered: the installed runtime cannot show Welcome. Run at final approval (it builds a wheel).

**C. Route:** in `test_welcome_ui.py` (live server via `page.request`), replacing `test_how_gator_works_endpoint_is_fixed`.
1. *Serves the four* (parameterized): status 200, `text/html; charset=utf-8`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy` equal to `_B2_CSP_EXTERNAL`, and a body byte-equal to the shipped file. A query string does not change the body.
2. *Rejects everything else* (parameterized): unknown name, `how-gator-works.md`, `How-Gator-Works.html`, `..%2fREADME.md`, `%2e%2e/`, `how-gator-works.html/extra`, the old `/api/welcome/how-gator-works`, and the bare prefix. Each returns 404 with no shipped-document body.

**D. Snapshot:** `tests/test_snapshot.py`, replacing `test_welcome_doc_inlined_and_script_safe`.
1. `GATOR_WELCOME_DOCS` has exactly the four keys. Each value equals the shipped text with exactly one CSP meta (`html_csp_meta_policy()`) right after `<head>`.
2. *Script safety and no-head fallback* (monkeypatched reader). A document containing `</script><!--<script>` and U+2028 leaves no raw `<` in the inline JSON and round-trips through `json.loads`. A document without `<head>` becomes `null`.

**E. Frames (checkpoint 1):** `tests/test_dashboard_ui/test_welcome_ui.py`.
1. *Lazy, persistent, exactly sandboxed.* On opening Welcome, only `how` has an iframe and only its document is requested. Selecting each tab creates its frame with `sandbox === "allow-scripts"`, the right `title`, and the right `src`.
   - A marker set in a frame through Playwright's frame API survives switching away and back.
   - After visiting all four tabs, the only Welcome-originated requests are the four document GETs, one each. That proves no reload and no extra request.
   - The panel has no `.welcome-doc` / inserted document markup.
2. Existing pins are kept and adjusted to the new panel content: `test_logo_opens_welcome_without_repo_mutation` (its no-request assertion becomes "only the `how` document request"), `test_welcome_tabs_aria_and_keyboard`, `test_welcome_narrow_width`, and `test_welcome_back_forward_and_topic_reset`.
3. Retired: `test_how_gator_works_renders_shipped_doc_once`, `test_how_gator_works_unavailable_is_explained`, and the parent-side `test_welcome_copy_success` / `test_welcome_copy_fallback` (replaced in F).
4. *Snapshot frames.* Load a built snapshot file in Playwright. Selecting the session topic yields an iframe with `sandbox === "allow-scripts"` whose `srcdoc` document contains the CSP meta and the prompt.

**F. Copy protocol (checkpoint 2):** `test_welcome_ui.py`.
1. *Success.* Clipboard permissions are granted. The in-frame button is activated with the keyboard (focus, then Enter). The frame status reads "Copied" (`role=status`, `aria-live=polite`). The parent `navigator.clipboard.readText()` equals `SESSION_PROMPT` exactly, with no newline. The prompt does not appear in history state or storage.
2. *Manual state* (parameterized: parent Clipboard API missing / rejects / document opened top-level at the route). `#copy-manual` is visible, the status announces the manual instruction, and "Copied" never appears.
3. *Ignored messages* (parameterized). A wrapper counts parent `writeText` calls, and frame-side listeners record replies. Cases:
   - from the page itself (`window.postMessage`, non-`"null"` origin);
   - from an injected unrelated sandboxed `srcdoc` frame;
   - from the mounted `how` frame;
   - from a stale session frame (the previous mount's iframe node re-attached after reopening Welcome);
   - `v: 2`;
   - an unknown action;
   - an extra key;
   - an array;
   - a string.

   Each yields zero `writeText` calls, no reply to the sender, an unchanged `selectedTopic` / URL / history length, and no new network request.

**Verification ladder.**
- *Checkpoint 1:* `pytest tests/test_welcome_docs.py tests/test_snapshot.py tests/test_dashboard_ui/test_welcome_ui.py tests/test_dashboard_ui/test_html_preview.py`. The last proves the CSP move left B2 headers byte-identical.
- *Checkpoint 2:* `pytest tests/test_dashboard_ui/test_welcome_ui.py tests/test_welcome_docs.py`.
- *Final approval (once):* `pytest tests/test_dashboard_ui tests/test_snapshot.py tests/test_packaging.py tests/test_layout.py tests/test_gatorize.py`. The full matrix is left to CI.
- *Manual:* the Architect human-checks the source Dashboard on :8422 before any release, as the sketch requires.

## Charter Impact

- `scripts-dashboard.md`:
  - Replace the `read_welcome_doc()` / `WELCOME_DOC_PATH` / `GET /api/welcome/how-gator-works` entry with `read_welcome_html(name)` / `WELCOME_DOC_NAMES` / `GET /api/welcome/docs/<name>`. TRIPWIRE: a closed four-name set, membership test only, no path built from input, `_B2_CSP_EXTERNAL`, `nosniff`, plain-text 404, no fall-through.
  - `apply_response_headers()` / `apply_html_csp_headers()`: note that the Welcome route reuses `_B2_CSP_EXTERNAL` directly, and that the directives now live in `content_policy.HTML_CSP_DIRECTIVES`. Name the in-document copy script's dependency on `'unsafe-inline'`.
  - `content_policy.py` entry: add `HTML_CSP_DIRECTIVES` / `html_csp_meta_policy()`.
  - `build_snapshot()`: `GATOR_WELCOME_DOCS`, the per-document CSP meta (no `<head>` → `null`), and hardened `_json_script()`.
- `scripts-dashboard-ui.md`:
  - Rewrite the Welcome entry: `ensureFrame()`, lazy and persistent frames, `srcdoc` in snapshots, and the removed panel content.
  - Add `isCopyRequest()` / `bindCopyListener()` / `handleCopyRequest()` with TRIPWIREs: sandbox exactly `allow-scripts`; source plus `"null"` origin plus exact shape; reply only to the source with no prompt text; the prompt is never received from or sent to a document.
  - Keep the existing `SESSION_PROMPT` TRIPWIRE.
- `scripts-cross-cutting.md` (Package surface): the runtime-read note now names the four `templates/gator-starter/docs/*.html` files. It also notes that their delivery to repos rides the generic `docs/` overlay in both `gatorize` and `gator update`.
- No new charter. No `INDEX.md` change: every file is already routed. `scripts-installer.md` / `scripts-repo-update.md` stay unchanged because their code does not change.

## Coding Checkpoints

1. **Sandboxed Welcome documents** — ship the four standalone placeholder documents; move the HTML CSP directives to `content_policy` (verbatim); serve the documents through the closed four-name `/api/welcome/docs/<name>` route with `_B2_CSP_EXTERNAL`; embed them in the snapshot as script-safe JSON with a CSP meta; host each in a lazily created, persistent iframe sandboxed exactly `allow-scripts` (`srcdoc` in snapshots); retire the Markdown route, the inline panels, and the parent copy button; update charters and the inbox hold note. Verify: `pytest tests/test_welcome_docs.py tests/test_snapshot.py tests/test_dashboard_ui/test_welcome_ui.py tests/test_dashboard_ui/test_html_preview.py`.
2. **Bounded copy action** — add the parent's exact-message copy listener (current session frame, `"null"` origin, three-key shape, Dashboard-owned prompt, reply to the source only) and the Start-a-session document's button, polite status, 1500 ms timeout, and manual-copy state; update the Welcome charter TRIPWIREs. Verify: `pytest tests/test_dashboard_ui/test_welcome_ui.py tests/test_welcome_docs.py`, then the final-approval suite once: `pytest tests/test_dashboard_ui tests/test_snapshot.py tests/test_packaging.py tests/test_layout.py tests/test_gatorize.py`.
