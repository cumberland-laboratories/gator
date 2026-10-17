# Implementation: #80 Checkpoint 3 — Workspace model and session cache (revision 1)

## Response to Findings

- **Finding 1 (Medium): the 16 KB cap measured characters, not bytes.** Accepted and fixed.
  - **The change:** `workspace.js` gains `overLimit(text)`. It returns true when `text.length > MAX_BYTES` (a cheap early answer: a string longer than the limit in UTF-16 units is always over it in UTF-8 bytes). Otherwise it compares `new TextEncoder().encode(text).length` with `MAX_BYTES`.
  - **Both paths use it:** `readCache()` (raw stored value) and `save()` (serialized JSON). The fail-safe behaviour is unchanged: an over-limit read gives an empty cache, and an over-limit write is skipped.
  - **New test case,** `oversize-bytes` in `test_workspace_cache_rejects_bad_records`: 9,000 `é` characters give a 9,011-character value that is 18,011 bytes in UTF-8. It is seeded as real non-ASCII text (`ensure_ascii=False`).
  - **Mutation check:** with the byte comparison replaced by `return false`, `oversize-bytes` fails and the character-length `oversize` case still passes. The file was then restored, which I confirmed by grep.
  - **The write path cannot be reached from a test with valid contexts.** Registered fixture names are ASCII, and a valid `loopId` is at most 200 characters (at most 600 UTF-8 bytes). Twelve such contexts stay under 16 KB. It shares `overLimit()` with the tested read path.
  - **Charter:** `scripts-dashboard-ui.md`'s storage contract now says "16,384 UTF-8 bytes (`overLimit()` …; never `.length` alone)", and that `save()` uses the same limit.
- **Results:** `pytest tests/test_dashboard_ui/test_workspace_tabs.py tests/test_snapshot.py` → **31 passed** (was 30). Nothing else changed since generation 2.

## Executive Summary

- **What changed:** a new shell module, `dashboard/workspace.js` (`window.GatorWorkspace`), keeps the per-browser-tab list of contexts `{id, repo, repoKey, view, sub}`. It has a versioned, bounded `sessionStorage` cache. `dashboard.js` records what is on screen into the active context and merges the cache after landing. The snapshot inlines the module.
- **Key decisions:**
  - The model never routes.
  - The active context is a copy of shell state.
  - Nothing is written before `load()`, so the landing cannot overwrite the cache before reading it.
  - Cached repositories survive only if the current fleet data still has them, matched by key and never substituted.
- **Risk:** the module has no visible UI yet (the strip is checkpoint 4). Its effects are storage and the `GatorWorkspace.list()` accessor.
- **Verified:**
  - 30/30 in `test_workspace_tabs.py` plus `tests/test_snapshot.py`;
  - 151/151 in the Welcome and Loop workspace suites;
  - three mutations, each failing its pin.

## Implementation Summary

**`src/gator_command/scripts/dashboard/workspace.js` (new):**
- **Constants:** `STORAGE_KEY = "gator.dashboard.workspace"`, `VERSION = 1`, `MAX_CONTEXTS = 12`, `MAX_BYTES = 16384`, `REPO_MAX = 200`, `LOOP_ID_MAX = 200`, `ID_RE`, `KEY_RE`.
- **`sanitize(raw)`** validates one record. It requires a valid id, a view accepted by the shell (`isView`), a repository that is null or a 1–200 character string, and a `repoKey` that is null or matches `KEY_RE` (non-null only with a repository). For Loop views, `sub` goes through the shell's `cleanSub` with `loopId` capped.
- **`readCache()`** returns null (an empty cache) for a throwing accessor, a non-string, an oversize value, a parse error, a wrong `v`, a non-array `contexts`, or more than 12 contexts. Otherwise it keeps valid records and drops invalid ones and duplicate ids or repositories.
- **`save()`** does nothing before hydration, skips a value over the limit, and swallows a `setItem` error.
- **`syncActive(fields)`** does nothing before hydration. It writes the fields into the active context (creating one if needed), drops an inactive duplicate of the same repository (the active one wins), and saves.
- **`load(current, validateRepo)`:**
  1. Read the cache and keep a repository context only when `validateRepo` returns the registry's current `{repo, repoKey}`.
  2. Choose the active context: the cached context for `current`'s repository, or the cached active context when both have no repository. Otherwise append a new one (at 12, the last inactive one is dropped first).
  3. Mark the model hydrated, then `syncActive(current)`.
- **Accessors:** `active()`, `list()` and `findByRepo()` return copies. `configure({isView, cleanSub})` sets the shell callbacks.

**`dashboard.js`:**
- **`workspace()`** returns `GatorWorkspace` unless `GATOR_SNAPSHOT` is set. `configure()` runs once at script load.
- **`syncWorkspace(sub)`** is called from:
  - `showView()`'s `finally`, with `sub: null` (the Loop mount's `replaceSubState` then records the sub);
  - `recordShell()`, which covers navigate, sub push and replace, the landing and the fallback;
  - the `views.loop.restore` branch of `applyShellEntry()`, where no `showView` runs.
- **`validateRepo(repo, repoKey)`** finds the fleet entry by key when one is recorded, else by name. It returns `{repo: name, repoKey}` or null.
- **`hydrateWorkspace()`** runs at the end of `init()`: after the landing `recordShell`, and after the #70 re-render (so it is built from the view the user navigated to).

**Other files:**
- `dashboard.html` adds `<script src="workspace.js">` before `dashboard.js`.
- `snapshot.py` reads `workspace.js`, adds it to the regex between `views/docs.js` and `dashboard.js`, and inlines it after the data block, before `dashboard.js`.
- `tests/test_snapshot.py` checks that the reference is gone and that `window.GatorWorkspace` is inlined.

## Charter Updates

- **`scripts-dashboard-ui.md`:**
  - **Covers** adds `workspace.js`.
  - A new entry, `window.GatorWorkspace … / syncWorkspace() / hydrateWorkspace() / validateRepo()`, covering:
    - the never-routes tripwire;
    - the active context as a copy of shell state;
    - no writes before hydration;
    - the four `load()` steps;
    - one context per repository;
    - the full storage contract (rejected whole versus dropped per record, `sub`, never-stored);
    - snapshot off;
    - the accessors and the pinning tests.
- **`scripts-dashboard.md` (Dashboard Server), `build_snapshot()`:** the script-tag rule now covers the shell modules and states the new order (… docs, workspace, then `dashboard.js`; the data block sits between docs and workspace). A new tripwire says `GATOR_SNAPSHOT` turns workspaces off and keeps history entries state-only.
- **`scripts-cross-cutting.md`:** the snapshot-inlining sentence now names shell modules, with `workspace.js` as an example.

I checked every name against the code.

## Verification

- `pytest tests/test_dashboard_ui/test_workspace_tabs.py tests/test_snapshot.py` → **30 passed**. New tests:
  - **`test_workspace_cache_rejects_bad_records`** has 7 cases: not-json, wrong version, oversize (17 KB pad), 13 contexts, invalid fields (bad id, bad key, unknown view, key without a repository), an unregistered repository, and a throwing `sessionStorage` getter. In each case exactly the URL's context remains (`alpha`, the registry key, `repo`), it is active, and there are no page errors.
  - **`test_workspace_cache_keeps_valid_contexts`** seeds beta Loop (with sub), a repository-less Fleet context and alpha Docs (no key), then lands on `?repo=alpha`. The order `b1, w1, a1` is kept. `a1` becomes active, adopts the registry key and takes the on-screen view `repo`. Beta's sub is preserved, and the stored `activeId` is `a1`.
  - **`test_workspace_cache_holds_only_bounded_fields`:** after alpha Loop History, the stored record's keys are exactly `v`, `activeId` and `contexts`; each context has exactly the five fields; `sub` has exactly its three keys. The alpha context is active with Loop and History. There is no `glp_` and no registered repository path, in plain or JSON-escaped form.
- `pytest tests/test_dashboard_ui/test_welcome_ui.py tests/test_dashboard_ui/test_loop_workspace.py` → **151 passed** (4 min 57 s).
- **Mutation checks** (restored from a copy each time; I confirmed by grepping the original lines):
  - keeping unregistered repositories → the `unregistered` case fails;
  - removing the 12-context limit → `too-many` fails;
  - removing the before-hydration guards → `keeps_valid_contexts` fails.
- **During testing:** my first version of the bounded-fields test assumed alpha was the only context. It isn't: the test's earlier visit to `/` stores a Welcome context, because `sessionStorage` lasts for the tab. That is correct behaviour, and the assertion now finds the alpha context.
- **Deferred to final approval:** the full `tests/test_dashboard_ui/`.

**Residue:** `.gator/commit_draft.md` (checkpoints 1–3 body) is in the working tree only. The pre-existing staged snippet is unchanged.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp3 (3 of 5) — Workspace model and session cache |
| Checkpoint base tree | `a07f827fda83d56fc70abe9ec95eb740c770a499` |
| Generation | 3 |
| Staged tree (candidate) | `dbf9ee67c96d82ba10a84da764db3d7cbe5e5c0a` |
| Changed paths in this checkpoint | 9 (A 1, M 8) |
| Loop base HEAD | `aac105b1618b4a7ea87f37fb6d288da1e1268d12` |
| Loop base tree | `b74ac09fb57299f319beabf948a5ff00a619d99e` |
| Current HEAD | `aac105b1618b4a7ea87f37fb6d288da1e1268d12` (dev) |
| Changed paths vs loop base (cumulative) | 10 |
| Unstaged / untracked residue | 1 other + 20 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff a07f827fda83d56fc70abe9ec95eb740c770a499 dbf9ee67c96d82ba10a84da764db3d7cbe5e5c0a
```

Cumulative context (approved checkpoints plus this one): `git diff b74ac09fb57299f319beabf948a5ff00a619d99e dbf9ee67c96d82ba10a84da764db3d7cbe5e5c0a`.

Changed paths in this checkpoint (status, path):

```text
M .gator/charters/scripts-cross-cutting.md
M .gator/charters/scripts-dashboard-ui.md  [revisits an earlier checkpoint]
M .gator/charters/scripts-dashboard.md
M src/gator_command/scripts/dashboard/dashboard.html
M src/gator_command/scripts/dashboard/dashboard.js  [revisits an earlier checkpoint]
M src/gator_command/scripts/dashboard/snapshot.py
A src/gator_command/scripts/dashboard/workspace.js
M tests/test_dashboard_ui/test_workspace_tabs.py  [revisits an earlier checkpoint]
M tests/test_snapshot.py
```

Paths marked as revisiting an earlier checkpoint were also changed by an approved checkpoint; this is information for the Reviewer, not a prohibition.

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/commit_draft.md
```

Loop residue: 20 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
