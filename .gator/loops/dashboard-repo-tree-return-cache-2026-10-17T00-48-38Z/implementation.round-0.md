# Implementation: Repo tree return — Checkpoint 1: Keyed tree state and mount lifecycle guard

## Executive Summary

- **What changed:**
  - `GatorViews.repo` now receives the repository key from the shell.
  - The single `_treeState` is replaced by a bounded per-key state map, with `setSelectedFile()` as the only selected-file writer.
  - A mount generation guards every asynchronous listing path.
  - The search-box and `popstate` listeners are registered once per mount and removed at teardown.
- **Visible result:** alpha → beta → alpha now brings back alpha's expanded folders and selected file, though the tree still fetches before drawing (instant drawing is Checkpoint 2). A late alpha listing can no longer change beta.
- **Found while testing:** the leftover search handlers share one debounce timer, so counting search requests could not detect the leak. The listener test therefore counts registrations directly.
- **Verified:**
  - 4/4 new tests;
  - 241 passed, 11 skipped across the Repo-view, workspace, harness, responsive and content suites;
  - four mutations, each failing its pin.

## Implementation Summary

**`src/gator_command/scripts/dashboard/views/repo.js`:**
- **Tree state:**
  - `_treeStates` (Map, `TREE_STATE_MAX = 32`, LRU by insertion order); `cleanRepoKey` accepts a 1–128 character string.
  - `newTreeState()` gives `{expandedDirs: Set(["section:gator"]), selectedFile: null, scrollTop: 0}`.
  - `acquireTreeState(key)` returns the stored state or a new one; with no key it returns a transient state that is never stored.
  - `treeState()` reads `_repoView.state`; `setSelectedFile(path)` is the only selected-file writer.
  - `_treeState` and `resetTreeStateFor` are removed; grep finds no remaining reference.
- **Converted call sites:**
  - selection: the tree click, the search-result click, the Markdown link and the default selection in `loadFileList` now call `setSelectedFile`, and `applyRefresh`'s drop uses `treeState()` + `setSelectedFile(null)`;
  - expansion: `expandAncestors`, `renderTree`, `renderSection` and the directory toggles use `treeState().expandedDirs`;
  - storage: `toggleSidebarCollapse` and `initResizeHandle`'s storage name use `_repoView.repoName`.
- **`_repoView`** gains `repoKey`, `gen`, `state`, `files`, `searchHandler` and `searchTimer`.
- **Mount generation:**
  - `_mountGen`; `teardownRepoView()` increments it and sets `_repoView.gen = null`, and the mount increments it again and stores it;
  - `isCurrentMount(gen)` requires the same `gen` and a connected container that still holds `#repo-file-list`;
  - `loadFileList(gen, …)` returns before any write when it is not current, on the success, error-body and catch paths alike;
  - `pollRepoFiles()` captures `gen` before fetching and re-checks `isCurrentMount(gen)` and `isPinnedView()` after.
- **Listeners:**
  - `installSearchListeners(repoName, container)` runs synchronously at mount and registers one `input` handler (debounce in `_repoView.searchTimer`) and one `popstate` handler;
  - both find the content pane at event time, and read the latest listing from `_repoView.files` (`currentFilePaths()`, and `pickDefaultFile()` extracted from `loadFileList`);
  - `teardownRepoView()` removes both and clears a pending search timer;
  - `initResizeHandle(sidebar)` is still called after a successful load, as before.
- **Debug seam:** `__gator_debug.sidebar` returns a fresh `{repoName, repoKey, expandedDirs: [...], selectedFile, scrollTop}` from `_repoView`. `test_harness.py`'s `repoName` and `expandedDirs` contract still passes.

**`dashboard.js`:** both `views.repo(...)` calls (the `showView("repo")` branch and the branch-history dropdown) pass `state.activeRepoKey` as the fifth argument.

## Charter Updates

- **`.gator/charters/scripts-dashboard-ui.md`:** the Repo entry heading becomes `GatorViews.repo(data, container, repoName, version, repoKey) / loadFileList() / loadFile() / acquireTreeState() / setSelectedFile() / isCurrentMount() / installSearchListeners() / teardownRepoView()`. Its `<-` names the shell's key passing. New tripwires:
  - per-key tree state (bound, transient state without a key, never the display name, the single writer, teardown keeps states, and the old singleton gone);
  - the mount generation guard (the counter, the conditions, which paths it covers, why, and that `loadFile` writes only to its captured element);
  - single-registration listeners (what is registered, when it is removed, and the old leak);
  - the debug-seam shape;
  - the server routes are addressed by name, and the follow-up for the name-keyed sidebar preferences.
- **`.gator/inbox.md`:** the follow-up "Repo sidebar preferences are keyed by display name", from plan assumption 4.

I checked all names against the code.

## Verification

- `pytest tests/test_dashboard_ui/test_repo_tree_cache.py` → **4 passed**:
  - **`test_return_restores_expansion_and_selection`:** open a folder and select a document inside it, then expand a second folder that is not an ancestor of the selection (only remembered state can bring that back). alpha → beta → alpha restores both, through the debug seam and the active tree item.
  - **`test_stale_listing_response_is_ignored`:** hold alpha's first `/files`, then navigate to beta. Release alpha with a listing whose default document (`pulse.md`) beta lacks, so an unguarded write would select it in beta's state. Beta's debug state and tree HTML are unchanged.
  - **`test_same_name_different_key_state_is_separate`:** expand under alpha's real key; `gatorNavToRepo('alpha', 'fakekey0001')` gives default state; returning to the real key gives the expansion back.
  - **`test_single_search_listener_after_revisits`:** an init script counts `input` listener add and remove calls on `#repo-search-input`. After alpha → beta → alpha the count is 1, and one query sends exactly one `/search` request, for alpha.
- **Mutation checks** (restored from a copy each time; `cmp` confirmed):
  - removing the `loadFileList` guard → the stale test fails;
  - always returning a fresh state → `restores_expansion` fails;
  - sharing one state across keys → `same_name` fails;
  - not removing the `input` listener → `single_search` fails (only after counting registrations; see below).
- **Lesson from testing:** in the first version of the listener test, the "not removed" mutation **survived**. Leftover handlers share `_repoView.searchTimer`, so each cancels the previous handler's pending search and the request count stays 1. The test now counts registrations. Two smaller test fixes: the first draft picked a document inside a collapsed folder, and the fixture has only one visible top-level document.
- **Neighbouring suites:** `pytest test_repo_tree_cache.py test_harness.py test_responsive_shell.py test_workspace_tabs.py test_content_transport_slice{1,2,3}.py test_html_preview.py test_syntax_highlight.py` → **241 passed, 11 skipped** (2 min 30 s). The skips are the existing POSIX and symlink cases.
- **Deferred to final approval:** the full `tests/test_dashboard_ui/`.

**Residue:**
- The staged `.gator/session-snippets/2026-10-17-gator-e4bcabb51ded4.json` is the previous commit's evidence snippet, which the next real commit sweeps up by design.
- `.gator/commit_draft.md` is in the working tree only.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp1 (1 of 2) — Keyed tree state and mount lifecycle guard |
| Checkpoint base tree | `5fa96d3fbb68a3bbb0112e0286950f37e4b7a1fa` |
| Generation | 0 |
| Staged tree (candidate) | `373d19115436c8e686cd181754f4e6c1831576a5` |
| Changed paths in this checkpoint | 6 (A 2, M 4) |
| Loop base HEAD | `e4bcabb51ded413044f020d03df6db8e58d3fef0` |
| Loop base tree | `5fa96d3fbb68a3bbb0112e0286950f37e4b7a1fa` |
| Current HEAD | `e4bcabb51ded413044f020d03df6db8e58d3fef0` (dev) |
| Changed paths vs loop base (cumulative) | 6 |
| Unstaged / untracked residue | 1 other + 36 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff 5fa96d3fbb68a3bbb0112e0286950f37e4b7a1fa 373d19115436c8e686cd181754f4e6c1831576a5
```

Cumulative context (approved checkpoints plus this one): `git diff 5fa96d3fbb68a3bbb0112e0286950f37e4b7a1fa 373d19115436c8e686cd181754f4e6c1831576a5`.

Changed paths in this checkpoint (status, path):

```text
M .gator/charters/scripts-dashboard-ui.md
M .gator/inbox.md
A .gator/session-snippets/2026-10-17-gator-e4bcabb51ded4.json
M src/gator_command/scripts/dashboard/dashboard.js
M src/gator_command/scripts/dashboard/views/repo.js
A tests/test_dashboard_ui/test_repo_tree_cache.py
```

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/commit_draft.md
```

Loop residue: 36 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
