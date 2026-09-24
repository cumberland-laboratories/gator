# Charter: Dashboard Browser UI

**Covers**: `src/gator_command/scripts/dashboard/dashboard.html`, `src/gator_command/scripts/dashboard/dashboard.css`, `src/gator_command/scripts/dashboard/dashboard.js`, `src/gator_command/scripts/dashboard/views/**`, `src/gator_command/scripts/dashboard/*.png`

## Owns

- The framework-free dashboard shell, navigation, responsive layout, and browser-side routing.
- Fleet, history, repo, audit, loop, updates, and settings views.
- Document browsing, syntax highlighting, cross-document search, and sandboxed HTML preview controls.
- Browser requests to the local dashboard server.

## Does Not Own

- Route authorization, path containment, filesystem access, or data computation; see [`scripts-dashboard.md`](scripts-dashboard.md).
- Governance business rules.
- Cumberland document-template styling; see [`contracts.md`](contracts.md).

---

### navigate() / renderCurrentView()
File: src/gator_command/scripts/dashboard/dashboard.js
Own browser history, selected repository/view state, and dispatch into view modules.
<- sidebar, topbar, URL changes
-> `views/*`
! URL state and visible selection stay synchronized; refresh re-renders the same repo/view rather than silently returning home.

### apiFetch() / mutation requests
File: src/gator_command/scripts/dashboard/dashboard.js
Call same-origin dashboard APIs and normalize errors for views.
<- all view modules
-> Dashboard server
! Every POST includes `X-Gator-Dashboard: 1`. Never add cross-origin fallback behavior.

### renderFleet() / fleet actions
File: src/gator_command/scripts/dashboard/views/fleet.js
Render repository health and expose explicit per-repository actions via a three-dot overflow menu.
<- fleet route
-> repo update/gatorize endpoints, `POST /api/repos/remove`
! The overflow menu carries dual identity: `data-repo-name` for name-addressed Update/Gatorize, `data-repo-path` for path-addressed Remove. Each action dispatches to the correct identity.
! Actions use the repository's stable key, not display text or array position.
! Missing repositories remain representable so users can understand and clean stale registry entries.

### openRemoveConfirmDialog() / remove handler
File: src/gator_command/scripts/dashboard/views/fleet.js
Confirmation dialog for removing a repo from the dashboard registry. Reuses the `.gator-modal` pattern.
<- overflow menu Remove action
-> `POST /api/repos/remove` (path-addressed)
! Registry-only operation — no filesystem access. Dialog text makes this explicit.
! Posts the registered path, not the display name.

### renderHistory()
File: src/gator_command/scripts/dashboard/views/history.js
Render Git-native commit history and Gator trailer attribution.
<- history route
-> repo history endpoint
! Accept both current Architect and legacy PI attribution supplied by the backend.

### renderRepo() / loadFileList() / loadFile()
File: src/gator_command/scripts/dashboard/views/repo.js
Render the repository knowledge browser, fetch canonical listings, and display supported content.
<- repo route and sidebar clicks
-> list/file/raw/search endpoints
! Encode file paths per segment so separators retain namespace meaning.
! Render untrusted text as text or through the syntax renderer; do not interpolate repository content into executable markup.

### buildRawUrl() / bindHtmlPreviewControls()
File: src/gator_command/scripts/dashboard/views/repo.js
Build version-aware raw URLs and wire Copy path, Refresh, and Open externally controls for HTML documents.
<- `loadFile()` HTML branch
-> sandboxed iframe and raw endpoint
! The iframe sandbox is exactly `allow-scripts`; do not add `allow-same-origin`, forms, popups, or top navigation.
! Refresh reissues the request while preserving the selected historical version. External open uses `noopener`.

### renderContentFor() / gatorHighlight()
File: src/gator_command/scripts/dashboard/views/repo.js
File: src/gator_command/scripts/dashboard/views/syntax.js
Select safe Markdown/JSON/code rendering and lightweight syntax highlighting.
<- `loadFile()`
! Highlighting is presentation only and must not reinterpret file bytes as HTML capabilities.

### renderAudit() / showSessionModal()
File: src/gator_command/scripts/dashboard/views/audit.js
Render session evidence and request source-qualified drill-down content.
<- audit/repo session panels
-> audit/session endpoints
! Preserve `source_kind` and repository identity through drill-down; never fetch a same-named file from a different source.

### renderUpdates()
File: src/gator_command/scripts/dashboard/views/updates.js
Render installed/latest version state and request an explicit upgrade.
<- updates route
-> check and upgrade endpoints
! Checking and upgrading are visibly separate actions; failure output remains visible after restart attempts.

### renderLoop() / renderLoopStatus() / renderControls() / renderTimeline() / renderArtifacts()
File: src/gator_command/scripts/dashboard/views/loop.js
Render the governed planning loop workspace: loop list sidebar, status panel, Architect controls, event timeline, and collapsible artifact inspector.
<- loop route
-> loop list/status/events/artifact endpoints, control endpoints (pause/interject/unblock/end) (`/api/repo-by-key/<repo_key>/loops/...`)
! Polls every 3s for non-terminal loops; stops on terminal state. Teardown clears interval via `window._gatorRepoTeardown`.
! Artifact content is escaped through `escHtml()` and rendered in `<pre>` — never interpolated as HTML.
! Active/paused loops sort before terminal loops in the list.
! Architect controls are contextual: active loops show Pause/Interject/End; paused/blocked loops show Unblock/End; terminal loops show no controls. Each button opens an inline input area; Interject requires non-empty message. Controls POST via `postAction()` with anti-CSRF header and re-poll on success. Non-2xx control responses render a `.loop-ctrl-error` message and preserve the input area for retry.
! Executive summary extraction: `extractSummary()` (exposed as `window.GatorViews._extractSummary`) parses `## Executive Summary` headings from plan/findings artifacts (case-insensitive, tolerates leading whitespace, truncated at 500 chars). Summaries render in two locations: (1) inline in the artifact inspector via `.loop-summary-text` / `.loop-summary-absent`; (2) inside timeline event cards for `draft_submitted` and `review_submitted` events via `.loop-timeline-summary-text` / `.loop-timeline-summary-absent`, with a "View full artifact" link that scrolls to and opens the corresponding artifact inspector section. Event-to-artifact mapping uses `_EVENT_ARTIFACT_MAP` with round-aware filenames (`plan.round-{R}.md`, `findings.round-{R}.md`).

### renderSettings()
File: src/gator_command/scripts/dashboard/views/settings.js
Render and update machine-local dashboard preferences exposed by the server.
<- settings route
! Client validation improves feedback but does not replace server-side shape validation.

### responsive shell
File: src/gator_command/scripts/dashboard/dashboard.css
Maintain the sidebar/topbar/content flex chain and usable narrow-screen layout.
<- all views
! Repository content and iframe containers need `min-width: 0`; HTML preview retains a visible minimum height and scrollable overflow.

## Before Changing This Module

- Confirm the backend wire schema and empty/error states.
- Exercise keyboard/mouse navigation and narrow/wide layouts.
- Run Playwright tests for mutations, file browsing, CSP liveness, iframe isolation, and preview controls.
- Keep the UI dependency-free unless the product architecture explicitly changes.

## Connections

-> [Dashboard Server](scripts-dashboard.md) - APIs, security, and content policy
-> [Session Archaeology](scripts-session-archaeology.md) - evidence identity and provenance
-> [Contracts](contracts.md) - Cumberland HTML compatibility
