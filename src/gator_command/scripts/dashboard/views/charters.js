/**
 * views/charters.js — Charters view: charter health, code map and the charter
 * sync check (charters-sidebar-sync; charters-health-section Release A).
 *
 * Repository-scoped, in three tabs. Overview shows the charter report's
 * health figures (GET/POST /api/repo/<name>/charters-report) above the charter
 * sync check (GET/POST /api/repo/<name>/charter-sync). Code shows where the
 * code is by charter. Features is a placeholder for a later release.
 *
 * The server owns both checks and their sanitized results; the page only
 * shows what the server returned, never an optimistic result. A failed run
 * or refresh keeps the displayed figures and shows an alert. A page open
 * makes one report GET and at most one automatic report refresh; nothing is
 * timed. The mount sends one POST at a time, because both runs take the
 * same per-repository lock. The report pages use the Cumberland reading
 * style (lede, ruled headings, inline-SVG figures with text captions). State
 * is always a word; colours and shapes are never the only cue.
 *
 * Exposes: window.GatorViews.charters(data, container, repoName, repoKey)
 */

(function () {
  "use strict";

  window.GatorViews = window.GatorViews || {};

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

  // The repair hand-off: the Dashboard never edits charters, so a check that
  // needs review offers one line for the Architect's agent session. It names
  // the saved report (which holds the repair sketch) and the flagged charters,
  // and carries no token or secret. Shown in full and copied on request.
  var PROMPT_CHARTERS = 8;

  function repairPrompt(d) {
    var names = [];
    d.findings.forEach(function (g) {
      if (g.charter_path && names.indexOf(g.label) === -1) names.push(g.label);
    });
    var shown = names.slice(0, PROMPT_CHARTERS);
    var more = names.length - shown.length;
    var which = shown.length
      ? "the flagged charters (" + shown.join(", ") + (more ? " and " + more + " more" : "") + ")"
      : "the flagged charters and files";
    return "Read the charter sync report at " + d.artifact_path + ". For " + which
      + ", compare each charter with its code and follow the report's repair sketch so the "
      + "charter matches the code, and move dated history (release notes, review rounds, "
      + "resolved findings) out of the charter, per the charter README. Change charters "
      + "only, not code. Show me the charter changes before you commit.";
  }

  function repairBlock(d) {
    var text = repairPrompt(d);
    var box = el("div", "charters-prompt");
    box.appendChild(el("p", "charters-prompt-label",
      "To fix these charters, give this prompt to your agent session:"));
    box.appendChild(el("p", "charters-prompt-text", text));
    var row = el("div", "charters-prompt-actions");
    var copy = el("button", "charters-action charters-copy", "Copy prompt");
    copy.type = "button";
    var status = el("span", "charters-copy-status");
    status.setAttribute("aria-live", "polite");
    copy.addEventListener("click", function () {
      if (!(navigator.clipboard && navigator.clipboard.writeText)) {
        status.textContent = "Copy is not available here. Select the prompt above and copy it.";
        return;
      }
      navigator.clipboard.writeText(text).then(function () {
        status.textContent = "✓ Copied";
      }, function () {
        status.textContent = "Copy failed. Select the prompt above and copy it.";
      });
    });
    row.appendChild(copy);
    row.appendChild(status);
    box.appendChild(row);
    return box;
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

    // Charters current vs needing review, as the same donut as Coverage.
    var charters = d.counts.current + d.counts.needs_review;
    band.appendChild(donutChart([
      { value: d.counts.current, stroke: "charters-stroke", swatch: "charters-swatch",
        label: plural(d.counts.current, "charter") + " current" },
      { value: d.counts.needs_review, stroke: "charters-stroke-review",
        swatch: "charters-swatch charters-swatch-review",
        label: plural(d.counts.needs_review, "charter") + " need review" },
    ], charters ? Math.round(d.counts.current * 100 / charters) + "%" : "—", "current",
      d.counts.current + " of " + plural(charters, "charter") + " current", "sync"));
    band.appendChild(el("p", "charters-note charters-missing",
      num(d.counts.missing) + " source " + (d.counts.missing === 1 ? "file has" : "files have")
      + " no charter."));
    if (d.state === "needs-review") band.appendChild(repairBlock(d));
    body.appendChild(band);

    // Recent commits: how many changed governed code without a charter update.
    var commits = section("charters-commits", "Recent commit coverage");
    var rc = d.recent_commits;
    if (rc.reason || !rc.examined) {
      commits.appendChild(el("p", "charters-prose", rc.reason || "No commits were examined."));
    } else {
      var ok = rc.examined - rc.without_charter_update;
      commits.appendChild(figure("commits", donutChart([
        { value: ok, stroke: "charters-stroke", swatch: "charters-swatch",
          label: plural(ok, "commit") + " kept charters in step" },
        { value: rc.without_charter_update, stroke: "charters-stroke-review",
          swatch: "charters-swatch charters-swatch-review",
          label: plural(rc.without_charter_update, "commit") + " changed governed code without a charter update" },
      ], Math.round(ok * 100 / rc.examined) + "%", "in step",
        ok + " of " + plural(rc.examined, "recent commit") + " kept charters in step", "commits"),
        "The last " + plural(rc.examined, "commit") + " (merges excluded). A commit is in step "
        + "unless it changed governed code without a charter update."));
    }
    body.appendChild(commits);

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
  // Cumberland reading style: a lede sentence, ruled section headings, and
  // figures drawn as inline SVG. Every figure states its numbers in text as
  // well (labels, caption, <title> hover), so the drawing is never the only
  // carrier of a value and colour is never the only cue.

  var SVG_NS = "http://www.w3.org/2000/svg";
  var CHART_ROWS = 24;          // more charters than this fold into one row

  function svg(tag, attrs, text) {
    var e = document.createElementNS(SVG_NS, tag);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, String(attrs[k])); });
    if (text !== undefined && text !== null) e.textContent = String(text);
    return e;
  }

  function hover(node, text) {
    node.appendChild(svg("title", null, text));
    return node;
  }

  function mark(symbol, word, cls) {
    var s = el("span", cls);
    var sym = el("span", "charters-mark-symbol", symbol);
    sym.setAttribute("aria-hidden", "true");
    s.appendChild(sym);
    s.appendChild(document.createTextNode(" "));
    s.appendChild(el("span", "charters-mark-word", word));
    return s;
  }

  function figure(key, chart, caption) {
    var f = el("figure", "charters-figure");
    f.dataset.figure = key;
    f.appendChild(chart);
    var c = el("figcaption", "charters-caption");
    if (caption.nodeType) c.appendChild(caption); else c.textContent = caption;
    f.appendChild(c);
    return f;
  }

  function section(cls, title) {
    var s = el("section", "charters-doc-section " + cls);
    s.appendChild(el("h2", "charters-doc-title", title));
    return s;
  }

  // Charter lines as a share of product lines, against the 3–6% target band.
  function sizeChart(code) {
    var W = 640, H = 64, L = 16, R = 20, base = 38;
    var pct = code.charter_to_code_pct;
    var max = Math.max(10, Math.ceil(((pct || 0) + 1) / 2) * 2);
    var x = function (v) { return L + (W - L - R) * Math.min(v, max) / max; };
    var s = svg("svg", { viewBox: "0 0 " + W + " " + H, role: "img",
      "aria-label": "Charter size " + (pct === null ? "unknown" : pct + "% of product code")
        + "; target " + code.target.min + " to " + code.target.max + "%" });
    s.setAttribute("class", "charters-chart");
    s.appendChild(svg("line", { x1: L, y1: base, x2: W - R, y2: base, class: "charters-axis" }));
    s.appendChild(hover(svg("rect", { x: x(code.target.min), y: base - 16,
      width: x(code.target.max) - x(code.target.min), height: 16, rx: 2, class: "charters-band-fill" }),
      "Target: " + code.target.min + "–" + code.target.max + "% of product code"));
    s.appendChild(svg("text", { x: (x(code.target.min) + x(code.target.max)) / 2, y: base - 21,
      "text-anchor": "middle", class: "charters-chart-note" },
      "target " + code.target.min + "–" + code.target.max + "%"));
    for (var t = 0; t <= max; t += 2) {
      s.appendChild(svg("line", { x1: x(t), y1: base, x2: x(t), y2: base + 4, class: "charters-axis" }));
      s.appendChild(svg("text", { x: x(t), y: base + 17, "text-anchor": "middle",
        class: "charters-chart-tick" }, t + "%"));
    }
    if (pct !== null) {
      s.appendChild(hover(svg("rect", { x: x(pct) - 2, y: base - 22, width: 4, height: 26, rx: 2,
        class: "charters-marker" }), "Charter size: " + pct + "% of product code"));
    }
    return s;
  }

  // What a charter covers, in one short line under its bar: the files by name
  // when there are few, otherwise their folders with a count each.
  var MODULE_NAMES = 6;

  function folderOf(path) {
    var parts = path.split("/");
    parts.pop();
    return parts.length ? parts.slice(-2).join("/") + "/" : "./";
  }

  function moduleSummary(paths, files, truncated) {
    if (!paths.length) return "";
    var text;
    if (files <= MODULE_NAMES && !truncated) {
      text = paths.map(shortName).join(", ");
    } else {
      var counts = {}, order = [];
      paths.forEach(function (p) {
        var d = folderOf(p);
        if (!counts[d]) { counts[d] = 0; order.push(d); }
        counts[d] += 1;
      });
      order.sort(function (a, b) { return counts[b] - counts[a] || (a < b ? -1 : 1); });
      var shown = order.slice(0, 4).map(function (d) { return d + " (" + counts[d] + ")"; });
      if (order.length > 4) shown.push("+" + (order.length - 4) + " more");
      text = shown.join(", ") + (truncated ? " (first " + paths.length + " files)" : "");
    }
    return text.length > 72 ? text.slice(0, 71) + "…" : text;
  }

  // Lines of code covered by each charter: one series, a direct label on every
  // row, what the charter covers in a line under its bar, "No charter" last.
  function modulesChart(code, cov) {
    var rows = code.modules.map(function (m) {
      return { name: m.charter, lines: m.lines, files: m.files, none: false,
        paths: m.paths || [], truncated: !!m.paths_truncated };
    });
    if (rows.length > CHART_ROWS) {
      var rest = rows.slice(CHART_ROWS - 1);
      rows = rows.slice(0, CHART_ROWS - 1);
      rows.push({ name: "Other charters (" + rest.length + ")", none: false, paths: [], truncated: false,
        lines: rest.reduce(function (a, r) { return a + r.lines; }, 0),
        files: rest.reduce(function (a, r) { return a + r.files; }, 0) });
    }
    rows.push({ name: "No charter", lines: code.uncovered_module.lines,
      files: code.uncovered_module.files, none: true,
      paths: cov.uncovered, truncated: cov.uncovered_truncated });
    var max = 1;
    rows.forEach(function (r) { if (r.lines > max) max = r.lines; });
    var W = 640, LABEL = 200, VALUE = 92, ROW = 42, BAR = 12, TOP = 4;
    var plot = W - LABEL - VALUE;
    var s = svg("svg", { viewBox: "0 0 " + W + " " + (rows.length * ROW + TOP), role: "img",
      "aria-label": "Lines of code covered by each charter" });
    s.setAttribute("class", "charters-chart charters-chart-bars");
    rows.forEach(function (r, i) {
      var y = i * ROW + TOP;
      var g = svg("g", { class: "charters-row" + (r.none ? " charters-row-none" : "") });
      var label = r.name.length > 30 ? r.name.slice(0, 29) + "…" : r.name;
      g.appendChild(svg("text", { x: LABEL - 8, y: y + BAR - 1, "text-anchor": "end",
        class: "charters-chart-label" }, label));
      var w = Math.max(r.lines ? 4 : 0, Math.round(plot * r.lines / max));
      if (w) {
        g.appendChild(svg("rect", { x: LABEL, y: y, width: w, height: BAR, rx: 2,
          class: r.none ? "charters-fill-none" : "charters-fill" }));
      }
      g.appendChild(svg("text", { x: LABEL + w + 6, y: y + BAR - 1, class: "charters-chart-value" },
        num(r.lines)));
      var summary = moduleSummary(r.paths, r.files, r.truncated);
      if (summary) {
        g.appendChild(svg("text", { x: LABEL, y: y + BAR + 14, class: "charters-chart-sub" }, summary));
      }
      // A full-row hit target, larger than the bar; the hover lists the files.
      g.appendChild(hover(svg("rect", { x: 0, y: y - 6, width: W, height: ROW, class: "charters-hit" }),
        r.name + ": " + num(r.lines) + " lines in " + plural(r.files, "file")
        + (r.paths.length ? "\n" + r.paths.join("\n") + (r.truncated ? "\n…" : "") : "")));
      s.appendChild(g);
    });
    return s;
  }


  function renderHealth(area, r, freshness, ctx) {
    area.textContent = "";
    var f = FRESHNESS[freshness] || FRESHNESS.unknown;
    var ch = r.charters, cov = r.coverage, code = r.code;

    var lede = ch.count === 0
      ? "This repository has no charters yet. None of its " + plural(cov.source_files, "source file")
        + " is described by a charter."
      : plural(ch.count, "charter") + " describe " + num(cov.covered_files) + " of "
        + num(cov.source_files) + " source files"
        + (cov.uncovered_files ? "; " + num(cov.uncovered_files)
          + (cov.uncovered_files === 1 ? " has" : " have") + " no charter yet." : ".");
    area.appendChild(el("p", "charters-doc-lede", lede));

    var prov = el("p", "charters-provenance");
    prov.appendChild(mark(f[0], f[1], "charters-freshness"));
    prov.appendChild(el("span", null, " From the charter report, " + relativeTime(r.generated_at)
      + " · " + (r.inputs.revision ? "revision " + r.inputs.revision : "no commits yet")));
    prov.title = r.generated_at;
    area.appendChild(prov);

    if (r.problems.length) {
      area.appendChild(el("p", "charters-note", "Partial report. Some figures are incomplete:"));
      var partial = el("ul", "charters-problems");
      r.problems.forEach(function (p) { partial.appendChild(el("li", null, p.message)); });
      area.appendChild(partial);
    }

    var sizes = section("charters-sizes", "Charters by size");
    if (ch.items.length) {
      sizes.appendChild(figure("charters", charterSizesChart(ch.items, ctx),
        guideLegend(CHARTER_GUIDE, "charter")));
      if (ch.items_truncated) {
        sizes.appendChild(el("p", "charters-note", "Showing the first " + ch.items.length + " charters."));
      }
    } else {
      sizes.appendChild(el("p", "charters-prose", "There are no charters to show yet."));
    }
    area.appendChild(sizes);

    var size = section("charters-size", "Total charters size as percentage of codebase size");
    var band = BANDS[code.band];
    var cap = el("span");
    if (code.charter_to_code_pct === null) {
      cap.textContent = "There are no source lines to compare with.";
    } else {
      cap.appendChild(document.createTextNode(num(ch.lines) + " charter lines are "
        + code.charter_to_code_pct + "% of " + num(code.product_lines) + " lines of product code. "));
      if (band) cap.appendChild(mark(band[0], band[1], "charters-figure-status"));
      cap.appendChild(document.createTextNode(" Target " + code.target.min + "–"
        + code.target.max + "%. The charters document " + plural(ch.documented_functions, "function") + "."));
    }
    size.appendChild(figure("size", sizeChart(code), cap));
    area.appendChild(size);

    var covSec = section("charters-coverage", "Coverage");
    covSec.appendChild(figure("coverage", coverageChart(cov),
      num(cov.covered_files) + " covered · " + num(cov.uncovered_files) + " without a charter"
      + (cov.percent === null ? "" : " · " + cov.percent + "% covered") + "."));
    area.appendChild(covSec);

    var how = el("details", "charters-measured");
    how.appendChild(el("summary", "charters-measured-summary", "How measured"));
    var list = el("ul", "charters-measured-list");
    Object.keys(r.measurement).forEach(function (k) {
      list.appendChild(el("li", null, r.measurement[k]));
    });
    how.appendChild(list);
    area.appendChild(how);
  }

  // Ranked bars with a guide (largest files; charters by size): bars on a light
  // track, a dashed guide crossing every row, and size bands shown by fill AND
  // a symbol after the value. Each row is a link (click, Enter or Space) that
  // opens its file in Repo. The guides are reading aids fixed in the view, not
  // rules: thresholds and their tracked setting are a later release.
  var FILE_GUIDE = { guide: 1500, large: 4000 };
  var CHARTER_GUIDE = { guide: 300, large: 600 };

  // A readable label: the file with its folder (skipping generic folders), and
  // a tag for shipped copies, so the starter and Enterprise copies of one
  // script are told apart. The full path is in the hover text and aria-label.
  var GENERIC_DIRS = ["scripts", "dashboard", "bundled_scripts", "src"];

  function shortName(path) {
    var parts = path.split("/");
    var base = parts[parts.length - 1];
    var parent = parts.length > 1 ? parts[parts.length - 2] : "";
    var label = (parent && GENERIC_DIRS.indexOf(parent) === -1 ? parent + "/" : "") + base;
    if (path.indexOf("templates/gator-starter/") !== -1) label += " · starter";
    else if (path.indexOf("enterprise/") === 0) label += " · enterprise";
    return clip(label);
  }

  function clip(label) {
    return label.length > 34 ? "…" + label.slice(label.length - 33) : label;
  }

  function sizeBand(lines, guide) {
    if (lines > guide.large) return { cls: "charters-fill-large", symbol: "■", word: "over " + num(guide.large) + " lines" };
    if (lines > guide.guide) return { cls: "charters-fill-over", symbol: "▲", word: "over " + num(guide.guide) + " lines" };
    return { cls: "charters-fill", symbol: "", word: "" };
  }

  // rows: [{label, lines, path, detail}] in display order.
  function rankedChart(rows, guide, ariaLabel, rowClass, ctx) {
    var max = guide.guide * 1.2;
    rows.forEach(function (r) { if (r.lines > max) max = r.lines; });
    var W = 640, LABEL = 250, TAIL = 96, ROW = 30, BAR = 14, TOP = 6;
    var plot = W - LABEL - TAIL;
    var x = function (v) { return LABEL + plot * v / max; };
    var H = rows.length * ROW + TOP + 4;
    var s = svg("svg", { viewBox: "0 0 " + W + " " + H, role: "group", "aria-label": ariaLabel });
    s.setAttribute("class", "charters-chart charters-chart-ranked");
    rows.forEach(function (r, i) {
      var y = TOP + i * ROW;
      var band = sizeBand(r.lines, guide);
      var g = svg("g", { class: "charters-link-row " + rowClass, role: "link", tabindex: 0,
        "aria-label": "Open " + r.path + ", " + num(r.lines) + " lines" + (band.word ? ", " + band.word : "") });
      g.appendChild(svg("rect", { x: 0, y: y - 7, width: W, height: ROW, rx: 4, class: "charters-hit" }));
      g.appendChild(svg("text", { x: LABEL - 10, y: y + BAR - 2, "text-anchor": "end",
        class: "charters-chart-label charters-chart-path" }, r.label));
      g.appendChild(svg("rect", { x: LABEL, y: y, width: plot, height: BAR, rx: 2, class: "charters-track" }));
      g.appendChild(svg("rect", { x: LABEL, y: y, width: Math.max(4, x(r.lines) - LABEL), height: BAR,
        rx: 2, class: band.cls }));
      g.appendChild(svg("text", { x: LABEL + plot + 10, y: y + BAR - 2, class: "charters-chart-value" },
        num(r.lines)));
      if (band.symbol) {
        g.appendChild(svg("text", { x: W - 8, y: y + BAR - 2, "text-anchor": "end",
          class: "charters-chart-symbol", "aria-hidden": "true" }, band.symbol));
      }
      hover(g, r.detail + (band.word ? " · " + band.word : ""));
      var open = function () { openFile(ctx.repoName, ctx.repoKey, r.path); };
      g.addEventListener("click", open);
      g.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
      });
      s.appendChild(g);
    });
    // The guide is drawn last so it crosses every bar.
    s.appendChild(svg("line", { x1: x(guide.guide), y1: TOP - 4, x2: x(guide.guide), y2: H - 2,
      class: "charters-guide", "aria-hidden": "true" }));
    return s;
  }

  function guideLegend(guide, noun) {
    var p = el("span");
    [["■", "over " + num(guide.large) + " lines"], ["▲", "over " + num(guide.guide)],
     ["┆", num(guide.guide) + "-line guide"]].forEach(function (m) {
      p.appendChild(mark(m[0], m[1], "charters-legend-item"));
    });
    p.appendChild(document.createTextNode(" Select a row to open the " + noun + "."));
    return p;
  }

  function largestChart(files, ctx) {
    return rankedChart(files.map(function (f) {
      return { label: shortName(f.path), lines: f.lines, path: f.path,
        detail: f.path + ": " + num(f.lines) + " lines"
          + (f.charters.length ? " · " + f.charters.join(", ") : " · no charter") };
    }), FILE_GUIDE, "Largest files by lines; select a row to open the file", "charters-file-row", ctx);
  }

  function charterSizesChart(items, ctx) {
    var rows = items.slice().sort(function (a, b) {
      return b.lines - a.lines || (a.name < b.name ? -1 : 1);
    });
    return rankedChart(rows.map(function (c) {
      return { label: clip(c.name), lines: c.lines, path: c.path,
        detail: c.name + ": " + num(c.lines) + " lines · "
          + plural(c.documented_functions, "documented function") + " · covers "
          + plural(c.covered_files, "file") };
    }), CHARTER_GUIDE, "Charters by size; select a row to open the charter", "charters-charter-row", ctx);
  }

  // A donut (coverage, charter sync, recent commits): parts drawn in order from
  // twelve o'clock with 2px gaps, any non-zero part at least a visible sliver,
  // the headline value in the middle, and a legend list with every count in
  // words (swatches aria-hidden). parts: [{value, stroke, swatch, label}].
  function donutChart(parts, center, unit, ariaLabel, key) {
    var wrap = el("div", "charters-donut");
    wrap.dataset.donut = key;
    var R = 58, SW = 24, C = 2 * Math.PI * R, GAP = 2, MIN = Math.max(8, C * 0.012);
    var total = parts.reduce(function (a, p) { return a + p.value; }, 0);
    var s = svg("svg", { viewBox: "0 0 160 160", role: "img", "aria-label": ariaLabel });
    s.setAttribute("class", "charters-chart charters-donut-chart");
    var ring = svg("g", { transform: "rotate(-90 80 80)" });
    var live = parts.filter(function (p) { return p.value > 0; });
    if (!live.length) {
      ring.appendChild(svg("circle", { cx: 80, cy: 80, r: R, fill: "none", "stroke-width": SW,
        class: "charters-donut-empty" }));
    } else {
      var lens = live.map(function (p) { return C * p.value / total; });
      // Lift small parts to the sliver minimum, taking the difference from the largest.
      var big = lens.indexOf(Math.max.apply(null, lens));
      lens.forEach(function (l, i) {
        if (live.length > 1 && l < MIN) { lens[big] -= MIN - l; lens[i] = MIN; }
      });
      var at = 0;
      live.forEach(function (p, i) {
        var gap = live.length > 1 ? GAP : 0;
        var len = lens[i] - gap;
        ring.appendChild(hover(svg("circle", { cx: 80, cy: 80, r: R, fill: "none", "stroke-width": SW,
          class: p.stroke, "stroke-dasharray": len + " " + (C - len),
          "stroke-dashoffset": -(at + gap / 2) }), p.label));
        at += lens[i];
      });
    }
    s.appendChild(ring);
    s.appendChild(svg("text", { x: 80, y: 80, "text-anchor": "middle", class: "charters-donut-value" }, center));
    s.appendChild(svg("text", { x: 80, y: 100, "text-anchor": "middle", class: "charters-donut-unit" }, unit));
    wrap.appendChild(s);

    var legend = el("ul", "charters-donut-legend");
    parts.forEach(function (p) {
      var li = el("li", "charters-donut-item");
      var sw = el("span", p.swatch);
      sw.setAttribute("aria-hidden", "true");
      li.appendChild(sw);
      li.appendChild(el("span", null, p.label));
      legend.appendChild(li);
    });
    wrap.appendChild(legend);
    return wrap;
  }

  // Coverage: covered and uncovered source files.
  function coverageChart(cov) {
    return donutChart([
      { value: cov.covered_files, stroke: "charters-stroke", swatch: "charters-swatch",
        label: num(cov.covered_files) + " covered by a charter" },
      { value: cov.uncovered_files, stroke: "charters-stroke-none",
        swatch: "charters-swatch charters-swatch-none",
        label: num(cov.uncovered_files) + " without a charter" },
    ], cov.percent === null ? "—" : cov.percent + "%", "covered",
      num(cov.covered_files) + " of " + num(cov.source_files) + " source files covered by a charter",
      "coverage");
  }

  function renderCode(panel, r, ctx) {
    panel.textContent = "";
    var code = r.code, cov = r.coverage;
    panel.appendChild(el("p", "charters-doc-lede", num(code.product_lines)
      + " lines of product code in " + plural(code.product_files, "source file") + "."));

    var big = section("charters-largest", "Largest files");
    if (code.largest_files.length) {
      big.appendChild(figure("largest", largestChart(code.largest_files, ctx), guideLegend(FILE_GUIDE, "file")));
    } else {
      big.appendChild(el("p", "charters-prose", "There are no source files to show."));
    }
    panel.appendChild(big);

    var mods = section("charters-modules", "Lines of code covered by each charter");
    mods.appendChild(figure("modules", modulesChart(code, cov),
      "Each row is one charter and the lines of the files it covers; the line under each bar "
      + "names those files, or their folders with a count. A file covered by two charters "
      + "counts in both rows."));
    if (code.modules_truncated) {
      mods.appendChild(el("p", "charters-note", "Showing the first " + code.modules.length + " charters."));
    }
    panel.appendChild(mods);
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
    // The report feeds both Overview and Code, so its refresh sits with the tabs.
    var refresh = el("button", "charters-action charters-refresh", "Refresh report");
    refresh.type = "button";
    bar.appendChild(refresh);
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
    health.appendChild(el("h2", "charters-doc-title", "Charter health"));
    var healthError = el("p", "charters-prose charters-health-error");
    healthError.setAttribute("role", "alert");
    healthError.hidden = true;
    health.appendChild(healthError);
    var healthArea = el("div", "charters-health-area");
    health.appendChild(healthArea);
    overview.appendChild(health);

    overview.appendChild(el("h2", "charters-doc-title charters-sync-title", "Charter sync"));
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
      renderHealth(healthArea, r, freshness, ctx);
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
