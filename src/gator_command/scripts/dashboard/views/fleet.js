/**
 * fleet.js — Fleet view for Gator Dashboard.
 *
 * Repo operations surface: which repos are governed, their charter
 * state, last activity, and template update status.
 */

(function () {
  "use strict";

  window.GatorViews = window.GatorViews || {};

  // ── helpers ────────────────────────────────────────────────────────────────

  function escHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // ── render ─────────────────────────────────────────────────────────────

  window.GatorViews.fleet = function (data, container) {
    renderStandaloneRepos(data, container);
  };

  // ── render (standalone mode) ────────────────────────────────────────────

  function renderStandaloneRepos(data, container) {
    const repos = data.repos || [];
    const currentVersion = data.gator_cli_version || "";

    let html = `
      <div class="fleet-header">
        <span></span>
        <button class="gator-btn gator-btn-primary" id="add-repo-btn">Add Repository</button>
      </div>
      <div class="section">
        <table class="data-table">
          <thead>
            <tr>
              <th>Repo</th>
              <th>Branch</th>
              <th>Enforcement</th>
              <th>Version</th>
              <th></th>
              <th style="width:24px"></th>
            </tr>
          </thead>
          <tbody>
    `;

    for (const repo of repos) {
      const accIcon = repo.accessible ? "" : ' <span title="Not accessible" class="muted">!</span>';
      const branch = repo.branch ? escHtml(repo.branch) : '<span class="muted">-</span>';
      const cliVersion = repo.cli_version ? escHtml(repo.cli_version) : "";
      const isCurrent = currentVersion && cliVersion === currentVersion;
      const isGatorized = repo.gatorized !== false;
      const needsUpdate = isGatorized && !isCurrent && repo.accessible;

      const enfLevel = (repo.config && repo.config.enforcement_level) || "strict";
      const enfId = `enf-${escHtml(repo.name)}`;
      const enfDropdown = isGatorized
        ? `<select id="${enfId}" data-repo="${escHtml(repo.name)}" class="enforcement-select" ${repo.accessible ? "" : "disabled"}>
            <option value="strict"${enfLevel === "strict" ? " selected" : ""}>strict</option>
            <option value="warn"${enfLevel === "warn" ? " selected" : ""}>warn</option>
            <option value="off"${enfLevel === "off" ? " selected" : ""}>off</option>
          </select>`
        : '<span class="muted">-</span>';

      // Overflow menu replaces the direct action button.
      // Carries both data-repo-name (for Update/Gatorize) and
      // data-repo-path (for Remove) — each action uses its own identity.
      const lifecycleAction = isGatorized ? "update" : "gatorize";
      const lifecycleLabel = isGatorized ? "Update" : "Gatorize";
      const lifecycleDisabled = !repo.accessible || (isGatorized && !needsUpdate);

      const menuHtml = `<div class="overflow-menu-wrapper">
        <button class="overflow-menu-btn" aria-label="Actions for ${escHtml(repo.name)}">&#8942;</button>
        <div class="overflow-menu">
          <button class="menu-item menu-lifecycle"
            data-repo-name="${escHtml(repo.name)}"
            data-action="${lifecycleAction}"
            ${lifecycleDisabled ? "disabled" : ""}>${lifecycleLabel}</button>
          <button class="menu-item menu-remove"
            data-repo-name="${escHtml(repo.name)}"
            data-repo-path="${escHtml(repo.path || "")}"
            data-action="remove">Remove</button>
        </div>
      </div>`;

      html += `
        <tr>
          <td>
            <button class="link-btn" onclick="window.gatorNavToRepo('${escHtml(repo.name)}')">${escHtml(repo.name)}</button>
            ${accIcon}
          </td>
          <td>${branch}</td>
          <td>${enfDropdown}</td>
          <td class="mono" style="font-size:12px">${cliVersion || '<span class="muted">-</span>'}</td>
          <td class="status-cell">${menuHtml}</td>
          <td class="activity-cell" data-repo="${escHtml(repo.name)}"><span class="activity-indicator" aria-live="polite"></span></td>
        </tr>
      `;
    }

    if (repos.length === 0) {
      html += `<tr><td colspan="6" class="muted" style="text-align:center;padding:24px">
        No repos registered yet.<br><br>
        <code style="font-size:12px;">gator gatorize /path/to/repo</code> — install governance + register<br>
        <code style="font-size:12px;">gator dashboard --add-repo /path/to/repo</code> — register an existing gatorized repo
      </td></tr>`;
    }

    html += `</tbody></table></div>`;
    container.innerHTML = html;
    bindOverflowMenus(container);
    bindEnforcementDropdowns(container);

    // Add Repository button
    const addBtn = container.querySelector("#add-repo-btn");
    if (addBtn) {
      addBtn.addEventListener("click", () => openAddRepoModal(container));
    }
  }

  // ── Add Repository modal ────────────────────────────────────────────────

  function openAddRepoModal(container) {
    const modal = document.createElement("div");
    modal.className = "gator-modal-overlay";
    modal.innerHTML = `
      <div class="gator-modal">
        <h3>Add Repository</h3>
        <div class="gator-modal-body">
          <div class="gator-input-group">
            <label>Repository path</label>
            <div style="display:flex;gap:8px">
              <input type="text" id="repo-path-input" placeholder="/path/to/repo" style="flex:1" />
              <button id="repo-path-submit" class="gator-btn">Register</button>
            </div>
          </div>
          <hr style="border-color:var(--border);margin:16px 0"/>
          <div id="discovered-repos">
            <p class="muted">Scanning for repositories...</p>
          </div>
        </div>
        <div class="gator-modal-footer">
          <button class="gator-btn" id="modal-close-btn">Close</button>
        </div>
      </div>
    `;
    container.appendChild(modal);

    modal.querySelector("#modal-close-btn").addEventListener("click", () => modal.remove());
    modal.addEventListener("click", (e) => {
      if (e.target === modal) modal.remove();
    });

    modal.querySelector("#repo-path-submit").addEventListener("click", () => {
      const path = modal.querySelector("#repo-path-input").value.trim();
      if (path) registerRepo(path, modal);
    });

    fetch("/api/repos/discover")
      .then(r => r.json())
      .then(data => renderDiscoveredRepos(data.repos || [], modal))
      .catch(() => {
        const target = modal.querySelector("#discovered-repos");
        if (target) target.innerHTML = '<p class="muted">Could not scan for repositories.</p>';
      });
  }

  function renderDiscoveredRepos(repos, modal) {
    const target = modal.querySelector("#discovered-repos");
    if (!repos.length) {
      target.innerHTML = '<p class="muted">No unregistered repos found in common locations.</p>';
      return;
    }
    target.innerHTML = '<p class="muted" style="margin-bottom:8px">Repos found:</p>' +
      repos.map((r, i) => `
        <div class="discovered-repo-row">
          <span class="repo-name">${escHtml(r.name)}</span>
          <span class="repo-path muted">${escHtml(r.path)}</span>
          <span class="muted" style="font-size:12px">${r.gatorized ? "gatorized" : "ungoverned"}</span>
          <button class="gator-btn gator-btn-sm add-repo-btn" data-idx="${i}">Add</button>
        </div>
      `).join("");

    target.querySelectorAll(".add-repo-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const idx = parseInt(btn.dataset.idx);
        registerRepo(repos[idx].path, modal);
      });
    });
  }

  function registerRepo(path, modal) {
    fetch("/api/repos/register", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-Gator-Dashboard": "1"},
      body: JSON.stringify({path}),
    })
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        alert(data.error);
        return;
      }
      modal.remove();
      if (window.gatorRefreshFleet) window.gatorRefreshFleet();
    })
    .catch(() => alert("Registration failed"));
  }

  // ── Overflow menu ───────────────────────────────────────────────────────

  function bindOverflowMenus(container) {
    // Toggle menu on trigger click; close others first
    container.querySelectorAll(".overflow-menu-btn").forEach(btn => {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        const menu = this.nextElementSibling;
        const wasOpen = menu.classList.contains("open");
        closeAllMenus(container);
        if (!wasOpen) menu.classList.add("open");
      });
    });

    // Close on outside click (once per render)
    document.addEventListener("click", () => closeAllMenus(container));

    // Close on Escape
    container.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeAllMenus(container);
    });

    // Dispatch menu item clicks
    container.querySelectorAll(".menu-item").forEach(btn => {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        const action = this.dataset.action;
        const repoName = this.dataset.repoName;
        const repoPath = this.dataset.repoPath;
        closeAllMenus(container);

        if (action === "remove") {
          openRemoveConfirmDialog(repoName, repoPath, container);
        } else if (action === "update" || action === "gatorize") {
          performLifecycleAction(repoName, action, container);
        }
      });
    });
  }

  function closeAllMenus(container) {
    container.querySelectorAll(".overflow-menu.open").forEach(m => m.classList.remove("open"));
  }

  // ── Lifecycle actions (Update / Gatorize) ─────────────────────────────

  async function performLifecycleAction(repoName, action, container) {
    const activityCell = container.querySelector(`.activity-cell[data-repo="${repoName}"]`);
    const indicator = activityCell && activityCell.querySelector(".activity-indicator");

    if (indicator) indicator.innerHTML = '<span class="dot-pulse"></span>';

    try {
      const resp = await fetch(`/api/repo/${encodeURIComponent(repoName)}/${action}`, {
        method: "POST",
        headers: { "X-Gator-Dashboard": "1" },
      });
      const data = await resp.json();

      if (indicator) indicator.innerHTML = "";
      if (data.status === "ok") {
        if (window.gatorRefreshFleet) window.gatorRefreshFleet();
      } else {
        const reason = (data.output || data.error || "no output from CLI").trim();
        if (indicator) indicator.innerHTML = '<span style="color:var(--color-critical)" title="' + escHtml(reason) + '">!</span>';
        const label = action === "gatorize" ? "Gatorize" : "Update";
        alert(label + " failed for " + repoName + ":\n\n" + reason);
      }
    } catch (err) {
      if (indicator) indicator.innerHTML = '<span style="color:var(--color-critical)">!</span>';
      const label = action === "gatorize" ? "Gatorize" : "Update";
      alert(label + " request failed for " + repoName + ": " + err);
    }
  }

  // ── Remove confirmation dialog ────────────────────────────────────────

  function openRemoveConfirmDialog(repoName, repoPath, container) {
    const modal = document.createElement("div");
    modal.className = "gator-modal-overlay";
    modal.innerHTML = `
      <div class="gator-modal">
        <h3>Remove Repository</h3>
        <div class="gator-modal-body">
          <p>Are you sure you want to remove <strong>${escHtml(repoName)}</strong> from the dashboard?</p>
          <p class="muted" style="font-size:13px">This only removes the registry entry &mdash; no files will be deleted.</p>
          <p class="remove-error" style="color:var(--color-critical);display:none;margin-top:12px"></p>
        </div>
        <div class="gator-modal-footer" style="display:flex;justify-content:flex-end;gap:8px">
          <button class="gator-btn modal-cancel-btn">Cancel</button>
          <button class="gator-btn remove-confirm-btn" style="color:var(--color-critical);border-color:var(--color-critical)">Remove</button>
        </div>
      </div>
    `;
    container.appendChild(modal);

    const cancelBtn = modal.querySelector(".modal-cancel-btn");
    const confirmBtn = modal.querySelector(".remove-confirm-btn");
    const errorEl = modal.querySelector(".remove-error");

    function close() { modal.remove(); }

    cancelBtn.addEventListener("click", close);
    modal.addEventListener("click", (e) => { if (e.target === modal) close(); });
    modal.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });

    confirmBtn.addEventListener("click", async function () {
      confirmBtn.disabled = true;
      confirmBtn.textContent = "Removing…";
      errorEl.style.display = "none";

      try {
        const resp = await fetch("/api/repos/remove", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Gator-Dashboard": "1" },
          body: JSON.stringify({ path: repoPath }),
        });
        const data = await resp.json();

        if (resp.ok && data.status === "ok") {
          close();
          if (window.gatorRefreshFleet) window.gatorRefreshFleet();
        } else {
          errorEl.textContent = data.error || "Removal failed";
          errorEl.style.display = "block";
          confirmBtn.disabled = false;
          confirmBtn.textContent = "Remove";
        }
      } catch (err) {
        errorEl.textContent = "Request failed: " + err;
        errorEl.style.display = "block";
        confirmBtn.disabled = false;
        confirmBtn.textContent = "Remove";
      }
    });
  }

  function bindEnforcementDropdowns(container) {
    container.querySelectorAll(".enforcement-select").forEach(select => {
      select.addEventListener("change", async function () {
        const repoName = this.dataset.repo;
        const level = this.value;
        try {
          const resp = await fetch(`/api/repo/${encodeURIComponent(repoName)}/config`, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-Gator-Dashboard": "1" },
            body: JSON.stringify({ enforcement_level: level }),
          });
          const result = await resp.json();
          if (result.status === "ok") {
            const check = document.createElement("span");
            check.className = "save-check";
            check.textContent = " \u2713";
            this.parentNode.appendChild(check);
            setTimeout(() => check.remove(), 1200);
          } else {
            this.style.outline = "2px solid var(--color-critical)";
            setTimeout(() => { this.style.outline = ""; }, 2000);
          }
        } catch (err) {
          this.style.outline = "2px solid var(--color-critical)";
          setTimeout(() => { this.style.outline = ""; }, 2000);
        }
      });
    });
  }

  function parseSummaryLine(output) {
    if (!output) return "Done";
    const lines = output.split("\n").map(l => l.trim()).filter(Boolean);
    const done = lines.find(l => l.startsWith("Done:"));
    if (done) return done;
    const current = lines.find(l => l.includes("Everything is current"));
    if (current) return "Already current";
    return "Done";
  }
})();
