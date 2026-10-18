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
  - **Welcome (#72):** `welcome` is a `VIEW_META` view ("Welcome to Gator!") shown on a live load without `?repo=` (see Landing view), and reached from the `#brand-home` logo button (`aria-label="Open Welcome"`; `navigate("welcome")`; `aria-current="page"` while it is shown) and from Back/Forward. Its `showView` branch never calls `setActiveRepo` / `clearActiveRepo`, and its entries carry `sub: null` (`cleanSub` stays Loop-only).
  - **Repository context:** `setActiveRepo(name, key)` (extracted from the `repo` branch) sets `activeRepo` / `activeRepoKey`, the "▸ <name>" Repo label, and un-dims Repo, Commits (`#history-tab`, since 2026-10-18) and Loop. `clearActiveRepo()` is its inverse (label "Repo", those tabs dimmed). The sidebar click handler ignores a dimmed item, so Commits, like Loop, does nothing until a repository is selected; without one the view would only show its "Select a repo" placeholder. **Docs is always enabled** (2026-10-13): it is repository-independent (`GatorViews.docs`), never dimmed, not guarded by the sidebar click handler, and its `showView` branch needs no active repository and shows no repo search box.
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
  - The strip holds a `div.workspace-tablist[role=tablist][aria-label="Open workspaces"]` of `div.workspace-item[role=presentation]`, each with:
    - `button.workspace-tab[role=tab]` (`#ws-tab-<id>`, `aria-selected`, `aria-controls="app-shell"`, roving `tabindex`, `data-ctx`), labelled with the repository display name. A context with no repository (`.workspace-tab-gator`) instead shows the white Gator mark (`img.workspace-tab-logo`, `gator-logo.png`, `alt=""`, 18 px, opacity 0.7, or 1 when selected). Its text is "Gator" in a visually hidden `span.workspace-tab-text`, so its accessible name and `textContent` stay "Gator", and its `title` is "No repository". Before 2026-10-17 this tab was labelled `—`;
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
- **Snapshot:** `init()` hides the strip and removes `#app-shell`'s tab-panel role.
! TRIPWIRE: inactive contexts are not live. Only the selected context is rendered, so switching tears down Loop polling, timers and listeners through `showView()`'s existing teardown. Never keep hidden DOM copies of other contexts.
- **Pinned by** `test_strip_spans_shell_above_sidebar`, `test_strip_aria_keyboard_and_close_labels`, `test_switch_restores_each_context`, `test_only_active_loop_context_polls` and `test_close_changes_navigation_only` in `tests/test_dashboard_ui/test_workspace_tabs.py`.

### fetch() / mutation requests — same-origin API calls from every view
File: src/gator_command/scripts/dashboard/dashboard.js
Call same-origin dashboard APIs and normalize errors for views.
<- all view modules
-> Dashboard server
! Every POST includes `X-Gator-Dashboard: 1`. Never add cross-origin fallback behavior.

### renderStandaloneRepos() / GatorViews.fleet() / placeMenu() / window.gatorNavToRepo() / window.gatorOpenRepoInNewContext() — Fleet view and actions
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

### openRemoveConfirmDialog() / remove handler
File: src/gator_command/scripts/dashboard/views/fleet.js
Confirmation dialog for removing a repo from the dashboard registry. Reuses the `.gator-modal` pattern.
<- overflow menu Remove action
-> `POST /api/repos/remove` (path-addressed)
! Registry-only operation — no filesystem access. Dialog text makes this explicit.
! Posts the registered path, not the display name.

### GatorViews.history() — Commits view
File: src/gator_command/scripts/dashboard/views/history.js
Render Git-native commit history and Gator trailer attribution.
<- history route (nav label and topbar title "Commits" since #56; the route key `history`, `data-view="history"` and the endpoint are unchanged)
-> repo history endpoint
! Accept both current Architect and legacy PI attribution supplied by the backend.
! **Stale-render guard (#56):** the commits fetch writes only while the "Loading history..." node it created is still attached. If another view owns `#view-slot` by the time the fetch resolves (for example after a quick Back), the result is dropped.

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

### buildLoopTabs() / ensureLoopPanels() / applyTabState() / switchTab() / renderLoopSidebar() / renderCreateWorkspace() / renderHandoff() / renderSelectedLoop() / buildLoopSkeleton() / patchRegion() / renderOutcomeHeader() / renderBlockedCard() / renderPromptSection() / renderControls() / renderContinueControl() / showExtendNotice() / ensurePolling() / updateTimeline() / renderTimeline() / renderArtifacts() / fetchLiveness() / postRenotify() / refreshLiveness() / applyLiveness() / openRenotifyForm() / fetchCodingSnapshot() / patchCodingRegion() / renderCodingRegion() / openReopenForm() / refreshCoding() — Loop workspace
File: src/gator_command/scripts/dashboard/views/loop.js
Render the governed planning loop workspace: a full-width Create / History tab bar across the top of the main pane (#72), a secondary list sidebar (Create: Create Loop + Active; History: terminal loops) and mode-driven main content (creation workspace or active-loop explanation, participant handoff, or selected-loop inspection).
<- loop route
-> loop list/status/events/artifact endpoints, control endpoints (pause/interject/unblock/end/extend), start endpoint, prompt endpoint, sketch-sources endpoint (`/api/repo-by-key/<repo_key>/...`)
! **Mode state**: `_state.mode` ("create" | "handoff" | "inspect") drives which main content renderer is called. `_state.handoffId` tracks the loop during participant handoff.
! **Create / History tabs (#56; main-pane bar since #72)**: `renderLoopSidebar()` classifies loops into active (non-terminal) and history (terminal, newest-first). It always draws both `.loop-sidebar-section-header`s ("Active", "History") once `/loops` returns, even when a section is empty (`.loop-sidebar-empty`). UI tests use the headers as the "list rendered" signal: `test_loop_workspace.py` `_navigate_to_loop()` waits for them, because `#loop-sidebar-nav` appears before the list (Windows CI races, 2026-10-18).
  - **Layout:** the mount skeleton is `.loop-workspace` (column) → `#loop-tabbar.gator-tabbar.loop-tabbar` (full width, owns the baseline) + `.loop-workspace-body` (row: `#loop-sidebar-nav` + `#loop-main-content`; stacks at ≤768px). `.loop-workspace` keeps `dataset.polling`.
  - **Tabs:** `buildLoopTabs(container)` writes a `role="tablist"` (`.loop-subnav`, the JS/test hook) with two `button.gator-tab.loop-subnav-tab[role=tab]`, **Create** and **History** (`#loop-tab-create` / `#loop-tab-history`, `aria-controls`), into `#loop-tabbar`, **once per mount**, right after the skeleton. `renderLoopSidebar()` never builds or rewrites it, so a focused tab keeps focus across polls.
  - **Panels:** the two `role="tabpanel"` containers (`#loop-panel-create` / `#loop-panel-history`, `aria-labelledby`) stay in `#loop-sidebar-nav`: they are the lists the tab chooses. `ensureLoopPanels(listEl)` replaces the sidebar's "Loading…" placeholder with them once; polls re-render only their contents.
  - **State:** `applyTabState(container)` looks tabs and panels up from the view container and writes `aria-selected`, roving `tabindex` (0/-1) and the inactive panel's `hidden` only when they differ (it skips silently until the panels exist).
  - **Inert until loaded (#72):** the bar exists from mount, but `switchTab()` returns early until `#loop-panel-create` exists (the first `/loops` response). Before that, `_state` still holds the previous mount's mode/loops, and a push would land ahead of the mount's landing `shellReplace()`. ARIA relationships cross containers (tablist in the bar, panels in the sidebar); DOM order keeps the tablist before its panels.
  - **Pinned by** `test_loop_subnav_tabs` (roles, roving tabindex, keys; `_tab_state` asserts the tablist is in `#loop-tabbar` and not in `#loop-sidebar-nav`), `test_loop_tabs_survive_polls` (tablist node and focus survive polls), `test_loop_tabs_inert_until_loops_load` (a pre-load click adds no history entry and the mount lands on its default; mutation-checked), and `test_loop_tabbar_spans_main_pane` (bar from the sidebar's left edge to the pane's content edge, above both columns; weight + underline; a half-filled form survives History → Create).
  - **Keyboard:** Left/Right/Home/End switch and focus the tab (automatic activation). The selected tab is shown by weight plus an underline, never colour alone.
  - **`_state.view`** (`"create" | "history"`) selects the tab. `_state.mode` keeps its meaning.
  - **Create panel:** the always-actionable `.loop-sidebar-create` button and the "Active" section (active cards only). The active loop is never listed in History.
  - **History panel:** the "History" section with terminal loops only. The `.loop-sidebar-section(-header)` markup is kept inside the panels.
  - **`switchTab()`:** Create switches the main content to the creation workspace (unless already there, so a half-filled form survives). History changes only the list; the main content stays until a card is chosen.
  - **Selection:** `selectLoop(id)` sets inspect mode and the tab that matches the loop's terminal state.
  - **Mount default unchanged:** an active loop opens in inspect with the Create tab selected; otherwise Create.
! **Active-loop explanation (#56)**: with an active loop, `renderCreateWorkspace()` calls `renderActiveLoopExplanation()` instead of rendering a form. It shows: "A **<Mode>** loop ‘<feature>’ is active (<stage>). Only one loop runs at a time.", plus the mode and stage badges, the counter text, and an **Open active loop** button (`.loop-sidebar-open-active`). The button selects the loop (inspect) and focuses its heading. With no active loop the form renders exactly as before.
! **Loop history sub-state (#56)**: the shell owns history (see `navigate()` above). This view only contributes sub-state and registers **no** global listener.
  - **Recording:** `currentSub()` gives `{view, mode, loopId}`; a handoff is recorded as inspect of that loop. User selections call `shellPush()` → `GatorShell.pushSubState`: tab switch, card select, Create Loop, Open active loop, the 409 "Open active loop" link, create → handoff, and handoff → Open loop workspace.
  - **Restoring the tab:** `applySub()` restores the recorded `sub.view` as recorded, in both modes. A History tab chosen while an active loop stays inspected comes back as History; it is never derived from the loop's stage (pinned).
  - **Mount:** `views.loop(…, initialSub)` applies `initialSub` through `applySub()` when its loop still exists (else `applyDefaultSelection()`), records the landing state with `shellReplace()` (no new entry), and focuses the main heading after a restore.
  - **`views.loop.restore(sub)`** applies a sub-state to the mounted view: it bumps `generation`, re-renders the sidebar, then `loadSelectedLoop()` or `renderMainContent()`, and moves focus to the main heading (`focusMainHeading()`). It never pushes.
! **Creation workspace**: `renderCreateWorkspace()` renders feature name, sketch source picker (dropdown from `/sketch-sources` + manual path toggle), advanced settings disclosure (max rounds 1–20, turn timeout 30–3600s), and Create button calling existing start endpoint. Client-side validation before POST. 409 "active loop exists" is race-recovery only (shows "Open active loop").
! **Participant handoff**: `renderHandoff()` shows prompt-copy cards for Draftor and Reviewer roles. `copyPrompt()` fetches from the no-store prompt endpoint, writes to clipboard, then nulls the prompt variable. Clipboard unavailable: shows read-only textarea fallback, removed on dismiss. Join state polls at 3s interval; Draftor joining does NOT remove Reviewer copy action. "Open loop workspace" navigates to inspect mode explicitly — never auto-navigates on join.
! **Token non-persistence**: prompt text never stored in localStorage, sessionStorage, URL state, data- attributes, or console logs. JS variable nulled after clipboard write. DOM elements removed on navigation.
! **Live vs history**: `renderSelectedLoop()` orchestrates live or read-only workspace. Live loops show status header, suspension card (#53, below), decision history, the Participant recovery disclosure (#56, below), controls, timeline, artifacts. Terminal loops show outcome header with badge (Approved/Max Rounds/Timed Out/Ended), completed date, no controls, no prompts.
! **Mode projection (#56)** — `loopModeInfo(src)` / `modeBadge(info)` is the ONLY place loop-mode text is decided. It accepts a `/loops` item (normalized `mode` plus boolean `mode_legacy`) or a `/status` body (raw `mode`) and returns `{key, label}`:
  - `coding` → **Coding**;
  - no recorded mode (status `mode` absent, or list `mode_legacy === true`) → **Planning · legacy**;
  - `planning` / `planning-only` → **Planning**;
  - anything else → **Unknown mode**.

  It never reads feature names, filenames or artifacts. `modeBadge` renders `span.loop-mode-badge[data-mode]` with `aria-label="Loop mode: <label>"`: text plus a per-mode border (2px solid coding, solid planning, dashed legacy, dotted italic unknown), never colour alone. It appears in `renderLiveHeader`, `renderOutcomeHeader` and every sidebar card (`renderSidebarCard`, inside `.loop-card-badges` next to the stage badge). `headerFingerprint` includes the mode key, so identical polls stay mutation-free (pinned).
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

### responsive shell
File: src/gator_command/scripts/dashboard/dashboard.css
Maintain the sidebar/topbar/content flex chain and usable narrow-screen layout.
<- all views
! Repository content and iframe containers need `min-width: 0`; HTML preview retains a visible minimum height and scrollable overflow.
! **Body column (#80):**
  - **Layout:** `body` is a column flex box (`height: 100vh; overflow: hidden`) holding `#workspace-strip` and then `#app-shell`.
  - **The strip** is `flex: 0 0 var(--workspace-strip-height)` (36px). It is one row that never wraps, and scrolls horizontally when narrow.
  - **`#app-shell`** is `flex: 1; min-height: 0; position: relative`. It replaced `height: 100vh`, and the page still never scrolls.
  - **`#sidebar-toggle`** is `position: absolute` within `#app-shell` (no positioned ancestor between), with unchanged offsets, so it sits below the strip.
  - **Selected tab:** weight 700 plus a 3px `currentColor` underline (border-bottom); never colour alone.
! **Shared main-pane tab bar (#72):** `.gator-tabbar` is a full-width block that owns the 1px baseline (it reaches the main pane's right edge); `.gator-tabbar [role="tablist"]` wraps when narrow; `.gator-tab` keeps a fixed 13px label. Selected = `aria-selected="true"` → weight 700 plus a 3px `currentColor` underline; unselected = weight 400, transparent underline; `:focus-visible` outline. Never colour alone. Loop's Create / History uses it; the old `.loop-subnav*` styles were removed (the class names remain as hooks).
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
