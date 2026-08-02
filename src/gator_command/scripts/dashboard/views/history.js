/**
 * history.js — History view for Gator Dashboard.
 *
 * Shows recent commits from git log with rich descriptions.
 * Pure git — no session dependency, no aggregator, no snippets.
 *
 * Data source: GET /api/repo/<name>/history?limit=20
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

  function fmtDate(ts) {
    if (!ts) return "";
    try {
      return new Date(ts).toLocaleDateString(undefined, {
        year: "numeric", month: "short", day: "numeric",
        hour: "2-digit", minute: "2-digit",
      });
    } catch (_) { return ts; }
  }

  function renderBody(body) {
    if (!body) return "";
    // Convert markdown-like bullet lists to HTML
    const lines = body.split("\n");
    const parts = [];
    let inList = false;
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
        if (!inList) { parts.push("<ul>"); inList = true; }
        parts.push("<li>" + escHtml(trimmed.slice(2)) + "</li>");
      } else {
        if (inList) { parts.push("</ul>"); inList = false; }
        if (trimmed) {
          parts.push("<p>" + escHtml(trimmed) + "</p>");
        }
      }
    }
    if (inList) parts.push("</ul>");
    return parts.join("\n");
  }

  window.GatorViews.history = function (data, container, repoName) {
    container.innerHTML = "<p class='muted' style='padding:20px'>Loading history...</p>";

    if (!repoName) {
      container.innerHTML = "<p class='muted' style='padding:40px;text-align:center'>Select a repo from the Fleet view to see its history.</p>";
      return;
    }

    fetch("/api/repo/" + encodeURIComponent(repoName) + "/history?limit=30")
      .then(function (r) { return r.json(); })
      .then(function (result) {
        if (result.error) {
          container.innerHTML = "<p class='muted'>" + escHtml(result.error) + "</p>";
          return;
        }
        const commits = result.commits || [];
        if (commits.length === 0) {
          container.innerHTML = "<p class='muted' style='padding:20px'>No commits found.</p>";
          return;
        }

        var html = "<div class='history-view' style='padding:16px;max-width:900px'>";
        html += "<h2 style='margin:0 0 16px 0;font-size:18px;font-weight:600'>" + escHtml(repoName) + " — Recent Commits</h2>";

        for (var i = 0; i < commits.length; i++) {
          var c = commits[i];
          var hasBody = c.body && c.body.trim();
          var agentBadge = c.agent ? "<span class='history-badge agent'>" + escHtml(c.agent) + "</span>" : "";
          var architectBadge = c.architect ? "<span class='history-badge architect'>" + escHtml(c.architect) + "</span>" : "";

          html += "<div class='history-commit" + (hasBody ? " has-body" : "") + "'>";
          html += "<div class='history-header'>";
          html += "<code class='history-hash'>" + escHtml(c.short_hash) + "</code>";
          html += "<span class='history-subject'>" + escHtml(c.subject) + "</span>";
          html += "<span class='history-meta'>" + fmtDate(c.date) + " · " + escHtml(c.author) + "</span>";
          html += agentBadge + architectBadge;
          html += "</div>";

          if (hasBody) {
            html += "<div class='history-body'>" + renderBody(c.body) + "</div>";
          }

          html += "</div>";
        }

        html += "</div>";
        container.innerHTML = html;
      })
      .catch(function (err) {
        container.innerHTML = "<p class='muted'>Error loading history: " + escHtml(err.message) + "</p>";
      });
  };
})();
