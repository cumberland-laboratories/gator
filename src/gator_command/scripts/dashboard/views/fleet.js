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

      // Ungoverned repos show "Gatorize", governed repos show "Update"
      let actionBtn;
      if (!repo.accessible) {
        actionBtn = `<button class="update-btn" disabled>Update</button>`;
      } else if (!isGatorized) {
        // Gatorize button gets its own class so it does NOT trigger the
        // Update handler (which POSTs to /update — an endpoint that now
        // pre-checks for .gator/ and 400s on ungoverned repos).
        actionBtn = `<button class="update-btn gatorize-btn" data-repo="${escHtml(repo.name)}" style="background:#2563eb;color:#fff;border-color:#2563eb">Gatorize</button>`;
      } else {
        actionBtn = `<button class="update-btn" data-repo="${escHtml(repo.name)}" ${needsUpdate ? "" : "disabled"}>Update</button>`;
      }

      html += `
        <tr>
          <td>
            <button class="link-btn" onclick="window.gatorNavToRepo('${escHtml(repo.name)}')">${escHtml(repo.name)}</button>
            ${accIcon}
          </td>
          <td>${branch}</td>
          <td>${enfDropdown}</td>
          <td class="mono" style="font-size:12px">${cliVersion || '<span class="muted">-</span>'}</td>
          <td class="status-cell">${actionBtn}</td>
          <td class="activity-cell" data-repo="${escHtml(repo.name)}"></td>
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
    bindUpdateButtons(container, currentVersion);
    bindGatorizeButtons(container);
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

  // ── Update flow ────────────────────────────────────────────────────────

  function bindUpdateButtons(container, currentVersion) {
    // Exclude .gatorize-btn — those POST to /gatorize, not /update.
    container.querySelectorAll(".update-btn:not(.gatorize-btn)").forEach(btn => {
      btn.addEventListener("click", async function () {
        const repoName = this.dataset.repo;
        const activityCell = container.querySelector(`.activity-cell[data-repo="${repoName}"]`);

        this.disabled = true;
        if (activityCell) activityCell.innerHTML = '<span class="dot-pulse"></span>';

        try {
          const resp = await fetch(`/api/repo/${encodeURIComponent(repoName)}/update`, {
            method: "POST",
            headers: { "X-Gator-Dashboard": "1" },
          });
          const data = await resp.json();

          if (activityCell) activityCell.innerHTML = "";
          if (data.status === "ok") {
            if (window.gatorRefreshFleet) window.gatorRefreshFleet();
          } else {
            if (activityCell) activityCell.innerHTML = '<span style="color:var(--color-critical)" title="' + escHtml(data.output || data.error || "") + '">!</span>';
            this.disabled = false;
          }
        } catch (err) {
          if (activityCell) activityCell.innerHTML = '<span style="color:var(--color-critical)">!</span>';
          this.disabled = false;
        }
      });
    });
  }

  // ── Gatorize flow (Stage 3 of retire-gator-install plan) ───────────────
  // Ungoverned repos get a "Gatorize" button that POSTs to a separate
  // /gatorize endpoint. That endpoint runs `gatorize --yes` — non-interactive
  // by definition because the Dashboard cannot answer prompts.

  function bindGatorizeButtons(container) {
    container.querySelectorAll(".gatorize-btn").forEach(btn => {
      btn.addEventListener("click", async function () {
        const repoName = this.dataset.repo;
        const activityCell = container.querySelector(`.activity-cell[data-repo="${repoName}"]`);

        this.disabled = true;
        if (activityCell) activityCell.innerHTML = '<span class="dot-pulse"></span>';

        try {
          const resp = await fetch(`/api/repo/${encodeURIComponent(repoName)}/gatorize`, {
            method: "POST",
            headers: { "X-Gator-Dashboard": "1" },
          });
          const data = await resp.json();

          if (activityCell) activityCell.innerHTML = "";
          if (data.status === "ok") {
            if (window.gatorRefreshFleet) window.gatorRefreshFleet();
          } else {
            if (activityCell) activityCell.innerHTML = '<span style="color:var(--color-critical)" title="' + escHtml(data.output || data.error || "") + '">!</span>';
            this.disabled = false;
          }
        } catch (err) {
          if (activityCell) activityCell.innerHTML = '<span style="color:var(--color-critical)">!</span>';
          this.disabled = false;
        }
      });
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
