---
generated: 2026-06-07
generator: field-guide-gen-v1
type: agent-patterns
language: javascript
source-charters: [scripts-dashboard]
source-file-count: 5
pattern-count: 14
tutorial: javascript-tutorial.md
---

# JavaScript Patterns

### IIFE Encapsulation
Files: dashboard.js, fleet.js, audit.js, repo.js, updates.js
Every file wraps all code in `(function () { "use strict"; ... })();`. No exceptions. Prevents global scope pollution; each file gets a private scope for helpers and state.

### View Registration
Files: fleet.js, audit.js, repo.js, updates.js
Views register as `window.GatorViews.<name> = function (data, container, ...extras)`. Signature: data is the full dashboard JSON, container is the DOM element to fill. repo.js is async (Tier 2 lazy fetch). dashboard.js dispatches to these by name.

### escHtml for All Dynamic Content
Files: fleet.js, audit.js, repo.js, updates.js
All user-provided or server-provided values inserted into HTML must be wrapped in `escHtml()`. Each view file defines its own copy (not shared). Never use template literals with raw data.
! XSS vulnerability if escHtml is omitted on any dynamic value in innerHTML.

### X-Gator-Dashboard Header on POSTs
Files: fleet.js, updates.js
Every `fetch()` call with `method: "POST"` must include `headers: { "X-Gator-Dashboard": "1" }`. The server rejects POSTs without this header (403).
! This is the CSRF trust boundary. Browsers cannot send custom headers on form POSTs or embeds — only explicit fetch with headers, which triggers CORS preflight the server won't answer.

### Snapshot Mode Guard
Files: dashboard.js, fleet.js, repo.js, updates.js
Check `!!window.GATOR_SNAPSHOT` before rendering write controls or making POST calls. Snapshot mode is a static HTML report with no server. All write UI (Update buttons, Pull button) must be suppressed. audit.js has no write controls, so no guard needed.

### Null-Safe Data Extraction
Files: fleet.js, audit.js, repo.js, updates.js
Default to empty array/object when accessing nested server data: `const repos = fleet.repos || [];`, `const summary = fleet.summary || {};`. Never access properties on potentially undefined values without this guard.

### Error Block Early Return
Files: fleet.js, audit.js, repo.js
If server data contains an `error` field, render `<div class="error-block">` and return immediately. Check `data.error` before attempting to render the full view.

### HTML String Building with innerHTML
Files: fleet.js, audit.js, repo.js, updates.js
Build complete HTML as a string, then assign to `container.innerHTML` once. Never incrementally append to DOM. Tables follow: open tags → loop rows → close tags → assign innerHTML.

### Disabled Button During Async
Files: fleet.js, updates.js
Set `btn.disabled = true` and update `btn.textContent` to a progress message before any async operation. Restore both in the `finally` block. Prevents double-click.

### Health Badge Semantics
Files: fleet.js
Only `severity === "drift"` maps to Drifted badge. `severity === "warn"` maps to Healthy. The `driftedCount` summary card must use the same filter. Badge and card must stay in sync.
! Do NOT map warn to Drifted. Charter: "Drifted = Hook present AND policy drift detected" — policy drift only.

### Stale Sources Not Covers
Files: repo.js
When rendering stale charters, iterate `item.stale_sources` (files actually newer than the charter), not `item.covers` (all declared files).
! Using covers overstates staleness when only one file in a multi-file charter is newer.

### parseSummaryLine Priority
Files: fleet.js
Extract summary from gator-update output in fixed order: "Policy version:" → "Done:" → "Everything is current" → "Done" fallback.
! Do not reorder. "Policy version:" is the most informative signal when a bump occurred.

### Timestamp Formatting with Silent Catch
Files: dashboard.js, audit.js, repo.js
All date formatting uses `try { new Date(ts).toLocale...() } catch (_) { return ts; }`. Never let a bad timestamp crash the view — return the raw string as fallback.

### gatorRefreshFleet Guard
Files: fleet.js
After a successful update POST, call `window.gatorRefreshFleet()` to re-fetch Tier 1 data. Always guard with `if (window.gatorRefreshFleet)` — it's set by dashboard.js but fleet.js event handlers shouldn't assume it exists.
