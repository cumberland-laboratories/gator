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

  // ── commit policy posture (#75) ──────────────────────────────────────────
  //
  // The strict/warn/off selector stays retired: one broad switch
  // misdescribes the two categories (charter integrity blocks, with an
  // Architect approval as the escape hatch; dangerous patterns pause). Shared with views/settings.js through
  // window.GatorCommitPolicy (fleet.js loads first). The only Fleet
  // control is the machine-local Warn checkbox (below).

  // `active` is false for the two states with no effective policy to
  // report (unreadable, or not gatorized): they never claim the default
  // checks, and they carry no sort value (missing sorts last).
  function commitPolicy(repo) {
    if (repo && repo.accessible === false) {
      return { key: "unknown", label: "Unknown", active: false,
               note: "Not accessible: the commit policy cannot be read." };
    }
    if (repo && repo.gatorized === false) {
      return { key: "not-gatorized", label: "Not gatorized", active: false,
               note: "No Gator pre-commit checks run in this repository." };
    }
    if (repo && repo.enterprise_managed) {
      return { key: "enterprise", label: "Managed by Enterprise", active: true,
               note: "The Enterprise hook mode decides this repository's checks." };
    }
    const level = policyLevel(repo);
    if (level === "warn") {
      return { key: "warn", label: "Warn", active: true,
               note: "On this machine only: every finding is advisory, so commits go through with missing charter updates and dangerous-pattern findings. Each such commit records Gator-Commit-Policy: warn." };
    }
    return { key: "default", label: "Default", active: true,
             note: "Charter updates block; dangerous patterns pause for an Architect decision." };
  }

  // This machine's level for the clone (Git's private area, never the
  // repository): "strict" or "warn". The tracked config.json is not read.
  function policyLevel(repo) {
    return repo && repo.commit_policy === "warn" ? "warn" : "strict";
  }

  // The local Dashboard may change the policy only of a readable, gatorized
  // repository that Enterprise does not manage, and never in a snapshot.
  // The server refuses Enterprise-managed repositories too.
  function policyEditable(repo) {
    return !window.GATOR_SNAPSHOT && repo && repo.accessible !== false
      && repo.gatorized !== false && !repo.enterprise_managed;
  }

  window.GatorCommitPolicy = { posture: commitPolicy };

  // ── sorting (Paper inventory) ────────────────────────────────────────────
  //
  // One column at a time, client-only. `fleetSort` lives for the page
  // load: it is never stored, put in history or in the URL, and it
  // survives a Fleet re-render (Refresh, gatorRefreshFleet). key null =
  // registry order. Rows carry their sort values as data attributes, so a
  // sort reorders the existing <tr> nodes and never rebinds a listener.

  const SORT_COLUMNS = [
    { key: "name", label: "Repo" },
    { key: "branch", label: "Branch" },
    { key: "policy", label: "Commit policy" },
    { key: "version", label: "Version" },
  ];
  const SORT_ATTR = {
    name: "sortName", branch: "sortBranch",
    policy: "sortPolicy", version: "sortVersion",
  };
  const fleetSort = { key: null, dir: "asc" };

  function sortValue(row, key) {
    return row.dataset[SORT_ATTR[key]] || "";
  }

  // Stable: ties keep registry order; a missing value sorts last in both
  // directions.
  function sortRows(rows) {
    const key = fleetSort.key;
    const sign = fleetSort.dir === "desc" ? -1 : 1;
    const index = row => Number(row.dataset.rowIndex);
    return rows.slice().sort((a, b) => {
      if (key) {
        const va = sortValue(a, key), vb = sortValue(b, key);
        if (!va !== !vb) return va ? -1 : 1;
        const c = va.localeCompare(vb, undefined, { numeric: true, sensitivity: "base" });
        if (c) return sign * c;
      }
      return index(a) - index(b);
    });
  }

  function applySortHeaderState(table) {
    table.querySelectorAll("th[data-sort-key]").forEach(th => {
      const active = th.dataset.sortKey === fleetSort.key;
      if (active) th.setAttribute("aria-sort", fleetSort.dir === "desc" ? "descending" : "ascending");
      else th.removeAttribute("aria-sort");
      th.classList.toggle("fleet-sort-active", active);
      const mark = th.querySelector(".fleet-sort-mark");
      if (mark) mark.textContent = active ? (fleetSort.dir === "desc" ? "▼" : "▲") : "";
    });
  }

  // Reorder the existing rows in place (tbody.append moves them), then
  // mark the headers. Shared by the render and header activation.
  function applySort(table) {
    if (!table || !table.tBodies[0]) return;
    const tbody = table.tBodies[0];
    const rows = Array.from(tbody.rows).filter(r => r.dataset.rowIndex !== undefined);
    sortRows(rows).forEach(r => tbody.append(r));
    applySortHeaderState(table);
  }

  function bindSortHeaders(container) {
    container.querySelectorAll(".fleet-sort").forEach(btn => {
      btn.addEventListener("click", function () {
        const key = this.dataset.sortKey;
        fleetSort.dir = fleetSort.key === key && fleetSort.dir === "asc" ? "desc" : "asc";
        fleetSort.key = key;
        applySort(this.closest("table"));
      });
    });
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
        <button class="gator-btn gator-btn-primary" id="add-repo-btn">Add Repository</button>
      </div>
      <div class="section">
        <table class="data-table fleet-table">
          <thead>
            <tr>
              ${SORT_COLUMNS.map(c => `<th data-sort-key="${c.key}"><button class="fleet-sort" data-sort-key="${c.key}">${c.label}<span class="fleet-sort-mark" aria-hidden="true"></span></button></th>`).join("")}
              <th></th>
              <th style="width:24px"></th>
            </tr>
          </thead>
          <tbody>
    `;

    repos.forEach((repo, rowIndex) => {
      const accIcon = repo.accessible ? "" : ' <span title="Not accessible" class="muted">!<span class="fleet-hidden-text">Not accessible</span></span>';
      const branch = repo.branch ? escHtml(repo.branch) : '<span class="muted">-</span>';
      const cliVersion = repo.cli_version ? escHtml(repo.cli_version) : "";
      const isCurrent = currentVersion && cliVersion === currentVersion;
      const isGatorized = repo.gatorized !== false;
      const needsUpdate = isGatorized && !isCurrent && repo.accessible;

      const policy = commitPolicy(repo);
      const policyHtml = `<span class="fleet-policy${policy.active ? "" : " muted"}" title="${escHtml(policy.note)}">${escHtml(policy.label)}</span>`;

      // Warn checkbox: this machine's policy for the clone, only where the
      // local Dashboard may change it. It sits inside the Commit policy cell,
      // before the label, so the table gains no width (a separate column
      // pushed the ⋮ menu past the pane edge at 800px).
      const warnHtml = policyEditable(repo)
        ? `<input type="checkbox" class="fleet-warn-toggle"
             data-repo-name="${escHtml(repo.name)}"
             aria-label="Use warn mode for ${escHtml(repo.name)} on this machine"
             ${policyLevel(repo) === "warn" ? "checked" : ""}>`
        : "";

      // Overflow menu replaces the direct action button.
      // Carries both data-repo-name (for Update/Gatorize) and
      // data-repo-path (for Remove) — each action uses its own identity.
      const lifecycleAction = isGatorized ? "update" : "gatorize";
      const lifecycleLabel = isGatorized ? "Update" : "Gatorize";
      const lifecycleDisabled = !repo.accessible || (isGatorized && !needsUpdate);

      // #80: open the repository in a new workspace context (key-addressed)
      // or a new browser tab (a native same-origin link). A snapshot has
      // no workspaces and no server, so neither is offered there.
      const openHtml = window.GATOR_SNAPSHOT ? "" : `
          <button class="menu-item menu-open-workspace"
            data-repo-name="${escHtml(repo.name)}"
            data-repo-key="${escHtml(repo.repo_key || "")}"
            data-action="open-workspace">Open in new workspace tab</button>
          <a class="menu-item menu-open-browser-tab"
            href="?repo=${escHtml(encodeURIComponent(repo.name))}"
            target="_blank" rel="noopener">Open in new browser tab</a>`;

      const menuHtml = `<div class="overflow-menu-wrapper">
        <button class="overflow-menu-btn" aria-label="Actions for ${escHtml(repo.name)}">&#8942;</button>
        <div class="overflow-menu">${openHtml}
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
        <tr data-row-index="${rowIndex}"
            data-sort-name="${escHtml(repo.name)}"
            data-sort-branch="${escHtml(repo.branch || "")}"
            data-sort-version="${cliVersion}"
            data-sort-policy="${policy.active ? escHtml(policy.label) : ""}">
          <td>
            <button class="link-btn fleet-repo-name" onclick="window.gatorNavToRepo('${escHtml(repo.name)}', '${escHtml(repo.repo_key || "")}')">${escHtml(repo.name)}</button>
            ${accIcon}
          </td>
          <td class="fleet-branch">${branch}</td>
          <td class="fleet-policy-cell">${warnHtml}${policyHtml}<span class="fleet-policy-error" role="alert"></span></td>
          <td class="fleet-version">${cliVersion || '<span class="muted">-</span>'}</td>
          <td class="status-cell">${menuHtml}</td>
          <td class="activity-cell" data-repo="${escHtml(repo.name)}"><span class="activity-indicator" aria-live="polite"></span></td>
        </tr>
      `;
    });

    if (repos.length === 0) {
      html += `<tr><td colspan="6" class="fleet-empty">
        <p>No repos registered yet.</p>
        <p><code>gator gatorize /path/to/repo</code> — install governance + register</p>
        <p><code>gator dashboard --add-repo /path/to/repo</code> — register an existing gatorized repo</p>
      </td></tr>`;
    }

    html += `</tbody></table></div>`;
    container.innerHTML = html;
    applySort(container.querySelector(".fleet-table"));
    bindSortHeaders(container);
    bindOverflowMenus(container);
    bindWarnToggles(container);

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
        if (!wasOpen) {
          menu.classList.add("open");
          placeMenu(this, menu);
        }
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

        if (action === "open-workspace") {
          if (window.gatorOpenRepoInNewContext) {
            window.gatorOpenRepoInNewContext(repoName, this.dataset.repoKey || null);
          }
        } else if (action === "remove") {
          openRemoveConfirmDialog(repoName, repoPath, container);
        } else if (action === "update" || action === "gatorize") {
          performLifecycleAction(repoName, action, container);
        }
      });
    });
  }

  // #74: open upward when the menu does not fit below its button inside
  // the visible area (the window, or the scrolling view pane if it ends
  // sooner) and there is more room above. Measured once per open.
  function placeMenu(btn, menu) {
    menu.classList.remove("open-up");
    const pane = btn.closest("#view-slot");
    const visibleTop = Math.max(0, pane ? pane.getBoundingClientRect().top : 0);
    const visibleBottom = Math.min(window.innerHeight,
      pane ? pane.getBoundingClientRect().bottom : window.innerHeight);
    const b = btn.getBoundingClientRect();
    const needed = menu.offsetHeight + 4;
    const below = visibleBottom - b.bottom;
    const above = b.top - visibleTop;
    if (below < needed && above > below) menu.classList.add("open-up");
  }

  function closeAllMenus(container) {
    container.querySelectorAll(".overflow-menu.open").forEach(m => m.classList.remove("open", "open-up"));
  }

  // ── Commit policy: the Warn checkbox (machine-local) ─────────────────
  //
  // The level lives in this clone's Git private area on this machine, never
  // in the repository, so it never changes another engineer's checks. The
  // checkbox never shows a state the server has not confirmed. Turning Warn
  // on is reverted at once and asks first; clearing it (the safe direction)
  // writes `strict` directly. Both go through writePolicy(), the only caller
  // of POST /api/repo/<name>/commit-policy; success re-renders Fleet from
  // the server, failure keeps the prior state and shows a row error.

  function bindWarnToggles(container) {
    container.querySelectorAll(".fleet-warn-toggle").forEach(box => {
      box.addEventListener("change", function () {
        const repoName = this.dataset.repoName;
        const errorEl = this.closest("td").querySelector(".fleet-policy-error");
        if (this.checked) {
          this.checked = false;
          openWarnConfirmDialog(repoName, container, this, errorEl);
        } else {
          writePolicy(repoName, "strict", errorEl, this, true);
        }
      });
    });
  }

  function openWarnConfirmDialog(repoName, container, box, errorEl) {
    const modal = document.createElement("div");
    modal.className = "gator-modal-overlay";
    modal.innerHTML = `
      <div class="gator-modal fleet-warn-dialog" role="dialog" aria-modal="true" aria-labelledby="fleet-warn-title">
        <h3 id="fleet-warn-title">Use Warn mode for ${escHtml(repoName)} on this machine?</h3>
        <div class="gator-modal-body">
          <p>Warn mode allows your commits in <strong>${escHtml(repoName)}</strong> with missing charter updates and dangerous-pattern findings. Every finding becomes advisory.</p>
          <p class="muted" style="font-size:13px">This applies only to this checkout on this machine. It is not stored in the repository and does not change anyone else's checks. Each commit you make in Warn mode records <code>Gator-Commit-Policy: warn</code>. Clear the Warn box to restore the default checks.</p>
        </div>
        <div class="gator-modal-footer" style="display:flex;justify-content:flex-end;gap:8px">
          <button class="gator-btn modal-cancel-btn">Cancel</button>
          <button class="gator-btn warn-confirm-btn">Use Warn mode</button>
        </div>
      </div>
    `;
    container.appendChild(modal);
    const cancelBtn = modal.querySelector(".modal-cancel-btn");
    const confirmBtn = modal.querySelector(".warn-confirm-btn");

    function close() { modal.remove(); box.focus(); }

    cancelBtn.addEventListener("click", close);
    modal.addEventListener("click", (e) => { if (e.target === modal) close(); });
    modal.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
    confirmBtn.addEventListener("click", function () {
      modal.remove();
      writePolicy(repoName, "warn", errorEl, box, false);
    });
    cancelBtn.focus();
  }

  // `box` (optional) is disabled during the request; on failure it returns
  // to `boxPrior`, the state the server still holds.
  async function writePolicy(repoName, level, errorEl, box, boxPrior) {
    if (errorEl) errorEl.textContent = "";
    if (box) box.disabled = true;
    function fail(message) {
      if (box) { box.disabled = false; box.checked = !!boxPrior; }
      if (errorEl) errorEl.textContent = "Not changed: " + message;
    }
    try {
      const resp = await fetch(`/api/repo/${encodeURIComponent(repoName)}/commit-policy`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Gator-Dashboard": "1" },
        body: JSON.stringify({ level: level }),
      });
      const data = await resp.json().catch(() => ({}));
      if (resp.ok && data.status === "ok") {
        if (window.gatorRefreshFleet) window.gatorRefreshFleet();
        else if (box) box.disabled = false;
      } else {
        fail(data.error || ("HTTP " + resp.status));
      }
    } catch (err) {
      fail("request failed (" + err + ")");
    }
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
