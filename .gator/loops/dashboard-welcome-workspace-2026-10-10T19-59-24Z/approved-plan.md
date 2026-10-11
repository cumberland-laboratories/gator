# Implementation Plan: Dashboard Welcome Workspace (#72)

## Executive Summary

- **What:** Make the sidebar Gator logo a real "Open Welcome" button that opens a new client-only `welcome` view. The view has four topics (What is Gator? · What Gator can do · Gatorize a repo · Start a session with Gator) in a full-width tab bar at the top of the main pane. It also has one **Copy session-opening prompt** control with the exact vendor-neutral text from the sketch.
- **Key decision:** Add one shared main-pane tab-bar style (`.gator-tabbar` / `.gator-tab`). Move Loop's existing Create / History tablist into that bar above the Loop workspace. The two list panels stay in the Loop sidebar as the `tabpanel`s. Loop's `_state.view`, `switchTab()`, `applyTabState()`, keyboard handling and shell sub-state keep their meaning; only where the tablist is built changes.
- **Main risk:** Moving the tablist could break the "polls keep the tablist and focus" behaviour or Back/Forward restoration. The tablist is still built once per mount and never touched by polls, and the existing #56 tests pin both.
- **Verification:** Two coding checkpoints, each with focused Playwright tests. A new `test_welcome_ui.py` covers routing, ARIA/keyboard, copy success and fallback, narrow width, history state and no repository mutation. Loop tests are updated for the new tablist location. `test_snapshot.py` gets the new script. The full Dashboard UI suite runs once at final approval.

## Summary

The plan adds a `welcome` view to the shell and a new `views/welcome.js` module that owns fixed topic content, an accessible tab bar, and copy behaviour. It also moves Loop's Create / History tablist from the narrow Loop sidebar into the same full-width main-pane tab bar, so both workspaces use one navigation style. No backend route, API, framework, persisted state or native agent file is added or changed.

## Context Checked

- Architect brief: none listed by `gator loop status` (no `Architect brief:` line).
- `sketch.md` for this loop (scope, constraints, verification, non-goals).
- `.gator/procedures/writing-implementation-plans.md` (planning path, module and test discipline).
- `.gator/charters/INDEX.md` (routing for Dashboard browser assets).
- `.gator/charters/scripts-cross-cutting.md`: Package and License Surface. A new `scripts/dashboard/views/*.js` needs no `package-data` entry but must be added to `snapshot.py build_snapshot()` (regex and inlined block).
- `.gator/charters/scripts-dashboard-ui.md`: shell-owned history (#56) (`navigate`/`showView`/`restoreShellState`/`isShellEntry`/`cleanSub`, "no prompt text ever enters a state object"), `setActiveRepo`/`clearActiveRepo`, the Loop workspace entry (#56 tabs, `applyTabState`, `switchTab`, polls re-render panel contents only), `copyPrompt()`/`showPromptFallback()` fallback pattern, and the responsive shell.
- `.gator/charters/scripts-dashboard.md`: `build_snapshot(fast_data)` tripwire (script-tag regex plus inlined block, order pinned by `tests/test_snapshot.py`).
- Code: `src/gator_command/scripts/dashboard/dashboard.html` (brand `<img>`, sidebar nav, script order), `dashboard.js` (`VIEW_META`, `navigate`, `GatorShell`, `isShellEntry`, `restoreShellState`, `showView`, sidebar click handler, `doRefresh`, `init`), `views/loop.js` (`buildSidebarTabs`, `applyTabState`, `switchTab`, `renderLoopSidebar`, `copyPrompt`, `showPromptFallback`, the mount function `GatorViews.loop` and `.restore`), `views/repo.js` (copy-path clipboard handlers: success-only, no fallback), `dashboard.css` (`#sidebar-brand`, `#brand-logo`, `.loop-workspace`/`.loop-sidebar`/`.loop-main`, `.loop-subnav*`, the 768px media blocks), `snapshot.py`.
- Tests: `tests/test_dashboard_ui/test_loop_workspace.py` (`_navigate_to_loop`, `_tab_state` which asserts the tablist is inside `#loop-sidebar-nav`, `test_loop_subnav_tabs`, `test_loop_tabs_survive_polls`, empty-state tests reading `#loop-sidebar-nav` text, the #56 Back/Forward tests), the `tests/test_dashboard_ui/` file list, and `tests/test_snapshot.py` (script-tag assertions).
- Content sources: `README.md` (opening and Installation Notes), `docs/how-to-use-gator.md` (gatorize and session-start passages), and `.gator/mission.md`. The `docs/` directory listing confirms `architecture.md` and `how-to-use-gator.md` exist.

## Approach

**Planning path: one implementation-plan review.** The sketch recommends direct-to-coding, and the change is client-side only. It still has two separate responsibilities (Loop relocation and the new Welcome view) and one integration point (shell routing and history). A reviewed plan with two checkpoints fits this best. No trust boundary, API, schema or durable state changes.

**Module map (by responsibility):**

1. **Shared main-pane tab bar, with Loop moved onto it.** It owns the rule that Loop's Create / History selector is a full-width bar across the top of Loop's main pane and not part of the sidebar. Loop's selection, focus, polling and history behaviour do not change.
   - The bar spans the whole Loop view, above both the list column and the detail column. Its baseline therefore reaches the right edge of the Dashboard main pane, as the sketch's layout diagram shows.
   - The tabs stay left-aligned.
2. **Welcome workspace and logo routing.** It owns the `welcome` view: logo entry point, fixed topic content, ARIA tabs, and the transient copy behaviour. It never changes repository context or makes a request.

**Key design decisions:**

- **Panels stay where the lists are.** The tablist moves into the bar. The two `role="tabpanel"` containers (`#loop-panel-create`, `#loop-panel-history`) stay inside `#loop-sidebar-nav`, because they *are* the sidebar lists the tab chooses. `aria-controls` / `aria-labelledby` may point across containers. This keeps the sketch's "tab chooses the list/context, main pane inspects the selection" model with no new state.
- **Welcome topic state is module-local.** `views/welcome.js` keeps `selectedTopic` in a module variable, starting at `"what"`:
  - reopening Welcome while the page stays loaded (logo again, Back/Forward, Refresh) keeps the topic;
  - a fresh page load starts at **What is Gator?**.

  The shell records Welcome as an ordinary view entry `{view: "welcome", sub: null}`, and `cleanSub` stays Loop-only. *Rejected:* a shell-owned Welcome sub-state. It would widen the history contract for no requirement in the sketch, which marks it optional.
- **Copy fallback mirrors Loop's established pattern, but is not shared code.** On failure, Welcome shows a read-only `<textarea>` holding the prompt, pre-selected, with "Select all and copy manually." and a **Dismiss** button. This is the same structure and wording as `showPromptFallback()`. *Rejected:* extracting a shared helper out of `loop.js`. Loop's `copyPrompt` path carries the token epoch guards and the token non-persistence tripwire. Changing that path to share eight lines would put a security-relevant seam in scope for no benefit. `repo.js`'s copy handlers have no fallback, so they are not the pattern to follow.
- **Static content goes in with fixed markup.** All topic text is constant source text written by us, so it may be built with `innerHTML` from constants. No repository, server or user data is put into the Welcome DOM. The prompt string is written only through `textContent` and `textarea.value`.

**Simplicity boundary:**

- No backend change, no new endpoint, no `fetch` from `welcome.js`, no storage access, and no new framework.
- No per-vendor variants.
- No change to `cleanSub`, `GatorShell`, or the Loop copy path.

## Changes

Ordered by dependency (checkpoint 1, then checkpoint 2).

### 1. Shared main-pane tab-bar styling
- File: `src/gator_command/scripts/dashboard/dashboard.css`
- What:
  - Add `.gator-tabbar`, a block-level, full-width container that owns the baseline: `border-bottom: 1px solid var(--color-border)`, `padding: 0 24px`, `flex-shrink: 0`.
  - Add `.gator-tabbar [role="tablist"]`: `display:flex; flex-wrap:wrap; gap:4px`.
  - Add `.gator-tab`, moving the current `.loop-subnav-tab` rules over: transparent background, `border-bottom: 3px solid transparent`, `margin-bottom:-1px`, `padding:8px 12px`, `font-size:13px` (never reduced at narrow widths), muted colour, weight 400.
  - Add `.gator-tab[aria-selected="true"]`: `font-weight:700`, `border-bottom-color: currentColor`, text colour.
  - Add `.gator-tab:focus-visible`: `outline: 2px solid var(--color-link); outline-offset: 2px`.
  - Delete the `.loop-subnav` and `.loop-subnav-tab*` rules. The class names stay on the Loop elements only as JS and test hooks.
  - Change `.loop-workspace` to `flex-direction: column` (still `height:100%; min-height:0`).
  - Add `.loop-workspace-body` with the old row rules: `display:flex; flex:1; min-height:0`.
  - Move the 768px rule `.loop-workspace { flex-direction: column }` to `.loop-workspace-body`.
- Why: the sketch asks for one main-pane tab look for Welcome and Loop. The selected state is shown by weight plus underline, never by colour alone.

### 2. Move Loop's tablist into the main-pane bar
- File: `src/gator_command/scripts/dashboard/views/loop.js`
- What:
  - **Mount (`GatorViews.loop`).** The skeleton becomes:

    ```html
    <div class="loop-workspace">
      <div class="gator-tabbar loop-tabbar" id="loop-tabbar"></div>
      <div class="loop-workspace-body">
        <div class="loop-sidebar" id="loop-sidebar-nav">…Loading…</div>
        <div class="loop-main" id="loop-main-content">…</div>
      </div>
    </div>
    ```

    `.loop-workspace` keeps its `dataset.polling` role.
  - **Replace `buildSidebarTabs(listEl)`** with two functions:
    - `buildLoopTabs(container)`: called once per mount, right after the skeleton is written. It writes `<div class="loop-subnav" role="tablist" aria-label="Loop workspace">` with the two existing tab buttons (same ids, `data-tab`, `aria-controls`; classes `gator-tab loop-subnav-tab`) into `#loop-tabbar`. It binds the same click and keydown handlers as before, unchanged.
    - `ensureLoopPanels(listEl)`: called from `renderLoopSidebar()`. If `#loop-panel-create` is absent, it replaces the sidebar's contents (the "Loading…" placeholder) with the two existing `role="tabpanel"` containers (same ids and `aria-labelledby`). Otherwise it does nothing, so polls rewrite panel contents only, exactly as today.
  - **`applyTabState(root)`** now takes the view container and looks up tabs and panels by id from it. Its body (write only on difference) is unchanged.
    - Call sites: `renderLoopSidebar()` passes `container`; `switchTab()`'s else branch calls `applyTabState(container)` instead of querying `#loop-sidebar-nav`.
  - **Unchanged:** `LOOP_TABS`, `switchTab()` semantics (Create re-renders the main content only when not already in create mode, so a half-filled form survives), `selectLoop()`, `applySub()`, `currentSub()`, `shellPush()` / `shellReplace()`, `.restore`, polling, and every main-content renderer.
- Why: this is the sketch's "move Loop's existing Create / History selector … into an equivalent full-width tab bar". The tablist node is built once per mount and never by `renderLoopSidebar()`, so the #56 rule "polls re-render only the panel contents, so a focused tab keeps focus" still holds.

### 3. Loop test updates for the new location
- File: `tests/test_dashboard_ui/test_loop_workspace.py`
- What:
  - In `_tab_state`, replace `out.tablist = !!document.querySelector('#loop-sidebar-nav [role="tablist"]')` with a check that the tablist is inside `#loop-tabbar` and **not** inside `#loop-sidebar-nav`. `test_loop_subnav_tabs`, `test_loop_tabs_survive_polls` and the #56 Back/Forward tests then keep pinning roles, roving tabindex, keys, focus survival and history, unchanged otherwise.
  - Add `test_loop_tabbar_spans_main_pane`, which checks two things:
    - **Geometry:** `#loop-tabbar`'s bounding box runs from the Loop sidebar's left edge to `#view-slot`'s right edge (±1px), and its top lies above both `#loop-sidebar-nav` and `#loop-main-content`. The selected tab's computed `font-weight` is ≥ 700 and its `border-bottom-width` is 3px, while the unselected tab has weight 400 and a transparent border.
    - **Half-filled form:** with no active loop (the `beta` repo), type into `#loop-feature-input`, click History, then Create. The field still holds the text.
- Why: the existing tests assert the old location in only one place. Every other Loop guarantee the sketch lists (selection persistence, polling stability, Back/Forward) is already pinned by #56 tests that keep running. The form-survival case is not pinned today, and sketch Verification 8 names it.

### 4. Welcome view module
- File: `src/gator_command/scripts/dashboard/views/welcome.js` (new)
- What: an IIFE that registers `window.GatorViews.welcome = function (data, container)`.
  - **Constants:**
    - `TOPICS`: an ordered array of `{key, label}`:
      - `what` / "What is Gator?"
      - `can` / "What Gator can do"
      - `gatorize` / "Gatorize a repo"
      - `session` / "Start a session with Gator"
    - `SESSION_PROMPT`: exactly `"Run gator init in this repository. Treat its output, including the required\nsession-opening reads, as binding. Do not provide a substantive response until\nthose reads are complete."`, with the line breaks as written in the sketch.
    - `DOCS`: fixed absolute links to the public repository: `README.md`, `docs/architecture.md` and `docs/how-to-use-gator.md` under `https://github.com/cumberland-laboratories/gator/blob/main/`.
    - Module variable `selectedTopic = "what"`.
  - **Render.** It writes a `.welcome-workspace` container:
    - `div.gator-tabbar.welcome-tabbar` holding `div[role=tablist][aria-label="Welcome topics"]` with four `button.gator-tab[role=tab]` (`id="welcome-tab-<key>"`, `aria-controls="welcome-panel-<key>"`, `data-topic`);
    - then `div.welcome-body` holding four `section[role=tabpanel][id="welcome-panel-<key>"][aria-labelledby][tabindex="0"]`.

    It then calls `applyTopic()`, which writes `aria-selected`, roving `tabindex` (0/-1) and panel `hidden`, each only when it differs.
  - **Keyboard and mouse.** Click selects. Left/Right (wrapping), Home and End select and focus (automatic activation), with `preventDefault`. This is the same logic as Loop's handler. A switch only changes `selectedTopic` and calls `applyTopic()`: no re-render, no fetch, no shell call.
  - **Topic content** (short, plain sentences; no protocol or constitution text copied in):
    - *What is Gator?* One paragraph: Gator is the Git-native governance layer for AI-assisted engineering, not an AI coding framework or a hosted audit tool. One paragraph on the charter-first model: agents keep a compact map of each module (charters) as they work, and every governed commit records that understanding as evidence in Git. Next-step buttons "What Gator can do →" and "Gatorize a repo →" select those tabs. A link to the README.
    - *What Gator can do.* A four-item list with one sentence each: governed session opening; charters and commit evidence; local Dashboard inspection; governed Loop collaboration. Links to `how-to-use-gator.md` and `architecture.md`.
    - *Gatorize a repo.*
      - What gatorizing adds: the `.gator/` layer, templates, Git hooks, and Dashboard registration.
      - What it leaves alone: `CLAUDE.md`, `AGENTS.md` and `GEMINI.md` stay owned by the repository and untouched.
      - The command as a code sample, `<pre class="welcome-code"><code>gator gatorize &lt;target-directory&gt;</code></pre>`. This uses no second copy control, so the session prompt stays the one obvious copy action.
      - The next step: "Open the repository in your coding agent, then start a session (next tab)", with a button that selects *Start a session with Gator*.
      - A link to `how-to-use-gator.md`.
    - *Start a session with Gator.*
      - An ordered list of the sketch's four steps.
      - The prompt shown read-only in `pre.welcome-prompt` (set by `textContent`), so the Architect can see what will be pasted.
      - One `button.welcome-copy` labelled **Copy session-opening prompt**.
      - A `div.welcome-copy-status[role=status][aria-live=polite]`.
  - **`copySessionPrompt(btn)`:**
    - **Success:** if `navigator.clipboard && navigator.clipboard.writeText`, await `writeText(SESSION_PROMPT)`. Then the button text becomes "Copied", the status reads "Session-opening prompt copied.", and after 2 s the button label is restored and the status cleared. The status is cleared only if it still holds that text and the node is still connected.
    - **Unavailable or rejected:** call `showCopyFallback(btn)`, which removes any earlier `.welcome-copy-fallback` and inserts the Loop-pattern fallback: a `textarea.welcome-copy-fallback-text[readonly][rows=4]` with `.value = SESSION_PROMPT`, then `select()`, the hint "Select all and copy manually." and a **Dismiss** button that removes the fallback. It also sets the status to "Clipboard unavailable — copy the prompt manually." The fallback is never silent.
    - **Never:** `console.*`, storage, `data-*` holding the prompt, or `history` calls.
  - **Lifecycle.** Welcome registers no global listener or timer, so the shell's `_gatorRepoTeardown` handling needs nothing. The 2 s timeout checks `btn.isConnected`.
- Why: covers every bullet of the sketch's Content Model, Interaction and Accessibility Contract, and the prompt-transience constraint.

### 5. Shell routing and logo control
- Files: `src/gator_command/scripts/dashboard/dashboard.html`, `src/gator_command/scripts/dashboard/dashboard.js`
- What:
  - **`dashboard.html`:**
    - Wrap the logo as `<button type="button" id="brand-home" class="brand-home" aria-label="Open Welcome" title="Open Welcome"><img id="brand-logo" src="gator-logo.png" alt="" /></button>`. The image becomes decorative inside a named button.
    - Add `<script src="views/welcome.js"></script>` immediately after `views/settings.js` and before `dashboard.js`.
  - **`dashboard.js`:**
    - **`VIEW_META`:** add `welcome: { title: "Welcome to Gator!", subtitle: "" }`. `isShellEntry` therefore accepts Welcome entries, and Back/Forward works through the existing single restoration path.
    - **`showView`:** add a `welcome` branch that calls `updateTopbar("welcome", "")` and `views.welcome(state.data, viewSlot)`, with the usual "not available" fallback. It does **not** call `setActiveRepo` / `clearActiveRepo` and does not read or change `activeRepo` / `activeRepoKey`. The generic sidebar `.active` toggle already clears every nav item, since none has `data-view="welcome"`.
    - **Logo state:** in `showView`, also set `aria-current="page"` on `#brand-home` when the view is `welcome`, and remove it otherwise.
    - **Logo click:** `document.getElementById("brand-home").addEventListener("click", () => navigate("welcome"))`. This pushes `{view:"welcome", repo: activeRepo, repoKey, sub:null}`. On Back/Forward, `restoreShellState` re-hydrates the same repository context it recorded, so Welcome leaves Repo/Docs/Loop dimming exactly as it was.
    - **Unchanged:** the `#sidebar-nav` handler, `cleanSub`, `GatorShell`, `doRefresh` (Refresh on Welcome re-runs `showView("welcome")`, and the module-local topic survives), and `init` (a fresh load still lands on Fleet or `?repo=`).
- Why: the sketch's logo-as-real-control and routing requirements. History stays shell-owned and holds no prompt text.

### 6. Welcome and logo styling
- File: `src/gator_command/scripts/dashboard/dashboard.css`
- What:
  - **`.brand-home`:** button reset (`background:none; border:0; padding:0; cursor:pointer; border-radius:8px`) with `:focus-visible { outline: 2px solid var(--color-link); outline-offset: 4px }`. `#sidebar-brand` and `#brand-logo` sizing is unchanged, including the 768px block.
  - **Welcome layout:** `.welcome-workspace` (block layout under the default `#view-slot` scrolling) and `.welcome-body` (`padding: 20px 24px; max-width: 760px`).
  - **Code and prompt:** `.welcome-code` and `.welcome-prompt` (monospace, bordered, `white-space: pre-wrap`).
  - **Copy control:** `.welcome-copy`, `.welcome-copy-status`, and `.welcome-copy-fallback*`, which match the `.loop-handoff-fallback*` sizing.
  - **Tabs:** no Welcome-specific tab rules; `.gator-tabbar` / `.gator-tab` from Change 1 apply.
- Why: a visible focus indicator on the logo, and Welcome uses the shared tab look.

### 7. Offline snapshot inlining
- File: `src/gator_command/scripts/dashboard/snapshot.py`
- What:
  - Read `views/welcome.js`.
  - Add `<script src="views/welcome\.js"></script>\s*` to the regex after `settings`.
  - Add the inlined `<script>` block after `settings_js` and before the data block.
- Why: the `build_snapshot` tripwire. Without this change, the snapshot keeps an external reference and the regex stops matching.

### 8. Welcome and snapshot tests
- Files: `tests/test_dashboard_ui/test_welcome_ui.py` (new); `tests/test_snapshot.py`
- What: each test proves a separate risk.
  1. `test_logo_opens_welcome_without_repo_mutation`, parametrized over `fleet`, `repo` (`?repo=alpha`) and `loop`. It records the Repo label text and the `dimmed` state of `#repo-tab` / `#docs-tab` / `#loop-tab`, then clicks `#brand-home`. Checks:
     - the topbar title is "Welcome to Gator!";
     - **What is Gator?** is selected;
     - the label and dimming are unchanged;
     - `page.on("request")` records no request to `/api/` from the logo click through every tab switch and the copy action.

     This covers sketch Verification 1, 2 (default) and 5.
  2. `test_welcome_tabs_aria_and_keyboard`: checks roles and `aria-controls` ↔ panel ids, roving tabindex, click selection, ArrowRight/ArrowLeft wrap and Home/End moving focus and selection, exactly one visible panel, the selected tab with computed weight ≥ 700 and a 3px bottom border while the others have 400 and a transparent border, and `.welcome-tabbar` spanning `#view-slot`'s width (±1px). This covers Verification 2 and 3.
  3. `test_welcome_copy_success`: grants `clipboard-read`/`clipboard-write`, clicks copy, and checks:
     - the clipboard text equals the sketch prompt exactly;
     - the button reads "Copied" and the `role=status` region announces it;
     - `history.state`, `localStorage` and `sessionStorage` contain no part of the prompt.

     This covers Verification 4 and 6.
  4. `test_welcome_copy_fallback`, parametrized over `navigator.clipboard` undefined and `writeText` rejecting (via `add_init_script`). It checks that a read-only textarea holds the exact prompt and is selected, that the status announces the failure, and that Dismiss removes it. This covers the "honest fallback" requirement.
  5. `test_welcome_narrow_width`: at a 400×800 viewport, all four tabs are visible and fully inside the viewport (not clipped), and the tab font-size equals the desktop value. This covers the narrow-width contract.
  6. `test_welcome_back_forward_and_topic_reset`: Fleet → logo → select *Gatorize a repo* → Back shows Fleet → Forward shows Welcome with *Gatorize a repo* still selected (same page). Then `page.reload()` and the logo show *What is Gator?*. This covers the shell-owned history and the default-on-fresh-load rule.
  - **Snapshot test:** `tests/test_snapshot.py` adds `'src="views/welcome.js"'` to both "no external script tag" lists and asserts `GatorViews.welcome` is inlined.
- Why: one test per new behaviour or invariant. Unchanged Fleet/Commits/Docs/Loop navigation (Verification 7) is covered by the existing suites at final approval.

## Dependencies and Ordering

1. Changes 1–3 (checkpoint 1) come first: they create the shared `.gator-tabbar` / `.gator-tab` style and prove it on Loop.
2. Changes 4–8 (checkpoint 2) depend on the shared style. Inside checkpoint 2, `welcome.js` (4) must exist before the HTML script tag and shell branch (5) and the snapshot regex (7). The tests (8) come last.
3. Nothing can run in parallel across checkpoints. Charter updates follow each file edit.

## Assumptions, Risks, and Required Architect Decisions

- **Non-blocking (assumption): Loop bar span.** "Across the top of Loop's main pane" is read as spanning the whole Loop view (list column plus detail column), so its baseline reaches the main pane's right edge, as the sketch's layout diagram shows. *Will narrow it to the detail column only if the Architect directs.*
- **Non-blocking (assumption): doc links.** "Link outward" uses plain hyperlinks to the canonical public docs on GitHub (`target="_blank"`, `rel="noopener noreferrer"`). These are navigation links, not loaded resources, so the "no remote dependency" constraint holds and snapshots work offline. *Will switch to plain file-path references if the Architect prefers no outbound links.*
- **Non-blocking (assumption): visible prompt.** The prompt is shown read-only in the session panel as well as copied, so the Architect can see exactly what is pasted. It is never persisted or put into navigation state. *Will hide it behind the copy control if the Architect directs.*
- **Non-blocking (assumption): topbar title.** The topbar title reads "Welcome to Gator!" as the sketch's layout reference shows.
- **Risk: Loop focus or poll stability after the move.** Mitigated: the tablist is built once in `#loop-tabbar` at mount, and `renderLoopSidebar()` only rewrites panel contents. `test_loop_tabs_survive_polls` (keeps the tablist node across more than two polls, plus focus) stays in force.
- **Risk: Loop layout height chain.** Adding a column wrapper could break the inner scroll owners. Mitigated: `.loop-workspace-body { flex:1; min-height:0 }` keeps `.loop-sidebar` / `.loop-main` `overflow-y:auto`. The full Loop suite runs at final approval.
- **Risk: the snapshot regex silently failing to match.** Mitigated: `test_snapshot.py` asserts there are no external view tags and that the module is inlined.
- **No blocking decisions.** Nothing touches native agent files, the copy prompt has no layout-dependent path, and no backend change is needed.

## Testing

Verification ladder:

- **Checkpoint 1 (focused):** `pytest tests/test_dashboard_ui/test_loop_workspace.py -k "subnav or tabs or tabbar or back or history_tab or sidebar or create"`. This covers the moved tablist, the new geometry and form-survival test, polls and focus, and #56 Back/Forward.
- **Checkpoint 2 (focused):** `pytest tests/test_dashboard_ui/test_welcome_ui.py tests/test_snapshot.py`.
- **Final approval (broad, once):** `pytest tests/test_dashboard_ui tests/test_snapshot.py tests/test_packaging.py`. This is the whole Dashboard UI suite (Loop, liveness, coding, markdown, responsive shell, fleet layout) and confirms Fleet/Commits/Docs/Loop navigation is unchanged (Verification 7). `test_packaging.py` confirms the new view ships under the existing `dashboard/**/*` glob.
- **Manual check at final approval:** open the logo from Fleet, from Repo, and with no repository selected, at desktop width and at ~400px width. Confirm the focus ring on the logo and tabs, and run a real clipboard copy in a browser.

## Charter Impact

- `scripts-dashboard-ui.md`:
  - **Covers / Owns:** add Welcome to the view list.
  - **`navigate()…` entry:** state that `welcome` is a `VIEW_META` view routed only from `#brand-home` (`aria-label="Open Welcome"`, `aria-current="page"` while shown), that it never calls `setActiveRepo` / `clearActiveRepo`, and that its entries carry `sub:null`.
  - **New entry `GatorViews.welcome / applyTopic() / copySessionPrompt() / showCopyFallback()`:**
    - fixed content and module-local `selectedTopic` (reset on page load);
    - ARIA tab contract and keyboard;
    - no fetch, storage, console or history writes;
    - the prompt is written only via `textContent` / `textarea.value`;
    - a tripwire that the copied prompt contains no `GATOR_INIT.md` path and no vendor name;
    - pinned by `test_welcome_ui.py`.
  - **Loop workspace entry:** rewrite the "Secondary sidebar (#56 tabs)" bullet. The tablist lives in `#loop-tabbar` (`.gator-tabbar`), built once per mount by `buildLoopTabs()`. The panels stay in `#loop-sidebar-nav` (via `ensureLoopPanels()`). `applyTabState(container)`. Rename the function list (`buildSidebarTabs` → `buildLoopTabs`, add `ensureLoopPanels`).
  - **Responsive shell entry:** add the shared `.gator-tabbar` / `.gator-tab` main-pane tab treatment (selected = weight + underline) and the `.loop-workspace` → `.loop-workspace-body` column/row chain.
- `scripts-dashboard.md` → `build_snapshot()`: update the pinned script order to add `welcome` after `settings`.
- `scripts-cross-cutting.md`: no change. The Dashboard-asset packaging rule already covers a new `views/*.js`.
- `INDEX.md`: no change. `views/**` is already routed.

## Coding Checkpoints

1. **Shared main-pane tab bar with Loop relocation** — add the `.gator-tabbar` / `.gator-tab` treatment and move Loop's Create / History tablist from the Loop sidebar into a full-width `#loop-tabbar` above the Loop workspace body. The panels stay in the sidebar, and selection, polling, focus and Back/Forward behaviour are unchanged. Update the Loop charter entries.
  Verify: `pytest tests/test_dashboard_ui/test_loop_workspace.py -k "subnav or tabs or tabbar or back or history_tab or sidebar or create"`, including the updated `_tab_state` location assertion and the new `test_loop_tabbar_spans_main_pane`.
2. **Welcome workspace and logo routing** — add `views/welcome.js` (four ARIA topics, fixed content, transient copy with the Loop-pattern fallback), the `#brand-home` logo button, the `welcome` shell view and routing, Welcome styling, snapshot inlining, and the charter updates.
  Verify: `pytest tests/test_dashboard_ui/test_welcome_ui.py tests/test_snapshot.py`. At final approval, run once: `pytest tests/test_dashboard_ui tests/test_snapshot.py tests/test_packaging.py`.
