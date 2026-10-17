# Implementation: #80 Checkpoint 4 — Workspace strip and context switching

## Executive Summary

- **What changed:** a full-width `nav#workspace-strip` sits above the sidebar and main pane, with one tab per workspace context, a labelled close button on each, and `+`.
  - Selecting a tab goes through `applyShellEntry()`, whose `showView()` tears the old view down, and records one history entry. Each entry now carries `ctx`, so Back undoes a tab selection.
  - Closing changes navigation state only.
- **Key decisions:**
  - Manual activation: arrow keys move focus only; Enter selects.
  - The strip is rebuilt only when what it shows changes, and focus is restored across a rebuild.
  - Selecting a context whose repository is no longer registered leaves it on Fleet without a repository.
  - The body is now a flex column, and `#sidebar-toggle` is anchored inside `#app-shell`.
- **Contract update to an existing pin:** `test_history_state_never_holds_tokens` listed the exact state keys. It now includes the planned `ctx` and checks its format.
- **Verified:**
  - all 28 workspace tests pass;
  - 189 of 190 tests pass across the responsive shell, Welcome, Loop workspace, Fleet layout, Docs and snapshot suites; the one failure was that exact-key pin, which passes after its update;
  - three deliberate code changes each made their test fail.

## Implementation Summary

**`workspace.js`:**
- **List operations:** `create(fields)` (null at 12), `select(id)`, `neighbourOf(id)` (right, else left), `remove(id)` and `count()`. They change the list and save, nothing else.
- **`renderStrip(container, {onSelect, onClose, onNew}, opts)`:**
  - **Markup:** a `div.workspace-tablist[role=tablist][aria-label="Open workspaces"]` of `div.workspace-item[role=presentation]`, each holding:
    - `button.workspace-tab[role=tab]` (`#ws-tab-<id>`, `aria-selected`, `aria-controls="app-shell"`, roving `tabindex`, `data-ctx`), labelled with the repository name or `—` (`title="No repository"`);
    - `button.workspace-tab-close` ("Close alpha workspace" / "Close workspace without repository", `tabindex` 0 on the active item, else -1).
  - Then `button.workspace-new` ("+"), disabled at 12 with the title "Workspace limit reached (12)". All text is set with `textContent`.
  - **Keyboard:** a `keydown` handler on the tablist handles Left/Right (wrapping), Home and End. It moves focus and the roving `tabindex` and never selects.
  - **Rebuilding:** only when `[activeId, ids, repos]` changes. Focus on a tab, close button or `+` is restored, falling back to the active tab. `focusActive` focuses the active tab even when nothing changed. The active tab is scrolled into view.
  - **Return value:** the active tab's element id.

**`dashboard.js`:**
- **History state:** `shellState()` adds `ctx` (the active context's id, null before hydration and in snapshots). `isShellEntry` accepts `ctx` absent, null or a string.
- **`popstate`:** under `restoring`, when `entry.ctx` names an open context other than the active one, `GatorWorkspace.select(entry.ctx)` runs first. Then `restoreShellState` runs as before.
- **`syncWorkspace()`** now also calls `renderWorkspaceStrip()`, which sets `#app-shell`'s `aria-labelledby`.
- **`selectContext(id, {force, focus})`:**
  1. `select` the context.
  2. If `validateRepo` fails, apply `{view: fleet, repo: null}` and show the notice. Otherwise apply the context's `{view, repo, repoKey, sub}` through `applyShellEntry`.
  3. `recordShell("pushState", sub)`.
  4. Re-render, with focus when asked.

  Because the repository is checked first, `applyShellEntry`'s own fallback (which rewrites the current entry) is never reached from a strip selection.
- **`newContext()`:** creates a repository-less Welcome context and selects it with focus.
- **`closeContext(id)`:**
  - inactive: `remove`, then re-render (no navigation, no history entry);
  - active: `neighbourOf`, `remove`, then select the neighbour with focus;
  - last: `create` a fresh Welcome context and select it.
- **`hydrateWorkspace()`:** after `load()`, it rewrites the current entry through `recordShell("replaceState", <kept sub>)`, so the landing entry names its context and the strip is drawn.
- **`init()` in snapshot mode:** hides the strip and removes `#app-shell`'s `role` and `aria-labelledby`.

**`dashboard.html`:** `nav#workspace-strip[aria-label="Workspaces"]` before `#app-shell`, which gains `role="tabpanel"`.

**`dashboard.css`:**
- `body` is a column flex box (`height: 100vh; overflow: hidden`).
- `#app-shell` changes from `height: 100vh` to `flex: 1; min-height: 0; position: relative`.
- The strip is `flex: 0 0 36px`, with `overflow-x: auto` and `nowrap`, plus a `[hidden]` rule.
- Tabs:
  - selected: `aria-selected="true"` gives weight 700 plus a 3px `currentColor` border-bottom; unselected: weight 400 with a transparent border;
  - hover;
  - `:focus-visible` outline;
  - disabled `+`.
- `#sidebar-toggle` changes from `position: fixed` to `absolute`, with the same offsets. I checked that there is no positioned ancestor between it and `#app-shell`.

## Charter Updates

`.gator/charters/scripts-dashboard-ui.md`:
- **State shape:** adds `ctx` and the `isShellEntry` rule.
- **Restoration:** a new "before step 1" rule for `entry.ctx`: select an open context with no push, else apply the entry to the active context, which drops its inactive duplicate.
- **The `GatorWorkspace` entry:** adds the list operations.
- **A new entry,** "Workspace strip — `renderStrip()` · `renderWorkspaceStrip()` / `selectContext()` / `newContext()` / `closeContext()`", covering the markup, manual activation and why, the rebuild and focus rules (including focusing even when nothing changed), the four select steps, the three close cases, the snapshot behaviour, the TRIPWIRE that inactive contexts are not live, and the pins.
- **Responsive shell:** a new "Body column (#80)" rule covering the strip row, `#app-shell` sizing, the toggle anchoring and the never-colour-alone selection style.

I checked all names against the code.

## Verification

- `pytest tests/test_dashboard_ui/test_workspace_tabs.py` → **28 passed**. The new tests for this checkpoint:
  - **`test_strip_spans_shell_above_sidebar`** at 1440×900 and 375×700, with 12 contexts:
    - the strip is at top 0, left 0, full width and 36 px high;
    - the sidebar, main pane and toggle are all below it;
    - the 12 tabs form one row and `+` is disabled;
    - neither the page nor its width scrolls;
    - at 375 px the strip scrolls horizontally.
  - **`test_strip_aria_keyboard_and_close_labels`:**
    - labels, `aria-selected`, roving `tabindex`, `role` and `aria-controls`;
    - the close-button labels and `tabindex`;
    - weight 700 against 400 and the 3 px underline;
    - `#app-shell` `role=tabpanel` with its `aria-labelledby`, plus the tablist and `+` labels;
    - the keys: ArrowRight moves focus without selecting and without a URL change; End; ArrowRight wraps; ArrowLeft; Home; then ArrowRight + Enter selects beta Docs, with focus on its tab.
  - **`test_switch_restores_each_context`:**
    - alpha Loop History, then `+` (repository-less, focus on the new tab), then Fleet → beta → Docs;
    - selecting alpha restores Loop with the History tab, the sidebar Loop item, the title and the URL;
    - selecting beta restores Docs;
    - Back re-selects the alpha context, with History.
  - **`test_only_active_loop_context_polls`:** alpha Loop polling, then select beta: 0 `/status` requests in 4 s. Select alpha again: 1–3 `/status` requests in 6.5 s (a 3 s interval; a leaked second interval would double it).
  - **`test_close_changes_navigation_only`:**
    - closing the inactive context changes neither the URL nor the selection;
    - closing the active beta selects alpha Loop and focuses its tab;
    - closing the last context gives one `—` Welcome context and an empty query;
    - only GET requests; the registry count is unchanged; alpha's loop stages are unchanged.
- `pytest test_responsive_shell.py test_welcome_ui.py test_loop_workspace.py test_fleet_layout.py test_docs_view.py tests/test_snapshot.py` → **189 passed, 1 failed** (5 min 22 s).
  - The failure was `test_history_state_never_holds_tokens`, an exact-key pin on history state that `ctx` (approved plan, decision 3) deliberately extends.
  - I updated it to expect `ctx` and to check `ctx` is null or `[a-z0-9]{1,16}`. Its token, prompt and artifact checks are unchanged. Re-run → passed.
  - No other test pins the exact key set (checked by grep).
- **Mutation checks** (each restored from a copy; I confirmed the restore by grep):
  - arrow keys also clicking (automatic activation) → `aria_keyboard` fails;
  - closing an inactive context navigates → `close_changes_navigation_only` fails;
  - removing the `popstate` `ctx` selection → `switch_restores_each_context` fails.
- **Found during testing:** after `+`, focus stayed on `+`. The strip had already been rebuilt by the sync inside the selection, so the final `focusActive` render took the unchanged-strip early return. Fixed: an unchanged strip still honours `focusActive`. The fix is recorded in the charter.
- **Deferred to final approval:** the full `tests/test_dashboard_ui/`.

**Residue:** `.gator/commit_draft.md` (checkpoints 1–4 body) is in the working tree only. The pre-existing staged snippet is unchanged.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp4 (4 of 5) — Workspace strip and context switching |
| Checkpoint base tree | `dbf9ee67c96d82ba10a84da764db3d7cbe5e5c0a` |
| Generation | 4 |
| Staged tree (candidate) | `73f1221404c91f80c83e1c2d073eddcb79208aa3` |
| Changed paths in this checkpoint | 7 (M 7) |
| Loop base HEAD | `aac105b1618b4a7ea87f37fb6d288da1e1268d12` |
| Loop base tree | `b74ac09fb57299f319beabf948a5ff00a619d99e` |
| Current HEAD | `aac105b1618b4a7ea87f37fb6d288da1e1268d12` (dev) |
| Changed paths vs loop base (cumulative) | 12 |
| Unstaged / untracked residue | 1 other + 22 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff dbf9ee67c96d82ba10a84da764db3d7cbe5e5c0a 73f1221404c91f80c83e1c2d073eddcb79208aa3
```

Cumulative context (approved checkpoints plus this one): `git diff b74ac09fb57299f319beabf948a5ff00a619d99e 73f1221404c91f80c83e1c2d073eddcb79208aa3`.

Changed paths in this checkpoint (status, path):

```text
M .gator/charters/scripts-dashboard-ui.md  [revisits an earlier checkpoint]
M src/gator_command/scripts/dashboard/dashboard.css
M src/gator_command/scripts/dashboard/dashboard.html  [revisits an earlier checkpoint]
M src/gator_command/scripts/dashboard/dashboard.js  [revisits an earlier checkpoint]
M src/gator_command/scripts/dashboard/workspace.js  [revisits an earlier checkpoint]
M tests/test_dashboard_ui/test_loop_workspace.py
M tests/test_dashboard_ui/test_workspace_tabs.py  [revisits an earlier checkpoint]
```

Paths marked as revisiting an earlier checkpoint were also changed by an approved checkpoint; this is information for the Reviewer, not a prohibition.

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/commit_draft.md
```

Loop residue: 22 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
