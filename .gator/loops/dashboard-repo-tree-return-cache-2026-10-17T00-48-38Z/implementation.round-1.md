# Implementation: Repo tree return — Checkpoint 2: Cached return and background reconciliation

## Executive Summary

- **What changed:** a bounded, live-only, memory-only LRU listing cache. A revisited repository's tree is drawn at once, with its scroll position restored. A guarded background `/files` request then decides:
  - unchanged → no DOM write;
  - changed → `applyRefresh`;
  - failed → the cached tree stays.
- **Key decision:** one first-render path, `renderListing()`, serves both the cached and the fresh render. The scroll position is captured at teardown while the sidebar still exists.
- **Final-approval sweep:** `tests/test_dashboard_ui/` plus `tests/test_snapshot.py` → **532 passed, 11 skipped, 0 failed** (12 min 5 s).
- **Verified:** 11/11 in `test_repo_tree_cache.py`, and six mutations, each failing its pin.

## Implementation Summary

`src/gator_command/scripts/dashboard/views/repo.js`:
- **Cache:** `_listingCache: Map<repoKey, {files, fp, items}>`, with `LIVE_CACHE_MAX_REPOS = 8` and `LIVE_CACHE_MAX_ITEMS = 20000`.
  - **`cacheGet(key)`** moves the entry to most recently used.
  - **`cachePut(key, files)`** deletes the old entry, skips a listing over the item budget, stores `{files, fp, items}`, then evicts the oldest entries until both bounds hold, never the key being stored.
  - **`cacheable()`** requires a repository key and no `version`.
- **Mount:** after the skeleton and the listeners, a cache hit calls `renderListing(repoName, container, cached.files)` and sets `_repoView.fromCache = true`. The flag is reset on every mount.
- **`renderListing()`** is extracted from `loadFileList`'s success path, so the cached and fresh renders share one path. It chooses the file, draws the tree, sets `#repo-file-list.scrollTop = treeState().scrollTop`, sets `files` / `lastFp`, loads the file, and binds the resize handle once per mount.
- **`loadFileList(gen, …)`,** after the Checkpoint 1 guard:
  - an error body or exception with `fromCache` returns without a write, keeping the cached tree;
  - success calls `cachePut` (when cacheable), then either `renderListing` (no cache hit), or `applyRefresh` on a changed fingerprint, or nothing on an unchanged one.
- **`pollRepoFiles()`:** a guarded success also calls `cachePut`, which keeps the entry fresh and recently used.
- **`teardownRepoView()`:** before incrementing the generation, it records `Math.round(#repo-file-list.scrollTop)` into the tree state. That happens only when the sidebar is connected and the mount is live (`gen !== null`), so the mount's own idempotent teardown records nothing. Both the shell path (teardown before the slot is cleared) and the branch-history direct remount capture it.
- **Debug seam:** `__gator_debug.listingCache` returns a fresh `[{repoKey, items}]` in LRU order, never the files.

## Charter Updates

`.gator/charters/scripts-dashboard-ui.md`, Repo entry: a new tripwire, "Live listing cache — `cacheGet()` / `cachePut()` / `cacheable()` / `renderListing()`". It covers:
- the storage, memory-only and no-HTML rules;
- the live-only scope;
- both bounds and the eviction rule;
- that writes happen only after a guarded success;
- the mount sequence and `renderListing` as the single first-render path;
- the four reconciliation outcomes;
- the scroll capture conditions;
- that inactive views are still not live.

The debug-seam tripwire gains `listingCache`. I checked all names against the code.

## Verification

- `pytest tests/test_dashboard_ui/test_repo_tree_cache.py` → **11 passed**. New in this checkpoint:
  - **`test_return_draws_cached_tree_before_listing`:** alpha → beta → alpha with alpha's `/files` held. Tree items are visible and there is no "Loading files" text while the request is in flight.
  - **`test_return_restores_scroll`:** at 1280×600, with `artifacts` and `artifacts/many` expanded and `scrollTop` set to 300, beta shows its own `scrollTop` of 0, and alpha's returns within 1 px.
  - **`test_background_listing_reconciles`,** after a cached return with a non-default selection and a MutationObserver on `#repo-file-list`:
    - **unchanged** (`continue_`) → 0 mutations and the selection kept;
    - **changed** (`route.fetch`, with the selected file removed) → mutations, the item gone and `selectedFile` null;
    - **failed** (`abort`) → 0 mutations and the selection kept.
  - **`test_versioned_view_bypasses_cache`:** a commit from the branch dropdown, with `/files?version=` held, shows "Loading files" and fetches; `listingCache` is unchanged afterwards.
  - **`test_cache_bounds_evict_oldest`:**
    - the real key plus `k01`–`k09` leave exactly `k02`–`k09`, in order;
    - a fulfilled 20,001-entry listing under `bigkey01` renders but is not cached, and the cache is unchanged.
    - **Test adjustment:** the copied entries are hidden by the top-level allow-list in `filterFiles`, so the test waits for the render to finish, not for 20,000 visible items. The budget applies to the canonical listing.
- **Mutation checks** (restored from a copy each time; `cmp` confirmed):
  - no cache hit → `draws_cached` fails;
  - always `applyRefresh` → `reconciles[unchanged]` fails;
  - no keep-on-failure → `reconciles[failed]` fails;
  - no item budget → `bounds` fails;
  - no scroll capture → `restores_scroll` fails;
  - `cacheable()` ignoring `version` → `versioned` fails.
- **Final approval sweep:** `pytest tests/test_dashboard_ui/ tests/test_snapshot.py` → **532 passed, 11 skipped**, exit 0. The skips are the existing POSIX and symlink cases in `test_content_transport_slice3.py`.

**Residue:**
- `.gator/commit_draft.md` is updated for the whole feature, in the working tree only.
- The previous commit's snippet is still staged (disclosed in Checkpoint 1).

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp2 (2 of 2) — Cached return and background reconciliation |
| Checkpoint base tree | `373d19115436c8e686cd181754f4e6c1831576a5` |
| Generation | 1 |
| Staged tree (candidate) | `f60ce6a21e935025414481f4bcf2e1574e9359cf` |
| Changed paths in this checkpoint | 3 (M 3) |
| Loop base HEAD | `e4bcabb51ded413044f020d03df6db8e58d3fef0` |
| Loop base tree | `5fa96d3fbb68a3bbb0112e0286950f37e4b7a1fa` |
| Current HEAD | `e4bcabb51ded413044f020d03df6db8e58d3fef0` (dev) |
| Changed paths vs loop base (cumulative) | 6 |
| Unstaged / untracked residue | 1 other + 40 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff 373d19115436c8e686cd181754f4e6c1831576a5 f60ce6a21e935025414481f4bcf2e1574e9359cf
```

Cumulative context (approved checkpoints plus this one): `git diff 5fa96d3fbb68a3bbb0112e0286950f37e4b7a1fa f60ce6a21e935025414481f4bcf2e1574e9359cf`.

Changed paths in this checkpoint (status, path):

```text
M .gator/charters/scripts-dashboard-ui.md  [revisits an earlier checkpoint]
M src/gator_command/scripts/dashboard/views/repo.js  [revisits an earlier checkpoint]
M tests/test_dashboard_ui/test_repo_tree_cache.py  [revisits an earlier checkpoint]
```

Paths marked as revisiting an earlier checkpoint were also changed by an approved checkpoint; this is information for the Reviewer, not a prohibition.

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/commit_draft.md
```

Loop residue: 40 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
