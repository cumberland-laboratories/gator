---
date: 2026-10-16
type: implementation-sketch
feature: dashboard-repository-tree-return-cache
related: 70, 80
recommended-path: focused-direct-implementation-after-current-worktree-settles
---

# Dashboard Repository Tree: Instant Return from Workspace Contexts

## Executive Summary

- The full-width Dashboard workspace strip deliberately tears down inactive
  views. That remains correct: hidden Loop views must not continue polling or
  retain live DOM/listeners.
- The Repo view currently fetches `/files` and rebuilds its file-tree sidebar
  at every mount. Its one global `_treeState` also resets folders and selected
  file whenever the repository changes, so returning Alpha → Beta → Alpha
  behaves like a fresh visit.
- Keep a bounded, live-version-only listing cache in browser memory and a
  per-repository tree-state map. Render a cached tree immediately, then fetch
  in the background and redraw only when its fingerprint changed.
- Key all cached state by stable repository key, not display name, and use a
  mount-generation guard. Duplicate display names and stale responses are the
  meaningful correctness hazards; keeping inactive DOM alive is not a fix.

## User Experience Goal

When an Architect switches from one open repository workspace to another and
later returns, the Repo view should feel continuous:

```text
Odyssey → Gator → Odyssey

return to Odyssey:
  the file tree appears immediately
  expanded folders remain expanded
  the selected file and tree scroll position return
  a background check quietly reflects any changed listing
```

The expected behavior is **fast return with eventual freshness**, not an
assertion that a cached tree is permanently current. A first visit still loads
honestly. A repository whose listing changed while inactive is updated once
the background request completes.

## Current Behavior and Cause

`views/repo.js` currently does three sensible things that combine poorly with
frequent workspace switching:

1. `GatorViews.repo()` creates the Repo DOM skeleton and calls
   `loadFileList()` on every mount. `loadFileList()` fetches
   `/api/repo/<name>/files`, filters the result, and rebuilds the sidebar.
2. `_treeState` holds exactly one `{repoName, expandedDirs, selectedFile}`.
   `resetTreeStateFor(repoName)` replaces it when the repository name changes.
   `teardownRepoView()` intentionally preserves that one object, but returning
   to a previously visited repository after another repository has mounted
   still resets it.
3. The Repo lifecycle correctly tears down its timer and global listener when
   the shell changes view or workspace context. #80 explicitly requires that
   inactive contexts are remembered navigation state, never hidden live DOM
   copies. This must stay true.

The view already contains useful pieces for this work:

- `fingerprint(files)` cheaply identifies an unchanged listing.
- `applyRefresh(files)` rebuilds only the file sidebar, preserving its current
  DOM scroll position and selection where possible.
- `pollRepoFiles()` fetches every five seconds for the active, live Repo view
  and avoids redraw when the fingerprint is unchanged.
- lifecycle teardown already centralizes poll-timer and `popstate` listener
  cleanup.

## Scope and Non-goals

### In scope

- Instant in-memory restoration of a previously visited live repository tree.
- Per-repository expanded directories, selected file, and sidebar scroll
  position.
- A background freshness check after a cached restore.
- Safe handling of rapid workspace/view switches and duplicate display names.

### Out of scope

- Keeping inactive Repo DOM mounted or allowing inactive Repo/Loop polling.
- Persisting complete file listings into `localStorage` or `sessionStorage`.
- Caching historical `?version=` Repo views.
- Changing server-side containment, listing visibility, or filesystem policy.
- Replacing the separate server-side listing/search performance effort in
  `.gator/artifacts/2026-10-16-dashboard-listing-performance-sketch.md`.
- Fleet-wide document search or workspace-strip behavior beyond its existing
  view teardown contract.

## Design

### Repository identity

Cache and tree-state records must use the Dashboard stable repository key, not
the display name. Registered repositories can have duplicate display names;
name-keyed state could show one repository tree in another repository context.

The current `GatorViews.repo(data, container, repoName, version)` surface does
not receive the key. Extend the shell-to-view call to pass the already resolved
`repoKey` explicitly, and use a cache key shaped like:

```text
live:<repoKey>
```

Do not cache a historical tree in this first slice. A `version` view remains
an honest fetch-and-render path because Git object identity, branch history,
and file-list freshness have different semantics.

### Bounded in-memory listing cache

Add a module-private cache, conceptually:

```text
RepoTreeCacheEntry
  repoKey: stable registry key
  files: canonical unfiltered `/files` response array
  fingerprint: fingerprint(files)
  touchedAt: monotonic use counter or timestamp
```

Properties:

- Browser-memory only; it disappears on reload and is never serialized.
- Store the canonical response array, then run the existing `filterFiles()` at
  render time. Do not cache rendered HTML or file content.
- Bound it deterministically, for example eight live repositories and a
  conservative total item count. Evict least-recently-used inactive entries.
  Never evict the active repository while mounting it.
- A failed background fetch leaves the cached tree visible. It must not replace
  valid cached content with a failure message merely because a refresh failed.
- On every successful active-view poll or initial background refresh, replace
  the cache entry only after the response passes the active mount guard.

This cache makes the return render fast even before the server-side listing
performance work lands. That separate work makes both cached refreshes and
first visits faster; neither effort depends on the other.

### Per-repository browsing state

Replace the singleton `_treeState` with a private map keyed by `repoKey`. Each
entry contains only:

```text
RepoTreeState
  expandedDirs: Set<string>
  selectedFile: null | logical file path
  scrollTop: non-negative integer
```

On first use, initialize `.gator` expanded as today. On Repo teardown, snapshot
the current `#repo-file-list.scrollTop` into the active state before its DOM is
discarded. On restore, render from that state, then set `scrollTop` after the
tree is in the DOM. Keep the existing behavior that drops a selected file if a
fresh listing no longer contains it.

Any code path that changes selected file—tree click, search-result click,
Markdown link navigation, default selection, and a refresh removing a file—must
update the active state through one accessor. The debug seam must expose a
fresh copy of the active repository state and its stable key; it must never
leak a mutable map or `Set`.

Sidebar width/collapse preferences already persist by repository display name.
This sketch does not widen that change, but implementation should record a
follow-up if duplicate display names make those existing preferences ambiguous.

### Render and refresh sequence

For a live Repo mount:

1. Tear down the prior active view as today; record its tree scroll position.
2. Create the Repo skeleton and restore the per-key collapse/width preference.
3. Acquire the active repository tree state.
4. If a cached listing exists, immediately filter and render its tree, restore
   expanded state/selection/scroll, and load the selected/default file. Mark
   this render as cached internally; no “stale” warning is needed for normal
   short-lived navigation.
5. Start one background `/files` request. If its fingerprint matches the cache,
   make no DOM write. If it differs, update the cache and use the existing
   refresh path to reconcile the visible tree while preserving state where
   valid.
6. Start the existing active-view polling timer only after mount. Its successful
   results update the same cache; an unchanged fingerprint remains mutation
   free.

For a first visit, retain the existing Loading files state until the initial
response arrives. For a historical version view, retain the existing behavior.

### Stale-response guard

Introduce a monotonically increasing Repo mount generation, captured by every
initial load, background refresh, and poll. A response may change DOM, tree
state, cache, or `_repoView.lastFp` only if all are still true:

- its generation equals the current mount generation;
- its container is the current connected Repo container;
- its repository key and version match the current Repo view; and
- the view is not pinned when the operation requires a live view.

Increment the generation before teardown/mount transitions. A stale Alpha
response arriving after Beta has mounted must be ignored completely. Do not
rely on detached-DOM mutation being harmless: global state and cache writes can
still be wrong without this guard.

## Suggested Implementation Slices

### Slice A — State and cache primitives

1. Pass `repoKey` into `GatorViews.repo` and hold it in `_repoView`.
2. Add the bounded in-memory cache, per-key tree-state map, accessors, and
   mount-generation helper.
3. Convert existing selection/expansion writes to use the active state
   accessor, without changing visible load behavior.
4. Add narrow unit-style/browser pins for duplicate display names and state
   isolation.

### Slice B — Cached first render and background reconciliation

1. Render a cache hit immediately on Repo mount.
2. Start a guarded background listing fetch.
3. Reuse `fingerprint()` and `applyRefresh()` only after adapting them to the
   new per-key state/cache contract.
4. Capture/restore sidebar scroll position around teardown and cached render.
5. Ensure a failed refresh preserves a valid cached tree and does not produce
   a misleading success/freshness claim.

### Slice C — Hardening and cleanup

1. Exercise rapid Alpha → Beta → Alpha switching with deferred responses.
2. Verify view transitions and workspace-context switches both invoke the same
   cleanup path.
3. Set explicit cache-count/item limits and prove LRU eviction never disturbs
   the active tree.
4. Update the Dashboard UI charter with cache scope, identity, lifecycle, and
   stale-response invariants.

## Test Plan

Add focused Dashboard UI tests, using delayed/intercepted `/files` responses
where necessary:

1. **Instant return:** visit Alpha, then Beta, then Alpha. Delay Alpha's second
   listing response; assert Alpha's cached tree appears before it is released.
2. **State restoration:** expand folders, select a file, scroll the tree, leave
   Alpha, and return. Assert all three are restored.
3. **Changed listing:** return from cache with a selected file; deliver a
   changed listing. Assert the tree updates once, valid state persists, and a
   removed selection is cleared safely.
4. **Unchanged listing:** cached render followed by an equal fingerprint makes
   no tree re-render or selection/scroll reset.
5. **Stale response:** delay Alpha, mount Beta, then release Alpha. Assert Beta
   DOM, state, cache, and selected file remain Beta-only.
6. **Duplicate display names:** two registered repositories with the same name
   and distinct keys never share listing or tree state.
7. **Historical view:** a versioned Repo mount does not consume or populate the
   live cache.
8. **Lifecycle:** a cached inactive workspace has no Repo poll timer or global
   `popstate` listener; returning creates exactly one active timer/listener.
9. **Cache bound:** after more than the configured number of repositories,
   verify LRU eviction and that the active context remains usable.

## Risks and Decisions

| Risk | Guard |
|---|---|
| A stale response corrupts another workspace | Stable repo key plus mount-generation/container guard. |
| Cache makes data look permanently current | Always issue a background listing check; no durable cache. |
| Hidden views keep consuming resources | Cache data only; never retain inactive DOM, listeners, or timers. |
| Memory grows with large fleets | Small bounded LRU and item budget. |
| Existing duplicate-name behavior is exposed | Key new cache/state by repo key; evaluate old name-keyed sidebar preferences separately. |
| Backend listing remains slow | Coordinate with, but do not block on, the server-side performance sketch. |

## Likely Files

- `src/gator_command/scripts/dashboard/dashboard.js` — pass stable repository
  key into Repo view without creating a second routing authority.
- `src/gator_command/scripts/dashboard/views/repo.js` — cache, per-key tree
  state, guarded mount/refresh flow, and teardown scroll snapshot.
- `tests/test_dashboard_ui/test_workspace_tabs.py` and/or a focused Repo-view
  test module — cache return, race, and multi-repository state pins.
- `.gator/charters/scripts-dashboard-ui.md` — update immediately with the
  identity, stale-response, bounded-cache, and teardown rules when code work
  starts.

## Connections

- #80 — workspace contexts deliberately tear down inactive views; this sketch
  complements rather than relaxes that invariant.
- #70 — Dashboard browser readiness and current server/listing performance
  work; cached rendering reduces repeat-navigation sensitivity.
- `.gator/artifacts/2026-10-16-dashboard-listing-performance-sketch.md` —
  independent server-side listing/search performance work.
- `.gator/charters/scripts-dashboard-ui.md` — Repo view lifecycle and shell
  routing contracts.
