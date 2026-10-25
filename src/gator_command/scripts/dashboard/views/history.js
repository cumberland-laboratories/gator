/**
 * history.js — Commits view for Gator Dashboard.
 *
 * One collapsed line per commit, grouped by day. Opening a commit shows its
 * description (the body without the trailer block, rendered by the closed
 * GatorLoopMarkdown grammar) and a structured Gator record built from the
 * commit's Gator-* trailers. Filter chips and a search box work over the
 * loaded commits.
 *
 * Commit text is model-authored and untrusted: every commit-derived string
 * reaches the DOM through textContent or GatorLoopMarkdown (createElement /
 * createTextNode only), never through innerHTML.
 *
 * Pure git — no session dependency, no aggregator, no snippets.
 * Data source: GET /api/repo/<name>/history?limit=30
 */

(function () {
  "use strict";

  window.GatorViews = window.GatorViews || {};

  // Change-type vocabulary: a consumer of the shared `change-type` contract
  // (producer: VALID_CHANGE_TYPES in gator-pre-commit.py). Every producer
  // value has an entry; tests/test_dashboard_ui/test_commits_view.py pins
  // the keys against the producer so drift fails a test. `group` is the
  // filter chip; an unknown value gets a neutral label.
  const KINDS = {
    feature:     { label: "Feature",      glyph: "✦", group: "feature" },
    fix:         { label: "Fix",          glyph: "✚", group: "fix" },
    docs:        { label: "Docs",         glyph: "▤", group: "docs" },
    release:     { label: "Release",      glyph: "⬆", group: "release" },
    maintenance: { label: "Housekeeping", glyph: "↺", group: "housekeeping" },
    governance:  { label: "Governance",   glyph: "↺", group: "housekeeping" },
    refactor:    { label: "Refactor",     glyph: "↺", group: "housekeeping" },
    test:        { label: "Tests",        glyph: "↺", group: "housekeeping" },
    review:      { label: "Review",       glyph: "◇", group: "other" },
  };

  const FILTERS = [
    ["all", "All"], ["feature", "Features"], ["fix", "Fixes"], ["docs", "Docs"],
    ["housekeeping", "Housekeeping"], ["release", "Releases"],
  ];

  const CHARTER_TEXT = {
    "yes": "✓ Updated with the code",
    "no": "— No code changed",
    "override-skip": "⚑ Skipped by approved override",
  };

  function kindOf(type) {
    if (type && Object.prototype.hasOwnProperty.call(KINDS, type)) return KINDS[type];
    return { label: type ? String(type) : "Commit", glyph: "•", group: "other" };
  }

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = String(text);
    return e;
  }

  // The commit's Gator record from its ordered trailers (first value wins).
  function recordOf(c) {
    const t = {};
    (c.trailers || []).forEach(function (p) {
      if (p && typeof p.key === "string" && !(p.key in t)) t[p.key] = String(p.value || "");
    });
    const split = function (v) {
      return (v || "").split(/[,\s]+/).map(function (s) { return s.trim(); }).filter(Boolean);
    };
    return {
      type: t["Gator-Change-Type"] || "",
      significance: t["Gator-Significance"] || "",
      charterChanged: t["Gator-Charter-Changed"] || "",
      tags: split(t["Gator-Decision-Tags"]),
      issues: split(t["Gator-Issues"]).map(function (s) { return s.replace(/^#/, ""); }),
      charters: t["Gator-Charters"] || "",
      functions: t["Gator-Functions"] || "",
      threads: t["Gator-Threads"] || "",
      override: (t["Gator-Override-Approved-By"] || t["Gator-Override-Block"]
                 || t["Gator-Override-Rules"] || t["Gator-Override-Reason"]) ? {
        by: t["Gator-Override-Approved-By"] || "",
        block: t["Gator-Override-Block"] || "",
        rules: t["Gator-Override-Rules"] || "",
        reason: t["Gator-Override-Reason"] || "",
      } : null,
      // #75: an Architect kept a dangerous-pattern warning. Not an override.
      // Keys are comma-delimited; a key's path may contain spaces, so never
      // split on whitespace here (unlike tags and issues).
      acknowledgement: t["Gator-Dangerous-Patterns"] ? {
        patterns: t["Gator-Dangerous-Patterns"].split(",")
          .map(function (s) { return s.trim(); }).filter(Boolean),
        by: t["Gator-Dangerous-Pattern-Acknowledged-By"] || "",
      } : null,
      // A recorded skip: committed without an Architect decision.
      unacknowledged: t["Gator-Dangerous-Patterns-Unacknowledged"]
        ? t["Gator-Dangerous-Patterns-Unacknowledged"].split(",")
            .map(function (s) { return s.trim(); }).filter(Boolean)
        : null,
    };
  }

  function localDayKey(d) {
    return d.getFullYear() + "-" + (d.getMonth() + 1) + "-" + d.getDate();
  }

  function dayLabel(d, now) {
    const opts = { weekday: "long", month: "long", day: "numeric" };
    if (d.getFullYear() !== now.getFullYear()) opts.year = "numeric";
    const text = d.toLocaleDateString(undefined, opts);
    const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
    if (localDayKey(d) === localDayKey(now)) return "Today · " + text;
    if (localDayKey(d) === localDayKey(yesterday)) return "Yesterday · " + text;
    return text;
  }

  function timeText(d) {
    try {
      return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
    } catch (_) { return ""; }
  }

  function dl(rows) {
    const list = el("dl", "commit-dl");
    rows.forEach(function (r) {
      if (!r[1]) return;
      list.appendChild(el("dt", null, r[0]));
      list.appendChild(el("dd", null, r[1]));
    });
    return list;
  }

  function recordColumn(title) {
    const col = el("div", "commit-record-col");
    col.appendChild(el("h4", null, title));
    return col;
  }

  function chips(values, prefix) {
    const box = el("div", "commit-chips-inline");
    values.forEach(function (v) { box.appendChild(el("span", "commit-chip-inline", (prefix || "") + v)); });
    return box;
  }

  function renderDescription(text) {
    const box = el("div", "commit-desc");
    if (!text) {
      box.appendChild(el("p", "muted", "No description."));
      return box;
    }
    try {
      if (!window.GatorLoopMarkdown) throw new Error("no formatter");
      box.appendChild(window.GatorLoopMarkdown.render(text));
    } catch (_) {
      // Too large or no formatter: the literal text, never markup.
      box.appendChild(el("pre", "commit-desc-raw", text));
    }
    return box;
  }

  function commitBody(c, rec) {
    const body = el("div", "commit-body");
    body.appendChild(renderDescription(c.description));

    const record = el("div", "commit-record");
    if (rec.override) {
      const o = rec.override;
      const note = el("div", "commit-override");
      note.appendChild(el("strong", null, "⚑ Override" + (o.by ? " approved by " + o.by : "") + "."));
      const parts = [];
      if (o.rules) parts.push("Rule " + o.rules + " blocked the commit");
      if (o.block) parts.push("block " + o.block);
      if (o.reason) parts.push("reason: " + o.reason);
      if (parts.length) note.appendChild(document.createTextNode(" " + parts.join("; ") + "."));
      record.appendChild(note);
    }
    if (rec.acknowledgement) {
      const a = rec.acknowledgement;
      const note = el("div", "commit-acknowledgement");
      note.appendChild(el("strong", null, "✓ Architect acknowledgement" + (a.by ? " by " + a.by : "") + "."));
      note.appendChild(document.createTextNode(
        " Kept on the Architect's direction: " + a.patterns.join(", ")
        + ". The decision is in the description."));
      record.appendChild(note);
    }
    if (rec.unacknowledged) {
      const note = el("div", "commit-unacknowledged");
      note.appendChild(el("strong", null, "! Unacknowledged dangerous pattern."));
      note.appendChild(document.createTextNode(
        " Committed without an Architect decision: " + rec.unacknowledged.join(", ") + "."));
      record.appendChild(note);
    }

    const change = recordColumn("Change");
    change.appendChild(dl([
      ["Type", rec.type],
      ["Significance", rec.significance],
      ["Charters", CHARTER_TEXT[rec.charterChanged] || rec.charterChanged],
    ]));
    if (rec.issues.length) {
      change.appendChild(el("h5", null, "Issues"));
      change.appendChild(chips(rec.issues, "#"));
    }
    record.appendChild(change);

    const tags = recordColumn("Decision tags");
    if (rec.tags.length) tags.appendChild(chips(rec.tags));
    else tags.appendChild(el("p", "muted", "None recorded."));
    record.appendChild(tags);

    const layer = recordColumn("Knowledge layer at this commit");
    if (rec.charters || rec.functions || rec.threads) {
      layer.appendChild(dl([
        ["Charters", rec.charters], ["Functions", rec.functions], ["Threads", rec.threads],
      ]));
    } else {
      layer.appendChild(el("p", "muted", "Not recorded."));
    }
    record.appendChild(layer);
    body.appendChild(record);

    // Quiet actions: copy the full hash; show the exact trailer lines.
    const actions = el("div", "commit-actions");
    const copy = el("button", "commit-action commit-copy", "⧉ Copy hash");
    copy.type = "button";
    copy.addEventListener("click", function () {
      const done = function (ok) {
        copy.textContent = ok ? "✓ Copied" : "Copy failed";
        setTimeout(function () { copy.textContent = "⧉ Copy hash"; }, 1500);
      };
      try {
        navigator.clipboard.writeText(c.hash).then(function () { done(true); },
                                                    function () { done(false); });
      } catch (_) { done(false); }
    });
    actions.appendChild(copy);

    const trailers = c.trailers || [];
    if (trailers.length) {
      const rawBtn = el("button", "commit-action commit-raw-toggle", "{ } Raw trailers");
      rawBtn.type = "button";
      rawBtn.setAttribute("aria-expanded", "false");
      const raw = el("pre", "commit-raw",
                     trailers.map(function (p) { return p.key + ": " + p.value; }).join("\n"));
      raw.hidden = true;
      rawBtn.addEventListener("click", function () {
        raw.hidden = !raw.hidden;
        rawBtn.setAttribute("aria-expanded", raw.hidden ? "false" : "true");
      });
      actions.appendChild(rawBtn);
      body.appendChild(actions);
      body.appendChild(raw);
    } else {
      body.appendChild(actions);
    }
    return body;
  }

  function commitRow(c, rec, kind, openSet) {
    const row = el("details", "commit-row");
    row.dataset.kind = kind.group;
    row.dataset.hash = c.hash || "";
    if (openSet.has(c.hash)) row.open = true;

    const summary = el("summary", "commit-summary");
    const kindEl = el("span", "commit-kind");
    kindEl.appendChild(el("span", "commit-tag commit-tag-" + kind.group, kind.glyph + " " + kind.label));
    summary.appendChild(kindEl);

    const head = el("div", "commit-headline");
    head.appendChild(el("div", "commit-subject", c.subject || "(no subject)"));
    const meta = el("div", "commit-meta");
    meta.appendChild(el("span", "commit-hash", c.short_hash || ""));
    const d = new Date(c.date);
    const bits = [];
    if (!isNaN(d)) bits.push(timeText(d));
    if (c.agent && c.architect) bits.push(c.agent + " with " + c.architect);
    else if (c.agent || c.architect || c.author) bits.push(c.agent || c.architect || c.author);
    if (bits.length) meta.appendChild(document.createTextNode(" · " + bits.join(" · ")));
    head.appendChild(meta);
    summary.appendChild(head);

    const flags = el("span", "commit-flags");
    if (rec.significance === "notable") {
      flags.appendChild(el("span", "commit-tag commit-flag-notable", "★ Notable"));
    }
    if (rec.override) {
      const f = el("span", "commit-tag commit-flag-override", "⚑ Override");
      f.title = "Pre-commit block overridden";
      flags.appendChild(f);
    }
    if (rec.acknowledgement) {
      const f = el("span", "commit-tag commit-flag-acknowledged", "✓ Acknowledged");
      f.title = "Dangerous-pattern warning kept on the Architect's direction";
      flags.appendChild(f);
    }
    if (rec.unacknowledged) {
      const f = el("span", "commit-tag commit-flag-unacknowledged", "! Unacknowledged");
      f.title = "Dangerous pattern committed without an Architect decision";
      flags.appendChild(f);
    }
    flags.appendChild(el("span", "commit-chev", "▸"));
    summary.appendChild(flags);
    row.appendChild(summary);

    row.appendChild(commitBody(c, rec));
    row.addEventListener("toggle", function () {
      if (row.open) openSet.add(c.hash); else openSet.delete(c.hash);
    });
    return row;
  }

  function matches(item, query) {
    if (!query) return true;
    const hay = [item.c.subject || "", item.c.hash || "", item.c.short_hash || ""]
      .concat(item.rec.tags).join(" ").toLowerCase();
    return hay.indexOf(query) >= 0;
  }

  function buildView(container, commits) {
    const items = commits.map(function (c) {
      const rec = recordOf(c);
      return { c: c, rec: rec, kind: kindOf(rec.type) };
    });
    const state = { filter: "all", query: "", open: new Set() };

    const root = el("div", "commits-view");
    const toolbar = el("div", "commit-toolbar");
    const chipBar = el("div", "commit-filters");
    chipBar.setAttribute("role", "group");
    chipBar.setAttribute("aria-label", "Filter commits by type");
    FILTERS.forEach(function (f) {
      const n = f[0] === "all" ? items.length
        : items.filter(function (it) { return it.kind.group === f[0]; }).length;
      const b = el("button", "commit-filter");
      b.type = "button";
      b.dataset.filter = f[0];
      b.appendChild(document.createTextNode(f[1]));
      b.appendChild(el("span", "commit-filter-count", n));
      b.setAttribute("aria-pressed", f[0] === state.filter ? "true" : "false");
      b.addEventListener("click", function () {
        state.filter = f[0];
        chipBar.querySelectorAll(".commit-filter").forEach(function (x) {
          x.setAttribute("aria-pressed", x.dataset.filter === state.filter ? "true" : "false");
        });
        renderList();
      });
      chipBar.appendChild(b);
    });
    toolbar.appendChild(chipBar);

    const search = el("input", "commit-search");
    search.type = "search";
    search.placeholder = "Search subject, hash or tag";
    search.setAttribute("aria-label", "Search commits");
    search.addEventListener("input", function () {
      state.query = search.value.trim().toLowerCase();
      renderList();
    });
    toolbar.appendChild(search);
    root.appendChild(toolbar);

    const list = el("div", "commit-list");
    root.appendChild(list);

    function renderList() {
      list.textContent = "";
      const now = new Date();
      let lastDay = null;
      let shown = 0;
      items.forEach(function (it) {
        if (state.filter !== "all" && it.kind.group !== state.filter) return;
        if (!matches(it, state.query)) return;
        const d = new Date(it.c.date);
        const key = isNaN(d) ? "unknown" : localDayKey(d);
        if (key !== lastDay) {
          list.appendChild(el("h3", "commit-day", isNaN(d) ? "Undated" : dayLabel(d, now)));
          lastDay = key;
        }
        list.appendChild(commitRow(it.c, it.rec, it.kind, state.open));
        shown++;
      });
      if (!shown) list.appendChild(el("p", "muted commit-empty", "No commits match."));
    }

    renderList();
    container.textContent = "";
    container.appendChild(root);
  }

  window.GatorViews.history = function (data, container, repoName) {
    container.textContent = "";
    if (!repoName) {
      container.appendChild(el("p", "muted commit-placeholder",
                               "Select a repo from the Fleet view to see its history."));
      return;
    }
    const loadingEl = el("p", "muted commit-placeholder", "Loading history...");
    container.appendChild(loadingEl);

    // #56: another view (e.g. after a Back) may own the container by the
    // time the fetch resolves; a detached loading node means drop the result.
    function stale() { return !loadingEl.isConnected; }

    fetch("/api/repo/" + encodeURIComponent(repoName) + "/history?limit=30")
      .then(function (r) { return r.json(); })
      .then(function (result) {
        if (stale()) return;
        if (result.error) {
          container.textContent = "";
          container.appendChild(el("p", "muted", result.error));
          return;
        }
        const commits = result.commits || [];
        if (commits.length === 0) {
          container.textContent = "";
          container.appendChild(el("p", "muted commit-placeholder", "No commits found."));
          return;
        }
        buildView(container, commits);
      })
      .catch(function (err) {
        if (stale()) return;
        container.textContent = "";
        container.appendChild(el("p", "muted", "Error loading history: " + err.message));
      });
  };

  // Read-only: the change types this view labels (pinned against the producer).
  window.GatorViews.history.changeTypes = Object.keys(KINDS);
})();
