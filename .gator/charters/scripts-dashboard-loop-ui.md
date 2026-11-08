# Charter: Loop Workspace View

**Covers**: `src/gator_command/scripts/dashboard/views/loop.js`, `src/gator_command/scripts/dashboard/views/loop-markdown.js`

## Owns

The Loop workspace in the browser: Active, History, Create and the Help and Extras tabs, the live timeline, checkpoint rail, artifacts and Architect controls, and the sanitized Markdown renderer it uses. The shell is in [Dashboard Shell](scripts-dashboard-shell.md).

- The Primary tab's derivation from the loop list, and History selection and sub-state.
- The create form for every planning source and for coding loops.
- Participant handoff and recovery prompts.
- The selected-loop workspace: header, Now line, suspension card, Architect controls and dialogs, timeline, artifacts, coding resolution, checkpoint rail, attention notice and liveness panel.
- Incremental rendering and the view's single polling timer.

## Does Not Own

- Route authorization, path containment, filesystem access, or data computation; see [`scripts-dashboard.md`](scripts-dashboard.md).
- Governance business rules. Every state, decision, resolution and liveness value comes from the server; the browser only projects it.
- Cumberland document-template styling; see [`contracts.md`](contracts.md).
- The page shell, navigation, workspace tabs, requests and styling; see [Dashboard Shell](scripts-dashboard-shell.md).
- The other views; see [Dashboard Views](scripts-dashboard-views.md).

---

## TRIPWIRE: View-Wide Rules

These hold across every entry below.

- **Unchanged polls write nothing.** Each region is rewritten only when its fingerprint changes, and fingerprints use returned data, never wall-clock time. An identical poll makes zero DOM mutations in the main panel, timeline, controls, notices, recovery and liveness regions. This is what keeps an open dialog, a typed draft, an expanded artifact and focus alive without any "skip while composing" rule. Pinned by the MutationObserver tests in `tests/test_dashboard_ui/test_loop_workspace.py`.
- **A failed fetch is never an empty result.** `fetchLoops()` and `fetchEvents()` return null on any HTTP, network or shape failure, and `[]` only for a genuinely empty answer. A failed list is never "no active loop"; a failed event log never prunes event-derived artifact sections.
- **Participant and artifact text never becomes markup.** Event text goes through `escHtml()`; artifact text reaches the DOM only through `GatorLoopMarkdown` DOM construction (Rendered) and `textContent` (Raw), both from the same fetched string. Never `innerHTML` for either.
- **Prompts are never persisted.** Prompt text is never stored in `localStorage`, `sessionStorage`, URL state, `data-` attributes or the console. The variable is nulled after the clipboard write, and prompt DOM is removed on navigation.
- **No time display.** Architect decision: no countdown and no elapsed time (do not reintroduce `timeRemainingText` / `elapsedText` / `updateTimeRemaining`). Legacy loops still time out on the server; the attention notice is the Architect's only time signal.
- **Never colour alone.** Every state (mode badge, Now line, suspension card, resolution banner, checkpoint rail, liveness, recovery need) carries text plus a glyph, weight or border style; colour is a second cue only.

---

### render(text) / safeHref(url) — window.GatorLoopMarkdown
File: src/gator_command/scripts/dashboard/views/loop-markdown.js
A closed display formatter for expanded Loop artifacts, which are hostile, model-authored text. Loaded before `views/loop.js` and inlined by `build_snapshot()`.
- **Closed grammar**, one linear pass, no nesting or recursion; anything else is literal text. Lines: fence → `pre > code` (to EOF if unclosed); `#`…`######` → `h3`–`h6`; rule → `hr`; `>` → one-line `blockquote`; `-`/`*`/`+` and `N.` items → `li` in one flat `ul` with `md-indent-0..3` (numbers kept literal); `|` tables with a delimiter line (≤ 32 columns, in `div.loop-md-tablewrap`). Inline, first match wins: `![…](…)` as one literal text node (before links, so never an image or link), `` `code` ``, `[text](url)`, `**bold**`.
- **`safeHref`** accepts only an absolute `http:` / `https:` URL with no control characters or backslash; anchors get `target=_blank` and `rel="noopener noreferrer nofollow"`. A rejected link is literal `text (url)` in `span.loop-md-link-blocked`.
- **Bounds:** `MAX_RENDER_CHARS` (200,000); longer input throws `TooLarge` and the caller shows Raw.
<- `renderArtifactBody()`
! TRIPWIRE: output only through `createElement` / `createTextNode`. Elements are limited to `h3 h4 h5 h6 p ul li pre code strong a table thead tbody tr th td blockquote hr div span`; classes to `md-indent-0..3`, `loop-md-tablewrap`, `loop-md-link-blocked`; `a` attributes to `href` / `target` / `rel`. No `style`, `on*` or `src`.
! The grammar is a complexity budget (≤ 160 non-comment lines). A new rule needs a plan revision.
- **Pinned by** `tests/test_dashboard_ui/test_loop_markdown_ui.py` (adversarial-corpus allowlist walk).

### buildLoopTabs() / applyTabState() / currentTab() / switchTab() / renderHistoryList() / syncListChrome() / applyPrimaryLabel() — tabs and History list
File: src/gator_command/scripts/dashboard/views/loop.js
The tab bar (Primary, History, Help, Extras) above a body of `#loop-sidebar-nav` (History only) and `#loop-main-content`.
- `buildLoopTabs()` writes the tablist once per mount; polls never rebuild it, so a focused tab keeps focus. Keyboard: Left, Right, Home and End switch and focus (automatic activation).
- The Primary tab reads "…" (`data-primary="unknown"`) until the first list lands, then "Create" or "Active". `applyPrimaryLabel()` writes the label only when it differs.
- `renderHistoryList()` lists terminal loops newest first and rewrites only when its fingerprint changes. The active loop is never listed.
- `switchTab("history")` changes only the list pane; the main content stays until a card is chosen.
! **Inert until loaded.** `switchTab()` returns early until `.loop-workspace[data-loaded="1"]`, because `_state` may still hold the previous mount's selection. UI tests wait for that attribute.

### primaryState() / primaryDecision() / applyPrimary() / reconcilePrimary() / landPrimary() / landFromLoops() / retryLanding() / renderActiveConflict() / showPrimaryNotice() — the Primary tab
File: src/gator_command/scripts/dashboard/views/loop.js
The Primary tab is derived from the loop list, never stored: Create when no loop is active, Active (that loop's handoff or workspace) when one is.
- `primaryDecision(ps, display)` is the one rule for what Primary shows:

  | list | keep when | otherwise |
  |---|---|---|
  | none active | mode `create` | `create` |
  | one active (A) | inspecting or handing off A | `inspect(A)` |
  | several | the conflict state with the same ids, or inspecting one of them after choosing it from the conflict list | `conflict(ids)` |

- `applyPrimary()` carries out a non-keep decision: bump `generation`, stop polling unless inspecting, clear `handoffId` / `conflictIds` / `conflictChoice`, record history (`shellPush` for a user action, `shellReplace` for an automatic one), then render.
- `reconcilePrimary()` runs after every list fetch after the landing. A null list changes nothing. Under History it only refreshes the list, so a refresh never moves the Architect out of History. A transition shows a notice: "Loop ‘…’ ended — <Outcome>." with a "View in History" link, or "…is no longer listed."
! **Conflict state is defensive.** Gator allows one active loop. With several, `renderActiveConflict()` lists them and the Dashboard picks none by position. `conflictChoice` is set only by a click in that list, cleared by every other selection, and never persisted.
! **A terminal loop under Primary is a pending reconciliation.** The poll fetches the list and replaces it in the same poll (no empty intermediate panel). If the list failed or still shows it active, the terminal status is patched in place and the timer keeps running until a valid list moves Primary.
! **A failed first list** shows "Loop list unavailable — retrying." and keeps the tabs inert; `pollLoop()` calls `retryLanding()` until a list arrives, and `landFromLoops()` lands exactly once.
! **409 on create** is race recovery only: fetch a fresh list and show the active loop with "Another loop was already active; your form was not submitted." With no active loop or a failed list, the form is kept with a text explanation. Never a disabled form.
- **Pinned by** `test_active_loop_ends_reconciles_primary`, `test_list_failure_keeps_primary_workspace`, `test_initial_list_failure_retries`, `test_active_conflict_state`.

### ensureAuxFrame() / bindExtrasCopyListener() / isGoalCopyRequest() / handleGoalCopy() / replyGoalCopy() — Help and Extras tabs
File: src/gator_command/scripts/dashboard/views/loop.js
Help shows the shipped `gator-loop.html`; Extras shows `gator-loop-extras.html` (per-model notes, with the Codex `/goal` prompt and a copy button).
- `_state.aux` (`null` | `"help"` | `"extras"`) selects them; `_state.view` keeps its `create|history` vocabulary, so neither tab ever enters shell history. Switching works before the first list lands.
- The workspace body and panels are hidden, never removed, so the Create form, a selected loop and the poller survive a visit.
- Frames: `sandbox="allow-scripts"` exactly; live `src` from `/api/welcome/docs/<doc>`, or `srcdoc` from `window.GATOR_WELCOME_DOCS` in a snapshot. No loop data enters them; the Help frame has no messages.
! TRIPWIRE (Extras copy protocol), same rules as Welcome's: a message is accepted only from this mount's connected Extras frame, with `event.origin === "null"`, as a plain object with exactly `{type: "gator-loop", v: 1, action: "copy-codex-goal"}`. Anything else gets no clipboard write and no reply. The reply goes to that source only and carries no secret.
! `CODEX_GOAL_PROMPT` is owned by the Dashboard, never received from a message, and must equal the visible `#codex-goal` text in `gator-loop-extras.html` (pinned by `tests/test_welcome_docs.py`). Its wait uses `--max-seconds 3600`, an Architect-chosen interval; the protocol default stays 360.

### currentSub() / applySub() / selectLoop() / applyDefaultSelection() / views.loop.restore() — History sub-state
File: src/gator_command/scripts/dashboard/views/loop.js
The shell owns history (see `navigate()` in [Dashboard Shell](scripts-dashboard-shell.md)); this view contributes sub-state `{view, mode, loopId}` and registers no global listener.
- A handoff is recorded as inspecting that loop, and the conflict state as mode `create`. The vocabulary is unchanged (`view: create|history`), so the shell's `cleanSub()` and `cleanContextSub()` need no change.
- `selectLoop()` picks the tab matching the loop: terminal → History, otherwise Primary.
! **Primary content is always derived from the current list, never from the record.** Restoring `{view: create}` lands Primary afresh; `{view: history, loopId: L}` inspects L only while L is listed. `restore()` never pushes.
- **Pinned by** `test_loop_back_forward_within_loop`, `test_history_tab_with_active_loop_round_trips`.

### renderCreateWorkspace() / applyPlanSourceFields() / loadRevisePicker() / loadSourcePicker() / loadSourceBrief() / updateCreateEnabled() / briefByteLength() — create form
File: src/gator_command/scripts/dashboard/views/loop.js
Feature name, loop type, source, optional Architect brief, rounds and attention interval, posted to the start endpoint. Client checks are convenience only; the server re-validates everything.
- **Planning sources:** sketch, revision (an approved planning loop plus a revision sketch) or Architect plan (sketch optional). The POST carries exactly the chosen source's fields.
- **Coding:** "Approved planning loop" lists only `mode === "planning" && stage === "plan_approved"`. Selecting one fetches its status for the "Include the approved plan's Architect brief" control; a corrupt brief adds a text warning and is never auto-unchecked.
- **Brief:** counted in UTF-8 bytes (`TextEncoder`), limit 32,768; over the limit disables Create. A blank brief is omitted.
- **Attention interval** posts `attention_interval` (element id `#loop-turn-timeout` kept).
! A source's status response is applied only if it is still the latest request (`_create.sourceRev`) and the select still shows that source. A stale response never updates the control.
! `prefillFeature` writes only into an empty field or one still holding the earlier prefill.

### renderHandoff() / copyPrompt() / renderPromptSection() / recoveryNeed() / applyRecovery() — participant handoff and recovery
File: src/gator_command/scripts/dashboard/views/loop.js
After creation, the handoff shows Draftor and Reviewer prompt-copy cards. Join state polls every 3 s; a Draftor joining does not remove the Reviewer's copy action, and "Open loop workspace" is an explicit click, never automatic. Live loops later show the same prompts under "Participant recovery".
- `copyPrompt()` fetches from the no-store prompt endpoint, writes the clipboard, then nulls the text; with no clipboard it shows a read-only textarea, removed on dismiss.
- `recoveryNeed()` (pure): not joined → "Has not joined yet."; joined and `stale` → reconnect advice; joined and `released` → watcher-exited advice; otherwise "Joined — no action needed".
! A joined role with no watcher (`not_registered`, a `gator loop wait` participant) is never flagged as absent.
! `pollLoop()` bumps `promptEpoch` as soon as it sees a terminal status, before awaiting events, so an in-flight copy cannot write an old prompt.
! `applyRecovery()` changes the disclosure's `open` only when the need set changes, so a manual toggle holds.

### renderSelectedLoop() / buildLoopSkeleton() / patchRegion() / loadSelectedLoop() / pollLoop() / ensurePolling() / setNotice() / setRefreshFailed() / teardownLoopView() — workspace rendering and polling
File: src/gator_command/scripts/dashboard/views/loop.js
Builds a stable skeleton once per selection, then patches regions by fingerprint on each 3 s poll.
- **Region order** (`buildLoopSkeleton()`): header and controls; resolution; source; notices; suspension card; Now line; checkpoint rail beside the timeline; then artifacts, "Candidate evidence" (coding facts), participant recovery, liveness and "Decisions"; the dialog host last. The two disclosures are skeleton-owned, so their `open` state survives polls. Liveness is never inside a closed disclosure, so Re-notify stays reachable.
- **Snapshot:** `_state.render` holds the generation, loop id, root and per-region fingerprints. Any selection, mount or mode change bumps `generation`, which invalidates it.
- **Notice slots:** `#loop-region-notice` has three slots, each with one owner: `refresh` (`pollLoop()` via `setRefreshFailed()`), `action` (Architect action results) and `attention` (`setAttentionNotice()`). No path assigns the whole region, so clearing one never erases another.
- **Poll order:** status, events, then the list. A failed fetch returns without rendering (the last valid workspace, open controls, expanded sections and scroll survive), shows "Refresh failed — retrying.", and keeps the timer. Success in all three clears it.
! **One timer.** `ensurePolling()` is the only place an interval is created. Polling stops at terminal stages, except an approved coding loop, whose resolution can still change.
! **Teardown is installed before the first await.** `window._gatorRepoTeardown = teardownLoopView` is set right after the skeleton, before `await fetchLoops()`, so leaving Loop while the list is in flight bumps `mountId` and no orphan timer starts. Pinned by `test_departed_mount_does_not_resurrect_polling`.
! A stale in-flight response acts only if its snapshot is still current (same generation, loop id and attached root).
- Known limit: a view showing a terminal loop does not poll, so an extension made elsewhere appears after reselecting the loop.

### renderLiveHeader() / renderOutcomeHeader() / counterLineHtml() / nowLine() / renderNowLine() / loopModeInfo() / modeBadge() / renderSourceLine() — header, Now line and mode
File: src/gator_command/scripts/dashboard/views/loop.js
- **Header:** mode and stage badges, the loop name, and "Round X / Y", or for checkpoint loops "Checkpoint K of N · findings round r of b · Generation g". A checkpoint loop never renders "Round X/Y". Terminal loops show the outcome badge and completed date instead, with no controls or prompts.
- **Now line:** `nowLine(status, terminal)` is pure and reads status only (never artifacts, time, liveness or `/snapshot`): active, blocked, paused, approved or terminal, each with its own glyph and text.
- **Source line:** Architect-originated draft (awaiting review, approved, or under revision) or "Revision of <id>", with integrity problems as text.
! `loopModeInfo()` is the only place loop-mode text is decided: `coding` → Coding; no recorded mode → Planning · legacy; `planning` / `planning-only` → Planning; anything else → Unknown mode. It never reads feature names or artifacts.

### renderControls() / openLoopDialog() / loopDialogConfig() / setControlsPending() / closeLoopDialog() / focusAfterDialogInvalidated() / renderContinueControl() / renderBlockedCard() / renderDecisionHistory() / showUnblockNotice() / showExtendNotice() — Architect controls
File: src/gator_command/scripts/dashboard/views/loop.js
Live loops show Interject, Pause and End; paused or blocked loops show Respond (with a pending decision) or Resume, and End; `max_rounds_exceeded` shows Continue; other terminal loops show none. Each button opens one native modal `<dialog>`; only clicks open dialogs, never a poll.
- **Unblock is decision-aware** (`pendingDecision(status)`): with a pending decision the field is "Response to <Role> (required)" and blank is refused; an ordinary pause takes an optional message. Legacy loops only (no `status.attention`) show a "Turn window (s)" input, defaulted from the session and checked against `TURN_TIMEOUT_MIN/MAX`. The Dashboard has no `no_response` control (CLI-only).
- **Continue** posts `{rounds, message}` to `/extend`: rounds 1–20 (`ROUNDS_MIN..ROUNDS_MAX`, mirroring `loop/session.py`), reason required. On success `showExtendNotice()` writes the old and new ceiling and restarts polling.
- **Suspension card:** blocked ("⚑ Blocked — awaiting your decision", with Respond) or paused ("⏸ Architect hold", dashed border). It is built only from fields the loop writes, and a hold never uses escalation wording. The full request text lives in the decision dialog.
- **Decisions:** every `decisions[]` entry with its request and resolution label, including on terminal loops.
- `showUnblockNotice()` says the role resumes when its watcher or wait sees the change; it never claims model work.
! **One request in flight.** The pending action belongs to the selected-loop snapshot, not the dialog. While sending, Cancel and Escape are blocked, the header buttons are disabled, and a new dialog is refused. A failure keeps the dialog and input for retry; a completion is dropped if the generation or snapshot changed.
! **Context change closes the dialog unsent.** When `controlsFingerprint()` changes, an open dialog is closed with "…nothing was sent", and focus moves to the first enabled control or the main heading, never the document body. A dialog already sending is left to report its own result.
! Controls post through `postAction()` with the anti-CSRF header; the server re-validates everything.
! `.loop-dialog` needs `margin: auto` to stay centred, because the global margin reset removes the user-agent centring. Pinned by `test_loop_dialog_is_centred`.

### renderTimeline() / updateTimeline() / timelineGroupKey() / timelineGroups() / eventCardHtml() / eventSummary() / wireTimelineCards() / openArtifactSection() — timeline
File: src/gator_command/scripts/dashboard/views/loop.js
Newest first, grouped by checkpoint (`cp:<id>`) for declared-checkpoint loops, else by round (`r:<n>`); events before the first group are "Start". The scheme is fixed on a snapshot's first render, and an untagged event inherits the group before it, so a pause or escalation stays in its checkpoint. Groups are contiguous runs, so global newest-first order is never broken.
- `updateTimeline()` front-patches strictly new events when the previous newest event is still in place; any other change redraws just the timeline.
- **Executive summaries come from the event, never the artifact.** `eventSummary(ev)` returns text only for an event with `artifact_path` whose `executive_summary` is a string of 1–1,200 code points after whitespace collapse (`Array.from` length, matching the CLI's `len()`; `EXECUTIVE_SUMMARY_MAX` mirrors `submit.EXECUTIVE_SUMMARY_MAX`). Otherwise the card says "Executive summary unavailable for this artifact."
- Participant-submission events show only the role as detail. `FULL_DETAIL_EVENTS` (pause, unblock, escalation, interjection, end) show their full multi-line detail.
! **Timeline cards never fetch.** A card's "View full artifact" link (`href="#"`, keyboard-focusable) scrolls to the artifact and expands it only if collapsed; the artifact then fetches once through its own expand path. Do not reintroduce summary extraction from artifacts (`extractSummary()`, `SUMMARY_RE`, `.loop-event-summary`). Pinned by `test_timeline_card_summary_from_event`.

### renderArtifacts() / collectArtifactPaths() / loadArtifactContent() / renderArtifactBody() / applyArtifactView() / briefEntries() — artifacts
File: src/gator_command/scripts/dashboard/views/loop.js
Artifact sections are derived from event `artifact_path` fields and `status.decisions[]`, so round-zero artifacts are included. Provenance comes first: the plan (`approved-plan.md` / `plan.current.md`), then linked Architect briefs, then the Architect plan or revision baselines. Brief states (required reading, digest mismatch, invalid reference, not carried forward) are text.
- `renderArtifacts()` reconciles sections by `data-artifact`: existing ones keep their expanded state and content. When the event log changes, `MUTABLE_ARTIFACTS` (`plan.current.md`, `findings.current.md`, `implementation.current.md`) refresh in place if expanded, or are marked unloaded if collapsed.
- An expanded body shows Rendered (default) or Raw. The choice is per section, written only by its buttons, survives refreshes and is never stored. Over `MAX_RENDER_CHARS`, or if the formatter fails, Raw is shown with a text reason; the panel is never empty.
! **Collapsed cards carry no excerpt and never fetch.**
! **Fetch ordering.** `loadArtifactContent()` bumps a per-node request revision before each fetch, and applies a result only if it is still the latest for that node (plus the generation and `isConnected` checks). An older response for a mutable artifact cannot overwrite newer text. `fetchArtifact()` uses `cache: "no-store"`.
! `renderArtifactBody()` skips all work when the text equals what is shown. Raw is never reconstructed from rendered nodes. Pinned by `tests/test_dashboard_ui/test_loop_markdown_ui.py`.

### renderResolution() / refreshCoding() / openReopenForm() / renderCodingRegion() / railItems() / renderRail() — coding loops
File: src/gator_command/scripts/dashboard/views/loop.js
Shown only for `status.mode === "coding"`, from the slim `status.coding` projection.
- **Resolution banner** (approved coding loops): `refreshCoding()` fetches the Architect-only `/snapshot` and shows Committed, Pending commit, Stale (with `STALE_REASON_TEXT`, word for word the CLI's `_STALE_REASONS`) or Unknown. Server `guidance` is shown as escaped plain text.
- **Reopen for revision** appears only for Stale or Unknown, with a required reason, and posts `/reopen`. The banner is not repatched while its form is open.
- **Candidate evidence:** the approved plan's source, the base commit, the latest candidate (staged tree, HEAD, changed-path counts), the review verdict, and a note when residue exists outside the loop directory.
- **Checkpoint rail:** filled only for declared-checkpoint loops, from `status.coding.checkpoints` alone (approved ✓, active ●, not started ○). No plan parsing, no request, non-interactive.
! **The resolution state comes from the server alone.** The browser holds no Git-history logic and never parses Git text. Unknown is never treated as approved.
- Coding stages are in `TERMINAL_STAGES` / stage labels; `implementation.current.md` is mutable; checkpoint suffixes "(cpK · gen g)" come from event fields only.

### setAttentionNotice() / refreshLiveness() / applyLiveness() / postRenotify() / openRenotifyForm() — attention and liveness
File: src/gator_command/scripts/dashboard/views/loop.js
The Architect's own view of time and participant presence; participants never see Dashboard time.
- **Attention notice** (attention-mode loops): "◷ Attention: <Role> has been active for at least N min…", written to the `attention` slot only when its derived state changes. When no notice is recorded yet, the text follows only the server's `attention.host`: no host running, host attached (pending), or neutral. Host absence is never inferred from a missing marker.
- **Liveness panel:** `refreshLiveness()` fetches `/liveness` (no-store) after each render and drops stale results. States: ● Connected, ◐ Stale (bold, underlined), ◇ Released, ■ Closed, ○ Not registered; while suspended, "Connected — waiting through the hold". Times are absolute, never "Ns ago". Degraded modes (403/404, unavailable, corrupt) are text; `retry` keeps the last good view.
- **Re-notify:** a button only when `renotify_eligible`. Its inline reason form survives polls; the result goes to the `action` slot and never claims work was done.
! The footnote is fixed: "Acknowledged means received — not that the model read, worked on, or will submit anything."

## Before Changing This Module

- Confirm the backend wire schema and empty/error states.
- Keep every view-wide rule above: zero writes on unchanged polls, failures never shown as empty, no markup from participant or artifact text, no stored prompts, no time display, never colour alone.
- Exercise keyboard/mouse navigation and narrow/wide layouts.
- Run `tests/test_dashboard_ui/test_loop_workspace.py`, `test_loop_coding_ui.py` and `test_loop_markdown_ui.py`.
- Keep the UI dependency-free unless the product architecture explicitly changes.

## Connections

-> [Dashboard Server](scripts-dashboard.md) - APIs, security, and content policy
-> [Dashboard Shell](scripts-dashboard-shell.md) -- navigation, workspace tabs and styling the Loop workspace relies on
-> [Dashboard Views](scripts-dashboard-views.md) -- sibling views; Welcome's copy protocol is the model for the Extras copy action
-> [Loop Commands](scripts-loop-commands.md) -- the CLI rules the browser mirrors (`_STALE_REASONS`, `EXECUTIVE_SUMMARY_MAX`)
-> [Loop State](scripts-loop-state.md) -- stage vocabulary, round and turn-window bounds the create form and controls mirror
