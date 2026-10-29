/**
 * settings.js — Settings view for Gator Dashboard.
 *
 * Read-only commit policy (#75): the pre-commit hook's two categories and
 * each repository's effective posture. The strict/warn/off selector was
 * retired; the only control is Fleet's machine-local Warn checkbox. The
 * posture text comes from window.GatorCommitPolicy
 * (views/fleet.js, which loads first) over the Fleet payload, so this view
 * makes no request.
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

    container.innerHTML = html;
  };
})();
