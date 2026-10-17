# Implementation: #80 Checkpoint 5 — Fleet cross-context opening

## Executive Summary

- **What changed:** Fleet's ⋮ menu gains two items.
  - **"Open in new workspace tab"** is key-addressed. It selects the repository's existing context, or creates one at Repo overview.
  - **"Open in new browser tab"** is a native same-origin `?repo=` link.

  The row link still means "open in the current context", but it selects an existing context for that repository instead of creating a duplicate.
- **Key decisions:**
  - Neither item is shown in snapshots.
  - At 12 contexts, the new-workspace action shows a visible notice and changes nothing.
  - The plan's inbox clarification is included: "document tabs" are not #80 "workspace tabs".
- **Final-approval sweep:** `tests/test_dashboard_ui/` plus `tests/test_snapshot.py` → **521 passed, 11 skipped, 0 failed** (11 min 54 s).
- **Verified:** 2/2 new tests pass, and two mutations each fail the main test.

## Implementation Summary

**`views/fleet.js`:**
- When `!window.GATOR_SNAPSHOT`, the ⋮ menu starts with two items:
  - `button.menu-item.menu-open-workspace[data-action="open-workspace"]`, with `data-repo-name` and `data-repo-key` (both `escHtml`'d);
  - `a.menu-item.menu-open-browser-tab`, with `href="?repo=<escHtml(encodeURIComponent(name))>"`, `target="_blank"` and `rel="noopener"`.
- `bindOverflowMenus` dispatches `open-workspace` to `window.gatorOpenRepoInNewContext(name, key)`.
- The link has no action, so its default navigation proceeds. The existing click handler only stops propagation and closes the menu.

**`dashboard.js`:**
- **`gatorNavToRepo(name, key)`:** when the model is hydrated and `findByRepo(name, key)` finds a context other than the active one, `selectContext(existing.id, {focus: true})`. Otherwise `navigate("repo", …)` as before, which turns the current context into that repository's context.
- **`gatorOpenRepoInNewContext(name, key)`:**
  - with no workspace model (snapshot or not yet hydrated), it falls back to `gatorNavToRepo`;
  - an existing context is selected with focus;
  - otherwise `create({repo, repoKey, view: "repo"})` and select it with focus;
  - at the limit (`create` returns null), it shows the `.shell-notice` "Workspace limit reached (12). Close a workspace first." and nothing else changes.

**`dashboard.css`:** `a.menu-item { text-decoration: none; }`, so the link matches the button items. The existing `.overflow-menu .menu-item` rules already style it.

**`.gator/inbox.md`:** the Dashboard decision "Document tabs: dropped" gains a sentence distinguishing #80 workspace tabs, as the approved plan's assumption 5 promised.

## Charter Updates

In `.gator/charters/scripts-dashboard-ui.md`, the `renderFleet()` entry gains the tripwire "Opening actions (#80)". It covers:
- the two menu items, their classes and data, and that they are shown only outside snapshots;
- that the link carries no path or key;
- the row link's select-existing rule;
- `gatorOpenRepoInNewContext`'s three outcomes, including the limit notice;
- key identity, never row position;
- the pinning tests.

I checked it against the code.

## Verification

- **New tests** (`test_workspace_tabs.py`), both passing:
  - **`test_fleet_open_actions`:**
    1. From a fresh repository-less context on Fleet, "Open in new workspace tab" for alpha creates and selects alpha at Repo, with focus on its tab.
    2. Repeating it from the blank context selects the same alpha context (still 2 contexts).
    3. The alpha row link from the blank context also selects it.
    4. The beta row link opens beta in the current (blank) context.
    5. The browser-tab link has `href="?repo=alpha"`, `_blank` and `noopener`. Clicking it opens a page on alpha Repo with its own one-context strip, and the original strip is unchanged.
  - **`test_fleet_open_workspace_at_limit`:** with 12 seeded contexts, the action shows the exact notice; there are still 12 contexts, no alpha, and the URL is unchanged.
- **Mutation checks** (restored from a copy; I confirmed by grep):
  - the row link ignoring existing contexts → `test_fleet_open_actions` fails;
  - the new-workspace action ignoring existing contexts → it fails again.
- **Final approval sweep (plan):** `pytest tests/test_dashboard_ui/ tests/test_snapshot.py` → **521 passed, 11 skipped**, exit 0. The 11 skips are the existing POSIX and symlink `skipif` / `pytest.skip` cases in `test_content_transport_slice3.py`, which this change does not touch.

**Residue:**
- `.gator/commit_draft.md` is rewritten for the whole feature. It is in the working tree only, not staged, and the commit hook reads it.
- The pre-existing staged session snippet is unchanged.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp5 (5 of 5) — Fleet cross-context opening |
| Checkpoint base tree | `73f1221404c91f80c83e1c2d073eddcb79208aa3` |
| Generation | 5 |
| Staged tree (candidate) | `5fa96d3fbb68a3bbb0112e0286950f37e4b7a1fa` |
| Changed paths in this checkpoint | 6 (M 6) |
| Loop base HEAD | `aac105b1618b4a7ea87f37fb6d288da1e1268d12` |
| Loop base tree | `b74ac09fb57299f319beabf948a5ff00a619d99e` |
| Current HEAD | `aac105b1618b4a7ea87f37fb6d288da1e1268d12` (dev) |
| Changed paths vs loop base (cumulative) | 14 |
| Unstaged / untracked residue | 1 other + 24 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff 73f1221404c91f80c83e1c2d073eddcb79208aa3 5fa96d3fbb68a3bbb0112e0286950f37e4b7a1fa
```

Cumulative context (approved checkpoints plus this one): `git diff b74ac09fb57299f319beabf948a5ff00a619d99e 5fa96d3fbb68a3bbb0112e0286950f37e4b7a1fa`.

Changed paths in this checkpoint (status, path):

```text
M .gator/charters/scripts-dashboard-ui.md  [revisits an earlier checkpoint]
M .gator/inbox.md
M src/gator_command/scripts/dashboard/dashboard.css  [revisits an earlier checkpoint]
M src/gator_command/scripts/dashboard/dashboard.js  [revisits an earlier checkpoint]
M src/gator_command/scripts/dashboard/views/fleet.js
M tests/test_dashboard_ui/test_workspace_tabs.py  [revisits an earlier checkpoint]
```

Paths marked as revisiting an earlier checkpoint were also changed by an approved checkpoint; this is information for the Reviewer, not a prohibition.

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/commit_draft.md
```

Loop residue: 24 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
