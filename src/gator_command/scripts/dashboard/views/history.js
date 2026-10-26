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
 * Blocked commit (#76): GET /api/repo/<name>/override once per mount, and
 * POST .../override/{approve,cancel} from the dialog (see below).
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
    return { toolbar: toolbar, search: search };
  }

  // ── Blocked commit (#76) ──────────────────────────────────────────────────
  //
  // A quiet toolbar alert and a native <dialog> over the repository's own
  // override CLI, relayed by GET /api/repo/<name>/override and
  // POST .../override/{approve,cancel}. The CLI decides everything: what is
  // covered, what is approvable, and whether a guarded action still matches
  // the state the Architect saw (`revision`). This view only maps the CLI's
  // answer to a label and never classifies a rule. Every CLI-derived string
  // reaches the DOM as text.

  const BLOCK_REFRESH_STATES = ["malformed", "expired", "stale", "legacy", "incomplete"];
  const BLOCK_GROUPS = [
    ["external-approval", "⚑", "External approval"],
    ["pause", "⏸", "Architect decision required"],
    ["fix-required", "✚", "Fix required"],
  ];
  const BLOCK_NAME_MAX = 80;
  const BLOCK_REASON_MAX = 200;
  const BLOCK_FILES_SHOWN = 8;
  const BLOCK_CHANGED_NOTICE = "The blocked commit changed. Review it again before approving.";
  const DISCARD_CHANGED_NOTICE = "The blocked commit changed. Review it, then confirm again.";
  const REFRESH_TEXT = {
    stale: "The staged change differs from the blocked attempt. Retry the commit to "
      + "record a fresh block, or discard this one.",
    expired: "This blocked attempt has expired. Retry the commit, or discard it.",
    malformed: "The recorded block cannot be read. Discard it, then retry the commit.",
    legacy: "This block was recorded by an earlier Gator runtime. Discard it, then "
      + "retry the commit.",
  };

  function overrideUrl(repoName, suffix) {
    return "/api/repo/" + encodeURIComponent(repoName) + "/override" + (suffix || "");
  }

  function fetchOverrideStatus(repoName) {
    return fetch(overrideUrl(repoName), { cache: "no-store" }).then(function (r) {
      return r.json().then(function (d) {
        if (!r.ok || !d || typeof d !== "object" || !d.state) {
          throw new Error((d && d.error) || ("HTTP " + r.status));
        }
        return d;
      });
    });
  }

  function postOverride(repoName, action, body) {
    return fetch(overrideUrl(repoName, "/" + action), {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Gator-Dashboard": "1" },
      body: JSON.stringify(body),
    }).then(function (r) {
      return r.json().catch(function () { return {}; })
        .then(function (d) { return { status: r.status, data: d || {} }; });
    });
  }

  function findingsOf(status, resolution) {
    return (status.findings || []).filter(function (f) { return f.resolution === resolution; });
  }

  // {label, kind} for the toolbar alert, or null for no alert. Approve is
  // offered only for `uncovered_external_rules`, never from approval.state.
  function alertState(status) {
    if (!status || typeof status !== "object" || !status.state) return null;
    const st = status.state;
    if (st === "none" || st === "ungoverned") return null;
    if (BLOCK_REFRESH_STATES.indexOf(st) >= 0) {
      return { label: "⚑ Commit block needs refresh", kind: "refresh" };
    }
    if (st !== "blocked" && st !== "approved") {
      return { label: "⚑ Commit status unavailable", kind: "unavailable" };
    }
    const ext = status.uncovered_external_rules || [];
    const pause = findingsOf(status, "pause").length > 0;
    const fix = findingsOf(status, "fix-required").length > 0;
    if (ext.length) return { label: "⚑ Commit blocked", kind: "blocked" };
    if (pause && !fix) return { label: "⚑ Architect decision needed", kind: "pause" };
    if (fix && !pause) return { label: "⚑ Commit fix needed", kind: "fix" };
    if (pause && fix) return { label: "⚑ Commit blocked", kind: "mixed" };
    return { label: "✓ Approved — retry commit", kind: "approved" };
  }

  function approvableHere(status) {
    return status.state === "blocked"
      && (status.uncovered_external_rules || []).length > 0
      && (status.approve_refusal === null || status.approve_refusal === "too-recent");
  }

  function ageText(seconds) {
    const s = Math.max(0, Math.round(Number(seconds) || 0));
    if (s < 60) return s + " s ago";
    if (s < 3600) return Math.round(s / 60) + " min ago";
    return Math.round(s / 3600) + " h ago";
  }

  function mountBlockAlert(repoName, toolbar, search, statusPromise) {
    const ctl = { repoName: repoName, toolbar: toolbar, search: search, status: null, button: null };

    ctl.update = function (status) {
      ctl.status = status;
      if (ctl.button && ctl.button.parentNode) ctl.button.parentNode.removeChild(ctl.button);
      ctl.button = null;
      const a = alertState(status);
      if (!a || !toolbar.isConnected) return;
      const b = el("button", "commit-block-alert", a.label);
      b.type = "button";
      b.dataset.kind = a.kind;
      b.setAttribute("aria-haspopup", "dialog");
      b.addEventListener("click", function () { openBlockDialog(ctl, b); });
      toolbar.insertBefore(b, search || null);
      ctl.button = b;
    };

    statusPromise.then(function (status) {
      if (status && toolbar.isConnected) ctl.update(status);
    });
    return ctl;
  }

  function openBlockDialog(ctl, invoker) {
    const dlg = el("dialog", "loop-dialog commit-block-dialog");
    dlg.setAttribute("aria-labelledby", "commit-block-title");
    const st = {
      status: ctl.status,
      fetchedAt: Date.now(),
      name: ctl.status.architect_default || "",
      reason: "",
      notice: "",
      error: "",
      success: "",
      confirmDiscard: false,
      sending: false,
      timer: null,
    };

    function waitLeft() {
      const wait = Number(st.status.approve_wait_seconds) || 0;
      return Math.max(0, Math.ceil((st.fetchedAt + wait * 1000 - Date.now()) / 1000));
    }

    function fieldsValid() {
      const n = st.name.trim();
      const r = st.reason.trim();
      return n.length > 0 && n.length <= BLOCK_NAME_MAX
        && r.length > 0 && r.length <= BLOCK_REASON_MAX;
    }

    function setStatus(fresh, notice) {
      st.status = fresh;
      st.fetchedAt = Date.now();
      if (notice !== undefined) st.notice = notice;
      ctl.update(fresh);
    }

    function changed(fresh) {
      const a = st.status;
      const blockId = function (s) { return s.block ? s.block.block_id : null; };
      return fresh.revision !== a.revision || fresh.state !== a.state
        || blockId(fresh) !== blockId(a);
    }

    function scopeLine(status) {
      const b = status.block;
      const box = el("div", "commit-block-scope");
      if (!b) return box;
      const parts = ["Block " + b.block_id, "recorded " + ageText(b.age_seconds)];
      if (b.expires_epoch) {
        const exp = new Date(b.expires_epoch * 1000);
        if (!isNaN(exp)) parts.push("expires " + exp.toLocaleString());
      }
      parts.push(b.tree_matches ? "Staged change matches" : "Staged change differs");
      box.appendChild(el("p", "commit-block-scope-line", parts.join(" · ")));
      const files = b.files || [];
      const total = Number(b.files_total) || files.length;
      if (files.length) {
        box.appendChild(el("p", "commit-block-files",
                           "Staged: " + files.slice(0, BLOCK_FILES_SHOWN).join(", ")));
        if (total > BLOCK_FILES_SHOWN) {
          const more = el("details", "commit-block-more");
          more.appendChild(el("summary", "commit-block-more-toggle",
                              "+" + (total - BLOCK_FILES_SHOWN) + " more"));
          let rest = files.slice(BLOCK_FILES_SHOWN).join(", ");
          if (total > files.length) rest += " (and " + (total - files.length) + " not listed)";
          more.appendChild(el("p", "commit-block-files", rest));
          box.appendChild(more);
        }
      }
      return box;
    }

    function groups(status) {
      const box = el("div", "commit-block-groups");
      const approvedBy = (status.approval && status.approval.approved_by) || "";
      BLOCK_GROUPS.forEach(function (g) {
        const items = findingsOf(status, g[0]);
        if (!items.length) return;
        const sec = el("section", "commit-block-group");
        sec.dataset.resolution = g[0];
        sec.appendChild(el("h3", "commit-block-group-title", g[1] + " " + g[2]));
        const list = el("ul", "commit-block-list");
        items.forEach(function (f) {
          const li = el("li", "commit-block-finding");
          li.dataset.rule = f.rule;
          const head = el("div", "commit-block-finding-head");
          head.appendChild(el("span", "commit-block-rule", f.rule));
          if (g[0] === "external-approval") {
            const tag = f.covered
              ? el("span", "commit-block-tag commit-block-covered",
                   "✓ Approved" + (approvedBy ? " by " + approvedBy : ""))
              : el("span", "commit-block-tag commit-block-needs", "Needs approval");
            head.appendChild(tag);
          }
          li.appendChild(head);
          if (f.message) li.appendChild(el("p", "commit-block-msg", f.message));
          list.appendChild(li);
        });
        sec.appendChild(list);
        box.appendChild(sec);
      });
      return box;
    }

    function guidance(status, body) {
      const note = function (text) { body.appendChild(el("p", "loop-dialog-note", text)); };
      const st0 = status.state;
      if (st0 === "unsupported" || st0 === "unavailable" || st0 === "incomplete") {
        note(status.message || "This repository cannot report a blocked commit to the Dashboard.");
        if (status.command) {
          const p = el("p", "commit-block-command");
          p.appendChild(document.createTextNode("In a terminal: "));
          p.appendChild(el("code", "commit-block-code", status.command));
          body.appendChild(p);
        }
        return;
      }
      if (REFRESH_TEXT[st0]) note(REFRESH_TEXT[st0]);
      const covered = status.covered_rules || [];
      const uncovered = status.uncovered_external_rules || [];
      if (covered.length) {
        const by = (status.approval && status.approval.approved_by) || "the Architect";
        note("External approval recorded by " + by + " for " + covered.join(", ") + ".");
        if (uncovered.length) note("Still needs approval: " + uncovered.join(", ") + ".");
      }
      if (findingsOf(status, "external-approval").length) {
        note("An approval covers only this exact staged change. Changing what is "
             + "staged needs a new blocked attempt.");
      }
      if (findingsOf(status, "pause").length) {
        note("A pause is resolved in the active agent session: the Architect's decision "
             + "is recorded in commit_draft.md. It cannot be approved here.");
      }
      if (findingsOf(status, "fix-required").length) {
        note("Fix-required findings must be corrected, then the commit retried.");
      }
    }

    function fields(body) {
      const area = el("div", "loop-ctrl-input-area commit-block-fields");
      const nameLabel = el("label", "loop-ctrl-label", "Architect name");
      nameLabel.htmlFor = "commit-block-name";
      const name = el("input", "loop-ctrl-input");
      name.id = "commit-block-name";
      name.type = "text";
      name.maxLength = BLOCK_NAME_MAX;
      name.value = st.name;
      name.disabled = st.sending;
      const reasonLabel = el("label", "loop-ctrl-label", "Reason (required)");
      reasonLabel.htmlFor = "commit-block-reason";
      const reason = el("textarea", "loop-ctrl-input");
      reason.id = "commit-block-reason";
      reason.rows = 3;
      reason.maxLength = BLOCK_REASON_MAX;
      reason.value = st.reason;
      reason.disabled = st.sending;
      const count = el("span", "commit-block-count", st.reason.length + " / " + BLOCK_REASON_MAX);
      count.setAttribute("aria-live", "polite");
      name.addEventListener("input", function () { st.name = name.value; syncApprove(); });
      reason.addEventListener("input", function () {
        st.reason = reason.value;
        count.textContent = st.reason.length + " / " + BLOCK_REASON_MAX;
        syncApprove();
      });
      area.appendChild(nameLabel);
      area.appendChild(name);
      area.appendChild(reasonLabel);
      area.appendChild(reason);
      area.appendChild(count);
      body.appendChild(area);
    }

    function syncApprove() {
      const btn = dlg.querySelector(".commit-block-approve");
      if (!btn) return;
      if (st.sending) {
        btn.disabled = true;
        btn.textContent = "Sending…";
        return;
      }
      const left = waitLeft();
      btn.textContent = left > 0 ? "Approve (available in " + left + "s)" : "Approve";
      btn.disabled = left > 0 || !fieldsValid();
      if (left > 0 && !st.timer) {
        st.timer = setTimeout(function () { st.timer = null; syncApprove(); }, 1000);
      }
    }

    function button(cls, text, onClick) {
      const b = el("button", cls, text);
      b.type = "button";
      b.disabled = st.sending;
      b.addEventListener("click", onClick);
      return b;
    }

    function render() {
      dlg.textContent = "";
      const status = st.status;
      const unavailable = ["unsupported", "unavailable"].indexOf(status.state) >= 0;
      dlg.appendChild(el("h2", "loop-dialog-title",
                         unavailable ? "Commit status unavailable" : "Commit blocked"))
        .id = "commit-block-title";
      if (st.notice) {
        const n = el("p", "commit-block-notice", st.notice);
        n.setAttribute("role", "status");
        dlg.appendChild(n);
      }
      if (st.success) {
        const s = el("p", "commit-block-success", st.success);
        s.setAttribute("role", "status");
        dlg.appendChild(s);
        const actions = el("div", "loop-dialog-actions");
        actions.appendChild(button("loop-ctrl-cancel commit-block-close", "Close", close));
        dlg.appendChild(actions);
        return;
      }
      dlg.appendChild(scopeLine(status));
      if (status.state === "incomplete" && status.findings_total) {
        dlg.appendChild(el("p", "commit-block-scope-line",
                           "Showing " + (status.findings || []).length + " of "
                           + status.findings_total + " findings."));
      }
      dlg.appendChild(groups(status));
      guidance(status, dlg);
      const canApprove = approvableHere(status) && !st.confirmDiscard;
      if (canApprove) fields(dlg);

      const err = el("p", "loop-ctrl-error commit-block-error", st.error);
      err.setAttribute("role", "alert");
      err.hidden = !st.error;
      dlg.appendChild(err);

      const actions = el("div", "loop-dialog-actions");
      if (st.confirmDiscard) {
        actions.appendChild(el("p", "loop-dialog-note commit-block-confirm",
          "Discard this blocked attempt and any approval? Nothing is committed. "
          + "The next commit attempt records a fresh block."));
        actions.appendChild(button("loop-ctrl-cancel commit-block-keep", "Keep", function () {
          st.confirmDiscard = false;
          render();
        }));
        actions.appendChild(button("loop-ctrl-confirm commit-block-discard-confirm", "Discard",
                                   discard));
      } else {
        if (status.revision) {
          actions.appendChild(button("loop-dialog-end-instead commit-block-discard",
                                     "Discard block…", function () {
            st.confirmDiscard = true;
            st.error = "";
            render();
          }));
        }
        actions.appendChild(button("loop-ctrl-cancel commit-block-close", "Close", close));
        if (canApprove) {
          actions.appendChild(button("loop-ctrl-confirm commit-block-approve", "Approve", approve));
        }
      }
      dlg.appendChild(actions);
      syncApprove();
    }

    function setSending(on) {
      st.sending = on;
      if (on) dlg.dataset.sending = "1"; else delete dlg.dataset.sending;
    }

    function finish(error) {
      setSending(false);
      if (error !== undefined) st.error = error;
      if (dlg.isConnected) render();
    }

    // Re-read the state; resolve with the fresh status, or null when it
    // changed (the dialog then shows it with `notice`) or the read failed.
    function preflight(notice) {
      return fetchOverrideStatus(ctl.repoName).then(function (fresh) {
        if (changed(fresh)) {
          setStatus(fresh, notice);
          st.confirmDiscard = false;
          finish("");
          return null;
        }
        return fresh;
      }, function (e) {
        finish("Could not refresh the blocked commit: " + e.message + ". Nothing was sent.");
        return null;
      });
    }

    function afterRefusal(res, notice) {
      const refusal = res.data.refusal;
      const message = res.data.message || res.data.error || ("Request failed (HTTP " + res.status + ")");
      if (refusal === "block-changed" || refusal === "findings-changed") {
        return fetchOverrideStatus(ctl.repoName).then(function (fresh) {
          setStatus(fresh, notice);
          st.confirmDiscard = false;
          finish(message);
        }, function () { finish(message); });
      }
      finish(message);
      return null;
    }

    function approve() {
      if (st.sending || !fieldsValid() || waitLeft() > 0) return;
      st.error = "";
      st.notice = "";
      setSending(true);
      render();
      preflight(BLOCK_CHANGED_NOTICE).then(function (fresh) {
        if (!fresh) return null;
        const body = { block_id: st.status.block.block_id, revision: st.status.revision,
                       name: st.name.trim(), reason: st.reason.trim() };
        return postOverride(ctl.repoName, "approve", body).then(function (res) {
          if (res.status !== 200 || !res.data.ok) return afterRefusal(res, BLOCK_CHANGED_NOTICE);
          const rem = res.data.remaining || {};
          const remaining = (rem.fix_required || []).length + (rem.paused || []).length;
          st.success = remaining
            ? "External approval recorded. This commit is still blocked until the "
              + "remaining findings are resolved."
            : "External approval recorded. Retry the commit in your Git client or agent session.";
          finish("");
          return fetchOverrideStatus(ctl.repoName).then(function (s) { ctl.update(s); },
                                                        function () {});
        });
      }).catch(function (e) { finish("Not sent: " + e.message); });
    }

    function discard() {
      if (st.sending) return;
      st.error = "";
      st.notice = "";
      setSending(true);
      render();
      preflight(DISCARD_CHANGED_NOTICE).then(function (fresh) {
        if (!fresh) return null;
        const body = { block_id: st.status.block ? st.status.block.block_id : null,
                       revision: st.status.revision };
        return postOverride(ctl.repoName, "cancel", body).then(function (res) {
          if (res.status !== 200 || !res.data.ok) return afterRefusal(res, DISCARD_CHANGED_NOTICE);
          st.confirmDiscard = false;
          st.success = "Discarded. Nothing was committed. The next commit attempt "
            + "records a fresh block.";
          finish("");
          return fetchOverrideStatus(ctl.repoName).then(function (s) { ctl.update(s); },
                                                        function () {});
        });
      }).catch(function (e) { finish("Not sent: " + e.message); });
    }

    function close() {
      if (st.sending) return;
      dlg.close();
    }

    dlg.addEventListener("cancel", function (e) {
      if (st.sending) e.preventDefault();
    });
    dlg.addEventListener("close", function () {
      if (st.timer) clearTimeout(st.timer);
      if (dlg.parentNode) dlg.parentNode.removeChild(dlg);
      const target = (ctl.button && ctl.button.isConnected) ? ctl.button : ctl.search;
      if (target && target.isConnected) {
        target.focus();
        return;
      }
      // No alert and no search box (empty or failed history): the page title.
      const title = document.getElementById("topbar-title");
      if (title) {
        if (title.getAttribute("tabindex") !== "-1") title.setAttribute("tabindex", "-1");
        title.focus();
      }
    });

    render();
    (ctl.toolbar.parentNode || document.body).appendChild(dlg);
    dlg.showModal();
    return dlg;
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

    // #76: the blocked-commit status is fetched once, beside the history
    // (no poller). A failure (or the offline snapshot) means no alert.
    const overridePromise = fetchOverrideStatus(repoName).catch(function () { return null; });

    // A history that is empty or failed still gets the block alert: a new
    // repository can block its very first commit, and a history error must
    // not hide a recorded block. The message keeps its own region.
    function showMessage(cls, text) {
      container.textContent = "";
      const root = el("div", "commits-view");
      const toolbar = el("div", "commit-toolbar commit-toolbar-bare");
      root.appendChild(toolbar);
      root.appendChild(el("p", cls, text));
      container.appendChild(root);
      mountBlockAlert(repoName, toolbar, null, overridePromise);
    }

    fetch("/api/repo/" + encodeURIComponent(repoName) + "/history?limit=30")
      .then(function (r) { return r.json(); })
      .then(function (result) {
        if (stale()) return;
        if (result.error) {
          showMessage("muted commit-history-message", result.error);
          return;
        }
        const commits = result.commits || [];
        if (commits.length === 0) {
          showMessage("muted commit-placeholder", "No commits found.");
          return;
        }
        const view = buildView(container, commits);
        mountBlockAlert(repoName, view.toolbar, view.search, overridePromise);
      })
      .catch(function (err) {
        if (stale()) return;
        showMessage("muted commit-history-message", "Error loading history: " + err.message);
      });
  };

  // Read-only: the change types this view labels (pinned against the producer).
  window.GatorViews.history.changeTypes = Object.keys(KINDS);
  // Read-only: the blocked-commit alert mapping (pinned by the block UI test).
  window.GatorViews.history.alertState = alertState;
})();
