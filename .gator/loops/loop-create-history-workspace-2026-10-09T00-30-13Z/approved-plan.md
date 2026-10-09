# Implementation Plan: #56 Clear Loop Create, Active, and History Workspaces

## Executive Summary

- **Proposal:** restructure the Dashboard Loop area into two loop-local views, **Create** (which reaches the active loop) and **History** (terminal loops only), using an accessible tab sub-navigation in the existing loop sidebar.
  - Show one central **mode badge** (Planning / Coding / Planning · legacy) on every header and card.
  - Replace the bare **Copy Draftor/Reviewer prompt** buttons with a labelled **Participant recovery** disclosure that opens only when a recovery need is detected.
  - Rename the global commit timeline **History → Commits** (label only).
- **Key decisions:**
  - Recovery need uses facts the browser already receives (`status.roles[r].joined` and the allowlisted liveness `state`). A joined participant with no watcher (`not_registered`, e.g. a Codex/`wait` participant) is never treated as absent, per #52.
  - The only server change is one additive `/loops` field, `mode_legacy`, because the list normalizes a missing `mode` to `planning` and cannot otherwise show the legacy fallback.
- **Main risk:** existing Playwright tests pin the old sidebar sections and prompt buttons. The plan keeps their selectors where the behavior survives (`.loop-prompt-copy`, the section headers inside tab panels) and updates the rest deliberately.
- **Revision 1:** browser history is now owned by the shell (`dashboard.js`). It pushes and restores a state for every Dashboard view; the Loop view only contributes optional sub-state through `window.GatorShell` and never installs its own `popstate` listener. Back/Forward across leaving the Loop view is tested end to end. **Revision 2:** one `restoreShellState()` path hydrates the recorded repository (`setActiveRepo` / `clearActiveRepo`) before dispatching any view, and a cross-repository Back test covers it.
- **Verification:** three responsibility checkpoints, each with focused Playwright and unit tests. The full Dashboard UI suite runs once at final approval.

## Summary

The plan implements the sketch's information architecture inside the existing `views/loop.js` state machinery, with no change to loop semantics, tokens, liveness or coding checkpoints.
- **Navigation:** Create/History tabs. Create explains and links the active loop instead of showing a disabled form, and History lists only terminal loops.
- **Mode labels:** one projection function feeds every header and card.
- **Recovery:** the copy-prompt buttons move into a "Participant recovery" section with in-place guidance and the credential warning. It opens automatically only when a role has not joined or its watcher is stale or released.
- **Back/forward:** the shell owns history for all views, and the Loop view adds its tab/selection as sub-state. Back/forward works within Loop and across leaving and returning to it. Entries are state-only, with no URL change.
- **Commits:** the global "History" nav label becomes "Commits"; its route and data are unchanged.

## Response to Review Findings (round 1)

- **Finding 1 (High): loop-local browser history has no owner after leaving the Loop view. Accepted.**
  - Browser history moves to the shell. `dashboard.js` owns `pushState`, `replaceState` and the single `popstate` handler for every view.
  - The Loop view contributes optional `sub` state through a narrow `window.GatorShell` API and exposes `views.loop.restore(sub)`. It never registers a listener, so `teardownLoopView()` removes only Loop-local resources.
  - Restoration runs under a shell `restoring` flag and never pushes.
  - New end-to-end test: select a history loop → Commits → Back restores the Loop view with that selection → Forward returns to Commits. A Fleet variant and a no-token check on every `history.state` are included. See decision 5, Change 2 and tests 7a–7d.

## Response to Review Findings (round 2)

- **Finding 1 (High): popstate restoration does not establish the recorded repository for Loop entries. Accepted.**
  - Today's `repo` branch state updates move into one shell helper, `setActiveRepo(name, key)`, plus its inverse `clearActiveRepo()`.
  - A single `restoreShellState(entry)` validates the entry, **hydrates the repository context before any view dispatch** (from fleet data; an unregistered repo falls back to Fleet with a notice), then dispatches.
  - `showView` stays a renderer, and its `loop`/`docs` branches read the hydrated shell state. A repository change always remounts the Loop view; the no-remount fast path applies only after hydration and only for the same repository key the Loop view mounted with.
  - New tests: 7e covers the reviewer's sequence (repo A history loop → repo B → Back restores A's Loop with A's API key, card, heading and sidebar label → Forward returns to B), and 7f covers an unregistered repo. The no-token check (7d) still covers every state.
  - See decision 5, Change 2 and the Testing section.

## Context Checked

- No Architect brief: `gator loop status` lists none for this loop.
- `sketch.md` (this loop; issue #56).
- Protocol and formats: `.gator/.includes/procedures/gator-loop-protocol.md`, `.gator/.includes/reference-notes/loop-artifact-formats.md`, `.gator/procedures/writing-implementation-plans.md`.
- Charters:
  - `.gator/charters/INDEX.md`.
  - `scripts-dashboard-ui.md`:
    - `navigate() / renderCurrentView()`, `renderHistory()`;
    - the whole "Loop workspace" entry: mode state, secondary sidebar, handoff and token non-persistence, live vs history, incremental rendering and fingerprints, polling ownership, the liveness panel states, #53 cards, #55 counters;
    - "Before Changing" (Playwright, keyboard, narrow/wide).
  - `scripts-dashboard.md`: the `/loops` list item fields (`mode` is normalized, plus `attention_notified` and `checkpoint_summary`) and `_LOOP_STATUS_ALLOWED_KEYS` (raw `mode`, `roles`, …).
  - `scripts-loop.md`: `loop_mode()` normalization (a missing mode or `planning-only` → planning).
- Code:
  - `src/gator_command/scripts/dashboard/views/loop.js`:
    - `_state` and `teardownLoopView` (l.150–185);
    - `classifyLoops` / `renderLoopSidebar` / `renderSidebarCard` (l.418–588);
    - `renderSelectedLoop` (l.1496–1565), `renderPromptSection` (l.1808), `renderLiveHeader` / `renderOutcomeHeader` (l.1932–2058);
    - `LIVENESS_STATES` / `applyLiveness` / `refreshLiveness` (l.2031–2273);
    - `renderMainContent` / `loadSelectedLoop` / `pollLoop` / mount (l.3254–3425);
    - the handoff credential warning text (l.1163).
  - `src/gator_command/scripts/dashboard/dashboard.html` (nav button `data-view="history"`, label "History").
  - `dashboard.js`:
    - `VIEW_META.history`; `showView(name, extra, repoKeyOverride)` with its per-view dispatch (`views.loop(state.data, viewSlot, repoName, repoKey)`) and the `_gatorRepoTeardown` hook;
    - the sidebar click handler, `window.gatorNavToRepo` (called from `views/fleet.js` row links), `doRefresh`, which re-runs `showView(activeView, activeRepo)`, and `init()`, which reads `?repo=`;
    - no `pushState`/`popstate` anywhere today.
  - `src/gator_command/scripts/gator-dashboard.py`: the `/loops` list builder (l.2350–2395, `loop_mode` → `"mode"`) and `_LOOP_STATUS_ALLOWED_KEYS` (l.2398).
  - `src/gator_command/scripts/loop/session.py` `loop_mode()` and `create_session` (`"mode": "planning-only"`).
- Tests:
  - `tests/test_dashboard_ui/test_loop_workspace.py`: the sidebar section tests (l.958–1000), `.loop-prompt-copy` counts and click flows (l.1140–1160, 1830–1940, 2262, 2376).
  - `tests/test_dashboard_ui/test_loop_seed.py`: seeded sessions carry no `mode` key, so they are legacy.
  - `tests/test_dashboard_ui/test_responsive_shell.py`: navigates by `data-view="history"`, not by label.

## Approach

**Planning path:** full planning loop (the Architect started one). The sketch's escalation trigger is partly met: the list projection lacks the legacy distinction. The plan uses the sketch's prescribed remedy, the smallest additive allowlisted field.

**Module map:**

| Module (responsibility) | Owns | Files |
|---|---|---|
| **Mode projection** | One function maps loop mode facts to an accessible badge; the only place mode text is decided. | `views/loop.js` (`loopModeInfo()`, `modeBadge()`), `gator-dashboard.py` (`mode_legacy`), `dashboard.css` (`.loop-mode-badge`) |
| **Loop-local navigation** | Create/History tabs, the active-loop explanation in Create, history-only listing, loop-local back/forward, the Commits label. | `views/loop.js`, `dashboard.html`, `dashboard.js`, `dashboard.css` |
| **Participant recovery** | Whether and why recovery prompts are offered; copying still goes through the existing `copyPrompt()`. | `views/loop.js`, `dashboard.css` |

**Key design decisions:**

1. **Mode projection.**
   - `loopModeInfo(src)` accepts a `/loops` item (`mode` normalized, plus the new `mode_legacy`) or a `/status` body (raw `mode`). It returns `{key, label}`:
     - `"coding"` → **Coding**;
     - planning with a recorded mode (`planning` / `planning-only`) → **Planning**;
     - planning with no recorded mode (status `mode` absent, or list `mode_legacy === true`) → **Planning · legacy**;
     - anything else (list `"unknown"`, an unexpected raw value) → **Unknown mode**.
   - It never reads feature names or filenames.
   - `modeBadge(info)` renders `<span class="loop-mode-badge" data-mode="…" aria-label="Loop mode: Coding">Coding</span>`: text plus a distinct border style per mode (solid for coding, dashed for legacy), never colour alone.
   - Badges are added to `renderLiveHeader`, `renderOutcomeHeader`, `renderSidebarCard` (active and history) and the Create view's active-loop explanation. `headerFingerprint` gains the mode key, so it is re-rendered only on change.
2. **Server field.** The `/loops` item gains `"mode_legacy": "mode" not in session`, a boolean, additive and computed server-side. This is the smallest allowlisted field the sketch permits; nothing else in the list or status projections changes. Status already carries the raw `mode`.
3. **Loop-local navigation.**
   - The loop sidebar gets a `role="tablist"` with two `role="tab"` buttons, **Create** and **History** (`aria-selected`, `aria-controls`, arrow-key switching per the WAI tabs pattern), above two `role="tabpanel"` containers. The inactive one gets `hidden`.
   - `_state.view` (`"create" | "history"`) is new. `_state.mode` (`create | handoff | inspect`) keeps its meaning.
   - **Create panel:** the "+ Create Loop" button, plus an "Active" section with the active loop's card (mode badge, stage, counters). The active loop is one click away from Create and never appears in History.
   - **History panel:** the "History" section with terminal loops, newest first (the existing `classifyLoops`).
   - **Main content in Create mode with an active loop:** `renderCreateWorkspace()` renders an explanation card instead of a disabled form:
     - "A **Coding** loop ‘feature’ is active (Review). Only one loop runs at a time.";
     - an **Open active loop** button that selects it (inspect).
     
     With no active loop the form renders exactly as today. The planning/coding/source-plan/revision/brief behavior is untouched, and the existing 409 race path is kept.
   - **Mount default is unchanged:** an active loop opens in inspect, with the Create tab selected; otherwise Create. Selecting a history card selects the History tab.
   - **Back/forward:** shell-owned; see decision 5.
   - **Commits:** in `dashboard.html` the nav label "History" becomes "Commits". In `dashboard.js`, `VIEW_META.history.title` becomes `"Commits"` and the "History view not available" fallback text becomes "Commits view not available". The route key `history`, `data-view="history"`, `views/history.js` and the endpoint are unchanged.
4. **Participant recovery.**
   - `renderPromptSection()` (live loops only; terminal stays empty) builds `<details class="loop-recovery" id="loop-recovery">` once per snapshot:
     - **Summary:** "Participant recovery".
     - **Fixed guidance:** "Use these prompts only to start a new participant session or reconnect one that dropped. Do not paste a prompt into a session that has already joined." Then the existing warning: "The copied prompt carries a role credential. Paste only into the intended participant session."
     - **Per-role rows** for Draftor and Reviewer: a `.loop-recovery-need` text node, plus the existing `button.loop-prompt-copy[data-role]` wired to `copyPrompt()`.
   - **`recoveryNeed(role, joined, livenessState)`** (pure):
     - not joined → "Has not joined yet.";
     - joined and `stale` → "Watcher is stale — reconnect if the session dropped.";
     - joined and `released` → "Watcher exited after a notification — reconnect if the session closed.";
     - otherwise (connected, `not_registered`, closed, unknown or liveness unavailable) → null, shown as "Joined — no action needed".
     
     The `not_registered` → no-need rule is the #52 guard: no optional watcher does not mean absent.
   - **`applyRecovery(snap)`** runs after each status render and each liveness apply. It reads `status.roles` (stored on the snapshot) and `snap.liveness.lastView`, and patches only changed text (`setText`) and the `open` attribute.
     - It opens the disclosure when any role has a need and the need set changed, and closes it when the need set becomes empty. If the Architect toggled the disclosure manually, that choice holds until the need set changes (`data-user-toggled` plus the stored need key).
     - Identical polls produce zero mutations.
   - **Copying** is unchanged: `copyPrompt()` and fallback, `promptEpoch`, token non-persistence. It mutates no loop state. The handoff cards (post-create) are unchanged and remain the normal copy surface.

5. **Shell-owned browser history.**
   - **State shape:** `{gatorDashboard: 1, view, repo, repoKey, sub}`.
     - `view`, `repo` and `repoKey` are the shell's `state.activeView`, `activeRepo` and `activeRepoKey`; `repoKey` is the path hash already used in API URLs.
     - `sub` is `null` except for Loop entries: `{view: "create"|"history", mode: "create"|"inspect", loopId}`. A handoff is recorded as inspect of that loop.
     - Entries are state-only (`""` title, URL unchanged). `?repo=` on reload behaves as today.
     - **No token, prompt text or artifact content ever enters any state object.**
   - **Ownership in `dashboard.js`:**
     - `navigate(name, extra, repoKeyOverride)` = `showView(...)` followed by `history.pushState(shellState(null))`.
     - The sidebar click handler and `window.gatorNavToRepo` call `navigate`.
     - `init()` calls `showView` then `history.replaceState(shellState(null))`.
     - `doRefresh` keeps calling `showView` and pushes nothing.
   - **`window.GatorShell`:**
     - `pushSubState(sub)` pushes `shellState(sub)` only when `state.activeView === "loop"` and not `restoring`;
     - `replaceSubState(sub)` replaces the current entry's state with `shellState(sub)`;
     - `isRestoring()`.
   - **Repository context is explicit (revision 2).**
     - **`setActiveRepo(repoName, repoKey)`** is one shell helper extracted from today's `repo` branch of `showView`. It sets `state.activeRepo` / `state.activeRepoKey`, rebuilds the Repo sidebar label (`▸ <name>`), and un-dims the Repo/Docs/Loop tabs. The `repo` branch calls it, so its behavior is unchanged.
     - **`clearActiveRepo()`** is its inverse: it nulls both fields, restores the "Repo" label and re-dims the three tabs, matching the initial page state.
     - `showView` stays a renderer and lifecycle transition. Its `loop` and `docs` branches keep reading `state.activeRepo` / `state.activeRepoKey` and never restore state themselves.
   - **`restoreShellState(entry)`** is the single restoration path, called only by the `popstate` handler:
     1. **Validate.** `entry.gatorDashboard === 1`, `entry.view` is a key of `VIEW_META`, and `entry.repo` is null or a string. Anything else is ignored.
     2. **Hydrate the repository context before any dispatch.**
        - If `entry.repo` is non-null, look the name up in the current fleet data. If found, call `setActiveRepo(name, fleetKey)`; the fleet's current key is authoritative and the recorded `repoKey` is only a cross-check.
        - If it is no longer registered, show Fleet and `replaceState` the entry to Fleet, with an inline notice "That repository is no longer registered", instead of rendering a Loop against nothing.
        - If `entry.repo` is null, call `clearActiveRepo()`.
     3. **Dispatch.**
        - If `entry.view === "loop"`, the currently mounted view is Loop for the *same* `activeRepoKey` (checked after hydration, against the key the Loop view mounted with), and `views.loop.restore` exists: call `views.loop.restore(entry.sub)`. This is the no-remount fast path.
        - Otherwise call `showView(entry.view, entry.repo, state.activeRepoKey, {initialSub: entry.sub})`. `showView` gains an optional fourth `opts` argument and passes `opts.initialSub` as a fifth argument to `views.loop`.
     
     The handler sets `restoring = true` around this and clears it in a `finally`. A repository change therefore always remounts, so the Loop view's own `_state.repoKey` comes from the hydrated shell state.
   - **Loop's part (`views/loop.js`):**
     - **Mount** accepts `initialSub`. If its `loopId` exists in the fetched list, that view/mode/selection is applied; otherwise today's default. Mount ends with `GatorShell.replaceSubState(currentSub())`, which records the landing state on the current entry without adding one.
     - **User selections** (tab switch, card select, Open active loop, handoff → Open loop workspace) call `GatorShell.pushSubState(currentSub())`.
     - **`views.loop.restore(sub)`** applies a sub-state: it bumps `generation`, re-renders the sidebar, then `loadSelectedLoop()` or `renderMainContent()`. It never pushes.
     - **Focus** moves to the main heading after a restore.
     - The Loop view registers no global listener. `teardownLoopView()` is unchanged apart from new Loop-local fields.
   - **No re-entrancy:** pushes are suppressed while `restoring`, and the restore paths call no pushing function, so Back/Forward cannot grow the stack.
   - **Out of scope:** the Repo/Docs view's internal browsing (selected file) is not recorded. Back from Repo returns to the previous shell view, as a page-level history would.

**Simplicity boundary:**
- No new endpoints and no change to `/status`, `/liveness`, tokens, stages or polling ownership.
- No URL routing (state-only history entries), and no change to the #53 blocked/paused cards, decision history, the coding panel or the liveness panel.
- The recovery disclosure reuses the existing `copyPrompt()` and liveness data; nothing new is derived in JS beyond the documented `recoveryNeed` table.

**Rejected alternatives:**
- **Inferring legacy mode from `feature` or artifacts:** the sketch forbids it.
- **Hiding recovery entirely for joined roles:** this would remove the deliberate reconnect path.
- **URL query/hash routing:** state-only entries give Back/Forward without URL or token hygiene concerns. Deep links can follow later.
- **A Loop-owned `popstate` listener (round 0):** rejected per Finding 1. History must have one owner that outlives any view.

## Changes

### 1. Mode projection
- `gator-dashboard.py` (`/loops` builder): add `"mode_legacy": "mode" not in session`.
- `views/loop.js`: add `loopModeInfo(src)` and `modeBadge(info)`. Use them in `renderLiveHeader`, `renderOutcomeHeader` and `renderSidebarCard`. Add the mode key to `headerFingerprint`.
- `dashboard.css`: add `.loop-mode-badge` with `[data-mode]` border styles (solid / dashed / dotted) and a compact size for cards.

### 2. Loop-local navigation and Commits label
- `views/loop.js`:
  - add `_state.view`;
  - `renderLoopSidebar` builds the tablist and two tabpanels (keeping the `.loop-sidebar-section` / `.loop-sidebar-section-header` markup inside the panels);
  - add tab keyboard handling (Left/Right/Home/End, roving `tabindex`);
  - `renderCreateWorkspace` gets the active-loop explanation branch;
  - add `currentSub()` and `applySub(sub)`; mount gains the `initialSub` parameter; `views.loop.restore` applies a sub-state without pushing; user selections call `GatorShell.pushSubState`; mount calls `GatorShell.replaceSubState`;
  - focus moves to the selected tab after a tab switch, and to the main region's heading after Open active loop or a back/forward restore.
- `dashboard.html`: the nav label "History" becomes "Commits".
- `dashboard.js`:
  - `VIEW_META.history.title` and the fallback text become "Commits";
  - add `shellState(sub)`, `navigate()`, `window.GatorShell` (`pushSubState` / `replaceSubState` / `isRestoring`) and the single `popstate` handler with the `restoring` guard;
  - `showView(name, extra, repoKeyOverride, opts)` passes `opts.initialSub` to `views.loop`;
  - the sidebar handler and `gatorNavToRepo` use `navigate`; `init` uses `replaceState`;
  - extract `setActiveRepo()` from the `repo` branch, add `clearActiveRepo()`, and add `restoreShellState(entry)` (validate → hydrate repository context → dispatch). `showView`'s `loop`/`docs` branches keep reading the shell's active repository.
- `dashboard.css`: `.loop-subnav` tab styles (the selected tab is shown by weight plus an underline, not colour alone), the active-loop explanation card, and wrapping on narrow screens.

### 3. Participant recovery
- `views/loop.js`: rewrite `renderPromptSection` as the `<details>` structure; add `recoveryNeed()` and `applyRecovery()`; store `status.roles` on the snapshot in `renderSelectedLoop`; call `applyRecovery` from `renderSelectedLoop` and at the end of `applyLiveness`.
- `dashboard.css`: `.loop-recovery` (summary weight, guidance text, per-role rows, a need line marked by glyph ⚠ plus bold, not colour).

## Dependencies and Ordering

1 → 2 → 3. Navigation (2) places the cards and badges from 1. Recovery (3) is independent of 2 but lands last because it changes the most pinned tests. No server change other than item 1.

## Assumptions, Risks, and Required Architect Decisions

- **Assumption (non-blocking):** history entries are state-only (no URL change), so a reload behaves as today (`?repo=` only). Repo/Docs internal file selection is not recorded. Reversible: URL deep links can be added on the same state shape.
- **Assumption (non-blocking):** `released` triggers the recovery prompt as the sketch lists it, even though it can be a short normal gap for watcher-based participants. The wording is conditional ("reconnect if the session closed").
- **Assumption (non-blocking):** the mount default stays "inspect the active loop" with the Create tab selected, preserving today's landing behavior.
- **Assumption (non-blocking):** the label is "Planning · legacy" (the sketch gave "Planning / legacy" as an example).
- **Risk:** test churn. The selectors kept are `.loop-prompt-copy`, `.loop-sidebar-section(-header)`, `.loop-sidebar-create` and `.loop-sidebar-open-active` (now the Create-view button). Tests whose expectation changes (Create disabled-state, prompts always visible) are rewritten, not deleted.
- **Risk:** zero-mutation polling. Recovery and badges are added under the existing fingerprint and `setText` discipline, with MutationObserver pins.
- **No blocking Architect decision identified.**

## Testing

New Playwright tests go in `tests/test_dashboard_ui/test_loop_workspace.py` (existing harness and seed). The seed gains one coding terminal loop and one planning loop with `"mode": "planning-only"`; existing seeded loops have no `mode`, so they are legacy.

- **Checkpoint 1 (mode):**
  1. `test_mode_badges_on_cards_and_headers` (parameterized over three seeded loops: coding terminal, planning-only terminal, legacy active): the sidebar card and the selected header show Coding / Planning / Planning · legacy, with `aria-label` "Loop mode: …".
  2. A server unit test in `tests/test_dashboard_loops.py`: `/loops` gives `mode_legacy` true for a session without `mode`, false for `planning-only` and coding.
  3. `test_mode_badge_poll_is_mutation_free`: the MutationObserver on the header region sees zero mutations across an identical poll.
- **Checkpoint 2 (navigation):**
  4. `test_loop_subnav_tabs`: tablist/tab/tabpanel roles, `aria-selected`, arrow-key switching, and History listing only terminal loops while the active loop appears only in the Create panel.
  5. `test_create_with_active_loop_explains_and_opens`: the Create tab with an active loop shows the explanation (mode + feature + stage) and no form; Open active loop selects it (inspect) and moves focus to its heading.
  6. `test_create_without_active_loop_unchanged`: the existing create-form tests still pass, re-pointed where the old disabled-state assertions lived.
  7. History tests:
     - **7a** `test_loop_back_forward_within_loop`: select a history loop → Create tab → Back restores the History tab and that loop's header (no stale content, `history.length` unchanged by the restore) → Forward returns to Create.
     - **7b** `test_back_restores_loop_after_leaving` (the reviewer's sequence): select a history loop → click Commits → Back shows the Loop view with the History tab and that loop selected (outcome header, mode badge) → Forward shows Commits again.
     - **7c** the same with Fleet instead of Commits, and a Back past the Loop entry to the Repo/Fleet entry, each restoring the right shell view.
     - **7e** `test_back_restores_loop_in_its_own_repository` (the round-2 reviewer's sequence):
       - In repo A (`alpha`, seeded loops), select a history loop. Navigate to Fleet and open repo B (`beta`, no loops). Back twice.
       - Assert that the Loop view is shown, the selected card and heading are A's loop, the Repo sidebar label reads A, and every `/api/repo-by-key/<key>/loops…` request after the Back used A's key (captured with `page.on("request")`).
       - Then Forward twice returns to repo B's view with B's label.
     - **7f** `test_back_to_unregistered_repo_falls_back_to_fleet`: a recorded repo that is no longer in the fleet data shows Fleet with the notice and never issues a Loop API request for it. This is unit-level, injecting a history state through `history.replaceState` before Back.
     - **7d** `test_history_state_never_holds_tokens`: walk every entry (`history.back()` loop), assert each `history.state` has `gatorDashboard` and no string matching `glp_`, and that no state carries prompt or artifact text.
  8. `test_commits_nav_label`: the nav shows "Commits", clicking it reaches the commit timeline, and `data-view="history"` is unchanged. The responsive-shell tests pass unchanged.
- **Checkpoint 3 (recovery):**
  9. `test_recovery_hidden_for_healthy_joined` (parameterized over liveness `connected` and `not_registered`, both joined): the disclosure is closed, both rows read "Joined — no action needed", and the copy buttons exist but are not visible.
  10. `test_recovery_opens_for_need` (parameterized: not joined; stale; released): it opens with the role's need text and the credential warning, and Copy writes the clipboard without any loop POST other than `/prompt`.
  11. `test_recovery_user_toggle_survives_poll` and `test_recovery_poll_mutation_free`.
  12. `test_terminal_loop_has_no_recovery` (the existing B19 assertion is kept: `.loop-prompt-copy` count is 0).
  - The existing copy-flow tests (l.1830–1940) keep clicking `.loop-prompt-copy[data-role="draftor"]` through JS. They are updated only where they assumed visibility.
- **Per checkpoint:** run the new and touched tests plus `tests/test_dashboard_loops.py` (cp1).
- **Final approval:** `python -m pytest tests/test_dashboard_ui -q` and `python -m pytest tests -q` once.

## Charter Impact

- `scripts-dashboard-ui.md`:
  - `navigate() / renderCurrentView()` becomes the shell-owned history contract:
    - the state shape, `navigate` versus `showView`, and `window.GatorShell`;
    - the single `popstate` handler → `restoreShellState()` (validate → hydrate the repository through `setActiveRepo` / `clearActiveRepo` → dispatch), with the rule that `showView` never restores state itself;
    - the `restoring` guard and the no-token rule.
  - "Loop workspace": a tab sub-navigation replaces the three-section description; the Create active-loop explanation; History is terminal only; `_state.view`; Loop's sub-state contribution (`initialSub`, `restore`, push on user selection only, no global listener).
  - The mode projection (`loopModeInfo` / `modeBadge`, legacy fallback, not colour alone).
  - The Participant recovery disclosure (`recoveryNeed` table, the #52 guard, user-toggle rule, fingerprint discipline) replaces "prompt copy section".
  - `renderHistory()` / shell: the nav label is "Commits" and the route `history` is unchanged.
- `scripts-dashboard.md`: the `/loops` item gains additive `mode_legacy`.

## Coding Checkpoints

1. **Mode labels** — Add `mode_legacy` to `/loops`; add `loopModeInfo` / `modeBadge` and use them in the live and outcome headers and on sidebar cards (header fingerprint includes mode); add CSS badge styles; seed one coding and one planning-only terminal loop. Verify: `pytest tests/test_dashboard_loops.py -k mode_legacy` and `tests/test_dashboard_ui/test_loop_workspace.py -k "mode_badge"`.
2. **Loop navigation, shell-owned history and Commits label** — Add the Create/History tablist and tabpanels with keyboard support; the Create-view active-loop explanation with Open active loop; history-only listing; shell-owned browser history in `dashboard.js` (`navigate`, `GatorShell` sub-state API, single `popstate` handler → `restoreShellState` with repository hydration via `setActiveRepo` / `clearActiveRepo` before dispatch, the `restoring` guard, `initialSub` into the Loop mount, `views.loop.restore`); and the "Commits" nav label and title. Verify: `pytest tests/test_dashboard_ui/test_loop_workspace.py -k "subnav or create or back or history_state or sidebar or commits"` and `tests/test_dashboard_ui/test_responsive_shell.py`.
3. **Participant recovery** — Replace the bare copy buttons with the "Participant recovery" disclosure: guidance and the credential warning, per-role `recoveryNeed` from `joined` plus liveness state (no-watcher joined roles never flagged), auto-open on need with the user-toggle rule, and zero-mutation patching. Verify: `pytest tests/test_dashboard_ui/test_loop_workspace.py tests/test_dashboard_ui/test_loop_liveness_ui.py`; then `python -m pytest tests/test_dashboard_ui -q` and `python -m pytest tests -q` once at final approval.
