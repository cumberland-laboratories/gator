# Implementation: Dashboard Welcome Workspace (#72) — Checkpoint 1

## Executive Summary

- **What changed:** Added a shared main-pane tab bar style (`.gator-tabbar` / `.gator-tab`). Loop's Create / History tablist moved from the Loop sidebar into a full-width `#loop-tabbar` above a new `.loop-workspace-body` row.
- **Key decision:** As the approved plan says, the tablist is built once per mount (`buildLoopTabs`). The two `role="tabpanel"` lists stay in `#loop-sidebar-nav` (`ensureLoopPanels`). `_state.view`, `switchTab()` semantics, keyboard handling, shell sub-state and polling are unchanged.
- **Main risk:** Breaking focus or poll stability, or the Loop height chain. Both are covered: `test_loop_tabs_survive_polls` and the full Loop workspace and responsive-shell files pass.
- **Verified:** The checkpoint's focused command passes 20/20. The full `test_loop_workspace.py` and `test_responsive_shell.py` pass 133/133.

## Implementation Summary

- `dashboard.css`
  - New `.gator-tabbar`: a full-width block that owns the 1px baseline, with `padding: 0 24px`.
  - New `.gator-tabbar [role="tablist"]`: flex, wraps when narrow.
  - New `.gator-tab`: 13px label; weight 400 with a transparent 3px underline. When selected, weight 700 with a `currentColor` underline, plus a `:focus-visible` outline.
  - The old `.loop-subnav` / `.loop-subnav-tab*` rules are removed; the class names remain as JS/test hooks.
  - `.loop-workspace` is now a column. The new `.loop-workspace-body` (`flex:1; min-height:0`) holds the old row layout, and the ≤768px stacking rule moved to it.
- `views/loop.js`
  - The mount skeleton is now `.loop-workspace` → `#loop-tabbar.gator-tabbar.loop-tabbar` + `.loop-workspace-body` (`#loop-sidebar-nav` + `#loop-main-content`). It calls `buildLoopTabs(container)` immediately after writing the skeleton.
  - `buildSidebarTabs(listEl)` is replaced by two functions:
    - `buildLoopTabs(container)`: the same tablist markup (with an added `gator-tab` class) and the same click/keydown handlers, written into `#loop-tabbar`;
    - `ensureLoopPanels(listEl)`: replaces the sidebar's "Loading…" placeholder with the two tabpanels once per mount, and is a no-op afterwards.
  - `applyTabState(root)` now receives the view container. It skips quietly until both the tab and its panel exist (the short window before `/loops` resolves). It still writes only values that differ.
  - The `switchTab()` else branch and `renderLoopSidebar()` call `applyTabState(container)`. Nothing else changed.
- `tests/test_dashboard_ui/test_loop_workspace.py`
  - `_tab_state` now asserts that the tablist is in `#loop-tabbar` and not in `#loop-sidebar-nav`.
  - New `test_loop_tabbar_spans_main_pane`. It checks:
    - the bar runs from the Loop sidebar's left edge to the main pane's content edge (`#view-slot` right minus its 28px padding, ±1px) and sits above both columns;
    - the baseline is 1px;
    - the selected tab has weight ≥ 700 and a 3px underline, while the unselected tab has weight 400 and a transparent underline;
    - on `beta` (no loops), a half-filled `#loop-feature-input` survives History → Create.

  On the pane-edge measurement: the first run compared against `#view-slot`'s border box and failed by its 28px padding. The pane's content edge is the right reference, because Loop content (and Welcome in checkpoint 2) is laid out inside that padding.

## Charter Updates

- `.gator/charters/scripts-dashboard-ui.md`
  - **Loop workspace heading:** the function list now starts `buildLoopTabs() / ensureLoopPanels() / applyTabState() / switchTab()`. The purpose line describes the full-width tab bar plus the list sidebar.
  - **Tabs bullet:** "Secondary sidebar (#56 tabs)" is rewritten as "Create / History tabs (#56; main-pane bar since #72)". It covers the layout chain, `buildLoopTabs` built once per mount, panels kept in the sidebar via `ensureLoopPanels`, `applyTabState(container)`, and a "Pinned by" line naming the three tests. The Keyboard, `_state.view`, panel content, `switchTab()`, Selection and Mount-default sub-bullets are unchanged, because their behaviour is unchanged.
  - **Responsive shell entry:** two new tripwires. One describes the shared `.gator-tabbar` / `.gator-tab` treatment (selected = weight + underline, never colour alone; `.loop-subnav*` styles removed, names kept as hooks). The other describes the Loop height chain (`.loop-workspace` column → `.loop-workspace-body` `flex:1; min-height:0`).
- **How I checked them against the code:** I grepped `buildSidebarTabs` (no references left) and `applyTabState` / `ensureLoopPanels` / `buildLoopTabs` call sites in `views/loop.js`, and `loop-subnav` in `dashboard.css` (none left).
- `scripts-dashboard.md`, `scripts-cross-cutting.md` and `INDEX.md` need no change at this checkpoint. The snapshot order changes in checkpoint 2.
- **Commit draft:** `.gator/commit_draft.md` is populated with the message, `change-type: feature`, `significance: minor` (both in the pre-commit enums), and checkpoint 1 log bullets. No significance check was run, because nothing touches a public API, a cross-module invariant, a TRIPWIRE or security-relevant code.

## Verification

- `python -m pytest tests/test_dashboard_ui/test_loop_workspace.py -k "subnav or tabs or tabbar or back or history_tab or sidebar or create"` → **20 passed**, 90 deselected.
- An extra sanity check, because the workspace wrapper changed: `python -m pytest tests/test_dashboard_ui/test_loop_workspace.py tests/test_dashboard_ui/test_responsive_shell.py` → **133 passed**.
- **Not run at this checkpoint:** the other Dashboard UI files (`test_loop_coding_ui`, `test_loop_markdown_ui`, `test_loop_refresh_ui`, `test_loop_liveness_ui`, `test_loop_attention_ui`, `test_loop_brief_ui`, the content transport files and `test_fleet_layout`). Per the plan's ladder, they run once at final approval. Three of them read `.loop-workspace`'s `dataset.polling`, which this change keeps on the same element.
- **Residue note:** the index also holds `.gator/session-snippets/2026-10-10-gator-9db8fd0ef4693.json`. It was already staged before this loop started (an evidence snippet from the previous commit), and the next real commit is expected to sweep it up. `.gator/.gator-version` and `.gator/runtime-pin.json` are modified but intentionally left unstaged: they are not part of this change.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp1 (1 of 2) — Shared main-pane tab bar with Loop relocation |
| Checkpoint base tree | `597eaa5f4fbfbd348d04851ec24d07428133e403` |
| Generation | 0 |
| Staged tree (candidate) | `43c2eadfb246e26716469e9f88c14db37bb1816e` |
| Changed paths in this checkpoint | 6 (A 1, M 5) |
| Loop base HEAD | `9db8fd0ef4693bcc124e75de8776929c28793f23` |
| Loop base tree | `597eaa5f4fbfbd348d04851ec24d07428133e403` |
| Current HEAD | `9db8fd0ef4693bcc124e75de8776929c28793f23` (dev) |
| Changed paths vs loop base (cumulative) | 6 |
| Unstaged / untracked residue | 2 other + 10 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff 597eaa5f4fbfbd348d04851ec24d07428133e403 43c2eadfb246e26716469e9f88c14db37bb1816e
```

Cumulative context (approved checkpoints plus this one): `git diff 597eaa5f4fbfbd348d04851ec24d07428133e403 43c2eadfb246e26716469e9f88c14db37bb1816e`.

Changed paths in this checkpoint (status, path):

```text
M .gator/charters/scripts-dashboard-ui.md
M .gator/commit_draft.md
A .gator/session-snippets/2026-10-10-gator-9db8fd0ef4693.json
M src/gator_command/scripts/dashboard/dashboard.css
M src/gator_command/scripts/dashboard/views/loop.js
M tests/test_dashboard_ui/test_loop_workspace.py
```

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/.gator-version
.gator/runtime-pin.json
```

Loop residue: 10 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
