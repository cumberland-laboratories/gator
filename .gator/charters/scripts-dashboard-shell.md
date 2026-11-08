# Charter: Dashboard Shell

**Covers**: `src/gator_command/scripts/dashboard/dashboard.html`, `src/gator_command/scripts/dashboard/dashboard.css`, `src/gator_command/scripts/dashboard/dashboard.js`, `src/gator_command/scripts/dashboard/workspace.js`, `src/gator_command/scripts/dashboard/*.png`

## Owns

The framework-free page around every view: navigation and history, workspace tabs, same-origin requests, Paper tokens and the responsive layout. The views themselves are in [Dashboard Views](scripts-dashboard-views.md) and [Loop Workspace View](scripts-dashboard-loop-ui.md).

- The framework-free dashboard shell, navigation, responsive layout, and browser-side routing.
- Browser requests to the local dashboard server.

## Does Not Own

- Route authorization, path containment, filesystem access, or data computation; see [`scripts-dashboard.md`](scripts-dashboard.md).
- Governance business rules.
- Cumberland document-template styling; see [`contracts.md`](contracts.md).
- The views; see [Dashboard Views](scripts-dashboard-views.md) and [Loop Workspace View](scripts-dashboard-loop-ui.md).

---

### navigate() / showView() / renderView() / restoreShellState() / applyShellEntry() / setActiveRepo() / clearActiveRepo() / shellUrl() / parseShellUrl() / recordShell() / formatDocumentTitle() / updateDocumentTitle() / window.GatorShell
File: src/gator_command/scripts/dashboard/dashboard.js
Own browser history, selected repository/view state, and dispatch into view modules.
<- sidebar, topbar, `window.gatorNavToRepo` (fleet rows), popstate
-> `views/*`
! URL state and visible selection stay synchronized; refresh re-renders the same repo/view rather than silently returning home.
! **Shell-owned history.** `dashboard.js` is the only owner of Dashboard history entries, for every view.
  - **State shape:** `{gatorDashboard: 1, view, repo, repoKey, sub, ctx}`, built by `shellState(sub)`. `ctx` is the opaque id of the workspace context shown, or null before hydration and in snapshots. `isShellEntry` accepts it absent, null or a string. Every entry also carries the canonical URL of the active context (see "Shell URL" below). Snapshot entries stay state-only (`file:` URLs). `sub` is `null` except for Loop entries: `cleanSub()` keeps exactly `{view: create|history, mode: create|inspect, loopId}`. **No token, prompt text or artifact content ever enters a state object.**
  - **`navigate()` versus `showView()`:** `navigate()` = `showView()` plus `recordShell("pushState")`. It is used by the sidebar click handler and `gatorNavToRepo`. `init()` lands through `applyShellEntry()` and then `recordShell("replaceState")`. `doRefresh` calls `showView` and pushes nothing. `showView(name, extra, repoKeyOverride, opts)` is a renderer only. It passes `opts.initialSub` as the fifth argument to `views.loop`, and records `state.mountedLoopKey` (the repo key a mounted Loop view uses; `undefined` otherwise).
  - **`window.GatorShell`:** `pushSubState(sub)` pushes only when the active view is Loop and no restoration is running. `replaceSubState(sub)` replaces the current entry (Loop only). `isRestoring()`.
  - ! **Shell URL — `shellUrl(view, repo)` / `parseShellUrl()` / `recordShell(method, sub)`.**
    - **Canonical forms** (`shellUrl`):
      - `?repo=<name>` for the Repo view (the legacy link, still produced by `gator dashboard --repo`);
      - `?repo=<name>&view=<view>` for any other view with a repository;
      - `?view=<view>` without a repository;
      - no query (the page path) for Welcome without a repository.
    - **What stays out of the URL:** Loop `sub` and `repoKey` stay in history state only. The URL never carries a token, prompt or path.
    - **Parsing:** `parseShellUrl()` returns `{repo, view}`. A `view` outside `VIEW_META` and an empty `repo` are null.
    - **Recording:** `recordShell` is the only writer of shell entries: `navigate`, `GatorShell.push/replaceSubState`, the landing and the unregistered fallback. With `window.GATOR_SNAPSHOT` it omits the URL argument (state-only).
    - **The server never reads `view`.** The root route strips the query, and `_parse_request` tolerates it (see `scripts-dashboard.md`).
    - **`views/repo.js`** still pushes its own entries, including `?repo=<name>&q=<query>`. That URL is valid under this contract (no `view` means Repo).
  - **Landing view (`init()`):** it builds an entry from `parseShellUrl()`.
    - **Choosing the view.** A missing `view` keeps the legacy meaning: `?repo=<name>` → that Repo view; otherwise a snapshot (`window.GATOR_SNAPSHOT`) → Fleet (a snapshot is a fleet report); otherwise → **Welcome** (the front door, opening on the "Start a session with Gator" topic). `?view=<view>` (with or without `repo`) lands on that view.
    - **Reload or duplicated tab.** When `history.state` is a valid shell entry for the same view and repository name, its `repoKey` (which disambiguates same-named repositories) and `cleanSub(sub)` are reused, so a Loop tab and selection survive a reload.
    - **Dispatch.** The entry goes through `applyShellEntry()`, the same hydrate → dispatch path as Back/Forward. **An unregistered `?repo=` therefore lands on Fleet with the "no longer registered" notice**.
    - **Recording.** The landing entry is recorded with `recordShell("replaceState")`, so Back from the first navigation returns to the landing view.
    - the guard below runs before any of this and is unchanged.
  - ! **Navigation during load wins.** `showView()` increments `viewRenders`; `init()` compares it across its `/api/data` await. If anything rendered a view meanwhile (sidebar click, `gatorNavToRepo`, popstate), `init()` re-renders that view with the loaded data (`showView(activeView, activeRepo, activeRepoKey)`, like `doRefresh`) and skips both the landing view and the landing `replaceState`. Before this, a navigation made before `/api/data` returned was replaced by Welcome.
  - **Title-only header — `updateTopbar(name)`:**
    - It writes only `#topbar-title`, through `textContent`, from `VIEW_META[name].title`. `#topbar-subtitle` stays in the DOM, `hidden` and never written; the `VIEW_META.*.subtitle` fields are unused (follow-up: remove both).
    - **Repo branch tools:** the branch-history picker (`#branch-version-label`, `#branch-history-btn`, `#branch-history-dropdown`, with unchanged ids and click wiring) lives in `span#topbar-repo-tools` in `#topbar-right`, before `#repo-search-input`.
      - `showView()` empties and hides it on every render.
      - Only the Repo branch with a known `branch` fills it, from static markup only: no repository name or branch text, which the sidebar context shows. It is then un-hidden.
      - The dropdown is positioned against it (`.history-dropdown`: `right: 0`).
      - Before Paper, this markup, with the name and branch, was written into the subtitle through `innerHTML`.
  - **Welcome:** `welcome` is a `VIEW_META` view ("Welcome to Gator!") shown on a live load without `?repo=` (see Landing view), and reached from the `#brand-home` logo button (`aria-label="Open Welcome"`; `navigate("welcome")`; `aria-current="page"` while it is shown) and from Back/Forward. Its `showView` branch never calls `setActiveRepo` / `clearActiveRepo`, and its entries carry `sub: null` (`cleanSub` stays Loop-only).
  - **Repository context:** `setActiveRepo(name, key)` (extracted from the `repo` branch) sets `activeRepo` / `activeRepoKey`, calls `renderSidebarContext()`, and un-dims Repo, Commits (`#history-tab`), Loop and Charters (`#charters-tab`) through `setRepoItemsEnabled(true)`. `clearActiveRepo()` is its inverse: the empty card, and those items dimmed.
    - **Context card:** `renderSidebarContext()` rebuilds `div#sidebar-context[aria-live="polite"]` (under `#sidebar-brand`) from the shell state and the matching Fleet record (by `repo_key` when known, else by name).
      - **With a repository:** `.ctx-name` holds the registry display name, then `.ctx-meta` holds `span.ctx-branch` (`branch`) · "Gator " `span.ctx-version` (`cli_version`). A missing field is omitted, and the meta line is dropped when both are missing (for example, a navigation made before `/api/data` returned; the late-data re-render fills it). Both lines truncate with an ellipsis, so each carries a `title` with its full text: `.ctx-name` the display name, `.ctx-meta` its whole text ("<branch> · Gator <version>"). The empty state has no `title`.
      - **Empty state** (also the static HTML before any script runs): `.ctx-name.ctx-empty` "None selected" and `.ctx-meta` "Choose one in Fleet".
      - **`doRefresh`** re-renders the card from the fresh data.
      - ! Every value is set with `textContent` / text nodes (`contextEl()`), never markup.
      - Mono applies only to the branch and version fragments.
      - The card is hidden at ≤768px, where the strip tab already names the repository.
    - **Repo label:** the Repo item is the static "▸ Repo" label. The "▸ <name>" label and `setRepoTabLabel()` are gone, and so is the item's inline 28px indentation.
    - **Unavailable items:** `setRepoItemsEnabled(enabled)` toggles `dimmed` together with `aria-disabled="true"` and `title="Choose a repository in Fleet first"` on `#repo-tab`, `#history-tab`, `#loop-tab` and `#charters-tab`; the static HTML starts in that state. This is the non-colour cue for the gray-500 dimmed text.
    - **Charters item:** `button.sidebar-item#charters-tab[data-view="charters"]` ("§ Charters") sits directly after `#loop-tab` and before the Knowledge group label, with the same left edge, icon/label treatment and active rail. It is gated exactly like Loop: dimmed with the non-colour cue until a repository is selected, ignored by the sidebar click handler while dimmed, and also refused by the handler's no-repository guard (`repo`, `loop`, `charters`). `VIEW_META.charters` ("Charters") makes it a valid URL `view`, shell-history entry and workspace-context view, and gives the title `Gator · <repo> · Charters`. Its `renderView` branch shows the Loop-style "Select a repo from the Fleet view first." placeholder without a repository; otherwise it calls `GatorViews.charters(data, slot, repoName, repoKey)`.
    - **Welcome item:** `button.sidebar-item#welcome-nav[data-view="welcome"]` ("⌂ Welcome") is the first Overview item. It is never dimmed, it navigates through the ordinary sidebar click handler, and it gets `.active` from `showView()`. The `#brand-home` logo stays a second Welcome entry, with its `aria-current`.
    - **Pinned by:**
      - `tests/test_dashboard_ui/test_paper_shell.py`: `test_context_card_shows_repository_and_empty_state`, `test_context_card_renders_text_literally`, `test_context_card_hidden_when_narrow`, `test_welcome_sidebar_item_navigates` and `test_unavailable_items_carry_non_colour_cue`;
      - `test_docs_view.py`: the `aria-disabled` / `title` toggle;
      - `test_loop_workspace.py` / `test_welcome_ui.py`: the card name follows Back/Forward and landing;
      - `test_loop_workspace.py` `test_commits_tab_is_gated_like_loop` (an existing test): a dimmed click still does nothing. It is now a forced click, because an `aria-disabled` item fails Playwright's actionability check, and it asserts `aria-disabled` first. The sidebar click handler ignores a dimmed item, so Commits, like Loop, does nothing until a repository is selected; without one the view would only show its "Select a repo" placeholder. **Docs is always enabled**: it is repository-independent (`GatorViews.docs`), never dimmed, not guarded by the sidebar click handler, and its `showView` branch needs no active repository and shows no repo search box.
  - **Restoration:** a single `popstate` handler → `restoreShellState(entry)`, run under the `restoring` flag (cleared in `finally`). Step 1 is in `restoreShellState`; steps 2–3 are `applyShellEntry(entry)`, which `init()` also uses. **Before step 1:** when `entry.ctx` names a workspace context that is still open and is not the active one, that context is selected (`GatorWorkspace.select`, no push). Back therefore undoes a strip selection. Otherwise (no `ctx`, or a closed context) the entry is applied to the active context, whose inactive duplicate for the same repository is dropped.
    1. **Validate:** `isShellEntry` (marker, a `VIEW_META` view, `repo` null or a string). Anything else is ignored.
    2. **Hydrate the repository before any dispatch.** The fleet entry matching name and recorded key, else name only, is authoritative → `setActiveRepo`. An unregistered repo → `clearActiveRepo`, Fleet with a `.shell-notice` "That repository is no longer registered.", and `recordShell("replaceState")` to Fleet (URL `?view=fleet`). A null repo → `clearActiveRepo`.
    3. **Dispatch:** a Loop entry for the already-mounted Loop view of the *same* repo key → `views.loop.restore(sub)` (no remount). Otherwise `showView(view, repo, activeRepoKey, {initialSub})`, so a repository change always remounts.
  - **`views/repo.js` entries:** `repo.js` still pushes its own search/file entries (`{view: "repo", repo, searchQuery|filePath}`, no marker) and applies them with its own controller-scoped `popstate` listener while mounted. The shell leaves such an entry to `repo.js` when that repo's Repo view is mounted (Docs no longer mounts `repo.js`). Otherwise it restores that Repo view, so Back never goes dead.
  - **No re-entrancy:** pushes are suppressed while restoring, and the restore paths call no pushing function.
  - ! **Browser-tab title — `formatDocumentTitle(view, repo)` / `updateDocumentTitle()`.**
    - **Formatter:** a pure function of the shell's `activeView` and `activeRepo`:
      - `Gator · Fleet` and `Gator · Welcome` never show a repository;
      - any other view with a repository is `Gator · <repo> · <Label>` (for example `Gator · alpha · Docs`, `Gator · alpha · Loop`);
      - otherwise `Gator · <Label>`.
    - **Labels:** `TITLE_LABELS` (`welcome` → "Welcome", `history` → "Commits"), else `VIEW_META[view].title`.
    - **Repository part:** the registry display name, truncated to `TITLE_REPO_MAX` (60) characters with "…". It is assigned through `document.title` (text). It never comes from repository content, a file path or a document.
    - **Single exit:** `showView()` is now `viewRenders++`, then `renderView()` (the former body) in `try`, then `updateDocumentTitle()` in `finally`. Every path that renders therefore sets the title: landing, `navigate()`, `doRefresh`, the late-data re-render, `restoreShellState()` and its unregistered-repository Fleet fallback. No other code assigns `document.title`. `views.loop.restore()` (no remount) keeps the same view and repository, so the title is already correct.
    - **Pinned by** `tests/test_dashboard_ui/test_workspace_tabs.py` (`test_document_title_follows_view`, `test_two_pages_distinct_titles_and_urls`).

### syncWorkspace() / hydrateWorkspace() / validateRepo() / workspace() · window.GatorWorkspace: configure() / load() / syncActive() / findByRepo() / active() / list() / readCache() / save() / sanitize() / overLimit() / sameRepo() / dropDuplicatesOf() / assign() / newId() / cleanRepo() / cleanKey() / cleanContextSub()
File: src/gator_command/scripts/dashboard/workspace.js
File: src/gator_command/scripts/dashboard/dashboard.js
The per-browser-tab list of workspace contexts `{id, repo, repoKey, view, sub}` and its session cache. A context is an optional repository plus the last view to restore for it.
<- `dashboard.js`: `syncWorkspace(sub)` from `showView()`'s `finally`, `recordShell()`, and the `views.loop.restore` branch of `applyShellEntry()`; `hydrateWorkspace()` at the end of `init()` (landing and late-data branches)
-> `sessionStorage` only
! TRIPWIRE: `workspace.js` never routes. It renders no view, never calls `history`, `showView` or `fetch`. `dashboard.js` stays the only router.
! **The active context is a recorded copy of the shell state, never a second authority.** `syncActive()` writes the shell's `activeView` / `activeRepo` / `activeRepoKey` (+ Loop `sub`) into the active context. `showView()` syncs with `sub: null`; the Loop mount's `GatorShell.replaceSubState` then records the real sub.
! **Before hydration nothing is written.** `syncActive()` and `save()` are no-ops until `load()`, so the landing never overwrites the cache before reading it.
- **`load(current, validateRepo)`**, after the landing or the late-data re-render, so a navigation during load still wins:
  1. Read the cache.
  2. Keep a cached context only if `validateRepo(repo, repoKey)` finds it in the current fleet data: by key when the record has one, else by name. It takes the registry's current name and key and never substitutes another repository. A repository-less context always survives.
  3. The active context is the cached one for the same repository, or (no repository) the cached active context when it was repository-less. Otherwise a new context is appended; at 12 contexts the last inactive one is dropped.
  4. Sync it from `current` and save.
- **One context per repository:** `sameRepo` matches by key when both are known, else by name. A cache with duplicates keeps the first. `syncActive` drops an inactive duplicate of the active context's repository (the active wins).
- **Storage contract:** key `gator.dashboard.workspace`, `sessionStorage` (per browser tab; never `localStorage`). Value `{"v": 1, "activeId", "contexts": [...]}`.
  - **Rejected whole:** a wrong `v`, a non-array `contexts`, more than 12 contexts, more than 16,384 **UTF-8 bytes** (`overLimit()`: string length first, then `TextEncoder` byte length; never `.length` alone, since a non-ASCII name or loop id takes several bytes per character), a parse error, or a throwing accessor. The result is an empty cache, and the page renders the URL's context.
  - **Dropped quietly, one record at a time:** an invalid `id` (`/^[a-z0-9]{1,16}$/`), a `view` outside `VIEW_META`, a `repo` that is not a 1–200 character string or null, a `repoKey` that does not match `/^[A-Za-z0-9_-]{1,128}$/` or is non-null with a null repo, and duplicate ids or repositories.
  - **`sub`:** kept only for `view: "loop"`, through the shell's `cleanSub` (configured), with `loopId` capped at 200 characters.
  - **Saves happen on hydration and later syncs, not only on user actions.** A page that is still hydrating, or still re-rendering after its first data load, can write the workspace after a test's `sessionStorage.clear()`, which brings back a repository-less context. UI tests that clear the store must first let the current page settle: `test_workspace_tabs.py` `_keys()` waits for `isHydrated()` and network idle.
  - **Writes:** `save()` skips a value over the same `overLimit()` byte limit and swallows a throwing `setItem`.
  - **Never stored:** tokens, prompts, artifact text, filesystem paths or API responses.
- **Snapshot:** `workspace()` returns null when `window.GATOR_SNAPSHOT` is set. A static fleet report has no workspaces, and nothing is read or written.
- **Accessors** `active()` / `list()` / `findByRepo()` return copies. `configure({isView, cleanSub})` is called once by the shell at script load.
- **Pinned by** `tests/test_dashboard_ui/test_workspace_tabs.py` (`test_workspace_cache_rejects_bad_records`, `test_workspace_cache_keeps_valid_contexts`, `test_workspace_cache_holds_only_bounded_fields`).
- **List operations** (`create` (null at 12) / `select` / `neighbourOf` (right, else left) / `remove` / `count`) change only the list and save. The shell renders and records.

### renderWorkspaceStrip() / selectContext() / newContext() / closeContext() · GatorWorkspace: renderStrip() / onStripKey() / tabLabel() / closeLabel() / create() / select() / neighbourOf() / remove() — workspace strip
File: src/gator_command/scripts/dashboard/workspace.js
File: src/gator_command/scripts/dashboard/dashboard.js
File: src/gator_command/scripts/dashboard/dashboard.html
The full-width strip of workspace contexts above the sidebar and main pane. Top tabs are places the Architect has open; sidebar items are activities in the selected place.
<- `syncWorkspace()` (after every sync) and strip clicks
-> `applyShellEntry()`, `recordShell("pushState")`
- **Markup:**
  - `nav#workspace-strip[aria-label="Workspaces"]` is the first child of `<body>`, before `#app-shell`, which carries `role="tabpanel"` and an `aria-labelledby` that follows the active tab.
  - **Two regions.** The strip holds two static regions:
    - `div#workspace-tabs`, the **render container**. `renderWorkspaceStrip()` passes it to `GatorWorkspace.renderStrip`, which empties and rebuilds it.
    - `div#strip-status[role=group][aria-label="Dashboard status"]`, which holds `#generated-at` ("Updated <time>") and `#refresh-btn` ("↺ Refresh", `doRefresh`).

    A flexible `div.strip-spacer` sits between them. The status region is a sibling of the render container, so a rebuild never touches it, and it is outside the tablist, so arrow keys never reach it.
    ! TRIPWIRE: never pass `#workspace-strip` itself to `renderStrip` (`container.textContent = ""` would delete the status region).
  - `#workspace-tabs` holds a `div.workspace-tablist[role=tablist][aria-label="Open workspaces"]` of `div.workspace-item[role=presentation]`. The active context's item also has `.workspace-item-active` (Paper, presentation only), so the selected tab and its close button share one fill and one top bar. The class changes only with `activeId`, which is already in the rebuild fingerprint. Each item holds:
    - `button.workspace-tab[role=tab]` (`#ws-tab-<id>`, `aria-selected`, `aria-controls="app-shell"`, roving `tabindex`, `data-ctx`), labelled with the repository display name. A context with no repository (`.workspace-tab-gator`) instead shows the Gator mark (`img.workspace-tab-logo`, `gator-logo.png`, `alt=""`, 18 px, opacity 0.7, or 1 when selected), drawn dark on the light strip by `filter: brightness(0) opacity(.8)`. Its text is "Gator" in a visually hidden `span.workspace-tab-text`, so its accessible name and `textContent` stay "Gator", and its `title` is "No repository";
    - a separately focusable `button.workspace-tab-close` labelled "Close <repo> workspace" / "Close workspace without repository" (`tabindex` 0 on the active item, else -1).
  - Then `button.workspace-new` ("+", `aria-label="New workspace"`). At 12 contexts it is disabled, with the title "Workspace limit reached (12)".
  - All text is set through `textContent`.
- **Keyboard (manual activation):** Left/Right (wrapping), Home and End move focus and the roving `tabindex` only. Enter/Space (native button click) selects. The reason: a selection remounts a view and records history, which must not happen on every arrow key.
- **Rendering:** `renderStrip` rebuilds only when `[activeId, ids, repos]` changes (or `force`). Focus inside the strip (tab, close or +) is restored across a rebuild, falling back to the active tab. `focusActive` puts focus on the active tab, even when the strip is unchanged (the strip may already have been rebuilt by the sync inside the same selection). The active tab is scrolled into view.
- **`selectContext(id, {force, focus})`:** a no-op for the active context unless `force`.
  1. `GatorWorkspace.select`.
  2. If the context's repository is no longer registered (`validateRepo`), apply `{view: fleet, repo: null}` and show the "no longer registered" notice: the context becomes repository-less, never another repository. Otherwise apply `{view, repo, repoKey, sub}` through `applyShellEntry()`. Its `showView()` runs the previous view's teardown first.
  3. Push one entry with `recordShell("pushState", sub)`.
  4. Re-render the strip.
- **`newContext()`:** creates `{repo: null, view: "welcome"}` and selects it with focus.
- **`closeContext(id)`:**
  - **An inactive context** is removed, with no navigation and no history entry.
  - **The active context** is removed, then its right-hand (else left-hand) neighbour is selected with focus.
  - **The last context** is replaced by a new repository-less Welcome context.
  - Close never calls a registry or Loop endpoint.
- **Snapshot:** `init()` hides the strip, which also hides `#strip-status` and its Refresh button, and removes `#app-shell`'s tab-panel role. `updateTimestamp()` then also writes "at <date-time>" into `#snapshot-generated-at` in `#snapshot-banner`, so a static report keeps its capture time.
! TRIPWIRE: inactive contexts are not live. Only the selected context is rendered, so switching tears down Loop polling, timers and listeners through `showView()`'s existing teardown. Never keep hidden DOM copies of other contexts.
- **Pinned by** `test_strip_spans_shell_above_sidebar`, `test_strip_aria_keyboard_and_close_labels`, `test_switch_restores_each_context`, `test_only_active_loop_context_polls` and `test_close_changes_navigation_only` in `tests/test_dashboard_ui/test_workspace_tabs.py`.

### Same-origin API requests — fetch and mutation calls from every view
File: src/gator_command/scripts/dashboard/dashboard.js
Call same-origin dashboard APIs and normalize errors for views.
<- all view modules
-> Dashboard server
! Every POST includes `X-Gator-Dashboard: 1`. Never add cross-origin fallback behavior.

### Paper tokens
File: src/gator_command/scripts/dashboard/dashboard.css
The one token source for browser UI. It is the first `:root` block.
- **Type:** `--font-sans`, `--font-mono`, `--text-xs/sm/base/ui/nav/section/page` (11/12/16/14/13/18/30px), `--leading-compact/ui/prose`, `--weight-normal/medium/emphasis`, `--tracking-label`.
  - **Roles.** `--text-base` is the **reading-prose** role (the Now line, turn summaries, help and dialog explanations). `--text-ui` is **section/action text** (labels, row titles, the sidebar context name). Navigation uses `--text-nav`, technical metadata `--text-xs` / `--text-sm`, and code keeps its explicit 12–13px mono sizes.
  - ! **No text inherits the root type.** Every visible text element gets its size from an explicit rule or a token, and its line height from an explicit rule or a **compact-leading owner**. A compact-leading owner is a container that declares `line-height: var(--leading-ui)`: `#workspace-strip`, `#sidebar`, `#view-slot.route-repo` (Repo and Docs), `.view-header`, `.section`, `.card`, `.data-table`, `.gator-modal`, `.commits-view`, `.loop-workspace`, `.loop-dialog` and `.charters-view` (which also sets `--text-ui`; its reading prose, `.charters-prose`, is `--text-base` / `--leading-prose`). The former root inheritors are pinned to `--text-ui`: `.ctx-name`, `.repo-markdown p` / `li`, `.commit-subject`, `.commit-chev`, `.commit-body`, `.loop-recovery-summary` and `.loop-recovery-role`. `.gator-modal h3` is `--text-section` (it was the browser's 1.17em). `.gator-modal-body p` (the Fleet dialogs' explanation) is reading prose, `--text-base` / `--leading-prose`. A new surface needs an explicit role or one of these owners.
  - **Pinned by** `test_no_text_inherits_root_type` (`test_paper_shell.py`). For each of 13 surfaces (Fleet, the Add Repository modal, Repo Markdown, an expanded commit, the blocked-commit dialog, Updates, Settings, Docs, the Charters page (measured after its health report settles, so the report's lede is always checked), the active Loop, the Interject and decision dialogs, and a terminal Loop), it sets `html` and `body` to sentinel values (23px / 2.3) without touching the tokens. It asserts that no visible text or form control changes its computed size or line height.
- **Neutrals and teal:** `--gray-50…900` (Tailwind gray), `--teal`, `--teal-dark`, `--teal-ink`, `--teal-light`, `--amber-light` (the tint behind amber-ruled notes, such as the Commits override note), `--focus-ring`.
- **Rhythm:** `--space-1…7` (4, 8, 12, 16, 24, 32, 48px) and `--radius-control` (6px) / `--radius-card` (8px).
- **Legacy names are aliases, not a second source.** In the second `:root` block, `--color-bg` (gray-50), `--color-border` (gray-200), `--color-text` (gray-800), `--color-muted` (gray-500) and `--color-link` (teal-ink) read the Paper scale, and `--font` / `--mono` alias `--font-sans` / `--font-mono`. View CSS that reads them follows Paper without a rewrite. Status colours (`--color-healthy` …) and `--sidebar-*` are not yet Paper (the sidebar moves with the Paper frame).
! **Final reading baseline:** `html, body` is 16px/1.6 (`--text-base`, `--leading-prose`). It replaces the temporary 14px/1.5 baseline.
  - **No visible text inherits it** (see Roles above). Dense surfaces keep 1.5 through the compact-leading owners, and the role tokens keep their sizes: `--text-ui` 14, `--text-nav` 13, `--text-sm` 12, `--text-xs` 11.
  - **The only reviewed compact override** is `.fleet-table td:first-child { white-space: nowrap; }`. At 375px, the larger repository names otherwise broke at a hyphen into tall rows; the narrow table already scrolls sideways.
  - **What actually grew** is only the reading-prose roles that read `--text-base`: the Loop Now line, executive paragraphs and dialog explanations; the Fleet repository names, empty state and dialog prose.
  - **Welcome and Docs frame content** is unaffected; each document owns its typography.
  - **Pinned by** `test_root_reading_baseline` (`test_paper_shell.py`): `html` and `body` compute to 16px / 25.6px, and the token sizes are as above.
! New shell CSS uses tokens, never new palette literals. The roughly 200 legacy hex literals in view CSS retire with each view's redesign.
! Mono marks literal technical values (versions, SHAs, paths, code), not "small text". `gray-400` is for decorative rules only, never meaningful text: `gray-500` is the minimum for supporting text on white (WCAG AA).
! **Dormant `--font-mono` references woke up.** Nine view rules read `var(--font-mono)` before the token existed. The seven with no fallback therefore inherited sans; the two with a `monospace` fallback used the browser monospace. Defining the token switches them all to the Consolas stack.
  - **Mono, as the rule above intends:** `.repo-file-header` (the file path), `.history-hash`, `.md-code-block`, `.md-inline-code`, `.loop-brief-input` and `.loop-coding-value`.
  - **Kept sans with `font-family: inherit`:** the three navigation labels `.repo-sidebar-header`, `.repo-sidebar-section` and `.repo-tree-dir`, so their rendering is unchanged.
  - **For later Paper work:** a newly defined token can activate existing `var()` reads. Grep for the name before adding one.

### responsive shell
File: src/gator_command/scripts/dashboard/dashboard.css
Maintain the sidebar/topbar/content flex chain and usable narrow-screen layout.
<- all views
! Repository content and iframe containers need `min-width: 0`; HTML preview retains a visible minimum height and scrollable overflow.
! **Body column:**
  - **Layout:** `body` is a column flex box (`height: 100vh; overflow: hidden`) holding `#workspace-strip` and then `#app-shell`.
  - **The strip** is `flex: 0 0 var(--workspace-strip-height)` (46px since Paper; 36px before). It is one row that never wraps, and scrolls horizontally when narrow. The `#strip-status` region scrolls with it. Surfaces: gray-100 fill, gray-600 text, a gray-200 bottom border and gray-200 item seams.
  - **`#app-shell`** is `flex: 1; min-height: 0; position: relative`. It replaced `height: 100vh`, and the page still never scrolls.
  - **`#sidebar-toggle`** is `position: absolute` within `#app-shell` (no positioned ancestor between), so it sits below the strip. Its `top` centres it on the header (`(var(--topbar-height) - 28px) / 2`; 8px at ≤768px), and `left` is unchanged.
! **Paper frame:**
  - **Sidebar:** white, `--sidebar-width` 244px (220px before), a gray-200 right border (removed when collapsed), gray-700 items at `--text-nav` with a 36px minimum height, gray-100 hover. Group labels are 11px/600, uppercase, tracked, gray-500. The footer is gray-500 on a gray-200 top rule.
  - **Logo:** `#brand-logo` is 56px (120px before; 32px at ≤768px) and drawn dark by `filter: brightness(0) opacity(.8)`. It is still the snapshot's one external image reference.
  - **Unavailable items:** `.sidebar-item.dimmed` / `.placeholder` text is **gray-500**, never gray-400, because these are meaningful labels that must meet WCAG AA on white. Only the redundant icon glyph is lighter (`opacity: .6`).
  - **Page header (`#topbar`):**
    - `--topbar-height` is 88px (64px at ≤768px), with a gray-50 background like the canvas and no bottom border.
    - The title `#topbar-title` is `--text-page` (30px; 24px at ≤768px) / 700, line-height 1.2, `-.015em` tracking, gray-900, ellipsis.
    - It sits over a 3px teal rule (`#topbar::after`, decorative), inset by `--page-gutter`.
    - `#topbar-left` no longer needs its 36px toggle padding: the 48px gutter clears the toggle (8px + 28px) and aligns the title with view content.
  - **Gutter:** `--page-gutter` is 48px (32px at ≤768px). `#view-slot` padding is 32px × gutter (32px all round at ≤768px). `.route-repo` keeps `padding: 0`.
  - **Strip status:** `#generated-at` is 12px sans gray-600 (no longer mono: a clock time is not a literal technical value). `#refresh-btn` is a white button with a gray-300 border and 12px/500 text.
  - **Selection grammar: three families, one rule.** Every selected state is a positioned teal bar plus weight 600, never colour alone. The bar's edge encodes the control's place:
    - **Workspace tab, TOP bar:** `.workspace-item-active` has a gray-50 fill joined to the canvas, gray-200 side and top seams, an 8px top-only radius, and `box-shadow: inset 0 3px 0 var(--teal)`. Its tab is 600 gray-900. Items are 38px on the strip's bottom edge (`align-items: flex-end`), and inactive items keep a transparent 1px seam so selection never shifts the row. The strip's baseline is `box-shadow: inset 0 -1px 0 gray-200`, not a border, so the selected item paints over it.
    - **In-view tab (`.gator-tab`), BOTTOM rule:** transparent fill; selected is a 3px teal `border-bottom` + 600 gray-900; unselected is 400 gray-600 with a transparent rule.
    - **Sidebar item (`.sidebar-item.active`), LEFT rail:** `--sidebar-active-bg` (teal-light) fill, `--sidebar-active` (gray-900) text, 600, and `box-shadow: inset 4px 0 0 var(--teal)`, inset so the label does not move. Sidebar items stay buttons, never `role=tab`.
  - **Focus:** one 2px `--focus-ring` (teal-dark) `:focus-visible` outline for `.gator-tab`, `.sidebar-item`, `#refresh-btn`, `#topbar-repo-tools button`, `#sidebar-toggle` and `.brand-home` (offset 2px; 4px for the logo). Strip controls draw it inside (offset −2px), because the strip clips overflow.
  - **Reduced motion:** `@media (prefers-reduced-motion: reduce)` sets `transition: none; animation: none` on `#sidebar`, `.sidebar-item`, `#refresh-btn` and `.motion-shell`. `.motion-shell` is the hook that later shell animations (loop marks) must use.
  - **Selection, focus, contrast and motion are pinned by** `test_paper_shell.py`: `test_selection_families_bar_plus_weight`, `test_shell_text_meets_wcag_aa` (10 quiet-text selectors ≥ 4.5:1 against the composited background, including dimmed items), `test_focus_ring_visible_on_shell_controls` and `test_reduced_motion_turns_off_shell_transitions`. They are also pinned by the selected-state assertions in `test_workspace_tabs.py` (`test_strip_aria_keyboard_and_close_labels`), `test_welcome_ui.py` and `test_loop_workspace.py` (`test_loop_tabbar_spans_main_pane`).
  - **Pinned by:**
    - `tests/test_dashboard_ui/test_paper_shell.py`: `test_header_is_title_only` (seven views) and `test_paper_frame_geometry_bounded` (1440 and 375);
    - `test_workspace_tabs.py`: `test_strip_spans_shell_above_sidebar` (46px) and `test_strip_status_outside_tablist`;
    - `test_repo_tree_cache.py` `test_versioned_view_bypasses_cache` (the picker in `#topbar-repo-tools`);
    - `test_welcome_ui.py` `test_welcome_snapshot_frames` (the banner capture time, with the strip and Refresh hidden).
! **Shared main-pane tab bar:** `.gator-tabbar` is a full-width block that owns the 1px baseline (it reaches the main pane's right edge); `.gator-tabbar [role="tablist"]` wraps when narrow; `.gator-tab` keeps a fixed 13px label. Selected = `aria-selected="true"` → weight 600 plus a 3px teal underline (Paper; 700 and `currentColor` before); unselected = weight 400 gray-600, transparent underline; the Paper `:focus-visible` ring. Never colour alone. Loop's Create / History uses it; the old `.loop-subnav*` styles were removed (the class names remain as hooks).
! **Logo button:** `.brand-home` resets button chrome around the unchanged `#brand-logo` sizing and adds a `:focus-visible` outline. Welcome content uses `.welcome-body` under the default `#view-slot` scrolling. It has no max-width and no side padding, so each topic frame spans the full main-pane content width, aligned with the tab bar. Each document sets its own reading width inside its frame. A column flex chain (`.welcome-workspace` `min-height: 100%` → `.welcome-body` `flex: 1` → `.welcome-panel:not([hidden])` `flex: 1` → `.welcome-frame` `flex: 1`) makes each topic iframe fill the main pane down to `#view-slot`'s bottom padding, so the bottom margin matches the side margins. `.welcome-frame` is block, full width, no border, `min-height: 480px` (`420px` at ≤600px); below that the view slot scrolls. ! The panel rule must keep `:not([hidden])`: a bare `display: flex` would override the `hidden` attribute and show every topic. There is no auto-height cross-frame coordination: a document scrolls inside its frame. `.welcome-doc-status` styles the snapshot's unavailable-document notice. The old Markdown, list, next-button and copy rules were removed.
! Loop height chain: `.loop-workspace` (column, `height:100%`) → `.loop-workspace-body` (`flex:1; min-height:0`) keeps `.loop-sidebar` / `.loop-main` as the scroll owners.

## Before Changing This Module

- Confirm the backend wire schema and empty/error states.
- Exercise keyboard/mouse navigation and narrow/wide layouts.
- Run Playwright tests for mutations, file browsing, CSP liveness, iframe isolation, and preview controls.
- Keep the UI dependency-free unless the product architecture explicitly changes.

## Connections

-> [Dashboard Server](scripts-dashboard.md) - APIs, security, and content policy
-> [Contracts](contracts.md) - Cumberland HTML compatibility
-> [Dashboard Views](scripts-dashboard-views.md) -- views the shell mounts through `showView()` / `renderView()`
-> [Loop Workspace View](scripts-dashboard-loop-ui.md) -- the Loop workspace the shell mounts and restores
