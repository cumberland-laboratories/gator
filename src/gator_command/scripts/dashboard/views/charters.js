/**
 * views/charters.js — Charters view: charter health, code map and the charter
 * sync check (charters-sidebar-sync; charters-health-section Release A).
 *
 * Repository-scoped, in three tabs. Overview shows the charter report's
 * health tiles (GET/POST /api/repo/<name>/charters-report) above the charter
 * sync check (GET/POST /api/repo/<name>/charter-sync). Code shows where the
 * code is by charter. Features is a placeholder for a later release.
 *
 * The server owns both checks and their sanitized results; the page only
 * shows what the server returned, never an optimistic result. A failed run
 * or refresh keeps the displayed figures and shows an alert. A page open
 * makes one report GET and at most one automatic report refresh; nothing is
 * timed. The mount sends one POST at a time, because both runs take the
 * same per-repository lock. State is always a word; colours and bars are
 * decorative.
 *
 * Exposes: window.GatorViews.charters(data, container, repoName, repoKey)
 */

(function () {
  "use strict";

  window.GatorViews = window.GatorViews || {};

  var VISIBLE_GROUPS = 8;
  var STATE_WORDS = { "current": "Current", "needs-review": "Needs review" };
  var TABS = [
    { key: "overview", label: "Overview" },
    { key: "code", label: "Code" },
    { key: "features", label: "Features" },
  ];
  // Freshness and target band, each a symbol plus a word (never colour alone).
  var FRESHNESS = {
    "current": ["✓", "Current"],
    "stale": ["▲", "Stale"],
    "unknown": ["?", "Not verified"],
  };
  var BANDS = {
    "within": ["✓", "In range"],
    "below": ["▲", "Below range"],
    "above": ["▲", "Above range"],
  };
  var mountGen = 0;
  var selectedTab = "overview";   // module-local; resets on page load

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = String(text);
    return e;
  }

  function dot(kind) {
    var d = el("span", "charters-dot charters-dot-" + kind);
    d.setAttribute("aria-hidden", "true");
    return d;
  }

  function plural(n, word) {
    return n + " " + word + (n === 1 ? "" : "s");
  }

  function route(repoName) {
    return "/api/repo/" + encodeURIComponent(repoName) + "/charter-sync";
  }

  function reportRoute(repoName) {
    return "/api/repo/" + encodeURIComponent(repoName) + "/charters-report";
  }

  function num(n) {
    return Number(n).toLocaleString("en-US");
  }

  function postJSON(url) {
    return fetch(url, {
      method: "POST",
      cache: "no-store",
      headers: { "X-Gator-Dashboard": "1", "Content-Type": "application/json" },
      body: "{}",
    }).then(function (r) {
      return r.json().catch(function () { return {}; })
        .then(function (j) { return { ok: r.ok, status: r.status, data: j }; });
    });
  }

  // The Repo view's logical path: `.gator/` content is addressed without
  // the prefix; other namespaces keep their path.
  function toLogical(rel) {
    return rel.indexOf(".gator/") === 0 ? rel.slice(".gator/".length) : rel;
  }

  function relativeTime(iso) {
    var t = Date.parse(iso);
    if (isNaN(t)) return iso;
    var s = Math.max(0, Math.round((Date.now() - t) / 1000));
    if (s < 60) return "just now";
    if (s < 3600) return plural(Math.round(s / 60), "minute") + " ago";
    if (s < 86400) return plural(Math.round(s / 3600), "hour") + " ago";
    return plural(Math.round(s / 86400), "day") + " ago";
  }

  function openFile(repoName, repoKey, rel) {
    var repo = window.GatorViews.repo;
    if (repo && typeof repo.preselect === "function") repo.preselect(repoKey, toLogical(rel));
    if (typeof window.gatorNavToRepo === "function") window.gatorNavToRepo(repoName, repoKey);
  }

  function actionButton(label, onClick) {
    var b = el("button", "charters-action", label);
    b.type = "button";
    b.addEventListener("click", onClick);
    return b;
  }

  function renderIntro(body) {
    body.textContent = "";
    body.appendChild(el("p", "charters-prose",
      "No charter sync check has been recorded for this checkout."));
    body.appendChild(el("p", "charters-prose",
      "The check reads charters and source structure. It does not edit code or "
      + "charters. It writes a reviewable report and repair sketch to .gator/artifacts/."));
  }

  function findingItem(g, ctx) {
    var li = el("li", "charters-finding");
    li.dataset.kind = g.kind;
    li.appendChild(dot(g.kind === "coverage-gap" ? "missing" : "review"));
    var main = el("div", "charters-finding-main");
    var head = el("div", "charters-finding-head");
    head.appendChild(el("span", "charters-finding-label", g.label));
    head.appendChild(el("span", "charters-finding-count", plural(g.count, "finding")));
    main.appendChild(head);
    main.appendChild(el("p", "charters-prose charters-finding-message", g.message));
    var actions = el("div", "charters-actions");
    if (g.charter_path) {
      actions.appendChild(actionButton("Open charter",
        function () { openFile(ctx.repoName, ctx.repoKey, g.charter_path); }));
    }
    actions.appendChild(actionButton("Open report",
      function () { openFile(ctx.repoName, ctx.repoKey, ctx.artifact); }));
    main.appendChild(actions);
    li.appendChild(main);
    return li;
  }

  function renderResult(body, d, ctx) {
    body.textContent = "";
    ctx.artifact = d.artifact_path;
    var stateWord = STATE_WORDS[d.state] || d.state;

    var band = el("section", "charters-band");
    band.dataset.state = d.state;
    band.setAttribute("aria-label", "Charter sync result");
    var top = el("div", "charters-band-top");
    top.appendChild(el("span", "charters-label", "Charter sync"));
    var state = el("span", "charters-state");
    state.appendChild(dot(d.state === "current" ? "current" : "review"));
    state.appendChild(el("span", "charters-state-word", stateWord));
    top.appendChild(state);
    var checked = el("span", "charters-checked", "Checked " + relativeTime(d.checked_at));
    checked.title = d.checked_at + (d.revision ? " · " + d.revision : "")
      + (d.dirty ? " · uncommitted changes" : "");
    top.appendChild(checked);
    band.appendChild(top);
    band.appendChild(el("p", "charters-prose charters-headline", d.headline));

    var counts = el("div", "charters-counts");
    [["current", d.counts.current, "current", null],
     ["review", d.counts.needs_review, "needs review", null],
     ["missing", d.counts.missing, "missing charter", "source files"]].forEach(function (c) {
      var box = el("div", "charters-count");
      box.dataset.count = c[0];
      var n = el("span", "charters-count-n");
      n.appendChild(dot(c[0]));
      n.appendChild(document.createTextNode(String(c[1])));
      box.appendChild(n);
      box.appendChild(el("span", "charters-count-label", c[2]));
      if (c[3]) box.appendChild(el("span", "charters-count-unit", c[3]));
      counts.appendChild(box);
    });
    band.appendChild(counts);
    body.appendChild(band);

    var commits = el("section", "charters-section charters-commits");
    commits.appendChild(el("h2", "charters-section-title", "Recent commit coverage"));
    var rc = d.recent_commits;
    commits.appendChild(el("p", "charters-prose", rc.reason
      ? rc.reason
      : plural(rc.examined, "commit") + " examined · " + rc.without_charter_update
        + " changed governed code without a charter update"));
    body.appendChild(commits);

    if (d.findings.length) {
      var attention = el("section", "charters-section charters-attention");
      attention.appendChild(el("h2", "charters-section-title", "Needs attention"));
      var list = el("ul", "charters-findings");
      d.findings.slice(0, VISIBLE_GROUPS).forEach(function (g) {
        list.appendChild(findingItem(g, ctx));
      });
      attention.appendChild(list);
      if (d.findings.length > VISIBLE_GROUPS) {
        var more = el("details", "charters-more");
        more.appendChild(el("summary", "charters-more-summary",
          "Show all (" + d.findings.length + ")"));
        var rest = el("ul", "charters-findings");
        d.findings.slice(VISIBLE_GROUPS).forEach(function (g) {
          rest.appendChild(findingItem(g, ctx));
        });
        more.appendChild(rest);
        attention.appendChild(more);
      }
      if (d.groups_total > d.findings.length) {
        attention.appendChild(el("p", "charters-note",
          "Showing the first " + d.findings.length + " groups. The report lists all "
          + plural(d.findings_total, "finding") + "."));
      }
      body.appendChild(attention);
    }

    var report = el("p", "charters-report");
    report.appendChild(el("span", "charters-report-label", "Report: "));
    report.appendChild(el("code", "charters-report-path", d.artifact_path));
    report.appendChild(actionButton("Open report",
      function () { openFile(ctx.repoName, ctx.repoKey, d.artifact_path); }));
    body.appendChild(report);
  }

  function renderUnavailable(body, run, message) {
    body.textContent = "";
    run.hidden = true;
    body.appendChild(el("p", "charters-prose",
      message || "The charter sync check is not available for this repository."));
  }

  function isResult(d) {
    return !!d && (d.state === "current" || d.state === "needs-review");
  }

  // ── Charter report (charters-health-section) ─────────────────────────

  function mark(symbol, word, cls) {
    var s = el("span", cls);
    var sym = el("span", "charters-mark-symbol", symbol);
    sym.setAttribute("aria-hidden", "true");
    s.appendChild(sym);
    s.appendChild(document.createTextNode(" "));
    s.appendChild(el("span", "charters-mark-word", word));
    return s;
  }

  function tile(key, label, value, status, sub) {
    var t = el("div", "charters-tile");
    t.dataset.tile = key;
    t.appendChild(el("span", "charters-tile-label", label));
    t.appendChild(el("span", "charters-tile-value", value));
    if (status) t.appendChild(status);
    if (sub) t.appendChild(el("span", "charters-tile-sub", sub));
    return t;
  }

  function renderHealth(area, r, freshness) {
    area.textContent = "";
    var f = FRESHNESS[freshness] || FRESHNESS.unknown;
    var ch = r.charters, cov = r.coverage, code = r.code;

    var tiles = el("div", "charters-tiles");
    tiles.appendChild(tile("charters", "Charters", num(ch.count), null,
      num(ch.lines) + " lines · " + num(ch.documented_functions) + " documented functions"));
    var band = BANDS[code.band];
    tiles.appendChild(tile("size", "Charter size vs code",
      code.charter_to_code_pct === null ? "—" : code.charter_to_code_pct + "%",
      band ? mark(band[0], band[1], "charters-tile-status") :
        mark("–", "No source lines", "charters-tile-status"),
      "target " + code.target.min + "–" + code.target.max + "%"));
    tiles.appendChild(tile("uncovered", "Files without a charter", num(cov.uncovered_files),
      null, "of " + num(cov.source_files) + " source files"));
    area.appendChild(tiles);

    if (ch.count === 0) {
      area.appendChild(el("p", "charters-prose", "This repository has no charters yet."));
    }
    if (r.problems.length) {
      var partial = el("ul", "charters-problems");
      r.problems.forEach(function (p) { partial.appendChild(el("li", null, p.message)); });
      area.appendChild(el("p", "charters-note", "Partial report. Some figures are incomplete:"));
      area.appendChild(partial);
    }

    var prov = el("p", "charters-provenance");
    prov.appendChild(mark(f[0], f[1], "charters-freshness"));
    prov.appendChild(el("span", null, " From the charter report, " + relativeTime(r.generated_at)
      + " · " + (r.inputs.revision ? "revision " + r.inputs.revision : "no commits yet")));
    prov.title = r.generated_at;
    area.appendChild(prov);

    var how = el("details", "charters-measured");
    how.appendChild(el("summary", "charters-measured-summary", "How measured"));
    var list = el("ul", "charters-measured-list");
    Object.keys(r.measurement).forEach(function (k) {
      list.appendChild(el("li", null, r.measurement[k]));
    });
    how.appendChild(list);
    area.appendChild(how);
  }

  function barRow(name, lines, files, max) {
    var li = el("li", "charters-module");
    var head = el("div", "charters-module-head");
    head.appendChild(el("span", "charters-module-name", name));
    head.appendChild(el("span", "charters-module-size",
      num(lines) + " lines · " + plural(files, "file")));
    li.appendChild(head);
    var bar = el("span", "charters-bar");
    bar.setAttribute("aria-hidden", "true");
    bar.style.width = (max > 0 ? Math.max(1, Math.round(lines * 100 / max)) : 0) + "%";
    li.appendChild(bar);
    return li;
  }

  function renderCode(panel, r, ctx) {
    panel.textContent = "";
    var code = r.code, cov = r.coverage;
    panel.appendChild(el("p", "charters-prose charters-code-total", "Product code: "
      + num(code.product_lines) + " lines in " + plural(code.product_files, "source file") + "."));

    var mods = el("section", "charters-section charters-modules");
    mods.appendChild(el("h2", "charters-section-title", "Lines by charter"));
    var max = code.uncovered_module.lines;
    code.modules.forEach(function (m) { if (m.lines > max) max = m.lines; });
    var ul = el("ul", "charters-module-list");
    code.modules.forEach(function (m) { ul.appendChild(barRow(m.charter, m.lines, m.files, max)); });
    ul.appendChild(barRow("No charter", code.uncovered_module.lines,
      code.uncovered_module.files, max));
    mods.appendChild(ul);
    if (code.modules_truncated) {
      mods.appendChild(el("p", "charters-note", "Showing the first " + code.modules.length + " charters."));
    }
    panel.appendChild(mods);

    var big = el("section", "charters-section charters-largest");
    big.appendChild(el("h2", "charters-section-title", "Largest files"));
    var ol = el("ol", "charters-file-list");
    code.largest_files.forEach(function (f) {
      var li = el("li", "charters-file");
      var main = el("div", "charters-file-main");
      main.appendChild(el("code", "charters-file-path", f.path));
      main.appendChild(el("span", "charters-file-meta", num(f.lines) + " lines · "
        + (f.charters.length ? f.charters.join(", ") : "No charter")));
      li.appendChild(main);
      li.appendChild(actionButton("Open file",
        function () { openFile(ctx.repoName, ctx.repoKey, f.path); }));
      ol.appendChild(li);
    });
    big.appendChild(ol);
    panel.appendChild(big);

    var gaps = el("section", "charters-section charters-uncovered");
    gaps.appendChild(el("h2", "charters-section-title", "Files without a charter"));
    if (!cov.uncovered_files) {
      gaps.appendChild(el("p", "charters-prose", "Every source file is covered by a charter."));
    } else {
      var gl = el("ul", "charters-uncovered-list");
      cov.uncovered.forEach(function (p) { gl.appendChild(el("li", null)).appendChild(el("code", null, p)); });
      gaps.appendChild(gl);
      if (cov.uncovered_files > cov.uncovered.length) {
        gaps.appendChild(el("p", "charters-note",
          "and " + num(cov.uncovered_files - cov.uncovered.length) + " more."));
      }
    }
    panel.appendChild(gaps);
  }

  window.GatorViews.charters = function (data, container, repoName, repoKey) {
    var gen = ++mountGen;
    var ctx = { repoName: repoName, repoKey: repoKey || null, artifact: null };
    container.textContent = "";

    var root = el("div", "charters-view");

    // Tabs (Welcome pattern): roving tabindex, Left/Right/Home/End.
    var bar = el("div", "gator-tabbar charters-tabbar");
    var tablist = el("div", "charters-tablist");
    tablist.setAttribute("role", "tablist");
    tablist.setAttribute("aria-label", "Charters sections");
    bar.appendChild(tablist);
    root.appendChild(bar);
    var tabs = {}, panels = {};
    TABS.forEach(function (t) {
      var b = el("button", "gator-tab charters-view-tab", t.label);
      b.type = "button";
      b.id = "charters-view-tab-" + t.key;
      b.dataset.tab = t.key;
      b.setAttribute("role", "tab");
      b.setAttribute("aria-controls", "charters-panel-" + t.key);
      tablist.appendChild(b);
      tabs[t.key] = b;
      var p = el("section", "charters-panel");
      p.id = "charters-panel-" + t.key;
      p.setAttribute("role", "tabpanel");
      p.setAttribute("tabindex", "0");
      p.setAttribute("aria-labelledby", b.id);
      panels[t.key] = p;
    });
    function applyTab() {
      TABS.forEach(function (t) {
        var on = t.key === selectedTab;
        tabs[t.key].setAttribute("aria-selected", on ? "true" : "false");
        tabs[t.key].setAttribute("tabindex", on ? "0" : "-1");
        panels[t.key].hidden = !on;
      });
    }
    function selectTab(key, focus) {
      selectedTab = key;
      applyTab();
      if (focus) tabs[key].focus();
    }
    tablist.addEventListener("click", function (e) {
      var b = e.target.closest(".charters-view-tab");
      if (b) selectTab(b.dataset.tab, false);
    });
    tablist.addEventListener("keydown", function (e) {
      var i = 0, n = TABS.length;
      TABS.forEach(function (t, k) { if (t.key === selectedTab) i = k; });
      var next = null;
      if (e.key === "ArrowRight") next = TABS[(i + 1) % n].key;
      else if (e.key === "ArrowLeft") next = TABS[(i - 1 + n) % n].key;
      else if (e.key === "Home") next = TABS[0].key;
      else if (e.key === "End") next = TABS[n - 1].key;
      if (next === null) return;
      e.preventDefault();
      selectTab(next, true);
    });

    // Overview: the charter report's health area, then the charter sync check.
    var overview = panels.overview;
    var health = el("section", "charters-health");
    health.setAttribute("aria-label", "Charter health");
    var healthHead = el("div", "charters-head");
    healthHead.appendChild(el("h2", "charters-section-title", "Charter health"));
    var refresh = el("button", "charters-action charters-refresh", "Refresh report");
    refresh.type = "button";
    healthHead.appendChild(refresh);
    health.appendChild(healthHead);
    var healthError = el("p", "charters-prose charters-health-error");
    healthError.setAttribute("role", "alert");
    healthError.hidden = true;
    health.appendChild(healthError);
    var healthArea = el("div", "charters-health-area");
    health.appendChild(healthArea);
    overview.appendChild(health);

    var head = el("div", "charters-head");
    head.appendChild(el("p", "charters-prose charters-lede",
      "Keep the repository’s architecture guidance connected to its code."));
    var run = el("button", "charters-run", "Run charter sync check");
    run.type = "button";
    head.appendChild(run);
    overview.appendChild(head);
    var error = el("p", "charters-prose charters-error");
    error.setAttribute("role", "alert");
    error.hidden = true;
    overview.appendChild(error);
    var body = el("div", "charters-body");
    overview.appendChild(body);

    var codePanel = panels.code;
    panels.features.appendChild(el("p", "charters-prose",
      "A feature map is planned for a later release. It will list each feature "
      + "and where it lives in the code."));

    TABS.forEach(function (t) { root.appendChild(panels[t.key]); });
    applyTab();
    container.appendChild(root);

    function current() { return gen === mountGen && root.isConnected; }

    // One POST at a time for this mount: a report refresh and a sync run
    // take the same per-repository lock, so a second POST would get 409.
    var postChain = Promise.resolve();
    function enqueuePost(url) {
      var p = postChain.then(function () { return postJSON(url); });
      postChain = p.catch(function () {});
      return p;
    }

    // The initial read owns the body only until a run starts. A run takes
    // ownership, so a late initial response (a result, no record, or a
    // failure) can never replace what the run painted.
    var readOwnsBody = true;
    function readMayPaint() { return current() && readOwnsBody; }

    function showError(text) {
      error.textContent = text;
      error.hidden = false;
    }

    if (window.GATOR_SNAPSHOT) {
      run.hidden = true;
      refresh.hidden = true;
      body.appendChild(el("p", "charters-prose",
        "The charter sync check runs in the live Dashboard. It is not part of this snapshot."));
      healthArea.appendChild(el("p", "charters-prose",
        "The charter report runs in the live Dashboard. It is not part of this snapshot."));
      codePanel.appendChild(el("p", "charters-prose",
        "The charter report runs in the live Dashboard. It is not part of this snapshot."));
      health.dataset.report = "snapshot";
      return;
    }

    // ── Charter report: one GET, at most one automatic refresh ─────────
    var shown = null;            // the report currently painted, if any
    var autoRefreshed = false;

    function paintReport(r, freshness) {
      shown = r;
      health.dataset.report = freshness;
      renderHealth(healthArea, r, freshness);
      renderCode(codePanel, r, ctx);
    }
    function paintNoReport(text) {
      healthArea.textContent = "";
      healthArea.appendChild(el("p", "charters-prose", text));
      codePanel.textContent = "";
      codePanel.appendChild(el("p", "charters-prose", text));
    }
    function showHealthError(text) {
      healthError.textContent = text + (shown
        ? " Figures shown are from " + relativeTime(shown.generated_at) + "."
        : " No figures are available yet.");
      healthError.hidden = false;
    }
    function unavailable(message) {
      shown = null;
      health.dataset.report = "unavailable";
      refresh.hidden = true;
      paintNoReport(message || "The charter report is not available for this repository.");
    }

    function refreshReport() {
      if (refresh.disabled) return;
      refresh.disabled = true;
      refresh.setAttribute("aria-busy", "true");
      refresh.textContent = "Refreshing…";
      health.dataset.refreshing = "true";
      enqueuePost(reportRoute(repoName))
        .then(function (res) {
          if (!current()) return;
          var d = res.data || {};
          if (res.ok && d.state === "report" && d.report) {
            healthError.hidden = true;
            paintReport(d.report, d.freshness);
          } else if (res.ok && d.state === "unavailable") {
            healthError.hidden = true;
            unavailable(d.message);
          } else {
            if (!shown) health.dataset.report = "failed";
            showHealthError("Refresh failed: " + (d.error || ("HTTP " + res.status)) + ".");
          }
        })
        .catch(function () {
          if (!current()) return;
          if (!shown) health.dataset.report = "failed";
          showHealthError("Refresh failed: the Dashboard could not be reached.");
        })
        .then(function () {
          if (!current()) return;
          refresh.disabled = false;
          refresh.removeAttribute("aria-busy");
          refresh.textContent = "Refresh report";
          delete health.dataset.refreshing;
        });
    }
    function autoRefresh() {
      if (autoRefreshed) return;
      autoRefreshed = true;
      refreshReport();
    }
    refresh.addEventListener("click", refreshReport);

    health.dataset.report = "pending";
    paintNoReport("Reading the charter report…");
    fetch(reportRoute(repoName), { cache: "no-store" })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, data: j }; }); })
      .then(function (res) {
        if (!current() || shown) return;   // a manual refresh already painted
        var d = res.data || {};
        if (res.ok && d.state === "report" && d.report) {
          paintReport(d.report, d.freshness);
          if (d.freshness !== "current") autoRefresh();
        } else if (res.ok && d.state === "none") {
          health.dataset.report = "none";
          paintNoReport("Building the charter report…");
          autoRefresh();
        } else if (res.ok && d.state === "unavailable") {
          unavailable(d.message);
        } else {
          health.dataset.report = "failed";
          paintNoReport("The charter report could not be read.");
          showHealthError("The charter report could not be read: " + (d.error || "server error") + ".");
        }
      })
      .catch(function () {
        if (!current() || shown) return;
        health.dataset.report = "failed";
        paintNoReport("The charter report could not be read.");
        showHealthError("The charter report could not be read: the Dashboard could not be reached.");
      });

    // ── Charter sync check (unchanged behaviour) ──────────────────────
    root.dataset.loaded = "pending";
    fetch(route(repoName), { cache: "no-store" })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, data: j }; }); })
      .then(function (res) {
        if (!readMayPaint()) return;
        if (res.ok && isResult(res.data)) renderResult(body, res.data, ctx);
        else if (res.ok && res.data && res.data.state === "none") renderIntro(body);
        else {
          renderIntro(body);
          showError("The last charter sync result could not be read.");
        }
      })
      .catch(function () {
        if (!readMayPaint()) return;
        renderIntro(body);
        showError("The last charter sync result could not be read.");
      })
      .then(function () { if (current()) root.dataset.loaded = "true"; });

    run.addEventListener("click", function () {
      if (run.disabled) return;
      readOwnsBody = false;
      run.disabled = true;
      run.setAttribute("aria-busy", "true");
      run.textContent = "Checking…";
      root.dataset.running = "true";
      enqueuePost(route(repoName))
        .then(function (res) {
          if (!current()) return;
          if (res.ok && isResult(res.data)) {
            error.hidden = true;
            renderResult(body, res.data, ctx);
          } else if (res.ok && res.data && res.data.state === "unavailable") {
            error.hidden = true;
            renderUnavailable(body, run, res.data.message);
          } else {
            showError("The charter sync check failed: "
              + ((res.data && res.data.error) || ("HTTP " + res.status)) + ". "
              + "The previous result is unchanged.");
          }
        })
        .catch(function () {
          if (current()) showError("The charter sync check failed: the Dashboard could not be reached. "
            + "The previous result is unchanged.");
        })
        .then(function () {
          if (!current()) return;
          run.disabled = false;
          run.removeAttribute("aria-busy");
          run.textContent = "Run charter sync check";
          delete root.dataset.running;
        });
    });
  };
})();
