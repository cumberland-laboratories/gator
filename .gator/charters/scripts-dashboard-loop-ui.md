# Charter: Loop Workspace View

**Covers**: `src/gator_command/scripts/dashboard/views/loop.js`, `src/gator_command/scripts/dashboard/views/loop-markdown.js`

## Owns

The Loop workspace in the browser: Active, History, Create and the Help and Extras tabs, the live timeline, checkpoint rail, artifacts and Architect controls, and the sanitized Markdown renderer it uses. The shell is in [Dashboard Shell](scripts-dashboard-shell.md).


## Does Not Own

- Route authorization, path containment, filesystem access, or data computation; see [`scripts-dashboard.md`](scripts-dashboard.md).
- Governance business rules.
- Cumberland document-template styling; see [`contracts.md`](contracts.md).
- The page shell, navigation, workspace tabs, requests and styling; see [Dashboard Shell](scripts-dashboard-shell.md).
- The other views; see [Dashboard Views](scripts-dashboard-views.md).

---

### renderArtifactBody(section, content, text) / buildArtifactViewBar() / applyArtifactView()
File: src/gator_command/scripts/dashboard/views/loop.js
The expanded artifact body. `loadArtifactContent()` calls it after its generation, `isConnected` and `_gatorContentRev` guards, so a stale response is dropped **before** any parse.
- **Equality skip:** if `text === content._gatorText` and the body is loaded, it returns with **no reparse and no DOM writes**. Writing "Loading…" over the panes resets `_gatorText`, so a re-expand never equality-skips onto it.
- **Changed text:** it builds the Raw pane (`pre.loop-artifact-pre`, `textContent = text`) and the Rendered pane (`div.loop-md` from `GatorLoopMarkdown.render`, in `try/catch`). It reuses the view bar, sets `_gatorText` and `dataset.loaded`, then calls `applyArtifactView`.
- **View bar:** `div.loop-artifact-viewbar[role=group][aria-label="Artifact view"]` holds native **Rendered** / **Raw** buttons (`aria-pressed`) and an `aria-live` caption naming the state in text. The pressed button is bold, underlined and has a 2px border, so state is never colour-only. Keyboard use is native: Tab, then Enter/Space.
- **View choice:** `section.dataset.view` (`rendered` default / `raw`) is written **only by the buttons**. It survives refreshes and collapse/expand, resets with the skeleton, and is never stored in `localStorage`. Switching toggles `hidden` / `aria-pressed` only, with no refetch and no reparse. `applyArtifactView` writes only values that differ.
- **Fallbacks:** over `MAX_RENDER_CHARS` (200,000) the caption reads "Too large to render (N characters); showing raw text". If the formatter is missing or throws, it reads "Could not render Markdown; showing raw text". In both cases Raw is shown and Rendered disabled, but the section's chosen view is **not** overwritten. The panel is never empty.
- **Height:** `.loop-artifact-content` has `max-height: 70vh` (scrollable): the full document is read in place, with no extra pane.
- **Row label:** `.loop-artifact-toggle` is sans `--text-ui` / 500 (it was mono 13px), because its label is often prose (brief and baseline labels). The rows, their padding and the `(cpK · gen g)` suffix are unchanged. Pinned with the reading roles by `test_loop_reading_hierarchy` (`test_loop_workspace.py`); the rail size is pinned by `test_checkpoint_progress_and_labels` (`test_loop_coding_ui.py`).
- **Pinned by:** `tests/test_dashboard_ui/test_loop_markdown_ui.py`.
  - The tests check: no excerpt and no fetch when collapsed; the full document Rendered by default; Raw identical to what was served; keyboard switching with no refetch; 0 mutations and 0 renders on unchanged polls and on an unchanged refetch; a changed refresh updating both panes and keeping Raw; a stale response unable to reset text or view; and the large and failure fallbacks.
  - **Mutation-checked:** Raw via `innerHTML`, no equality skip, no revision guard, a collapsed fetch restored, and the view reset on render all fail it.

### render(text) / safeHref(url) — window.GatorLoopMarkdown
File: src/gator_command/scripts/dashboard/views/loop-markdown.js
A closed display formatter for **expanded Loop artifacts**: hostile, model-authored text. It is loaded before `views/loop.js` and inlined by `build_snapshot()`.
- **Closed grammar** (plan rev 2), in one linear pass with no nesting and no recursion. Anything else is literal text.
  - **Line rules**, first match wins:
    1. fence → `pre > code`, literal, running to EOF if unclosed;
    2. `#`…`######` heading → `h3`–`h6`;
    3. `---` / `***` / `___` → `hr`;
    4. `>` → a one-line `blockquote`;
    5. a `-` / `*` / `+` bullet, or
    6. an `N.` item, both as `li` in one **flat** `ul` with `md-indent-0..3` (leading spaces ÷ 2, capped) and the number kept literal (no `ol`);
    7. a `|` table with a delimiter second line, split on every `|`, padded or trimmed to the header, ≤ 32 columns, wrapped in `div.loop-md-tablewrap`;
    8. blank → closes the block.

    Anything else joins the current `p` with a space.
  - **Inline rules**, one scan, first match wins: (1) `![…](…)` is emitted as ONE literal text node, **before** links, so it is never an image or a link; (2) `` `code` ``; (3) `[text](url)`, with literal link text; (4) `**bold**`, with literal content. Everything else is literal, including italics, entities, HTML and backslashes.
- **`safeHref`:** trims, rejects empty / whitespace / control characters / backslash, and accepts only `new URL(url)` (no base) with protocol `http:` or `https:`. Anchors get `target=_blank` and `rel="noopener noreferrer nofollow"`. Rejected links become literal `text (url)` in `span.loop-md-link-blocked`. A URL containing parentheses never matches the link rule, so it is fully literal.
- **Bounds:** `MAX_RENDER_CHARS = 200000`. Longer input throws an `Error` named `TooLarge`; the caller falls back to Raw. CRLF is normalized.
- **Complexity budget:** ≤ 160 non-comment lines (currently 160). A new rule requires a plan revision.
! TRIPWIRE: artifact text reaches the DOM ONLY via `createElement` / `createTextNode`. Never `innerHTML` / `outerHTML` / `insertAdjacentHTML`, `style`, `on*` or `src`.
  - **Elements:** `h3 h4 h5 h6 p ul li pre code strong a table thead tbody tr th td blockquote hr div span`.
  - **Classes:** only `md-indent-0..3`, `loop-md-tablewrap` and `loop-md-link-blocked`.
  - **`a` attributes:** only `href` / `target` / `rel`.

  Pinned by `tests/test_dashboard_ui/test_loop_markdown_ui.py`: an allowlist walk over an adversarial corpus; images giving no `img`, no `a` and no request; the link policy; malformed input; size. Mutation-checked: an HTML text write, link-before-image ordering, any scheme accepted, and parsed bold content each fail it.

### buildLoopTabs() / applyTabState() / currentTab() / ensureAuxFrame() / isGoalCopyRequest() / replyGoalCopy() / handleGoalCopy() / bindExtrasCopyListener() / applyPrimaryLabel() / switchTab() / primaryState() / primaryDecision() / applyPrimary() / setPrimaryDisplay() / landPrimary() / renderHistoryList() / syncListChrome() / reconcilePrimary() / showPrimaryNotice() / primaryNoticeEl() / landFromLoops() / retryLanding() / renderListUnavailable() / renderActiveConflict() / renderCreateWorkspace() / renderHandoff() / renderSelectedLoop() / buildLoopSkeleton() / patchRegion() / renderLiveHeader() / counterLineHtml() / renderOutcomeHeader() / nowLine() / renderNowLine() / unblockActionLabel() / renderBlockedCard() / syncDecisionsDisclosure() / renderPromptSection() / renderControls() / loopDialogConfig() / openLoopDialog() / closeLoopDialog() / setControlsPending() / focusAfterDialogInvalidated() / renderContinueControl() / showExtendNotice() / ensurePolling() / updateTimeline() / renderTimeline() / timelineGroupKey() / timelineGroups() / groupLabel() / groupHtml() / renderArtifacts() / fetchLiveness() / postRenotify() / refreshLiveness() / applyLiveness() / openRenotifyForm() / fetchCodingSnapshot() / patchCodingRegion() / renderCodingRegion() / renderResolution() / railItems() / railFingerprint() / renderRail() / openReopenForm() / refreshCoding() — Loop workspace
File: src/gator_command/scripts/dashboard/views/loop.js
Render the governed planning loop workspace. A full-width tab bar runs across the top of the main pane. It holds a derived **Primary** tab (**Create** or **Active**) and **History**. The list pane holds History only. The main content follows the mode: the creation form, the participant handoff, the selected-loop inspection, or the defensive conflict state.
<- loop route
-> loop list/status/events/artifact endpoints, control endpoints (pause/interject/unblock/end/extend), start endpoint, prompt endpoint, sketch-sources endpoint (`/api/repo-by-key/<repo_key>/...`)
! **Mode state**: `_state.mode` ("create" | "handoff" | "inspect" | "conflict") selects the main content renderer (`renderMainContent()` / `showMain()`).
  - `_state.handoffId` tracks the loop during participant handoff.
  - `_state.conflictIds` holds the sorted active ids while the conflict state is shown.
  - `_state.conflictChoice`: see below.
! **Primary tab.** The first tab is derived from the loop list.
  - **Labels:** it reads **Create** (the creation form) when no loop is active, and **Active** (that loop's handoff or live workspace) when one is.
  - **Removed:** the `+ Create Loop` action, the sidebar Active section and card, and the "a loop is active" explanation. `renderActiveLoopExplanation()` and `.loop-sidebar-open-active` are gone.
  - **`primaryState(loops)`** (pure, built on `classifyLoops`) returns `{kind: "none"}`, `{kind: "one", id}` or `{kind: "many", ids}` (ids sorted).
  - **`primaryDecision(ps, display)`** (pure) is the one rule for what Primary shows. `display` comes from `currentDisplay()`: `{mode, selectedLoopId, handoffId, conflictIds, conflictChoice}`. It returns `keep`, `create`, `inspect(loopId)` or `conflict(ids)`:

    | `ps` | `keep` when | otherwise |
    |---|---|---|
    | none | mode `create` | `create` |
    | one(A) | inspect A, or handoff A | `inspect(A)` |
    | many(ids) | mode `conflict` with the same ids; or inspect of a loop in ids **and** `conflictChoice === conflictKey(ids)` | `conflict(ids)` |

  - **`applyPrimary(decision, opts)`** carries out a non-keep decision, in this order:
    1. `generation++`;
    2. `stopPolling()`, unless the decision is to inspect;
    3. `setPrimaryDisplay()`, which always clears `handoffId`, `conflictIds` and `conflictChoice` before it sets the new display;
    4. records history: `shellPush()` for `opts.record: "push"` (a user action), or `shellReplace()` for `"replace"` (an automatic transition);
    5. `renderHistoryList()`, then `showMain()`.
  - **Conflict state (defensive):** Gator allows one active loop. With more than one, `renderActiveConflict()` shows:
    - the heading "Active loops";
    - a text-led `.loop-primary-notice[role=status]` ("⚠ N loops are active… the Dashboard does not pick one…");
    - one `button.loop-conflict-open[data-loop-id]` per loop, labelled with the escaped feature, in id order.

    Nothing is chosen by position.
  - **`conflictChoice`** is `conflictKey(ids)` (the ids joined by newlines).
    - **Set:** only by a click in the conflict list (`selectLoop(id, {conflictKey})`).
    - **Cleared:** by every other `selectLoop()`, by `setPrimaryDisplay()` (so by every non-keep `applyPrimary()` and every mount or restore landing), and by `teardownLoopView()`.
    - **Never persisted:** `currentSub()` records the conflict state as mode `create`.
  - **Label:**
    - **Before the first list:** `buildLoopTabs()` creates the Primary tab (`#loop-tab-create`, `data-tab="create"`) as "…", with `aria-label="Loading loops"` and `data-primary="unknown"`. Nothing claims Create before a list exists.
    - **After:** `applyPrimaryLabel(root, ps)` writes "Create" or "Active" and `data-primary="create|active"`, and removes the `aria-label`. It writes each only when it differs. The tab node is never rebuilt.
  - **`syncListChrome(loops, container)`** is `applyPrimaryLabel()` plus `renderHistoryList()`. The mount landing calls it directly; every later list fetch reaches it through `reconcilePrimary()`.
! **Primary reconciliation and list failure.**
  - **`fetchLoops()`** returns the `loops` array, or **null** on a non-2xx response, a network error, an unparsable body, or a body without an array `loops`. It returns `[]` only for a genuinely empty list, the same rule as `fetchEvents()`. A failure is never read as "no active loop". The create-form pickers (`loadRevisePicker`, `loadSourcePicker`) treat null as an empty list, as before.
  - **`reconcilePrimary(loops, opts)`** runs after every list fetch made after the landing: `pollLoop()`, `refreshSidebarOnly()`, `refreshSidebarAndMain()` and the 409 path. It returns `false` for a null list (nothing changes), `"kept"` or `"applied"`. On a valid list it, in order:
    1. stores `_state.loops`. If `primaryState` is not `many`, it also clears `conflictChoice` (state only, before any early return). A choice therefore lasts only while the same conflict lasts unbroken;
    2. `syncListChrome()`;
    3. stops if `view === "history"`, so a refresh never moves the Architect out of History;
    4. stops on `primaryDecision(...) === keep`, with no mutation;
    5. otherwise calls `applyPrimary(decision, {record: "replace", notice})`. An automatic transition never adds a history entry.
  - **Transition notice:**
    - **When it appears:** when the previously shown loop (`shownLoopId()`: inspect or handoff) leaves Primary.
    - **Listed as terminal** (`kind: "ended"`): "■ Loop ‘<feature>’ ended — <Outcome>." plus a "View in History" link, which calls `selectLoop(id)`.
    - **No longer listed** (`kind: "gone"`): "Loop ‘<id>’ is no longer listed."
    - **Caller text:** `opts.notice` overrides both (`kind: "text"`).
    - **Rendering:** `primaryNoticeEl()` builds `p.loop-primary-notice.loop-transition-notice[role=status][data-kind]` from text nodes only. `showPrimaryNotice()` runs after `showMain()` resolves for the same generation. For Create or conflict, the notice goes first in `#loop-main-content`. For inspect, it goes in the new workspace's `action` slot.
    - **Covers** one → none (the Create form, plan option (a): an approved loop's commit banner and Continue control are reached through History), the A → B turnover, and one → many.
  - **`pollLoop()` ordering:** status, then events, then the list.
    - **Failures:** a failed status or events response keeps the refresh-failure behaviour. A failed list (null) keeps the workspace and `_state.loops`, shows the `refresh` slot's "Refresh failed — retrying.", and **never stops the timer** (see "Pending reconciliation keeps the timer").
    - **Clearing the notice:** `setRefreshFailed(false)` runs only after all three succeed.
    - **Terminal under Primary** (`view === "create"`): the poll does not patch first. It fetches the list and reconciles in the same poll, so no empty intermediate panel appears. If the list failed, or still lists the loop as active, it patches the terminal `/status` in place and keeps the timer, so the next poll reconciles.
    - **Terminal under History:** unchanged — the in-place patch, then the timer stops (except approved coding).
  - **Pending reconciliation keeps the timer.** When Primary shows a loop whose status is terminal, that is a reconciliation still pending. The single timer runs until a valid list moves Primary (`applyPrimary()` → `stopPolling()`). A failed or stale list leaves the view in place, and the next poll retries.
    - **`loadSelectedLoop()`:** a terminal status under Primary (a stale list, for example after a History detour) calls `ensurePolling()` and `refreshSidebarOnly()`. `pollLoop()`'s terminal-under-Primary branch then owns the retries.
    - **`updateHandoffStatus()` terminal:** it keeps its epoch bump, "Loop ended" buttons and outcome badge, no longer stops the timer, then fetches the list and calls `reconcilePrimary()`. A null list adds the text-led `.loop-handoff-refresh` line ("Refresh failed — retrying.", via `setHandoffRefreshFailed()`), which is removed on the next valid list. Every poll repeats this until a valid list resolves it. Under History, a known list stops the timer instead.
    - **`switchTab("create")` with `keep`:** for an inspect or handoff selection, the switch restarts a stopped timer, so a loop that finished while History was shown is checked and reconciled.
  - **`refreshSidebarAndMain()`:** if reconciliation applied a transition, it is done. Otherwise (kept, or a null list) it renders the current selection as before.
  - **Mount with a failed first list:**
    - **What shows:** `renderListUnavailable()` shows `.loop-primary-notice[data-kind="unavailable"]` "Loop list unavailable — retrying.". `data-loaded` stays unset, so the tabs are inert and the label stays "…". The sub-state is kept in `_state.pendingSub`.
    - **Retry:** `ensurePolling()` still starts the timer. `pollLoop()` calls `retryLanding()` until a valid list arrives. It is guarded by `_state.landing`, `mountId` and `isLoaded()`.
    - **Landing:** `landFromLoops(loops, sub, mount)` (also the normal mount landing) applies the sub-state, records with `shellReplace()`, writes the chrome, and sets `data-loaded` before any await, so only one landing happens.
    - **Restore before landing:** `restore()` only replaces `pendingSub`.
  - **409 race (`handleCreateSubmit`):** a fresh list is fetched (generation-guarded).
    - **One or more active loops:** `reconcilePrimary()` with the text notice "Another loop was already active; your form was not submitted. Showing the active loop." (Active, or the conflict state).
    - **No active loop:** the form is kept, with "A loop is already active elsewhere. Refresh to see it."
    - **A null list:** the form is kept, with "…and the loop list could not be loaded. Refresh to see it."

    There is no "Open active loop" link (`.loop-create-open-active` is gone) and never a disabled form.
  - **Pinned by** `test_active_loop_ends_reconciles_primary`, `test_primary_follows_active_identity`, `test_list_failure_keeps_primary_workspace`, `test_initial_list_failure_retries`, `test_creation_409_transitions_to_active`, `test_terminal_handoff_disables_copy_buttons` (including the failed-then-terminal list case) and `test_stale_primary_selection_retries_after_history`.
! **Tabs and layout**:
  - **Layout:** the mount skeleton is `.loop-workspace` (a column) holding two children:
    - `#loop-tabbar.gator-tabbar.loop-tabbar`: full width; it owns the baseline;
    - `.loop-workspace-body#loop-tabpanel[role=tabpanel]`: a row of `#loop-sidebar-nav` + `#loop-main-content`, stacked at ≤768px.

    `.loop-workspace` keeps `dataset.polling`, and gains `data-loaded="1"` once the first list has landed.
  - **Tabs:** `buildLoopTabs(container)` writes the tablist **once per mount**. It is a `role="tablist"` (`.loop-subnav`, the JS/test hook) with four `button.gator-tab.loop-subnav-tab[role=tab]` (`#loop-tab-create` / `#loop-tab-history` / `#loop-tab-help` / `#loop-tab-extras`, `LOOP_TABS` order).
    - Create and History have `aria-controls="loop-tabpanel"`. The workspace body is their single tab panel, the same pattern as `#app-shell` under the workspace strip. Help has `aria-controls="loop-help-panel"` and Extras `aria-controls="loop-extras-panel"`.
  - **Help and Extras tabs:** `#loop-help-panel.loop-help-panel` and `#loop-extras-panel.loop-help-panel.loop-extras-panel` (`[role=tabpanel][tabindex=0]`) are siblings of the body in `.loop-workspace`. Help shows the shipped `gator-loop.html` (`LOOP_HELP_DOC`), the same document as Welcome's "Gator loop" topic. Extras shows `gator-loop-extras.html` (`LOOP_EXTRAS_DOC`): per-model notes (Codex: `gator loop codex`, the trust cost and the `/goal` prompt with a copy button; Opus: works well as the Draftor). `AUX_TABS` holds each one's document, panel id, frame class, frame title and snapshot-missing text.
    - **State:** `_state.aux` (`null` | `"help"` | `"extras"`, reset by `teardownLoopView()`). `currentTab()` is `_state.aux` when it is set, else `_state.view`. `_state.view` keeps its `create|history` vocabulary, so `currentSub()`, `cleanSub()` and `cleanContextSub()` are unchanged and **neither Help nor Extras ever enters shell history**.
    - **`switchTab("help"|"extras")`** sets `_state.aux`, calls `ensureAuxFrame()` and `applyTabState()`, and returns: no push, no `primaryDecision`, no polling change. It works before the first list lands (`isLoaded()` is not required). Leaving either (`switchTab("create"|"history")`) clears `_state.aux` first; before the first list it only re-applies the tab state. A return to the tab it was opened from is `changed === false`, so it pushes nothing.
    - **Hidden, not removed:** `applyTabState()` writes `body.hidden = !!_state.aux` and, for each `AUX_TABS` panel, `hidden = (_state.aux !== name)`, each only when it differs. The Create form, a selected loop, its regions and the poller therefore survive a visit. CSS needs `.loop-workspace-body[hidden], .loop-help-panel[hidden] { display: none }` because `display: flex` would override the attribute (both panels carry `.loop-help-panel`).
    - **Frames:** `ensureAuxFrame(container, name)` creates the panel's frame once per mount: `iframe.loop-help-frame` (`title="Gator loop help"`) or `iframe.loop-extras-frame` (`title="Gator loop extras"`), `sandbox="allow-scripts"` exactly, `src` `/api/welcome/docs/<doc>` live, or the `srcdoc` property from `window.GATOR_WELCOME_DOCS` in a snapshot (missing → `p.loop-help-status`). The Extras frame is kept in `_state.extrasFrame`. Same TRIPWIRE as Welcome frames: never widen the sandbox, no loop data. The Help frame has no messages in either direction.
    - **Extras copy action:** `bindExtrasCopyListener(root)` runs once per mount (after `buildLoopTabs`) and is removed by `teardownLoopView()`; the listener also removes itself once its root is detached. It calls `handleGoalCopy(event.source)` only when `_state.extrasFrame` is a connected `IFRAME` inside this mount's root, `event.source === frame.contentWindow`, `event.origin === "null"`, and `isGoalCopyRequest(event.data)`: a plain object (prototype `Object.prototype`) with exactly three own keys, `type === "gator-loop"`, `v === 1`, `action === "copy-codex-goal"`. `handleGoalCopy()` writes `CODEX_GOAL_PROMPT` with `navigator.clipboard.writeText`; `replyGoalCopy()` posts `{type:"gator-loop", v:1, action:"copy-codex-goal-result", ok}` (+ `reason` `"unavailable"` / `"denied"`) to that source only, target origin `"*"` (opaque origin; no secret in the reply).
    ! TRIPWIRE (Extras copy protocol): same rules as Welcome's copy protocol. Only this mount's Extras frame is accepted; the Help frame, the page, any other frame, a stale frame, a non-`"null"` origin, an unknown version or action, an extra key, an array or a string cause no clipboard write and no reply. The prompt is never received from or sent through a message. `CODEX_GOAL_PROMPT` is one line, owned by the Dashboard, and tells Codex to run every `gator loop` command as one plain command judged by Gator's printed text, never by exit codes (a wrapped `...; exit $LASTEXITCODE` misses the profile's allow rule), and must equal the visible `#codex-goal` text in `gator-loop-extras.html` (pinned by `tests/test_welcome_docs.py`); the `<token>` placeholder is part of it (Codex reuses its join token) and the wait is filled in as `--max-seconds 3600`, an Architect-chosen interval that keeps Codex's idle wait turns to at most one per hour (the protocol default stays 360). Never widen the accepted shape or sources without a new review.
    - **`restore(sub)`** (Back/Forward) clears `_state.aux` and re-applies the tab state, because history only records Create/History.
    - Polls never rebuild the tablist, so a focused tab keeps focus.
  - **State:** `applyTabState(root)` writes, each only when it differs: `aria-selected`, the roving `tabindex` (0/-1), the body's `aria-labelledby` (`loop-tab-<view>`), and `#loop-sidebar-nav.hidden = (view !== "history")`. On Primary the list pane is hidden (`.loop-sidebar[hidden] { display: none }`), so `.loop-main` fills the body with no blank column.
  - **History list:** `renderHistoryList(loops, container)` draws only `#loop-history-list.loop-sidebar-section`: the header "History", "No completed loops" when empty, and the terminal cards newest first. It wires card clicks to `selectLoop()`.
    - It rewrites only when its fingerprint changes. The fingerprint is `listEl._gatorHistoryFp`, built per card from `[loop_id, stage, feature, mode key, counter text, date, selected]`. Unchanged polls therefore make no list writes.
    - The active loop is never listed.
  - **Inert until loaded:** the bar exists from mount, but `switchTab()` returns early until `data-loaded="1"` (`isLoaded()`). Before that, `_state` may still hold the previous mount's selection, and a push would land ahead of the mount's landing `shellReplace()`. UI tests wait for `.loop-workspace[data-loaded="1"]` (`test_loop_workspace.py` `_navigate_to_loop()`).
  - **Keyboard:** Left, Right, Home and End switch the tab and focus it (automatic activation), over all three tabs from `currentTab()`. The selected tab is shown by weight plus an underline (the shared `.gator-tab` Paper rule), never colour alone.
  - **`switchTab()`:**
    - `"create"` computes `primaryDecision()`. `keep` re-renders nothing, so a half-filled form, or a live workspace kept from History, survives. Anything else runs `applyPrimary(…, {record: "push"})`.
    - `"history"` changes only the list pane and the tab state. The main content stays until a card is chosen.
  - **Selection:** `selectLoop(id, opts)` sets inspect mode and the tab that matches the loop's state: a terminal loop → History, otherwise Primary.
  - **Mount default:** `applyDefaultSelection()` selects Primary and runs `landPrimary()` (`primaryDecision` against an empty display): none → Create, one → inspect it, many → the conflict state.
  - **Pinned by** `test_loop_subnav_tabs`, `test_primary_tab_reflects_active_state`, `test_loop_tabs_survive_polls`, `test_loop_tabs_inert_until_loops_load`, `test_loop_tabbar_spans_main_pane` and `test_active_conflict_state`.
  - **UI test fixture:** the `alpha` seed (`test_loop_seed.py`) holds four live loops on disk, so that each live state has a fixture. A list with several live loops violates the one-active-loop rule, and the view shows it as the conflict state.
    - **Default:** the autouse `_sole_active_loop` fixture in `tests/test_dashboard_ui/conftest.py` serves the real list through `_harness.sole_active_loop_list(page, "widget-refactor")`. That keeps the terminal loops plus one live loop, so every test lands on `widget-refactor` as before.
    - **Another live loop:** `_open_sole_active(page, fleet, feature)` makes a different live loop the only active one.
    - **Raw list:** `@pytest.mark.raw_loop_list` sees the raw seed (used by `test_active_conflict_state`).
    - **Own mocks:** a test's own list mock takes precedence. A held or counted request must be released with `route.fallback()`, not `route.continue_()`, so it still passes through the filter.
    - **Held lists:** a test that holds the `/loops` response must wait for the mounted view (`#loop-sidebar-nav`, `state="attached"`), never for `data-loaded`, which can only appear after the hold. `test_departed_mount_does_not_resurrect_polling` raced its own timeout this way.
      - **The departed mount.** The test holds the first `/loops` with a **non-blocking** handler: it keeps the `route` and answers it from the test thread after leaving Loop. The departure therefore really happens while the list is pending. It prints a request trace (time, phase, URL) and the page state on failure.
! **Loop history sub-state**: the shell owns history (see `navigate()` above). This view only contributes sub-state and registers **no** global listener.
  - **Recording:** `currentSub()` gives `{view, mode, loopId}`. A handoff is recorded as inspect of that loop, and the conflict state as mode `create`.
    - The persisted vocabulary is unchanged: `view: create|history`, where `create` is the Primary tab. `dashboard.js` `cleanSub()` and `workspace.js` `cleanContextSub()` therefore need no change.
    - User selections call `shellPush()` → `GatorShell.pushSubState`: a tab switch, a card select, a conflict-list choice, create → handoff, and handoff → Open loop workspace. Automatic Primary transitions (`reconcilePrimary`, including the 409 recovery) use `shellReplace()`.
  - **Restoring (`applySub()`):** Primary content is always derived from the current list, never from the record:
    - `{view: create, …}` → Primary plus `landPrimary()`: the Create form, the active loop inspected, or the conflict state;
    - `{view: history, mode: inspect, loopId: L}` with L listed → History with L inspected, also when L is the active loop (pinned);
    - `{view: history}` without a listed L → History, with the Primary landing in the main pane.
  - **Mount:** `views.loop(…, initialSub)` applies `initialSub` through `applySub()` (else `applyDefaultSelection()`). It records the landing state with `shellReplace()` (no new entry), and focuses the main heading after a restore.
  - **`views.loop.restore(sub)`** applies a sub-state to the mounted view. It bumps `generation`, re-renders the History list, then runs `loadSelectedLoop()` or `renderMainContent()`, and moves focus to the main heading (`focusMainHeading()`). It never pushes.
  - **Pinned by** `test_old_loop_substate_records_restore`, `test_loop_back_forward_within_loop` and `test_history_tab_with_active_loop_round_trips`.
! **Creation workspace**: `renderCreateWorkspace()` renders feature name, sketch source picker (dropdown from `/sketch-sources` + manual path toggle), advanced settings disclosure (max rounds 1–20, turn timeout 30–3600s), and Create button calling existing start endpoint. Client-side validation before POST. 409 "active loop exists" is race-recovery only: see "Primary reconciliation and list failure".
! **Participant handoff**: `renderHandoff()` shows prompt-copy cards for Draftor and Reviewer roles. `copyPrompt()` fetches from the no-store prompt endpoint, writes to clipboard, then nulls the prompt variable. Clipboard unavailable: shows read-only textarea fallback, removed on dismiss. Join state polls at 3s interval; Draftor joining does NOT remove Reviewer copy action. "Open loop workspace" navigates to inspect mode explicitly — never auto-navigates on join.
! **Token non-persistence**: prompt text never stored in localStorage, sessionStorage, URL state, data- attributes, or console logs. JS variable nulled after clipboard write. DOM elements removed on navigation.
! **Live vs history**: `renderSelectedLoop()` orchestrates live or read-only workspace. Live loops show the calm header with controls, the approval resolution (approved coding), source line, notices, the suspension card (below), the Now line, the timeline, and the lower evidence section (artifacts, Candidate evidence, Participant recovery, liveness, Decisions). Terminal loops show outcome header with badge (Approved/Max Rounds/Timed Out/Ended), completed date, no controls, no prompts.
! **Calm workspace layout**: region order is fixed by `buildLoopSkeleton()`:
  1. `.loop-head`: `#loop-region-header` + `#loop-controls`;
  2. `#loop-region-resolution`;
  3. `#loop-region-source`;
  4. `#loop-region-notice` (three slots);
  5. `#loop-region-blocked`;
  6. `#loop-region-now`;
  7. `.loop-body`: `#loop-region-rail` (empty and `display:none` unless filled; the grid column exists only via `:has(> #loop-region-rail:not(:empty))`, stacked at ≤768px) + `.loop-timeline-col` (`#loop-timeline`);
  8. `.loop-lower`: `#loop-artifacts`, `<details id="loop-candidate-details">` › `#loop-region-coding` (`hidden` unless `isCoding`), `#loop-region-prompts`, `#loop-region-liveness` (never inside a closed disclosure, so Re-notify stays reachable), `<details id="loop-decisions-details">` › `#loop-region-decisions`;
  9. `#loop-dialog-host` (unpatched).

  The two `<details>` are skeleton-owned, so their `open` state survives polls.
  - **Header:** `renderLiveHeader()` is an eyebrow (`modeBadge` + `stageBadge`), the `<h3>` name and `.loop-counter-line` (`counterLineHtml()`: "Round X / Y", or for checkpoint loops "Checkpoint K of N · findings round r of b · Generation g" with `.loop-checkpoint-counter` / `.loop-generation-counter`). There is no status grid, no role ledger and **no time display** (Architect decision: no countdown and no elapsed time; do not reintroduce `timeRemainingText` / `elapsedText` / `updateTimeRemaining`; legacy loops still time out on the server). Join state is shown by Participant recovery.
  - **Now line:** `nowLine(status, terminal)` is pure and status-only (stage, `next_role`, round, `checkpointCounters`, `pendingDecision`, `OUTCOME_LABELS`). It never reads artifacts, time, liveness, `/snapshot` or a missing event. It returns `{state, glyph, text}`: active ▶ "Now: <Role> — <stage> (round r of m | checkpoint k of n). No action needed from you."; blocked ⚑ (names the escalating role and decision id, points to Respond/Resume); paused ⏸; implementation approved ✓ (defers to the resolution banner); max rounds ■; other terminal ■ "Outcome: …". `renderNowLine()` writes `p.loop-now[data-state]`. Its fingerprint is the JSON of that object. The amber rule for blocked/paused is a second cue only. **Paper type:** `.loop-now` is reading prose (`--text-base` / `--leading-prose`). The checkpoint rail stays `--text-sm` (12px/1.5), lighter than the Now line.
  - **Controls in the header:** live: Interject, then quiet (`.loop-ctrl-quiet`) Pause and End; paused/blocked: the unblock button labelled by `unblockActionLabel()` ("Respond" with a pending decision, else "Resume"), then End. Hooks and `data-action` values are unchanged. `renderControls()` is **button-only**: each button opens a dialog. Continue loop (max rounds) keeps its inline `renderContinueControl()` form.
  - **Focused intervention dialogs:** `openLoopDialog(kind, status, invoker)` builds one native `<dialog class="loop-dialog" data-kind>` in the unpatched `#loop-dialog-host` and calls `showModal()` (focus trap, inert page, Escape → `cancel` → close without acting). Only click handlers open one, never a poll.
    - **Kinds:** `loopDialogConfig()` defines:
      - **decision:** the full request in `.loop-blocked-reason`, the "View decision request" link (closes the dialog without restoring focus, then `wireArtifactJump`), and "Requested … · Resumes: …"; the required "Response to <Role> (required)"; "Record response and resume" → `unblock`; plus **End loop instead…**, which swaps in the End dialog;
      - **resume:** optional message → `unblock`;
      - **interject:** required message → `interject`;
      - **pause** and **end:** each with a consequence sentence; end posts `reason`.
    - **Validation and posting:** the existing hooks are reused (`.loop-ctrl-input-area`, `#loop-ctrl-message.loop-ctrl-input` with `<label for>`, `.loop-ctrl-label`, `.loop-ctrl-timeout` for legacy loops only (`!status.attention`), `.loop-ctrl-confirm`, `.loop-ctrl-cancel`, `.loop-ctrl-error[role=alert]`). The existing validation is unchanged: required decision response (Confirm disabled while blank, blank refused), required interject message, legacy turn-window bounds. Sending goes through `postAction()` only. A failure keeps the dialog open with the input. **Paper type:** `.loop-dialog-note` (the explanation) and `.loop-dialog .loop-blocked-reason` (the request text) are reading prose (`--text-base` / `--leading-prose`). `.loop-dialog .loop-ctrl-label` and `.loop-ctrl-input` are `--text-ui`. The title (`--text-section`), the meta lines and the buttons are unchanged. On the canvas, the blocked alert stays compact. Success closes it, then `showUnblockNotice` (unblock) and `loadSelectedLoop()`.
    - **One request in flight:** the pending action belongs to the selected-loop snapshot (`snap.pendingAction`), not to the dialog node.
      - **While sending:** the dialog's Cancel and End-instead are disabled, Confirm reads "Sending…", and the native `cancel` (Escape) is prevented. `setControlsPending()` disables the header dialog buttons (`#loop-controls .loop-ctrl-btn[data-action]`) and `.loop-blocked-respond`; `renderControls()` / `renderBlockedCard()` re-apply this on a rebuild. `openLoopDialog()` refuses with `DIALOG_PENDING_HTML` ("A request is still being sent…").
      - **If the browser still closes the dialog** (Escape without user activation), no second send is possible, and the completion is reported honestly in the action slot: "<title>: not sent — <error>", or "<title>: the request completed."
      - **On settle**, the pending state clears and the controls are usable again; a failure in an open dialog keeps the input for retry. The completion is dropped when the generation or snapshot changed.
    - **Placement:** `.loop-dialog` sets `margin: auto`, which restores the user-agent centring of a modal `<dialog>`. Without it, the global `*, *::before, *::after { margin: 0 }` reset would open the dialog at the viewport's top-left. Pinned by `test_loop_dialog_is_centred` (`test_loop_workspace.py`, 1440 and 375).
    - **Focus:** closing removes the dialog and returns focus to the invoker, or `focusMainHeading()` if the invoker was rebuilt.
    - **Context change:** when `controlsFingerprint` changes, `renderSelectedLoop()` closes an open dialog unsent (`closeLoopDialog`) and writes `DIALOG_CHANGED_HTML` ("…nothing was sent") to the action slot. After rebuilding the controls it moves focus to the first enabled `#loop-controls` button, or `focusMainHeading()` (`focusAfterDialogInvalidated()`), so keyboard focus never falls to the document body. A dialog that is sending (`data-sending`) is left to its own completion, which reports to the action slot if the dialog is gone. Identical polls touch neither the controls nor the dialog, so a typed draft survives.
  - **Checkpoint rail:** `#loop-region-rail` is filled only for declared-checkpoint coding loops (`checkpointCounters(status)` non-null); otherwise `renderRail()` leaves it empty, so there is no placeholder. `railItems()` reads only `status.coding.checkpoints` (`id`, `title`, `state`, `current`, `accepted_tree`): no plan parsing, no scope or Verify text, no request. Markup: `section.loop-rail[aria-label="Checkpoint progress"]` › `ol.loop-checkpoint-list` › `li.loop-checkpoint-item[data-state]` (✓ approved (tree …), ● active with `aria-current="step"` and weight 600, ○ not started). Glyph, text and weight carry the state; the amber rule and tint on the active item is a second cue. The rail is non-interactive; scroll-to-group is deferred (sketch). Fingerprint: `railFingerprint()` (the item list, or `"none"`). The list no longer appears in the coding facts panel, which keeps its Checkpoint and Generation rows.
  - **Decisions disclosure:** `syncDecisionsDisclosure()` writes only `hidden` (no decisions) and the summary count " (N)", each when it differs, and never touches `open`, so nothing opens automatically. `renderDecisionHistory()` writes no heading of its own.
! **Mode projection** — `loopModeInfo(src)` / `modeBadge(info)` is the ONLY place loop-mode text is decided. It accepts a `/loops` item (normalized `mode` plus boolean `mode_legacy`) or a `/status` body (raw `mode`) and returns `{key, label}`:
  - `coding` → **Coding**;
  - no recorded mode (status `mode` absent, or list `mode_legacy === true`) → **Planning · legacy**;
  - `planning` / `planning-only` → **Planning**;
  - anything else → **Unknown mode**.

  It never reads feature names, filenames or artifacts. `modeBadge` renders `span.loop-mode-badge[data-mode]` with `aria-label="Loop mode: <label>"`: text plus a per-mode border (2px solid coding, solid planning, dashed legacy, dotted italic unknown), never colour alone. It appears in `renderLiveHeader`, `renderOutcomeHeader` and every History card (`renderSidebarCard`, inside `.loop-card-badges` next to the stage badge). `headerFingerprint` includes the mode key, so identical polls stay mutation-free (pinned).
! **Participant recovery** — `#loop-region-prompts`, live loops only (terminal: empty, no `.loop-prompt-copy`). It replaces the bare copy buttons.
  - **Structure:** `renderPromptSection(terminal, root, snap)` builds, once per live snapshot (prompts fingerprint `live`/`terminal`): `<details class="loop-recovery" id="loop-recovery">` with summary "Participant recovery", the fixed guidance ("Use these prompts only to start a new participant session or reconnect one that dropped. Do not paste a prompt into a session that has already joined."), the credential warning, and one `.loop-recovery-row[data-role]` per role (a `.loop-recovery-need` line plus the existing `button.loop-prompt-copy[data-role]` → `copyPrompt()`). Copying is unchanged (epoch guard, fallback, token non-persistence) and mutates no loop state.
  - **`recoveryNeed(role, joined, livenessState)`** (pure):
    - not joined → "Has not joined yet.";
    - joined and `stale` → "Watcher is stale — reconnect if the session dropped.";
    - joined and `released` → "Watcher exited after a notification — reconnect if the session closed.";
    - otherwise (connected, `not_registered`, closed, unknown or liveness unavailable) → none, shown as "Joined — no action needed".

    **TRIPWIRE:** a joined role with no watcher (`not_registered`, e.g. a `gator loop wait` participant) is never flagged as absent.
  - **`applyRecovery(snap)`** runs after each `renderSelectedLoop()` (which stores `snap.statusRoles`) and at the end of `applyLiveness()`'s main path (`snap.liveness.lastView`).
    - It writes the need text (prefixed "⚠ "), the `data-need` flag (bold, never colour alone) and `open`, each only when it differs.
    - It changes `open` only when the need key changes: open when non-empty, close when empty. A manual toggle (`data-user-toggled`, set by a summary click) therefore holds until the need set changes.
    - Identical polls produce zero mutations (pinned).
! **Event-driven artifact enumeration**: `collectArtifactPaths()` derives immutable artifacts from event `artifact_path` fields and `status.decisions[]`, replacing the prior numeric round loop. Naturally includes round-zero artifacts. Deduplicates by path.
! Polls every 3s for non-terminal loops; stops on terminal state. `pollLoop()` increments `promptEpoch` immediately after terminal status is identified, before awaiting events — this closes the race window where an in-flight `copyPrompt()` could resolve during the events fetch and write to the clipboard with the old epoch. Teardown clears interval via `window._gatorRepoTeardown`.
! **TRIPWIRE:** expanded artifact text reaches the DOM only through `GatorLoopMarkdown` DOM construction (Rendered) and `pre.loop-artifact-pre.textContent` (Raw), both from the **same fetched string**. Raw is never reconstructed from rendered nodes, and artifact text never goes through `innerHTML`. This replaces the earlier "escaped through `escHtml()` and rendered in `<pre>`" rule.
! **Planning sources.**
  - **Create form (planning mode):** a "Plan source" radio group (`input[name="loop-plan-source"]`) with three options:
    - **sketch:** unchanged;
    - **revision:** `#loop-revise-select` (approved planning loops from `/loops`) plus a "Revision sketch";
    - **architect_plan:** `#loop-plan-path`, with the sketch labelled "(optional)".

    `applyPlanSourceFields` / `setPlanSource` / `loadRevisePicker` drive it. The POST carries exactly the chosen source's fields (`sketch_path` / `revise_from` / `plan_path`). Client checks are convenience only.
  - **Coding prefill:** `prefillFeature` writes the source's feature name only into an EMPTY field, or one still holding the earlier prefill, and it stays editable (pinned).
  - **Inspection:**
    - `#loop-region-source`, via `renderSourceLine` and `sourceFingerprint`, shows "Source: Architect-originated draft — awaiting Reviewer approval (not approved)" / "…approved by the Reviewer" / "…now under Draftor revision" / "Source: Revision of <id>", with `[!! …]` integrity text, never colour alone.
    - `renderArtifacts` puts provenance first (`sourceArtifactEntries`): `architect-plan.md` ("Architect-originated draft plan (provenance, unapproved)"), or the two baselines ("Baseline: approved plan from <id>", "Baseline: approving review"). A revision loop's `sketch.md` is labelled "Revision sketch"; an Architect-plan loop without a sketch lists no `sketch.md`.
    - `artifactsFingerprint` includes the provenance views.
    - The timeline label `architect_plan_submitted` is "Architect plan — awaiting Reviewer".
    - Unchanged polls are mutation-free (pinned).
! **Suspension card** — `#loop-region-blocked`, `renderBlockedCard()`. It is built ONLY from fields the loop writes: `stage`, `resume_stage` / `resume_next_role`, `suspended_at`, `pause_reason`, and the pending decision's `request` (`reason`, `role`, `ts`, `artifact_path`). The fictitious `status.escalation_reason` that hid the old card is gone.
  - **Blocked** (`.loop-decision-card`, `data-kind="architect_decision"`): L1 compact alert — "⚑ Blocked — awaiting your decision", then `decision-N · requested by <Role> · <time> · Resumes: <Role> · <stage>` and a `button.loop-blocked-respond` ("Respond", or "Resume" with no pending decision) that opens the decision (or resume) dialog. The full reason (`.loop-blocked-reason`, `white-space: pre-wrap`) and the "View decision request" link live in the decision dialog only.
  - **Paused** (`.loop-hold-card`, `data-kind="architect_hold"`): "⏸ Architect hold (paused)", "No participant response is required.", `Preserved:`, `Since:` and the pause reason. It never uses escalation wording.
  - **Telling them apart:** title text, glyph and border style (dashed for a hold), never colour alone.
  - **Fingerprint:** `blockedFingerprint` covers every field read, so unchanged polls are mutation-free (pinned).
! **Decision history** — `#loop-region-decisions`, `renderDecisionHistory()`, fingerprint `decisionsFingerprint` (ids + response kind/ts). It lists every `decisions[]` entry, including on terminal loops: the request (role, time, reason, "View request") and the resolution.
  - Resolution labels come from `RESPONSE_KIND_LABELS`, including "Cancelled — loop ended" for `cancelled_by_end`; an unknown kind shows "Resolved".
  - Each label carries a glyph: ✓ resolved, ○ pending (bold).
  - Text goes through `escHtml()` with pre-wrap. Artifact links reuse `wireArtifactJump()`.
! **Full-detail timeline events**: `FULL_DETAIL_EVENTS` (`loop_paused`, `loop_unblocked`, `escalated`, `architect_interjection`, `loop_ended_by_architect`) render their detail with `.loop-event-detail-full` (`pre-wrap`, no ellipsis), so a multi-line pause reason or unblock response stays readable after the hold ends. Other events keep the single-line ellipsis (pinned).
! **Unblock notice** — `showUnblockNotice()` writes the `action` slot after a successful unblock: "Unblocked. <Role> resumes at <stage> when its watcher or wait sees the change. The Dashboard does not run model work." It never claims model work.
! Architect controls are contextual: active loops show Interject/Pause/End; paused/blocked loops show Respond or Resume/End; terminal loops show no controls (max rounds: Continue). Each button opens a focused dialog (above); Interject requires a non-empty message. Controls POST via `postAction()` with anti-CSRF header and re-poll on success. Non-2xx control responses render a `.loop-ctrl-error` message in the dialog and keep it open with the input for retry.
! Unblock is decision-aware via `pendingDecision(status)`: with a pending decision (escalation) the field is labelled **Response to participant (required)**, Confirm stays disabled until non-blank, and blank input is refused before any request (text error + thicker border, not color alone); an ordinary Architect pause keeps **Message (optional)**. **Legacy loops only** (no `status.attention`): Unblock also shows a **Turn window (s)** number input defaulted to the session's `status.turn_timeout_seconds` (not a hard-coded 300), client-checked against `TURN_TIMEOUT_MIN/MAX` (mirrors `loop/session.py`), and sent as `timeout` only when changed. Attention-mode loops never show the field and never post `timeout` (`legacyWindow = !status.attention`). The Dashboard exposes no deliberate-empty (`no_response`) control — that exceptional path is CLI-only (`--no-response`). The server re-validates everything.
! **Incremental rendering**: `renderSelectedLoop()` builds a stable skeleton once per selection (`buildLoopSkeleton()` — regions listed under Calm workspace layout above; `#loop-region-notice` is unpatched, with named slots `refresh`, `action` and `attention`, see below; `#loop-region-liveness` is field-patched, see below) and records `_state.render` = {generation, loopId, root, per-region fingerprints, timeline cursor}. The snapshot is invalid (skeleton rebuilt) when `_state.generation` or `selectedLoopId` changes or the root is detached; `teardownLoopView()` and a null status clear it. Every selection/mount/mode transition bumps `generation`, so no stale snapshot survives.
! Per poll, `patchRegion()` rewrites a region only when its fingerprint changes: `headerFingerprint()` (terminal, stage, round, `max_rounds`, identity, checkpoint counters, mode key — L1 dropped times, joins and next role), `now` (the `nowLine()` object), `blockedFingerprint()` (escalation + pending decision), prompts (live vs terminal), `controlsFingerprint()` (only renderControls() inputs: terminal, paused, pending decision id, turn window, `!!status.attention`), `artifactsFingerprint()` (event count + last event key + decision artifacts). An unchanged poll performs **no** main-panel DOM writes (L1 removed the countdown/elapsed text patch, the last permitted per-poll write; pinned with no exemption). `setAttentionNotice()` writes only when its derived state changes. Fingerprints use returned data, never wall-clock time.
! **Multiline input:** the shared control input (inside the L1 dialog) is `<textarea id="loop-ctrl-message" class="loop-ctrl-input" rows="4">` with `<label for>` association and an `aria-label` fallback. The required unblock label names the escalating role ("Response to Reviewer (required)"; "participant" when unknown). A typed draft survives unchanged polls with zero mutations in the controls, suspension and decision regions (pinned).
! Because controls and the dialog host are untouched unless the control inputs change, an open dialog (message / required response) survives polling without any "skip while composing" rule; if the control context really changes (e.g. unblocked elsewhere) the controls are rebuilt and the dialog closes unsent with a notice, which is correct.
! Timeline: **newest first, grouped.**
  - **Scheme.** `snap.timelineScheme` is fixed on a snapshot's first render: `"checkpoint"` when `checkpointCounters(status)` is non-null, else `"round"`.
  - **Key.** `timelineGroupKey(ev, scheme, prevKey)` reads event fields only:
    - checkpoint scheme: `cp:<checkpoint_id>`; an untagged event inherits `prevKey` even when it has a `round`, so a pause, interjection, escalation, unblock or reopen stays in its checkpoint;
    - round scheme: `r:<round>`, inheriting when there is no numeric round;
    - leading keyless events: `start`.
  - **Groups.** `timelineGroups()` makes contiguous runs in chronological order: a recurring key after a different one opens a new group, so global newest-first order is never broken. `renderTimeline(events, root, scheme)` writes `section.loop-tl-group[data-group]` › `h4.loop-tl-group-label` ("Checkpoint cp2" / "Round 2" / "Start", from event fields, no status titles) › `.loop-tl-cards`, newest group first and newest card first. It returns the front key (`snap.frontGroupKey`).
  - **Patching.** `updateTimeline()` front-patches strictly-new events when the previously rendered newest event (`eventKey()`: ts|event|round) is still at the same index. Each new event is keyed with `prevKey = snap.frontGroupKey` (the same function as the full render) and inserted first in the front group, or as a new front group. Any other change redraws just `#loop-timeline`. Unchanged polls make no timeline writes. Cards still come from `eventCardHtml()` and stay link-only.
! Artifacts: `renderArtifacts(status, events, root, refreshMutable)` reconciles sections by `data-artifact` — existing nodes keep expanded state and loaded content and are only re-ordered; new ones come from `createArtifactSection()`; missing ones are removed. On event-log change (`refreshMutable`), `MUTABLE_ARTIFACTS` (`plan.current.md`, `findings.current.md`, `implementation.current.md`): loaded content refreshes in place if expanded, or is marked unloaded if collapsed. Collapsed artifact cards carry **no excerpt and never fetch**; `loadArtifactSummary()`, `isSummaryArtifact()` and the `.loop-artifact-summary` node were removed. `fetchArtifact()` uses `cache: "no-store"` so refreshes are real.
! Artifact fetch ordering: `loadArtifactContent()` bumps a per-node request revision (`nextRequestRev()` → `content._gatorContentRev`) before each fetch and apply a completion only if it is still the latest for that node (in addition to the generation and `isConnected` checks). An older in-flight response for a mutable artifact therefore cannot overwrite newer content. A refresh of a collapsed mutable section also bumps the content revision so an in-flight body fetch cannot mark it loaded with stale text; an expanded section (loaded or still loading) is always refetched.
! Terminal transition patches header/prompts/controls in place (never an empty intermediate panel), then polling stops. Under the Primary tab a finished loop is instead replaced in the same poll (see "Primary reconciliation and list failure").
! **Terminal is not always final.** For `max_rounds_exceeded` (`EXTENDABLE_STAGE`) `renderControls()` delegates to `renderContinueControl()`: a **Continue loop** button opening **Additional rounds** (number, `ROUNDS_MIN..ROUNDS_MAX` = 1..20, mirrors `loop/session.py`, default 2) and **Reason (required)**. Confirm stays disabled until the reason is non-blank; invalid rounds or a blank reason are refused before any request with a text error (not colour alone). It POSTs `{rounds, message}` to `/extend` via `postAction()`. Every other terminal stage renders no controls. `controlsFingerprint()` includes the extendable-stage flag so this control is (re)built only when that input changes.
! On extend success: `showExtendNotice()` writes to `#loop-region-notice` — a skeleton region that incremental rendering never patches, so the notice survives the terminal-to-live transition (cleared only by a skeleton rebuild on selection change). It states old → new ceiling and the participant re-engagement step, plus a **Warning:** line when `watcher === "failed"` (timeouts not enforced) or a neutral line for `already_hosted`. Then `ensurePolling()` restarts the interval (polling had stopped at terminal) and sets `data-polling="1"`, `refreshSidebarOnly()` moves the loop to Active, and `loadSelectedLoop()` patches header/prompts/controls live while timeline and artifacts are preserved; the timeline appends the `loop_extended` card (`EVENT_LABELS.loop_extended = "Extended"`).
! **Architect brief**
  - **Create form.** An optional "Architect brief (optional, Markdown)" textarea with a **UTF-8 byte** counter: `briefByteLength()` uses `new TextEncoder()`, labeled "N / 32,768 bytes", never string length. Over the limit the counter adds "over the limit…" (bold and underlined), Create is disabled, and the submit path refuses too. A blank brief is omitted from the POST; the server stays authoritative.
  - **Artifact inspector.** `briefEntries(status)` reads only the strict status projection. A position is listed when its check is not `absent`, and LINKED only when its positionally bound view is non-null. The artifact name is always the fixed constant for that position, never metadata. Linked briefs sort right after the plan (`renderArtifacts()` puts `approved-plan.md` / `plan.current.md` first), labeled "Architect brief" / "Architect brief (this coding loop)" / "Architect brief — from approved plan", with "(required reading)" when ok or "[!! DIGEST MISMATCH]" (and the other states) as text.
  - **Text-only notes.** Invalid references ("…: INVALID REFERENCE — escalate to the Architect") and a dropped planning brief ("Planning brief: not carried forward (Architect's choice at coding start)") are notes in `.loop-brief-notes`, with no link and no fetch.
  - **Change detection.** Labels and notes are written only when they differ, and `artifactsFingerprint` includes the brief metadata, checks and decision, so identical polls produce zero mutations (pinned).
! **Coding-loop creation:** the create form has a **Loop type** radio: "Planning — draft a plan from a sketch" or "Coding — implement an approved plan".
  - **Coding mode** hides the sketch field and shows "Approved planning loop", a select filled from `/loops` filtered to `mode === "planning" && stage === "plan_approved"`. With none, it shows "No approved planning loops to implement" and Create is disabled.
  - **Source brief state.** Selecting a source fetches that loop's `/status` (`loadSourceBrief`) behind two independent stale guards: a per-select `_create.sourceRev` revision, and a check that the select still shows that source. A stale response can never update the control (pinned; the test fails only when both guards are removed). While pending, the form says "Checking the approved plan's brief…" and Create is disabled.
  - **The keep/drop control** ("Include the approved plan's Architect brief", checked by default) is shown for every non-`absent` `brief_check`. Corrupt states add a text warning: "…failed its integrity check (DIGEST MISMATCH). Keeping it will fail; uncheck to start without it."; it is never auto-unchecked. A failed fetch shows "Brief state unknown"; the server decides. `absent` hides it, and `source_brief` is omitted.
  - **The POST** carries `mode`, `from_loop`, `source_brief` (`keep` / `drop` when shown) and the optional `brief`, never `sketch_path`. The server's honest error (for example, keep on a corrupt brief) appears in `#loop-create-error`.
  - **`updateCreateEnabled()`** combines the byte limit, no sources and pending source state.
! **Architect attention:** this is the Architect's own view; participants never see Dashboard time.
  - **Header:** L1 removed the "Elapsed this turn" item and the legacy "Time Remaining" countdown (Architect decision: no time display). The attention notice below is unchanged and is the Architect's attention signal.
  - **Notice:** `#loop-region-notice` gains a third slot, `attention`, owned only by `setAttentionNotice()`. It derives a state (`notified|<turn>`, `unrecorded|<turn>` when `due && !notified`, or empty) and writes the slot and the selected sidebar card's marker **only when that state changes**, so identical polls are mutation-free.
    - Notified text: "◷ Attention: Draftor has been active for at least 5 min in revision. The loop is still running — interject, pause, or end if needed; no action is required."
    - Unrecorded text (P2) follows **only** the server's authoritative `attention.host`:
      - `none`: "…no notice recorded — no loop host is running for this loop, so attention notices are not being recorded.";
      - `attached`: "…notice pending — the loop host records it on its next check.";
      - `unknown` or missing: neutral, "…no notice has been recorded for this turn yet."

      Host absence is never inferred from a missing marker. The state key includes the host value, so a host change rewrites the notice.
    - It uses `role="status"` and `.loop-attention-notice` (dashed border, glyph and bold label, never an error colour). It never touches the `refresh` / `action` slots or open controls, and clears when the turn changes or the loop pauses or ends.
  - **No sidebar marker:** the `.loop-card-attention` "◷ attention" marker lived on the active-loop card and was removed with it; `setAttentionNotice` writes only the notice slot. The browser no longer reads the `/loops` item's `attention_notified` (the server field is unchanged).
  - **Unblock control:** `legacyWindow = !status.attention`. Attention loops never show the "Turn window (s)" field and never post `timeout`. The controls fingerprint includes `!!status.attention`.
  - **Create form:** the field is labelled "Architect attention interval (seconds)" with the hint "Architect notice only — participants never see it…", and posts `attention_interval`. The element id `#loop-turn-timeout` is kept.
! **Coding candidate panel**: `#loop-region-coding` (facts, inside the collapsed "Candidate evidence" disclosure) and `#loop-region-resolution` (the approval banner, next to the header), shown only when `status.mode === "coding"` (they use the slim `status.coding` projection). L1 split them by responsibility: `renderCodingRegion()` / `codingFingerprint(status)` (stage, round, `max_rounds`, projection) own the facts; `renderResolution()` / `resolutionFingerprint(status, live)` own the banner and Reopen.
  - **Facts:** the approved plan's source loop and sha, the base commit, and the latest candidate (round, staged tree / HEAD / branch or detached, changed-path counts by status), plus the review verdict with a "candidate had changed" note.
  - **Residue:** a "Note:" line when residue outside the loop directory is non-zero. Loop residue is never warned about.
  - **Live resolution (`implementation_approved` only):** `refreshCoding()` fetches the Architect-only `/snapshot` (no-store) and renders one banner. Each state is text plus a distinct glyph plus weight or style (`data-state`), never hue alone:
    - ✓ Committed (commit),
    - ● Pending commit — one normal commit,
    - ⚠ Stale (reason text from `STALE_REASON_TEXT`, word for word the CLI's `_STALE_REASONS`: `staged_tree_changed`, `head_moved_tree_differs`, `detached_mismatch`, `history_diverged`; an unmapped reason shows raw),
    - ? Unknown — never treat as approved. When `live.live.guidance` is a string, a `div.loop-coding-guidance` shows it as escaped plain text under the banner (normal weight, gray; the glyph and label carry the state). The browser never parses Git text.

    The state comes from the server alone. Committed survives later commits, with the historical approval commit, and a detached HEAD after approval reads Stale. The browser holds no Git-history logic.
  - **Reopen:** a **Reopen for revision** button appears only for Stale or Unknown. It opens an inline required-reason form, Reopen stays disabled while the reason is blank, and it POSTs `/reopen` `{message}` with `X-Gator-Dashboard`. The notice reports invalidation and the watcher state.
  - **Patching:** each region is rewritten only when its own fingerprint changes; the resolution region never while the Reopen form is open (`data-reopen-open` on `#loop-region-resolution`; Reopen's close deletes `snap.fp.resolution`). `resolutionFingerprint` includes the stage, resolution state, reason, commit, `approved_tree`, and the live `ok` / `error` / `guidance`. Identical polls produce zero mutations (pinned).
  - **Checkpoints** apply when `status.coding.checkpoints` is present, which is declared loops only.
    - **Counters.** `checkpointCounters(status)` builds them from the projection plus `status.max_rounds`.
      - The **live header** replaces "Round X / Y" with a "Checkpoint" item ("Checkpoint K of N · findings round r of b", `.loop-checkpoint-counter`) and a separate "Generation" item (`.loop-generation-counter`, "none yet" before the first submission).
      - The **outcome header** and the handoff subtitle do the same.
      - **History cards** (`renderSidebarCard` via `sidebarCounterText`), show "Checkpoint K/N · findings r/b · gen g" from the `/loops` `checkpoint_summary`.
      - Every other card and header keeps "Round X/Y". **A checkpoint loop never renders `Round X/Y`** (pinned, with `status.round` 3 > budget 2).
    - **Coding region:**
      - Checkpoint and Generation rows; the candidate row reads "Candidate (cpK · gen g)".
      - The per-checkpoint progress list moved to the L1 rail (see Calm workspace layout above).
    - **Labels.** `EVENT_LABELS.checkpoint_approved = "Checkpoint approved"`. Timeline cards and artifact toggles add "(cpK · gen g)" from event fields only (`checkpointSuffix` / `artifactSuffixes`), never by parsing artifacts.
    - **Fingerprints.** `headerFingerprint` includes `checkpointCounters`, `artifactsFingerprint` includes `artifactSuffixes(events)`, and `codingFingerprint` includes `max_rounds`. Identical polls leave the coding region and the counter nodes untouched (pinned).
  - **Coding loops elsewhere in the view:**
    - stage labels and badges cover `implementation_drafting` / `implementation_review` / `implementation_revision` / `implementation_approved`, and `implementation_approved` is in `TERMINAL_STAGES`;
    - the artifact inspector lists `approved-plan.md`, `implementation.current.md` and `findings.current.md` first (no sketch or plan), `implementation.current.md` is mutable, and the `implementation.*` / `approved-plan.md` artifacts show summaries;
    - the event labels add `implementation_submitted`, `implementation_approved` and `loop_reopened`.
! **Refresh-failure visibility and notice ownership:**
  - **Three named slots.** `#loop-region-notice` holds `[data-slot="refresh"]`, `[data-slot="action"]` and `[data-slot="attention"]`. `noticeSlot()` / `setNotice()` write exactly one slot.
    - **Action:** Architect action results only — `showExtendNotice()` (Continue), `showLivenessNotice()` (Re-notify), and the Reopen notice.
    - **Refresh:** owned solely by `pollLoop()` through `setRefreshFailed()`.
    - **Attention:** owned solely by `setAttentionNotice()`, for attention-mode loops; it is empty for legacy loops.

    No path assigns the whole region's `innerHTML`, so clearing the refresh or attention notice can never erase an Architect message.
  - **On a failed poll** (`fetchStatus()` gives null, `fetchEvents()` gives **null**, or the list fetch gives null):
    - `pollLoop()` returns without rendering, so the last valid workspace, artifacts, open controls, expanded sections and scroll all survive, and polling continues on the same single timer;
    - it shows the text-led "Refresh failed — retrying." notice (`role="status"`).
  - **On recovery:** the next successful full status, events and list refresh clears only that notice. `setRefreshFailed()` writes only when the state changes, so repeated failures and successes are mutation-free.
  - **Stale guard:** it acts only if the snapshot is still `_state.render` for the same generation and `selectedLoopId`, with an attached root. A stale in-flight response can't set or clear a notice on a newer selection.
  - **Initial-load failure keeps its behavior:** the notice is shown only after a valid render of this selection, and `loadSelectedLoop()` still renders a failed events fetch as `[]`.
  - **`fetchEvents()` returns null on failure** (HTTP error, network, or a non-array body) and `[]` only for genuinely no events. A failure must never render as an empty history, which would prune event-derived artifact sections (the pre-fix behavior).
! **Teardown is installed before the first await.** `GatorViews.loop` sets `window._gatorRepoTeardown = teardownLoopView` right after building the skeleton, **before** `await fetchLoops()`.
  - **The leak it prevents:** `teardownLoopView()` at mount start nulls the hook. If the hook were installed only after the first list returned, leaving Loop while that list was in flight would leave the shell nothing to call: `mountId` would not change, the late list would land in the detached view, and `ensurePolling()` would start a 3-second poll (list, status, events) that nothing stops until a page reload.
  - **Now:** leaving Loop runs the teardown, which bumps `mountId`, so the post-await `myMount !== _state.mountId` check drops the late list, and no timer starts.
  - **Pinned by** `test_departed_mount_does_not_resurrect_polling`, whose non-blocking hold fails deterministically without the fix.
! **Polling ownership:**
  - `ensurePolling()` is the ONLY place an interval is created, at mount and on selection alike; a second, leaked interval would survive clearing at terminal stages.
  - `loadSelectedLoop()` calls it whenever the selected loop is non-terminal, so selecting a live loop after a terminal one resumes polling without re-navigating.
  - An approved coding loop stays polled (its resolution can move from Pending to Committed or Stale with no loop-state change). `pollLoop()` stops the timer only for other terminal stages.
! **Participant liveness panel** — `#loop-region-liveness`, Architect loop view only. While the loop is paused or blocked (`snap.suspended`, set by `renderSelectedLoop`), a connected role reads "● Connected — waiting through the hold".
  - **Fetching.** `refreshLiveness()` runs after every `renderSelectedLoop()` from `loadSelectedLoop()` and `pollLoop()`. It fetches GET `/liveness` with `cache: "no-store"` and drops the result if generation, snapshot or loopId changed. The fetch uses the allowlisted server view only; no other liveness data reaches the browser.
  - **Rendering.** `applyLiveness()` builds the panel once per snapshot (`snap.liveness.built`), then patches field by field:
    - the state and notification lines via `setText()`, and visibility via `setHidden()`, each written only when the value differs;
    - rendered text comes from returned data only: absolute `formatTime()` times, never "Ns ago".

    An identical poll or a repeated denial therefore produces **zero DOM mutations** (pinned by MutationObserver tests).
  - **Re-notify form.** Each role's action area holds a Re-notify button only when `renotify_eligible`. It is rebuilt only when that flag changes AND no inline reason form is open (`data-open="1"`), so a typed reason survives polling.
  - **Posting.** `postRenotify()` POSTs `{role, reason}` with `X-Gator-Dashboard: 1` and `no-store`. The result goes to `#loop-region-notice` (`showLivenessNotice()`): "Re-notify sent: … does not change the loop or prove any work", or "Re-notify not sent:" with a mapped reason for terminal / already_acknowledged / not_actionable / rate_limited / unavailable. On a refusal the form stays open and Send is re-enabled.
  - **Colorblind-safe states.** Each state is text plus a distinct glyph plus weight or style, never hue alone:
    - ● Connected · seen HH:MM:SS
    - ◐ Stale — last seen HH:MM:SS (bold and underlined)
    - ◇ Released — watcher exited after delivery
    - ■ Closed — loop ended (italic)
    - ○ Not registered (italic)
  - **Degraded modes.**
    - 403/404: "Liveness unavailable for this loop (no Architect authority on record)".
    - `available: false`: "Delivery unavailable — the loop runs normally".
    - `retry` keeps the last good view.
    - `corrupt`: "Liveness record unreadable; delivery degraded".
  - **Fixed footnote.** "Acknowledged means received — not that the model read, worked on, or will submit anything." It names Claude Code background tasks (open session), and says other participants use `gator loop wait`.
! Known limit: a view already showing a terminal loop does not poll, so an extension made elsewhere (CLI) appears after reselecting the loop.
! **Timeline cards never fetch; the summary comes from the event**:
  - **Summary from the event.** For an event with an `artifact_path`, `eventCardHtml()` renders, after the metadata and before the link, either `<p class="loop-event-executive">` + `escHtml(text)` for a valid projection, or `<p class="loop-event-executive loop-event-executive-absent">Executive summary unavailable for this artifact.</p>`. An event without `artifact_path` gets neither, whatever its `executive_summary` holds.
  - **`eventSummary(ev)` (closed projection check).** It returns display text only when `ev.artifact_path` is present, `typeof ev.executive_summary === "string"`, and the value collapsed by `/\s+/g` → " " and trimmed is 1–`EXECUTIVE_SUMMARY_MAX` (1,200) Unicode code points, counted with `Array.from(text).length` (the CLI's `len()` unit; `String.length` would count an astral character twice and hide valid stored text); otherwise null (whitespace-only, wrong type, over-limit). Non-canonical whitespace is normalized for display, never rejected. `EXECUTIVE_SUMMARY_MAX` mirrors `submit.EXECUTIVE_SUMMARY_MAX` (pinned by `test_summary_bound_matches_cli`). Pure: event data only, never an artifact read; participant text is never HTML.
  - **Detail rule.** `PARTICIPANT_SUMMARY_EVENTS` (`draft_submitted`, `revision_requested`, `plan_approved`, `max_rounds_exceeded`, `implementation_submitted`, `checkpoint_approved`, `implementation_approved`) show only `ev.role` as detail, legacy events included, so a tree id or path count never competes with the paragraph. Every other event keeps today's detail logic, including `FULL_DETAIL_EVENTS`.
  - **Layout.** `.loop-event` wraps; `.loop-event-executive` and `.loop-event-link-row` take a full line (`flex-basis: 100%`). The paragraph is plain reading prose (`--text-base` / `--leading-prose`), normal weight, with no border or background. A card that carries one gets `padding: var(--space-3) 0` through `.loop-event:has(> .loop-event-executive)`; other cards keep 6px. The absence line is 12px italic `--gray-600`, and the words carry the meaning, never colour alone. The event time and label stay 12/13px, and "View full artifact" is `--text-sm` (it was 11px). This is CSS only: a front-patched card gets its final styling as it is built, with no reconciliation pass.
  - **Synchronous link.** `eventCardHtml()` renders the event metadata (time, label, escaped detail) and, for an event with an `artifact_path`, a link built from that metadata: `<a class="loop-timeline-artifact-link" href="#" data-artifact="…">View full artifact</a>` (`escHtml()`; `href="#"` makes it keyboard-focusable). The link never depends on an Executive Summary heading or on a fetch.
  - **Click binding only.** `wireTimelineCards()` only binds clicks: it **never fetches artifact text**.
  - **Following a link.** `openArtifactSection(parentEl, name)` (with a `CSS.escape`'d selector) scrolls to the matching artifact card and clicks its toggle **only if it is collapsed**. An open card stays open. The artifact is then fetched once, by the card's own expand path, and opens Rendered by default with Raw as a toggle.
  - **Not present (do not reintroduce):** `extractSummary()`, `SUMMARY_MAX_CHARS` / `SUMMARY_RE`, `window.GatorViews._extractSummary`, the `.loop-event-summary` / `.loop-timeline-summary-*` nodes and styles. Summaries never come from artifact extraction: the summary is the CLI's event projection, captured at submission.
  - **Pinned by** `tests/test_dashboard_ui/test_loop_workspace.py`: `test_timeline_card_summary_from_event` (escaped paragraph between metadata and exactly one `href="#"` link, participant markup stays text, role-only detail, no `_extractSummary`); `test_timeline_projection_validity` (bound: at-limit, normalized and an emoji at the 1,200-code-point limit shown; empty, whitespace, number, null, list, over-limit and an emoji at 1,201 code points → absence line; link kept); `test_timeline_absence_only_for_artifact_events` (absence only on artifact cards, full Architect detail kept); no link on an event without an artifact; a link without an Executive Summary; **zero `/artifact/` requests** on initial render and on appended events (an appended event's summary comes from the event) until a link is followed, then exactly one; an open section stays open with no refetch; keyboard Enter activation; and the existing navigation and round-zero link tests. Mutation-checked: a restored timeline fetch, an unconditional toggle, a missing link, and a missing `href` each fail it.

## Before Changing This Module

- Confirm the backend wire schema and empty/error states.
- Exercise keyboard/mouse navigation and narrow/wide layouts.
- Keep the UI dependency-free unless the product architecture explicitly changes.

## Connections

-> [Dashboard Server](scripts-dashboard.md) - APIs, security, and content policy
-> [Dashboard Shell](scripts-dashboard-shell.md) -- navigation, workspace tabs and styling the Loop workspace relies on
-> [Dashboard Views](scripts-dashboard-views.md) -- sibling views; Welcome's copy protocol is the model for the Extras copy action
