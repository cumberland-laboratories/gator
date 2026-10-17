---
date: 2026-10-16
type: implementation-sketch
issue: 80
feature: dashboard-workspace-tabs-and-browser-identity
recommended-path: title-slice-then-shell-state-foundation
---

# #80 — Dashboard Workspace Tabs and Browser-Tab Identity

## Executive Summary

- Dashboard is one local server that serves many independent browser documents.
  Its workspace strip should improve navigation inside one browser document;
  it must not replace URLs, browser history, bookmarks, or normal browser tabs.
- Make browser tabs identifiable first with titles such as `Gator · Odyssey ·
  Loop`. This is independently valuable, low-risk, and validates the selected
  repository/view naming model.
- Then add a full-width strip above the sidebar and main pane. Every item is
  the same kind of Dashboard context: it optionally selects a repository and
  remembers its last view. There is no special Fleet tab.
- Keep only the active context authoritative in the URL. Persist inactive
  context tabs only as a versioned, per-browser-tab convenience cache, with
  safe validation and graceful loss when a repository is no longer registered.

## Goal

Let an Architect hold several deliberately chosen Dashboard contexts in one
window without repeatedly traversing Fleet:

```text
Gator | — | Odyssey × | Gator × | Databricks Admin × | +
----------------------------------------------------------------------
sidebar for selected context                              main content
Fleet | Commits | Loop | Docs | Updates                   Loop, Docs, etc.
```

The selected top tab controls both the sidebar context and main content. A
repository tab can return to its own useful place, for example Odyssey Loop or
Gator Docs. An unselected `—` tab can show Welcome or Fleet. Browser tabs
remain available for genuinely parallel attention and may each host their own
workspace strip.

## Current Foundation

`dashboard.js` already has the right boundary for the active view:

- `activeRepo`, `activeRepoKey`, and `activeView` are browser-document state.
- `navigate()` and `showView()` centralize dashboard navigation.
- Shell history entries carry `{gatorDashboard, view, repo, repoKey, sub}`;
  Loop substate is deliberately bounded and contains no token, prompt text, or
  artifact content.
- `popstate` validates a history entry, rehydrates the repository from the
  live Fleet data, and falls back safely if a repository is no longer
  registered.
- A direct `?repo=<name>` URL establishes repository context. A normal
  browser tab therefore already has independent selected-repository state even
  though all tabs use the same server and port.

The workspace feature must extend this shell rather than create a competing
router. In particular, it must preserve the #70 navigation-during-load guard:
a user action while `/api/data` is loading must still win rather than being
overwritten by the landing view.

## Core Model

### Workspace context

Use a small, serializable internal object:

```text
WorkspaceContext
  id: opaque client-generated identifier
  repo: null | registered repository display name
  repoKey: null | stable registered repository key
  view: one allowed Dashboard view
  sub: null | bounded view-specific state already accepted by the shell
```

Interpretation:

- `repo != null` labels the tab with the repository display name.
- `repo == null` labels it `—` (or a subtle Gator mark). Welcome and Fleet are
  ordinary views in such a context; neither is a privileged workspace type.
- `view` and `sub` are the last location to restore for that context.

The browser document holds:

```text
WorkspaceState
  contexts: ordered WorkspaceContext[]
  activeId: id
```

Only the selected context is rendered. Switching context tears down the
previous view through its existing teardown contract before mounting the next
one. This is essential for Loop polling, timers, event listeners, and
in-flight-response guards: inactive top tabs are remembered navigation state,
not hidden live copies of the Dashboard DOM.

### One context per repository: recommended initial rule

Initially, opening a repository that already has a workspace context in this
browser document selects that context instead of creating a duplicate. This
keeps labels unambiguous and makes the strip a compact set of places, not an
IDE tab system. A user who deliberately needs two simultaneous views of the
same repository can use a separate normal browser tab.

This is an implementation recommendation, not a governance boundary. It can
be relaxed later only if the product demonstrates a real need for duplicate
same-repository workspace contexts and supplies distinguishable labels.

## URL, History, and Storage Contract

### Active context: URL and normal history

The currently visible context is authoritative in the URL and browser history.
Selecting a top tab must use the same shell-owned navigation path as a sidebar
click, updating the URL to the selected repository/view and pushing or
replacing a normal browser-history entry according to the existing action.

Direct load, reload, duplicated browser tab, and Back/Forward must therefore
always restore an honest active Dashboard state without needing any private
workspace cache. The implementation should make the active view explicit in
the URL as part of this work rather than relying on a blank-title history state
alone. Preserve compatibility with existing `?repo=<name>` links.

### Inactive contexts: session-scoped convenience cache

Use versioned `sessionStorage`, not `localStorage`, for the optional
non-active context list. `sessionStorage` belongs to one browser tab, avoiding
an accidental merge of workspace strips across unrelated tabs that share the
same `127.0.0.1` origin. Store only the bounded context metadata above:

- no auth tokens, Loop prompts, artifact contents, filesystem paths, or API
  responses;
- a size and count limit; and
- schema version plus defensive parsing.

On load, hydrate the URL-selected active context first. Then validate cached
inactive contexts against the current registered-repository list. Drop invalid
records quietly; if the active URL refers to an unregistered repository, use
the existing visible Fleet notice and no-repository context fallback.

The product must remain correct if storage is blocked, corrupt, deleted, or
not restored by the browser. In that case, show one context derived from the
URL and let the Architect open more.

## Full-Width Shell Layout

### Placement

Add one `role="tablist"` strip across the entire Dashboard shell, above the
existing left navigation/sidebar and content region. It is not part of a view
module, and it is not the Loop Create/History subnavigation. The hierarchy is:

```text
Dashboard shell
  Workspace strip (cross-repository navigation)
  Existing shell body
    Global/sidebar navigation (views in selected context)
    View slot (selected context and selected view)
```

This placement makes the mental model visible: top tabs are places the
Architect has open; sidebar items are activities in the selected place.

### Interaction

- The active tab uses native button semantics with `role="tab"`,
  `aria-selected`, roving `tabindex`, and arrow/Home/End keyboard support.
- `+` creates and selects a no-repository `—` context. It is not a repository
  picker disguised as a tab; the normal sidebar/Fleet workflow remains usable.
- Selecting a repository from Fleet in the current context turns that context
  into the selected repository context. Fleet also gains separate actions to
  open the repository in a new Dashboard context or a new browser tab.
- A close button is separately focusable and labelled, for example `Close
  Odyssey workspace`. It changes only navigation state.
- On a narrow viewport, preserve the existing usable content minimums. The
  strip should horizontally scroll or use an overflow menu; it must not wrap
  into a multi-row control that displaces the current view unpredictably.
- An active Loop indicator is a small non-authoritative badge on its repository
  tab. It links to/opens the ordinary Loop view, never creates a fleet-wide
  blended Loop workspace.

### Document title

Centralize title generation in one shell function. The title follows the
selected context and visible view, for example:

```text
Gator · Odyssey · Loop
Gator · gator-command · Docs
Gator · Fleet
Gator · Welcome
```

Call it after every successful shell navigation, active-context selection,
initial load, and `popstate` restoration. Never set the title from repository
content or a user-controlled file path.

## Delivery Plan

### Slice A — Browser-tab identity

1. Add the centralized safe title formatter and apply it across initial load,
   normal navigation, and Back/Forward restoration.
2. Add focused browser tests for selected repo/view titles and unselected Fleet
   and Welcome titles.
3. Verify two normal browser tabs with different URLs display different titles
   while talking to the same Dashboard server.

This slice can ship independently. It directly solves the immediate problem of
recognizing several Gator tabs in the browser strip.

### Slice B — Context state foundation and strip shell

1. Extract the current single active-context state into a small shell-owned
   context adapter without changing visible behavior.
2. Add the full-width strip and a single initial context derived from the URL.
3. Add `+`, select, and close behavior with session-scoped cache validation.
4. Refactor sidebar/Fleet navigation to mutate the active context through the
   one shell owner, preserving the existing URL/history behavior.

Ship this slice with no duplicate-repository contexts, no drag reordering, and
no special Fleet type.

### Slice C — Cross-context opening affordances

1. Add accessible Fleet actions: open in current context, new Dashboard
   context, and new browser tab.
2. Add active-Loop badges when the required data is already available; do not
   add a second polling mechanism just for the strip.
3. Decide whether newly opened contexts inherit a view or always begin at Repo
   overview. Default to a clear, predictable repository overview.

### Follow-on, explicitly separate — document discovery

Cross-repository workspace tabs retain a document once found. They do not
solve discovery of an excellent narrative HTML artifact whose repository is
forgotten. Treat fleet-wide document search/command-palette work as a companion
issue: it should return repository, logical path, document title, metadata, and
excerpt, then open a result in the current context, a new Dashboard context, or
a new browser tab. Do not make that search index a prerequisite for #80.

## Test Strategy

Add focused Playwright coverage before broad migration:

1. Title updates for Welcome, Fleet, selected repository Docs, and Loop.
2. Create an unselected context; select a repository; then close it without
   mutating registry state or ending its active Loop.
3. Switch between two contexts with different views and confirm each restores
   its own sidebar selection and view-specific bounded substate.
4. Confirm only the active Loop context polls; switch away and verify its
   teardown clears its timer; switch back and verify one polling interval
   resumes.
5. Back/Forward, reload, direct URL, and browser-tab duplication restore the
   URL-selected active context without relying on `sessionStorage`.
6. Corrupt, unavailable, oversized, and stale session cache records fall back
   safely.
7. A repository removed from the registry while cached in a context yields the
   existing honest fallback, never a cross-repository substitution.
8. Narrow viewport keyboard, focus, overflow, and close-button behavior.
9. Two browser pages connected to the same fixture server retain distinct URLs,
   titles, and selected repository views.

## Non-goals

- A special Fleet workspace type.
- A second Dashboard process, port, or server session for each top tab.
- Replacing normal browser tabs or browser history.
- A full IDE/editor tab model, arbitrary browser, or per-tab Git worktree
  selector.
- Merging Loop state from separate repositories into a controller workspace.
- Fleet-wide document search in this implementation increment.

## Likely Files

- `src/gator_command/scripts/dashboard/dashboard.html` — shell strip mount.
- `src/gator_command/scripts/dashboard/dashboard.css` — full-width strip,
  responsive overflow, focus, and badge styling.
- `src/gator_command/scripts/dashboard/dashboard.js` — shell-owned workspace
  state, URL/history bridge, title function, and sidebar dispatch.
- `src/gator_command/scripts/dashboard/views/fleet.js` — explicit open-current,
  open-new-context, and open-new-browser-tab actions.
- `tests/test_dashboard_ui/` — focused shell, history, Fleet, responsive, and
  Loop-teardown pins.
- `.gator/charters/scripts-dashboard-ui.md` — updated shell and navigation
  invariants when implementation begins.

## Connections

- GitHub issue #80 — approved workspace-tab product direction.
- GitHub issue #79 — one active Loop per repository and parallel operation
  across repositories.
- `.gator/charters/scripts-dashboard-ui.md` — shell history, selected-repo,
  view rendering, and #70 navigation-during-load contracts.
- `src/gator_command/scripts/dashboard/dashboard.js` — present shell owner.
- `src/gator_command/scripts/dashboard/views/fleet.js` — repository entry
  points for context-opening actions.
