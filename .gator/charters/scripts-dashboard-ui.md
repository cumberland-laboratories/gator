# Charter: Dashboard Browser UI

**Covers**: `src/gator_command/scripts/dashboard/dashboard.html`, `src/gator_command/scripts/dashboard/dashboard.css`, `src/gator_command/scripts/dashboard/dashboard.js`, `src/gator_command/scripts/dashboard/views/**`, `src/gator_command/scripts/dashboard/*.png` (including `views/loop-markdown.js`, #45)

## Owns

- The framework-free dashboard shell, navigation, responsive layout, and browser-side routing.
- Fleet, history, repo, audit, loop, updates, and settings views.
- Document browsing, syntax highlighting, cross-document search, and sandboxed HTML preview controls.
- Browser requests to the local dashboard server.

## Does Not Own

- Route authorization, path containment, filesystem access, or data computation; see [`scripts-dashboard.md`](scripts-dashboard.md).
- Governance business rules.
- Cumberland document-template styling; see [`contracts.md`](contracts.md).

---

### navigate() / renderCurrentView()
File: src/gator_command/scripts/dashboard/dashboard.js
Own browser history, selected repository/view state, and dispatch into view modules.
<- sidebar, topbar, URL changes
-> `views/*`
! URL state and visible selection stay synchronized; refresh re-renders the same repo/view rather than silently returning home.

### apiFetch() / mutation requests
File: src/gator_command/scripts/dashboard/dashboard.js
Call same-origin dashboard APIs and normalize errors for views.
<- all view modules
-> Dashboard server
! Every POST includes `X-Gator-Dashboard: 1`. Never add cross-origin fallback behavior.

### renderFleet() / fleet actions
File: src/gator_command/scripts/dashboard/views/fleet.js
Render repository health and expose explicit per-repository actions via a three-dot overflow menu.
<- fleet route
-> repo update/gatorize endpoints, `POST /api/repos/remove`
! The overflow menu carries dual identity: `data-repo-name` for name-addressed Update/Gatorize, `data-repo-path` for path-addressed Remove. Each action dispatches to the correct identity.
! Actions use the repository's stable key, not display text or array position.
! Missing repositories remain representable so users can understand and clean stale registry entries.

### openRemoveConfirmDialog() / remove handler
File: src/gator_command/scripts/dashboard/views/fleet.js
Confirmation dialog for removing a repo from the dashboard registry. Reuses the `.gator-modal` pattern.
<- overflow menu Remove action
-> `POST /api/repos/remove` (path-addressed)
! Registry-only operation — no filesystem access. Dialog text makes this explicit.
! Posts the registered path, not the display name.

### renderHistory()
File: src/gator_command/scripts/dashboard/views/history.js
Render Git-native commit history and Gator trailer attribution.
<- history route
-> repo history endpoint
! Accept both current Architect and legacy PI attribution supplied by the backend.

### renderRepo() / loadFileList() / loadFile()
File: src/gator_command/scripts/dashboard/views/repo.js
Render the repository knowledge browser, fetch canonical listings, and display supported content.
<- repo route and sidebar clicks
-> list/file/raw/search endpoints
! Encode file paths per segment so separators retain namespace meaning.
! Render untrusted text as text or through the syntax renderer; do not interpolate repository content into executable markup.

### buildRawUrl() / bindHtmlPreviewControls()
File: src/gator_command/scripts/dashboard/views/repo.js
Build version-aware raw URLs and wire Copy path, Refresh, and Open externally controls for HTML documents.
<- `loadFile()` HTML branch
-> sandboxed iframe and raw endpoint
! The iframe sandbox is exactly `allow-scripts`; do not add `allow-same-origin`, forms, popups, or top navigation.
! Refresh reissues the request while preserving the selected historical version. External open uses `noopener`.

### renderContentFor() / gatorHighlight()
File: src/gator_command/scripts/dashboard/views/repo.js
File: src/gator_command/scripts/dashboard/views/syntax.js
Select safe Markdown/JSON/code rendering and lightweight syntax highlighting.
<- `loadFile()`
! Highlighting is presentation only and must not reinterpret file bytes as HTML capabilities.

### renderArtifactBody(section, content, text) / buildArtifactViewBar() / applyArtifactView() (#45)
File: src/gator_command/scripts/dashboard/views/loop.js
The expanded artifact body. `loadArtifactContent()` calls it after its generation, `isConnected` and `_gatorContentRev` guards, so a stale response is dropped **before** any parse.
- **Equality skip:** if `text === content._gatorText` and the body is loaded, it returns with **no reparse and no DOM writes**. Writing "Loading…" over the panes resets `_gatorText`, so a re-expand never equality-skips onto it.
- **Changed text:** it builds the Raw pane (`pre.loop-artifact-pre`, `textContent = text`) and the Rendered pane (`div.loop-md` from `GatorLoopMarkdown.render`, in `try/catch`). It reuses the view bar, sets `_gatorText` and `dataset.loaded`, then calls `applyArtifactView`.
- **View bar:** `div.loop-artifact-viewbar[role=group][aria-label="Artifact view"]` holds native **Rendered** / **Raw** buttons (`aria-pressed`) and an `aria-live` caption naming the state in text. The pressed button is bold, underlined and has a 2px border, so state is never colour-only. Keyboard use is native: Tab, then Enter/Space.
- **View choice:** `section.dataset.view` (`rendered` default / `raw`) is written **only by the buttons**. It survives refreshes and collapse/expand, resets with the skeleton, and is never stored in `localStorage`. Switching toggles `hidden` / `aria-pressed` only, with no refetch and no reparse. `applyArtifactView` writes only values that differ.
- **Fallbacks:** over `MAX_RENDER_CHARS` (200,000) the caption reads "Too large to render (N characters); showing raw text". If the formatter is missing or throws, it reads "Could not render Markdown; showing raw text". In both cases Raw is shown and Rendered disabled, but the section's chosen view is **not** overwritten. The panel is never empty.
- **Height:** `.loop-artifact-content` has `max-height: 70vh` (scrollable): the full document is read in place, with no extra pane.
- **Pinned by:** `tests/test_dashboard_ui/test_loop_markdown_ui.py` (M3).
  - The tests check: no excerpt and no fetch when collapsed; the full document Rendered by default; Raw identical to what was served; keyboard switching with no refetch; 0 mutations and 0 renders on unchanged polls and on an unchanged refetch; a changed refresh updating both panes and keeping Raw; a stale response unable to reset text or view; and the large and failure fallbacks.
  - **Mutation-checked:** Raw via `innerHTML`, no equality skip, no revision guard, a collapsed fetch restored, and the view reset on render all fail it.

### GatorLoopMarkdown.render(text) / safeHref(url) (#45)
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

### renderAudit() / showSessionModal()
File: src/gator_command/scripts/dashboard/views/audit.js
Render session evidence and request source-qualified drill-down content.
<- audit/repo session panels
-> audit/session endpoints
! Preserve `source_kind` and repository identity through drill-down; never fetch a same-named file from a different source.

### renderUpdates()
File: src/gator_command/scripts/dashboard/views/updates.js
Render installed/latest version state and request an explicit upgrade.
<- updates route
-> check and upgrade endpoints
! Checking and upgrading are visibly separate actions; failure output remains visible after restart attempts.

### Loop workspace — renderLoopSidebar() / renderCreateWorkspace() / renderHandoff() / renderSelectedLoop() / buildLoopSkeleton() / patchRegion() / renderOutcomeHeader() / renderBlockedCard() / renderPromptSection() / renderControls() / renderContinueControl() / showExtendNotice() / ensurePolling() / updateTimeline() / renderTimeline() / renderArtifacts() / fetchLiveness() / postRenotify() / refreshLiveness() / applyLiveness() / openRenotifyForm() / fetchCodingSnapshot() / patchCodingRegion() / renderCodingRegion() / openReopenForm() / refreshCoding()
File: src/gator_command/scripts/dashboard/views/loop.js
Render the governed planning loop workspace with a three-section secondary sidebar (Create Loop, Active, History) and mode-driven main content (creation workspace, participant handoff, or selected-loop inspection).
<- loop route
-> loop list/status/events/artifact endpoints, control endpoints (pause/interject/unblock/end/extend), start endpoint, prompt endpoint, sketch-sources endpoint (`/api/repo-by-key/<repo_key>/...`)
! **Mode state**: `_state.mode` ("create" | "handoff" | "inspect") drives which main content renderer is called. `_state.handoffId` tracks the loop during participant handoff.
! **Secondary sidebar**: `renderLoopSidebar()` classifies loops into active (non-terminal, at most 1) and history (terminal, newest-first). Create Loop button is non-actionable when an active loop exists (shows "Open active loop" link). Selection sets mode to "inspect".
! **Creation workspace**: `renderCreateWorkspace()` renders feature name, sketch source picker (dropdown from `/sketch-sources` + manual path toggle), advanced settings disclosure (max rounds 1–20, turn timeout 30–3600s), and Create button calling existing start endpoint. Client-side validation before POST. 409 "active loop exists" is race-recovery only (shows "Open active loop").
! **Participant handoff**: `renderHandoff()` shows prompt-copy cards for Draftor and Reviewer roles. `copyPrompt()` fetches from the no-store prompt endpoint, writes to clipboard, then nulls the prompt variable. Clipboard unavailable: shows read-only textarea fallback, removed on dismiss. Join state polls at 3s interval; Draftor joining does NOT remove Reviewer copy action. "Open loop workspace" navigates to inspect mode explicitly — never auto-navigates on join.
! **Token non-persistence**: prompt text never stored in localStorage, sessionStorage, URL state, data- attributes, or console logs. JS variable nulled after clipboard write. DOM elements removed on navigation.
! **Live vs history**: `renderSelectedLoop()` orchestrates live or read-only workspace. Live loops show status header, suspension card (#53, below), decision history, prompt copy section, controls, timeline, artifacts. Terminal loops show outcome header with badge (Approved/Max Rounds/Timed Out/Ended), completed date, no controls, no prompts.
! **Event-driven artifact enumeration**: `collectArtifactPaths()` derives immutable artifacts from event `artifact_path` fields and `status.decisions[]`, replacing the prior numeric round loop. Naturally includes round-zero artifacts. Deduplicates by path.
! Polls every 3s for non-terminal loops; stops on terminal state. `pollLoop()` increments `promptEpoch` immediately after terminal status is identified, before awaiting events — this closes the race window where an in-flight `copyPrompt()` could resolve during the events fetch and write to the clipboard with the old epoch. Teardown clears interval via `window._gatorRepoTeardown`.
! **TRIPWIRE (#45):** expanded artifact text reaches the DOM only through `GatorLoopMarkdown` DOM construction (Rendered) and `pre.loop-artifact-pre.textContent` (Raw), both from the **same fetched string**. Raw is never reconstructed from rendered nodes, and artifact text never goes through `innerHTML`. This replaces the earlier "escaped through `escHtml()` and rendered in `<pre>`" rule.
! **Planning sources (#51).**
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
! **Suspension card (#53)** — `#loop-region-blocked`, `renderBlockedCard()`. It is built ONLY from fields the loop writes: `stage`, `resume_stage` / `resume_next_role`, `suspended_at`, `pause_reason`, and the pending decision's `request` (`reason`, `role`, `ts`, `artifact_path`). The fictitious `status.escalation_reason` that hid the old card is gone.
  - **Blocked** (`.loop-decision-card`, `data-kind="architect_decision"`): "⚑ Blocked — awaiting your decision", then `decision-N · requested by <Role> · <time>`, the full reason (`.loop-blocked-reason`, `white-space: pre-wrap`), the "View decision request" link, and `Resumes: <Role> · <stage>`.
  - **Paused** (`.loop-hold-card`, `data-kind="architect_hold"`): "⏸ Architect hold (paused)", "No participant response is required.", `Preserved:`, `Since:` and the pause reason. It never uses escalation wording.
  - **Telling them apart:** title text, glyph and border style (dashed for a hold), never colour alone.
  - **Fingerprint:** `blockedFingerprint` covers every field read, so unchanged polls are mutation-free (pinned).
! **Decision history (#53)** — `#loop-region-decisions`, `renderDecisionHistory()`, fingerprint `decisionsFingerprint` (ids + response kind/ts). It lists every `decisions[]` entry, including on terminal loops: the request (role, time, reason, "View request") and the resolution.
  - Resolution labels come from `RESPONSE_KIND_LABELS`, including "Cancelled — loop ended" for `cancelled_by_end`; an unknown kind shows "Resolved".
  - Each label carries a glyph: ✓ resolved, ○ pending (bold).
  - Text goes through `escHtml()` with pre-wrap. Artifact links reuse `wireArtifactJump()`.
! **Full-detail timeline events (#53)**: `FULL_DETAIL_EVENTS` (`loop_paused`, `loop_unblocked`, `escalated`, `architect_interjection`, `loop_ended_by_architect`) render their detail with `.loop-event-detail-full` (`pre-wrap`, no ellipsis), so a multi-line pause reason or unblock response stays readable after the hold ends. Other events keep the single-line ellipsis (pinned).
! **Unblock notice (#53)** — `showUnblockNotice()` writes the `action` slot after a successful unblock: "Unblocked. <Role> resumes at <stage> when its watcher or wait sees the change. The Dashboard does not run model work." It never claims model work.
! Architect controls are contextual: active loops show Pause/Interject/End; paused/blocked loops show Unblock/End; terminal loops show no controls. Each button opens an inline input area; Interject requires non-empty message. Controls POST via `postAction()` with anti-CSRF header and re-poll on success. Non-2xx control responses render a `.loop-ctrl-error` message and preserve the input area for retry.
! Unblock is decision-aware via `pendingDecision(status)`: with a pending decision (escalation) the field is labelled **Response to participant (required)**, Confirm stays disabled until non-blank, and blank input is refused before any request (text error + thicker border, not color alone); an ordinary Architect pause keeps **Message (optional)**. **Legacy loops only** (no `status.attention`): Unblock also shows a **Turn window (s)** number input defaulted to the session's `status.turn_timeout_seconds` (not a hard-coded 300), client-checked against `TURN_TIMEOUT_MIN/MAX` (mirrors `loop/session.py`), and sent as `timeout` only when changed. Attention-mode loops (#47) never show the field and never post `timeout` (`legacyWindow = !status.attention`). The Dashboard exposes no deliberate-empty (`no_response`) control — that exceptional path is CLI-only (`--no-response`). The server re-validates everything.
! **Incremental rendering (#38)**: `renderSelectedLoop()` builds a stable skeleton once per selection (`buildLoopSkeleton()` — regions `#loop-region-header`, `#loop-region-blocked`, `#loop-region-prompts`, `#loop-region-notice` (unpatched; named slots `refresh`, `action` and `attention` (#47), see below), `#loop-region-liveness` (#36, field-patched — see below), `#loop-region-coding` (#41, see below), `#loop-controls`, `#loop-timeline`, `#loop-artifacts`) and records `_state.render` = {generation, loopId, root, per-region fingerprints, timeline cursor}. The snapshot is invalid (skeleton rebuilt) when `_state.generation` or `selectedLoopId` changes or the root is detached; `teardownLoopView()` and a null status clear it. Every selection/mount/mode transition bumps `generation`, so no stale snapshot survives.
! Per poll, `patchRegion()` rewrites a region only when its fingerprint changes: `headerFingerprint()` (stage, round, next role, blocked, `last_updated`, legacy deadline, #47 `turn_started_at` and attention interval, joins, identity), `blockedFingerprint()` (escalation + pending decision), prompts (live vs terminal), `controlsFingerprint()` (only renderControls() inputs: terminal, paused, pending decision id, turn window, `!!status.attention`), `artifactsFingerprint()` (event count + last event key + decision artifacts). An unchanged poll performs no main-panel DOM writes except `updateTimeRemaining()`, a text-only patch of the legacy countdown (`.loop-time-remaining`) or the attention-mode elapsed time (`.loop-elapsed`, #47), written only when its text differs. `setAttentionNotice()` writes only when its derived state changes. Fingerprints use returned data, never wall-clock time.
! **#53 multiline input:** the shared control input is `<textarea id="loop-ctrl-message" class="loop-ctrl-input" rows="4">` with `<label for>` association and an `aria-label` fallback. The required unblock label names the escalating role ("Response to Reviewer (required)"; "participant" when unknown). A typed draft survives unchanged polls with zero mutations in the controls, suspension and decision regions (pinned).
! Because controls are untouched unless their inputs change, an open control input (message / required response) survives polling without any "skip while composing" rule; if the control context really changes (e.g. unblocked elsewhere) the controls are rebuilt, which is correct.
! Timeline: `updateTimeline()` appends only strictly-new cards (`eventCardHtml()` + `wireTimelineCards()`) when the previously rendered last event (`eventKey()`: ts|event|round) is still at the same index; otherwise it redraws just `#loop-timeline`. Unchanged polls make no timeline writes.
! Artifacts: `renderArtifacts(status, events, root, refreshMutable)` reconciles sections by `data-artifact` — existing nodes keep expanded state and loaded content and are only re-ordered; new ones come from `createArtifactSection()`; missing ones are removed. On event-log change (`refreshMutable`), `MUTABLE_ARTIFACTS` (`plan.current.md`, `findings.current.md`, `implementation.current.md`): loaded content refreshes in place if expanded, or is marked unloaded if collapsed. **#45:** collapsed artifact cards carry **no excerpt and never fetch**; `loadArtifactSummary()`, `isSummaryArtifact()` and the `.loop-artifact-summary` node were removed. `fetchArtifact()` uses `cache: "no-store"` so refreshes are real.
! Artifact fetch ordering: `loadArtifactContent()` bumps a per-node request revision (`nextRequestRev()` → `content._gatorContentRev`) before each fetch and apply a completion only if it is still the latest for that node (in addition to the generation and `isConnected` checks). An older in-flight response for a mutable artifact therefore cannot overwrite newer content. A refresh of a collapsed mutable section also bumps the content revision so an in-flight body fetch cannot mark it loaded with stale text; an expanded section (loaded or still loading) is always refetched.
! Terminal transition patches header/prompts/controls in place (never an empty intermediate panel), then polling stops.
! **Terminal is not always final (#39).** For `max_rounds_exceeded` (`EXTENDABLE_STAGE`) `renderControls()` delegates to `renderContinueControl()`: a **Continue loop** button opening **Additional rounds** (number, `ROUNDS_MIN..ROUNDS_MAX` = 1..20, mirrors `loop/session.py`, default 2) and **Reason (required)**. Confirm stays disabled until the reason is non-blank; invalid rounds or a blank reason are refused before any request with a text error (not colour alone). It POSTs `{rounds, message}` to `/extend` via `postAction()`. Every other terminal stage renders no controls. `controlsFingerprint()` includes the extendable-stage flag so this control is (re)built only when that input changes.
! On extend success: `showExtendNotice()` writes to `#loop-region-notice` — a skeleton region that incremental rendering never patches, so the notice survives the terminal-to-live transition (cleared only by a skeleton rebuild on selection change). It states old → new ceiling and the participant re-engagement step, plus a **Warning:** line when `watcher === "failed"` (timeouts not enforced) or a neutral line for `already_hosted`. Then `ensurePolling()` restarts the interval (polling had stopped at terminal) and sets `data-polling="1"`, `refreshSidebarOnly()` moves the loop to Active, and `loadSelectedLoop()` patches header/prompts/controls live while timeline and artifacts are preserved; the timeline appends the `loop_extended` card (`EVENT_LABELS.loop_extended = "Extended"`).
! **Architect brief (#43)**
  - **Create form.** An optional "Architect brief (optional, Markdown)" textarea with a **UTF-8 byte** counter: `briefByteLength()` uses `new TextEncoder()`, labeled "N / 32,768 bytes", never string length. Over the limit the counter adds "over the limit…" (bold and underlined), Create is disabled, and the submit path refuses too. A blank brief is omitted from the POST; the server stays authoritative.
  - **Artifact inspector.** `briefEntries(status)` reads only the strict status projection. A position is listed when its check is not `absent`, and LINKED only when its positionally bound view is non-null. The artifact name is always the fixed constant for that position, never metadata. Linked briefs sort first, labeled "Architect brief" / "Architect brief (this coding loop)" / "Architect brief — from approved plan", with "(required reading)" when ok or "[!! DIGEST MISMATCH]" (and the other states) as text.
  - **Text-only notes.** Invalid references ("…: INVALID REFERENCE — escalate to the Architect") and a dropped planning brief ("Planning brief: not carried forward (Architect's choice at coding start)") are notes in `.loop-brief-notes`, with no link and no fetch.
  - **Change detection.** Labels and notes are written only when they differ, and `artifactsFingerprint` includes the brief metadata, checks and decision, so identical polls produce zero mutations (pinned).
! **Coding-loop creation (#43 M2a):** the create form has a **Loop type** radio: "Planning — draft a plan from a sketch" or "Coding — implement an approved plan".
  - **Coding mode** hides the sketch field and shows "Approved planning loop", a select filled from `/loops` filtered to `mode === "planning" && stage === "plan_approved"`. With none, it shows "No approved planning loops to implement" and Create is disabled.
  - **Source brief state.** Selecting a source fetches that loop's `/status` (`loadSourceBrief`) behind two independent stale guards: a per-select `_create.sourceRev` revision, and a check that the select still shows that source. A stale response can never update the control (pinned; the test fails only when both guards are removed). While pending, the form says "Checking the approved plan's brief…" and Create is disabled.
  - **The keep/drop control** ("Include the approved plan's Architect brief", checked by default) is shown for every non-`absent` `brief_check`. Corrupt states add a text warning: "…failed its integrity check (DIGEST MISMATCH). Keeping it will fail; uncheck to start without it."; it is never auto-unchecked. A failed fetch shows "Brief state unknown"; the server decides. `absent` hides it, and `source_brief` is omitted.
  - **The POST** carries `mode`, `from_loop`, `source_brief` (`keep` / `drop` when shown) and the optional `brief`, never `sketch_path`. The server's honest error (for example, keep on a corrupt brief) appears in `#loop-create-error`.
  - **`updateCreateEnabled()`** combines the byte limit, no sources and pending source state.
! **Architect attention (#47 M5):** this is the Architect's own view; participants never see Dashboard time.
  - **Header:** for loops whose `/status` carries `attention`, the countdown is replaced by **"Elapsed this turn"** (`.loop-elapsed`, "7m 12s · attention after 5 min", from `attention.turn_started_at`). `updateTimeRemaining()` text-patches both `.loop-elapsed` and the legacy `.loop-time-remaining`; it is the only permitted per-poll write, and a region is never rebuilt for it. The header fingerprint adds `turn_started_at` and the interval. Legacy loops keep the "Time Remaining" countdown.
  - **Notice:** `#loop-region-notice` gains a third slot, `attention`, owned only by `setAttentionNotice()`. It derives a state (`notified|<turn>`, `unrecorded|<turn>` when `due && !notified`, or empty) and writes the slot and the selected sidebar card's marker **only when that state changes**, so identical polls are mutation-free.
    - Notified text: "◷ Attention: Draftor has been active for at least 5 min in revision. The loop is still running — interject, pause, or end if needed; no action is required."
    - Unrecorded text (P2) follows **only** the server's authoritative `attention.host`:
      - `none`: "…no notice recorded — no loop host is running for this loop, so attention notices are not being recorded.";
      - `attached`: "…notice pending — the loop host records it on its next check.";
      - `unknown` or missing: neutral, "…no notice has been recorded for this turn yet."

      Host absence is never inferred from a missing marker. The state key includes the host value, so a host change rewrites the notice.
    - It uses `role="status"` and `.loop-attention-notice` (dashed border, glyph and bold label, never an error colour). It never touches the `refresh` / `action` slots or open controls, and clears when the turn changes or the loop pauses or ends.
  - **Sidebar:** `.loop-card-attention` shows "◷ attention". The initial render comes from the `/loops` item's `attention_notified` (a marker-only check on the server). It is then kept live for the selected loop by `setAttentionNotice` (the sidebar is not re-fetched on polls).
  - **Unblock control:** `legacyWindow = !status.attention`. Attention loops never show the "Turn window (s)" field and never post `timeout`. The controls fingerprint includes `!!status.attention`.
  - **Create form:** the field is labelled "Architect attention interval (seconds)" with the hint "Architect notice only — participants never see it…", and posts `attention_interval`. The element id `#loop-turn-timeout` is kept.
! **Coding candidate panel (#41)**: `#loop-region-coding`, shown only when `status.mode === "coding"` (it uses the slim `status.coding` projection).
  - **Facts:** the approved plan's source loop and sha, the base commit, and the latest candidate (round, staged tree / HEAD / branch or detached, changed-path counts by status), plus the review verdict with a "candidate had changed" note.
  - **Residue:** a "Note:" line when residue outside the loop directory is non-zero. Loop residue is never warned about.
  - **Live resolution (`implementation_approved` only):** `refreshCoding()` fetches the Architect-only `/snapshot` (no-store) and renders one banner. Each state is text plus a distinct glyph plus weight or style (`data-state`), never hue alone:
    - ✓ Committed (commit),
    - ● Pending commit — one normal commit,
    - ⚠ Stale (reason text),
    - ? Unknown — never treat as approved.
  - **Reopen:** a **Reopen for revision** button appears only for Stale or Unknown. It opens an inline required-reason form, Reopen stays disabled while the reason is blank, and it POSTs `/reopen` `{message}` with `X-Gator-Dashboard`. The notice reports invalidation and the watcher state.
  - **Patching:** the region is rewritten only when `codingFingerprint()` (stage, round, `max_rounds`, coding projection, resolution state, reason, commit) changes, and never while the Reopen form is open (`data-reopen-open`). Identical polls produce zero mutations (pinned).
  - **#55 checkpoints** apply when `status.coding.checkpoints` is present, which is declared loops only.
    - **Counters.** `checkpointCounters(status)` builds them from the projection plus `status.max_rounds`.
      - The **live header** replaces "Round X / Y" with a "Checkpoint" item ("Checkpoint K of N · findings round r of b", `.loop-checkpoint-counter`) and a separate "Generation" item (`.loop-generation-counter`, "none yet" before the first submission).
      - The **outcome header** and the handoff subtitle do the same.
      - **Sidebar cards**, active and history (`renderSidebarCard` via `sidebarCounterText`), show "Checkpoint K/N · findings r/b · gen g" from the `/loops` `checkpoint_summary`.
      - Every other card and header keeps "Round X/Y". **A checkpoint loop never renders `Round X/Y`** (pinned, with `status.round` 3 > budget 2).
    - **Coding region:**
      - Checkpoint and Generation rows; the candidate row reads "Candidate (cpK · gen g)".
      - An ordered `.loop-checkpoint-list` with one item per checkpoint: ✓ approved (tree …), ● active (weight 600), ○ not started. Each item is glyph + text + weight with `data-state`, never colour alone.
    - **Labels.** `EVENT_LABELS.checkpoint_approved = "Checkpoint approved"`. Timeline cards and artifact toggles add "(cpK · gen g)" from event fields only (`checkpointSuffix` / `artifactSuffixes`), never by parsing artifacts.
    - **Fingerprints.** `headerFingerprint` includes `checkpointCounters`, `artifactsFingerprint` includes `artifactSuffixes(events)`, and `codingFingerprint` includes `max_rounds`. Identical polls leave the coding region and the counter nodes untouched (pinned).
  - **Coding loops elsewhere in the view:**
    - stage labels and badges cover `implementation_drafting` / `implementation_review` / `implementation_revision` / `implementation_approved`, and `implementation_approved` is in `TERMINAL_STAGES`;
    - the artifact inspector lists `approved-plan.md`, `implementation.current.md` and `findings.current.md` first (no sketch or plan), `implementation.current.md` is mutable, and the `implementation.*` / `approved-plan.md` artifacts show summaries;
    - the event labels add `implementation_submitted`, `implementation_approved` and `loop_reopened`.
! **Refresh-failure visibility and notice ownership (#44):**
  - **Three named slots.** `#loop-region-notice` holds `[data-slot="refresh"]`, `[data-slot="action"]` and (#47) `[data-slot="attention"]`. `noticeSlot()` / `setNotice()` write exactly one slot.
    - **Action:** Architect action results only — `showExtendNotice()` (Continue), `showLivenessNotice()` (Re-notify), and the Reopen notice.
    - **Refresh:** owned solely by `pollLoop()` through `setRefreshFailed()`.
    - **Attention (#47):** owned solely by `setAttentionNotice()`, for attention-mode loops; it is empty for legacy loops.

    No path assigns the whole region's `innerHTML`, so clearing the refresh or attention notice can never erase an Architect message.
  - **On a failed poll** (`fetchStatus()` gives null, or `fetchEvents()` gives **null**):
    - `pollLoop()` returns without rendering, so the last valid workspace, artifacts, open controls, expanded sections and scroll all survive, and polling continues on the same single timer;
    - it shows the text-led "Refresh failed — retrying." notice (`role="status"`).
  - **On recovery:** the next successful full status-plus-events refresh clears only that notice. `setRefreshFailed()` writes only when the state changes, so repeated failures and successes are mutation-free.
  - **Stale guard:** it acts only if the snapshot is still `_state.render` for the same generation and `selectedLoopId`, with an attached root. A stale in-flight response can't set or clear a notice on a newer selection.
  - **Initial-load failure keeps its behavior:** the notice is shown only after a valid render of this selection, and `loadSelectedLoop()` still renders a failed events fetch as `[]`.
  - **`fetchEvents()` returns null on failure** (HTTP error, network, or a non-array body) and `[]` only for genuinely no events. A failure must never render as an empty history, which would prune event-derived artifact sections (the pre-fix behavior).
! **Polling ownership (#41, fixes #44's core):**
  - `ensurePolling()` is the ONLY place an interval is created, at mount and on selection alike; a second, leaked interval would survive clearing at terminal stages.
  - `loadSelectedLoop()` calls it whenever the selected loop is non-terminal, so selecting a live loop after a terminal one resumes polling without re-navigating.
  - An approved coding loop stays polled (its resolution can move from Pending to Committed or Stale with no loop-state change). `pollLoop()` stops the timer only for other terminal stages.
! **Participant liveness panel (#36)** — `#loop-region-liveness`, Architect loop view only. #53: while the loop is paused or blocked (`snap.suspended`, set by `renderSelectedLoop`), a connected role reads "● Connected — waiting through the hold".
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
  - **Fixed footnote.** "Acknowledged means received — not that the model read, worked on, or will submit anything." It names Claude Code background tasks (open session) per the M0 spike, and says other participants use `gator loop wait`.
! Known limit: a view already showing a terminal loop does not poll, so an extension made elsewhere (CLI) appears after reselecting the loop.
! **Timeline cards are link-only** (2026-10-04 follow-on to #45):
  - **Synchronous link.** `eventCardHtml()` renders the event metadata (time, label, escaped detail) and, for an event with an `artifact_path`, a link built from that metadata: `<a class="loop-timeline-artifact-link" href="#" data-artifact="…">View full artifact</a>` (`escHtml()`; `href="#"` makes it keyboard-focusable). The link never depends on an Executive Summary heading or on a fetch.
  - **Click binding only.** `wireTimelineCards()` only binds clicks: it **never fetches artifact text**.
  - **Following a link.** `openArtifactSection(parentEl, name)` (with a `CSS.escape`'d selector) scrolls to the matching artifact card and clicks its toggle **only if it is collapsed**. An open card stays open. The artifact is then fetched once, by the card's own #45 expand path, and opens Rendered by default with Raw as a toggle.
  - **Removed:** `extractSummary()`, `SUMMARY_MAX_CHARS` / `SUMMARY_RE`, `window.GatorViews._extractSummary`, the `.loop-event-summary` / `.loop-timeline-summary-*` nodes and styles, and the "No executive summary supplied" fallback. The `## Executive Summary` artifact requirement is unchanged: it remains part of the full rendered document.
  - **Pinned by** `tests/test_dashboard_ui/test_loop_workspace.py`: link-only cards (exactly one link, `href="#"`, no excerpt, no `_extractSummary`); no link on an event without an artifact; a link without an Executive Summary; **zero `/artifact/` requests** on initial render and on appended events until a link is followed, then exactly one; an open section stays open with no refetch; keyboard Enter activation; and the existing navigation and round-zero link tests. Mutation-checked: a restored timeline fetch, an unconditional toggle, a missing link, and a missing `href` each fail it.

### renderSettings()
File: src/gator_command/scripts/dashboard/views/settings.js
Render and update machine-local dashboard preferences exposed by the server.
<- settings route
! Client validation improves feedback but does not replace server-side shape validation.

### responsive shell
File: src/gator_command/scripts/dashboard/dashboard.css
Maintain the sidebar/topbar/content flex chain and usable narrow-screen layout.
<- all views
! Repository content and iframe containers need `min-width: 0`; HTML preview retains a visible minimum height and scrollable overflow.

## Before Changing This Module

- Confirm the backend wire schema and empty/error states.
- Exercise keyboard/mouse navigation and narrow/wide layouts.
- Run Playwright tests for mutations, file browsing, CSP liveness, iframe isolation, and preview controls.
- Keep the UI dependency-free unless the product architecture explicitly changes.

## Connections

-> [Dashboard Server](scripts-dashboard.md) - APIs, security, and content policy
-> [Session Archaeology](scripts-session-archaeology.md) - evidence identity and provenance
-> [Contracts](contracts.md) - Cumberland HTML compatibility
