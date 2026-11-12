/**
 * settings.js — Settings view for Gator Dashboard.
 *
 * Read-only commit policy (#75): the pre-commit hook's two categories and
 * each repository's effective posture. The strict/warn/off selector was
 * retired; the only control is Fleet's machine-local Warn checkbox. The
 * posture text comes from window.GatorCommitPolicy
 * (views/fleet.js, which loads first) over the Fleet payload.
 *
 * Connected AI tools: Gator's session hooks in each AI tool's user settings
 * on this machine. Read fresh from GET /api/integration (machine state is
 * not in the Fleet payload); the Codex /hooks reminder's Done button posts
 * /api/integration/dismiss-codex-reminder. Every state is a word, never
 * colour alone.
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

  // The fixed first-pass policy (precommit_policy.py). Read-only.
  const CATEGORIES = [
    ["Charter integrity", "Block",
     "Code needs its required charter update. When no charter edit is warranted, only the Architect may approve the exact staged change."],
    ["Dangerous patterns", "Pause",
     "HIGH/CRITICAL findings pause the commit until the Architect's decision is recorded; a skip without one is recorded as unacknowledged."],
  ];

  function posture(repo) {
    if (window.GatorCommitPolicy) return window.GatorCommitPolicy.posture(repo);
    return { label: "Default", note: "" };
  }

  function toolState(info) {
    if (info.problem) return "Problem: Gator could not read this settings file";
    if (info.connected) return "Connected";
    if (info.present) return "Not connected yet";
    return "Not installed";
  }

  function renderIntegration(box, report) {
    if (!report || report.state === "error") {
      box.innerHTML = `<h3 class="settings-integration-title" style="margin:0 0 12px 0;font-size:14px;font-weight:600">Connected AI tools</h3>
        <p class="muted">Gator could not read this machine's connection state${report && report.detail ? ": " + escHtml(report.detail) : "."}</p>`;
      return;
    }
    const rows = Object.values(report.vendors || {}).map(v => `
      <tr data-vendor="${escHtml(v.display)}">
        <td>${escHtml(v.display)}</td>
        <td class="settings-integration-state">${escHtml(toolState(v))}</td>
        <td class="muted settings-integration-path">${escHtml(v.config_path)}</td>
      </tr>`).join("");
    let html = `
      <h3 class="settings-integration-title" style="margin:0 0 12px 0;font-size:14px;font-weight:600">Connected AI tools</h3>
      <p class="muted" style="font-size:12px;margin:0 0 12px 0">
        Gator adds its two session hooks to the user settings of each AI tool installed on this machine. Repositories carry no AI-tool files.
      </p>
      <table class="data-table settings-integration-table">
        <thead><tr><th>AI tool</th><th>State</th><th>Settings file</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
    if (report.state === "unreadable") {
      html += `<p class="settings-integration-note">Gator's connection record is unreadable. Reset it with <code>gator integration remove</code>.</p>`;
    }
    if (report.codex_reminder_due) {
      html += `<p class="settings-integration-reminder">In Codex, approve Gator's hook once: run <code>/hooks</code>.
        <button type="button" class="gator-btn settings-integration-done">Done</button></p>`;
    }
    box.innerHTML = html;
    const done = box.querySelector(".settings-integration-done");
    if (done) {
      done.addEventListener("click", function () {
        done.disabled = true;
        fetch("/api/integration/dismiss-codex-reminder", {
          method: "POST",
          headers: { "X-Gator-Dashboard": "1" },
        })
          .then(r => r.json())
          .then(body => renderIntegration(box, body.status || body))
          .catch(() => { done.disabled = false; });
      });
    }
  }

  function loadIntegration(box) {
    fetch("/api/integration")
      .then(r => r.json())
      .then(report => renderIntegration(box, report))
      .catch(() => renderIntegration(box, null));
  }

  window.GatorViews.settings = function (data, container) {
    const repos = data.standalone ? (data.repos || []) : ((data.fleet || {}).repos || []);

    let html = `
      <div class="view-header">
        <span class="view-title">Settings</span>
        <span class="view-subtitle">Per-repo governance configuration</span>
      </div>
      <div class="section settings-commit-policy">
        <h3 style="margin:0 0 12px 0;font-size:14px;font-weight:600">Commit policy</h3>
        <p class="muted" style="font-size:12px;margin:0 0 12px 0">
          The pre-commit checks have two categories. This policy is fixed and read-only.
        </p>
        <table class="data-table settings-policy-table">
          <thead><tr><th>Category</th><th>Current policy</th><th>Meaning</th></tr></thead>
          <tbody>
            ${CATEGORIES.map(c => `<tr><td>${escHtml(c[0])}</td><td>${escHtml(c[1])}</td><td>${escHtml(c[2])}</td></tr>`).join("")}
          </tbody>
        </table>
      </div>
    `;

    if (repos.length > 0) {
      html += `
        <div class="section">
          <h3 style="margin:0 0 12px 0;font-size:14px;font-weight:600">Repositories</h3>
          <table class="data-table settings-repo-table">
            <thead><tr><th>Repo</th><th>Commit policy</th><th>Note</th></tr></thead>
            <tbody>
      `;
      for (const repo of repos) {
        const p = posture(repo);
        const label = p.label;
        const note = p.note;
        html += `
          <tr data-repo="${escHtml(repo.name || "")}">
            <td>${escHtml(repo.name || "")}</td>
            <td class="settings-policy">${escHtml(label)}</td>
            <td class="settings-policy-note">${escHtml(note)}</td>
          </tr>
        `;
      }
      html += `</tbody></table></div>`;
    } else {
      html += `<div class="section"><p class="muted">No repos registered.</p></div>`;
    }

    html += `<div class="section settings-integration"><h3 class="settings-integration-title" style="margin:0 0 12px 0;font-size:14px;font-weight:600">Connected AI tools</h3><p class="muted">Loading…</p></div>`;

    container.innerHTML = html;
    loadIntegration(container.querySelector(".settings-integration"));
  };
})();
