# Implementation: #56 Loop Create/History workspaces — Checkpoint 2 (Loop navigation, shell-owned history and Commits label)

## Executive Summary

- **What changed:**
  - The Loop sidebar has accessible Create/History tabs. Create shows an active-loop explanation with **Open active loop** instead of a form that cannot start, and History lists only terminal loops.
  - `dashboard.js` now owns browser history for every view through state-only entries, a single `popstate` → `restoreShellState()` (validate → hydrate repository → dispatch) and `window.GatorShell`. The Loop view contributes only sub-state.
  - The global nav label "History" becomes "Commits".
- **Key decisions:**
  - The tablist is built once per mount, so polls never destroy it.
  - A repository change on restore always remounts.
- **Deviations to review:**
  - `views/repo.js` already pushes its own history entries. The plan said none existed.
  - `views/history.js` had a stale-write race that Back exposed.

  Both are handled minimally; see Implementation Summary §5.
- **Verified:** the 20 focused Verify tests pass, and the 240 loop and shell UI tests pass.

## Implementation Summary

1. **Loop tabs (`views/loop.js`, `renderLoopSidebar` / `buildSidebarTabs` / `applyTabState` / `switchTab`).**
   - **Markup:** `role="tablist"` (`aria-label="Loop workspace"`) with `#loop-tab-create` / `#loop-tab-history` (`role="tab"`, `aria-controls`) and `#loop-panel-create` / `#loop-panel-history` (`role="tabpanel"`, `aria-labelledby`).
   - **Built once per mount.** Each later render (including every poll) rewrites only the two panels' contents, so the tablist node and a focused tab survive polls (pinned).
   - **Attribute writes:** `applyTabState()` writes `aria-selected`, roving `tabindex` and the inactive panel's `hidden` only when they differ.
   - **Keyboard:** Left/Right (wrapping), Home and End activate and focus the tab.
   - **`_state.view`** (`create | history`) is new. `_state.mode` keeps its meaning, and `teardownLoopView()` resets `view`.
   - **Create panel:** an always-actionable `.loop-sidebar-create` and the "Active" section. The disabled/conflict sidebar state and its CSS were removed.
   - **History panel:** the "History" section with terminal loops only. Both panels keep the `.loop-sidebar-section(-header)` markup.
   - **Switching:**
     - The Create tab switches the main content to the creation workspace, unless it is already showing, so a half-filled form survives.
     - The History tab changes only the list, and the main content stays until a card is chosen.
     - `selectLoop(id)` sets inspect mode and the tab that matches the loop's terminal state.
2. **Active-loop explanation (`renderCreateWorkspace` → `renderActiveLoopExplanation`).** With any active loop it renders:
   - "A **<Mode>** loop ‘<feature>’ is active (<stage>). Only one loop runs at a time.";
   - the mode and stage badges and the counter text;
   - `button.loop-sidebar-open-active` **Open active loop**, which selects the loop and focuses its `h3`.

   With no active loop the form renders exactly as before, and the 409 race path is kept.
3. **Shell-owned history (`dashboard.js`).**
   - **`shellState(sub)`** builds `{gatorDashboard: 1, view, repo, repoKey, sub}`. `cleanSub()` keeps only `{view, mode, loopId}`, so no other field can enter.
   - **`navigate()`** = `showView()` + `pushState`. The sidebar handler and `gatorNavToRepo` use it. `init()` calls `replaceState`, and `doRefresh` still uses `showView` with no push.
   - **`window.GatorShell`:**
     - `pushSubState(sub)`: Loop only, and not while restoring;
     - `replaceSubState(sub)`: Loop only;
     - `isRestoring()`.
   - **`setActiveRepo(name, key)`** is extracted from the `repo` branch (key resolution is unchanged). **`clearActiveRepo()`** is its inverse.
   - **`fleetRepos()`** is a shared helper. The `repo` branch's local `const fleetRepos` was replaced by it; the shadowed name caused a TDZ error during development.
   - **`state.mountedLoopKey`** records the repo key a mounted Loop view uses (`undefined` otherwise). `showView` resets it, and the `loop` branch sets it before calling `views.loop(…, initialSub)`.
   - **`restoreShellState(entry)`**, the single path, runs under `restoring` (`finally`-cleared):
     1. `isShellEntry` validation.
     2. **Hydration before dispatch.** The fleet repo matching name and recorded key (else name only) is authoritative → `setActiveRepo`. An unregistered repo → `clearActiveRepo`, Fleet, `.shell-notice` "That repository is no longer registered." and `replaceState` to Fleet. A null repo → `clearActiveRepo`.
     3. **Dispatch.** A same-repo mounted Loop → `views.loop.restore(sub)`. Otherwise `showView(view, repo, activeRepoKey, {initialSub})`.
4. **Loop sub-state (`views/loop.js`).**
   - `currentSub()` records a handoff as inspect of that loop.
   - `shellPush()` is called on user selections only: tab switch, card select, Create Loop, Open active loop, the 409 link, create → handoff, and handoff → Open loop workspace.
   - `applySub()` (falls back to `applyDefaultSelection()` when the loop no longer exists). The mount accepts `initialSub` and calls `shellReplace()` for the landing state.
   - **`views.loop.restore(sub)`** bumps `generation`, re-renders, loads or renders the main content, and focuses the main heading. It never pushes. No global listener is registered.
5. **Deviations from the approved plan (non-blocking; recorded as assumptions):**
   - **`views/repo.js` history entries.** The plan's Context Checked said there was no `pushState`/`popstate` anywhere. In fact `repo.js` pushes `{view: "repo", repo, searchQuery|filePath}` entries (cross-document search) and applies them through its own controller-scoped `popstate` listener while mounted, removing it in `teardownRepoView()`.
     - I did **not** change `repo.js`. The shell handler treats these unmarked entries as follows: if that repo's Repo/Docs view is mounted, it leaves them to `repo.js`; otherwise it restores that Repo view, so Back never goes dead after a search.
     - The plan's "Repo/Docs internal browsing is not recorded by the shell" still holds. Making `repo.js` emit shell entries would be a later change.
   - **`views/history.js` stale write.** The commits fetch wrote into `#view-slot` unconditionally. Back from Commits to Loop resolved the fetch after the Loop mount and wiped it, which failed the plan's test 7b.
     - The fix keeps the "Loading history..." node and drops the result (`stale()`) when it is detached.
     - This is a pre-existing race that history navigation made easy to hit. There is no behaviour change otherwise.
6. **Commits label.** In `dashboard.html` the nav text is "Commits". In `VIEW_META.history.title` it is "Commits", and the fallback text is "Commits view not available." The route `history`, `data-view="history"`, `views/history.js` routing and the endpoint are unchanged.
7. **CSS (`dashboard.css`):**
   - `.loop-subnav` / `.loop-subnav-tab`: the selected tab is shown by weight 700 plus a 3px underline, not colour; it wraps on narrow screens and has a `focus-visible` outline.
   - `.loop-create-active-*` and the `.loop-sidebar-open-active` button style.
   - `.shell-notice`: dashed border and bold.

## Charter Updates

`.gator/charters/scripts-dashboard-ui.md`:
- **`navigate()` entry**, renamed to `navigate() / showView() / restoreShellState() / setActiveRepo() / clearActiveRepo() / window.GatorShell`, with a new **Shell-owned history (#56)** tripwire. It covers the state shape, the no-token rule, `navigate` versus `showView`, the GatorShell API, the repository helpers, the restoration steps, `repo.js` entry handling and no re-entrancy.
- **Loop workspace:** the summary line now describes the tabbed sidebar.
  - **Secondary sidebar (#56 tabs)** replaces the old three-section rule.
  - **Active-loop explanation (#56)** and **Loop history sub-state (#56)** are new tripwires.
- **`renderHistory()`:** the `<-` line notes the "Commits" label and the unchanged route. A new **Stale-render guard (#56)** tripwire is added.
- **Checked against the code:** the function names `navigate`, `showView`, `restoreShellState`, `setActiveRepo`, `clearActiveRepo`, `shellState`, `cleanSub`, `isShellEntry`, `buildSidebarTabs`, `applyTabState`, `switchTab`, `selectLoop`, `renderActiveLoopExplanation`, `currentSub`, `applySub`, `applyDefaultSelection`, `focusMainHeading`, `shellPush` / `shellReplace` and `views.loop.restore`, and the ids and classes, match the staged diff.

`.gator/commit_draft.md` gains a Checkpoint 2 entry.

## Verification

- `python -m pytest tests/test_dashboard_ui/test_loop_workspace.py -k "subnav or create or back or history_state or sidebar or commits or tabs" -q`: **20 passed**. The plan's `-k` set plus `tabs` picks up the poll-survival pin. The new tests:
  - `test_loop_subnav_tabs`: roles, `aria-selected`, roving tabindex, panel `hidden`, Right/Home/End/wrap keyboard with focus; History holds exactly the 3 terminal loops and the active loop appears only in Create.
  - `test_loop_tabs_survive_polls`: the same tablist node and a focused tab survive more than two polls.
  - `test_sidebar_create_with_active_loop`: replaces B4 (the old disabled-state assertion). Create stays actionable and leads to the explanation.
  - `test_create_with_active_loop_explains_and_opens`: mode + feature + stage text, no form fields, and Open active loop selects the loop and focuses its heading.
  - `test_create_without_active_loop_unchanged`: the form renders with the Create tab selected.
  - `test_loop_back_forward_within_loop` (7a): restores the History tab and the loop header, `history.length` is unchanged by the restore, focus is on the heading, and Forward returns to Create.
  - `test_back_restores_loop_after_leaving[history|fleet]` (7b/7c): Back from Commits or Fleet restores the Loop with the History tab and the Coding badge; Forward leaves again.
  - `test_back_past_loop_entry_restores_shell_views` (7c): Loop → Repo → Fleet, and the landing Fleet entry restores the dimmed tabs.
  - `test_back_restores_loop_in_its_own_repository` (7e): alpha history loop → Fleet → beta → Back ×2 gives alpha's label, selected card and heading. Every `/loops` request after the Back uses alpha's key and none uses beta's. Forward ×2 returns to beta's Repo view and label.
  - `test_back_to_unregistered_repo_falls_back_to_fleet` (7f): an injected ghost-repo entry → Fleet with the notice, the entry replaced to Fleet, and no `/loops` request.
  - `test_history_state_never_holds_tokens` (7d): every `pushState`/`replaceState` argument, recorded by an init script, plus every walked `history.state`, has exactly the shell shape, no `glp_`, and no prompt or artifact text. This includes a prompt-copy click.
  - `test_commits_nav_label`: the nav reads "Commits", the topbar title is "Commits", and the route is `history`.
- `python -m pytest tests/test_dashboard_ui/test_responsive_shell.py tests/test_dashboard_ui -k "loop or responsive or shell" -q`: **240 passed**. This covers all loop UI files and the responsive-shell suite, which navigates by `data-view="history"`, not by label.
- The checkpoint 1 pins (mode badges, mutation-free header) are included in the 240.
- **Known gaps:**
  - The full `tests/test_dashboard_ui -q` and `tests -q` runs are reserved for final approval, per the plan.
  - `repo.js` search entries restore only the Repo view (not the search) when Back lands on them from another view; see Implementation Summary §5.
- **Staged-tree note:** unchanged from checkpoint 1. The pre-existing `.gator/session-snippets/…json` stays staged as designed, and `.gator/.gator-version` / `.gator/runtime-pin.json` stay unstaged and outside the candidate.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp2 (2 of 3) — Loop navigation, shell-owned history and Commits label |
| Checkpoint base tree | `b0e992c03ff4d4ca966405b433857c6bd8d20239` |
| Generation | 1 |
| Staged tree (candidate) | `b3fdd094276482b5a8d7cbb72df409380d8eefec` |
| Changed paths in this checkpoint | 8 (M 8) |
| Loop base HEAD | `34a9d0e417d431853181de99088547a9fce86698` |
| Loop base tree | `7e01b49b16a02cb832fd21eda069d58736482b40` |
| Current HEAD | `34a9d0e417d431853181de99088547a9fce86698` (dev) |
| Changed paths vs loop base (cumulative) | 13 |
| Unstaged / untracked residue | 3 other + 95 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff b0e992c03ff4d4ca966405b433857c6bd8d20239 b3fdd094276482b5a8d7cbb72df409380d8eefec
```

Cumulative context (approved checkpoints plus this one): `git diff 7e01b49b16a02cb832fd21eda069d58736482b40 b3fdd094276482b5a8d7cbb72df409380d8eefec`.

Changed paths in this checkpoint (status, path):

```text
M .gator/charters/scripts-dashboard-ui.md  [revisits an earlier checkpoint]
M .gator/commit_draft.md  [revisits an earlier checkpoint]
M src/gator_command/scripts/dashboard/dashboard.css  [revisits an earlier checkpoint]
M src/gator_command/scripts/dashboard/dashboard.html
M src/gator_command/scripts/dashboard/dashboard.js
M src/gator_command/scripts/dashboard/views/history.js
M src/gator_command/scripts/dashboard/views/loop.js  [revisits an earlier checkpoint]
M tests/test_dashboard_ui/test_loop_workspace.py  [revisits an earlier checkpoint]
```

Paths marked as revisiting an earlier checkpoint were also changed by an approved checkpoint; this is information for the Reviewer, not a prohibition.

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/.gator-version
.gator/runtime-pin.json
.gator/session-snippets/2026-10-06-gator-2d6996c33c4b8.json
```

Loop residue: 95 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
