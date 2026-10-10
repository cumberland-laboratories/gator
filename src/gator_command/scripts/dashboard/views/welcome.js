/**
 * views/welcome.js — Welcome workspace (#72), opened from the sidebar logo.
 *
 * Four fixed topics in the shared main-pane tab bar (.gator-tabbar), plus
 * one transient copy of the vendor-neutral session-opening prompt.
 *
 * Contract:
 *   - No fetch, no storage, no console output, no history calls. The shell
 *     owns routing; this view never touches repository context.
 *   - All markup comes from constants in this file. The prompt reaches the
 *     DOM only through textContent / textarea.value.
 *   - The selected topic is module-local: it survives reopening Welcome
 *     while the page stays loaded and resets on a fresh page load.
 */

(function () {
  "use strict";

  window.GatorViews = window.GatorViews || {};

  var TOPICS = [
    { key: "what",     label: "What is Gator?" },
    { key: "can",      label: "What Gator can do" },
    { key: "gatorize", label: "Gatorize a repo" },
    { key: "session",  label: "Start a session with Gator" },
  ];

  // Exact text from the #72 sketch. No layout-dependent path, no vendor.
  // One line by Architect direction (2026-10-10): a pasted newline can
  // submit early in terminal agent UIs.
  var SESSION_PROMPT =
    "Run gator init in this repository. Treat its output, including the required "
    + "session-opening reads, as binding. Do not provide a substantive response until "
    + "those reads are complete.";

  var DOCS_BASE = "https://github.com/cumberland-laboratories/gator/blob/main/";
  var DOCS = {
    readme: { href: DOCS_BASE + "README.md", label: "Gator README" },
    howto: { href: DOCS_BASE + "docs/how-to-use-gator.md", label: "How to use Gator" },
    arch: { href: DOCS_BASE + "docs/architecture.md", label: "Gator architecture" },
  };

  var COPY_LABEL = "Copy session-opening prompt";

  var selectedTopic = "what";
  var root = null;

  function docLink(key) {
    var d = DOCS[key];
    return '<a class="welcome-doc-link" href="' + d.href
      + '" target="_blank" rel="noopener noreferrer">' + d.label + '</a>';
  }

  function nextButton(topic, text) {
    return '<button type="button" class="welcome-next" data-goto="' + topic + '">'
      + text + ' →</button>';
  }

  var PANELS = {
    what:
      '<h3 class="welcome-heading">What is Gator?</h3>'
      + '<p>Gator is the Git-native governance layer for AI-assisted engineering. '
      + 'It is not an AI coding framework, and it is not a hosted audit tool. '
      + 'It works with the coding agent you already use.</p>'
      + '<p>Gator is charter-first. As agents work, they keep a compact map of each '
      + 'module, called a charter. Each governed commit records that understanding '
      + 'as evidence in Git, next to the code it describes.</p>'
      + '<div class="welcome-next-row">'
      +   nextButton("can", "What Gator can do")
      +   nextButton("gatorize", "Gatorize a repo")
      + '</div>'
      + '<p class="welcome-more">Read more: ' + docLink("readme") + '</p>',
    can:
      '<h3 class="welcome-heading">What Gator can do</h3>'
      + '<ul class="welcome-list">'
      + '<li><strong>Governed session opening.</strong> Every session starts from the '
      +   'same rules, priorities, and open work, whichever coding agent you use.</li>'
      + '<li><strong>Charters and commit evidence.</strong> Agents read and update the '
      +   'charters as they change code, and each commit carries a record of that work.</li>'
      + '<li><strong>Local Dashboard inspection.</strong> This Dashboard shows your '
      +   'repositories, commits, and documents from local Git state.</li>'
      + '<li><strong>Governed Loop collaboration.</strong> Two models draft and review '
      +   'a plan or a change in turns, and you keep the final decision.</li>'
      + '</ul>'
      + '<p class="welcome-more">Read more: ' + docLink("howto") + ' · '
      +   docLink("arch") + '</p>',
    gatorize:
      '<h3 class="welcome-heading">Gatorize a repo</h3>'
      + '<p>Gatorizing adds the <code>.gator/</code> layer, its templates, the Git '
      + 'hooks, and the Dashboard registration to a repository.</p>'
      + '<p>It does not change your code. Your <code>CLAUDE.md</code>, '
      + '<code>AGENTS.md</code>, and <code>GEMINI.md</code> files stay as they are: '
      + 'they belong to the repository.</p>'
      + '<p>Run this command:</p>'
      + '<pre class="welcome-code"><code>gator gatorize &lt;target-directory&gt;</code></pre>'
      + '<p>Then open the repository in your coding agent and start a session.</p>'
      + '<div class="welcome-next-row">'
      +   nextButton("session", "Start a session with Gator")
      + '</div>'
      + '<p class="welcome-more">Read more: ' + docLink("howto") + '</p>',
    session:
      '<h3 class="welcome-heading">Start a session with Gator</h3>'
      + '<ol class="welcome-steps">'
      + '<li>Paste the prompt into the coding-agent session for the repository.</li>'
      + '<li>The agent runs <code>gator init</code>.</li>'
      + '<li>The agent reads the Gator entry document and the required context '
      +   'before it does substantive work.</li>'
      + '<li>You give the task. You and the agent now share the same governance '
      +   'context.</li>'
      + '</ol>'
      + '<pre class="welcome-prompt"></pre>'
      + '<div class="welcome-copy-row">'
      +   '<button type="button" class="welcome-copy">' + COPY_LABEL + '</button>'
      +   '<div class="welcome-copy-status" role="status" aria-live="polite"></div>'
      + '</div>',
  };

  function keyIndex(key) {
    for (var i = 0; i < TOPICS.length; i++) if (TOPICS[i].key === key) return i;
    return -1;
  }

  // Attributes are written only when they differ.
  function applyTopic() {
    if (!root) return;
    TOPICS.forEach(function (t) {
      var selected = t.key === selectedTopic;
      var tab = root.querySelector("#welcome-tab-" + t.key);
      var panel = root.querySelector("#welcome-panel-" + t.key);
      var sel = selected ? "true" : "false";
      var ti = selected ? "0" : "-1";
      if (tab.getAttribute("aria-selected") !== sel) tab.setAttribute("aria-selected", sel);
      if (tab.getAttribute("tabindex") !== ti) tab.setAttribute("tabindex", ti);
      if (panel.hidden === selected) panel.hidden = !selected;
    });
  }

  function selectTopic(key, focusTab) {
    if (keyIndex(key) === -1) return;
    selectedTopic = key;
    applyTopic();
    if (focusTab && root) {
      var tab = root.querySelector("#welcome-tab-" + key);
      if (tab) tab.focus();
    }
  }

  function setStatus(btn, text) {
    var row = btn.parentNode;
    var status = row && row.querySelector(".welcome-copy-status");
    if (status && status.textContent !== text) status.textContent = text;
  }

  // Mirrors the Loop handoff fallback (views/loop.js showPromptFallback):
  // a selected read-only textarea, a manual-copy hint, and Dismiss.
  function showCopyFallback(btn) {
    var row = btn.parentNode;
    var existing = row.querySelector(".welcome-copy-fallback");
    if (existing) existing.remove();
    var fb = document.createElement("div");
    fb.className = "welcome-copy-fallback";
    var ta = document.createElement("textarea");
    ta.className = "welcome-copy-fallback-text";
    ta.readOnly = true;
    ta.rows = 4;
    ta.value = SESSION_PROMPT;
    var hint = document.createElement("div");
    hint.className = "welcome-copy-fallback-hint";
    hint.textContent = "Select all and copy manually.";
    var dismiss = document.createElement("button");
    dismiss.type = "button";
    dismiss.className = "welcome-copy-fallback-dismiss";
    dismiss.textContent = "Dismiss";
    dismiss.addEventListener("click", function () { fb.remove(); });
    fb.appendChild(ta);
    fb.appendChild(hint);
    fb.appendChild(dismiss);
    row.appendChild(fb);
    ta.focus();
    ta.select();
    setStatus(btn, "Clipboard unavailable — copy the prompt manually.");
  }

  async function copySessionPrompt(btn) {
    if (!(navigator.clipboard && navigator.clipboard.writeText)) {
      showCopyFallback(btn);
      return;
    }
    try {
      await navigator.clipboard.writeText(SESSION_PROMPT);
    } catch (e) {
      if (btn.isConnected) showCopyFallback(btn);
      return;
    }
    if (!btn.isConnected) return;
    var done = "Session-opening prompt copied.";
    btn.textContent = "Copied";
    setStatus(btn, done);
    setTimeout(function () {
      if (!btn.isConnected) return;
      btn.textContent = COPY_LABEL;
      var status = btn.parentNode.querySelector(".welcome-copy-status");
      if (status && status.textContent === done) status.textContent = "";
    }, 2000);
  }

  window.GatorViews.welcome = function (data, container) {
    var tabs = "";
    var panels = "";
    TOPICS.forEach(function (t) {
      tabs += '<button type="button" class="gator-tab welcome-tab" role="tab" '
        + 'id="welcome-tab-' + t.key + '" aria-controls="welcome-panel-' + t.key + '" '
        + 'data-topic="' + t.key + '">' + t.label + '</button>';
      panels += '<section class="welcome-panel" role="tabpanel" tabindex="0" '
        + 'id="welcome-panel-' + t.key + '" aria-labelledby="welcome-tab-' + t.key + '" hidden>'
        + PANELS[t.key] + '</section>';
    });
    container.innerHTML =
      '<div class="welcome-workspace">'
      + '<div class="gator-tabbar welcome-tabbar">'
      +   '<div class="welcome-tablist" role="tablist" aria-label="Welcome topics">'
      +   tabs + '</div>'
      + '</div>'
      + '<div class="welcome-body">' + panels + '</div>'
      + '</div>';
    root = container.querySelector(".welcome-workspace");
    root.querySelector(".welcome-prompt").textContent = SESSION_PROMPT;

    var tablist = root.querySelector('[role="tablist"]');
    tablist.addEventListener("click", function (e) {
      var tab = e.target.closest(".welcome-tab");
      if (tab) selectTopic(tab.dataset.topic, false);
    });
    tablist.addEventListener("keydown", function (e) {
      var idx = keyIndex(selectedTopic);
      var n = TOPICS.length;
      var next = null;
      if (e.key === "ArrowRight") next = TOPICS[(idx + 1) % n].key;
      else if (e.key === "ArrowLeft") next = TOPICS[(idx - 1 + n) % n].key;
      else if (e.key === "Home") next = TOPICS[0].key;
      else if (e.key === "End") next = TOPICS[n - 1].key;
      if (next === null) return;
      e.preventDefault();
      selectTopic(next, true);
    });
    root.querySelectorAll(".welcome-next").forEach(function (b) {
      b.addEventListener("click", function () { selectTopic(b.dataset.goto, true); });
    });
    var copyBtn = root.querySelector(".welcome-copy");
    copyBtn.addEventListener("click", function () { copySessionPrompt(copyBtn); });

    applyTopic();
  };
})();
