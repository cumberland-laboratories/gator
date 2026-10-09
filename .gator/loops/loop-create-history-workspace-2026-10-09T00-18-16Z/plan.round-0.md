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
- **Verification:** three responsibility checkpoints, each with focused Playwright and unit tests. The full Dashboard UI suite runs once at final approval.

## Summary

The plan implements the sketch's information architecture inside the existing `views/loop.js` state machinery, with no change to loop semantics, tokens, liveness or coding checkpoints.
- **Navigation:** Create/History tabs. Create explains and links the active loop instead of showing a disabled form, and History lists only terminal loops.
- **Mode labels:** one projection function feeds every header and card.
- **Recovery:** the copy-prompt buttons move into a "Participant recovery" section with in-place guidance and the credential warning. It opens automatically only when a role has not joined or its watcher is stale or released.
- **Back/forward:** loop-local history entries (state-only, no URL change) support browser back/forward within the Loop view.
- **Commits:** the global "History" nav label becomes "Commits"; its route and data are unchanged.

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
  - `src/gator_command/scripts/dashboard/dashboard.html` (nav button `data-view="history"`, label "History"), `dashboard.js` (`VIEW_META.history`, `showView("history")` → "Recent commits"; no `pushState`/`popstate` anywhere in the shell).
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
   - **Back/forward:** each user selection (tab switch, card select, Open active loop, handoff → Open loop workspace) calls `history.pushState({gatorLoop: {repoKey, view, mode, loopId}}, "")` with no URL change. Mount calls `replaceState` with the initial state.
     - A `popstate` listener, registered at mount and removed by `teardownLoopView()`, restores `{view, mode, loopId}` only when `event.state.gatorLoop.repoKey === _state.repoKey` and the container is connected. It bumps `generation`, re-renders the sidebar, and calls `loadSelectedLoop()` or `renderMainContent()`, so stale main content cannot survive (snapshot invalidation via generation, as today).
     - A restored `handoff` maps to `inspect` of that loop. A token is never placed in the state object; the loop id is already in the DOM.
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

**Simplicity boundary:**
- No new endpoints and no change to `/status`, `/liveness`, tokens, stages or polling ownership.
- No URL routing in the shell, and no change to the #53 blocked/paused cards, decision history, the coding panel or the liveness panel.
- The recovery disclosure reuses the existing `copyPrompt()` and liveness data; nothing new is derived in JS beyond the documented `recoveryNeed` table.

**Rejected alternatives:**
- **Inferring legacy mode from `feature` or artifacts:** the sketch forbids it.
- **Hiding recovery entirely for joined roles:** this would remove the deliberate reconnect path.
- **URL query/hash routing for loop views:** this needs shell routing changes and URL/token hygiene review, so it is out of the first-pass scope.

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
  - add `pushLoopState()`, `restoreLoopState()` and a `popstate` listener registered at mount and removed in `teardownLoopView()`;
  - focus moves to the selected tab after a tab switch, and to the main region's heading after Open active loop or a back/forward restore.
- `dashboard.html`: the nav label "History" becomes "Commits".
- `dashboard.js`: `VIEW_META.history.title` and the fallback text become "Commits".
- `dashboard.css`: `.loop-subnav` tab styles (the selected tab is shown by weight plus an underline, not colour alone), the active-loop explanation card, and wrapping on narrow screens.

### 3. Participant recovery
- `views/loop.js`: rewrite `renderPromptSection` as the `<details>` structure; add `recoveryNeed()` and `applyRecovery()`; store `status.roles` on the snapshot in `renderSelectedLoop`; call `applyRecovery` from `renderSelectedLoop` and at the end of `applyLiveness`.
- `dashboard.css`: `.loop-recovery` (summary weight, guidance text, per-role rows, a need line marked by glyph ⚠ plus bold, not colour).

## Dependencies and Ordering

1 → 2 → 3. Navigation (2) places the cards and badges from 1. Recovery (3) is independent of 2 but lands last because it changes the most pinned tests. No server change other than item 1.

## Assumptions, Risks, and Required Architect Decisions

- **Assumption (non-blocking):** back/forward is loop-local, implemented with state-only `pushState` entries and no URL change, because the shell has no routing to integrate with. Entries pushed while in the Loop view are ignored if the user has left it (the listener is removed). The visible effect is that Back may need extra presses after leaving the Loop view. Reversible: URL-level routing can follow as shell work.
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
  7. `test_loop_back_forward`: select a history loop → Create tab → Back restores the history selection with the correct header (no stale content); Forward returns. No token-like string appears in `history.state`.
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
  - "Loop workspace": a tab sub-navigation replaces the three-section description; the Create active-loop explanation; History is terminal only; `_state.view`; loop-local `pushState`/`popstate` (state-only, no token, listener lifecycle).
  - The mode projection (`loopModeInfo` / `modeBadge`, legacy fallback, not colour alone).
  - The Participant recovery disclosure (`recoveryNeed` table, the #52 guard, user-toggle rule, fingerprint discipline) replaces "prompt copy section".
  - `renderHistory()` / shell: the nav label is "Commits" and the route `history` is unchanged.
- `scripts-dashboard.md`: the `/loops` item gains additive `mode_legacy`.

## Coding Checkpoints

1. **Mode labels** — Add `mode_legacy` to `/loops`; add `loopModeInfo` / `modeBadge` and use them in the live and outcome headers and on sidebar cards (header fingerprint includes mode); add CSS badge styles; seed one coding and one planning-only terminal loop. Verify: `pytest tests/test_dashboard_loops.py -k mode_legacy` and `tests/test_dashboard_ui/test_loop_workspace.py -k "mode_badge"`.
2. **Loop-local navigation and Commits label** — Add the Create/History tablist and tabpanels with keyboard support; the Create-view active-loop explanation with Open active loop; history-only listing; loop-local `pushState` / `popstate` back/forward with listener teardown; and the "Commits" nav label and title. Verify: `pytest tests/test_dashboard_ui/test_loop_workspace.py -k "subnav or create or back_forward or sidebar or commits"` and `tests/test_dashboard_ui/test_responsive_shell.py`.
3. **Participant recovery** — Replace the bare copy buttons with the "Participant recovery" disclosure: guidance and the credential warning, per-role `recoveryNeed` from `joined` plus liveness state (no-watcher joined roles never flagged), auto-open on need with the user-toggle rule, and zero-mutation patching. Verify: `pytest tests/test_dashboard_ui/test_loop_workspace.py tests/test_dashboard_ui/test_loop_liveness_ui.py`; then `python -m pytest tests/test_dashboard_ui -q` and `python -m pytest tests -q` once at final approval.
