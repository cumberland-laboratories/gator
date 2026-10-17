# Implementation: #80 Checkpoint 2 — Active-context URL contract

## Executive Summary

- **What changed:** every shell history entry now carries the canonical URL of the active context (`?repo=alpha`, `?repo=alpha&view=loop`, `?view=fleet`, or no query for Welcome without a repository). `init()` lands from that URL through the same hydrate → dispatch path as Back/Forward.
- **Key decisions:**
  - **`recordShell(method, sub)`** is the only writer of shell entries. It leaves the URL unchanged in snapshot mode.
  - **`applyShellEntry()`** is a pure extraction of the restore steps 2–3.
  - **On reload,** a kept `history.state` for the same context restores its `repoKey` and Loop `sub`.
- **Behaviour change (planned):** an unregistered `?repo=` landing now shows Fleet with the "no longer registered" notice. The #70 guard is unchanged.
- **Verified:** 12/12 workspace tests and 151/151 in `test_welcome_ui.py` plus `test_loop_workspace.py` pass. Two mutations each fail their pin.

## Implementation Summary

`src/gator_command/scripts/dashboard/dashboard.js`:
- **`shellUrl(view, repo)`** uses `URLSearchParams`:
  - `repo` is set when present;
  - `view` is set unless it is implied: Repo with a repository, or Welcome without one;
  - an empty query returns `location.pathname`, so the query is cleared rather than kept.
- **`parseShellUrl()`** returns `{repo, view}`. An empty `repo` becomes null. A `view` that is not an own key of `VIEW_META` becomes null.
- **`recordShell(method, sub)`** calls `history[method](shellState(sub), "", shellUrl(...))`, or omits the URL when `window.GATOR_SNAPSHOT` is set. It is used by `navigate()`, `GatorShell.pushSubState` / `replaceSubState`, the unregistered fallback and the landing. No other shell code calls `pushState` or `replaceState`.
- **`restoreShellState(entry)`** is now validate + `applyShellEntry(entry)`. `applyShellEntry` holds the unchanged hydrate (key-and-name, else name) → unregistered fallback → dispatch (`views.loop.restore` or `showView`) code.
- **`init()` landing.** The #70 early return comes first and is unchanged. After it:
  1. Build `{view, repo}` from `parseShellUrl()`. A missing `view` means: `repo` → Repo, else snapshot → Fleet, else Welcome.
  2. If `history.state` is a valid shell entry with the same `view` and `repo`, reuse its `repoKey` and `cleanSub(sub)`.
  3. `applyShellEntry(entry)`.
  4. `recordShell("replaceState", null)`. The Loop mount's own later `shellReplace()` then records the restored `sub` as before.
- **Unchanged:** `views/repo.js` and its own `?repo=&q=` entries (still valid: no `view` means Repo), the server, and the snapshot.

## Charter Updates

`.gator/charters/scripts-dashboard-ui.md`, in the `navigate()` / `showView()` entry:
- **State shape:** "Entries are state-only" is replaced by "carry the canonical URL; snapshot entries stay state-only".
- **`navigate()` versus `showView()`:** now names `recordShell` and the `applyShellEntry` landing.
- **New tripwire, "Shell URL (#80)":**
  - the canonical forms, including that `gator dashboard --repo` still produces the legacy link;
  - `sub` and `repoKey` stay out of the URL;
  - the parsing rules;
  - `recordShell` is the sole writer, and the snapshot exception;
  - the server never reads `view`;
  - the `repo.js` `?q=` compatibility.
- **Landing view:** rewritten. It covers the URL-driven view choice, `history.state` reuse, dispatch through `applyShellEntry` with the unregistered → Fleet behaviour change, and the #70 ordering.
- **Restoration:** step 1 is `restoreShellState`; steps 2–3 are `applyShellEntry`. The fallback records `?view=fleet`.

I checked every name against the code. The Dashboard Server charter is unchanged, as the plan says: no server behaviour changed. Its `build_snapshot()` entry is updated in Checkpoint 3.

## Verification

- `pytest tests/test_dashboard_ui/test_workspace_tabs.py` → **12 passed**. New in this checkpoint:
  - **`test_active_view_in_url_and_reload`:**
    - alpha Loop, History tab → URL `?repo=alpha&view=loop`;
    - `sessionStorage.clear()`, then reload → Loop with History still selected, title `Gator · alpha · Loop`, same URL;
    - Fleet → `?repo=alpha&view=fleet`;
    - Welcome → `?repo=alpha&view=welcome`.
  - **`test_landing_url_forms`** (5 cases):
    - `?repo=alpha` → Repo;
    - `?repo=alpha&view=docs` → Docs;
    - `?view=fleet` → Fleet;
    - `?view=bogus` → Welcome, with the URL rewritten to no query;
    - `?repo=ghost` → Fleet plus the exact notice, no Repo file list, and the URL becomes `?view=fleet`.
- `pytest tests/test_dashboard_ui/test_welcome_ui.py tests/test_dashboard_ui/test_loop_workspace.py` → **151 passed** (4 min 59 s). This includes the #70 pin and every Back/Forward and Loop history test.
- **Mutation checks** (file restored from a copy after each; the staged diff is the intended one):
  - Disabling the `history.state` reuse → `test_active_view_in_url_and_reload` fails.
  - Landing `?repo=` through the old direct `showView("repo", …)` instead of `applyShellEntry` → the `?repo=ghost` case fails.
- **Deferred to final approval** (per the plan): the full `tests/test_dashboard_ui/` and `tests/test_snapshot.py`. The snapshot still produces state-only entries through `recordShell`'s `GATOR_SNAPSHOT` branch. `tests/test_snapshot.py` and `test_welcome_snapshot_frames` will confirm that at final approval.

**Residue:**
- `.gator/commit_draft.md` body is extended for checkpoints 1–2. It is in the working tree only, not staged.
- The pre-existing staged session snippet is unchanged.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp2 (2 of 5) — Active-context URL contract |
| Checkpoint base tree | `8a0252b1bff78e82a6db1b5ce4cf2942a4d85e29` |
| Generation | 1 |
| Staged tree (candidate) | `a07f827fda83d56fc70abe9ec95eb740c770a499` |
| Changed paths in this checkpoint | 3 (M 3) |
| Loop base HEAD | `aac105b1618b4a7ea87f37fb6d288da1e1268d12` |
| Loop base tree | `b74ac09fb57299f319beabf948a5ff00a619d99e` |
| Current HEAD | `aac105b1618b4a7ea87f37fb6d288da1e1268d12` (dev) |
| Changed paths vs loop base (cumulative) | 4 |
| Unstaged / untracked residue | 1 other + 16 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff 8a0252b1bff78e82a6db1b5ce4cf2942a4d85e29 a07f827fda83d56fc70abe9ec95eb740c770a499
```

Cumulative context (approved checkpoints plus this one): `git diff b74ac09fb57299f319beabf948a5ff00a619d99e a07f827fda83d56fc70abe9ec95eb740c770a499`.

Changed paths in this checkpoint (status, path):

```text
M .gator/charters/scripts-dashboard-ui.md  [revisits an earlier checkpoint]
M src/gator_command/scripts/dashboard/dashboard.js  [revisits an earlier checkpoint]
M tests/test_dashboard_ui/test_workspace_tabs.py  [revisits an earlier checkpoint]
```

Paths marked as revisiting an earlier checkpoint were also changed by an approved checkpoint; this is information for the Reviewer, not a prohibition.

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/commit_draft.md
```

Loop residue: 16 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
