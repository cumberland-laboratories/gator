# Implementation Plan: Dashboard Repository Tree — Instant Return from Workspace Contexts

## Executive Summary

- **What:** returning to a previously visited repository draws its file tree at once from a bounded in-memory listing cache, with its own expanded folders, selected file and tree scroll position. A guarded background `/files` request then reconciles the tree only when its fingerprint changed.
- **Key decisions:**
  - all browser state is keyed by the stable repository key, which `dashboard.js` now passes to `GatorViews.repo`;
  - one mount generation guards every asynchronous listing path;
  - inactive views stay torn down, as the #80 invariant requires.
- **Main risk:** a late response changing another repository's view or state. `loadFileList()` and the poll can do this today. The plan closes it, and also fixes a found listener leak: each mount adds another search-box `input` listener.
- **Verification:** one focused Playwright module, `test_repo_tree_cache.py`, with deferred or intercepted `/files` responses; two checkpoints; the full Dashboard UI suite runs once, at final approval.

## Summary

The work stays inside `views/repo.js`, plus a one-argument change in `dashboard.js`. Checkpoint 1 replaces the single `_treeState` with per-key tree state, gives the selected file one writer, and adds the mount-generation guard and single-registration listeners. Repeat visits then keep their expansion and selection, and late responses can no longer change another repository's view. Checkpoint 2 adds the live-only least-recently-used (LRU) listing cache, the cached first render, background reconciliation, and scroll capture and restore. No server, route, storage or shell-routing change.

## Context Checked

- `sketch.md` (this loop). Status lists no Architect brief.
- `.gator/procedures/writing-implementation-plans.md`, `.gator/.includes/procedures/gator-loop-protocol.md`, `.gator/.includes/reference-notes/loop-artifact-formats.md`.
- `.gator/charters/scripts-cross-cutting.md` (read for #80 in this session): there is no cross-cutting contract here, no new script file, and no snapshot change.
- `.gator/charters/scripts-dashboard-ui.md`, read in full this session and updated by #80. Relevant entries:
  - `renderRepo() / loadFileList() / loadFile()`;
  - the `navigate()` / `showView()` repository context and `views/repo.js` entries;
  - the #80 workspace TRIPWIRE that inactive contexts are not live;
  - the responsive shell and sidebar rules.
- `.gator/charters/scripts-dashboard.md` (read this session): `/api/repo/<name>/files` is **name-addressed** on the server, and listing visibility and containment belong to the server. Both are unchanged here.
- Code in `src/gator_command/scripts/dashboard/views/repo.js`:
  - lines 380–830: `_treeState`, `resetTreeStateFor`, the debug seam, `_repoView`, `fingerprint`, `isPinnedView`, `teardownRepoView`, `_fetchRepoFiles`, `applyRefresh`, `pollRepoFiles`, `renderSidebarShell`, `toggleSidebarCollapse`, `restoreSidebarState`, `renderSidebarInto`, `expandAncestors`, `renderTree`, `renderSection` and the `GatorViews.repo` mount;
  - lines 835–998: `loadFileList` and `runCrossDocSearch`;
  - lines 999–1305: `initResizeHandle`, `loadFile` and the Markdown-link handler.
- Every `_treeState` reference, found by grep: lines 386–424, 491, 546, 672–682, 747–776, 866–869, 984, 1036 and 1288.
- Code in `dashboard.js`: the `showView("repo")` branch, which calls `views.repo(state.data, viewSlot, repoName)` (line 557) and, from the branch-history dropdown, `views.repo(…, hash || null)` (line 620). Its `repoKey` resolution and teardown order (teardown runs before `viewSlot.innerHTML = ""`).
- `dashboard.css`: `.repo-sidebar` (`#repo-file-list`) is the tree's scroll owner (`overflow-y: auto`).
- Tests:
  - `tests/test_dashboard_ui/test_harness.py` pins the debug seam: a `__gator_debug.sidebar` snapshot with `repoName` and `expandedDirs`, fresh on every call;
  - `_harness.py` `seed_repo` builds the alpha and beta fixtures; `dashboard_fleet` runs with debug on;
  - `test_responsive_shell.py` covers the long-tree scroll and the per-repository sidebar state;
  - `test_workspace_tabs.py` covers #80.

## Approach

**Planning path:** full planning loop, as the Architect chose. The change adds a new lifecycle and ordering invariant (a mount generation over asynchronous listing work) and new browser state.

**Module map.**

| Module | Responsibility and invariant | Where |
|---|---|---|
| Keyed browsing state | Tree state belongs to one repository key. It has one selected-file writer and no cross-repository bleed. | `repo.js` |
| Mount lifecycle guard | Only the current mount's listing work may change DOM, state, cache or `lastFp`. Global listeners are registered once per mount and removed at teardown. | `repo.js` |
| Live listing cache | A bounded, live-only, memory-only LRU of canonical `/files` arrays. A cache hit draws the tree at once, then a guarded background check updates it only on a changed fingerprint. | `repo.js` |

`dashboard.js` changes only to pass `repoKey` (no routing change).

**Key design decisions.**
1. **Identity.**
   - **The new parameter:** `GatorViews.repo(data, container, repoName, version, repoKey)`. `repoKey` is the shell's resolved `state.activeRepoKey`, passed from both call sites: the `showView` repo branch, and the "Current (HEAD)" / commit entries of the branch-history dropdown.
   - **Which key to use:** `cleanKey(repoKey)` accepts a non-empty string of at most 128 characters, else null.
   - **With a key:** state and cache are keyed by it.
   - **Without a key:** the view uses a transient tree state for that mount only and never reads or writes the cache. This is today's behaviour, and it never borrows another repository's state.
2. **Per-key tree state.** `_treeStates: Map<repoKey, {expandedDirs: Set, selectedFile, scrollTop}>` is bounded at 32 keys, LRU on use.
   - `acquireTreeState(repoKey)` returns the existing state or a new one, with `section:gator` expanded as today.
   - `_repoView.state` is the active one; `treeState()` reads it and `setSelectedFile(path)` is the **only** selected-file writer.
   - Callers converted to `setSelectedFile` and `treeState().expandedDirs`: the tree click, the search-result click, the Markdown link, the default selection in `loadFileList`, the drop in `applyRefresh`, `expandAncestors`, `renderTree`, `renderSection` and the directory toggles.
   - `resetTreeStateFor` and `_treeState` are removed.
   - `toggleSidebarCollapse` and `initResizeHandle` use `_repoView.repoName` (their storage stays keyed by name; see risks).
3. **Mount generation.** A module counter `_mountGen` is incremented in `teardownRepoView()` and again at mount. `_repoView.gen` holds the current mount's value. `isCurrentMount(gen)` requires:
   - `gen === _repoView.gen`;
   - `_repoView.container` connected and still containing `#repo-file-list`.

   Every `await` in `loadFileList` and `pollRepoFiles` captures `gen` first. After resuming, the code returns without **any** DOM, state, cache or `lastFp` write unless `isCurrentMount(gen)` holds. `pollRepoFiles` also requires `!isPinnedView()`, as today. The key and version are fixed per generation, because every mount takes a new generation.
4. **Single-registration listeners.** The search-box `input` listener and the `popstate` handler are installed synchronously at mount, held in `_repoView.searchHandler` / `_repoView.popHandler`, and removed in `teardownRepoView()`. They read the latest listing from `_repoView.files`, not from a closure over one fetch. Today they are added after the `await` on every mount, and the `input` listener is never removed. After alpha → beta → alpha, one keystroke therefore runs one search per visit.
5. **Live listing cache (Checkpoint 2).**
   - **Storage:** `_listingCache: Map<repoKey, {files, fp, items}>`. Map insertion order is the LRU order; a touch deletes and re-sets the entry.
   - **Limits:** `LIVE_CACHE_MAX_REPOS = 8` and `LIVE_CACHE_MAX_ITEMS = 20000` (total file entries). A listing with more than 20,000 entries is not cached, and any older entry for its key is deleted. Eviction removes the oldest entries first and never the key being mounted.
   - **Contents:** the canonical unfiltered `/files` array; `filterFiles()` runs at render time. No rendered HTML, no content, never serialized.
   - **Scope:** live only. A `version` mount neither reads nor writes it.
   - **Writes:** a cache entry is updated only after a guarded successful response (initial, background or poll).
6. **Mount sequence (live, with a key):**
   1. teardown (scroll snapshot, generation increment, listener removal);
   2. skeleton plus `restoreSidebarState` as today;
   3. `acquireTreeState`;
   4. on a **cache hit**: `renderListing(files)` at once (filter, tree, restore `scrollTop` after insertion, then load the selected or default file through the existing selection logic), with `_repoView.lastFp = fp` and `_repoView.files = files`;
   5. start one guarded background `/files` request;
   6. start the poll timer, as today.

   **When the background response arrives (guarded):**
   - **Failure or error body:** on a cache hit, keep the cached tree with no DOM write. On a first visit, show today's error.
   - **Same fingerprint:** update the cache's LRU position only; no DOM write.
   - **Different fingerprint:** update the cache, `_repoView.files` and `applyRefresh(files)`. That redraws the sidebar while keeping expansion and scroll, and drops a selection whose file is gone (the content pane stays, as today).
   - **First visit:** today's render path, then cache the listing.
7. **Scroll capture.** `teardownRepoView()` writes `#repo-file-list.scrollTop` into `_repoView.state.scrollTop` when that element is still in the current container, before any DOM is cleared. The shell runs teardown before clearing the slot, and the branch-history remount calls the view directly, so both paths capture it. The view's own idempotent teardown call at mount finds no sidebar and does nothing. Scroll is restored after every initial render, cached or fresh.

**Rejected alternative:** keeping inactive Repo DOM mounted. The sketch and #80 rule it out: inactive views must not poll or keep listeners.

**Simplicity boundary.**
- No content-pane cache.
- No historical-version cache.
- No server change, and no change to the name-addressed `/files` route.
- No `sessionStorage` or `localStorage` for listings.
- No freshness badge.
- No change to the existing name-keyed sidebar width and collapse preferences; recorded as a follow-up.

## Changes

### 1. Pass the repository key (Checkpoint 1)
- **File:** `dashboard.js`.
- **What:** `views.repo(state.data, viewSlot, repoName, null, state.activeRepoKey)` in the `showView` repo branch, after `setActiveRepo`. The branch-history dropdown calls pass `state.activeRepoKey` as the fifth argument.
- **Why:** the view has no key today, and the sketch requires key identity.

### 2. Keyed state, single writer, mount guard, listener lifecycle (Checkpoint 1)
- **File:** `views/repo.js`.
- **What:** design decisions 1–4.
  - **Debug seam:** the `__gator_debug.sidebar` getter returns a fresh plain object `{repoName, repoKey, expandedDirs: [...], selectedFile, scrollTop}` built from `_repoView`. It keeps `repoName` and `expandedDirs` (pinned by `test_harness.py`) and never returns the map or a `Set`.
  - **`loadFileList(gen, …)`:** guarded after its `await`. It assigns `_repoView.files`, and installs no listeners itself.
  - **`pollRepoFiles()`:** captures `gen` before fetching.
  - **`runCrossDocSearch`:** unchanged, except that it is called by the single registered handler.
- **Why:** sketch "Per-repository browsing state" and "Stale-response guard", and test plan item 8. Without this, alpha → beta → alpha keeps resetting and late responses can change the wrong repository.

### 3. Live listing cache, cached render, reconciliation, scroll (Checkpoint 2)
- **File:** `views/repo.js`.
- **What:**
  - design decisions 5–7: `cacheGet` / `cachePut` / `evict`, and `renderListing(files, {fromCache})` extracted from `loadFileList`'s success path so the cached and fresh first renders share code;
  - the mount sequence;
  - the teardown scroll snapshot and the restore after render;
  - the debug seam gains a `listingCache` getter returning `[{repoKey, items}]` in LRU order (a fresh array), for the eviction pins.
- **Why:** sketch "Bounded in-memory listing cache" and "Render and refresh sequence".

## Dependencies and Ordering

- Checkpoint 1 → Checkpoint 2.
- Checkpoint 2's cache writes rely on Checkpoint 1's generation guard and key plumbing, and the cached render relies on per-key state.
- Each checkpoint leaves a working Dashboard. After Checkpoint 1 a return still fetches before drawing, but restores expansion and selection; Checkpoint 2 makes the drawing instant.

## Assumptions, Risks, and Required Architect Decisions

**Non-blocking assumptions (reversible):**
1. **Bounds:** 8 repositories and 20,000 total listing entries for the cache; 32 keys for tree state. Changing them is a constant edit.
2. **No key, no cache:** a mount without a repository key keeps today's behaviour, with a fresh state and no cache.
3. **Duplicate display names stay ambiguous on the server.** The `/files`, `/file` and `/search` routes are addressed by name. Two same-named repositories therefore fetch the same listing even though their browser state is now separate. Out of scope here (server routes are excluded by the sketch); noted in the charter.
4. **Follow-up recorded, not implemented:** `gator-sidebar-collapsed:<name>` / `gator-sidebar-width:<name>` in `localStorage` are keyed by display name and are ambiguous for duplicate names. The implementing commit adds an inbox line.

**Risks:**
- **Converting every `_treeState` site.** A missed site would read a removed object; grep finds 19 references. Mitigation: `_treeState` is deleted outright, so a missed site throws in the existing suites instead of silently using the wrong state.
- **Changing the selected-file logic in `loadFileList`.** The default-selection logic moves into `renderListing`. Mitigation: `test_responsive_shell.py` and the existing Repo tests run at both checkpoints.
- **A cached tree hides a change for up to one request.** By design (the sketch's "eventual freshness"). The background request starts at mount.

**Blocking decisions:** none.

## Testing

New module: `tests/test_dashboard_ui/test_repo_tree_cache.py`, on `dashboard_fleet` (debug seam on, `alpha` and `beta`).
- **Navigation:** `window.gatorNavToRepo(name, key)`.
- **Holding a listing:** `page.route` on `**/api/repo/alpha/files*`.
- **Fake second key:** `gatorNavToRepo('alpha', '<fake key>')` gives a second key with the same display name. The shell accepts an override key, so no fixture change is needed.

| Checkpoint | Test | Risk it proves |
|---|---|---|
| 1 | `test_return_restores_expansion_and_selection` (expand a directory, select a file, alpha → beta → alpha; same expanded set and selection, through the debug seam and the active tree item) | Per-key state, single writer |
| 1 | `test_stale_listing_response_is_ignored` (hold alpha's first `/files`, navigate to beta and wait for its tree, release alpha: beta's DOM, debug state and `selectedFile` are unchanged) | Mount guard on the initial load. The poll uses the same guard and helper. |
| 1 | `test_same_name_different_key_state_is_separate` (expand under the real key; mount alpha with a fake key, which has default state; return to the real key, which has the expansion back) | Key identity, no cross-repository bleed |
| 1 | `test_single_search_listener_after_revisits` (alpha → beta → alpha, type a query: exactly one `/search` request) | Listener lifecycle (the found leak) |
| 2 | `test_return_draws_cached_tree_before_listing` (alpha, beta, then hold alpha's `/files` and return: `.repo-file-item` is visible while the request is held) | Instant return |
| 2 | `test_return_restores_scroll` (long-tree fixture, sidebar scrolled; after return `scrollTop` is equal, within 1 px) | Scroll capture and restore |
| 2 | `test_background_listing_reconciles` (parametrized: **unchanged**, so a MutationObserver on `#repo-file-list` sees 0 mutations after release; **changed with the selected file removed**, so the tree updates once and `selectedFile` becomes null; **failed** (500), so the cached tree stays with no mutations) | Fingerprint skip, reconciliation, failure keeps the cache |
| 2 | `test_versioned_view_bypasses_cache` (mount a commit from the branch dropdown with its `/files?version=` held: "Loading files…" shows, and the debug `listingCache` has no new entry) | Live-only scope |
| 2 | `test_cache_bounds_evict_oldest` (nine fake keys give 8 entries with the oldest gone and the active one present; a fulfilled 20,001-entry listing renders but is not cached) | LRU and item budget |

**Per checkpoint:** run the new tests for that checkpoint plus `test_responsive_shell.py`, `test_harness.py` (the debug seam) and `test_workspace_tabs.py`.

**Final approval:** run `tests/test_dashboard_ui/` once.

Mutation checks to run during coding:
- remove the generation check → the stale test fails;
- re-add the per-mount `input` listener → the listener test fails;
- render without the cache → the instant-return test fails;
- remove the fingerprint skip → the unchanged case fails.

## Charter Impact

**`.gator/charters/scripts-dashboard-ui.md`, the `renderRepo() / loadFileList() / loadFile()` entry,** becomes `GatorViews.repo(data, container, repoName, version, repoKey)`, with new tripwires for:
- key identity (no key means no cache and a transient state);
- the per-key tree-state map and its bound, and the single selected-file writer;
- the mount-generation guard, and the rule that no write happens after an `await` without it;
- single-registration search and `popstate` listeners, removed at teardown;
- the live-only, memory-only LRU listing cache, with its bounds, contents and update rules;
- the cached-render and reconciliation sequence, and that failure keeps the cached tree;
- the scroll capture at teardown and restore after render;
- inactive views are still not live (#80);
- the debug seam shape;
- the name-addressed server routes stay ambiguous for duplicate names.

**Elsewhere in that charter:** the `navigate()` / `showView()` entry notes that the Repo branch passes `activeRepoKey`.

**`.gator/inbox.md`:** a follow-up line about the name-keyed sidebar width and collapse preferences.

No other charter changes. `scripts-dashboard.md` is unaffected: no server change.

## Coding Checkpoints

1. **Keyed tree state and mount lifecycle guard** — pass `repoKey` into `GatorViews.repo`, replace `_treeState` with the bounded per-key map and a single selected-file writer, add the mount-generation guard to `loadFileList` and `pollRepoFiles`, register the search and `popstate` listeners once per mount and remove them at teardown, and update the debug seam. Verify: `test_return_restores_expansion_and_selection`, `test_stale_listing_response_is_ignored`, `test_same_name_different_key_state_is_separate`, `test_single_search_listener_after_revisits`, `test_harness.py`, `test_responsive_shell.py`.
2. **Cached return and background reconciliation** — the bounded live-only LRU listing cache, the immediate cached render, the guarded background fingerprint check (unchanged → no DOM write, changed → `applyRefresh`, failure keeps the cache), the teardown scroll capture and restore, the version bypass, and the eviction and item budget. Verify: `test_return_draws_cached_tree_before_listing`, `test_return_restores_scroll`, `test_background_listing_reconciles`, `test_versioned_view_bypasses_cache`, `test_cache_bounds_evict_oldest`, `test_workspace_tabs.py`; then, for final approval, `tests/test_dashboard_ui/`.
