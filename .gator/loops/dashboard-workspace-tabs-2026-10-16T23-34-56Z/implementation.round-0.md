# Implementation: #80 Checkpoint 1 — Browser-tab identity

## Executive Summary

- **What changed:** the document title now follows the shell's view and repository: `Gator · alpha · Loop`, `Gator · alpha · Docs`, `Gator · Fleet`, `Gator · Welcome`.
- **Key decision:** `showView()` became a thin wrapper. It runs `viewRenders++`, then `renderView()` (the unchanged former body) inside `try`, then `updateDocumentTitle()` in `finally`. That gives one title exit for every landing, navigation, refresh and restore path.
- **Risk:** low. The only behavioural change is the title. The #70 counter stays where it was, before rendering.
- **Verified:** the new tests and `test_welcome_ui.py` pass (46 passed). A mutation that removes the title call fails all 6 new tests.

## Implementation Summary

`src/gator_command/scripts/dashboard/dashboard.js`:
- **`TITLE_LABELS`:** `welcome` → "Welcome", `history` → "Commits". Other views use `VIEW_META[view].title`.
- **`TITLE_NO_REPO`:** `fleet` and `welcome` never name a repository.
- **`TITLE_REPO_MAX`:** 60 characters; longer names are truncated with "…".
- **`formatDocumentTitle(view, repo)`:** a pure function that joins `Gator`, the repository display name (when present and allowed for the view) and the label with " · ".
- **`updateDocumentTitle()`:** assigns `document.title` from `state.activeView` and `state.activeRepo`. It is a text property, so no markup path exists. The repository part is the registry display name only.
- **`showView(name, extra, repoKeyOverride, opts)`:** now `viewRenders++`, then `try { renderView(...) } finally { updateDocumentTitle(); }`. `renderView` is the previous body, byte-for-byte apart from its name. The `repo` branch's `setActiveRepo` runs before the `finally`, so the title sees the new repository. In `restoreShellState()`'s unregistered fallback, `clearActiveRepo()` runs before `showView("fleet")`, so the title is "Gator · Fleet".
- **`views.loop.restore()`** (no remount) keeps the same view and repository, so the title is already correct.

No other file assigns `document.title`; checked by grepping `src/gator_command/scripts/dashboard/`.

## Charter Updates

`.gator/charters/scripts-dashboard-ui.md`, in the `navigate()` / `showView()` / … entry: a new tripwire bullet, "Browser-tab title (#80)". It covers:
- the formatter rules and labels;
- the 60-character truncation;
- the never-from-content rule;
- the single `finally` exit, and the paths it covers;
- the `views.loop.restore()` note;
- the pinning tests.

I checked it against the code: the function and constant names match `dashboard.js`.

The URL contract, workspace and snapshot charter changes belong to later checkpoints, per the plan.

## Verification

- `python -m pytest tests/test_dashboard_ui/test_workspace_tabs.py tests/test_dashboard_ui/test_welcome_ui.py -q` → **46 passed** (45.96 s). This includes the #70 pin `test_navigation_before_data_load_is_not_replaced_by_welcome`.
- New tests (`tests/test_dashboard_ui/test_workspace_tabs.py`):
  - **`test_document_title_follows_view`**, parametrized over Welcome, Fleet, alpha Repo, alpha Docs and alpha Loop. It checks:
    - the landing title (`Gator · Welcome`);
    - the `?repo=alpha` landing title (`Gator · alpha · Repo`);
    - the title after navigation (Fleet and Welcome drop the repository even though alpha stays active);
    - the title after Back, which runs `restoreShellState`.
  - **`test_two_pages_distinct_titles_and_urls`:** two pages on one server (`?repo=alpha` Repo, `?repo=beta` Loop) keep distinct URLs and titles.
- **Mutation check:** I replaced the `finally` call with a comment. All 6 new tests failed ("6 failed"). The file was restored from a copy afterwards, and the staged diff is the intended one.
- **Deferred:** the full `tests/test_dashboard_ui/` and `tests/test_snapshot.py` run at final approval, per the plan's verification ladder. No snapshot change is in this checkpoint.

**Staged residue:**
- `.gator/session-snippets/2026-10-16-gator-aac105b1618b4.json` was already staged before this loop. It is the previous commit's evidence snippet, which the next real commit sweeps up by design.
- `.gator/commit_draft.md` is updated in the working tree for the eventual hook and is not staged, per the protocol.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp1 (1 of 5) — Browser-tab identity |
| Checkpoint base tree | `b74ac09fb57299f319beabf948a5ff00a619d99e` |
| Generation | 0 |
| Staged tree (candidate) | `8a0252b1bff78e82a6db1b5ce4cf2942a4d85e29` |
| Changed paths in this checkpoint | 4 (A 2, M 2) |
| Loop base HEAD | `aac105b1618b4a7ea87f37fb6d288da1e1268d12` |
| Loop base tree | `b74ac09fb57299f319beabf948a5ff00a619d99e` |
| Current HEAD | `aac105b1618b4a7ea87f37fb6d288da1e1268d12` (dev) |
| Changed paths vs loop base (cumulative) | 4 |
| Unstaged / untracked residue | 1 other + 12 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff b74ac09fb57299f319beabf948a5ff00a619d99e 8a0252b1bff78e82a6db1b5ce4cf2942a4d85e29
```

Cumulative context (approved checkpoints plus this one): `git diff b74ac09fb57299f319beabf948a5ff00a619d99e 8a0252b1bff78e82a6db1b5ce4cf2942a4d85e29`.

Changed paths in this checkpoint (status, path):

```text
M .gator/charters/scripts-dashboard-ui.md
A .gator/session-snippets/2026-10-16-gator-aac105b1618b4.json
M src/gator_command/scripts/dashboard/dashboard.js
A tests/test_dashboard_ui/test_workspace_tabs.py
```

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/commit_draft.md
```

Loop residue: 12 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
