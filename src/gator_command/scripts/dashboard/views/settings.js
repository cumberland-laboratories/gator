/**
 * settings.js — Settings view for Gator Dashboard.
 *
 * Per-repo settings: enforcement level and governance topology.
 * No dashboard-wide mode toggle — topology is per-repo.
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

  window.GatorViews.settings = function (data, container, opts) {
    const standalone = opts.standalone || false;
    const repos = data.standalone ? (data.repos || []) : ((data.fleet || {}).repos || []);

    let html = `
      <div class="view-header">
        <span class="view-title">Settings</span>
        <span class="view-subtitle">Per-repo governance configuration</span>
      </div>
    `;

    if (repos.length > 0) {
      html += `
        <div class="section">
          <h3 style="margin:0 0 12px 0;font-size:14px;font-weight:600">Repo Governance</h3>
          <p class="muted" style="font-size:12px;margin:0 0 12px 0">
            <strong>Enforcement</strong>: controls whether the pre-commit hook blocks commits (strict), warns only (warn), or skips checks (off).
          </p>
          <table class="data-table">
            <thead>
              <tr>
                <th>Repo</th>
                <th>Enforcement</th>
              </tr>
            </thead>
            <tbody>
      `;

      for (const repo of repos) {
        const name = repo.name || "";
        const accessible = repo.accessible !== false;
        html += `
          <tr>
            <td>${escHtml(name)}</td>
            <td>
              <select class="enforce-select" data-repo="${escHtml(name)}" ${accessible ? "" : "disabled"}>
                <option value="strict">strict</option>
                <option value="warn">warn</option>
                <option value="off">off</option>
              </select>
              <span class="enforce-status"></span>
              ${accessible ? "" : '<span class="muted" style="font-size:11px"> (not accessible)</span>'}
            </td>
          </tr>
        `;
      }

      html += `</tbody></table></div>`;
    } else {
      html += `<div class="section"><p class="muted">No repos registered.</p></div>`;
    }

    container.innerHTML = html;

    // Load current values from each repo
    container.querySelectorAll(".enforce-select").forEach(select => {
      const repoName = select.dataset.repo;
      fetch(`/api/repo/${encodeURIComponent(repoName)}`)
        .then(r => r.json())
        .then(repoData => {
          const level = (repoData.config || {}).enforcement_level || "strict";
          select.value = level;
        })
        .catch(() => {});

      select.addEventListener("change", async function () {
        const statusSpan = this.nextElementSibling;
        try {
          const resp = await fetch(`/api/repo/${encodeURIComponent(repoName)}/config`, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-Gator-Dashboard": "1" },
            body: JSON.stringify({ enforcement_level: this.value }),
          });
          const result = await resp.json();
          statusSpan.textContent = result.status === "ok" ? " saved" : " error";
          statusSpan.style.color = result.status === "ok" ? "var(--color-healthy)" : "var(--color-critical)";
          setTimeout(() => { statusSpan.textContent = ""; }, 2000);
        } catch (err) {
          statusSpan.textContent = " error";
          statusSpan.style.color = "var(--color-critical)";
        }
      });
    });

  };
})();
