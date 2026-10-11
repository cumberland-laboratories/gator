---
date: 2026-10-10
type: implementation-sketch
feature: welcome-html-documents
follows: 72
source: .gator/artifacts/2026-10-10-welcome-html-documents-sketch.md
recommended-path: full-planning-loop
---

# Welcome HTML Documents — revised working sketch

## Decision

Keep the Welcome workspace shipped in #72 as the stable Dashboard shell: the
logo opens Welcome, the main-pane tab bar owns navigation, and the Dashboard
owns the one universal session-opening prompt and its clipboard behavior.

The next feature replaces the four hand-written Welcome topic panels with four
self-contained HTML documents in the Cumberland visual grammar. The documents
are shown in sandboxed iframes under the existing, full-width Welcome tab bar.
The first implementation proves the serving, sandbox, snapshot, and one
bounded copy-action path with minimal placeholder content. It does not ship
showpiece copy or elaborate diagrams until the later content pass is ready.

## Existing baseline that must remain true

- The persistent sidebar stays unchanged. Welcome is opened from its logo.
- Welcome's tab bar is in the right main pane, beneath the `Welcome to Gator!`
  header. Its selected-label underline sits above a baseline spanning the full
  main-pane width.
- Loop uses the same main-pane tab grammar for Create / History. This work does
  not move, restyle, or otherwise reopen Loop behavior.
- The Welcome workspace is repository-independent. It does not change active
  repository state or enable Repo, Docs, or Loop.
- The current tab labels are retained:
  **How Gator works**, **What Gator can do**, **Gatorize a repo**, and
  **Start a session with Gator**.

## Content and shipping model

Add one document for each existing topic to the starter-template docs folder:

| Key | Tab label | Shipped document |
|---|---|---|
| `how` | How Gator works | `docs/how-gator-works.html` |
| `can` | What Gator can do | `docs/what-gator-can-do.html` |
| `gatorize` | Gatorize a repo | `docs/gatorize-a-repo.html` |
| `session` | Start a session with Gator | `docs/start-a-session.html` |

The installed wheel reads its package-relative starter-template copies, so the
Dashboard can show Welcome without a selected repository. The same documents
are installed into `.gator/docs/` by gatorize/update alongside their Markdown
complements, where the existing Docs HTML preview can render them.

The HTML documents are standalone: no external stylesheet, font, script,
image, diagram library, request, or telemetry. Each placeholder has a title,
short direct prose, and—where helpful—small inline SVG with a text equivalent.
Markdown complements remain agent-facing and are not a byte-identical source
for the HTML.

Do not release the placeholder documents to the fleet. They may be developed
on `dev`, but the release is held until the content pass makes the shipped
documents suitable for every updated repository.

## Serving and isolation

- Replace the current fixed Markdown JSON route,
  `/api/welcome/how-gator-works`, with a four-name allowlisted HTML route.
  Request input selects only one of the names in the table; unknown values,
  traversal, and arbitrary paths return 404.
- Serve each document with the existing embedded-HTML CSP appropriate for
  sandboxed local documents: no external network/content, inline style and
  script only as required by the document, and no relaxed frame policy.
- Each selected topic loads into an iframe whose sandbox is exactly
  `allow-scripts`. Never add `allow-same-origin`, forms, popups, or top
  navigation. The Dashboard never inserts document HTML into its own DOM.
- Frames load lazily on first selection and remain mounted for the life of the
  Welcome view. Returning to a selected topic does not reload it.
- The offline Dashboard snapshot embeds the four documents as safely escaped
  `srcdoc` values with an equivalent CSP meta policy and the same sandbox.
  Document text must not be able to escape a `srcdoc` attribute or enclosing
  script.

## Start-a-session document and universal prompt

The document visibly presents the exact one-line universal prompt:

```text
Run gator init in this repository. Treat its output, including the required session-opening reads, as binding. Do not provide a substantive response until those reads are complete.
```

It explains the ordinary-session handoff: the agent runs `gator init`; that
output names the resolved `GATOR_INIT.md` and required reads; the agent
completes those reads before substantive work. It must not hard-code a
`.gator/.includes/` path or suggest that Gator owns native agent files.

The copied text remains a Dashboard constant. It is never supplied by,
accepted from, persisted by, logged by, or exposed through a message from the
document.

## Narrow copy-action protocol

The Start-a-session document may show a **Copy session-opening prompt** button,
but the parent Dashboard owns the clipboard write. The only permitted message
is:

```js
{ type: "gator-welcome", v: 1, action: "copy-session-prompt" }
```

The parent accepts it only when all of these hold:

1. `event.source` is the `contentWindow` of a currently mounted Welcome frame.
2. The sandboxed frame has opaque origin (`event.origin === "null"`).
3. The data is a plain object with exactly the three keys and values above.

Everything else is ignored. In particular, documents cannot switch tabs,
change repository context, request an endpoint, or send prompt text.

The parent replies only to the requesting frame with a versioned result object
containing `ok` and, on failure, a small reason such as `unavailable` or
`denied`; it contains no prompt text. The document announces **Copied** through
a polite live region on success.

Clipboard user activation is not assumed to cross the iframe-to-parent
`postMessage` boundary. Chromium/Playwright must prove it works. If the parent
cannot write, or the document receives no reply promptly, the document shows
an honest manual-copy instruction beside the already visible prompt. It never
claims that copying succeeded. This same manual state makes the document useful
when directly opened or viewed in Docs, where no Welcome parent exists.

## Required behavior and verification

1. Each of the four Welcome tabs renders its corresponding shipped document in
   an exactly sandboxed iframe. The current tab keyboard contract, focus
   handling, and full-width tab chrome stay unchanged.
2. The route allows only the four declared names and carries the required CSP.
   It cannot serve arbitrary package or repository files.
3. The copy request copies exactly the Dashboard's one-line universal prompt;
   success and Clipboard-unavailable/manual-copy states are visible and
   announced.
4. Messages from the page, an unrelated frame, a stale frame, an unexpected
   origin, an unknown version/action, or an object with extra keys have no
   effect: no clipboard write, reply, navigation, state change, or API call.
5. The frames make no requests beyond their own allowlisted document loads.
   No Welcome interaction changes repository context or creates/changes
   `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, or any other native agent file.
6. Snapshot output safely embeds each document and preserves the same sandbox
   and CSP behavior.
7. The documents remain readable with colour disabled, have text equivalents
   for diagrams, expose meaningful iframe titles, and allow keyboard access to
   the in-document copy action and its fallback.
8. Wheel/package-data and gatorize/update tests prove all four files are
   available in the installed runtime and delivered to `.gator/docs/` as
   intended.

## Implementation seams

- `templates/gator-starter/docs/*.html`: the four documents and their
  repository-installed copies.
- `dashboard/helpers.py`, `gator-dashboard.py`, and `dashboard/snapshot.py`:
  replace the current one-file Markdown reader/route/snapshot variable with a
  fixed HTML allowlist and safe per-document snapshot data.
- `dashboard/views/welcome.js`: replace string-built topic content with iframe
  hosts; retain topic state, universal-prompt constant, and clipboard fallback;
  add a per-mount message listener and teardown.
- `dashboard/dashboard.css`: Welcome iframe sizing and responsive layout only;
  reuse the existing shared main-pane tab chrome.
- Dashboard server, snapshot, and Playwright Welcome tests; update Dashboard
  and cross-cutting charters in the same implementation change.

## Non-goals

- A model-generated onboarding narrative, remote content, telemetry, or a
  framework dependency.
- Relaxing the existing HTML-preview sandbox/CSP or adding CORS.
- Turning documents into Dashboard navigation controllers.
- Auto-height cross-frame coordination, deep links to individual topics, or
  changing the Loop workspace.
- Per-vendor variants of the universal startup prompt.

## Delivery guidance

This feature crosses a content-serving and iframe trust boundary, and it
changes starter-template shipping behavior. Use a full planning loop. Keep the
first plan separated into: (1) allowlisted serving/snapshot plus placeholder
documents, and (2) the bounded copy protocol and fallback. Human-check the
source Dashboard before release; complete the content pass before any fleet
release.
