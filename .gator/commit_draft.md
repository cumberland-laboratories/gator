---
message: "Welcome: four shipped HTML documents in sandboxed iframes, with a bounded copy action"
change-type: feature
significance: notable
decision-tags: [dashboard, welcome, docs, security]
agent: claude-opus-5-5
architect: Alan Gillette
---

# Session Change Log

- Planning loop `welcome-html-documents-2026-10-11T00-15-22Z` (approved round 1); coding loop `welcome-html-documents-2026-10-11T00-26-12Z`.
- **Checkpoint 1: sandboxed Welcome documents.**
  - Four placeholder documents ship in `templates/gator-starter/docs/`: `how-gator-works.html`, `what-gator-can-do.html`, `gatorize-a-repo.html`, `start-a-session.html`. Each is a filled, cut-down copy of the Cumberland master template: the `CUMBERLAND-NARRATIVE-STYLE` region is byte-identical, the master's meta CSP (`script-src 'none'`) is kept, and no `==TODO==` remains. They load no external resource. The SVG has `role="img"`, `<title>`, `<desc>` and a text equivalent. `gatorize` and `gator update` deliver them through the existing `docs/` overlay, with no installer code change.
  - The HTML CSP directive text moved verbatim to `dashboard/content_policy.HTML_CSP_DIRECTIVES`, with `html_csp_meta_policy()` (no `frame-ancestors`). `gator-dashboard.py` keeps `_B2_CSP_DIRECTIVES` as an alias, so the B2 header bytes are unchanged.
  - Server: `GET /api/welcome/docs/<name>` (`_send_welcome_doc()`, `helpers.read_welcome_html()` / `WELCOME_DOC_NAMES`) serves only the four names. Membership test only; no path is built from input. It sends `text/html; charset=utf-8`, `nosniff`, `no-cache` and `Content-Security-Policy: _B2_CSP_EXTERNAL`. Everything else gets a plain-text 404 and the branch never falls through; encoded separators are already 400 at the shared parser. The JSON `/api/welcome/how-gator-works` route is removed.
  - Snapshot: `window.GATOR_WELCOME_DOCS` replaces `GATOR_WELCOME_DOC`. Each document gets one CSP `<meta>` inserted right after `<head>` (no `<head>` → `null`). `_json_script()` now escapes every `<` `>` `&`.
  - Browser: `welcome.js` replaces the inline panels, the Markdown rendering, the next buttons and the parent copy button with `ensureFrame()`. It creates one `iframe.welcome-frame` per topic on first selection in a mount: `sandbox="allow-scripts"` exactly, `title` = tab label, live `src` or snapshot `srcdoc` property. The frame is never re-created while the mount lives. The tab and keyboard contract, the topic state and `SESSION_PROMPT` are unchanged. `dashboard.css`: `.welcome-frame` sizing; dead Welcome rules removed.
  - Tests: new `tests/test_welcome_docs.py` (Cumberland structure, standalone and accessible, the session prompt equals the Dashboard constant, gatorize/update delivery). `test_snapshot.py` (four documents with CSP meta; script safety; no-head → null). `test_welcome_ui.py` (lazy/persistent/exact-sandbox frames; the four-name route's headers and bodies; rejections; snapshot `srcdoc` frames; repo-context test now allows only the four document GETs). `test_packaging.py::test_wheel_has_templates` (four wheel members). Retired the Markdown-document and parent-copy pins.
  - Charters: `scripts-dashboard.md` (route/reader entry rewritten; CSP source of truth; snapshot), `scripts-dashboard-ui.md` (Welcome entry: frames and sandbox TRIPWIRE; CSS note), `scripts-cross-cutting.md` (runtime read of the four starter documents and their delivery).
  - `inbox.md`: release hold until the content pass replaces the placeholders.
- **Checkpoint 2: bounded copy action.**
  - Parent (`welcome.js`): `bindCopyListener()` installs one `message` listener per mount. It removes the previous one, and removes itself once its root is detached. It acts only when the sender is the current mount's connected Start-a-session iframe (`event.source === frames.session.contentWindow`), `event.origin === "null"`, and `isCopyRequest()` passes: a plain object with exactly `{type:"gator-welcome", v:1, action:"copy-session-prompt"}`. `handleCopyRequest()` writes the Dashboard's own `SESSION_PROMPT`. `replyCopy()` answers only that frame with `{…, action:"copy-session-prompt-result", ok}` plus `reason` (`unavailable` / `denied`) on failure, and never includes the prompt.
  - Document (`start-a-session.html`): adds a `Copy session-opening prompt` button, a polite `role=status` region, a hidden `#copy-manual` line, and an inline script. It posts the exact request, accepts only a strictly shaped reply from `window.parent`, and shows "Copied" only on `ok:true`. A failure, no reply within 1500 ms, or no parent (opened directly, or in the Docs preview) gives the manual state: instruction shown and announced, the prompt selected. Its master meta CSP changes only `script-src 'none'` → `'unsafe-inline'`; the other three documents keep `'none'` and carry no script.
  - Tests: `test_welcome_ui.py`. Real-clipboard success through keyboard activation in Chromium (exact one-line prompt, "Copied" announced, nothing in history or storage). The manual state when the parent's Clipboard API is missing or rejects, and when the document is opened top-level. An ignored-message matrix with a positive control: page, unrelated sandboxed frame, the `how` frame, a stale re-attached session frame, `v:2`, an unknown action, an extra key, an array and a string each cause no write, no reply, no topic/URL/history change and no request. `test_welcome_docs.py`: per-document meta CSP pinned to the master's (only the session document differs, only in `script-src`), and the exact request with the prompt appearing once.
  - Charters: `scripts-dashboard-ui.md` (copy-action bullet and copy-protocol TRIPWIRE).
- **Significance check** (a new iframe trust boundary, a new HTTP route, a cross-frame message protocol, and starter templates that change what every updated repo receives). Steelman against:
  1. Iframes plus `postMessage` add a new attack surface to a local tool whose earlier Welcome made one fixed GET. Any future widening of the accepted message (more actions, prompt text from the document) would let shipped or replaced documents drive the Dashboard.
  2. In-document scripts depend on B2's `script-src 'unsafe-inline'`, which makes that allowance harder to tighten later.
  3. The documents ship into every repo's `.gator/docs/` on update, so placeholder text could reach the fleet. The release hold covers this.
  4. The served policy uses `_B2_CSP_EXTERNAL` rather than the `/raw` Sec-Fetch-Dest split: a second way to apply B2.
  5. Moving the CSP text into `content_policy` touches a seam other code relies on.

  Compatibility: the removed `/api/welcome/how-gator-works` route and the `GATOR_WELCOME_DOC` snapshot global were internal to Welcome. There is no CLI, schema or history change, and B2 header bytes are unchanged.

  Mitigations: a closed four-name route with membership-only lookup; an exact-`allow-scripts` sandbox; the snapshot's injected CSP meta and `<`/`>`/`&`-escaped JSON; one exact message from one frame identity, checked for source, `"null"` origin and shape, with the Dashboard-owned prompt and a reply with no secret; an ignored-message test matrix with a positive control; and charter TRIPWIREs on every invariant.
