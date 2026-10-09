---
message: "Dashboard: clear Loop Create and History workspaces, mode badges, participant recovery (#56)"
change-type: feature
significance: notable
decision-tags: [dashboard, loop, ux, accessibility]
agent: claude-opus-5-5
architect: Alan Gillette
---

# Session Change Log

- Checkpoint 1 (mode labels):
  - **Server:** each `/loops` item gains the additive boolean `mode_legacy` (`"mode" not in session`) in `gator-dashboard.py`. Normalization maps a missing mode to `planning`, so this field is the only way to show the legacy fallback. `/status` is unchanged; it already carries the raw `mode`.
  - **UI:** `loopModeInfo(src)` / `modeBadge(info)` in `views/loop.js` are the only place mode text is decided: Coding / Planning / Planning · legacy / Unknown mode, from recorded mode facts only (never the feature name or artifacts). The badge (`span.loop-mode-badge[data-mode]`, `aria-label="Loop mode: …"`) appears in the live and outcome headers and on every sidebar card (`.loop-card-badges`). `headerFingerprint` includes the mode key.
  - **CSS:** `.loop-mode-badge` with a distinct border per mode (2px solid coding, solid planning, dashed legacy, dotted italic unknown), never colour alone.
  - **Seed:** two terminal (`ended_by_architect`) loops with recorded mode `coding` and `planning-only`. The other seeded loops have no mode, so they are legacy.
  - **Tests:** `test_list_mode_legacy` (server), plus Playwright `test_mode_badges_on_cards_and_headers` (×3), `test_mode_badge_styles_differ_without_colour` and `test_mode_badge_poll_is_mutation_free`.
  - **Charters:** `scripts-dashboard.md` (`mode_legacy`) and `scripts-dashboard-ui.md` (mode projection entry).
- Checkpoint 2 (loop navigation, shell-owned history, Commits label):
  - **Tabs:** the Loop sidebar gets Create/History tabs (`role="tablist"`/`tab`/`tabpanel`, roving tabindex, Left/Right/Home/End), built once per mount so polls re-render only panel contents. Create holds "+ Create Loop" and the Active section. History holds terminal loops only. `_state.view` selects the tab.
  - **Create with an active loop:** shows an explanation (mode, feature, stage, counters) with **Open active loop** instead of the form. Without an active loop the form is unchanged. The Create action is always actionable, and the disabled/conflict sidebar state was removed.
  - **Shell-owned history (`dashboard.js`):**
    - `navigate()` pushes state-only entries `{gatorDashboard: 1, view, repo, repoKey, sub}`. The sidebar and fleet row links use it; `init()` replaces.
    - `window.GatorShell` (`pushSubState` / `replaceSubState` / `isRestoring`).
    - A single `popstate` handler → `restoreShellState()`: validate → hydrate the repository through `setActiveRepo()` / `clearActiveRepo()` (an unregistered repo falls back to Fleet with a notice) → dispatch (`views.loop.restore` for the same mounted repo, otherwise `showView(..., {initialSub})`).
    - `repo.js`'s own search/file entries are left to `repo.js` while that repo is mounted, and restore the Repo view otherwise.
  - **Loop sub-state:** `currentSub` / `applySub` / `selectLoop`; the mount takes `initialSub` and replaces the landing entry; `views.loop.restore(sub)` never pushes; focus moves to the main heading after Open active loop or a restore. No Loop-owned global listener.
  - **Commits:** the global "History" nav label and topbar title become "Commits". The route `history` is unchanged. `views/history.js` drops a commits response that arrives after another view took the container (this race was exposed by Back).
  - **Tests:** `test_loop_subnav_tabs`, `test_loop_tabs_survive_polls`, `test_sidebar_create_with_active_loop` (replaces B4), `test_create_with_active_loop_explains_and_opens`, `test_create_without_active_loop_unchanged`, `test_loop_back_forward_within_loop`, `test_back_restores_loop_after_leaving` (Commits, Fleet), `test_back_past_loop_entry_restores_shell_views`, `test_back_restores_loop_in_its_own_repository`, `test_back_to_unregistered_repo_falls_back_to_fleet`, `test_history_state_never_holds_tokens`, `test_commits_nav_label`, `test_history_tab_with_active_loop_round_trips` (review round 1: `applySub()` keeps the recorded tab for an inspected active loop).
  - **Charters:** `scripts-dashboard-ui.md` (shell history entry, Loop tabs, active-loop explanation, Loop sub-state, `renderHistory` label and stale guard).
- Checkpoint 3 (participant recovery):
  - The bare "Copy Draftor/Reviewer prompt" buttons become a labelled **Participant recovery** disclosure (`details#loop-recovery`). It holds fixed guidance ("only to start a new participant session or reconnect one that dropped…"), the credential warning, and a per-role need line beside the existing `.loop-prompt-copy` buttons. Copying is unchanged (`copyPrompt()`, epoch guard, fallback, no token persistence).
  - `recoveryNeed()`: not joined / watcher stale / watcher released. Joined roles that are connected, have no watcher (`not_registered`, #52), are closed, or whose liveness is unavailable are never flagged.
  - `applyRecovery()` runs after each status render and liveness apply. It patches only changed text, the `data-need` flag and `open`. It opens when the need set changes and is non-empty and closes when it empties, so a manual toggle holds until then. Identical polls are mutation-free. Terminal loops show no recovery.
  - **CSS:** `.loop-recovery*`; a need is shown by ⚠ plus bold, not colour. The unused `.loop-prompt-section` styles were removed.
  - **Tests:** `test_recovery_hidden_for_healthy_joined` (connected, not_registered), `test_recovery_opens_for_need` (not joined, stale, released; Copy posts only `/prompt`), `test_recovery_user_toggle_survives_poll`, `test_recovery_poll_mutation_free`. The two in-flight copy tests now wait for the button attached rather than visible.
  - **Charter:** `scripts-dashboard-ui.md` (Participant recovery tripwire; "Live vs history" wording).
