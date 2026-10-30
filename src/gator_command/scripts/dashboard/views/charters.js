/**
 * views/charters.js — Charters view: the charter sync check (charters-sidebar-sync).
 *
 * Repository-scoped. Shows the last recorded charter sync result for this
 * checkout (GET /api/repo/<name>/charter-sync) and runs a new check
 * (POST, same route). The server owns the check and the sanitized summary;
 * the page only shows what the server returned, never an optimistic
 * result. A failed run keeps the displayed result and shows an alert.
 * State is always a word; the coloured dots are decorative.
 *
 * Exposes: window.GatorViews.charters(data, container, repoName, repoKey)
 */

(function () {
  "use strict";

  window.GatorViews = window.GatorViews || {};

  var VISIBLE_GROUPS = 8;
  var STATE_WORDS = { "current": "Current", "needs-review": "Needs review" };
  var mountGen = 0;

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

  window.GatorViews.charters = function (data, container, repoName, repoKey) {
    var gen = ++mountGen;
    var ctx = { repoName: repoName, repoKey: repoKey || null, artifact: null };
    container.textContent = "";

    var root = el("div", "charters-view");
    var head = el("div", "charters-head");
    head.appendChild(el("p", "charters-prose charters-lede",
      "Keep the repository’s architecture guidance connected to its code."));
    var run = el("button", "charters-run", "Run charter sync check");
    run.type = "button";
    head.appendChild(run);
    root.appendChild(head);
    var error = el("p", "charters-prose charters-error");
    error.setAttribute("role", "alert");
    error.hidden = true;
    root.appendChild(error);
    var body = el("div", "charters-body");
    root.appendChild(body);
    container.appendChild(root);

    function current() { return gen === mountGen && root.isConnected; }

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
      body.appendChild(el("p", "charters-prose",
        "The charter sync check runs in the live Dashboard. It is not part of this snapshot."));
      return;
    }

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
      fetch(route(repoName), {
        method: "POST",
        cache: "no-store",
        headers: { "X-Gator-Dashboard": "1", "Content-Type": "application/json" },
        body: "{}",
      })
        .then(function (r) {
          return r.json().catch(function () { return {}; })
            .then(function (j) { return { ok: r.ok, status: r.status, data: j }; });
        })
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
