# Implementation: Dashboard Welcome Workspace (#72) — Checkpoint 1 (revision 1)

## Executive Summary

- **What changed:** The shared main-pane tab bar style (`.gator-tabbar` / `.gator-tab`) and the move of Loop's Create / History tablist into a full-width `#loop-tabbar` are unchanged from generation 0. This revision adds the significance check that was wrongly skipped.
- **Finding 1 (addressed):** The change rewrites the #56 Loop-tab TRIPWIRE, so it is now classified as significance-triggering (`significance: notable`). The steelman and the compatibility assessment are recorded in `commit_draft.md` and below, to be surfaced to the Architect before the final commit.
- **Concrete fix found by the check:** The tablist now exists before `/loops` resolves, a window the old sidebar-built tablist never had. A click in that window ran `switchTab()` against stale `_state` and could push a history entry. Fixed with a one-line inert guard, and pinned by a new test.
- **Verified:** The focused command plus the new test pass 21/21. The new test fails when the guard is removed. Generation 0's full Loop workspace and responsive-shell run passed 133/133.

## Response to Findings

### Finding 1: Required significance check is incorrectly skipped — **Accepted.**
The `! **Secondary sidebar (#56 tabs)**` entry is a charter TRIPWIRE, and this checkpoint rewrites it. The generation 0 statement that no TRIPWIRE was touched was wrong.

The check has now been run (see "Significance Check" below). It produced one concrete code change, the inert guard, which is staged here with its test and charter line. The steelman and compatibility assessment are recorded in `.gator/commit_draft.md`. They are marked "to be surfaced to the Architect before the final commit", and I am surfacing them to the Architect in my session now.

## Significance Check

**Steelman (the strongest case against this change):**
1. **ARIA relationships now cross containers.** The tablist is in `#loop-tabbar` and its tabpanels are in `#loop-sidebar-nav`. Assistive technology that ignores `aria-controls` loses the old adjacency between tabs and panels.
2. **The tablist now exists before `/loops` resolves.** The old tablist was built inside the sidebar on the first render, so this window is new. During it, `_state.mode` and `_state.loops` still belong to the previous mount (possibly another repository). A click would render stale content and push a history entry ahead of the mount's landing `shellReplace()`. **This check found a real regression here, and it is fixed** (below).
3. **The flex and scroll chain changes.** `.loop-workspace` becomes a column, a new `.loop-workspace-body` holds the old row layout, and a fixed-height bar sits above both columns. That reduces vertical space, most noticeably on mobile, where the list sidebar is capped at 30vh.
4. **Removed CSS can break out-of-tree code silently.** Deleting the `.loop-subnav*` rules breaks any external style or selector that targeted the sidebar tabs.
5. **A less invasive alternative existed:** restyling the tabs in place in the sidebar. The approved sketch rejects it explicitly, because it asks for the same main-pane treatment as Welcome.

**Compatibility:**
- No public API, CLI, HTTP route, schema, or history-state change.
- `_state.view`, the shell `sub` shape `{view, mode, loopId}` and Back/Forward entries are unchanged.
- The DOM change is internal to the Dashboard. Only tests targeted the old tablist location, and they are updated here.
- This is a semver-minor UI change.

**Mitigations:**
- The tablist precedes its panels in DOM order.
- Polls never touch the tablist (`test_loop_tabs_survive_polls`).
- Pre-load clicks are inert (`test_loop_tabs_inert_until_loops_load`).
- The full Loop workspace and responsive-shell files pass.

**Decision:** Architect-owned at the final commit (proceed, adjust, revert or defer).

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

- **Revision 1 — `views/loop.js` `switchTab()`:** returns early while `#loop-panel-create` does not exist yet (it appears with the first `/loops` response, via `ensureLoopPanels`). Mouse and keyboard activation both route through `switchTab()`, so both are covered.
- **Revision 1 — new test `test_loop_tabs_inert_until_loops_load`:** it holds the `/loops` request, clicks History, and asserts that `history.length` is unchanged and no panel exists yet. It then releases the request and asserts the mount lands on its default (Create selected) without adding a history entry. Mutation-checked: with the guard removed, the test fails.

## Charter Updates

- `.gator/charters/scripts-dashboard-ui.md`
  - **Loop workspace heading:** the function list now starts `buildLoopTabs() / ensureLoopPanels() / applyTabState() / switchTab()`. The purpose line describes the full-width tab bar plus the list sidebar.
  - **Tabs bullet:** "Secondary sidebar (#56 tabs)" is rewritten as "Create / History tabs (#56; main-pane bar since #72)". It covers the layout chain, `buildLoopTabs` built once per mount, panels kept in the sidebar via `ensureLoopPanels`, `applyTabState(container)`, and a "Pinned by" line naming the pinning tests (four after revision 1). The Keyboard, `_state.view`, panel content, `switchTab()`, Selection and Mount-default sub-bullets are unchanged, because their behaviour is unchanged.
  - **Responsive shell entry:** two new tripwires. One describes the shared `.gator-tabbar` / `.gator-tab` treatment (selected = weight + underline, never colour alone; `.loop-subnav*` styles removed, names kept as hooks). The other describes the Loop height chain (`.loop-workspace` column → `.loop-workspace-body` `flex:1; min-height:0`).
- **How I checked them against the code:** I grepped `buildSidebarTabs` (no references left) and `applyTabState` / `ensureLoopPanels` / `buildLoopTabs` call sites in `views/loop.js`, and `loop-subnav` in `dashboard.css` (none left).
- `scripts-dashboard.md`, `scripts-cross-cutting.md` and `INDEX.md` need no change at this checkpoint. The snapshot order changes in checkpoint 2.
- **Revision 1 charter changes:** a new "Inert until loaded (#72)" sub-bullet under the Loop tabs TRIPWIRE. It covers the guard, the reason for it, and the cross-container ARIA relationship with DOM order. The "Pinned by" line adds `test_loop_tabs_inert_until_loops_load`. I checked it by grepping the guard in `switchTab()`.
- **Commit draft:** `significance` is raised from `minor` to `notable` (the value is in the pre-commit `VALID_SIGNIFICANCE` enum). Two log bullets are added: the inert guard, and the full significance check (steelman, compatibility, mitigations, and "to be surfaced to the Architect before the final commit").

## Verification

- **Revision 1:** `python -m pytest tests/test_dashboard_ui/test_loop_workspace.py -k "subnav or tabs or tabbar or back or history_tab or sidebar or create or inert"` → **21 passed**, 90 deselected.
- **Revision 1 mutation check:** with the `switchTab()` guard line replaced by a comment, `-k inert` → **1 failed**. The guard was restored and the staged file verified.
- **Generation 0:** the checkpoint's focused command → 20 passed.
- **Generation 0 sanity run**, because the workspace wrapper changed: `python -m pytest tests/test_dashboard_ui/test_loop_workspace.py tests/test_dashboard_ui/test_responsive_shell.py` → **133 passed**. Revision 1 changes only an early return in `switchTab()` that applies before the panels exist, so it was not rerun.
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
| Generation | 1 |
| Staged tree (candidate) | `7778f63837b285d2bc992967fa3dda889090aed3` |
| Changed paths in this checkpoint | 6 (A 1, M 5) |
| Loop base HEAD | `9db8fd0ef4693bcc124e75de8776929c28793f23` |
| Loop base tree | `597eaa5f4fbfbd348d04851ec24d07428133e403` |
| Current HEAD | `9db8fd0ef4693bcc124e75de8776929c28793f23` (dev) |
| Changed paths vs loop base (cumulative) | 6 |
| Unstaged / untracked residue | 2 other + 14 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff 597eaa5f4fbfbd348d04851ec24d07428133e403 7778f63837b285d2bc992967fa3dda889090aed3
```

Cumulative context (approved checkpoints plus this one): `git diff 597eaa5f4fbfbd348d04851ec24d07428133e403 7778f63837b285d2bc992967fa3dda889090aed3`.

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

Loop residue: 14 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
