# Charter: Dashboard Views

**Covers**: `src/gator_command/scripts/dashboard/views/fleet.js`, `src/gator_command/scripts/dashboard/views/history.js`, `src/gator_command/scripts/dashboard/views/repo.js`, `src/gator_command/scripts/dashboard/views/syntax.js`, `src/gator_command/scripts/dashboard/views/audit.js`, `src/gator_command/scripts/dashboard/views/updates.js`, `src/gator_command/scripts/dashboard/views/docs.js`, `src/gator_command/scripts/dashboard/views/charters.js`, `src/gator_command/scripts/dashboard/views/welcome.js`, `src/gator_command/scripts/dashboard/views/settings.js`

## Owns

- Fleet, history, repo, audit, loop, charters, updates, settings, and welcome views.
- Document browsing, syntax highlighting, cross-document search, and sandboxed HTML preview controls.

## Does Not Own

- Route authorization, path containment, filesystem access, or data computation; see [`scripts-dashboard.md`](scripts-dashboard.md).
- Governance business rules.
- Cumberland document-template styling; see [`contracts.md`](contracts.md).
- The page shell, navigation, workspace tabs, requests and styling; see [Dashboard Shell](scripts-dashboard-shell.md).
- The Loop workspace; see [Loop Workspace View](scripts-dashboard-loop-ui.md).

---

### renderStandaloneRepos() / GatorViews.fleet() / placeMenu() / applySort() / sortRows() / window.gatorNavToRepo() / window.gatorOpenRepoInNewContext() — Fleet view and actions
File: src/gator_command/scripts/dashboard/views/fleet.js
File: src/gator_command/scripts/dashboard/dashboard.js
Render repository health and expose explicit per-repository actions via a three-dot overflow menu.
<- fleet route
-> repo update/gatorize endpoints, `POST /api/repos/remove`
! The overflow menu carries dual identity: `data-repo-name` for name-addressed Update/Gatorize, `data-repo-path` for path-addressed Remove. Each action dispatches to the correct identity.
! **Update result: `openUntrackedDialog(repoName, result)`.** When a successful update response carries `transient_untracked`, `performLifecycleAction()` opens `.gator-modal-overlay.fleet-untracked-dialog` with the CLI's `message`, the exact `paths` (`ul.fleet-untracked-paths`), a `details.fleet-untracked-why` "Why am I seeing this?" holding `why`, and Close. All text is escaped and comes from the server. The dialog is attached to `<body>` so the Fleet refresh that follows cannot remove it. A null result shows nothing. Pinned by `test_update_result_lists_untracked_hook_files` / `test_update_without_untracking_shows_no_dialog` (`test_fleet_layout.py`).
! Actions use the repository's stable key, not display text or array position.
! Missing repositories remain representable so users can understand and clean stale registry entries.
! **⋮ menu stays visible.** The menu (`.overflow-menu`, absolute in `.overflow-menu-wrapper`) must never be clipped, including on the last row and in a short window.
  - The Fleet table is `table.data-table.fleet-table` with `overflow: visible`. `.data-table`'s `overflow: hidden` would clip a menu that extends past the last row. The rounded corners are kept by radius on the header's top corner cells and the last body row's bottom corner cells. Other `.data-table` uses keep `overflow: hidden`.
  - `placeMenu(btn, menu)` runs on every open. It measures the space below the button inside the visible area (the window, or `#view-slot` if that ends sooner). If the menu does not fit there and there is more room above, it adds `.open-up` (`bottom: 100%`). `closeAllMenus()` removes `open` and `open-up`.
  - Pinned by `test_last_row_menu_is_fully_visible` (`test_fleet_layout.py`).
! **Opening actions.**
  - **The ⋮ menu** gains two items, before Update/Gatorize and Remove, and only when `!window.GATOR_SNAPSHOT`:
    - **"Open in new workspace tab":** `button.menu-item.menu-open-workspace[data-action="open-workspace"]`, carrying `data-repo-name` and `data-repo-key`. It dispatches to `window.gatorOpenRepoInNewContext(name, key)`.
    - **"Open in new browser tab":** a native `a.menu-item.menu-open-browser-tab`, with `href="?repo=<encodeURIComponent(name)>"`, `target="_blank"` and `rel="noopener"`. It is a same-origin relative link with no handler of its own, so middle-click works. It never names a path or key.
  - **The row link** (`gatorNavToRepo`) means "open in the current context". When another context already holds that repository, it selects that context instead (one context per repository). Otherwise it navigates as before, which turns the current context into that repository's context.
  - **`gatorOpenRepoInNewContext`** (`dashboard.js`) selects the existing context for that repository, or creates `{repo, repoKey, view: "repo"}` (the Repo overview) and selects it with focus. At 12 contexts it shows the `.shell-notice` "Workspace limit reached (12). Close a workspace first." and does nothing else.
  - **Identity:** contexts match by `repoKey` when both sides have one, never by row position.
  - **Pinned by** `test_fleet_open_actions` and `test_fleet_open_workspace_at_limit` (`test_workspace_tabs.py`).
! **Paper inventory.** Under the title-only header, Fleet is `div.fleet-header`, holding only `#add-repo-btn` (Paper-styled through a scoped rule), then one `table.data-table.fleet-table`. It has no summary text and no cards.
  - **Typography:** the repository name, `button.link-btn.fleet-repo-name`, is `--text-base` (`.fleet-table .fleet-repo-name`, which outranks the later `.link-btn { font: inherit }`). `td.fleet-branch` and `td.fleet-version` are mono `--text-sm`; the version's inline style is gone. Column labels are `--text-ui` / 500 / gray-600, in sentence case.
  - **Table:** one gray-200 boundary, gray-100 row hairlines and a gray-50 hover, all scoped to `.fleet-table`. The `overflow: visible` and corner rules are unchanged.
  - **Row menu (⋮):** `.overflow-menu-btn` has a transparent 1px border at rest; the border appears on `:hover` and `:focus-visible`. It is transparent rather than removed, so the button keeps its size. Opening the menu and menu placement are unchanged.
  - **Empty state:** `td.fleet-empty`, with prose at `--text-base` / `--leading-prose` and `code` at mono `--text-sm`.
  - **Unavailable repository:** the "!" marker also holds the visually hidden text "Not accessible" (`.fleet-hidden-text`).
  - **Narrow widths:** the table is not wrapped. At ≤768px it scrolls sideways inside `#main-shell`, the narrow scroll owner, and the page never scrolls.
! **Sorting — `SORT_COLUMNS` / `fleetSort` / `sortValue()` / `sortRows()` / `applySort()` / `applySortHeaderState()` / `bindSortHeaders()`.**
  - **Columns:** Repo, Branch, Commit policy and Version. Each `th[data-sort-key]` holds a native `button.fleet-sort` and an `aria-hidden` `.fleet-sort-mark`. The ⋮ and activity columns are not sortable, so there are still six `th`. ! The machine-local Strict/Warn dropdown sits **inside** the Commit policy cell, not in a column of its own (see below).
  - **State:** `fleetSort = {key, dir}` is module-local for the page load. It is never stored, and never put in history or the URL. It survives a Fleet re-render (Refresh, `gatorRefreshFleet`). `key: null` (the default) is registry order.
  - **Activation:** a click, or Enter/Space. A new column sorts ascending; the same column toggles between ascending and descending.
  - **The sorted `th`:** it gets `aria-sort`, a ▲/▼ mark and `.fleet-sort-active` (weight 600, gray-900). Other headers have no `aria-sort` and no mark. The state is never colour alone.
  - **Values:** each row carries `data-row-index`, `data-sort-name`, `data-sort-branch`, `data-sort-version` and `data-sort-policy`. Comparison is `localeCompare(…, {numeric: true, sensitivity: "base"})`. A missing value sorts last in both directions, and ties keep registry order.
  - **Applying a sort:** `applySort(table)` moves the existing `<tr>` nodes (`tbody.append`), so no menu listener is rebound and header focus stays. The render and header clicks call it.
  - ! **Commit policy.** `commitPolicy(repo)` maps the payload to one posture, in this order: `Unknown` when `repo.accessible === false`; `Not gatorized` when `repo.gatorized === false`; `Managed by Enterprise` when `repo.enterprise_managed`; `Warn` when `repo.commit_policy === "warn"` (`policyLevel()`: this machine's level for the clone, never the tracked `config.json`); else `Strict` (key `default`). There is no local Off. Each posture has a one-sentence `note`, and `active` is false for the first two, which never claim the default checks. A non-editable row's cell is `span.fleet-policy` text (also `.muted` when inactive) with the note in `title`; `data-sort-policy` is the label for active postures and empty otherwise, so inactive rows sort last. The old three-way strict/warn/off selector, `bindEnforcementDropdowns()`, the save-then-sort path and the `.enforcement-select` / `.save-check` CSS stay removed. `window.GatorCommitPolicy.posture` exposes the same mapping to `views/settings.js`, so the two views cannot disagree.
  - ! **Strict/Warn dropdown: `policyEditable()` / `bindPolicySelects()` / `openWarnConfirmDialog()` / `writePolicy()`.** Only an editable row gets the control. That means not a snapshot, accessible, gatorized, and not Enterprise-managed; the server also refuses Enterprise-managed rows with 409. An editable row shows `select.fleet-policy-select` **instead of** the posture text in `td.fleet-policy-cell`, with exactly two options, `strict` "Strict" and `warn` "Warn", `aria-label="Commit policy for <repo> on this machine"` and the posture note in `title`. The cell gains no column and no width; a seventh column once pushed the ⋮ menu past the pane edge at 800px, which Linux CI caught as a column shift in `test_fleet_update_click_preserves_column_geometry`. The level is machine-local (Git's private area for the clone), so it never changes another engineer's checks.
    - **Choosing Warn** resets the dropdown to Strict at once and opens `.fleet-warn-dialog` (a `role="dialog"` `.gator-modal`, focus on Cancel; Escape, backdrop and Cancel close and refocus the dropdown). The dialog names the repository and says commits then go through with missing charter updates and dangerous-pattern findings. It also says this applies only to this checkout on this machine, is not stored in the repository, that each Warn commit records `Gator-Commit-Policy: warn`, and to choose Strict to restore the default checks. Only "Use Warn mode" writes `warn`.
    - **Choosing Strict** writes `strict` with no dialog (the safe direction).
    - `writePolicy(repoName, level, errorEl, control, prior)` is the only caller of `POST /api/repo/<name>/commit-policy` (body `{level}`, `X-Gator-Dashboard`). It disables the dropdown during the request. On success it calls `gatorRefreshFleet()`, so the row re-renders from the server. On failure it restores the dropdown to `prior`, the level the server still holds, and writes "Not changed: <reason>" into the row's `span.fleet-policy-error` (`role="alert"`, text, not colour alone). It never claims a change optimistically.
  - **Pinned by** `test_fleet_title_only_inventory` (1440 and 375; the only selects are `fleet-policy-select` with `strict/warn`), `test_fleet_sort_one_column`, `test_fleet_commit_policy_postures`, `test_fleet_policy_dropdown`, `test_fleet_warn_success_rerenders_from_the_server`, `test_settings_commit_policy_is_read_only` and `test_sorted_last_row_menu_targets_its_row`, all in `test_fleet_layout.py`.
  - `test_last_row_menu_is_fully_visible` now also runs at 375×700. It measures the items against the scrolling pane (`#view-slot` on desktop, `#main-shell` when narrow) and asserts that the page never scrolls. The first row is pinned to open downward only in tall windows: at 1280×420 the taller Paper rows leave no room for the menu below it, so `placeMenu()` correctly opens it upward, and the test checks that it is fully usable.

### openRemoveConfirmDialog() / remove handler
File: src/gator_command/scripts/dashboard/views/fleet.js
Confirmation dialog for removing a repo from the dashboard registry. Reuses the `.gator-modal` pattern.
<- overflow menu Remove action
-> `POST /api/repos/remove` (path-addressed)
! Registry-only operation — no filesystem access. Dialog text makes this explicit.
! Posts the registered path, not the display name.

### GatorViews.history() / buildView() / commitRow() / commitBody() / recordOf() / kindOf() / renderDescription() / dayLabel() — Commits view
File: src/gator_command/scripts/dashboard/views/history.js
Render Git-native commit history as collapsed rows with a readable Gator record.
<- history route (nav label and topbar title "Commits"; the route key `history`, `data-view="history"` and the endpoint keep the name history)
-> `GET /api/repo/<name>/history?limit=30` (`description` and `trailers` fields: see `scripts-dashboard.md` → `get_repo_history()`); `window.GatorLoopMarkdown`
! Accept both current Architect and legacy PI attribution supplied by the backend (the server already folds `Gator-PI` into `architect`).
! **Stale-render guard:** the commits fetch writes only while the "Loading history..." node it created is still attached. If another view owns `#view-slot` by the time the fetch resolves (for example after a quick Back), the result is dropped.
! TRIPWIRE (untrusted text): commit text is model-authored. Every commit-derived string reaches the DOM through `textContent` / text nodes (`el()`), and the description through `GatorLoopMarkdown.render()` (closed grammar, DOM-only). No `innerHTML` anywhere in the view. If the formatter throws (too large) or is missing, `renderDescription()` shows the literal text in `pre.commit-desc-raw`.
- **Layout:** `div.commits-view` > `div.commit-toolbar` + `div.commit-list`.
  - **List:** `h3.commit-day` headings by **local** day ("Today · …", "Yesterday · …", then the weekday and date; the year when it is not the current one; "Undated" for a bad date). Each commit is a `details.commit-row[data-kind=<group>][data-hash]`, collapsed by default and opened by click or Enter/Space (native `<summary>`).
  - **Summary:** `span.commit-kind` (glyph + label tag), `div.commit-subject`, `div.commit-meta` (`span.commit-hash` short hash · local time · "<agent> with <architect>", else whichever is known, else the author), and `span.commit-flags`: "★ Notable" only for significance `notable`, "⚑ Override" only when an override trailer exists, "✓ Acknowledged" (`commit-flag-acknowledged`) only when `Gator-Dangerous-Patterns` exists, then a chevron.
  - **Body (`commitBody()`):**
    - `div.commit-desc`: the `description`, or "No description.";
    - an optional `div.commit-override` (amber left border): approved by, rules, block, reason;
    - an optional `div.commit-acknowledgement` (neutral gray left border): "✓ Architect acknowledgement by <Architect>." plus the kept keys from `recordOf().acknowledgement` (`patterns`, `by`). `patterns` splits the trailer on `,` only and trims each key; it never uses the tag/issue whitespace splitter, because a key's path may contain spaces. It is a separate element from the override note and is told apart by label and glyph, not colour alone. Pinned by `test_acknowledgement_note_is_distinct_from_override`;
    - an optional `div.commit-unacknowledged` (dashed gray rule): "! Unacknowledged dangerous pattern. Committed without an Architect decision: <keys>" from `recordOf().unacknowledged` (`Gator-Dangerous-Patterns-Unacknowledged`, split on `,` only), with a "! Unacknowledged" row tag (`commit-flag-unacknowledged`, bold). Pinned by `test_unacknowledged_note_is_distinct`;
    - `div.commit-record` with three columns: **Change** (Type, Significance, Charters through `CHARTER_TEXT`: yes / no / override-skip; plus **Issues** chips "#N" from `Gator-Issues`), **Decision tags** (chips), and **Knowledge layer at this commit** (Charters, Functions, Threads). A missing field is omitted, never "undefined", so older commits render cleanly;
    - `div.commit-actions`: "⧉ Copy hash" (full hash via the Clipboard API; the label shows "✓ Copied" or "Copy failed" for 1.5 s) and "{ } Raw trailers" (`aria-expanded`), which toggles `pre.commit-raw` with every projected `Key: value` line. `Gator-Machine-Id` appears **only** there; `recordOf()` never reads it, so the record stays free of machine identity.
- **Change types (`KINDS`):** one entry per producer value (`VALID_CHANGE_TYPES`).
  - Feature ✦, Fix ✚, Docs ▤ and Release ⬆ each have their own group.
  - Housekeeping ↺ groups maintenance, governance, refactor and test, each still labelled by its own name.
  - Review ◇ is grouped "other".
  - `kindOf()` gives any unknown or empty value a neutral "•" label (the raw value, or "Commit").
  - `GatorViews.history.changeTypes` exposes the keys read-only so the test can pin them against the producer.
- **Toolbar:**
  - **Filter chips:** `div.commit-filters[role=group]` buttons with `aria-pressed` and a count: All, Features, Fixes, Docs, Housekeeping, Releases. "Other" commits show only under All.
  - **Search:** `input.commit-search[type=search]` matches subject, full or short hash, and decision tags, case-insensitive.
  - **Scope and state:** both work over the loaded commits only (30). The filter, query and set of open rows live in the mount's closure. A re-render keeps open rows open, and nothing is stored or put in history.
- **Blocked commit — `alertState()` / `mountBlockAlert()` / `openBlockDialog()` / `fetchOverrideStatus()` / `postOverride()`:**
  - **Fetch.** The mount fetches `GET /api/repo/<name>/override` once, beside `/history` (`overridePromise`). There is no poller, timer or Fleet/sidebar mark. A failed fetch (including the offline snapshot) means no alert. The result is applied only while the toolbar is still connected, the same stale guard as the commits fetch.
  - **Alert.** `button.commit-block-alert[data-kind]`, inserted between `.commit-filters` and `.commit-search`, exists only when `alertState(status)` is non-null. `alertState` is exposed read-only as `GatorViews.history.alertState`.
    - `none` / `ungoverned` → no alert.
    - `malformed` / `expired` / `stale` / `legacy` / `incomplete` → "⚑ Commit block needs refresh" (`refresh`).
    - `unsupported` / `unavailable` / an unknown state → "⚑ Commit status unavailable".
    - Otherwise, from the CLI's `uncovered_external_rules`, never from `approval.state`: uncovered rules → "⚑ Commit blocked" (`blocked`); pause only → "⚑ Architect decision needed"; fix only → "⚑ Commit fix needed"; pause + fix → "⚑ Commit blocked" (`mixed`, no Approve); else "✓ Approved — retry commit".
    - The label and glyph carry the meaning; the border colour is only a second cue.
  - **Dialog.** A native `<dialog class="loop-dialog commit-block-dialog">` opened with `showModal()`, so it gets the Loop dialog styling, centring and compact leading. Contents:
    - the title (`h2#commit-block-title`), with an optional `p.commit-block-notice[role=status]`;
    - the scope (`.commit-block-scope-line`: block id, age, local expiry, "Staged change matches/differs"; `.commit-block-files`, the first 8, with a `details.commit-block-more` "+N more" using `files_total`);
    - labelled groups `section.commit-block-group[data-resolution]`: ⚑ External approval, ⏸ Architect decision required, ✚ Fix required. An external finding's tag reads "✓ Approved by <name>" (`covered`) or "Needs approval";
    - `.loop-dialog-note` guidance per state and group (covered/still-needed lines, exact-change, pause → decide here or in the agent session, ending with `PAUSE_OPEN_TEXT` "Closing does not resolve the pause. The commit still pauses until a decision is recorded here, by an agent, or as a visible skip.", fix → retry);
    - the unsupported, unavailable and incomplete message, with `code.commit-block-command`.
  - **Approve.** It appears only when `approvableHere()` holds: state `blocked`, uncovered external rules, and `approve_refusal` null or `too-recent`.
    - Fields: "Architect name" (prefilled from `architect_default`, max 80) and "Reason (required)" (max 500 after line breaks and tabs are folded to single spaces by `oneLine()`, live "n / 500", "(too long)" above it; no `maxLength`, so a paste is never silently cut; the textarea has `flex: none` in `.commit-block-fields` so `resize: vertical` works).
    - It stays disabled until both are valid and `approve_wait_seconds` (from fetch time) has passed. The label reads "Approve (available in Ns)", ticking with one-second `setTimeout`s while the dialog is open; this is not a server poll.
  - **Every mutation re-reads first (`preflight()`).** A changed `revision`, state or block id re-renders from the fresh status with "The blocked commit changed. Review it again before approving." (Discard: "… Review it, then confirm again."), keeps the fields, and posts nothing. A failed re-read shows the error and posts nothing.
    - The POST carries the `block_id` and `revision` the dialog was rendered from (Discard sends `block_id: null` for an unreadable block).
    - A `block-changed` / `findings-changed` refusal re-fetches and re-renders the same way. Any other refusal keeps the fields and shows the server `message` in `p.loop-ctrl-error[role=alert]`.
  - **Acknowledge: `ackable()` / `ackIdentity()` / `ackPanel()` / `acknowledge()`.** `section.commit-block-ack` appears only when the state is `blocked` or `approved`, a pause finding is recorded, `pause_findings` is non-empty and not `pause_findings_incomplete`, and `block.tree_matches`. It shows "Acknowledge N current finding(s)", every paused key (`code`) with its severity and message, and an optional "Shared note" (≤ 500). The identity is the draft's Architect, else `architect_default` (sent as `architect`), and an "Architect name" field (`#commit-block-ack-name`) appears only when neither exists. One confirm button, **Acknowledged** (`.commit-block-acknowledge`), posts `{block_id, keys: <every pause_findings key>, architect?, note?}` after `preflight()`. Success shows "Decision recorded; retry the commit." and re-fetches. `findings-changed` / `block-changed` / `tree-changed` re-fetch and re-render the new set. The browser never builds keys or YAML.
  - **Close without resolving.** The Close button reads "Close without resolving" whenever a pause, a fix-required finding or an uncovered external rule remains; closing posts nothing, and the alert stays.
  - **Discard block…** swaps in an inline confirmation ("Discard this blocked attempt and any approval? Nothing is committed…"; with a pause it adds "Discarding does not decide the pause: it returns on the next attempt until a decision is recorded.") with Keep and Discard.
  - **In flight:** `data-sending`, every button and field disabled, Approve reads "Sending…", and the native `cancel` (Escape) is prevented.
  - **Honesty strings.** Success shows "External approval recorded. Retry the commit in your Git client or agent session.", or, with remaining findings, "External approval recorded. This commit is still blocked until the remaining findings are resolved." Discard shows "Discarded. Nothing was committed…". No string implies a commit happened. The alert is re-fetched after a success.
  - **Focus.** Closing removes the dialog and returns focus to the alert, or to the search when the alert is gone.
  - ! TRIPWIRE: the view never classifies a rule or decides coverage; it maps the CLI's answer only. Every CLI-derived string is set with `textContent` (no `innerHTML`, as for commit text).
  - ! The alert does not depend on the history. With commits it sits in `buildView()`'s toolbar. When the history is empty (a blocked first commit), returns an error, or the request fails, `showMessage()` renders a bare `div.commit-toolbar.commit-toolbar-bare` plus the history's own message (`.commit-placeholder` / `.commit-history-message`), and mounts the same alert there. A history failure never hides a recorded block. With no alert and no search box to return to, closing the dialog focuses `#topbar-title`.
  - Pinned by `tests/test_dashboard_ui/test_commits_block_ui.py`; the text roles by the `commits-block-dialog` surface of `test_no_text_inherits_root_type`.
- **CSS:** `commit-*` rules under "Commits view" in `dashboard.css`, built from tokens. The 120px type column folds above the subject at ≤1100px. The `commit-block-*` rules (alert, scope, groups, findings, tags, notice/success, count, command) are scoped additions with explicit text roles. At ≤600px the toolbar stacks and the alert takes its own full-width row.
  - The old commit-list classes (`.history-commit`, `-header`, `-subject`, `-meta`, `-badge`, `-body`) are gone.
  - ! The `.history-toggle-btn`, `.history-dropdown`, `.history-item`, `.history-active`, `.history-hash`, `.history-date` and `.history-msg` rules belong to the **Repo branch-history dropdown** (`#topbar-repo-tools`) and stay.
  - The old view's second `.history-hash` rule used to restyle that dropdown through the cascade; its properties were folded into the dropdown's own rule, so the dropdown looks the same.
- **Pinned by** `tests/test_dashboard_ui/test_commits_view.py`.

### GatorViews.repo(data, container, repoName, version, repoKey) / loadFileList() / renderListing() / loadFile() / applyRefresh() / pollRepoFiles() / pickDefaultFile() / currentFilePaths() / cleanRepoKey() / newTreeState() / acquireTreeState() / treeState() / setSelectedFile() / isCurrentMount() / installSearchListeners() / teardownRepoView() / cacheGet() / cachePut() / cacheable()
File: src/gator_command/scripts/dashboard/views/repo.js
Render the repository knowledge browser, fetch canonical listings, and display supported content.
<- repo route and sidebar clicks; `dashboard.js` passes `state.activeRepoKey` as `repoKey` from the `showView("repo")` branch and the branch-history dropdown
-> list/file/raw/search endpoints
! **Tree state is per repository KEY.**
  - **Storage:** `_treeStates: Map<repoKey, {expandedDirs: Set, selectedFile, scrollTop}>`, bounded at `TREE_STATE_MAX` (32), LRU by Map insertion order.
  - **`acquireTreeState(key)`** returns the stored state or a new one with `section:gator` expanded. `cleanRepoKey` accepts a 1–128 character string.
  - **No key:** a mount without a key gets a transient state of its own and never reads or writes the map, so it never borrows another repository's state.
  - **Never the display name:** two registered repositories can share one.
  - **`_repoView.state`** is the active state, read through `treeState()`.
  - **`setSelectedFile(path)`** is the ONLY writer of the selected file: tree click, search-result click, Markdown link, default selection and the `applyRefresh` drop.
  - **Teardown keeps every state.** The old single `_treeState` / `resetTreeStateFor` (reset on every repository change) is gone.
! **Mount generation guard.**
  - **The counter:** `_mountGen` is incremented in `teardownRepoView()` (which also sets `_repoView.gen = null`) and again at mount (`_repoView.gen = gen`).
  - **`isCurrentMount(gen)`** requires the same `gen` and a connected container that still holds `#repo-file-list`.
  - **The rule:** every asynchronous listing path captures `gen` before awaiting. In `loadFileList(gen, …)` (success, error and catch) and `pollRepoFiles()` (which also re-checks `isPinnedView()`), nothing writes DOM, state, `files` or `lastFp` after the `await` unless `isCurrentMount(gen)`.
  - **Why:** without this, a late alpha response could change beta's view and state after a switch. `loadFile()` content writes still go to their captured element, which is detached once another view mounts.
! **Single-registration listeners.** `installSearchListeners()` runs synchronously at mount, not after the listing `await`. It registers exactly one search-box `input` handler (`_repoView.searchHandler`, debounce timer `_repoView.searchTimer`) and one `popstate` handler (`_repoView.popHandler`). `teardownRepoView()` removes both and clears a pending search. Before this, each mount added an `input` listener that was never removed, so one keystroke ran one search per earlier visit. The handlers read the latest listing from `_repoView.files` and pick the default document with `pickDefaultFile()`.
! **Live listing cache — `cacheGet()` / `cachePut()` / `cacheable()` / `renderListing()`.**
  - **Storage:** `_listingCache: Map<repoKey, {files, fp, items}>` holds the last canonical unfiltered `/files` array per key. It is browser memory only (never serialized) and holds no rendered HTML and no file content.
  - **Scope:** `cacheable()` is true only for a mount with a key and no `version`. A historical (`?version=`) mount neither reads nor writes the cache.
  - **Bounds:** `LIVE_CACHE_MAX_REPOS` (8) and `LIVE_CACHE_MAX_ITEMS` (20,000 total entries). `cachePut` drops a listing over the item budget (and any older entry for that key), and evicts least-recently-used entries but never the key being stored. `cacheGet` marks an entry most recently used.
  - **Writes:** only after a guarded successful response, from `loadFileList` or `pollRepoFiles`.
  - **Mount sequence:** on a cache hit, the mount calls `renderListing()` at once and sets `_repoView.fromCache = true`. `renderListing()` is the single first-render path, cached or fresh: choose the file, draw the tree, set `#repo-file-list.scrollTop` from the tree state, set `files` / `lastFp`, load the file, and bind the resize handle (once per mount).
  - **The guarded background `loadFileList` then:**
    - error body or failure with `fromCache` → keeps the cached tree, with no DOM write;
    - same fingerprint → no DOM write;
    - different fingerprint → `applyRefresh(files)`, which redraws while keeping expansion and scroll and drops a vanished selection;
    - no cache hit → `renderListing` (a first visit keeps "Loading files…" until then).
! **Explicit open — `GatorViews.repo.preselect(repoKey, path)`.** It is called only by the Charters view, immediately before `gatorNavToRepo()`. For a non-empty key and a string path of at most 400 characters, it (a) sets `acquireTreeState(repoKey).selectedFile = path` and (b) deletes that key's `_listingCache` entry; otherwise it does nothing.
  - **Why the cache entry goes:** with a cache hit, the mount's first `renderListing()` would run on the old listing and replace a path missing from it, such as a report created after the visit, with the default document. `applyRefresh()` then never loads content. With the entry gone, the first `renderListing()` runs on the fresh listing, and its ordinary restore rule loads the requested file.
  - **Fallback:** a path not in the fresh listing (deleted, or hidden by the listing policy) loads the default document, like any stale selection.
  - **Scope:** an explicit open owns the selection for that one next mount. Every other navigation keeps cache-first drawing and ordinary restoration. `renderListing()`, `applyRefresh()` and the cache functions are unchanged. `setSelectedFile()` remains the only writer inside a mounted view; `preselect` writes only the stored state of a repository that is not mounted.
  - **Pinned by** `tests/test_dashboard_ui/test_charters_view.py` (the new-report regression), with `test_repo_tree_cache.py` pinning the unchanged cache-first path.
  - **Scroll capture:** `teardownRepoView()` writes `#repo-file-list.scrollTop` into the tree state while that element is still connected and the mount is live (`gen !== null`). The shell tears down before clearing the slot; the mount's own idempotent teardown records nothing.
  - **Inactive views are still not live:** only data is cached, never DOM, timers or listeners.
! **Debug seam:** `__gator_debug.sidebar` returns a fresh plain object `{repoName, repoKey, expandedDirs: [...], selectedFile, scrollTop}` from `_repoView`, never the map or a `Set`. `__gator_debug.listingCache` returns a fresh `[{repoKey, items}]` in LRU order (oldest first): keys and sizes only.
! The listing, file and search routes are addressed by **name** on the server (`scripts-dashboard.md`). Two same-named repositories therefore fetch the same listing even though their browser state is separate. The sidebar width and collapse preferences (`gator-sidebar-*:<name>` in `localStorage`) are also keyed by name: follow-up in `inbox.md`.
- **Pinned by** `tests/test_dashboard_ui/test_repo_tree_cache.py` and `test_harness.py` (debug seam).
! Encode file paths per segment so separators retain namespace meaning.
! Render untrusted text as text or through the syntax renderer; do not interpolate repository content into executable markup.
! **No Docs mode.** `GatorViews.repo(data, container, repoName, version)` has no `filter` parameter: the Docs view is the repository-independent `GatorViews.docs` (`views/docs.js`), which reads the shipped documents from the package. The Repo tree still shows `.gator/docs/` (Markdown and HTML) like any other `.gator/` folder.

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

### GatorViews.audit() / showSessionModal() — Audit view
File: src/gator_command/scripts/dashboard/views/audit.js
File: src/gator_command/scripts/dashboard/dashboard.js
Render session evidence and request source-qualified drill-down content.
<- audit/repo session panels
-> audit/session endpoints
! Preserve `source_kind` and repository identity through drill-down; never fetch a same-named file from a different source.

### GatorViews.updates() — Updates view
File: src/gator_command/scripts/dashboard/views/updates.js
Render installed/latest version state and request an explicit upgrade.
<- updates route
-> check and upgrade endpoints
! Checking and upgrading are visibly separate actions; failure output remains visible after restart attempts.

### GatorViews.docs() / showDoc() / select() (repo-independent Docs view)
File: src/gator_command/scripts/dashboard/views/docs.js
The Docs view: the shipped Gator HTML documents, from the installed package, the same list for every repository. A `nav.repo-sidebar.docs-sidebar` (`aria-label="Gator documents"`) lists `DOCS` in order with reader-friendly labels (library reading order: Gator overview, What Gator can do, Gatorize a repo, Start a session, "Asking for a Gator doc", "Gator loop", "Gator loop extras" (its copy button has no channel here and falls back to manual copy, like Start a session), "Pre-commit checks" (Docs only, placed after the Welcome topics because `test_every_shipped_document_is_served_and_listed` pins them first), then "Charter formation process", "Charter schema", "Code migrations"; deliberately not Welcome's tab order. "Asking for a Gator doc" is labelled as the capability so it is not read as a description of the Docs library itself); `.repo-content.docs-content` holds one `iframe.repo-iframe.docs-frame` (`sandbox="allow-scripts"`, `title` = label) inside `.repo-iframe-wrapper`. Reuses the repo-browser classes so the `.route-repo` flex chain sizes it.
! **Product intent (Architect):** Docs is Gator's comprehensive documentation library, what someone coming from docs.python.org expects: the same everywhere and never a per-repository collection. Repository-specific understanding belongs in `.gator/blueprints/`, the charters and the other `.gator/` surfaces, not in Docs.
<- `showView("docs")` (always available; no repository needed)
-> `GET /api/welcome/docs/<doc>` (see `scripts-dashboard.md` → `read_welcome_html()`), or the `srcdoc` property from `window.GATOR_WELCOME_DOCS` in a snapshot (missing entry → `p.docs-status` notice). No repository API calls, no storage, no history calls.
- **State:** module-local `selectedDoc` (default `gator-overview.html`) survives reopening Docs while the page stays loaded; the active button gets `.active` and `aria-current="page"`. A click on another entry replaces the frame; a click on the active entry does nothing.
! Every `DOCS[i].doc` must be in `WELCOME_DOC_NAMES`; otherwise the frame shows the route's 404 body. Adding a document = file in `templates/gator-starter/docs/` + name in `WELCOME_DOC_NAMES` + entry in `DOCS`.
! The frame sandbox is exactly `allow-scripts` (same TRIPWIRE as Welcome). The Start-a-session copy button has no Welcome channel here; after its 1.5 s timeout the document shows its own manual-copy text, by design.
! The DOM is built with `createElement`/`textContent` only: no document text or label is interpolated into HTML.
- **Pinned by** `tests/test_dashboard_ui/test_docs_view.py`.

### GatorViews.charters() / renderResult() / renderIntro() / renderUnavailable() / openFile() / toLogical() / renderHealth() / renderCode() / mark() / figure() / section() / sizeChart() / coverageChart() / modulesChart() / rankedChart() / largestChart() / charterSizesChart() / guideLegend() / donutChart() / moduleSummary() / folderOf() / repairPrompt() / repairBlock() / shortName() / sizeBand() (Charters view)
File: src/gator_command/scripts/dashboard/views/charters.js
The Charters page, in three tabs. The report pages use the **Cumberland reading style** of the Welcome documents, drawn in the view rather than in a frame (Architect choice: keep the page live and interactive): a `.charters-doc-lede` sentence, ruled `h2.charters-doc-title` section headings and `figure.charters-figure` cards holding inline-SVG charts. **Overview** shows the charter report's health above the charter sync check. **Code** shows where the code is by charter. **Features** is one sentence: a feature map is planned for a later release.
<- `showView("charters")` (repository-scoped; see the shell entry's Charters item)
-> `GET` / `POST /api/repo/<encoded name>/charter-sync` (see `scripts-dashboard.md` → `_handle_charter_sync_post()`); `GET` / `POST /api/repo/<encoded name>/charters-report` (see `scripts-dashboard.md` → `dashboard/charters_report.py`); `GatorViews.repo.preselect()` + `window.gatorNavToRepo()` for "Open file" (the ranked-chart rows)
- **Tabs (Welcome pattern):** `div.gator-tabbar.charters-tabbar` > `[role=tablist][aria-label="Charters sections"]` > `button.gator-tab.charters-view-tab#charters-view-tab-<key>` (never `#charters-tab`, the sidebar item), and `section.charters-panel#charters-panel-<key>[role=tabpanel]`. `aria-selected`, roving `tabindex`, `hidden`; click, Left/Right (wrapping), Home and End. Module-local `selectedTab` (default `overview`) survives remounts and resets on page load. `.charters-panel[hidden]` must stay `display: none`, because `.charters-panel` sets `display: flex`. **The tab bar is sticky**, like the Welcome tabs: `.charters-tabbar` is `position: sticky` with `top` and `margin-top` of minus `--space-6` plus matching `padding-top`, so it pins to the very top of the scroll container (`#view-slot`, or `#main-shell` on narrow screens) without moving at rest, on an opaque `--color-bg` with `z-index: 2` so content passes under it. Refresh report rides along. Changing `#view-slot` padding means changing these offsets.
- **Charter report (Overview `section.charters-health[data-report]`, Code panel):**
  - One GET on mount. `report` + `current` paints and sends no POST. `report` + `stale` / `unknown` paints the cached figures labelled "▲ Stale" / "? Not verified", then sends one POST. `none` shows "Building the charter report…" and sends one POST. `unavailable` shows the server's message and hides "Refresh report".
  - **At most one automatic refresh per mount** (`autoRefreshed`), even when the refresh itself answers `stale`. "Refresh report" (`.charters-refresh`, `aria-busy` while running) is the only other way to refresh. It sits right-aligned in the tab bar (`.charters-tabbar`, flex), not in a panel, because the report feeds both Overview and Code; the sync check keeps its own "Run charter sync check" button in Overview. Nothing is timed.
  - A failed refresh or read shows `p.charters-health-error[role=alert]`: "Refresh failed: <error>." plus "Figures shown are from <time>." or "No figures are available yet." The painted figures stay. A late initial GET never replaces figures a refresh already painted (`shown`).
  - Overview, in order: the lede ("N charters describe X of Y source files; Z have no charter yet.", or the no-charters sentence), the provenance line, "Charters by size" (`data-figure="charters"`, `charterSizesChart()`: every charter, longest first, as the same ranked chart as "Largest files" with a 300-line guide, ▲ over 300, ■ over 600; it doubles as the charter list and each row opens its charter), "Total charters size as percentage of codebase size" (`data-figure="size"`, `sizeChart()`: a 0–10% or wider axis, the dashed target band labelled "target 3–6%", a dark marker at the value; the caption gives charter lines, percent and product lines in words, the band mark "✓ In range" / "▲ Below range" / "▲ Above range", the target and the documented-function count), then "Coverage" (`data-figure="coverage"`, a donut of covered and uncovered source files). A partial report lists its problems.
! **Donuts (`donutChart(parts, center, unit, ariaLabel, key)`, `div.charters-donut[data-donut=key]`)** are the one part-to-whole form on the page, used for coverage (`coverage`), the sync check (`sync`: charters current vs needing review) and recent commits (`commits`: commits in step vs changed governed code without a charter update). Parts start at twelve o'clock with 2px gaps; a non-zero part is never thinner than a visible sliver (taken from the largest part); the headline percent is in the middle; a legend list gives every count in words (swatches `aria-hidden`). Teal for the good part, amber `#d4880f` for review / out of step, gray for "without a charter".
  - `.charters-provenance`: the freshness mark plus "From the charter report, <relative time> · revision <rev>". `details.charters-measured` "How measured" (summary class `charters-measured-summary`) lists the report's `measurement` sentences.
  - Code, in order: the lede "N lines of product code in M source files."; "Largest files" (`data-figure="largest"`, `largestChart()`, after the mock-up): bars on a light track, a dashed 1,500-line guide crossing every row, and size bands by fill **and** a symbol after the value (teal; ▲ amber over 1,500; ■ red over 4,000; `FILE_GUIDE`), with a legend caption. Both ranked charts share `rankedChart(rows, guide, ariaLabel, rowClass, ctx)` and `guideLegend()`. Labels come from `shortName()`: the file with its folder (generic folders such as `scripts/` skipped) plus "· starter" / "· enterprise" for shipped copies; the full path is in the hover text and `aria-label`.; then "Lines of code covered by each charter" (`data-figure="modules"`, `modulesChart(code, cov)`): one horizontal bar per charter, longest first, then "No charter" in gray, each row with its name and value as text and, under the bar, `moduleSummary()`: the covered files by name when there are at most 6 (`shortName()`, comma-separated), otherwise their folders (last two path segments) with a count each, the 4 largest plus "+N more", and "(first 50 files)" when the report capped the list; cut at 72 characters. "No charter" uses the coverage list of uncovered files. The full-row `<title>` hover gives "name: N lines in M files" and every listed path. More than 24 charters fold into "Other charters (N)" (no file line). There is no "Files without a charter" list in Code (uncovered files belong to Overview).
! **Ranked-chart rows are the "Open file" links:** each `g.charters-link-row` (plus `charters-file-row` or `charters-charter-row`) is `role="link"`, `tabindex="0"`, with `aria-label` "Open <path>, N lines[, band]", and opens the file on click, Enter or Space through `openFile()`; the chart is `role="group"`. The bands (`FILE_GUIDE` 1,500 / 4,000 lines; `CHARTER_GUIDE` 300 / 600, the sketch's proposed charter limit and twice it) are reading guides fixed in the view, not enforced thresholds (thresholds and their tracked setting are a later release); move them to that setting when it exists.
! Charts are inline SVG built with `createElementNS`; every other chart is `role="img"` with an `aria-label`, every mark that carries a value has `<title>` hover text, and every value also appears as text (labels or caption), so the drawing is never the only carrier. One series per chart in `#0e9aa6` (the Welcome documents' validated chart teal; `--teal-dark` fails the dataviz chroma floor), the neutral "No charter" gray `#9ca3af` always with its own label. The largest-files bands add amber `#d4880f` and red `#d94040` (validated with the teal; amber's contrast warning is met by the visible value and symbol on every row). On a phone the charts scale down as a whole, so their labels get small; there is no horizontal scroll. No legend: each chart has one series and the heading names it.
  - `data-report` is `pending` → `current` | `stale` | `unknown` | `none` | `unavailable` | `failed` | `snapshot`; `data-refreshing` is set while a refresh runs.
! **One POST at a time per mount (`enqueuePost`).** A report refresh and a sync run take the same server `_repo_action` lock, so concurrent POSTs would give 409. Both go through one promise chain. A "Run charter sync check" click during a refresh waits for it, and the button shows "Checking…" at once. Pinned by `test_a_sync_run_waits_for_an_inflight_refresh`.
! Report-area class names never reuse the sync section's (`.charters-error`, `.charters-count`, `.charters-band`), because the sync tests and the page address those by class.
- **Charter sync check states** (under its own "Charter sync" heading; there is no per-group "Needs attention" list, because nobody opens a report per group):
  - **Loading:** the lede and button render at once. One GET with `cache: "no-store"`, under a mount-generation guard (`mountGen` plus `root.isConnected`); `root.dataset.loaded` goes from `pending` to `true`.
  - **First visit:** `{state: "none"}` → the sketch's first-visit text, which says the check does not edit code or charters and writes to `.gator/artifacts/`.
  - **Result:** `current` or `needs-review` → `renderResult()`:
    - the band: the label "Charter sync", a state **word** ("Current" / "Needs review") with a decorative dot, and "Checked <relative time>" with the absolute time, revision and uncommitted note in `title`;
    - the server's `headline` sentence;
    - the `sync` donut ("N charters current" / "N charters need review", percent current in the middle), then `p.charters-missing` "N source files have no charter.";
    - **repair hand-off** (`needs-review` only, `repairBlock()`): "To fix these charters, give this prompt to your agent session:", the prompt in full (`p.charters-prompt-text`, selectable), and "Copy prompt" (`navigator.clipboard.writeText`; "✓ Copied", or a select-and-copy fallback message, in an `aria-live` status). `repairPrompt()` is one line: the saved report's path (which holds the repair sketch), up to 8 charter names from the finding groups that have a `charter_path` and whose `kind` is not advisory (`function-gap` or `cross-cutting-suspect`; an advisory-only group names no drift, #105; then "and N more"), "compare each charter with its code and follow the report's repair sketch", "move dated history (release notes, review rounds, resolved findings) out of the charter, per the charter README" (the README's "what does not belong" rule; nothing measures it yet), "Do not add one heading per function; document seams, group related helpers, or use the Internal line", "Change charters only, not code", and "Show me the charter changes before you commit." It never carries a token or secret, and the Dashboard itself still edits nothing;
    - "Recent commit coverage" (its own `section.charters-commits` with a `charters-doc-title` heading, the same level as "Charter sync"): the server's `reason` when there is one, otherwise the `commits` donut in a figure card (percent in step in the middle) with a caption explaining "in step";
    - no saved-report line or "Open report" button; the report stays in `.gator/artifacts/`.
  - **Running:** the button is disabled with "Checking…" and `aria-busy`. The displayed result stays.
  - **Failure:** a non-2xx, a network error, or a 2xx that is not a result → `p.charters-error[role=alert]` "…failed: <server error>. The previous result is unchanged." The body is not touched. A GET failure shows the first-visit text plus the alert.
  - **Unavailable:** the server's `unavailable` hides the button and shows its message.
  - **Snapshot:** `window.GATOR_SNAPSHOT` hides both buttons and shows a live-Dashboard notice in the sync body, the health area and the Code panel, with no fetch (`data-report="snapshot"`).
! The browser never paints a result the server did not return: `renderResult()` runs only on a 2xx whose `state` is a result state.
! **Read/run ownership.** Two requests can paint the body: the initial GET and a run's POST. The mount guard (`current()`) only covers navigation, so it does not order them. The rule is that the initial read owns the body only until a run starts: the click handler sets `readOwnsBody = false` before its POST, and every initial-read callback that paints (result, no record, read failure) checks `readMayPaint()` (`current() && readOwnsBody`). A late initial response therefore never replaces a run's result or adds a read error after it. Only `root.dataset.loaded` still moves to `true`. The button stays enabled while the read is pending, so a run never waits on it. Pinned by `test_late_initial_read_never_replaces_a_run` (late no-record, older result and failure), which fails if the handoff is removed.
! The DOM is built with `createElement` / `textContent` only. Server text (headline, labels, messages, paths, reasons) never enters markup.
! "Open file" (the ranked-chart rows) maps the repo-relative path to the Repo view's logical path (`toLogical()`, the server's `parse_logical_path` namespaces: `.gator/` content without the prefix, `gator-command/` as it is, and every other path under `source/`, so a source file opens itself rather than falling back to the default document). Pinned by `test_open_file_hands_repo_the_right_namespace` (all three namespaces) and `test_real_run_then_open_file_over_a_cached_listing` (a real report's file is selected in the tree). They call `GatorViews.repo.preselect(repoKey, logical)`, then `gatorNavToRepo(repoName, repoKey)`, so a just-created report is selected over a stale listing cache (see the Repo entry's explicit-open TRIPWIRE).
! Colour is never the only cue. Every state and count carries a word, and every dot, symbol (`.charters-mark-symbol`, followed by a real space and the word) and bar is `aria-hidden`.
- **Pinned by** `tests/test_dashboard_ui/test_charters_view.py` (sync tests, and the report tests: a cache hit without a POST, exactly one refresh when stale, a failed refresh keeping figures, first build and unavailable, keyboard tabs with the Code and Features panels, and POST serialization).

### GatorViews.welcome() / applyTopic() / selectTopic() / ensureFrame() / bindCopyListener() / isCopyRequest() / handleCopyRequest() / replyCopy() (Welcome HTML documents)
File: src/gator_command/scripts/dashboard/views/welcome.js
The Welcome workspace: six topics (Start a session with Gator · Gator overview · What Gator can do · Gator docs · Gator loop · Gatorize a repo; the session topic is first and the default, for its copy-prompt button) in the shared main-pane tab bar. Each topic body is a shipped standalone HTML document in a sandboxed iframe.
<- `showView("welcome")` (live landing view from `init()`, the `#brand-home` logo button, and Back/Forward)
-> `GET /api/welcome/docs/<name>` (see `scripts-dashboard.md` → `read_welcome_html()`), or `window.GATOR_WELCOME_DOCS[name]` in a snapshot. No storage, no console output, no history calls.
- **Tabs:** `div.gator-tabbar.welcome-tabbar` > `[role=tablist][aria-label="Welcome topics"]` > six `button.gator-tab.welcome-tab[role=tab]` (`#welcome-tab-<key>`, `aria-controls`), and six `section[role=tabpanel][tabindex=0]` (`#welcome-panel-<key>`, `aria-labelledby`) in `.welcome-body`. `applyTopic()` writes `aria-selected`, roving `tabindex` and `hidden` only when they differ. Click selects; Left/Right (wrapping), Home and End select and focus. A switch never re-renders or calls the shell; it fetches only through `ensureFrame()` on a topic's first selection in a mount.
- **Topic state:** module-local `selectedTopic` (default `session`, the first tab). It survives reopening Welcome (logo, Back/Forward, Refresh) while the page stays loaded and resets on a fresh page load. It is never put in shell history (`sub` stays null).
- **Frames:** `TOPICS[i].doc` names each document. The `loop` topic's `gator-loop.html` is the same document the Loop workspace's Help tab shows (`views/loop.js` `LOOP_HELP_DOC`), so Welcome and Loop help cannot describe different products. `applyTopic()` calls `ensureFrame(selectedTopic)`, which creates `iframe.welcome-frame` once per mount in the empty tabpanel. It sets `sandbox="allow-scripts"` and `title` = the tab label, plus `src` = `/api/welcome/docs/<doc>` live, or the `srcdoc` property from `GATOR_WELCOME_DOCS` when `window.GATOR_SNAPSHOT`. A missing or `null` snapshot entry gives `p.welcome-doc-status` (text notice naming `.gator/docs/<doc>`) instead. `frames` (module-local, reset per mount) holds them. A frame is never re-created or re-pointed while the mount lives, so revisiting a topic does not reload it. Reopening Welcome is a new mount.
- **Does not own document content:** layout, the overview's hero mark, and images live in the documents themselves (see `scripts-dashboard.md` → Document content rules). The view never styles or measures frame content.
! TRIPWIRE: every Welcome frame is sandboxed exactly `allow-scripts` (opaque origin); never add `allow-same-origin`, forms, popups, or top navigation. Document HTML never enters the Dashboard DOM: live frames use `src`, and snapshot frames use the `srcdoc` DOM property, never an attribute string. Documents are not navigation controllers: no tab switching, repository context, or endpoint access from a document.
- **Copy action:** `bindCopyListener(root, frames)` runs on every mount.
  - It removes the previous mount's `message` listener and installs one bound to this mount. That listener removes itself once its root is detached.
  - It calls `handleCopyRequest(event.source)` only when all of these hold: `frames.session` is a connected `IFRAME`; `event.source === frames.session.contentWindow`; `event.origin === "null"`; and `isCopyRequest(event.data)`.
  - `isCopyRequest(event.data)` requires a non-null object with prototype `Object.prototype`, exactly three own keys, `type === "gator-welcome"`, `v === 1`, and `action === "copy-session-prompt"`.
  - `handleCopyRequest()` writes `SESSION_PROMPT` with `navigator.clipboard.writeText`. `replyCopy()` then posts `{type:"gator-welcome", v:1, action:"copy-session-prompt-result", ok}` to that source only, plus `reason: "unavailable"` (no Clipboard API) or `"denied"` (rejected) when it fails. The target origin is `"*"` because an opaque origin cannot be named and the reply carries no secret.
  - The visible manual-copy fallback lives in the document (`start-a-session.html`), beside the already visible prompt.
! TRIPWIRE (copy protocol): only this mount's Start-a-session frame is accepted. Messages from the page, an unrelated frame, another Welcome frame, a stale frame (the previous mount's iframe, even if re-attached), a non-`"null"` origin, an unknown version or action, an extra key, an array or a string cause no clipboard write, no reply, and no topic, history, focus or network change. The prompt is never received from, sent to, logged by or exposed through a message: the reply has no prompt text. Never widen the accepted shape or sources without a new review.
! TRIPWIRE: `SESSION_PROMPT` ends with the fallback for a session outside a governed repository (2.38.0): "If gator init reports that this is not a governed repository, run gator --explain, read the documents it lists, and ask me which repository to work in." It must equal the `<pre id="session-prompt">` text in `start-a-session.html` and the prompt in `gatorize-a-repo.html` (pinned by `tests/test_welcome_docs.py` and `test_welcome_ui.py`).
! TRIPWIRE: `SESSION_PROMPT` is the exact vendor-neutral text, as **one line** (a pasted newline can submit early in terminal agent UIs). It names no vendor and no layout-dependent path (never `.gator/.includes/GATOR_INIT.md`): `gator init` reports the canonical path itself. It is never logged, stored, put in `data-*`, or put into history state.
! Welcome never calls `setActiveRepo` / `clearActiveRepo` and works without a registered repository or an active Loop.
- **Pinned by** `tests/test_dashboard_ui/test_welcome_ui.py`. Tests read frame content through `page.frame_locator(...)`, which waits for the (src or srcdoc) document to load; scanning `page.frames` right after the iframe appears races on slow runners (Windows CI run 38101334192).

### GatorViews.settings() — Settings view
File: src/gator_command/scripts/dashboard/views/settings.js
Read-only commit policy: a `table.settings-policy-table` with the two fixed categories (Charter integrity: Block, with the Architect-only exact-change approval as the escape hatch; Dangerous patterns: Pause, each with its meaning), then `table.settings-repo-table` with one row per repository (`tr[data-repo]`, `td.settings-policy`, `td.settings-policy-note`) from `window.GatorCommitPolicy.posture()` over the Fleet payload, so an inaccessible repository shows "Unknown" and a not-gatorized one "Not gatorized", exactly as in Fleet. No `select`, no request.
<- settings route
! Depends on `views/fleet.js` loading first (live `dashboard.html` and the snapshot both load it first); without it every row falls back to "Default". Settings has no control; the only Commit policy control is Fleet's machine-local Strict/Warn dropdown, which is never offered where Enterprise manages the repository. Pinned by `test_settings_commit_policy_is_read_only` (`test_fleet_layout.py`).

## Before Changing This Module

- Confirm the backend wire schema and empty/error states.
- Exercise keyboard/mouse navigation and narrow/wide layouts.
- Run Playwright tests for mutations, file browsing, CSP liveness, iframe isolation, and preview controls.
- Keep the UI dependency-free unless the product architecture explicitly changes.

## Connections

-> [Dashboard Server](scripts-dashboard.md) - APIs, security, and content policy
-> [Session Archaeology](scripts-session-archaeology.md) - evidence identity and provenance
-> [Contracts](contracts.md) - Cumberland HTML compatibility
-> [Dashboard Shell](scripts-dashboard-shell.md) -- navigation, workspace tabs, requests and styling every view relies on
-> [Loop Workspace View](scripts-dashboard-loop-ui.md) -- the Loop workspace, a sibling view
