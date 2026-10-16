# Review: #70 — Windows Dashboard UI flakes, Slice 1

## Executive Summary

- **REVISE.** The new byte-budget contract is explicit, internally consistent, deterministically truncated, and well-tested.
- The plan also adds the requested repository-key field for shell history entries.
- However, the plan explicitly emits a null key after `repo.js` pushes its own unmarked search/file history entries—the normal state for tests that fail after opening or searching content.
- Slice 1 requires the selected repository key in the diagnostic bundle for failures generally, so this remaining identity gap must be resolved before approval.

## Verdict

REVISE

One material failure mode still produces no selected repository key, despite the sketch making that identity a required diagnostic field.

## Findings

### Finding 1: Repository key is still absent on normal Repo-view history entries

**Severity**: High

**Location**: Change 2, `browser_diagnostics(page)` history-state rules

**Issue**: The proposed snapshot records `history.state.repoKey` only for shell-marked entries, then intentionally records `selected_repo_key: null` for `repo.js` search/file entries. The Dashboard charter says `repo.js` owns those entries and they carry `{view: "repo", repo, searchQuery|filePath}` without the shell marker. Many Dashboard UI tests perform a repo action after initial navigation, so a failure in that common state loses precisely the repository identity the Slice 1 bundle is required to retain. The repository name is not a substitute for the key.

**Suggestion**: Define a key source that remains truthful for both shell and Repo-view entries, then pin both states. This can be a narrowly scoped, non-mutating diagnostic exposure at an existing shell seam (with the relevant Dashboard charter impact), or a documented browser-side derivation from an already available stable identity. Do not treat `null` as sufficient while a repository is selected.

## Scope Check

The plan remains within Slice 1 and all prior findings are resolved. This finding closes an existing diagnostic requirement rather than expanding scope: the sketch already requires the selected repository key.

## What Looks Good

- The 48 KiB measured guard and synthetic non-ASCII truncation test make the publication-safety claim credible.
- The Slice 2 evidence gate and final-verification ladder remain clear and appropriate.
