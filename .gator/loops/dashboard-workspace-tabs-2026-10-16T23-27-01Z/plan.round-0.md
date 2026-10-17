# Implementation Plan: #80 Dashboard Workspace Tabs and Browser-Tab Identity

## Executive Summary

- **What:** give every Dashboard browser tab a precise title (`Gator · alpha · Loop`), put the active view in the URL (`?repo=alpha&view=loop`), then add a full-width workspace strip above the sidebar and main pane. Each strip tab is one Dashboard context: an optional repository and its last view. Fleet gains "Open in new workspace tab" and "Open in new browser tab".
- **Key decision:** `dashboard.js` stays the only router. A new shell module, `dashboard/workspace.js`, owns only the context list, its `sessionStorage` cache and the strip DOM. It never renders views and never touches history.
- **Main risk:** history and lifecycle regressions in the shell, especially the #70 rule (a navigation during load wins) and Loop polling teardown on a context switch.
- **Verification:** one new Playwright file, `test_workspace_tabs.py`, with focused tests for each checkpoint. The full `tests/test_dashboard_ui/` suite and `tests/test_snapshot.py` run once, at final approval.

## Summary

The plan delivers sketch Slices A, B and C as five responsibility-based checkpoints. The order is: (1) the title, (2) the URL contract for the active context, (3) the context model and session cache, (4) the strip and context switching, (5) Fleet's cross-context opening actions. The active context is always derived from the shell's existing state (`state.activeView`, `activeRepo`, `activeRepoKey`, Loop `sub`), so there is still exactly one source of truth for what is rendered. Inactive contexts are remembered navigation state, not hidden DOM. No server, registry or Loop API changes.

## Context Checked

- `sketch.md` (this loop). Status lists no Architect brief.
- `.gator/.includes/constitution.md`, `.gator/procedures/writing-implementation-plans.md`, `.gator/.includes/procedures/gator-loop-protocol.md`, `.gator/.includes/reference-notes/loop-artifact-formats.md`.
- `.gator/charters/scripts-cross-cutting.md`: Dashboard assets ship by glob, but every new shell or view script must be added to the `build_snapshot()` script-tag regex and inlined block (`tests/test_snapshot.py`).
- `.gator/charters/scripts-dashboard-ui.md`, read in full. It constrains this work through:
  - `navigate()` / `showView()` / `restoreShellState()`: shell-owned history, the state shape, `cleanSub()`, the landing view and the #70 navigation-during-load guard;
  - the Loop polling-ownership and teardown rules (`ensurePolling`, `teardownLoopView`, `window._gatorRepoTeardown`);
  - the Fleet key-identity rules;
  - the responsive shell and shared tab-bar rules (selection is never shown by colour alone).
- `.gator/charters/INDEX.md`: `src/gator_command/scripts/dashboard/*.js` already maps to the Dashboard Browser UI charter.
- Code:
  - `dashboard/dashboard.js` (whole file);
  - `dashboard/dashboard.html`;
  - `dashboard/views/fleet.js` (whole file);
  - `dashboard.css` (`#app-shell`, `#sidebar`, `#sidebar-toggle`, `#main-shell`, the 768px media block);
  - `views/repo.js` (teardown, its own `pushState` calls including `?repo=&q=`, its scoped `popstate`);
  - `views/loop.js` (`teardownLoopView`, the mount entry point, `restore`);
  - `dashboard/snapshot.py` (`build_snapshot` script inlining);
  - `gator-dashboard.py` `do_GET` (root path strips the query string, so `/?repo=…&view=…` already serves the shell);
  - `dashboard/data.py` (no Loop state in `/api/data`).
- Tests:
  - `tests/test_dashboard_ui/_harness.py` and `conftest.py` (`dashboard_fleet` with `alpha` / `beta`);
  - `test_welcome_ui.py` (#70 test, Back/Forward);
  - `test_loop_workspace.py` (`test_departed_mount_does_not_resurrect_polling`);
  - `test_responsive_shell.py` (`test_desktop_app_shell_bounded_prevents_page_scroll`);
  - `tests/test_snapshot.py` (script-tag pins).

## Approach

**Planning path:** full planning loop. The work adds a new browser-state contract (a versioned `sessionStorage` record), changes the shell's URL contract, and changes a lifecycle invariant (which view is mounted and polling).

**Module map.**

| Module | Purpose and the invariant it owns | Files |
|---|---|---|
| Title formatter | The document title is a pure function of `(activeView, activeRepo)`. It is set in one place and never comes from repository content or file paths. | `dashboard.js` |
| Shell URL contract | The URL names the active context (`repo`, `view`). Landing, reload, direct links and Back/Forward all go through one hydrate → dispatch path. Legacy `?repo=` links keep working. | `dashboard.js` |
| Workspace model and cache | The ordered context list, the one-context-per-repository rule, and a bounded, versioned, defensively parsed `sessionStorage` record. Correct with storage absent. | new `dashboard/workspace.js` (model + storage functions, no DOM) |
| Strip and context switching | The strip DOM, ARIA and keyboard behaviour; select, `+` and close routed through the shell's single navigation path; layout above sidebar and main pane. | `workspace.js` (strip rendering), `dashboard.js` (select/close dispatch), `dashboard.html`, `dashboard.css`, `snapshot.py` |
| Fleet opening actions | Per-repository "open in new workspace tab" and "open in new browser tab", using the repository's stable key. | `views/fleet.js`, `dashboard.js` |

**Key design decisions.**

1. **One router.** `workspace.js` exposes `window.GatorWorkspace` with pure model functions and a strip renderer that takes callbacks (`onSelect(id)`, `onNew()`, `onClose(id)`). Only `dashboard.js` calls `showView`, `pushState` and `replaceState`. A competing router is rejected because the sketch requires extending the shell.
2. **The active context mirrors shell state.** After every `showView()` and every `GatorShell.push/replaceSubState`, `dashboard.js` calls `GatorWorkspace.syncActive({repo, repoKey, view, sub})`. The active context is therefore never a second authority. It is a recorded copy of what is on screen, so inactive contexts can restore it later.
3. **History entries name their context.** The shell state gains an optional `ctx` (an opaque id, `/^[a-z0-9]{1,16}$/`). Selecting a strip tab pushes an ordinary entry. Back returns to the previous context when that `ctx` still exists. Otherwise the entry is applied to the active context. Entries still carry no token, prompt or artifact text.
4. **Inactive contexts are not live.** Switching contexts calls `showView()`, which runs the existing teardown (`window._gatorRepoTeardown`) before mounting. A hidden DOM copy per context is rejected because it would keep Loop and Repo polling and listeners alive.
5. **Manual tab activation.** Arrow, Home and End keys move focus; Enter and Space select. Selecting a tab remounts a view, fetches data and pushes history, so automatic activation on every arrow key would remount and push repeatedly. This differs from Loop's Create/History tabs (automatic activation), which only switch local panels.

**Simplicity boundary.**
- No duplicate same-repository contexts, drag reordering, special Fleet type, per-context Repo file selection, Loop badges, server changes or new polling.
- The only per-context substate is the one the shell already accepts: Loop `sub` via `cleanSub()`.
- Repo-view file selection keeps its existing module behaviour (`_treeState`) and is not part of a context.

## Changes

### 1. Title formatter (Checkpoint 1)
- File: `src/gator_command/scripts/dashboard/dashboard.js`.
- What:
  - Add `TITLE_LABELS` (`welcome: "Welcome"`, `history: "Commits"`; other views use `VIEW_META[view].title`).
  - Add `formatDocumentTitle(view, repo)`, which returns:
    - `Gator · Fleet` and `Gator · Welcome`, which never show a repository;
    - `Gator · <repo> · <Label>` for every other view when a repository is active (for example `Gator · alpha · Docs` and `Gator · alpha · Loop`);
    - `Gator · <Label>` otherwise.
  - Add `updateDocumentTitle()`, which assigns `document.title` (a text property, so there is no markup path). Call it as the last step of every `showView()` branch through a single `finally`-style exit, so landing, `navigate()`, `doRefresh`, the #70 re-render, `restoreShellState()` and its unregistered-repository fallback are all covered.
  - The repository part is the registry display name (`state.activeRepo`), truncated to 60 characters with `…`.
- Why: sketch Slice A. A single point inside `showView()` cannot be missed by a future navigation path.

### 2. Shell URL contract (Checkpoint 2)
- File: `dashboard.js`.
- What:
  - **`shellUrl(view, repo)`** builds the canonical relative URL:
    - `?repo=<enc>` for the Repo view, so existing links are unchanged;
    - `?repo=<enc>&view=<view>` for other repository-context views;
    - `?view=<view>` for views without a repository;
    - an empty search string for Welcome without a repository.
  - **`navigate()`** pushes `history.pushState(shellState(null), "", shellUrl(...))`. `GatorShell.pushSubState` / `replaceSubState` pass the same URL (Loop `sub` stays in state only, never in the URL). In snapshot mode (`window.GATOR_SNAPSHOT`, `file:` URLs), the URL argument is omitted, which keeps today's state-only entries.
  - **`parseShellUrl()`** reads `repo` and `view` from `location.search`. A `view` outside `VIEW_META` is ignored. A missing `view` keeps the legacy meaning: `?repo=` opens Repo; otherwise a snapshot opens Fleet and a live load opens Welcome.
  - **`applyShellEntry(entry)`**, extracted from `restoreShellState()` steps 2–3, hydrates the repository (fleet key match, else name match), or uses the Fleet `.shell-notice` fallback and `clearActiveRepo` when the repository is unregistered. It then dispatches. `restoreShellState()` becomes validate + `applyShellEntry()`.
  - **`init()` landing** builds an entry from `parseShellUrl()` and calls `applyShellEntry()`, then `replaceState(shellState(null), "", shellUrl(...))`.
    - When `history.state` is a valid shell entry for the same view and repository name (reload or duplicated tab), its `repoKey` and `sub` are used. This restores the Loop tab and selection on reload and resolves duplicate repository names.
    - The #70 branch is unchanged: when `viewRenders` changed during `/api/data`, `init()` re-renders the current view and skips landing and `replaceState`.
  - **Behaviour change:** an unregistered `?repo=` on landing now shows Fleet with "That repository is no longer registered." (the sketch's honest fallback). Previously it mounted a Repo view that failed its file fetch.
- Why: the sketch requires that "direct load, reload, duplicated browser tab, and Back/Forward … restore an honest active Dashboard state without needing any private workspace cache", with the view explicit in the URL. `views/repo.js`'s own `?repo=&q=` push is unchanged and remains valid under this contract (no `view` means Repo).

### 3. Workspace model and session cache (Checkpoint 3)
- Files:
  - new `src/gator_command/scripts/dashboard/workspace.js`;
  - `dashboard.html` (script tag before `dashboard.js`);
  - `dashboard/snapshot.py` (inline it, and extend the script-tag regex);
  - `dashboard.js` (calls).
- What: `window.GatorWorkspace` holds the following, with no DOM work:
  - **State:** `{contexts: [{id, repo, repoKey, view, sub}], activeId}`.
  - **Functions:** `newId()`, `syncActive(fields)`, `findByRepo(repo, repoKey)`, `create(fields)`, `remove(id)`, `select(id)`, `neighbourOf(id)`, `load(validateRepo)` and `save()`.
  - **One context per repository:** `findByRepo` matches on `repoKey` when both keys are non-null, otherwise on name. `syncActive` drops any *inactive* context that now holds the same repository as the active one: the active context wins.
  - **Storage:** key `gator.dashboard.workspace` (`sessionStorage` only), value `{"v": 1, "activeId", "contexts": [...]}`.
    - Field rules:
      - `id`: `/^[a-z0-9]{1,16}$/`;
      - `repo`: a string of at most 200 characters, or null;
      - `repoKey`: `/^[A-Za-z0-9_-]{1,128}$/` or null;
      - `view`: a `VIEW_META` key, passed in from the shell;
      - `sub`: through the shell's `cleanSub` (passed in), with `loopId` at most 200 characters.
    - Limits: at most 12 contexts, and at most 16 KB serialized.
    - A wrong version, a parse error, an oversize value or an access that throws gives an empty cache. An invalid record is dropped on its own, quietly.
    - Nothing else is stored: no tokens, prompts, artifact content, filesystem paths or API responses.
    - Every `getItem` / `setItem` is wrapped in try/catch.
  - **Hydration (`load`)** runs after `/api/data` resolves, after the landing or the #70 re-render:
    1. Build the active context from the shell state on screen, not from the URL, so a navigation during load still wins.
    2. Read the cache. Keep a cached context only if `validateRepo(repo, repoKey)` finds it in the current fleet data (repository null always validates).
    3. Merge: if a cached context holds the same repository as the active state (or both have none and it was the cached `activeId`), it becomes the active context and takes the on-screen view. Otherwise the active context is appended.
    4. Save.
- Why: sketch "Inactive contexts: session-scoped convenience cache". `dashboard.js` stays the router. Model functions are separable from the DOM so the cache contract can be tested without the strip.

### 4. Strip, layout and context switching (Checkpoint 4)
- Files: `dashboard.html`, `dashboard.css`, `workspace.js` (`renderStrip(container, callbacks)`), `dashboard.js`.
- **Markup:**
  - `<nav id="workspace-strip" aria-label="Workspaces">` is the first child of `<body>`, before `#app-shell`.
  - Inside it: one `div[role=tablist][aria-label="Open workspaces"]`. Each item is a `div.workspace-item[role=presentation]` containing:
    - `button.workspace-tab[role=tab]` (`id="ws-tab-<id>"`, `aria-selected`, roving `tabindex`, `aria-controls="app-shell"`);
    - `button.workspace-tab-close` (`aria-label="Close alpha workspace"` / `"Close workspace without repository"`, `tabindex` 0 on the active item, otherwise -1).
  - A trailing `button.workspace-new` (`aria-label="New workspace"`, text `+`).
  - `#app-shell` gains `role="tabpanel"` and an `aria-labelledby` that follows the active tab.
  - Labels are built with `textContent` only: the repository display name, or `—` (with `title="No repository"`).
  - The strip renders only after hydration; before that it is an empty fixed-height bar.
  - In snapshot mode the strip is hidden (`hidden`), so the snapshot report is unchanged.
- **CSS:**
  - `body` becomes a column flex container with `height: 100vh; overflow: hidden`. `#workspace-strip` has `flex: 0 0 var(--workspace-strip-height)` (36px), `overflow-x: auto`, `overflow-y: hidden`, `white-space: nowrap`, and never wraps. `#app-shell` changes from `height: 100vh` to `flex: 1; min-height: 0; position: relative`.
  - `#sidebar-toggle` changes from `position: fixed` to `position: absolute` within `#app-shell`, with the same offsets, so it no longer sits on top of the strip. The implementer confirms there is no positioned ancestor between them.
  - Selected tab: weight 700 plus a 3px `currentColor` underline (the shared tab-bar convention). Every tab has a `:focus-visible` outline. Selection is never shown by colour alone.
  - The 768px media block keeps the strip a single scrolling row. The active tab is scrolled into view (`scrollIntoView({inline: "nearest", block: "nearest"})`) when it is selected.
- **Behaviour (all in `dashboard.js`):**
  - `selectContext(id, {push})` writes the active context's state, sets `activeId`, then `applyShellEntry({view, repo, repoKey, sub})` for the selected context. A repository that is no longer registered leaves the context blank, with the Fleet notice (no cross-repository substitution). It then pushes `shellState` (which now includes `ctx`) and the canonical URL.
  - `+` creates `{repo: null, view: "welcome"}` (Fleet in snapshot mode, but the strip is hidden there) and selects it. At 12 contexts, `+` is `disabled` with the visible title "Workspace limit reached (12)".
  - **Close of an inactive context** removes it and saves, with no navigation and no history entry. **Close of the active context** selects the right-hand neighbour, else the left-hand one, through `selectContext` with a push. **Close of the last context** replaces it with a new blank Welcome context. Close never calls a registry or Loop endpoint.
  - **Keyboard:** Left and Right (wrapping), Home and End move focus among tabs. Enter and Space select. Focus stays on the selected tab after selection. After a close, focus moves to the newly active tab.
  - **`popstate`:** when `entry.ctx` names an existing context other than the active one, that context is selected without a push. Then `applyShellEntry` runs as today, under `restoring`.
  - **Loop teardown on switch** is the existing `showView()` teardown. The plan adds a strip-switch variant of `test_departed_mount_does_not_resurrect_polling`. If implementation shows the departed-mount guard in `views/loop.js` depends on an exception rather than an explicit check, the coding Draftor adds an explicit `container`-ownership check after `fetchLoops()` in the Loop entry point (a one-line guard) and charters it.
- Why: sketch "Full-Width Shell Layout", "Interaction", Slice B and Test Strategy items 2–8.

### 5. Fleet cross-context opening (Checkpoint 5)
- Files: `views/fleet.js`, `dashboard.js`.
- What:
  - **Overflow menu items:** two new items are added to the existing `⋮` menu.
    - "Open in new workspace tab" is a `button.menu-item` carrying `data-action="open-workspace"`, `data-repo-name` and `data-repo-key`. It is dispatched through `bindOverflowMenus` to `window.gatorOpenRepoInNewContext(name, key)`.
    - "Open in new browser tab" is a native `a.menu-item` with `href="?repo=<encodeURIComponent(name)>"`, `target="_blank"` and `rel="noopener"`. A native link means middle-click and the browser's own tab handling work. It is hidden in snapshot mode.
  - **`gatorNavToRepo` (the row link) = open in the current context:**
    - If another context already holds that repository (`findByRepo`), select it.
    - Otherwise `navigate("repo", …)` as today, which turns the current context into that repository's context.
  - **`gatorOpenRepoInNewContext`:** select the existing context for that repository if there is one. Otherwise create `{repo, repoKey, view: "repo"}` (Repo overview, the sketch's predictable default) and select it. At the 12-context limit it shows a `.shell-notice`, "Workspace limit reached (12). Close a workspace first.", and does nothing else.
  - Actions use `data-repo-key`, never the row position.
- Why: sketch Slice C items 1 and 3.

## Dependencies and Ordering

- 1 → 2 → 3 → 4 → 5, strictly in that order.
- 2 depends on 1 only because both change the same `showView` and `init` code paths. The title can then be verified on the new restore paths.
- 3 needs 2's `applyShellEntry` and the URL-derived landing.
- 4 needs 3's model.
- 5 needs 4's `selectContext`.
- Nothing can run in parallel; each checkpoint is a working Dashboard on its own.

## Assumptions, Risks, and Required Architect Decisions

**Non-blocking assumptions (reversible):**
1. **Loop badges are deferred.** `/api/data` carries no Loop state (checked in `data.py`), and the sketch forbids a second polling mechanism for the strip. No badge ships in this increment. A later issue can add one when Fleet data carries Loop state.
2. **The strip is hidden in snapshot mode.** A snapshot is a static Fleet report with no Repo drill-down, so contexts add nothing there. `workspace.js` is still inlined, so the snapshot has no external script reference.
3. **The URL carries the repository name, not its key.** Duplicate display names are disambiguated by `history.state` on reload and by the cache's `repoKey`. A fresh direct link with a duplicate name keeps today's first-match behaviour. Repository keys stay out of shareable URLs.
4. **A context opened from Fleet starts at Repo overview.** This is the sketch's recommended default.
5. **The inbox "Document tabs: dropped" note (2026-09-12) concerns per-document tabs** inside the inspection workspace. #80 is a different, Architect-approved feature: repository contexts. The implementation does not revive document tabs. The coding commit updates that inbox note so the two are not confused.

**Risks:**
- **Shell regressions.** Changing `init()` and `restoreShellState()` can break the #70 guard or Back/Forward. Mitigations: the #70 test stays unchanged and must pass at Checkpoint 2, and `applyShellEntry` is a pure extraction of the existing restore steps.
- **Layout.** Making `body` the flex container could reintroduce page scroll or move `#sidebar-toggle`. Mitigations: the existing bounded-shell test plus a strip layout test, both at Checkpoint 4.
- **Storage hostility.** Blocked or corrupt storage must never stop rendering. All access is try/catch, and Checkpoint 3 tests this.
- **History growth.** Every tab selection pushes an entry. This is intended (it matches a sidebar click) and is bounded by user actions.

**Blocking decisions:** none.

## Testing

All new tests go in `tests/test_dashboard_ui/test_workspace_tabs.py` and use the existing `dashboard_fleet` (`alpha`, `beta`) and Loop seed fixtures.

| Checkpoint | Test | Risk it proves |
|---|---|---|
| 1 | `test_document_title_follows_view` (parametrized: Welcome, Fleet, alpha Repo, alpha Docs, alpha Loop; then Back restores the previous title) | Title on every shell path, including restoration |
| 1 | `test_two_pages_distinct_titles_and_urls` | Sketch item 9: two pages, one server, independent state |
| 2 | `test_active_view_in_url_and_reload` (navigate to alpha Loop History; URL is `?repo=alpha&view=loop`; reload restores the Loop History tab without storage) | URL contract, and reload via `history.state` |
| 2 | `test_landing_url_forms` (parametrized: `?repo=alpha` gives Repo; `?view=fleet` gives Fleet; `?view=bogus` gives Welcome; `?repo=ghost` gives Fleet plus the notice) | Legacy links, defensive parsing, honest fallback |
| 3 | `test_workspace_cache_rejects_bad_records` (parametrized seeds through `add_init_script`: invalid JSON, wrong version, oversize, 13 contexts, invalid fields, unregistered repository, and a throwing `sessionStorage`) | Every case renders exactly the URL context with no page error, and stale repositories are dropped |
| 3 | `test_workspace_cache_holds_only_bounded_fields` (after Loop navigation, the stored JSON keys are exactly the allowed set) | No-secrets storage contract |
| 4 | `test_strip_spans_shell_above_sidebar` (strip top 0, full width; sidebar and main pane below it; document does not scroll; at 375px with 12 contexts the strip keeps one row and scrolls horizontally) | Layout and narrow overflow |
| 4 | `test_strip_aria_keyboard_and_close_labels` | Roles, roving tabindex, manual activation, labelled and focusable close buttons |
| 4 | `test_switch_restores_each_context` (alpha Loop History and beta Docs; switching back and forth restores the sidebar selection, view and Loop sub-tab; Back returns to the previous context) | Per-context restore and `ctx` history |
| 4 | `test_only_active_loop_context_polls` (alpha Loop polling; switch to beta Docs: zero `/loops` requests over 4 s; switch back: one interval resumes) | Teardown on switch |
| 4 | `test_close_changes_navigation_only` (close an inactive context, the active context and the last context; no POST requests; `/api/data` repository count unchanged; the active loop's stage unchanged) | Close never mutates the registry or Loops |
| 5 | `test_fleet_open_actions` (new workspace tab creates and selects alpha at Repo; repeating it selects the same context; the row link from a blank context selects the existing alpha context; the browser-tab link has `?repo=alpha`, `_blank` and `noopener`) | One context per repository; three opening paths |

**Per checkpoint:** run the new tests for that checkpoint plus the nearest existing pins:
- Checkpoint 2: `test_welcome_ui.py`, and the Back/Forward tests in `test_loop_workspace.py`;
- Checkpoint 3: `tests/test_snapshot.py`;
- Checkpoint 4: `test_responsive_shell.py`.

**Final approval:** run `tests/test_dashboard_ui/` and `tests/test_snapshot.py` once. The full repository and the CI matrix are left to CI.

## Charter Impact

**`.gator/charters/scripts-dashboard-ui.md`:**
- Add `workspace.js` to **Covers**.
- In the `navigate()` / `showView()` entry:
  - the state shape gains `ctx`;
  - entries now carry the canonical URL (the "state-only, URL unchanged" text is replaced, except in snapshot mode);
  - `shellUrl` / `parseShellUrl` / `applyShellEntry`;
  - the new landing rules, including the unregistered `?repo=` fallback;
  - title ownership (`formatDocumentTitle`, never from content).
- A new entry, `GatorWorkspace` / `renderStrip()` / `selectContext()`, covering the model, the one-per-repository rule, the storage contract (key, version, limits, allowed fields, fail-safe) and the strip ARIA and keyboard behaviour. Its tripwires:
  - inactive contexts are not live;
  - `workspace.js` never routes.
- The `renderFleet()` entry gains the two opening actions (key-addressed).
- The responsive shell entry gains the body flex column, the strip row and the `#sidebar-toggle` anchoring.

**`.gator/charters/scripts-dashboard.md`:** the `build_snapshot()` entry lists `workspace.js` among the inlined scripts.

**`.gator/charters/scripts-cross-cutting.md`:** extend the snapshot-inlining sentence to name `dashboard/workspace.js`, not only `views/*.js`.

`INDEX.md` needs no change, because `dashboard/*.js` is already mapped.

## Coding Checkpoints

1. **Browser-tab identity** — `formatDocumentTitle` / `updateDocumentTitle` in `showView()`, so the title follows every landing, navigation, refresh and restore path; never from repository content. Verify: `test_document_title_follows_view`, `test_two_pages_distinct_titles_and_urls`, `test_welcome_ui.py`.
2. **Active-context URL contract** — `shellUrl`, `parseShellUrl` and `applyShellEntry`; `navigate` and the sub-state pushes carry the canonical URL; `init()` lands through `applyShellEntry` with `history.state` reuse; the unregistered `?repo=` fallback; the #70 guard unchanged. Verify: `test_active_view_in_url_and_reload`, `test_landing_url_forms`, `test_welcome_ui.py`, and the history tests in `test_loop_workspace.py`.
3. **Workspace model and session cache** — `GatorWorkspace` model, the one-per-repository rule, the versioned bounded `sessionStorage` record with defensive parsing and fleet validation, active-context sync from shell state, and snapshot inlining. Verify: `test_workspace_cache_rejects_bad_records`, `test_workspace_cache_holds_only_bounded_fields`, `tests/test_snapshot.py`.
4. **Workspace strip and context switching** — the full-width strip above the shell, its ARIA and keyboard behaviour, select / `+` / close through `selectContext` and shell history with `ctx`, teardown on switch, and the narrow-width overflow. Verify: `test_strip_spans_shell_above_sidebar`, `test_strip_aria_keyboard_and_close_labels`, `test_switch_restores_each_context`, `test_only_active_loop_context_polls`, `test_close_changes_navigation_only`, `test_responsive_shell.py`.
5. **Fleet cross-context opening** — "Open in new workspace tab" and "Open in new browser tab" menu actions, and the row link selecting an existing context for that repository; all key-addressed. Verify: `test_fleet_open_actions`; then, for final approval, `tests/test_dashboard_ui/` and `tests/test_snapshot.py`.
