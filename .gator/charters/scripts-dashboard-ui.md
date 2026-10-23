# Charter: Dashboard Browser UI

**Covers**: `src/gator_command/scripts/dashboard/dashboard.html`, `src/gator_command/scripts/dashboard/dashboard.css`, `src/gator_command/scripts/dashboard/dashboard.js`, `src/gator_command/scripts/dashboard/workspace.js` (#80), `src/gator_command/scripts/dashboard/views/**`, `src/gator_command/scripts/dashboard/*.png`. The view files, named one by one so the pre-commit heading check (which reads only literal paths, not globs) can verify them: `src/gator_command/scripts/dashboard/views/fleet.js`, `src/gator_command/scripts/dashboard/views/history.js`, `src/gator_command/scripts/dashboard/views/syntax.js`, `src/gator_command/scripts/dashboard/views/repo.js`, `src/gator_command/scripts/dashboard/views/updates.js`, `src/gator_command/scripts/dashboard/views/loop-markdown.js` (#45), `src/gator_command/scripts/dashboard/views/loop.js`, `src/gator_command/scripts/dashboard/views/settings.js`, `src/gator_command/scripts/dashboard/views/welcome.js`, `src/gator_command/scripts/dashboard/views/docs.js`, `src/gator_command/scripts/dashboard/views/audit.js`.

## Owns

- The framework-free dashboard shell, navigation, responsive layout, and browser-side routing.
- Fleet, history, repo, audit, loop, updates, settings, and welcome views.
- Document browsing, syntax highlighting, cross-document search, and sandboxed HTML preview controls.
- Browser requests to the local dashboard server.

## Does Not Own

- Route authorization, path containment, filesystem access, or data computation; see [`scripts-dashboard.md`](scripts-dashboard.md).
- Governance business rules.
- Cumberland document-template styling; see [`contracts.md`](contracts.md).

---

### navigate() / showView() / renderView() / restoreShellState() / applyShellEntry() / setActiveRepo() / clearActiveRepo() / shellUrl() / parseShellUrl() / recordShell() / formatDocumentTitle() / updateDocumentTitle() / window.GatorShell
File: src/gator_command/scripts/dashboard/dashboard.js
Own browser history, selected repository/view state, and dispatch into view modules.
<- sidebar, topbar, `window.gatorNavToRepo` (fleet rows), popstate
-> `views/*`
! URL state and visible selection stay synchronized; refresh re-renders the same repo/view rather than silently returning home.
! **Shell-owned history (#56).** `dashboard.js` is the only owner of Dashboard history entries, for every view.
  - **State shape:** `{gatorDashboard: 1, view, repo, repoKey, sub, ctx}`, built by `shellState(sub)`. `ctx` (#80) is the opaque id of the workspace context shown, or null before hydration and in snapshots. `isShellEntry` accepts it absent, null or a string. Since #80, every entry also carries the canonical URL of the active context (see "Shell URL (#80)" below). Snapshot entries stay state-only (`file:` URLs). `sub` is `null` except for Loop entries: `cleanSub()` keeps exactly `{view: create|history, mode: create|inspect, loopId}`. **No token, prompt text or artifact content ever enters a state object.**
  - **`navigate()` versus `showView()`:** `navigate()` = `showView()` plus `recordShell("pushState")`. It is used by the sidebar click handler and `gatorNavToRepo`. `init()` lands through `applyShellEntry()` and then `recordShell("replaceState")`. `doRefresh` calls `showView` and pushes nothing. `showView(name, extra, repoKeyOverride, opts)` is a renderer only. It passes `opts.initialSub` as the fifth argument to `views.loop`, and records `state.mountedLoopKey` (the repo key a mounted Loop view uses; `undefined` otherwise).
  - **`window.GatorShell`:** `pushSubState(sub)` pushes only when the active view is Loop and no restoration is running. `replaceSubState(sub)` replaces the current entry (Loop only). `isRestoring()`.
  - ! **Shell URL (#80) — `shellUrl(view, repo)` / `parseShellUrl()` / `recordShell(method, sub)`.**
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
    - **Choosing the view.** A missing `view` keeps the legacy meaning: `?repo=<name>` → that Repo view; otherwise a snapshot (`window.GATOR_SNAPSHOT`) → Fleet (a snapshot is a fleet report); otherwise → **Welcome** (the front door, Architect direction 2026-10-11; opening on the "Start a session with Gator" topic since 2026-10-15). `?view=<view>` (with or without `repo`) lands on that view.
    - **Reload or duplicated tab.** When `history.state` is a valid shell entry for the same view and repository name, its `repoKey` (which disambiguates same-named repositories) and `cleanSub(sub)` are reused, so a Loop tab and selection survive a reload.
    - **Dispatch.** The entry goes through `applyShellEntry()`, the same hydrate → dispatch path as Back/Forward. **An unregistered `?repo=` therefore lands on Fleet with the "no longer registered" notice** (before #80 it mounted a failing Repo view).
    - **Recording.** The landing entry is recorded with `recordShell("replaceState")`, so Back from the first navigation returns to the landing view.
    - **#70:** the guard below runs before any of this and is unchanged.
  - ! **Navigation during load wins (#70).** `showView()` increments `viewRenders`; `init()` compares it across its `/api/data` await. If anything rendered a view meanwhile (sidebar click, `gatorNavToRepo`, popstate), `init()` re-renders that view with the loaded data (`showView(activeView, activeRepo, activeRepoKey)`, like `doRefresh`) and skips both the landing view and the landing `replaceState`. Before this, a navigation made before `/api/data` returned was replaced by Welcome (Windows CI flake #70).
  - **Title-only header (Paper, 2026-10-19) — `updateTopbar(name)`:**
    - It writes only `#topbar-title`, through `textContent`, from `VIEW_META[name].title`. `#topbar-subtitle` stays in the DOM, `hidden` and never written; the `VIEW_META.*.subtitle` fields are unused (follow-up: remove both).
    - **Repo branch tools:** the branch-history picker (`#branch-version-label`, `#branch-history-btn`, `#branch-history-dropdown`, with unchanged ids and click wiring) lives in `span#topbar-repo-tools` in `#topbar-right`, before `#repo-search-input`.
      - `showView()` empties and hides it on every render.
      - Only the Repo branch with a known `branch` fills it, from static markup only: no repository name or branch text, which the sidebar context shows. It is then un-hidden.
      - The dropdown is positioned against it (`.history-dropdown`: `right: 0`).
      - Before Paper, this markup, with the name and branch, was written into the subtitle through `innerHTML`.
  - **Welcome (#72):** `welcome` is a `VIEW_META` view ("Welcome to Gator!") shown on a live load without `?repo=` (see Landing view), and reached from the `#brand-home` logo button (`aria-label="Open Welcome"`; `navigate("welcome")`; `aria-current="page"` while it is shown) and from Back/Forward. Its `showView` branch never calls `setActiveRepo` / `clearActiveRepo`, and its entries carry `sub: null` (`cleanSub` stays Loop-only).
  - **Repository context:** `setActiveRepo(name, key)` (extracted from the `repo` branch) sets `activeRepo` / `activeRepoKey`, calls `renderSidebarContext()`, and un-dims Repo, Commits (`#history-tab`, since 2026-10-18) and Loop through `setRepoItemsEnabled(true)`. `clearActiveRepo()` is its inverse: the empty card, and those items dimmed.
    - **Context card (Paper, 2026-10-19):** `renderSidebarContext()` rebuilds `div#sidebar-context[aria-live="polite"]` (under `#sidebar-brand`) from the shell state and the matching Fleet record (by `repo_key` when known, else by name).
      - **With a repository:** `.ctx-name` holds the registry display name, then `.ctx-meta` holds `span.ctx-branch` (`branch`) · "Gator " `span.ctx-version` (`cli_version`). A missing field is omitted, and the meta line is dropped when both are missing (for example, a navigation made before `/api/data` returned; the #70 re-render fills it).
      - **Empty state** (also the static HTML before any script runs): `.ctx-name.ctx-empty` "None selected" and `.ctx-meta` "Choose one in Fleet".
      - **`doRefresh`** re-renders the card from the fresh data.
      - ! Every value is set with `textContent` / text nodes (`contextEl()`), never markup.
      - Mono applies only to the branch and version fragments.
      - The card is hidden at ≤768px, where the strip tab already names the repository.
    - **Repo label:** the Repo item is the static "▸ Repo" label. The "▸ <name>" label and `setRepoTabLabel()` are gone, and so is the item's inline 28px indentation.
    - **Unavailable items:** `setRepoItemsEnabled(enabled)` toggles `dimmed` together with `aria-disabled="true"` and `title="Choose a repository in Fleet first"` on `#repo-tab`, `#history-tab` and `#loop-tab`; the static HTML starts in that state. This is the non-colour cue for the gray-500 dimmed text.
    - **Welcome item:** `button.sidebar-item#welcome-nav[data-view="welcome"]` ("⌂ Welcome") is the first Overview item. It is never dimmed, it navigates through the ordinary sidebar click handler, and it gets `.active` from `showView()`. The `#brand-home` logo stays a second Welcome entry, with its `aria-current`.
    - **Pinned by:**
      - `tests/test_dashboard_ui/test_paper_shell.py`: `test_context_card_shows_repository_and_empty_state`, `test_context_card_renders_text_literally`, `test_context_card_hidden_when_narrow`, `test_welcome_sidebar_item_navigates` and `test_unavailable_items_carry_non_colour_cue`;
      - `test_docs_view.py`: the `aria-disabled` / `title` toggle;
      - `test_loop_workspace.py` / `test_welcome_ui.py`: the card name follows Back/Forward and landing;
      - `test_loop_workspace.py` `test_commits_tab_is_gated_like_loop` (an existing test): a dimmed click still does nothing. It is now a forced click, because an `aria-disabled` item fails Playwright's actionability check, and it asserts `aria-disabled` first. The sidebar click handler ignores a dimmed item, so Commits, like Loop, does nothing until a repository is selected; without one the view would only show its "Select a repo" placeholder. **Docs is always enabled** (2026-10-13): it is repository-independent (`GatorViews.docs`), never dimmed, not guarded by the sidebar click handler, and its `showView` branch needs no active repository and shows no repo search box.
  - **Restoration:** a single `popstate` handler → `restoreShellState(entry)`, run under the `restoring` flag (cleared in `finally`). Step 1 is in `restoreShellState`; steps 2–3 are `applyShellEntry(entry)` (#80), which `init()` also uses. **Before step 1 (#80):** when `entry.ctx` names a workspace context that is still open and is not the active one, that context is selected (`GatorWorkspace.select`, no push). Back therefore undoes a strip selection. Otherwise (no `ctx`, or a closed context) the entry is applied to the active context, whose inactive duplicate for the same repository is dropped.
    1. **Validate:** `isShellEntry` (marker, a `VIEW_META` view, `repo` null or a string). Anything else is ignored.
    2. **Hydrate the repository before any dispatch.** The fleet entry matching name and recorded key, else name only, is authoritative → `setActiveRepo`. An unregistered repo → `clearActiveRepo`, Fleet with a `.shell-notice` "That repository is no longer registered.", and `recordShell("replaceState")` to Fleet (URL `?view=fleet`). A null repo → `clearActiveRepo`.
    3. **Dispatch:** a Loop entry for the already-mounted Loop view of the *same* repo key → `views.loop.restore(sub)` (no remount). Otherwise `showView(view, repo, activeRepoKey, {initialSub})`, so a repository change always remounts.
  - **`views/repo.js` entries:** `repo.js` still pushes its own search/file entries (`{view: "repo", repo, searchQuery|filePath}`, no marker) and applies them with its own controller-scoped `popstate` listener while mounted. The shell leaves such an entry to `repo.js` when that repo's Repo view is mounted (Docs no longer mounts `repo.js`). Otherwise it restores that Repo view, so Back never goes dead.
  - **No re-entrancy:** pushes are suppressed while restoring, and the restore paths call no pushing function.
  - ! **Browser-tab title (#80) — `formatDocumentTitle(view, repo)` / `updateDocumentTitle()`.**
    - **Formatter:** a pure function of the shell's `activeView` and `activeRepo`:
      - `Gator · Fleet` and `Gator · Welcome` never show a repository;
      - any other view with a repository is `Gator · <repo> · <Label>` (for example `Gator · alpha · Docs`, `Gator · alpha · Loop`);
      - otherwise `Gator · <Label>`.
    - **Labels:** `TITLE_LABELS` (`welcome` → "Welcome", `history` → "Commits"), else `VIEW_META[view].title`.
    - **Repository part:** the registry display name, truncated to `TITLE_REPO_MAX` (60) characters with "…". It is assigned through `document.title` (text). It never comes from repository content, a file path or a document.
    - **Single exit:** `showView()` is now `viewRenders++`, then `renderView()` (the former body) in `try`, then `updateDocumentTitle()` in `finally`. Every path that renders therefore sets the title: landing, `navigate()`, `doRefresh`, the #70 re-render, `restoreShellState()` and its unregistered-repository Fleet fallback. No other code assigns `document.title`. `views.loop.restore()` (no remount) keeps the same view and repository, so the title is already correct.
    - **Pinned by** `tests/test_dashboard_ui/test_workspace_tabs.py` (`test_document_title_follows_view`, `test_two_pages_distinct_titles_and_urls`).

### syncWorkspace() / hydrateWorkspace() / validateRepo() / workspace() · window.GatorWorkspace: configure() / load() / syncActive() / findByRepo() / active() / list() / readCache() / save() / sanitize() / overLimit() / sameRepo() / dropDuplicatesOf() / assign() / newId() / cleanRepo() / cleanKey() / cleanContextSub() (#80)
File: src/gator_command/scripts/dashboard/workspace.js
File: src/gator_command/scripts/dashboard/dashboard.js
The per-browser-tab list of workspace contexts `{id, repo, repoKey, view, sub}` and its session cache. A context is an optional repository plus the last view to restore for it.
<- `dashboard.js`: `syncWorkspace(sub)` from `showView()`'s `finally`, `recordShell()`, and the `views.loop.restore` branch of `applyShellEntry()`; `hydrateWorkspace()` at the end of `init()` (landing and #70 branches)
-> `sessionStorage` only
! TRIPWIRE: `workspace.js` never routes. It renders no view, never calls `history`, `showView` or `fetch`. `dashboard.js` stays the only router.
! **The active context is a recorded copy of the shell state, never a second authority.** `syncActive()` writes the shell's `activeView` / `activeRepo` / `activeRepoKey` (+ Loop `sub`) into the active context. `showView()` syncs with `sub: null`; the Loop mount's `GatorShell.replaceSubState` then records the real sub.
! **Before hydration nothing is written.** `syncActive()` and `save()` are no-ops until `load()`, so the landing never overwrites the cache before reading it.
- **`load(current, validateRepo)`**, after the landing or the #70 re-render, so a navigation during load still wins:
  1. Read the cache.
  2. Keep a cached context only if `validateRepo(repo, repoKey)` finds it in the current fleet data: by key when the record has one, else by name. It takes the registry's current name and key and never substitutes another repository. A repository-less context always survives.
  3. The active context is the cached one for the same repository, or (no repository) the cached active context when it was repository-less. Otherwise a new context is appended; at 12 contexts the last inactive one is dropped.
  4. Sync it from `current` and save.
- **One context per repository:** `sameRepo` matches by key when both are known, else by name. A cache with duplicates keeps the first. `syncActive` drops an inactive duplicate of the active context's repository (the active wins).
- **Storage contract:** key `gator.dashboard.workspace`, `sessionStorage` (per browser tab; never `localStorage`). Value `{"v": 1, "activeId", "contexts": [...]}`.
  - **Rejected whole:** a wrong `v`, a non-array `contexts`, more than 12 contexts, more than 16,384 **UTF-8 bytes** (`overLimit()`: string length first, then `TextEncoder` byte length; never `.length` alone, since a non-ASCII name or loop id takes several bytes per character), a parse error, or a throwing accessor. The result is an empty cache, and the page renders the URL's context.
  - **Dropped quietly, one record at a time:** an invalid `id` (`/^[a-z0-9]{1,16}$/`), a `view` outside `VIEW_META`, a `repo` that is not a 1–200 character string or null, a `repoKey` that does not match `/^[A-Za-z0-9_-]{1,128}$/` or is non-null with a null repo, and duplicate ids or repositories.
  - **`sub`:** kept only for `view: "loop"`, through the shell's `cleanSub` (configured), with `loopId` capped at 200 characters.
  - **Saves happen on hydration and later syncs, not only on user actions.** A page that is still hydrating, or still re-rendering after its first data load, can write the workspace after a test's `sessionStorage.clear()`, which brings back a repository-less context. UI tests that clear the store must first let the current page settle: `test_workspace_tabs.py` `_keys()` waits for `isHydrated()` and network idle (Windows CI, 2026-10-18).
  - **Writes:** `save()` skips a value over the same `overLimit()` byte limit and swallows a throwing `setItem`.
  - **Never stored:** tokens, prompts, artifact text, filesystem paths or API responses.
- **Snapshot:** `workspace()` returns null when `window.GATOR_SNAPSHOT` is set. A static fleet report has no workspaces, and nothing is read or written.
- **Accessors** `active()` / `list()` / `findByRepo()` return copies. `configure({isView, cleanSub})` is called once by the shell at script load.
- **Pinned by** `tests/test_dashboard_ui/test_workspace_tabs.py` (`test_workspace_cache_rejects_bad_records`, `test_workspace_cache_keeps_valid_contexts`, `test_workspace_cache_holds_only_bounded_fields`).
- **List operations** (`create` (null at 12) / `select` / `neighbourOf` (right, else left) / `remove` / `count`) change only the list and save. The shell renders and records.

### renderWorkspaceStrip() / selectContext() / newContext() / closeContext() · GatorWorkspace: renderStrip() / onStripKey() / tabLabel() / closeLabel() / create() / select() / neighbourOf() / remove() — workspace strip (#80)
File: src/gator_command/scripts/dashboard/workspace.js
File: src/gator_command/scripts/dashboard/dashboard.js
File: src/gator_command/scripts/dashboard/dashboard.html
The full-width strip of workspace contexts above the sidebar and main pane. Top tabs are places the Architect has open; sidebar items are activities in the selected place.
<- `syncWorkspace()` (after every sync) and strip clicks
-> `applyShellEntry()`, `recordShell("pushState")`
- **Markup:**
  - `nav#workspace-strip[aria-label="Workspaces"]` is the first child of `<body>`, before `#app-shell`, which carries `role="tabpanel"` and an `aria-labelledby` that follows the active tab.
  - **Two regions (Paper, 2026-10-19).** The strip holds two static regions:
    - `div#workspace-tabs`, the **render container**. `renderWorkspaceStrip()` passes it to `GatorWorkspace.renderStrip`, which empties and rebuilds it.
    - `div#strip-status[role=group][aria-label="Dashboard status"]`, which holds `#generated-at` ("Updated <time>") and `#refresh-btn` ("↺ Refresh", `doRefresh`).

    A flexible `div.strip-spacer` sits between them. The status region is a sibling of the render container, so a rebuild never touches it, and it is outside the tablist, so arrow keys never reach it.
    ! TRIPWIRE: never pass `#workspace-strip` itself to `renderStrip` (`container.textContent = ""` would delete the status region).
  - `#workspace-tabs` holds a `div.workspace-tablist[role=tablist][aria-label="Open workspaces"]` of `div.workspace-item[role=presentation]`. The active context's item also has `.workspace-item-active` (Paper, presentation only), so the selected tab and its close button share one fill and one top bar. The class changes only with `activeId`, which is already in the rebuild fingerprint. Each item holds:
    - `button.workspace-tab[role=tab]` (`#ws-tab-<id>`, `aria-selected`, `aria-controls="app-shell"`, roving `tabindex`, `data-ctx`), labelled with the repository display name. A context with no repository (`.workspace-tab-gator`) instead shows the Gator mark (`img.workspace-tab-logo`, `gator-logo.png`, `alt=""`, 18 px, opacity 0.7, or 1 when selected), drawn dark on the light strip by `filter: brightness(0) opacity(.8)`. Its text is "Gator" in a visually hidden `span.workspace-tab-text`, so its accessible name and `textContent` stay "Gator", and its `title` is "No repository". Before 2026-10-17 this tab was labelled `—`;
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

### fetch() / mutation requests — same-origin API calls from every view
File: src/gator_command/scripts/dashboard/dashboard.js
Call same-origin dashboard APIs and normalize errors for views.
<- all view modules
-> Dashboard server
! Every POST includes `X-Gator-Dashboard: 1`. Never add cross-origin fallback behavior.

### renderStandaloneRepos() / GatorViews.fleet() / placeMenu() / applySort() / sortRows() / window.gatorNavToRepo() / window.gatorOpenRepoInNewContext() — Fleet view and actions
File: src/gator_command/scripts/dashboard/views/fleet.js
Render repository health and expose explicit per-repository actions via a three-dot overflow menu.
<- fleet route
-> repo update/gatorize endpoints, `POST /api/repos/remove`
! The overflow menu carries dual identity: `data-repo-name` for name-addressed Update/Gatorize, `data-repo-path` for path-addressed Remove. Each action dispatches to the correct identity.
! Actions use the repository's stable key, not display text or array position.
! Missing repositories remain representable so users can understand and clean stale registry entries.
! **⋮ menu stays visible (#74, 2026-10-18).** The menu (`.overflow-menu`, absolute in `.overflow-menu-wrapper`) must never be clipped, including on the last row and in a short window.
  - The Fleet table is `table.data-table.fleet-table` with `overflow: visible`. `.data-table`'s `overflow: hidden` would clip a menu that extends past the last row. The rounded corners are kept by radius on the header's top corner cells and the last body row's bottom corner cells. Other `.data-table` uses keep `overflow: hidden`.
  - `placeMenu(btn, menu)` runs on every open. It measures the space below the button inside the visible area (the window, or `#view-slot` if that ends sooner). If the menu does not fit there and there is more room above, it adds `.open-up` (`bottom: 100%`). `closeAllMenus()` removes `open` and `open-up`.
  - Pinned by `test_last_row_menu_is_fully_visible` (`test_fleet_layout.py`).
! **Opening actions (#80).**
  - **The ⋮ menu** gains two items, before Update/Gatorize and Remove, and only when `!window.GATOR_SNAPSHOT`:
    - **"Open in new workspace tab":** `button.menu-item.menu-open-workspace[data-action="open-workspace"]`, carrying `data-repo-name` and `data-repo-key`. It dispatches to `window.gatorOpenRepoInNewContext(name, key)`.
    - **"Open in new browser tab":** a native `a.menu-item.menu-open-browser-tab`, with `href="?repo=<encodeURIComponent(name)>"`, `target="_blank"` and `rel="noopener"`. It is a same-origin relative link with no handler of its own, so middle-click works. It never names a path or key.
  - **The row link** (`gatorNavToRepo`) means "open in the current context". When another context already holds that repository, it selects that context instead (one context per repository). Otherwise it navigates as before, which turns the current context into that repository's context.
  - **`gatorOpenRepoInNewContext`** (`dashboard.js`) selects the existing context for that repository, or creates `{repo, repoKey, view: "repo"}` (the Repo overview) and selects it with focus. At 12 contexts it shows the `.shell-notice` "Workspace limit reached (12). Close a workspace first." and does nothing else.
  - **Identity:** contexts match by `repoKey` when both sides have one, never by row position.
  - **Pinned by** `test_fleet_open_actions` and `test_fleet_open_workspace_at_limit` (`test_workspace_tabs.py`).
! **Paper inventory (2026-10-23).** Under the title-only header, Fleet is `div.fleet-header`, holding only `#add-repo-btn` (Paper-styled through a scoped rule), then one `table.data-table.fleet-table`. It has no summary text and no cards.
  - **Typography:** the repository name, `button.link-btn.fleet-repo-name`, is `--text-base` (`.fleet-table .fleet-repo-name`, which outranks the later `.link-btn { font: inherit }`). `td.fleet-branch` and `td.fleet-version` are mono `--text-sm`; the version's inline style is gone. Column labels are `--text-ui` / 500 / gray-600, in sentence case.
  - **Table:** one gray-200 boundary, gray-100 row hairlines and a gray-50 hover, all scoped to `.fleet-table`. The #74 `overflow: visible` and corner rules are unchanged.
  - **Empty state:** `td.fleet-empty`, with prose at `--text-base` / `--leading-prose` and `code` at mono `--text-sm`.
  - **Unavailable repository:** the "!" marker also holds the visually hidden text "Not accessible" (`.fleet-hidden-text`).
  - **Narrow widths:** the table is not wrapped. At ≤768px it scrolls sideways inside `#main-shell`, the narrow scroll owner, and the page never scrolls.
! **Sorting — `SORT_COLUMNS` / `fleetSort` / `sortValue()` / `sortRows()` / `applySort()` / `applySortHeaderState()` / `bindSortHeaders()`.**
  - **Columns:** Repo, Branch, Enforcement and Version. Each `th[data-sort-key]` holds a native `button.fleet-sort` and an `aria-hidden` `.fleet-sort-mark`. The ⋮ and activity columns are not sortable, so there are still six `th`.
  - **State:** `fleetSort = {key, dir}` is module-local for the page load. It is never stored, and never put in history or the URL. It survives a Fleet re-render (Refresh, `gatorRefreshFleet`). `key: null` (the default) is registry order.
  - **Activation:** a click, or Enter/Space. A new column sorts ascending; the same column toggles between ascending and descending.
  - **The sorted `th`:** it gets `aria-sort`, a ▲/▼ mark and `.fleet-sort-active` (weight 600, gray-900). Other headers have no `aria-sort` and no mark. The state is never colour alone.
  - **Values:** each row carries `data-row-index`, `data-sort-name`, `data-sort-branch`, `data-sort-version` and `data-enforcement`. Comparison is `localeCompare(…, {numeric: true, sensitivity: "base"})`. A missing value sorts last in both directions, and ties keep registry order.
  - **Applying a sort:** `applySort(table)` moves the existing `<tr>` nodes (`tbody.append`), so no menu or select listener is rebound and header focus stays. The render, header clicks and a successful enforcement save all call it.
  - ! **Enforcement sorts by the SAVED level.** `data-enforcement` (empty when the repository is not gatorized) is written only when `bindEnforcementDropdowns()` gets `status === "ok"`, with the `level` that request sent. If the active key is `enforcement`, the table is re-sorted at once and focus returns to the select. A failed save keeps the attribute, so the order never follows an unsaved value. The endpoint and the check-mark / outline feedback are unchanged.
  - **Pinned by** `test_fleet_title_only_inventory` (1440 and 375), `test_fleet_sort_one_column`, `test_fleet_sort_follows_saved_enforcement` (edit then sort, edit during an active sort, failed edit) and `test_sorted_last_row_menu_targets_its_row`, all in `test_fleet_layout.py`.
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
Render Git-native commit history as collapsed rows with a readable Gator record (Paper Commits view, 2026-10-19).
<- history route (nav label and topbar title "Commits" since #56; the route key `history`, `data-view="history"` and the endpoint are unchanged)
-> `GET /api/repo/<name>/history?limit=30` (`description` and `trailers` fields: see `scripts-dashboard.md` → `get_repo_history()`); `window.GatorLoopMarkdown` (#45)
! Accept both current Architect and legacy PI attribution supplied by the backend (the server already folds `Gator-PI` into `architect`).
! **Stale-render guard (#56):** the commits fetch writes only while the "Loading history..." node it created is still attached. If another view owns `#view-slot` by the time the fetch resolves (for example after a quick Back), the result is dropped.
! TRIPWIRE (untrusted text): commit text is model-authored. Every commit-derived string reaches the DOM through `textContent` / text nodes (`el()`), and the description through `GatorLoopMarkdown.render()` (closed grammar, DOM-only). No `innerHTML` anywhere in the view. If the formatter throws (too large) or is missing, `renderDescription()` shows the literal text in `pre.commit-desc-raw`.
- **Layout:** `div.commits-view` > `div.commit-toolbar` + `div.commit-list`.
  - **List:** `h3.commit-day` headings by **local** day ("Today · …", "Yesterday · …", then the weekday and date; the year when it is not the current one; "Undated" for a bad date). Each commit is a `details.commit-row[data-kind=<group>][data-hash]`, collapsed by default and opened by click or Enter/Space (native `<summary>`).
  - **Summary:** `span.commit-kind` (glyph + label tag), `div.commit-subject`, `div.commit-meta` (`span.commit-hash` short hash · local time · "<agent> with <architect>", else whichever is known, else the author), and `span.commit-flags`: "★ Notable" only for significance `notable`, "⚑ Override" only when an override trailer exists, then a chevron.
  - **Body (`commitBody()`):**
    - `div.commit-desc`: the `description`, or "No description.";
    - an optional `div.commit-override` (amber left border): approved by, rules, block, reason;
    - `div.commit-record` with three columns: **Change** (Type, Significance, Charters through `CHARTER_TEXT`: yes / no / override-skip; plus **Issues** chips "#N" from `Gator-Issues`), **Decision tags** (chips), and **Knowledge layer at this commit** (Charters, Functions, Threads). A missing field is omitted, never "undefined", so older commits render cleanly;
    - `div.commit-actions`: "⧉ Copy hash" (full hash via the Clipboard API; the label shows "✓ Copied" or "Copy failed" for 1.5 s) and "{ } Raw trailers" (`aria-expanded`), which toggles `pre.commit-raw` with every projected `Key: value` line. `Gator-Machine-Id` appears **only** there; `recordOf()` never reads it, so the record stays free of machine identity (Architect decision 2026-10-19).
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
- **CSS:** `commit-*` rules under "Commits view (Paper)" in `dashboard.css`, built from tokens. The 120px type column folds above the subject at ≤1100px.
  - The old commit-list classes (`.history-commit`, `-header`, `-subject`, `-meta`, `-badge`, `-body`) are gone.
  - ! The `.history-toggle-btn`, `.history-dropdown`, `.history-item`, `.history-active`, `.history-hash`, `.history-date` and `.history-msg` rules belong to the **Repo branch-history dropdown** (`#topbar-repo-tools`) and stay.
  - The old view's second `.history-hash` rule used to restyle that dropdown through the cascade; its properties were folded into the dropdown's own rule, so the dropdown looks the same.
- **Pinned by** `tests/test_dashboard_ui/test_commits_view.py`.

### GatorViews.repo(data, container, repoName, version, repoKey) / loadFileList() / renderListing() / loadFile() / applyRefresh() / pollRepoFiles() / pickDefaultFile() / currentFilePaths() / cleanRepoKey() / newTreeState() / acquireTreeState() / treeState() / setSelectedFile() / isCurrentMount() / installSearchListeners() / teardownRepoView() / cacheGet() / cachePut() / cacheable()
File: src/gator_command/scripts/dashboard/views/repo.js
Render the repository knowledge browser, fetch canonical listings, and display supported content.
<- repo route and sidebar clicks; `dashboard.js` passes `state.activeRepoKey` as `repoKey` from the `showView("repo")` branch and the branch-history dropdown
-> list/file/raw/search endpoints
! **Tree state is per repository KEY (2026-10-17, repo-tree return).**
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
! **Live listing cache — `cacheGet()` / `cachePut()` / `cacheable()` / `renderListing()` (checkpoint 2).**
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
  - **Scroll capture:** `teardownRepoView()` writes `#repo-file-list.scrollTop` into the tree state while that element is still connected and the mount is live (`gen !== null`). The shell tears down before clearing the slot; the mount's own idempotent teardown records nothing.
  - **Inactive views are still not live (#80):** only data is cached, never DOM, timers or listeners.
! **Debug seam:** `__gator_debug.sidebar` returns a fresh plain object `{repoName, repoKey, expandedDirs: [...], selectedFile, scrollTop}` from `_repoView`, never the map or a `Set`. `__gator_debug.listingCache` returns a fresh `[{repoKey, items}]` in LRU order (oldest first): keys and sizes only.
! The listing, file and search routes are addressed by **name** on the server (`scripts-dashboard.md`). Two same-named repositories therefore fetch the same listing even though their browser state is separate. The sidebar width and collapse preferences (`gator-sidebar-*:<name>` in `localStorage`) are also keyed by name: follow-up in `inbox.md`.
- **Pinned by** `tests/test_dashboard_ui/test_repo_tree_cache.py` and `test_harness.py` (debug seam).
! Encode file paths per segment so separators retain namespace meaning.
! Render untrusted text as text or through the syntax renderer; do not interpolate repository content into executable markup.
! **No Docs mode (2026-10-13).** `GatorViews.repo(data, container, repoName, version)` has no `filter` parameter: the Docs view is the repository-independent `GatorViews.docs` (`views/docs.js`), which reads the shipped documents from the package. The Repo tree still shows `.gator/docs/` (Markdown and HTML) like any other `.gator/` folder.

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
- **Row label (Paper, 2026-10-23):** `.loop-artifact-toggle` is sans `--text-ui` / 500 (it was mono 13px), because its label is often prose (brief and baseline labels). The rows, their padding and the `(cpK · gen g)` suffix are unchanged. Pinned with the reading roles by `test_loop_reading_hierarchy` (`test_loop_workspace.py`); the rail size is pinned by `test_checkpoint_progress_and_labels` (`test_loop_coding_ui.py`).
- **Pinned by:** `tests/test_dashboard_ui/test_loop_markdown_ui.py` (M3).
  - The tests check: no excerpt and no fetch when collapsed; the full document Rendered by default; Raw identical to what was served; keyboard switching with no refetch; 0 mutations and 0 renders on unchanged polls and on an unchanged refetch; a changed refresh updating both panes and keeping Raw; a stale response unable to reset text or view; and the large and failure fallbacks.
  - **Mutation-checked:** Raw via `innerHTML`, no equality skip, no revision guard, a collapsed fetch restored, and the view reset on render all fail it.

### render(text) / safeHref(url) — window.GatorLoopMarkdown (#45)
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

### GatorViews.audit() / showSessionModal() — Audit view
File: src/gator_command/scripts/dashboard/views/audit.js
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

### buildLoopTabs() / applyTabState() / applyPrimaryLabel() / switchTab() / primaryState() / primaryDecision() / applyPrimary() / setPrimaryDisplay() / landPrimary() / renderHistoryList() / syncListChrome() / reconcilePrimary() / showPrimaryNotice() / primaryNoticeEl() / landFromLoops() / retryLanding() / renderListUnavailable() / renderActiveConflict() / renderCreateWorkspace() / renderHandoff() / renderSelectedLoop() / buildLoopSkeleton() / patchRegion() / renderLiveHeader() / counterLineHtml() / renderOutcomeHeader() / nowLine() / renderNowLine() / unblockActionLabel() / renderBlockedCard() / syncDecisionsDisclosure() / renderPromptSection() / renderControls() / loopDialogConfig() / openLoopDialog() / closeLoopDialog() / setControlsPending() / focusAfterDialogInvalidated() / renderContinueControl() / showExtendNotice() / ensurePolling() / updateTimeline() / renderTimeline() / timelineGroupKey() / timelineGroups() / groupLabel() / groupHtml() / renderArtifacts() / fetchLiveness() / postRenotify() / refreshLiveness() / applyLiveness() / openRenotifyForm() / fetchCodingSnapshot() / patchCodingRegion() / renderCodingRegion() / renderResolution() / railItems() / railFingerprint() / renderRail() / openReopenForm() / refreshCoding() — Loop workspace
File: src/gator_command/scripts/dashboard/views/loop.js
Render the governed planning loop workspace. A full-width tab bar runs across the top of the main pane (#72). It holds a derived **Primary** tab (**Create** or **Active**) and **History**. The list pane holds History only. The main content follows the mode: the creation form, the participant handoff, the selected-loop inspection, or the defensive conflict state.
<- loop route
-> loop list/status/events/artifact endpoints, control endpoints (pause/interject/unblock/end/extend), start endpoint, prompt endpoint, sketch-sources endpoint (`/api/repo-by-key/<repo_key>/...`)
! **Mode state**: `_state.mode` ("create" | "handoff" | "inspect" | "conflict") selects the main content renderer (`renderMainContent()` / `showMain()`).
  - `_state.handoffId` tracks the loop during participant handoff.
  - `_state.conflictIds` holds the sorted active ids while the conflict state is shown.
  - `_state.conflictChoice`: see below.
! **Primary tab (Active-tab simplification, 2026-10-21).** The first tab is derived from the loop list.
  - **Labels:** it reads **Create** (the creation form) when no loop is active, and **Active** (that loop's handoff or live workspace) when one is.
  - **Removed:** the `+ Create Loop` action, the sidebar Active section and card, and the "a loop is active" explanation. `renderActiveLoopExplanation()` and `.loop-sidebar-open-active` are gone; this supersedes the #56 explanation.
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
! **Primary reconciliation and list failure (2026-10-21).**
  - **`fetchLoops()`** returns the `loops` array, or **null** on a non-2xx response, a network error, an unparsable body, or a body without an array `loops`. It returns `[]` only for a genuinely empty list, the same rule as `fetchEvents()` (#44). A failure is never read as "no active loop". The create-form pickers (`loadRevisePicker`, `loadSourcePicker`) treat null as an empty list, as before.
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
    - **Failures:** a failed status or events response keeps the #44 behaviour. A failed list (null) keeps the workspace and `_state.loops`, shows the `refresh` slot's "Refresh failed — retrying.", and **never stops the timer** (see "Pending reconciliation keeps the timer").
    - **Clearing the notice:** `setRefreshFailed(false)` runs only after all three succeed.
    - **Terminal under Primary** (`view === "create"`): the poll does not patch first. It fetches the list and reconciles in the same poll, so no empty intermediate panel appears. If the list failed, or still lists the loop as active, it patches the terminal `/status` in place and keeps the timer, so the next poll reconciles.
    - **Terminal under History:** unchanged — the in-place patch, then the timer stops (except approved coding, #41).
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
! **Tabs and layout (#56; main-pane bar since #72; single tabpanel since 2026-10-21)**:
  - **Layout:** the mount skeleton is `.loop-workspace` (a column) holding two children:
    - `#loop-tabbar.gator-tabbar.loop-tabbar`: full width; it owns the baseline;
    - `.loop-workspace-body#loop-tabpanel[role=tabpanel]`: a row of `#loop-sidebar-nav` + `#loop-main-content`, stacked at ≤768px.

    `.loop-workspace` keeps `dataset.polling`, and gains `data-loaded="1"` once the first list has landed.
  - **Tabs:** `buildLoopTabs(container)` writes the tablist **once per mount**. It is a `role="tablist"` (`.loop-subnav`, the JS/test hook) with two `button.gator-tab.loop-subnav-tab[role=tab]` (`#loop-tab-create` / `#loop-tab-history`).
    - Both tabs have `aria-controls="loop-tabpanel"`. The workspace body is the single tab panel, the same pattern as `#app-shell` under the workspace strip.
    - Polls never rebuild the tablist, so a focused tab keeps focus.
  - **State:** `applyTabState(root)` writes, each only when it differs: `aria-selected`, the roving `tabindex` (0/-1), the body's `aria-labelledby` (`loop-tab-<view>`), and `#loop-sidebar-nav.hidden = (view !== "history")`. On Primary the list pane is hidden (`.loop-sidebar[hidden] { display: none }`), so `.loop-main` fills the body with no blank column.
  - **History list:** `renderHistoryList(loops, container)` draws only `#loop-history-list.loop-sidebar-section`: the header "History", "No completed loops" when empty, and the terminal cards newest first. It wires card clicks to `selectLoop()`.
    - It rewrites only when its fingerprint changes. The fingerprint is `listEl._gatorHistoryFp`, built per card from `[loop_id, stage, feature, mode key, counter text, date, selected]`. Unchanged polls therefore make no list writes.
    - The active loop is never listed.
  - **Inert until loaded (#72):** the bar exists from mount, but `switchTab()` returns early until `data-loaded="1"` (`isLoaded()`). Before that, `_state` may still hold the previous mount's selection, and a push would land ahead of the mount's landing `shellReplace()`. UI tests wait for `.loop-workspace[data-loaded="1"]` (`test_loop_workspace.py` `_navigate_to_loop()`).
  - **Keyboard:** Left, Right, Home and End switch the tab and focus it (automatic activation). The selected tab is shown by weight plus an underline (the shared `.gator-tab` Paper rule), never colour alone.
  - **`switchTab()`:**
    - `"create"` computes `primaryDecision()`. `keep` re-renders nothing, so a half-filled form, or a live workspace kept from History, survives. Anything else runs `applyPrimary(…, {record: "push"})`.
    - `"history"` changes only the list pane and the tab state. The main content stays until a card is chosen.
  - **Selection:** `selectLoop(id, opts)` sets inspect mode and the tab that matches the loop's state: a terminal loop → History, otherwise Primary.
  - **Mount default:** `applyDefaultSelection()` selects Primary and runs `landPrimary()` (`primaryDecision` against an empty display): none → Create, one → inspect it, many → the conflict state.
  - **Pinned by** `test_loop_subnav_tabs`, `test_primary_tab_reflects_active_state`, `test_loop_tabs_survive_polls`, `test_loop_tabs_inert_until_loops_load`, `test_loop_tabbar_spans_main_pane` and `test_active_conflict_state`.
  - **UI test fixture:** the `alpha` seed (`test_loop_seed.py`) holds four live loops on disk, so that each live state has a fixture. A list with several live loops is a #79 violation, and the view shows it as the conflict state.
    - **Default:** the autouse `_sole_active_loop` fixture in `tests/test_dashboard_ui/conftest.py` serves the real list through `_harness.sole_active_loop_list(page, "widget-refactor")`. That keeps the terminal loops plus one live loop, so every test lands on `widget-refactor` as before.
    - **Another live loop:** `_open_sole_active(page, fleet, feature)` makes a different live loop the only active one.
    - **Raw list:** `@pytest.mark.raw_loop_list` sees the raw seed (used by `test_active_conflict_state`).
    - **Own mocks:** a test's own list mock takes precedence. A held or counted request must be released with `route.fallback()`, not `route.continue_()`, so it still passes through the filter.
    - **Held lists:** a test that holds the `/loops` response must wait for the mounted view (`#loop-sidebar-nav`, `state="attached"`), never for `data-loaded`, which can only appear after the hold. `test_departed_mount_does_not_resurrect_polling` raced its own timeout this way (Ubuntu Source CI, 2026-10-22).
! **Loop history sub-state (#56)**: the shell owns history (see `navigate()` above). This view only contributes sub-state and registers **no** global listener.
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
! **Live vs history**: `renderSelectedLoop()` orchestrates live or read-only workspace. Live loops show the calm header with controls, the approval resolution (approved coding), source line, notices, the suspension card (#53, below), the Now line, the timeline, and the lower evidence section (artifacts, Candidate evidence, Participant recovery (#56), liveness, Decisions). Terminal loops show outcome header with badge (Approved/Max Rounds/Timed Out/Ended), completed date, no controls, no prompts.
! **Calm workspace layout (L1, checkpoint 1)**: region order is fixed by `buildLoopSkeleton()`:
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
  - **Header:** `renderLiveHeader()` is an eyebrow (`modeBadge` + `stageBadge`), the `<h3>` name and `.loop-counter-line` (`counterLineHtml()`: "Round X / Y", or for #55 loops "Checkpoint K of N · findings round r of b · Generation g" with `.loop-checkpoint-counter` / `.loop-generation-counter`). There is no status grid, no role ledger and **no time display** (Architect decision: the legacy countdown and the #47 "Elapsed this turn" are removed; `timeRemainingText` / `elapsedText` / `updateTimeRemaining` no longer exist; legacy timeout behavior is unchanged). Join state is shown by Participant recovery.
  - **Now line:** `nowLine(status, terminal)` is pure and status-only (stage, `next_role`, round, `checkpointCounters`, `pendingDecision`, `OUTCOME_LABELS`). It never reads artifacts, time, liveness, `/snapshot` or a missing event. It returns `{state, glyph, text}`: active ▶ "Now: <Role> — <stage> (round r of m | checkpoint k of n). No action needed from you."; blocked ⚑ (names the escalating role and decision id, points to Respond/Resume); paused ⏸; implementation approved ✓ (defers to the resolution banner); max rounds ■; other terminal ■ "Outcome: …". `renderNowLine()` writes `p.loop-now[data-state]`. Its fingerprint is the JSON of that object. The amber rule for blocked/paused is a second cue only. **Paper type:** `.loop-now` is reading prose (`--text-base` / `--leading-prose`). The checkpoint rail stays `--text-sm` (12px/1.5), lighter than the Now line.
  - **Controls in the header:** live: Interject, then quiet (`.loop-ctrl-quiet`) Pause and End; paused/blocked: the unblock button labelled by `unblockActionLabel()` ("Respond" with a pending decision, else "Resume"), then End. Hooks and `data-action` values are unchanged. `renderControls()` is **button-only** (L1, checkpoint 4): each button opens a dialog. Continue loop (max rounds) keeps its inline `renderContinueControl()` form.
  - **Focused intervention dialogs (L1, checkpoint 4):** `openLoopDialog(kind, status, invoker)` builds one native `<dialog class="loop-dialog" data-kind>` in the unpatched `#loop-dialog-host` and calls `showModal()` (focus trap, inert page, Escape → `cancel` → close without acting). Only click handlers open one, never a poll.
    - **Kinds:** `loopDialogConfig()` defines:
      - **decision:** the full request in `.loop-blocked-reason`, the "View decision request" link (closes the dialog without restoring focus, then `wireArtifactJump`), and "Requested … · Resumes: …"; the required "Response to <Role> (required)"; "Record response and resume" → `unblock`; plus **End loop instead…**, which swaps in the End dialog;
      - **resume:** optional message → `unblock`;
      - **interject:** required message → `interject`;
      - **pause** and **end:** each with a consequence sentence; end posts `reason`.
    - **Validation and posting:** the existing hooks are reused (`.loop-ctrl-input-area`, `#loop-ctrl-message.loop-ctrl-input` with `<label for>`, `.loop-ctrl-label`, `.loop-ctrl-timeout` for legacy loops only (`!status.attention`), `.loop-ctrl-confirm`, `.loop-ctrl-cancel`, `.loop-ctrl-error[role=alert]`). The existing validation is unchanged: required decision response (Confirm disabled while blank, blank refused), required interject message, legacy turn-window bounds. Sending goes through `postAction()` only. A failure keeps the dialog open with the input. **Paper type:** `.loop-dialog-note` (the explanation) and `.loop-dialog .loop-blocked-reason` (the request text) are reading prose (`--text-base` / `--leading-prose`). `.loop-dialog .loop-ctrl-label` and `.loop-ctrl-input` are `--text-ui`. The title (`--text-section`), the meta lines and the buttons are unchanged. On the canvas, the blocked alert stays compact. Success closes it, then `showUnblockNotice` (unblock) and `loadSelectedLoop()`.
    - **One request in flight (checkpoint 4 revision):** the pending action belongs to the selected-loop snapshot (`snap.pendingAction`), not to the dialog node.
      - **While sending:** the dialog's Cancel and End-instead are disabled, Confirm reads "Sending…", and the native `cancel` (Escape) is prevented. `setControlsPending()` disables the header dialog buttons (`#loop-controls .loop-ctrl-btn[data-action]`) and `.loop-blocked-respond`; `renderControls()` / `renderBlockedCard()` re-apply this on a rebuild. `openLoopDialog()` refuses with `DIALOG_PENDING_HTML` ("A request is still being sent…").
      - **If the browser still closes the dialog** (Escape without user activation), no second send is possible, and the completion is reported honestly in the action slot: "<title>: not sent — <error>", or "<title>: the request completed."
      - **On settle**, the pending state clears and the controls are usable again; a failure in an open dialog keeps the input for retry. The completion is dropped when the generation or snapshot changed.
    - **Focus:** closing removes the dialog and returns focus to the invoker, or `focusMainHeading()` if the invoker was rebuilt.
    - **Context change:** when `controlsFingerprint` changes, `renderSelectedLoop()` closes an open dialog unsent (`closeLoopDialog`) and writes `DIALOG_CHANGED_HTML` ("…nothing was sent") to the action slot. After rebuilding the controls it moves focus to the first enabled `#loop-controls` button, or `focusMainHeading()` (`focusAfterDialogInvalidated()`), so keyboard focus never falls to the document body. A dialog that is sending (`data-sending`) is left to its own completion, which reports to the action slot if the dialog is gone. Identical polls touch neither the controls nor the dialog, so a typed draft survives.
  - **Checkpoint rail (L1, checkpoint 2):** `#loop-region-rail` is filled only for declared-checkpoint coding loops (`checkpointCounters(status)` non-null); otherwise `renderRail()` leaves it empty, so there is no placeholder. `railItems()` reads only `status.coding.checkpoints` (`id`, `title`, `state`, `current`, `accepted_tree`): no plan parsing, no scope or Verify text, no request. Markup: `section.loop-rail[aria-label="Checkpoint progress"]` › `ol.loop-checkpoint-list` › `li.loop-checkpoint-item[data-state]` (✓ approved (tree …), ● active with `aria-current="step"` and weight 600, ○ not started). Glyph, text and weight carry the state; the amber rule and tint on the active item is a second cue. The rail is non-interactive; scroll-to-group is deferred (sketch). Fingerprint: `railFingerprint()` (the item list, or `"none"`). The list no longer appears in the coding facts panel, which keeps its Checkpoint and Generation rows.
  - **Decisions disclosure:** `syncDecisionsDisclosure()` writes only `hidden` (no decisions) and the summary count " (N)", each when it differs, and never touches `open`, so nothing opens automatically. `renderDecisionHistory()` no longer writes its own "Architect decisions" heading.
! **Mode projection (#56)** — `loopModeInfo(src)` / `modeBadge(info)` is the ONLY place loop-mode text is decided. It accepts a `/loops` item (normalized `mode` plus boolean `mode_legacy`) or a `/status` body (raw `mode`) and returns `{key, label}`:
  - `coding` → **Coding**;
  - no recorded mode (status `mode` absent, or list `mode_legacy === true`) → **Planning · legacy**;
  - `planning` / `planning-only` → **Planning**;
  - anything else → **Unknown mode**.

  It never reads feature names, filenames or artifacts. `modeBadge` renders `span.loop-mode-badge[data-mode]` with `aria-label="Loop mode: <label>"`: text plus a per-mode border (2px solid coding, solid planning, dashed legacy, dotted italic unknown), never colour alone. It appears in `renderLiveHeader`, `renderOutcomeHeader` and every History card (`renderSidebarCard`, inside `.loop-card-badges` next to the stage badge). `headerFingerprint` includes the mode key, so identical polls stay mutation-free (pinned).
! **Participant recovery (#56)** — `#loop-region-prompts`, live loops only (terminal: empty, no `.loop-prompt-copy`). It replaces the bare copy buttons.
  - **Structure:** `renderPromptSection(terminal, root, snap)` builds, once per live snapshot (prompts fingerprint `live`/`terminal`): `<details class="loop-recovery" id="loop-recovery">` with summary "Participant recovery", the fixed guidance ("Use these prompts only to start a new participant session or reconnect one that dropped. Do not paste a prompt into a session that has already joined."), the credential warning, and one `.loop-recovery-row[data-role]` per role (a `.loop-recovery-need` line plus the existing `button.loop-prompt-copy[data-role]` → `copyPrompt()`). Copying is unchanged (epoch guard, fallback, token non-persistence) and mutates no loop state.
  - **`recoveryNeed(role, joined, livenessState)`** (pure):
    - not joined → "Has not joined yet.";
    - joined and `stale` → "Watcher is stale — reconnect if the session dropped.";
    - joined and `released` → "Watcher exited after a notification — reconnect if the session closed.";
    - otherwise (connected, `not_registered`, closed, unknown or liveness unavailable) → none, shown as "Joined — no action needed".

    **TRIPWIRE (#52):** a joined role with no watcher (`not_registered`, e.g. a `gator loop wait` participant) is never flagged as absent.
  - **`applyRecovery(snap)`** runs after each `renderSelectedLoop()` (which stores `snap.statusRoles`) and at the end of `applyLiveness()`'s main path (`snap.liveness.lastView`).
    - It writes the need text (prefixed "⚠ "), the `data-need` flag (bold, never colour alone) and `open`, each only when it differs.
    - It changes `open` only when the need key changes: open when non-empty, close when empty. A manual toggle (`data-user-toggled`, set by a summary click) therefore holds until the need set changes.
    - Identical polls produce zero mutations (pinned).
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
  - **Blocked** (`.loop-decision-card`, `data-kind="architect_decision"`): L1 compact alert — "⚑ Blocked — awaiting your decision", then `decision-N · requested by <Role> · <time> · Resumes: <Role> · <stage>` and a `button.loop-blocked-respond` ("Respond", or "Resume" with no pending decision) that opens the decision (or resume) dialog. The full reason (`.loop-blocked-reason`, `white-space: pre-wrap`) and the "View decision request" link live in the decision dialog only.
  - **Paused** (`.loop-hold-card`, `data-kind="architect_hold"`): "⏸ Architect hold (paused)", "No participant response is required.", `Preserved:`, `Since:` and the pause reason. It never uses escalation wording.
  - **Telling them apart:** title text, glyph and border style (dashed for a hold), never colour alone.
  - **Fingerprint:** `blockedFingerprint` covers every field read, so unchanged polls are mutation-free (pinned).
! **Decision history (#53)** — `#loop-region-decisions`, `renderDecisionHistory()`, fingerprint `decisionsFingerprint` (ids + response kind/ts). It lists every `decisions[]` entry, including on terminal loops: the request (role, time, reason, "View request") and the resolution.
  - Resolution labels come from `RESPONSE_KIND_LABELS`, including "Cancelled — loop ended" for `cancelled_by_end`; an unknown kind shows "Resolved".
  - Each label carries a glyph: ✓ resolved, ○ pending (bold).
  - Text goes through `escHtml()` with pre-wrap. Artifact links reuse `wireArtifactJump()`.
! **Full-detail timeline events (#53)**: `FULL_DETAIL_EVENTS` (`loop_paused`, `loop_unblocked`, `escalated`, `architect_interjection`, `loop_ended_by_architect`) render their detail with `.loop-event-detail-full` (`pre-wrap`, no ellipsis), so a multi-line pause reason or unblock response stays readable after the hold ends. Other events keep the single-line ellipsis (pinned).
! **Unblock notice (#53)** — `showUnblockNotice()` writes the `action` slot after a successful unblock: "Unblocked. <Role> resumes at <stage> when its watcher or wait sees the change. The Dashboard does not run model work." It never claims model work.
! Architect controls are contextual: active loops show Interject/Pause/End; paused/blocked loops show Respond or Resume/End; terminal loops show no controls (max rounds: Continue). Each button opens a focused dialog (above); Interject requires a non-empty message. Controls POST via `postAction()` with anti-CSRF header and re-poll on success. Non-2xx control responses render a `.loop-ctrl-error` message in the dialog and keep it open with the input for retry.
! Unblock is decision-aware via `pendingDecision(status)`: with a pending decision (escalation) the field is labelled **Response to participant (required)**, Confirm stays disabled until non-blank, and blank input is refused before any request (text error + thicker border, not color alone); an ordinary Architect pause keeps **Message (optional)**. **Legacy loops only** (no `status.attention`): Unblock also shows a **Turn window (s)** number input defaulted to the session's `status.turn_timeout_seconds` (not a hard-coded 300), client-checked against `TURN_TIMEOUT_MIN/MAX` (mirrors `loop/session.py`), and sent as `timeout` only when changed. Attention-mode loops (#47) never show the field and never post `timeout` (`legacyWindow = !status.attention`). The Dashboard exposes no deliberate-empty (`no_response`) control — that exceptional path is CLI-only (`--no-response`). The server re-validates everything.
! **Incremental rendering (#38)**: `renderSelectedLoop()` builds a stable skeleton once per selection (`buildLoopSkeleton()` — regions listed under Calm workspace layout above; `#loop-region-notice` is unpatched, with named slots `refresh`, `action` and `attention` (#47), see below; `#loop-region-liveness` (#36) is field-patched, see below) and records `_state.render` = {generation, loopId, root, per-region fingerprints, timeline cursor}. The snapshot is invalid (skeleton rebuilt) when `_state.generation` or `selectedLoopId` changes or the root is detached; `teardownLoopView()` and a null status clear it. Every selection/mount/mode transition bumps `generation`, so no stale snapshot survives.
! Per poll, `patchRegion()` rewrites a region only when its fingerprint changes: `headerFingerprint()` (terminal, stage, round, `max_rounds`, identity, checkpoint counters, mode key — L1 dropped times, joins and next role), `now` (the `nowLine()` object), `blockedFingerprint()` (escalation + pending decision), prompts (live vs terminal), `controlsFingerprint()` (only renderControls() inputs: terminal, paused, pending decision id, turn window, `!!status.attention`), `artifactsFingerprint()` (event count + last event key + decision artifacts). An unchanged poll performs **no** main-panel DOM writes (L1 removed the countdown/elapsed text patch, the last permitted per-poll write; pinned with no exemption). `setAttentionNotice()` writes only when its derived state changes. Fingerprints use returned data, never wall-clock time.
! **#53 multiline input:** the shared control input (inside the L1 dialog) is `<textarea id="loop-ctrl-message" class="loop-ctrl-input" rows="4">` with `<label for>` association and an `aria-label` fallback. The required unblock label names the escalating role ("Response to Reviewer (required)"; "participant" when unknown). A typed draft survives unchanged polls with zero mutations in the controls, suspension and decision regions (pinned).
! Because controls and the dialog host are untouched unless the control inputs change, an open dialog (message / required response) survives polling without any "skip while composing" rule; if the control context really changes (e.g. unblocked elsewhere) the controls are rebuilt and the dialog closes unsent with a notice, which is correct.
! Timeline (L1, checkpoint 3): **newest first, grouped.**
  - **Scheme.** `snap.timelineScheme` is fixed on a snapshot's first render: `"checkpoint"` when `checkpointCounters(status)` is non-null, else `"round"`.
  - **Key.** `timelineGroupKey(ev, scheme, prevKey)` reads event fields only:
    - checkpoint scheme: `cp:<checkpoint_id>`; an untagged event inherits `prevKey` even when it has a `round`, so a pause, interjection, escalation, unblock or reopen stays in its checkpoint;
    - round scheme: `r:<round>`, inheriting when there is no numeric round;
    - leading keyless events: `start`.
  - **Groups.** `timelineGroups()` makes contiguous runs in chronological order: a recurring key after a different one opens a new group, so global newest-first order is never broken. `renderTimeline(events, root, scheme)` writes `section.loop-tl-group[data-group]` › `h4.loop-tl-group-label` ("Checkpoint cp2" / "Round 2" / "Start", from event fields, no status titles) › `.loop-tl-cards`, newest group first and newest card first. It returns the front key (`snap.frontGroupKey`).
  - **Patching.** `updateTimeline()` front-patches strictly-new events when the previously rendered newest event (`eventKey()`: ts|event|round) is still at the same index. Each new event is keyed with `prevKey = snap.frontGroupKey` (the same function as the full render) and inserted first in the front group, or as a new front group. Any other change redraws just `#loop-timeline`. Unchanged polls make no timeline writes. Cards still come from `eventCardHtml()` and stay link-only.
! Artifacts: `renderArtifacts(status, events, root, refreshMutable)` reconciles sections by `data-artifact` — existing nodes keep expanded state and loaded content and are only re-ordered; new ones come from `createArtifactSection()`; missing ones are removed. On event-log change (`refreshMutable`), `MUTABLE_ARTIFACTS` (`plan.current.md`, `findings.current.md`, `implementation.current.md`): loaded content refreshes in place if expanded, or is marked unloaded if collapsed. **#45:** collapsed artifact cards carry **no excerpt and never fetch**; `loadArtifactSummary()`, `isSummaryArtifact()` and the `.loop-artifact-summary` node were removed. `fetchArtifact()` uses `cache: "no-store"` so refreshes are real.
! Artifact fetch ordering: `loadArtifactContent()` bumps a per-node request revision (`nextRequestRev()` → `content._gatorContentRev`) before each fetch and apply a completion only if it is still the latest for that node (in addition to the generation and `isConnected` checks). An older in-flight response for a mutable artifact therefore cannot overwrite newer content. A refresh of a collapsed mutable section also bumps the content revision so an in-flight body fetch cannot mark it loaded with stale text; an expanded section (loaded or still loading) is always refetched.
! Terminal transition patches header/prompts/controls in place (never an empty intermediate panel), then polling stops. Under the Primary tab a finished loop is instead replaced in the same poll (see "Primary reconciliation and list failure").
! **Terminal is not always final (#39).** For `max_rounds_exceeded` (`EXTENDABLE_STAGE`) `renderControls()` delegates to `renderContinueControl()`: a **Continue loop** button opening **Additional rounds** (number, `ROUNDS_MIN..ROUNDS_MAX` = 1..20, mirrors `loop/session.py`, default 2) and **Reason (required)**. Confirm stays disabled until the reason is non-blank; invalid rounds or a blank reason are refused before any request with a text error (not colour alone). It POSTs `{rounds, message}` to `/extend` via `postAction()`. Every other terminal stage renders no controls. `controlsFingerprint()` includes the extendable-stage flag so this control is (re)built only when that input changes.
! On extend success: `showExtendNotice()` writes to `#loop-region-notice` — a skeleton region that incremental rendering never patches, so the notice survives the terminal-to-live transition (cleared only by a skeleton rebuild on selection change). It states old → new ceiling and the participant re-engagement step, plus a **Warning:** line when `watcher === "failed"` (timeouts not enforced) or a neutral line for `already_hosted`. Then `ensurePolling()` restarts the interval (polling had stopped at terminal) and sets `data-polling="1"`, `refreshSidebarOnly()` moves the loop to Active, and `loadSelectedLoop()` patches header/prompts/controls live while timeline and artifacts are preserved; the timeline appends the `loop_extended` card (`EVENT_LABELS.loop_extended = "Extended"`).
! **Architect brief (#43)**
  - **Create form.** An optional "Architect brief (optional, Markdown)" textarea with a **UTF-8 byte** counter: `briefByteLength()` uses `new TextEncoder()`, labeled "N / 32,768 bytes", never string length. Over the limit the counter adds "over the limit…" (bold and underlined), Create is disabled, and the submit path refuses too. A blank brief is omitted from the POST; the server stays authoritative.
  - **Artifact inspector.** `briefEntries(status)` reads only the strict status projection. A position is listed when its check is not `absent`, and LINKED only when its positionally bound view is non-null. The artifact name is always the fixed constant for that position, never metadata. Linked briefs sort right after the plan (L1: `renderArtifacts()` puts `approved-plan.md` / `plan.current.md` first, replacing the #43 brief-first order), labeled "Architect brief" / "Architect brief (this coding loop)" / "Architect brief — from approved plan", with "(required reading)" when ok or "[!! DIGEST MISMATCH]" (and the other states) as text.
  - **Text-only notes.** Invalid references ("…: INVALID REFERENCE — escalate to the Architect") and a dropped planning brief ("Planning brief: not carried forward (Architect's choice at coding start)") are notes in `.loop-brief-notes`, with no link and no fetch.
  - **Change detection.** Labels and notes are written only when they differ, and `artifactsFingerprint` includes the brief metadata, checks and decision, so identical polls produce zero mutations (pinned).
! **Coding-loop creation (#43 M2a):** the create form has a **Loop type** radio: "Planning — draft a plan from a sketch" or "Coding — implement an approved plan".
  - **Coding mode** hides the sketch field and shows "Approved planning loop", a select filled from `/loops` filtered to `mode === "planning" && stage === "plan_approved"`. With none, it shows "No approved planning loops to implement" and Create is disabled.
  - **Source brief state.** Selecting a source fetches that loop's `/status` (`loadSourceBrief`) behind two independent stale guards: a per-select `_create.sourceRev` revision, and a check that the select still shows that source. A stale response can never update the control (pinned; the test fails only when both guards are removed). While pending, the form says "Checking the approved plan's brief…" and Create is disabled.
  - **The keep/drop control** ("Include the approved plan's Architect brief", checked by default) is shown for every non-`absent` `brief_check`. Corrupt states add a text warning: "…failed its integrity check (DIGEST MISMATCH). Keeping it will fail; uncheck to start without it."; it is never auto-unchecked. A failed fetch shows "Brief state unknown"; the server decides. `absent` hides it, and `source_brief` is omitted.
  - **The POST** carries `mode`, `from_loop`, `source_brief` (`keep` / `drop` when shown) and the optional `brief`, never `sketch_path`. The server's honest error (for example, keep on a corrupt brief) appears in `#loop-create-error`.
  - **`updateCreateEnabled()`** combines the byte limit, no sources and pending source state.
! **Architect attention (#47 M5):** this is the Architect's own view; participants never see Dashboard time.
  - **Header:** L1 removed the "Elapsed this turn" item and the legacy "Time Remaining" countdown (Architect decision: no time display). The attention notice below is unchanged and is the Architect's attention signal.
  - **Notice:** `#loop-region-notice` gains a third slot, `attention`, owned only by `setAttentionNotice()`. It derives a state (`notified|<turn>`, `unrecorded|<turn>` when `due && !notified`, or empty) and writes the slot and the selected sidebar card's marker **only when that state changes**, so identical polls are mutation-free.
    - Notified text: "◷ Attention: Draftor has been active for at least 5 min in revision. The loop is still running — interject, pause, or end if needed; no action is required."
    - Unrecorded text (P2) follows **only** the server's authoritative `attention.host`:
      - `none`: "…no notice recorded — no loop host is running for this loop, so attention notices are not being recorded.";
      - `attached`: "…notice pending — the loop host records it on its next check.";
      - `unknown` or missing: neutral, "…no notice has been recorded for this turn yet."

      Host absence is never inferred from a missing marker. The state key includes the host value, so a host change rewrites the notice.
    - It uses `role="status"` and `.loop-attention-notice` (dashed border, glyph and bold label, never an error colour). It never touches the `refresh` / `action` slots or open controls, and clears when the turn changes or the loop pauses or ends.
  - **No sidebar marker (2026-10-21):** the `.loop-card-attention` "◷ attention" marker lived on the active-loop card and was removed with it; `setAttentionNotice` writes only the notice slot. The browser no longer reads the `/loops` item's `attention_notified` (the server field is unchanged).
  - **Unblock control:** `legacyWindow = !status.attention`. Attention loops never show the "Turn window (s)" field and never post `timeout`. The controls fingerprint includes `!!status.attention`.
  - **Create form:** the field is labelled "Architect attention interval (seconds)" with the hint "Architect notice only — participants never see it…", and posts `attention_interval`. The element id `#loop-turn-timeout` is kept.
! **Coding candidate panel (#41)**: `#loop-region-coding` (facts, inside the collapsed "Candidate evidence" disclosure) and `#loop-region-resolution` (the approval banner, next to the header), shown only when `status.mode === "coding"` (they use the slim `status.coding` projection). L1 split them by responsibility: `renderCodingRegion()` / `codingFingerprint(status)` (stage, round, `max_rounds`, projection) own the facts; `renderResolution()` / `resolutionFingerprint(status, live)` own the banner and Reopen.
  - **Facts:** the approved plan's source loop and sha, the base commit, and the latest candidate (round, staged tree / HEAD / branch or detached, changed-path counts by status), plus the review verdict with a "candidate had changed" note.
  - **Residue:** a "Note:" line when residue outside the loop directory is non-zero. Loop residue is never warned about.
  - **Live resolution (`implementation_approved` only):** `refreshCoding()` fetches the Architect-only `/snapshot` (no-store) and renders one banner. Each state is text plus a distinct glyph plus weight or style (`data-state`), never hue alone:
    - ✓ Committed (commit),
    - ● Pending commit — one normal commit,
    - ⚠ Stale (reason text from `STALE_REASON_TEXT`, word for word the CLI's `_STALE_REASONS`: `staged_tree_changed`, `head_moved_tree_differs`, `detached_mismatch`, `history_diverged`; an unmapped reason shows raw),
    - ? Unknown — never treat as approved. #67: when `live.live.guidance` is a string, a `div.loop-coding-guidance` shows it as escaped plain text under the banner (normal weight, gray; the glyph and label carry the state). The browser never parses Git text.

    The state comes from the server alone (#85). Committed survives later commits, with the historical approval commit, and a detached HEAD after approval reads Stale. The browser holds no Git-history logic.
  - **Reopen:** a **Reopen for revision** button appears only for Stale or Unknown. It opens an inline required-reason form, Reopen stays disabled while the reason is blank, and it POSTs `/reopen` `{message}` with `X-Gator-Dashboard`. The notice reports invalidation and the watcher state.
  - **Patching:** each region is rewritten only when its own fingerprint changes; the resolution region never while the Reopen form is open (`data-reopen-open` on `#loop-region-resolution`; Reopen's close deletes `snap.fp.resolution`). `resolutionFingerprint` includes the stage, resolution state, reason, commit, `approved_tree`, and the live `ok` / `error` / `guidance` (#67). Identical polls produce zero mutations (pinned).
  - **#55 checkpoints** apply when `status.coding.checkpoints` is present, which is declared loops only.
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
! **Refresh-failure visibility and notice ownership (#44):**
  - **Three named slots.** `#loop-region-notice` holds `[data-slot="refresh"]`, `[data-slot="action"]` and (#47) `[data-slot="attention"]`. `noticeSlot()` / `setNotice()` write exactly one slot.
    - **Action:** Architect action results only — `showExtendNotice()` (Continue), `showLivenessNotice()` (Re-notify), and the Reopen notice.
    - **Refresh:** owned solely by `pollLoop()` through `setRefreshFailed()`.
    - **Attention (#47):** owned solely by `setAttentionNotice()`, for attention-mode loops; it is empty for legacy loops.

    No path assigns the whole region's `innerHTML`, so clearing the refresh or attention notice can never erase an Architect message.
  - **On a failed poll** (`fetchStatus()` gives null, `fetchEvents()` gives **null**, or the list fetch gives null):
    - `pollLoop()` returns without rendering, so the last valid workspace, artifacts, open controls, expanded sections and scroll all survive, and polling continues on the same single timer;
    - it shows the text-led "Refresh failed — retrying." notice (`role="status"`).
  - **On recovery:** the next successful full status, events and list refresh clears only that notice. `setRefreshFailed()` writes only when the state changes, so repeated failures and successes are mutation-free.
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
! **Timeline cards never fetch; the summary comes from the event** (2026-10-04 follow-on to #45; #62):
  - **#62 summary from the event.** For an event with an `artifact_path`, `eventCardHtml()` renders, after the metadata and before the link, either `<p class="loop-event-executive">` + `escHtml(text)` for a valid projection, or `<p class="loop-event-executive loop-event-executive-absent">Executive summary unavailable for this artifact.</p>`. An event without `artifact_path` gets neither, whatever its `executive_summary` holds.
  - **#62 `eventSummary(ev)` (closed projection check).** It returns display text only when `ev.artifact_path` is present, `typeof ev.executive_summary === "string"`, and the value collapsed by `/\s+/g` → " " and trimmed is 1–`EXECUTIVE_SUMMARY_MAX` (1,200) Unicode code points, counted with `Array.from(text).length` (the CLI's `len()` unit; `String.length` would count an astral character twice and hide valid stored text); otherwise null (whitespace-only, wrong type, over-limit). Non-canonical whitespace is normalized for display, never rejected. `EXECUTIVE_SUMMARY_MAX` mirrors `submit.EXECUTIVE_SUMMARY_MAX` (pinned by `test_summary_bound_matches_cli`). Pure: event data only, never an artifact read; participant text is never HTML.
  - **#62 detail rule.** `PARTICIPANT_SUMMARY_EVENTS` (`draft_submitted`, `revision_requested`, `plan_approved`, `max_rounds_exceeded`, `implementation_submitted`, `checkpoint_approved`, `implementation_approved`) show only `ev.role` as detail, legacy events included, so a tree id or path count never competes with the paragraph. Every other event keeps today's detail logic, including `FULL_DETAIL_EVENTS`.
  - **#62 layout.** `.loop-event` wraps; `.loop-event-executive` and `.loop-event-link-row` take a full line (`flex-basis: 100%`). The paragraph is plain reading prose (`--text-base` / `--leading-prose` since Paper, 2026-10-23; 14px/1.5 before), normal weight, with no border or background. A card that carries one gets `padding: var(--space-3) 0` through `.loop-event:has(> .loop-event-executive)`; other cards keep 6px. The absence line is 12px italic `--gray-600`, and the words carry the meaning, never colour alone. The event time and label stay 12/13px, and "View full artifact" is `--text-sm` (it was 11px). This is CSS only: a front-patched card gets its final styling as it is built, with no reconciliation pass.
  - **Synchronous link.** `eventCardHtml()` renders the event metadata (time, label, escaped detail) and, for an event with an `artifact_path`, a link built from that metadata: `<a class="loop-timeline-artifact-link" href="#" data-artifact="…">View full artifact</a>` (`escHtml()`; `href="#"` makes it keyboard-focusable). The link never depends on an Executive Summary heading or on a fetch.
  - **Click binding only.** `wireTimelineCards()` only binds clicks: it **never fetches artifact text**.
  - **Following a link.** `openArtifactSection(parentEl, name)` (with a `CSS.escape`'d selector) scrolls to the matching artifact card and clicks its toggle **only if it is collapsed**. An open card stays open. The artifact is then fetched once, by the card's own #45 expand path, and opens Rendered by default with Raw as a toggle.
  - **Removed (2026-10-04, still absent):** `extractSummary()`, `SUMMARY_MAX_CHARS` / `SUMMARY_RE`, `window.GatorViews._extractSummary`, the `.loop-event-summary` / `.loop-timeline-summary-*` nodes and styles. #62 does NOT restore artifact extraction: the summary is the CLI's event projection, captured at submission.
  - **Pinned by** `tests/test_dashboard_ui/test_loop_workspace.py`: `test_timeline_card_summary_from_event` (#62: escaped paragraph between metadata and exactly one `href="#"` link, participant markup stays text, role-only detail, no `_extractSummary`); `test_timeline_projection_validity` (#62 bound: at-limit, normalized and an emoji at the 1,200-code-point limit shown; empty, whitespace, number, null, list, over-limit and an emoji at 1,201 code points → absence line; link kept); `test_timeline_absence_only_for_artifact_events` (#62: absence only on artifact cards, full Architect detail kept); no link on an event without an artifact; a link without an Executive Summary; **zero `/artifact/` requests** on initial render and on appended events (an appended event's summary comes from the event, #62) until a link is followed, then exactly one; an open section stays open with no refetch; keyboard Enter activation; and the existing navigation and round-zero link tests. Mutation-checked: a restored timeline fetch, an unconditional toggle, a missing link, and a missing `href` each fail it.

### GatorViews.docs() / showDoc() / select() (repo-independent Docs view, 2026-10-13)
File: src/gator_command/scripts/dashboard/views/docs.js
The Docs view: the shipped Gator HTML documents, from the installed package, the same list for every repository. A `nav.repo-sidebar.docs-sidebar` (`aria-label="Gator documents"`) lists `DOCS` in order with reader-friendly labels (library reading order: Gator overview, What Gator can do, Gatorize a repo, Start a session, then "Charter formation process", "Charter schema", "Code migrations"; deliberately not Welcome's tab order); `.repo-content.docs-content` holds one `iframe.repo-iframe.docs-frame` (`sandbox="allow-scripts"`, `title` = label) inside `.repo-iframe-wrapper`. Reuses the repo-browser classes so the `.route-repo` flex chain sizes it.
! **Product intent (Architect, 2026-10-13):** Docs is Gator's comprehensive documentation library, what someone coming from docs.python.org expects: the same everywhere and never a per-repository collection. Repository-specific understanding belongs in `.gator/blueprints/`, the charters and the other `.gator/` surfaces, not in Docs.
<- `showView("docs")` (always available; no repository needed)
-> `GET /api/welcome/docs/<doc>` (see `scripts-dashboard.md` → `read_welcome_html()`), or the `srcdoc` property from `window.GATOR_WELCOME_DOCS` in a snapshot (missing entry → `p.docs-status` notice). No repository API calls, no storage, no history calls.
- **State:** module-local `selectedDoc` (default `gator-overview.html`) survives reopening Docs while the page stays loaded; the active button gets `.active` and `aria-current="page"`. A click on another entry replaces the frame; a click on the active entry does nothing.
! Every `DOCS[i].doc` must be in `WELCOME_DOC_NAMES`; otherwise the frame shows the route's 404 body. Adding a document = file in `templates/gator-starter/docs/` + name in `WELCOME_DOC_NAMES` + entry in `DOCS`.
! The frame sandbox is exactly `allow-scripts` (same TRIPWIRE as Welcome). The Start-a-session copy button has no Welcome channel here; after its 1.5 s timeout the document shows its own manual-copy text, by design.
! The DOM is built with `createElement`/`textContent` only: no document text or label is interpolated into HTML.
- **Pinned by** `tests/test_dashboard_ui/test_docs_view.py`.

### GatorViews.welcome() / applyTopic() / selectTopic() / ensureFrame() / bindCopyListener() / isCopyRequest() / handleCopyRequest() / replyCopy() (#72; Welcome HTML documents)
File: src/gator_command/scripts/dashboard/views/welcome.js
The Welcome workspace: four topics (Start a session with Gator · Gator overview · What Gator can do · Gatorize a repo; the session topic is first and the default since 2026-10-15, for its copy-prompt button) in the shared main-pane tab bar. Each topic body is a shipped standalone HTML document in a sandboxed iframe.
<- `showView("welcome")` (live landing view from `init()`, the `#brand-home` logo button, and Back/Forward)
-> `GET /api/welcome/docs/<name>` (see `scripts-dashboard.md` → `read_welcome_html()`), or `window.GATOR_WELCOME_DOCS[name]` in a snapshot. No storage, no console output, no history calls.
- **Tabs:** `div.gator-tabbar.welcome-tabbar` > `[role=tablist][aria-label="Welcome topics"]` > four `button.gator-tab.welcome-tab[role=tab]` (`#welcome-tab-<key>`, `aria-controls`), and four `section[role=tabpanel][tabindex=0]` (`#welcome-panel-<key>`, `aria-labelledby`) in `.welcome-body`. `applyTopic()` writes `aria-selected`, roving `tabindex` and `hidden` only when they differ. Click selects; Left/Right (wrapping), Home and End select and focus. A switch never re-renders or calls the shell; it fetches only through `ensureFrame()` on a topic's first selection in a mount.
- **Topic state:** module-local `selectedTopic` (default `session`, the first tab). It survives reopening Welcome (logo, Back/Forward, Refresh) while the page stays loaded and resets on a fresh page load. It is never put in shell history (`sub` stays null).
- **Frames:** `TOPICS[i].doc` names each document. `applyTopic()` calls `ensureFrame(selectedTopic)`, which creates `iframe.welcome-frame` once per mount in the empty tabpanel. It sets `sandbox="allow-scripts"` and `title` = the tab label, plus `src` = `/api/welcome/docs/<doc>` live, or the `srcdoc` property from `GATOR_WELCOME_DOCS` when `window.GATOR_SNAPSHOT`. A missing or `null` snapshot entry gives `p.welcome-doc-status` (text notice naming `.gator/docs/<doc>`) instead. `frames` (module-local, reset per mount) holds them. A frame is never re-created or re-pointed while the mount lives, so revisiting a topic does not reload it. Reopening Welcome is a new mount.
- **Does not own document content:** layout, the overview's hero mark, and images live in the documents themselves (see `scripts-dashboard.md` → Document content rules). The view never styles or measures frame content.
! TRIPWIRE: every Welcome frame is sandboxed exactly `allow-scripts` (opaque origin); never add `allow-same-origin`, forms, popups, or top navigation. Document HTML never enters the Dashboard DOM: live frames use `src`, and snapshot frames use the `srcdoc` DOM property, never an attribute string. Documents are not navigation controllers: no tab switching, repository context, or endpoint access from a document.
- **Copy action:** `bindCopyListener(root, frames)` runs on every mount.
  - It removes the previous mount's `message` listener and installs one bound to this mount. That listener removes itself once its root is detached.
  - It calls `handleCopyRequest(event.source)` only when all of these hold: `frames.session` is a connected `IFRAME`; `event.source === frames.session.contentWindow`; `event.origin === "null"`; and `isCopyRequest(event.data)`.
  - `isCopyRequest(event.data)` requires a non-null object with prototype `Object.prototype`, exactly three own keys, `type === "gator-welcome"`, `v === 1`, and `action === "copy-session-prompt"`.
  - `handleCopyRequest()` writes `SESSION_PROMPT` with `navigator.clipboard.writeText`. `replyCopy()` then posts `{type:"gator-welcome", v:1, action:"copy-session-prompt-result", ok}` to that source only, plus `reason: "unavailable"` (no Clipboard API) or `"denied"` (rejected) when it fails. The target origin is `"*"` because an opaque origin cannot be named and the reply carries no secret.
  - The visible manual-copy fallback lives in the document (`start-a-session.html`), beside the already visible prompt.
! TRIPWIRE (copy protocol): only this mount's Start-a-session frame is accepted. Messages from the page, an unrelated frame, another Welcome frame, a stale frame (the previous mount's iframe, even if re-attached), a non-`"null"` origin, an unknown version or action, an extra key, an array or a string cause no clipboard write, no reply, and no topic, history, focus or network change. The prompt is never received from, sent to, logged by or exposed through a message: the reply has no prompt text. Never widen the accepted shape or sources without a new review.
! TRIPWIRE: `SESSION_PROMPT` is the exact vendor-neutral text from #72, as **one line** (Architect direction 2026-10-10: a pasted newline can submit early in terminal agent UIs). It names no vendor and no layout-dependent path (never `.gator/.includes/GATOR_INIT.md`): `gator init` reports the canonical path itself. It is never logged, stored, put in `data-*`, or put into history state.
! Welcome never calls `setActiveRepo` / `clearActiveRepo` and works without a registered repository or an active Loop.
- **Pinned by** `tests/test_dashboard_ui/test_welcome_ui.py`. Tests read frame content through `page.frame_locator(...)`, which waits for the (src or srcdoc) document to load; scanning `page.frames` right after the iframe appears races on slow runners (Windows CI run 38101334192).

### GatorViews.settings() — Settings view
File: src/gator_command/scripts/dashboard/views/settings.js
Render and update machine-local dashboard preferences exposed by the server.
<- settings route
! Client validation improves feedback but does not replace server-side shape validation.

### Paper tokens (Dashboard Paper visual system, 2026-10-19)
File: src/gator_command/scripts/dashboard/dashboard.css
The one token source for browser UI. It is the first `:root` block.
- **Type:** `--font-sans`, `--font-mono`, `--text-xs/sm/base/ui/nav/section/page` (11/12/16/14/13/18/30px), `--leading-compact/ui/prose`, `--weight-normal/medium/emphasis`, `--tracking-label`.
  - **Roles (Paper final-typography plan, 2026-10-23).** `--text-base` is the **reading-prose** role (the Now line, turn summaries, help and dialog explanations). `--text-ui` is **section/action text** (labels, row titles, the sidebar context name). Navigation uses `--text-nav`, technical metadata `--text-xs` / `--text-sm`, and code keeps its explicit 12–13px mono sizes.
  - ! **No text inherits the root type.** Every visible text element gets its size from an explicit rule or a token, and its line height from an explicit rule or a **compact-leading owner**. A compact-leading owner is a container that declares `line-height: var(--leading-ui)`: `#workspace-strip`, `#sidebar`, `#view-slot.route-repo` (Repo and Docs), `.view-header`, `.section`, `.card`, `.data-table`, `.gator-modal`, `.commits-view`, `.loop-workspace` and `.loop-dialog`. The former root inheritors are pinned to `--text-ui`: `.ctx-name`, `.repo-markdown p` / `li`, `.commit-subject`, `.commit-chev`, `.commit-body`, `.loop-recovery-summary` and `.loop-recovery-role`. `.gator-modal h3` is `--text-section` (it was the browser's 1.17em). `.gator-modal-body p` (the Fleet dialogs' explanation) is reading prose, `--text-base` / `--leading-prose`. A new surface needs an explicit role or one of these owners.
  - **Pinned by** `test_no_text_inherits_root_type` (`test_paper_shell.py`). For each of 11 surfaces (Fleet, the Add Repository modal, Repo Markdown, an expanded commit, Updates, Settings, Docs, the active Loop, the Interject and decision dialogs, and a terminal Loop), it sets `html` and `body` to sentinel values (23px / 2.3) without touching the tokens. It asserts that no visible text or form control changes its computed size or line height.
- **Neutrals and teal:** `--gray-50…900` (Tailwind gray), `--teal`, `--teal-dark`, `--teal-ink`, `--teal-light`, `--amber-light` (the tint behind amber-ruled notes, such as the Commits override note), `--focus-ring`.
- **Rhythm:** `--space-1…7` (4, 8, 12, 16, 24, 32, 48px) and `--radius-control` (6px) / `--radius-card` (8px).
- **Legacy names are aliases, not a second source.** In the second `:root` block, `--color-bg` (gray-50), `--color-border` (gray-200), `--color-text` (gray-800), `--color-muted` (gray-500) and `--color-link` (teal-ink) read the Paper scale, and `--font` / `--mono` alias `--font-sans` / `--font-mono`. View CSS that reads them follows Paper without a rewrite. Status colours (`--color-healthy` …) and `--sidebar-*` are not yet Paper (the sidebar moves with the Paper frame).
! **Final reading baseline (2026-10-23):** `html, body` is 16px/1.6 (`--text-base`, `--leading-prose`). It replaces the temporary 14px/1.5 baseline.
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
! **Body column (#80):**
  - **Layout:** `body` is a column flex box (`height: 100vh; overflow: hidden`) holding `#workspace-strip` and then `#app-shell`.
  - **The strip** is `flex: 0 0 var(--workspace-strip-height)` (46px since Paper; 36px before). It is one row that never wraps, and scrolls horizontally when narrow. The `#strip-status` region scrolls with it. Surfaces: gray-100 fill, gray-600 text, a gray-200 bottom border and gray-200 item seams.
  - **`#app-shell`** is `flex: 1; min-height: 0; position: relative`. It replaced `height: 100vh`, and the page still never scrolls.
  - **`#sidebar-toggle`** is `position: absolute` within `#app-shell` (no positioned ancestor between), so it sits below the strip. Its `top` centres it on the header (`(var(--topbar-height) - 28px) / 2`; 8px at ≤768px), and `left` is unchanged.
! **Paper frame (2026-10-19):**
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
! **Shared main-pane tab bar (#72):** `.gator-tabbar` is a full-width block that owns the 1px baseline (it reaches the main pane's right edge); `.gator-tabbar [role="tablist"]` wraps when narrow; `.gator-tab` keeps a fixed 13px label. Selected = `aria-selected="true"` → weight 600 plus a 3px teal underline (Paper; 700 and `currentColor` before); unselected = weight 400 gray-600, transparent underline; the Paper `:focus-visible` ring. Never colour alone. Loop's Create / History uses it; the old `.loop-subnav*` styles were removed (the class names remain as hooks).
! **Logo button (#72):** `.brand-home` resets button chrome around the unchanged `#brand-logo` sizing and adds a `:focus-visible` outline. Welcome content uses `.welcome-body` under the default `#view-slot` scrolling. It has no max-width and no side padding, so each topic frame spans the full main-pane content width, aligned with the tab bar. Each document sets its own reading width inside its frame (Architect direction 2026-10-10; this replaces the #72 760px cap). A column flex chain (`.welcome-workspace` `min-height: 100%` → `.welcome-body` `flex: 1` → `.welcome-panel:not([hidden])` `flex: 1` → `.welcome-frame` `flex: 1`) makes each topic iframe fill the main pane down to `#view-slot`'s bottom padding, so the bottom margin matches the side margins (Architect direction 2026-10-11; replaces the `100vh - 220px` estimate, which left ~66px unused). `.welcome-frame` is block, full width, no border, `min-height: 480px` (`420px` at ≤600px); below that the view slot scrolls. ! The panel rule must keep `:not([hidden])`: a bare `display: flex` would override the `hidden` attribute and show every topic. There is no auto-height cross-frame coordination: a document scrolls inside its frame. `.welcome-doc-status` styles the snapshot's unavailable-document notice. The old Markdown, list, next-button and copy rules were removed.
! Loop height chain: `.loop-workspace` (column, `height:100%`) → `.loop-workspace-body` (`flex:1; min-height:0`) keeps `.loop-sidebar` / `.loop-main` as the scroll owners.

## Before Changing This Module

- Confirm the backend wire schema and empty/error states.
- Exercise keyboard/mouse navigation and narrow/wide layouts.
- Run Playwright tests for mutations, file browsing, CSP liveness, iframe isolation, and preview controls.
- Keep the UI dependency-free unless the product architecture explicitly changes.

## Connections

-> [Dashboard Server](scripts-dashboard.md) - APIs, security, and content policy
-> [Session Archaeology](scripts-session-archaeology.md) - evidence identity and provenance
-> [Contracts](contracts.md) - Cumberland HTML compatibility
