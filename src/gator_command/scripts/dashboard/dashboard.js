/**
 * dashboard.js — Gator Dashboard shell controller.
 *
 * Responsibilities:
 *   - Load Tier 1 data from /api/data (or window.DASHBOARD_DATA in snapshot mode)
 *   - Route sidebar clicks to view modules
 *   - Handle ?repo=<name> query param to pre-load Repo view
 *   - Manage Refresh button (re-fetches /api/refresh then /api/data)
 *   - Update the topbar title (title only; Paper) from the active view
 *   - Own browser history for every view (#56): navigate() pushes, one
 *     popstate handler restores; views add sub-state via window.GatorShell
 *
 * View modules register via window.GatorViews.<name> = function(data, container, ...extras)
 */

(function () {
  "use strict";

  // ── state ──────────────────────────────────────────────────────────────────

  const state = {
    data: null,          // fast_data from server
    activeView: "fleet",
    activeRepo: null,    // name of currently loaded repo (Repo view)
    activeRepoKey: null, // path-hash key for session audit identity
    settings: null,      // dashboard settings (mode, etc.)
    mountedLoopKey: undefined, // repo key the mounted Loop view uses (#56); undefined = no Loop mounted
  };

  // #56: true while a popstate restoration runs; nothing pushes meanwhile.
  let restoring = false;
  // #70: incremented by every showView(). init() compares it across its
  // /api/data await so a navigation made meanwhile is never replaced by
  // the landing view.
  let viewRenders = 0;

  // ── view metadata ─────────────────────────────────────────────────────────

  const VIEW_META = {
    fleet:    { title: "Fleet",    subtitle: "" },
    history:  { title: "Commits",  subtitle: "" },
    repo:     { title: "Repo",     subtitle: "" },
    docs:     { title: "Docs",     subtitle: "" },
    updates:  { title: "Updates",  subtitle: "" },
    loop:     { title: "Loop",     subtitle: "" },
    settings: { title: "Settings", subtitle: "" },
    welcome:  { title: "Welcome to Gator!", subtitle: "" },
  };

  // #80: browser-tab title labels. Views not listed use VIEW_META's title.
  const TITLE_LABELS = { welcome: "Welcome", history: "Commits" };
  // Views that never show a repository in the title.
  const TITLE_NO_REPO = { fleet: true, welcome: true };
  const TITLE_REPO_MAX = 60;

  // ── DOM refs ───────────────────────────────────────────────────────────────

  const viewSlot       = document.getElementById("view-slot");
  const generatedAt    = document.getElementById("generated-at");
  const refreshBtn     = document.getElementById("refresh-btn");
  const repoTab        = document.getElementById("repo-tab");
  const loopTab        = document.getElementById("loop-tab");
  const historyTab     = document.getElementById("history-tab");
  const sidebarContext = document.getElementById("sidebar-context");
  const topbarTitle    = document.getElementById("topbar-title");
  const brandHome      = document.getElementById("brand-home");

  // ── sidebar toggle ────────────────────────────────────────────────────────

  const sidebarToggle = document.getElementById("sidebar-toggle");
  const sidebar = document.getElementById("sidebar");
  if (sidebarToggle && sidebar) {
    sidebarToggle.addEventListener("click", function () {
      sidebar.classList.toggle("collapsed");
    });
  }
  const repoTools      = document.getElementById("topbar-repo-tools");
  const snapshotGeneratedAt = document.getElementById("snapshot-generated-at");

  // ── data loading ───────────────────────────────────────────────────────────

  async function loadData() {
    if (window.DASHBOARD_DATA) {
      // Snapshot mode — data is already inlined
      return window.DASHBOARD_DATA;
    }
    const resp = await fetch("/api/data");
    if (!resp.ok) throw new Error(`/api/data returned ${resp.status}`);
    return resp.json();
  }

  function updateTimestamp(ts) {
    if (!ts) return;
    try {
      const d = new Date(ts);
      generatedAt.textContent = "Updated " + d.toLocaleTimeString();
      // A snapshot hides the strip (and #generated-at with it), so the
      // banner carries the capture time.
      if (window.GATOR_SNAPSHOT && snapshotGeneratedAt) {
        snapshotGeneratedAt.textContent = "at " + d.toLocaleString();
      }
    } catch (_) {
      generatedAt.textContent = ts;
    }
  }

  // ── topbar ─────────────────────────────────────────────────────────────────

  // Paper: the header shows the title only. #topbar-subtitle stays in the
  // DOM, hidden and never written.
  function updateTopbar(name) {
    const meta = VIEW_META[name] || { title: name };
    topbarTitle.textContent = meta.title;
  }

  // ── browser-tab title (#80) ───────────────────────────────────────────────
  //
  // The title is a pure function of the shell's view and repository display
  // name (the registry name, never repository content or a file path).
  // showView() sets it on every exit, so every landing, navigation, refresh
  // and restore path is covered.

  function formatDocumentTitle(view, repo) {
    const meta = VIEW_META[view];
    const label = TITLE_LABELS[view] || (meta ? meta.title : "");
    const parts = ["Gator"];
    if (repo && !TITLE_NO_REPO[view]) {
      const name = String(repo);
      parts.push(name.length > TITLE_REPO_MAX
        ? name.slice(0, TITLE_REPO_MAX - 1) + "…" : name);
    }
    if (label) parts.push(label);
    return parts.join(" · ");
  }

  function updateDocumentTitle() {
    document.title = formatDocumentTitle(state.activeView, state.activeRepo);
  }

  // ── view routing ───────────────────────────────────────────────────────────

  // ── active repository context (#56) ───────────────────────────────────────

  function fleetRepos() {
    return (state.data && state.data.fleet && state.data.fleet.repos)
      || (state.data && state.data.repos) || [];
  }

  // Paper sidebar context card (#sidebar-context): the active repository's
  // name, branch and Gator version from its Fleet record (by key, else by
  // name), or the empty state. Text nodes only: names and branches are
  // never parsed as markup.
  function contextEl(tag, cls, text) {
    const el = document.createElement(tag);
    el.className = cls;
    el.textContent = text;
    return el;
  }

  function renderSidebarContext() {
    if (!sidebarContext) return;
    sidebarContext.textContent = "";
    if (!state.activeRepo) {
      sidebarContext.appendChild(contextEl("div", "ctx-name ctx-empty", "None selected"));
      sidebarContext.appendChild(contextEl("div", "ctx-meta", "Choose one in Fleet"));
      return;
    }
    const repos = fleetRepos();
    const rec = (state.activeRepoKey && repos.find(r => r.repo_key === state.activeRepoKey))
      || repos.find(r => r.name === state.activeRepo) || {};
    // Both lines are cut off with an ellipsis; `title` gives the full text
    // on hover (a property, so it stays plain text).
    const nameEl = contextEl("div", "ctx-name", state.activeRepo);
    nameEl.title = state.activeRepo;
    sidebarContext.appendChild(nameEl);
    const meta = document.createElement("div");
    meta.className = "ctx-meta";
    if (rec.branch) meta.appendChild(contextEl("span", "ctx-branch", String(rec.branch)));
    if (rec.cli_version) {
      if (rec.branch) meta.appendChild(document.createTextNode(" · "));
      meta.appendChild(document.createTextNode("Gator "));
      meta.appendChild(contextEl("span", "ctx-version", String(rec.cli_version)));
    }
    if (meta.firstChild) {
      meta.title = meta.textContent;
      sidebarContext.appendChild(meta);
    }
  }

  // Repo/Commits/Loop need a repository. A dimmed item also carries
  // aria-disabled and an explanatory title (a non-colour cue); the
  // sidebar click handler still keys on the `dimmed` class.
  const REPO_ITEM_HINT = "Choose a repository in Fleet first";

  function setRepoItemsEnabled(enabled) {
    [repoTab, historyTab, loopTab].forEach(item => {
      if (!item) return;
      item.classList.toggle("dimmed", !enabled);
      if (enabled) {
        item.removeAttribute("aria-disabled");
        item.removeAttribute("title");
      } else {
        item.setAttribute("aria-disabled", "true");
        item.title = REPO_ITEM_HINT;
      }
    });
  }

  // Set the shell's repository context: name, API key, the sidebar
  // context card, and the Repo/Commits/Loop items enabled. Docs is
  // repository-independent and always enabled.
  function setActiveRepo(repoName, repoKey) {
    state.activeRepo = repoName;
    state.activeRepoKey = repoKey || null;
    renderSidebarContext();
    setRepoItemsEnabled(true);
  }

  // Inverse of setActiveRepo(): the initial page state.
  function clearActiveRepo() {
    state.activeRepo = null;
    state.activeRepoKey = null;
    renderSidebarContext();
    setRepoItemsEnabled(false);
  }

  // ── browser history (#56) ──────────────────────────────────────────────────
  //
  // The shell is the ONLY owner of Dashboard history entries. Entries are
  // state-only (URL unchanged) and carry no token, prompt or artifact text:
  // {gatorDashboard: 1, view, repo, repoKey, sub}. `sub` is Loop-only
  // ({view, mode, loopId}); views contribute it through window.GatorShell.

  function cleanSub(sub) {
    if (!sub || typeof sub !== "object") return null;
    return {
      view: sub.view === "history" ? "history" : "create",
      mode: sub.mode === "inspect" ? "inspect" : "create",
      loopId: typeof sub.loopId === "string" ? sub.loopId : null,
    };
  }

  function shellState(sub) {
    const ws = workspace();
    const active = ws && ws.isHydrated() ? ws.active() : null;
    return {
      gatorDashboard: 1,
      view: state.activeView,
      repo: state.activeRepo,
      repoKey: state.activeRepoKey,
      sub: state.activeView === "loop" ? cleanSub(sub) : null,
      ctx: active ? active.id : null,  // #80: the workspace context shown
    };
  }

  // ── shell URL (#80) ───────────────────────────────────────────────────────
  //
  // The URL names the active context: `repo` (registry display name) and
  // `view`. Canonical forms: `?repo=<name>` for the Repo view (the legacy
  // link), `?repo=<name>&view=<view>` for other views with a repository,
  // `?view=<view>` without one, and no query for Welcome without one. Loop
  // `sub` stays in history state only. Snapshot (file:) entries keep the
  // URL unchanged.

  function shellUrl(view, repo) {
    const params = new URLSearchParams();
    if (repo) params.set("repo", repo);
    if (repo ? view !== "repo" : view !== "welcome") params.set("view", view);
    const query = params.toString();
    return query ? "?" + query : window.location.pathname;
  }

  // The URL's context: {repo, view}. A `view` that is not a VIEW_META key
  // and an empty `repo` are ignored (null).
  function parseShellUrl() {
    const params = new URLSearchParams(window.location.search);
    const repo = params.get("repo") || null;
    const view = params.get("view");
    return {
      repo: repo,
      view: view && Object.prototype.hasOwnProperty.call(VIEW_META, view) ? view : null,
    };
  }

  function recordShell(method, sub) {
    const entry = shellState(sub);
    if (window.GATOR_SNAPSHOT) history[method](entry, "");
    else history[method](entry, "", shellUrl(entry.view, entry.repo));
    syncWorkspace(entry.sub);
  }

  // ── workspace contexts (#80) ──────────────────────────────────────────────
  //
  // workspace.js keeps the per-tab list of contexts. The shell
  // stays the only router: it records what is on screen as the active
  // context. Snapshots (a static fleet report) have no workspaces.

  function workspace() {
    return !window.GATOR_SNAPSHOT && window.GatorWorkspace ? window.GatorWorkspace : null;
  }

  if (workspace()) {
    workspace().configure({
      isView: v => typeof v === "string" && Object.prototype.hasOwnProperty.call(VIEW_META, v),
      cleanSub: cleanSub,
    });
  }

  function syncWorkspace(sub) {
    const ws = workspace();
    if (!ws) return;
    ws.syncActive({ view: state.activeView, repo: state.activeRepo,
                    repoKey: state.activeRepoKey, sub: sub || null });
    renderWorkspaceStrip();
  }

  // ── workspace strip (#80, checkpoint 4) ──────────────────────────────────
  //
  // Select, + and close change navigation state only: no registry or Loop
  // request. Selecting renders through applyShellEntry() (whose showView()
  // tears the previous view down: inactive contexts are not live) and
  // records one ordinary history entry.

  const workspaceStrip = document.getElementById("workspace-strip");
  // renderStrip() empties its container on a rebuild, so it gets only the
  // tabs region; #strip-status (timestamp, Refresh) is a sibling.
  const workspaceTabs = document.getElementById("workspace-tabs");
  const appShell = document.getElementById("app-shell");

  function renderWorkspaceStrip(opts) {
    const ws = workspace();
    if (!ws || !workspaceTabs) return;
    const tabId = ws.renderStrip(workspaceTabs, {
      onSelect: id => selectContext(id),
      onClose: id => closeContext(id),
      onNew: newContext,
    }, opts);
    if (tabId && appShell) appShell.setAttribute("aria-labelledby", tabId);
  }

  function selectContext(id, opts) {
    const ws = workspace();
    if (!ws) return;
    const current = ws.active();
    if (current && current.id === id && !(opts && opts.force)) return;
    const ctx = ws.select(id);
    if (!ctx) return;
    // A repository that is no longer registered leaves the context
    // without one, on Fleet with the notice; never another repository.
    const gone = ctx.repo !== null && !validateRepo(ctx.repo, ctx.repoKey);
    applyShellEntry(gone
      ? { gatorDashboard: 1, view: "fleet", repo: null, repoKey: null, sub: null }
      : { gatorDashboard: 1, view: ctx.view, repo: ctx.repo, repoKey: ctx.repoKey,
          sub: ctx.sub });
    if (gone) showFleetNotice("That repository is no longer registered.");
    recordShell("pushState", state.activeView === "loop" ? ctx.sub : null);
    renderWorkspaceStrip({ focusActive: !!(opts && opts.focus) });
  }

  function newContext() {
    const ws = workspace();
    if (!ws) return;
    const ctx = ws.create({ repo: null, view: "welcome" });
    if (ctx) selectContext(ctx.id, { focus: true });
  }

  function closeContext(id) {
    const ws = workspace();
    if (!ws) return;
    const current = ws.active();
    if (!current || current.id !== id) {
      ws.remove(id);  // inactive: no navigation, no history entry
      renderWorkspaceStrip();
      return;
    }
    const next = ws.neighbourOf(id);
    ws.remove(id);
    if (next) {
      selectContext(next.id, { force: true, focus: true });
      return;
    }
    const fresh = ws.create({ repo: null, view: "welcome" });
    if (fresh) selectContext(fresh.id, { force: true, focus: true });
  }

  // A cached context's repository → its current registry identity, or
  // null when it is no longer registered (never another repository).
  function validateRepo(repo, repoKey) {
    const repos = fleetRepos();
    const info = repoKey
      ? repos.find(r => r.repo_key === repoKey)
      : repos.find(r => r.name === repo);
    return info ? { repo: info.name, repoKey: info.repo_key || null } : null;
  }

  // After landing (or the #70 re-render): merge the per-tab cache around
  // the context the shell is showing.
  function hydrateWorkspace() {
    const ws = workspace();
    if (!ws) return;
    ws.load({ view: state.activeView, repo: state.activeRepo,
              repoKey: state.activeRepoKey, sub: null }, validateRepo);
    // The current entry now names its context (keeping a Loop sub the
    // mount may already have recorded). This also draws the strip.
    recordShell("replaceState", isShellEntry(history.state) ? history.state.sub : null);
  }

  // User navigation: render, then record one history entry.
  function navigate(name, extra, repoKeyOverride) {
    showView(name, extra, repoKeyOverride);
    if (!restoring) recordShell("pushState", null);
  }

  window.GatorShell = {
    pushSubState: function (sub) {
      if (restoring || state.activeView !== "loop") return;
      recordShell("pushState", sub);
    },
    replaceSubState: function (sub) {
      if (state.activeView !== "loop") return;
      recordShell("replaceState", sub);
    },
    isRestoring: function () { return restoring; },
  };

  function isShellEntry(entry) {
    return !!entry && typeof entry === "object" && entry.gatorDashboard === 1
      && Object.prototype.hasOwnProperty.call(VIEW_META, entry.view)
      && (entry.repo === null || typeof entry.repo === "string")
      && (entry.ctx === undefined || entry.ctx === null || typeof entry.ctx === "string");
  }

  function showFleetNotice(text) {
    const note = document.createElement("div");
    note.className = "shell-notice";
    note.setAttribute("role", "status");
    note.textContent = text;
    viewSlot.insertBefore(note, viewSlot.firstChild);
  }

  // The single restoration path: validate -> hydrate the repository
  // context -> dispatch. showView() never restores state itself.
  function restoreShellState(entry) {
    if (!isShellEntry(entry)) return;
    applyShellEntry(entry);
  }

  // Hydrate the repository context, then dispatch (#80: shared by
  // restoreShellState() and the init() landing). An unregistered
  // repository falls back to Fleet with a visible notice.
  function applyShellEntry(entry) {
    if (entry.repo !== null) {
      const repos = fleetRepos();
      // The fleet's current key is authoritative; the recorded key only
      // disambiguates same-named repositories.
      const info = repos.find(r => r.name === entry.repo && r.repo_key && r.repo_key === entry.repoKey)
        || repos.find(r => r.name === entry.repo);
      if (!info) {
        clearActiveRepo();
        showView("fleet");
        showFleetNotice("That repository is no longer registered.");
        recordShell("replaceState", null);
        return;
      }
      setActiveRepo(info.name, info.repo_key || null);
    } else {
      clearActiveRepo();
    }
    const views = window.GatorViews || {};
    if (entry.view === "loop" && state.activeView === "loop"
        && state.mountedLoopKey !== undefined
        && state.mountedLoopKey === state.activeRepoKey
        && views.loop && typeof views.loop.restore === "function") {
      views.loop.restore(cleanSub(entry.sub));  // same repository: no remount
      syncWorkspace(cleanSub(entry.sub));       // #80: no showView() ran
      return;
    }
    showView(entry.view, entry.repo, state.activeRepoKey,
             { initialSub: cleanSub(entry.sub) });
  }

  window.addEventListener("popstate", function (e) {
    let entry = e.state;
    if (!isShellEntry(entry)) {
      // views/repo.js records its own search/file entries ({view: "repo",
      // repo, ...}) and applies them while that repository is mounted.
      // Elsewhere, such an entry restores that Repo view so Back never
      // goes dead.
      if (!entry || entry.view !== "repo" || typeof entry.repo !== "string") return;
      if (state.activeView === "repo" && state.activeRepo === entry.repo) return;
      entry = { gatorDashboard: 1, view: "repo", repo: entry.repo, repoKey: null, sub: null };
    }
    restoring = true;
    try {
      // #80: an entry recorded in another, still-open workspace context
      // selects that context first (no push). Otherwise the entry is
      // applied to the active context.
      const ws = workspace();
      if (ws && ws.isHydrated() && typeof entry.ctx === "string") {
        const current = ws.active();
        if (!current || current.id !== entry.ctx) ws.select(entry.ctx);
      }
      restoreShellState(entry);
    } finally {
      restoring = false;
    }
  });

  function showView(name, extra, repoKeyOverride, opts) {
    viewRenders++;
    try {
      renderView(name, extra, repoKeyOverride, opts);
    } finally {
      updateDocumentTitle();  // #80: the single title exit
      syncWorkspace(null);    // #80: Loop sub arrives via GatorShell
    }
  }

  function renderView(name, extra, repoKeyOverride, opts) {
    // Tear down the previous view's lifecycle resources (poll timers, global
    // listeners) before rendering the next. Only the repo view registers any;
    // the hook is null otherwise. This is what stops the auto-refresh poll
    // from continuing to run after the user navigates away.
    if (typeof window._gatorRepoTeardown === "function") window._gatorRepoTeardown();

    state.activeView = name;
    state.mountedLoopKey = undefined;

    // Plan C Slice 1 (v2.13.0): route-scoped scroll ownership. The Repo and
    // Docs routes both mount `.repo-browser` and own scroll internally via
    // the flex chain. Fleet, History, Updates, Settings preserve the default
    // `#view-slot { overflow-y: auto }`. See scripts-dashboard.md
    // "Responsive shell + sidebar" TRIPWIRE for the invariants this class
    // toggle enforces.
    if (name === "repo" || name === "docs") {
      viewSlot.classList.add("route-repo");
    } else {
      viewSlot.classList.remove("route-repo");
    }

    // Update sidebar active state
    document.querySelectorAll(".sidebar-item").forEach(btn => {
      btn.classList.toggle("active", btn.dataset.view === name);
    });
    // #72: the logo is the Welcome entry point.
    if (brandHome) {
      if (name === "welcome") brandHome.setAttribute("aria-current", "page");
      else brandHome.removeAttribute("aria-current");
    }

    // Show/hide repo search input
    const repoSearchInput = document.getElementById("repo-search-input");
    if (repoSearchInput) {
      repoSearchInput.style.display = name === "repo" ? "" : "none";
      if (name !== "repo") repoSearchInput.value = "";
    }
    // The Repo branch-history picker lives in #topbar-repo-tools (Paper:
    // the title-only header has no subtitle). Only the Repo branch fills it.
    if (repoTools) {
      repoTools.textContent = "";
      repoTools.hidden = true;
    }

    // Clear slot
    viewSlot.innerHTML = "";

    const views = window.GatorViews || {};

    if (name === "fleet") {
      updateTopbar("fleet");
      if (views.fleet) {
        views.fleet(state.data, viewSlot);
      } else {
        viewSlot.innerHTML = "<p class='muted'>Fleet view not available.</p>";
      }
      return;
    }

    if (name === "history") {
      updateTopbar("history");
      if (views.history) {
        views.history(state.data, viewSlot, state.activeRepo);
      } else {
        viewSlot.innerHTML = "<p class='muted'>Commits view not available.</p>";
      }
      return;
    }

    if (name === "repo") {
      const repoName = extra || state.activeRepo;
      if (!repoName) {
        updateTopbar("repo");
        viewSlot.innerHTML = "<p class='muted' style='padding:40px;text-align:center'>Select a repo from the Fleet view.</p>";
        return;
      }
      // Resolve repo_key: explicit override from gatorNavToRepo wins;
      // otherwise always re-resolve from fleet data so a stale key
      // from a prior repo selection never persists across name-only
      // navigation (URL query param, sidebar re-click, refresh).
      let repoKey;
      if (repoKeyOverride) {
        repoKey = repoKeyOverride;
      } else {
        const matchedRepo = fleetRepos().find(r => r.name === repoName);
        repoKey = (matchedRepo && matchedRepo.repo_key) || null;
      }
      setActiveRepo(repoName, repoKey);
      // Find branch from fleet data
      const repoInfo = fleetRepos().find(r => r.name === repoName);
      const branch = repoInfo && repoInfo.branch ? repoInfo.branch : "";
      updateTopbar("repo");
      // The branch-history tools (static markup: the repository name and
      // branch are in the sidebar context, not here). The dropdown is
      // positioned against #topbar-repo-tools.
      if (branch && repoTools) {
        repoTools.innerHTML =
          '<span id="branch-version-label"></span>'
          + '<button class="history-toggle-btn" id="branch-history-btn" title="Browse commit history" style="font-size:13px;">&#9662;</button>'
          + '<div class="history-dropdown" id="branch-history-dropdown" style="display:none;"></div>';
        repoTools.hidden = false;
      }
      if (views.repo) {
        views.repo(state.data, viewSlot, repoName, null, state.activeRepoKey);
      } else {
        viewSlot.innerHTML = "<p class='muted'>Repo view not available.</p>";
      }
      // Wire up branch history dropdown
      const branchBtn = document.getElementById("branch-history-btn");
      const branchDropdown = document.getElementById("branch-history-dropdown");
      if (branchBtn && branchDropdown) {
        let branchHistLoaded = false;
        branchBtn.addEventListener("click", async function (e) {
          e.stopPropagation();
          if (branchDropdown.style.display !== "none") {
            branchDropdown.style.display = "none";
            return;
          }
          branchDropdown.style.display = "block";
          if (branchHistLoaded) return;
          branchDropdown.innerHTML = '<div style="padding:8px; color:#aaa;">Loading…</div>';
          try {
            const resp = await fetch(`/api/repo/${encodeURIComponent(repoName)}/commits`);
            const data = await resp.json();
            if (!data.commits || !data.commits.length) {
              branchDropdown.innerHTML = '<div style="padding:8px; color:#aaa;">No history</div>';
              branchHistLoaded = true;
              return;
            }
            // Add "Current (HEAD)" as first option
            let html = '<div class="history-item history-active" data-hash="" title="Current working state">'
              + '<span class="history-hash">HEAD</span>'
              + '<span class="history-date">current</span>'
              + '<span class="history-msg">Working state</span></div>';
            for (const c of data.commits) {
              const dateStr = (c.date || "").substring(0, 19);
              html += `<div class="history-item" data-hash="${c.hash}" title="${c.message}">
                <span class="history-hash">${c.short_hash}</span>
                <span class="history-date">${dateStr}</span>
                <span class="history-msg">${(c.message || "").substring(0, 50)}</span>
              </div>`;
            }
            branchDropdown.innerHTML = html;
            branchHistLoaded = true;
            branchDropdown.querySelectorAll(".history-item").forEach(item => {
              item.addEventListener("click", function (e) {
                e.stopPropagation();
                branchDropdown.style.display = "none";
                const hash = this.dataset.hash;
                // Update active highlight
                branchDropdown.querySelectorAll(".history-item").forEach(i => i.classList.remove("history-active"));
                this.classList.add("history-active");
                // Update version label in header
                const vLabel = document.getElementById("branch-version-label");
                if (vLabel) {
                  const commitDate = this.querySelector(".history-date");
                  const dateStr = commitDate ? commitDate.textContent.trim() : "";
                  if (hash) {
                    vLabel.innerHTML = ' <span class="muted" style="font-weight:normal; font-size:12px;">Viewing: ' + hash.substring(0, 8) + (dateStr && dateStr !== "current" ? ' (' + dateStr.substring(0, 19) + ')' : '') + '</span>';
                  } else {
                    vLabel.innerHTML = '';
                  }
                }
                // Set version context and reload file list
                window._gatorRepoVersion = hash || null;
                if (views.repo) {
                  views.repo(state.data, viewSlot, repoName, hash || null, state.activeRepoKey);
                }
              });
            });
          } catch (err) {
            branchDropdown.innerHTML = '<div style="padding:8px; color:var(--color-critical);">Error</div>';
          }
        });
        document.addEventListener("click", function () { branchDropdown.style.display = "none"; });
      }
      return;
    }

    // Docs: the shipped Gator documents, repository-independent (views/docs.js).
    if (name === "docs") {
      updateTopbar("docs");
      if (views.docs) {
        views.docs(state.data, viewSlot);
      } else {
        viewSlot.innerHTML = "<p class='muted'>Docs view not available.</p>";
      }
      return;
    }

    if (name === "updates") {
      updateTopbar("updates");
      if (views.updates) {
        views.updates(state.data, viewSlot);
      } else {
        viewSlot.innerHTML = "<p class='muted'>Updates view not available.</p>";
      }
      return;
    }

    if (name === "loop") {
      const repoName = state.activeRepo;
      if (!repoName) {
        updateTopbar("loop");
        viewSlot.innerHTML = "<p class='muted' style='padding:40px;text-align:center'>Select a repo from the Fleet view first.</p>";
        return;
      }
      updateTopbar("loop");
      if (views.loop) {
        state.mountedLoopKey = state.activeRepoKey;
        views.loop(state.data, viewSlot, repoName, state.activeRepoKey,
                   (opts && opts.initialSub) || null);
      } else {
        viewSlot.innerHTML = "<p class='muted'>Loop view not available.</p>";
      }
      return;
    }

    // #72: Welcome is repository-independent. It never reads or changes
    // activeRepo / activeRepoKey, so Repo/Docs/Loop dimming is untouched.
    if (name === "welcome") {
      updateTopbar("welcome");
      if (views.welcome) {
        views.welcome(state.data, viewSlot);
      } else {
        viewSlot.innerHTML = "<p class='muted'>Welcome view not available.</p>";
      }
      return;
    }

    if (name === "settings") {
      updateTopbar("settings");
      if (views.settings) {
        views.settings(state.data, viewSlot, {
          standalone: true,
        });
      } else {
        viewSlot.innerHTML = "<p class='muted'>Settings view not available.</p>";
      }
      return;
    }
  }

  // ── sidebar click handler ─────────────────────────────────────────────────

  document.getElementById("sidebar-nav").addEventListener("click", function (e) {
    const item = e.target.closest(".sidebar-item");
    if (!item || item.classList.contains("dimmed") || item.classList.contains("placeholder")) return;
    const view = item.dataset.view;
    if ((view === "repo" || view === "loop") && !state.activeRepo) return;
    navigate(view);
  });

  // #72: the logo opens Welcome (an ordinary shell history entry).
  if (brandHome) {
    brandHome.addEventListener("click", function () { navigate("welcome"); });
  }

  // ── session evidence modal ─────────────────────────────────────────────

  let modalOverlay = null;

  function ensureModal() {
    if (modalOverlay) return;
    modalOverlay = document.createElement("div");
    modalOverlay.className = "session-overlay";
    modalOverlay.style.display = "none";
    modalOverlay.innerHTML = `
      <div class="session-modal">
        <div class="session-modal-header">
          <span class="session-modal-title"></span>
          <button class="session-modal-close" title="Close">&times;</button>
        </div>
        <div class="session-modal-body"></div>
      </div>
    `;
    document.body.appendChild(modalOverlay);

    // Close handlers
    modalOverlay.querySelector(".session-modal-close").addEventListener("click", closeModal);
    modalOverlay.addEventListener("click", function (e) {
      if (e.target === modalOverlay) closeModal();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && modalOverlay.style.display !== "none") closeModal();
    });
  }

  function closeModal() {
    if (modalOverlay) modalOverlay.style.display = "none";
  }

  window.showSessionModal = async function (repo, sourceKind, filename) {
    ensureModal();
    const titleEl = modalOverlay.querySelector(".session-modal-title");
    const bodyEl = modalOverlay.querySelector(".session-modal-body");

    titleEl.textContent = filename;
    bodyEl.innerHTML = '<span class="muted">Loading…</span>';
    modalOverlay.style.display = "flex";

    try {
      const resp = await fetch("/api/session", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Gator-Dashboard": "1",
        },
        body: JSON.stringify({
          repo: repo,
          source_kind: sourceKind,
          filename: filename,
        }),
      });
      const data = await resp.json();
      if (data.error) {
        bodyEl.innerHTML = '<div class="session-modal-error">' + escHtml(data.error) + '</div>';
      } else {
        bodyEl.innerHTML = '<pre class="session-markdown">' + escHtml(data.content || "") + '</pre>';
      }
    } catch (err) {
      bodyEl.innerHTML = '<div class="session-modal-error">Failed to load: ' + escHtml(err.message) + '</div>';
    }
  };

  function escHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // ── repo navigation (called by fleet view) ─────────────────────────────────

  // The Fleet row link: open in the current workspace context. When another
  // context already holds that repository, select it instead (#80: one
  // context per repository).
  window.gatorNavToRepo = function (repoName, repoKey) {
    const ws = workspace();
    const existing = ws && ws.isHydrated() ? ws.findByRepo(repoName, repoKey || null) : null;
    const current = existing && ws.active();
    if (existing && (!current || current.id !== existing.id)) {
      selectContext(existing.id, { focus: true });
      return;
    }
    navigate("repo", repoName, repoKey || undefined);
  };

  // #80: Fleet's "Open in new workspace tab": select the repository's
  // context, or create one at its Repo overview. At the limit, a notice.
  window.gatorOpenRepoInNewContext = function (repoName, repoKey) {
    const ws = workspace();
    if (!ws || !ws.isHydrated()) {
      window.gatorNavToRepo(repoName, repoKey);
      return;
    }
    const existing = ws.findByRepo(repoName, repoKey || null);
    if (existing) {
      selectContext(existing.id, { focus: true });
      return;
    }
    const ctx = ws.create({ repo: repoName, repoKey: repoKey || null, view: "repo" });
    if (!ctx) {
      showFleetNotice("Workspace limit reached (" + ws.MAX_CONTEXTS
        + "). Close a workspace first.");
      return;
    }
    selectContext(ctx.id, { focus: true });
  };

  // ── refresh ────────────────────────────────────────────────────────────────

  let refreshPending = false;

  async function doRefresh() {
    if (refreshPending || window.GATOR_SNAPSHOT) return;
    refreshPending = true;
    refreshBtn.classList.add("spinning");
    refreshBtn.textContent = "↺ Refreshing…";

    try {
      await fetch("/api/refresh");
      const oldTs = state.data && state.data.generated_at;
      let attempts = 0;
      while (attempts < 30) {
        await sleep(1000);
        const fresh = await loadData();
        if (fresh.generated_at !== oldTs) {
          state.data = fresh;
          updateTimestamp(fresh.generated_at);
          // The card's branch/version come from the fresh Fleet record.
          renderSidebarContext();
          // Full rerender so repo-shell metadata (activeRepoKey, tab label,
          // subtitle/branch) is recomputed from fresh state.data. The repo
          // browser self-restores its expansion/selection via _treeState, so
          // no browsing state is lost. (The 5s auto-poll stays flicker-free
          // via its own sidebar-only applyRefresh path — this is only the
          // explicit global Refresh button.)
          showView(state.activeView, state.activeRepo);
          break;
        }
        attempts++;
      }
    } catch (err) {
      console.error("Refresh failed:", err);
    } finally {
      refreshBtn.classList.remove("spinning");
      refreshBtn.textContent = "↺ Refresh";
      refreshPending = false;
    }
  }

  refreshBtn.addEventListener("click", doRefresh);

  // Exposed so view modules (e.g. fleet.js) can trigger a fleet refresh
  window.gatorRefreshFleet = doRefresh;

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  // ── initial load ───────────────────────────────────────────────────────────

  async function init() {
    // Snapshot mode: show persistent banner and hide Refresh button.
    if (window.GATOR_SNAPSHOT) {
      const banner = document.getElementById("snapshot-banner");
      if (banner) banner.style.display = "block";
      refreshBtn.style.display = "none";
      // #80: a static fleet report has no workspaces.
      if (workspaceStrip) workspaceStrip.hidden = true;
      if (appShell) {
        appShell.removeAttribute("role");
        appShell.removeAttribute("aria-labelledby");
      }
    }

    const rendersBeforeLoad = viewRenders;
    try {
      state.data = await loadData();
      updateTimestamp(state.data.generated_at);
    } catch (err) {
      viewSlot.innerHTML = `<div class="error-block">Failed to load dashboard data: ${err.message}</div>`;
      return;
    }

    // #70: something navigated while /api/data was loading (a sidebar
    // click, gatorNavToRepo, Back). Keep that view and re-render it with
    // the loaded data, as doRefresh does; do not replace it with the
    // landing view or rewrite the history entry it pushed.
    if (viewRenders !== rendersBeforeLoad) {
      showView(state.activeView, state.activeRepo, state.activeRepoKey || undefined);
      hydrateWorkspace();
      return;
    }

    // #80: land on the URL's context. Without `view`, the legacy meaning
    // holds: ?repo= opens Repo; otherwise Welcome is the front door and a
    // snapshot is a fleet report.
    const url = parseShellUrl();
    const view = url.view
      || (url.repo ? "repo" : (window.GATOR_SNAPSHOT ? "fleet" : "welcome"));
    const entry = { gatorDashboard: 1, view: view, repo: url.repo, repoKey: null, sub: null };
    // A reload or duplicated tab keeps its history entry: when it describes
    // the same context, reuse its key (same-named repositories) and Loop sub.
    const kept = history.state;
    if (isShellEntry(kept) && kept.view === view && kept.repo === url.repo) {
      entry.repoKey = typeof kept.repoKey === "string" ? kept.repoKey : null;
      entry.sub = cleanSub(kept.sub);
    }
    applyShellEntry(entry);
    // #56: the landing entry becomes a shell entry without adding one.
    recordShell("replaceState", null);
    hydrateWorkspace();
  }

  init();
})();
