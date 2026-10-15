/**
 * views/docs.js — Docs view: the shipped Gator HTML documents.
 *
 * Repository-independent (2026-10-13): the documents come from the
 * installed Gator package through the same closed-allowlist route as
 * Welcome (GET /api/welcome/docs/<name>), so Docs is always available and
 * shows the same list everywhere. Each document opens in a sandboxed
 * iframe (exactly allow-scripts). In a snapshot the text comes from
 * window.GATOR_WELCOME_DOCS and is assigned through the srcdoc property.
 *
 * Exposes: window.GatorViews.docs(data, container)
 */

(function () {
  "use strict";

  window.GatorViews = window.GatorViews || {};

  var DOC_ROUTE = "/api/welcome/docs/";

  // Sidebar order and reader-friendly labels. Every name must be in
  // WELCOME_DOC_NAMES (dashboard/helpers.py). Reading order for a library:
  // Gator overview first (Welcome's tab order differs on purpose: there
  // "Start a session" comes first for its copy-prompt button).
  var DOCS = [
    { doc: "gator-overview.html",             label: "Gator overview" },
    { doc: "what-gator-can-do.html",          label: "What Gator can do" },
    { doc: "gatorize-a-repo.html",            label: "Gatorize a repo" },
    { doc: "start-a-session.html",            label: "Start a session" },
    { doc: "charter-formation-process.html",  label: "Charter formation process" },
    { doc: "charter-schema-v1.html",          label: "Charter schema" },
    { doc: "code-migrations.html",            label: "Code migrations" },
  ];

  // Module-local: survives reopening Docs while the page stays loaded.
  var selectedDoc = DOCS[0].doc;

  function entry(doc) {
    for (var i = 0; i < DOCS.length; i++) if (DOCS[i].doc === doc) return DOCS[i];
    return DOCS[0];
  }

  function showDoc(content, doc) {
    var item = entry(doc);
    content.textContent = "";
    if (window.GATOR_SNAPSHOT) {
      var text = (window.GATOR_WELCOME_DOCS || {})[item.doc];
      if (typeof text !== "string") {
        var notice = document.createElement("p");
        notice.className = "docs-status";
        notice.textContent = "“" + item.label + "” is not available in this "
          + "snapshot. In a gatorized repository, read .gator/docs/" + item.doc + ".";
        content.appendChild(notice);
        return;
      }
    }
    var wrapper = document.createElement("div");
    wrapper.className = "repo-iframe-wrapper";
    var frame = document.createElement("iframe");
    frame.className = "repo-iframe docs-frame";
    frame.setAttribute("sandbox", "allow-scripts");
    frame.title = item.label;
    if (window.GATOR_SNAPSHOT) frame.srcdoc = (window.GATOR_WELCOME_DOCS || {})[item.doc];
    else frame.src = DOC_ROUTE + item.doc;
    wrapper.appendChild(frame);
    content.appendChild(wrapper);
  }

  function select(sidebar, content, doc) {
    selectedDoc = entry(doc).doc;
    var buttons = sidebar.querySelectorAll(".repo-file-item");
    for (var i = 0; i < buttons.length; i++) {
      var on = buttons[i].dataset.doc === selectedDoc;
      buttons[i].classList.toggle("active", on);
      if (on) buttons[i].setAttribute("aria-current", "page");
      else buttons[i].removeAttribute("aria-current");
    }
    showDoc(content, selectedDoc);
  }

  window.GatorViews.docs = function (data, container) {
    container.textContent = "";
    var browser = document.createElement("div");
    browser.className = "repo-browser docs-browser";
    var sidebar = document.createElement("nav");
    sidebar.className = "repo-sidebar docs-sidebar";
    sidebar.setAttribute("aria-label", "Gator documents");
    var header = document.createElement("div");
    header.className = "repo-sidebar-header";
    header.textContent = "Docs";
    sidebar.appendChild(header);
    for (var i = 0; i < DOCS.length; i++) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "repo-file-item indented";
      b.dataset.doc = DOCS[i].doc;
      b.textContent = DOCS[i].label;
      sidebar.appendChild(b);
    }
    var content = document.createElement("div");
    content.className = "repo-content docs-content";
    browser.appendChild(sidebar);
    browser.appendChild(content);
    container.appendChild(browser);

    sidebar.addEventListener("click", function (e) {
      var btn = e.target.closest(".repo-file-item");
      if (btn && btn.dataset.doc !== selectedDoc) select(sidebar, content, btn.dataset.doc);
    });
    select(sidebar, content, selectedDoc);
  };
})();
