/**
 * dashboard.js — Gator Dashboard shell controller.
 *
 * Responsibilities:
 *   - Load Tier 1 data from /api/data (or window.DASHBOARD_DATA in snapshot mode)
 *   - Route sidebar clicks to view modules
 *   - Handle ?repo=<name> query param to pre-load Repo view
 *   - Manage Refresh button (re-fetches /api/refresh then /api/data)
 *   - Update topbar title/subtitle from active view
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
  };

  // ── view metadata ─────────────────────────────────────────────────────────

  const VIEW_META = {
    fleet:     { title: "Fleet",     subtitle: "" },
    history:   { title: "History",   subtitle: "" },
    repo:      { title: "Repo",      subtitle: "" },
    docs:      { title: "Docs",      subtitle: "" },
    blueprint: { title: "Blueprints", subtitle: "" },
    updates:   { title: "Updates",   subtitle: "" },
    settings:  { title: "Settings",  subtitle: "" },
  };

  // ── DOM refs ───────────────────────────────────────────────────────────────

  const viewSlot       = document.getElementById("view-slot");
  const generatedAt    = document.getElementById("generated-at");
  const refreshBtn     = document.getElementById("refresh-btn");
  const repoTab        = document.getElementById("repo-tab");
  const docsTab        = document.getElementById("docs-tab");
  const blueprintTab   = document.getElementById("blueprint-tab");
  const topbarTitle    = document.getElementById("topbar-title");

  // ── sidebar toggle ────────────────────────────────────────────────────────

  const sidebarToggle = document.getElementById("sidebar-toggle");
  const sidebar = document.getElementById("sidebar");
  if (sidebarToggle && sidebar) {
    sidebarToggle.addEventListener("click", function () {
      sidebar.classList.toggle("collapsed");
    });
  }
  const topbarSubtitle = document.getElementById("topbar-subtitle");

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
    } catch (_) {
      generatedAt.textContent = ts;
    }
  }

  // ── topbar ─────────────────────────────────────────────────────────────────

  function updateTopbar(name, subtitle) {
    const meta = VIEW_META[name] || { title: name, subtitle: "" };
    topbarTitle.textContent = meta.title;
    topbarSubtitle.innerHTML = subtitle || meta.subtitle;
  }

  // ── view routing ───────────────────────────────────────────────────────────

  function showView(name, extra) {
    // Tear down the previous view's lifecycle resources (poll timers, global
    // listeners) before rendering the next. Only the repo view registers any;
    // the hook is null otherwise. This is what stops the auto-refresh poll
    // from continuing to run after the user navigates away.
    if (typeof window._gatorRepoTeardown === "function") window._gatorRepoTeardown();

    state.activeView = name;

    // Update sidebar active state
    document.querySelectorAll(".sidebar-item").forEach(btn => {
      btn.classList.toggle("active", btn.dataset.view === name);
    });

    // Show/hide repo search input
    const repoSearchInput = document.getElementById("repo-search-input");
    if (repoSearchInput) {
      repoSearchInput.style.display = (name === "repo" || name === "docs") ? "" : "none";
      if (name !== "repo") repoSearchInput.value = "";
    }

    // Clear slot
    viewSlot.innerHTML = "";

    const views = window.GatorViews || {};

    if (name === "fleet") {
      const repos = (state.data && state.data.repos) || [];
      const total = repos.length;
      const accessible = repos.filter(r => r.accessible).length;
      updateTopbar("fleet", `${total} repos · ${accessible} accessible`);
      if (views.fleet) {
        views.fleet(state.data, viewSlot);
      } else {
        viewSlot.innerHTML = "<p class='muted'>Fleet view not available.</p>";
      }
      return;
    }

    if (name === "history") {
      updateTopbar("history", "Recent commits");
      if (views.history) {
        views.history(state.data, viewSlot, state.activeRepo);
      } else {
        viewSlot.innerHTML = "<p class='muted'>History view not available.</p>";
      }
      return;
    }

    if (name === "repo") {
      const repoName = extra || state.activeRepo;
      if (!repoName) {
        updateTopbar("repo", "Select a repo from Fleet");
        viewSlot.innerHTML = "<p class='muted' style='padding:40px;text-align:center'>Select a repo from the Fleet view.</p>";
        return;
      }
      state.activeRepo = repoName;
      // Resolve repo_key from fleet data
      const allRepos = (state.data && state.data.fleet && state.data.fleet.repos) || (state.data && state.data.repos) || [];
      const matchedRepo = allRepos.find(r => r.name === repoName);
      state.activeRepoKey = (matchedRepo && matchedRepo.repo_key) || null;
      // Update repo sidebar label
      repoTab.textContent = "";
      const icon = document.createElement("span");
      icon.className = "sidebar-icon";
      icon.textContent = "▸";
      repoTab.appendChild(icon);
      repoTab.appendChild(document.createTextNode(" " + repoName));
      repoTab.classList.remove("dimmed");
      if (docsTab) docsTab.classList.remove("dimmed");
      if (blueprintTab) blueprintTab.classList.remove("dimmed");
      // Find branch from fleet data
      const fleetRepos = (state.data && state.data.fleet && state.data.fleet.repos) || (state.data && state.data.repos) || [];
      const repoInfo = fleetRepos.find(r => r.name === repoName);
      const branch = repoInfo && repoInfo.branch ? repoInfo.branch : "";
      const subtitle = branch
        ? repoName + ' <span class="muted" style="font-weight:normal">' + branch + '</span>'
          + ' <button class="history-toggle-btn" id="branch-history-btn" title="Browse commit history" style="font-size:13px;">&#9662;</button>'
          + '<span id="branch-version-label"></span>'
          + '<div class="history-dropdown" id="branch-history-dropdown" style="display:none; left:0; right:auto;"></div>'
        : repoName;
      updateTopbar("repo", subtitle);
      // Make subtitle container position:relative for dropdown
      topbarSubtitle.style.position = "relative";
      if (views.repo) {
        views.repo(state.data, viewSlot, repoName);
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
                  views.repo(state.data, viewSlot, repoName, hash || null);
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

    if (name === "blueprint") {
      const repoName = state.activeRepo;
      if (!repoName) {
        updateTopbar("blueprint", "Select a repo from Fleet");
        viewSlot.innerHTML = "<p class='muted' style='padding:40px;text-align:center'>Select a repo from the Fleet view first.</p>";
        return;
      }
      updateTopbar("blueprint", repoName + ' <span class="muted" style="font-weight:normal">Level 1: charter map (experimental)</span>');
      if (views.blueprint) {
        views.blueprint(state.data, viewSlot, repoName);
      } else {
        viewSlot.innerHTML = "<p class='muted'>Blueprints view not available.</p>";
      }
      return;
    }

    if (name === "docs") {
      const repoName = state.activeRepo;
      if (!repoName) {
        updateTopbar("docs", "Select a repo from Fleet");
        viewSlot.innerHTML = "<p class='muted' style='padding:40px;text-align:center'>Select a repo from the Fleet view first.</p>";
        return;
      }
      updateTopbar("docs", repoName);
      if (views.repo) {
        views.repo(state.data, viewSlot, repoName, null, "docs");
      } else {
        viewSlot.innerHTML = "<p class='muted'>Docs view not available.</p>";
      }
      return;
    }

    if (name === "updates") {
      updateTopbar("updates", "Gator updates");
      if (views.updates) {
        views.updates(state.data, viewSlot);
      } else {
        viewSlot.innerHTML = "<p class='muted'>Updates view not available.</p>";
      }
      return;
    }

    if (name === "settings") {
      updateTopbar("settings", "Fleet settings");
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
    if ((view === "repo" || view === "docs") && !state.activeRepo) return;
    showView(view);
  });

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

  window.gatorNavToRepo = function (repoName) {
    showView("repo", repoName);
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
    }

    try {
      state.data = await loadData();
      updateTimestamp(state.data.generated_at);
    } catch (err) {
      viewSlot.innerHTML = `<div class="error-block">Failed to load dashboard data: ${err.message}</div>`;
      return;
    }

    // Check for ?repo= query param
    const params = new URLSearchParams(window.location.search);
    const preloadRepo = params.get("repo");
    if (preloadRepo) {
      showView("repo", preloadRepo);
    } else {
      showView("fleet");
    }
  }

  init();
})();
