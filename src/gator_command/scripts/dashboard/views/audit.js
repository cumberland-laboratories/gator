/**
 * audit.js — Audit view for Gator Dashboard.
 *
 * Data source: data.audit (gator-audit --json) for governance metrics,
 *              GET /api/audit/sessions for session summaries (lazy).
 *
 * Primary question: can I show human oversight? where are the gaps?
 */

(function () {
  "use strict";

  window.GatorViews = window.GatorViews || {};

  function escHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtTs(ts) {
    if (!ts) return "—";
    try {
      return new Date(ts).toLocaleDateString(undefined, {
        year: "numeric", month: "short", day: "numeric",
      });
    } catch (_) { return ts; }
  }

  function fmtDateRange(startedAt, endedAt) {
    if (!startedAt) return "—";
    try {
      const s = new Date(startedAt);
      const e = endedAt ? new Date(endedAt) : null;
      const datePart = s.toLocaleDateString(undefined, { month: "short", day: "numeric" });
      const startTime = s.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
      const endTime = e ? e.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false }) : "";
      return endTime ? `${datePart} ${startTime}\u2013${endTime}` : `${datePart} ${startTime}`;
    } catch (_) { return startedAt.slice(0, 16); }
  }

  function sessionStatus(endedAt) {
    if (!endedAt) return "in-flight";
    try {
      const ago = Date.now() - new Date(endedAt).getTime();
      return ago > 2 * 60 * 60 * 1000 ? "complete" : "in-flight";
    } catch (_) { return "?"; }
  }

  // ── significance bar chart ─────────────────────────────────────────────────

  function renderSigBars(dist) {
    const order  = ["critical", "high", "medium", "low", "routine"];
    const colors = {
      critical: "#a02020",
      high:     "#c44020",
      medium:   "#b8860b",
      low:      "#4a7a4a",
      routine:  "#888",
    };

    const total = Object.values(dist).reduce((s, v) => s + v, 0);
    if (total === 0) return "<p class='muted'>No governed commits found in this period.</p>";

    let html = "";
    for (const level of order) {
      const count = dist[level] || 0;
      if (count === 0) continue;
      const pct = Math.round((count / total) * 100);
      html += `
        <div class="sig-bar">
          <span class="sig-bar-label">${escHtml(level)}</span>
          <div class="sig-bar-track">
            <div class="sig-bar-fill" style="width:${pct}%;background:${colors[level] || '#888'}"></div>
          </div>
          <span class="sig-bar-count">${count}</span>
        </div>
      `;
    }
    return html;
  }

  // ── governed commits table ─────────────────────────────────────────────────

  function renderGoverned(govCommits) {
    const entries = Object.entries(govCommits).filter(([k]) => k !== "total");
    if (entries.length === 0) return "<p class='muted'>No data.</p>";

    entries.sort((a, b) => b[1] - a[1]);

    let html = `
      <table class="data-table">
        <thead><tr><th>Repo</th><th>Governed commits (7d)</th></tr></thead>
        <tbody>
    `;
    for (const [repo, count] of entries) {
      html += `<tr><td>${escHtml(repo)}</td><td class="mono">${count}</td></tr>`;
    }
    html += "</tbody></table>";
    return html;
  }

  // ── override events table ──────────────────────────────────────────────────

  function renderOverrides(events) {
    if (!events || events.length === 0) {
      return "<p class='muted'>No override events found.</p>";
    }

    let html = `
      <table class="data-table">
        <thead>
          <tr>
            <th>Repo</th>
            <th>Commit</th>
            <th>Date</th>
            <th>Type</th>
            <th>Approver</th>
          </tr>
        </thead>
        <tbody>
    `;
    for (const ev of events) {
      html += `
        <tr>
          <td>${escHtml(ev.repo || "—")}</td>
          <td class="mono">${escHtml((ev.hash || "").slice(0, 7))}</td>
          <td class="nowrap">${fmtTs(ev.timestamp)}</td>
          <td>${escHtml(ev.override_type || "—")}</td>
          <td>${escHtml(ev.approver || "—")}</td>
        </tr>
      `;
    }
    html += "</tbody></table>";
    return html;
  }

  // ── session summary table (from /api/audit/sessions) ───────────────────────

  function renderSessionTable(summaries, fleet) {
    if (!summaries || summaries.length === 0) {
      return "<p class='muted'>No session summaries available. Sessions are generated from committed snippets.</p>";
    }

    let html = `
      <table class="data-table session-table">
        <thead>
          <tr>
            <th>Session</th>
            ${fleet ? '<th>Repo</th>' : ''}
            <th>Model</th>
            <th>Commits</th>
            <th>Goal</th>
            <th>Tags</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
    `;

    for (const s of summaries) {
      const dateRange = fmtDateRange(s.started_at, s.ended_at);
      const goal = s.goal || "";
      const goalDisplay = goal.length > 50 ? goal.slice(0, 50) + "…" : goal;
      const tags = (s.decision_tags || []).slice(0, 4);
      const tagBadges = tags.map(t => `<span class="tag-badge">${escHtml(t)}</span>`).join(" ");
      const extraTags = (s.decision_tags || []).length > 4 ? ` <span class="muted">+${s.decision_tags.length - 4}</span>` : "";
      const status = sessionStatus(s.ended_at);
      const statusClass = status === "complete" ? "status-complete" : "status-inflight";
      const rowKey = escHtml((s.repo_key || "") + "-" + (s.session_id || ""));

      html += `
        <tr class="session-row" data-row-key="${rowKey}">
          <td class="nowrap">${escHtml(dateRange)}</td>
          ${fleet ? `<td>${escHtml(s.repo || "—")}</td>` : ''}
          <td>${escHtml(s.model || "—")}</td>
          <td class="mono">${s.commit_count || 0}</td>
          <td title="${escHtml(goal)}">${escHtml(goalDisplay || "—")}</td>
          <td>${tagBadges}${extraTags}</td>
          <td><span class="${statusClass}">${status}</span></td>
        </tr>
        <tr class="session-detail" id="detail-${rowKey}" style="display:none">
          <td colspan="${fleet ? 7 : 6}">
            <div class="session-detail-content">
              ${renderSessionDetail(s)}
            </div>
          </td>
        </tr>
      `;
    }

    html += "</tbody></table>";
    return html;
  }

  function renderSessionDetail(s) {
    let html = "";

    // Commits
    const commits = s.commits || [];
    if (commits.length > 0) {
      html += '<div class="detail-section"><strong>Commits</strong><div class="commit-list">';
      for (const c of commits) {
        html += `<div class="commit-entry"><span class="mono">${escHtml(c.short_commit || "?")}</span> <span class="commit-type">${escHtml(c.change_type || "")}</span> ${escHtml(c.intent || "")}</div>`;
      }
      html += "</div></div>";
    }

    // Files touched
    const files = s.files_touched || [];
    if (files.length > 0) {
      html += '<div class="detail-section"><strong>Files touched</strong> <span class="muted">(' + files.length + ')</span><div class="file-list">';
      const displayFiles = files.slice(0, 20);
      for (const f of displayFiles) {
        html += `<div class="mono" style="font-size:11px;color:#555">${escHtml(f)}</div>`;
      }
      if (files.length > 20) {
        html += `<div class="muted">… and ${files.length - 20} more</div>`;
      }
      html += "</div></div>";
    }

    // Notes
    const notes = s.notes || [];
    if (notes.length > 0) {
      html += '<div class="detail-section"><strong>Notes</strong><div class="notes-list">';
      for (const n of notes) {
        html += `<div style="font-size:12px;color:#444;margin:2px 0">• ${escHtml(n)}</div>`;
      }
      html += "</div></div>";
    }

    // Transcript link
    if (s.transcript_ref) {
      html += `<div class="detail-section"><strong>Transcript</strong> <span class="mono muted">${escHtml(s.transcript_ref)}</span></div>`;
    }

    if (!html) {
      html = '<span class="muted">No additional details.</span>';
    }

    return html;
  }

  // ── main render ─────────────────────────────────────────────────────────────

  window.GatorViews.audit = function (data, container, activeRepoKey) {
    const audit = data.audit || {};

    if (audit.error) {
      container.innerHTML = `<div class="error-block">Audit data unavailable: ${escHtml(audit.error)}</div>`;
      return;
    }

    const governance  = audit.governance  || {};
    const sessions    = audit.sessions    || {};
    const overrides   = audit.override_events || [];
    const sigDist     = audit.significance_distribution || {};
    const govCommits  = audit.governed_commits || {};
    const sinceDays   = audit.since_days  || 7;

    // Compute summary metrics
    const totalRepos   = governance.repos || 0;
    const hookCoverage = totalRepos > 0
      ? Math.round((governance.hooks_installed / totalRepos) * 100)
      : 0;
    const overrideRate = (govCommits.total || 0) > 0
      ? Math.round((overrides.length / govCommits.total) * 100)
      : 0;

    // Session summary coverage: repos with recent sessions / total repos
    const reposWithSessions = Object.keys(sessions.by_repo || {}).length;
    const sessionCoverage   = totalRepos > 0
      ? Math.round((reposWithSessions / totalRepos) * 100)
      : 0;

    let html = `
      <div class="view-header">
        <span class="view-title">Audit</span>
        <span class="view-subtitle">Last ${sinceDays} days &nbsp;·&nbsp; ${totalRepos} repos</span>
      </div>

      <div class="card-row">
        <div class="card">
          <div class="card-label">Hook coverage</div>
          <div class="card-value">${hookCoverage}%</div>
          <div class="card-note">${governance.hooks_installed || 0} of ${totalRepos} repos</div>
        </div>
        <div class="card">
          <div class="card-label">Governed commits</div>
          <div class="card-value">${govCommits.total || 0}</div>
          <div class="card-note">fleet total, ${sinceDays}d window</div>
        </div>
        <div class="card">
          <div class="card-label">Override events</div>
          <div class="card-value" style="color:${overrides.length > 0 ? 'var(--color-drifted)' : 'inherit'}">${overrides.length}</div>
          <div class="card-note">${overrideRate}% of governed commits</div>
        </div>
        <div class="card">
          <div class="card-label">Session coverage</div>
          <div class="card-value">${sessionCoverage}%</div>
          <div class="card-note">${reposWithSessions} repos with sessions (${sinceDays}d)</div>
        </div>
      </div>

      <div class="section">
        <div class="section-title">Significance distribution (fleet)</div>
        ${renderSigBars(sigDist)}
      </div>

      <div class="section">
        <div class="section-title">Governed commits by repo (${sinceDays}d)</div>
        ${renderGoverned(govCommits)}
      </div>

      <div class="section">
        <div class="section-title">Override events</div>
        ${renderOverrides(overrides)}
      </div>

      <div class="section">
        <div class="section-title">
          Session summaries
          <button class="fleet-toggle-btn" id="session-fleet-toggle" title="Toggle fleet view">Fleet</button>
        </div>
        <div id="session-table-container">
          <p class="muted" style="padding:12px">Loading sessions...</p>
        </div>
      </div>
    `;

    // Sessions by vendor
    if (sessions.by_vendor && Object.keys(sessions.by_vendor).length > 0) {
      html += `
        <div class="section">
          <div class="section-title">Sessions by agent (${sinceDays}d)</div>
          <table class="data-table">
            <thead><tr><th>Agent</th><th>Sessions</th></tr></thead>
            <tbody>
      `;
      for (const [vendor, count] of Object.entries(sessions.by_vendor)) {
        html += `<tr><td>${escHtml(vendor)}</td><td class="mono">${count}</td></tr>`;
      }
      html += "</tbody></table></div>";
    }

    container.innerHTML = html;

    // Load session summaries lazily from /api/audit/sessions
    // If no repo selected, start in fleet mode and hide the toggle
    let fleetMode = !activeRepoKey;
    const tableContainer = container.querySelector("#session-table-container");
    const fleetBtn = container.querySelector("#session-fleet-toggle");

    if (!activeRepoKey && fleetBtn) {
      fleetBtn.style.display = "none";  // no repo context — fleet-only, hide toggle
    } else if (fleetBtn) {
      fleetBtn.classList.toggle("active", fleetMode);
      fleetBtn.textContent = fleetMode ? "Single repo" : "Fleet";
    }

    function loadSessions() {
      let url;
      if (fleetMode) {
        url = "/api/audit/sessions?fleet=true";
      } else {
        url = "/api/audit/sessions?repo=" + encodeURIComponent(activeRepoKey);
      }
      tableContainer.innerHTML = '<p class="muted" style="padding:12px">Loading sessions...</p>';
      fetch(url)
        .then(r => r.json())
        .then(summaries => {
          if (summaries.error) {
            tableContainer.innerHTML = `<p class="muted" style="padding:12px">${escHtml(summaries.error)}</p>`;
            return;
          }
          tableContainer.innerHTML = renderSessionTable(summaries, fleetMode);

          // Expandable row click handlers
          tableContainer.querySelectorAll(".session-row").forEach(row => {
            row.style.cursor = "pointer";
            row.addEventListener("click", function () {
              const key = this.dataset.rowKey;
              const detail = document.getElementById("detail-" + key);
              if (detail) {
                const visible = detail.style.display !== "none";
                detail.style.display = visible ? "none" : "";
                this.classList.toggle("session-row-expanded", !visible);
              }
            });
          });
        })
        .catch(err => {
          tableContainer.innerHTML = `<p class="muted" style="padding:12px">Failed to load sessions: ${escHtml(err.message)}</p>`;
        });
    }

    if (fleetBtn) {
      fleetBtn.addEventListener("click", function () {
        fleetMode = !fleetMode;
        this.classList.toggle("active", fleetMode);
        this.textContent = fleetMode ? "Single repo" : "Fleet";
        loadSessions();
      });
    }

    // Initial load
    if (!window.GATOR_SNAPSHOT) {
      loadSessions();
    }
  };
})();
