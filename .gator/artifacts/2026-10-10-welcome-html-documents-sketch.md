---
date: 2026-10-10
type: implementation-sketch
feature: welcome-html-documents
follows: 72
recommended-path: full-planning-loop
---

# Welcome HTML Documents — the Welcome Workspace as a Showpiece

## Goal

Make the four Welcome topics HTML documents, shown in a sandbox, so that the Welcome workspace can later become Gator's showpiece introduction (Cumberland style, inline SVG diagrams). **This first pass builds the mechanism with placeholder documents.** Showpiece content is a later, separate pass (Architect direction 2026-10-10). The documents are shown in the existing Welcome tab bar. They are isolated from the Dashboard in the same sandbox the Dashboard already uses for repository HTML.

The **Copy session-opening prompt** button lives **inside** the Start-a-session document. The Dashboard still owns the prompt text and does the clipboard write. The document asks for the copy through one checked message channel (option A, Architect decision 2026-10-10).

## Product Rationale

The Welcome workspace (#72, `5c143ae`; Markdown "How Gator works" in `bd2be0d`) introduced the right structure but plain content. Welcome is the first thing a new Architect sees, and HTML with diagrams explains Gator's model (charters, governed sessions, commit evidence, Loop) far better than prose. The Docs view should later move to HTML too. This feature sets the pattern: shipped HTML, sandboxed display, and a narrow, checked channel for the few actions that belong to the Dashboard.

## Scope

### 1. Four HTML documents (placeholders in this pass)

One self-contained HTML document per Welcome topic, in tab order:

| Topic key | Tab label | Document |
|---|---|---|
| `how` | How Gator works | `how-gator-works.html` |
| `can` | What Gator can do | `what-gator-can-do.html` |
| `gatorize` | Gatorize a repo | `gatorize-a-repo.html` |
| `session` | Start a session with Gator | `start-a-session.html` |

- **Placeholder content.** Each document is a short, minimal placeholder in the Cumberland visual grammar. It has a title, one or two sentences, and one small inline-SVG figure with a text equivalent, which proves that diagrams render under the CSP. There is no exact or special content in this pass.
- **The session document is functional:** it carries the real **Copy session-opening prompt** button (Scope 4) and shows the prompt as visible, selectable text.
- **Self-contained:** no external scripts, stylesheets, fonts, images or requests. Each document renders under the CSP in Scope 3. Small inline scripts are allowed only for the message channel (Scope 4).
- **Accessibility and colour, already in the placeholders:** meaning is never carried by colour alone, every figure has a text equivalent, and prose is plain and direct.
- **Standalone and Docs-view behaviour:** each document reads correctly when opened on its own, and in a repository's Docs view (see Scope 2). There is no Welcome channel in those places, so the session document must not wait for a reply forever: if no reply arrives within a short timeout (about 1 s), it shows its manual-copy instructions (the prompt is already visible). It never claims a copy happened.

### 2. Location and shipping (Architect decision 2026-10-10: the simplest option that matches the coming Docs move to HTML)

- **One home: the starter-template `docs/` folder,** next to the Markdown complement: `src/gator_command/templates/gator-starter/docs/<name>.html`.
- **The Dashboard serves Welcome from the package's copy of that folder.** This uses the package-relative pattern already in `bd2be0d` (`templates/gator-starter/docs/`), so Welcome works with no repository selected.
- **Consequence: repositories receive the HTML too.** `docs` is a user-content template directory, so `gatorize` and `gator update` install these files into each repository's `.gator/docs/`, beside `how-gator-works.md`. The Docs view already previews `.html` files there in the same sandbox. This is the intended direction for Docs ("HTML documents with Markdown complements").
- **Release hold (Architect decision 2026-10-10):** once released, the placeholder HTML would land in every updated repository, so **no release ships this feature until the content pass is done.** The work may be committed to `dev`, but not released.
- **Markdown complements stay.** `how-gator-works.md` remains the agent-facing text, maintained separately in this pass, with no drift guard.
- **Retire the Markdown JSON route:** `GET /api/welcome/how-gator-works`, `read_welcome_doc()` and the snapshot's `window.GATOR_WELCOME_DOC` are replaced by the HTML route. The cross-cutting packaging note (a runtime read from `templates/gator-starter/docs/`) is **kept and updated** to name the HTML files.

### 3. Serving and display

- **Route:** a fixed allowlisted route (for example `GET /welcome/<topic>.html` for exactly the four names above) serves the documents with the existing embedded HTML CSP (`apply_html_csp_headers(..., external=False)`: `default-src 'none'`, inline script and style only, `frame-ancestors 'self'`). No request input reaches a filesystem path except through the four-name allowlist. Every other name returns 404.
- **Frame:** each topic panel holds one `<iframe sandbox="allow-scripts">` (exactly that, with **no** `allow-same-origin`, forms, popups or top navigation). It has a `title` naming the topic, and it fills the Welcome pane below the tab bar. The document scrolls inside the frame; there is no auto-height channel.
- **Loading:** frames load lazily when their topic is first selected and are kept for the life of the mount. A tab switch never reloads a frame that is already loaded.
- **Offline snapshot:** the snapshot inlines each document as `srcdoc`, with the same CSP as a `<meta http-equiv>` in the document and the same sandbox. JSON or attribute escaping must make it impossible for document text to break out of the attribute or the script.

### 4. The Welcome message channel (option A)

This is a narrow, versioned, checked protocol between a Welcome document and the Dashboard page.

- **Document → Dashboard:** `parent.postMessage({type: "gator-welcome", v: 1, action: "copy-session-prompt"}, "*")`. That is the **only** action: the Dashboard copies its own `SESSION_PROMPT`. Documents do not switch Welcome tabs (Architect decision 2026-10-10); navigation between topics stays in the native tab bar.
- **Dashboard checks** (all must pass, or the message is ignored silently):
  - `event.source` is the `contentWindow` of a Welcome frame in the currently mounted Welcome view;
  - `event.origin === "null"` (sandboxed origin);
  - the data is a plain object with exactly the keys `type`, `v` and `action`, holding exactly the values above.
- **The prompt text never crosses the channel in either direction.** The Dashboard copies its own constant. A document cannot choose, change or read the copied text. The #72 prompt TRIPWIRE (exact text, one line, no vendor, no layout path, never logged, stored or put in history) stays enforced in `welcome.js`.
- **Dashboard → document:** a reply to that frame only, `{type: "gator-welcome-result", v: 1, action, ok, reason?}`, where `reason` is `"unavailable"` or `"denied"`. The reply carries no prompt text. The document then shows **Copied**, or its own visible manual-copy fallback (the prompt text is already on the page), and announces the result in a `role="status"` live region.
- **User activation:** the copy relies on the click inside the frame activating the parent page. The plan must verify this on Chromium (Playwright). On failure the Dashboard reports `ok: false`, and the document falls back to its visible manual-copy instructions. It never fails silently.
- **Listener lifetime:** one listener per Welcome mount, removed on teardown. No global listener survives navigation away from Welcome.

### 5. Welcome view changes

- The tab bar, ARIA tab contract, keyboard handling, module-local topic state, shell routing, `#brand-home` logo, and "no repository context change" behaviour from #72 are unchanged.
- Each topic panel becomes the frame host. The native copy button and the hand-written panel content in `welcome.js` are removed. The prompt constant and the clipboard and fallback logic stay in `welcome.js` and are driven by the channel.
- **Requests:** Welcome makes only the frame-document GETs for topics the user opens. There is no `/api/` request.

## Out of Scope

- Converting the other Docs content to HTML, or any Docs-view change (a later sketch; the Docs view already previews `.html` files in the same sandbox). Installing the four Welcome documents into repositories happens only as a side effect of Scope 2.
- Showpiece content, real diagrams and final copy (a later content pass).
- Any change to the sandbox flags or CSP of repository HTML preview (`views/repo.js`, `/raw`).
- Auto-sizing frames, cross-document navigation history, or deep links to a Welcome topic.
- External or bundled diagram libraries (Mermaid, D3), web fonts or remote images.
- Per-vendor variants of the session prompt.

## Constraints

- Keep the Dashboard's existing HTML-isolation rules (`scripts-dashboard-ui.md` iframe-sandbox TRIPWIRE; `scripts-dashboard.md` CSP and no-CORS rules). Do **not** add `allow-same-origin` to any Welcome frame, do not relax the embedded CSP, and add no CORS.
- The Dashboard page never inserts document HTML into its own DOM.
- Remove the Markdown JSON route completely rather than leaving dead code. Update the charter entries for it in the same change.
- Do not create, edit, or recommend changing `CLAUDE.md`, `AGENTS.md` or `GEMINI.md`.
- No framework, no new runtime dependency, no telemetry.
- Colourblind-safe by construction (the Architect is colourblind): meaning is never carried by hue alone, in either the documents or the Dashboard chrome.

## Verification

1. All four topics render their shipped HTML document in a frame whose `sandbox` is exactly `allow-scripts`. The served response carries the embedded CSP. Unknown topic names, traversal and query strings return 404 or the same allowlisted file, never another file.
2. **Copy:** clicking **Copy session-opening prompt** inside the document copies exactly the Dashboard's `SESSION_PROMPT`. The document shows **Copied** and announces it. With the Clipboard API missing or rejecting, the document shows its manual-copy fallback and announces that.
3. **Channel checks:** a message from a non-Welcome frame, from the page itself, with extra keys, a wrong `v`, an unknown action, or an unknown topic is ignored (no clipboard write, no reply, no topic change). No message or reply ever contains the prompt text.
4. A document cannot change the selected Welcome tab or any Dashboard state: any message other than the exact copy request (including a `select-topic`-style message) is ignored.
5. **Isolation:** the documents make no network requests beyond their own load, and no Welcome interaction changes repository context or calls `/api/`.
6. **Offline snapshot:** the snapshot renders all four documents via `srcdoc` with the CSP meta and sandbox. Document text cannot break out of the attribute or script.
7. **Standalone and Docs view:** each document opened directly, or previewed in a repository's Docs view, reads correctly. The session document's prompt is visible and selectable, and its copy button falls back to manual instructions after the reply timeout, without claiming a copy.
8. **Accessibility:** every frame has a title, every placeholder figure has a text equivalent, and no meaning is carried by hue alone. Keyboard users can reach and operate the in-document copy button.
9. **Shipping:** the four HTML files ship in the wheel under `templates/gator-starter/docs/`, and a gatorize or update dry run lists them for `.gator/docs/`.
10. **Regression:** existing Welcome routing, tab and history tests are adapted, and the full Dashboard UI suite passes.

## Architect Decisions

Decided 2026-10-10:
- **Content:** placeholders in this pass. Only the session document's copy button and visible prompt are functional.
- **Location:** the starter-template `docs/` folder, next to the Markdown (Scope 2).
- **Markdown complement:** maintained separately, no drift guard (the placeholders make one premature).
- **Channel:** option A. The Dashboard owns the prompt and the clipboard write.

- **Navigation:** documents do not switch Welcome tabs; the channel carries only the copy request.
- **Release:** held until the content pass (Scope 2).

No decisions remain open.

## Likely Implementation Seams

- `src/gator_command/templates/gator-starter/docs/*.html` (new): the four placeholder documents. Also copy them into this repository's own `.gator/docs/` (dogfood), as the starter `how-gator-works.md` already is.
- `gator-dashboard.py`: the allowlisted `/welcome/<topic>.html` route, reusing `apply_response_headers` and `apply_html_csp_headers`. Remove the `/api/welcome/how-gator-works` route.
- `dashboard/helpers.py`: replace `read_welcome_doc()` / `WELCOME_DOC_PATH` with the four-name allowlist and its package-relative directory.
- `dashboard/snapshot.py`: replace the `GATOR_WELCOME_DOC` inline with per-topic `srcdoc` documents (or a JSON map consumed by `welcome.js`).
- `views/welcome.js`: frame hosts, lazy loading, the message listener and checks, copy driven by the channel. Remove the hand-written panels and the native copy button.
- `dashboard.css`: frame sizing in the Welcome pane.
- **Charters:**
  - `scripts-dashboard.md`: the route, with an allowlist TRIPWIRE, and the snapshot.
  - `scripts-dashboard-ui.md`: the Welcome entry, the channel TRIPWIRE, and the sandbox flags.
  - `scripts-cross-cutting.md`: update the runtime starter-template read note to name the HTML files.
  - `scripts-installer.md` / `scripts-repo-update.md`, only if their docs-shipping entries list files.
- **Tests:**
  - `tests/test_dashboard_ui/test_welcome_ui.py`: frames, channel success, rejection matrix (parametrized), copy and fallback, isolation;
  - server tests for the allowlisted route;
  - `tests/test_snapshot.py`: `srcdoc` and escaping.

## Delivery Guidance

This introduces a cross-frame message protocol across a trust boundary, a new served-content route, and content authoring at showpiece quality. Run a full planning loop (per `procedures/writing-implementation-plans.md`). The plan's checkpoints should separate the responsibilities:

1. serving and sandboxed display, with the placeholder documents;
2. the message channel and copy, including the session document's reply timeout and fallback.

The Architect checks Welcome by hand on the source Dashboard (`:8422`) before the final commit. The content pass follows as its own feature.
