/**
 * views/welcome.js — Welcome workspace (#72), opened from the sidebar logo.
 *
 * Four topics in the shared main-pane tab bar (.gator-tabbar). Each topic
 * body is a shipped, standalone HTML document shown in an iframe.
 *
 * Contract:
 *   - Requests: only GET /api/welcome/docs/<name> for the four allowlisted
 *     documents, each loaded lazily on its topic's first selection in a
 *     mount (a snapshot assigns window.GATOR_WELCOME_DOCS[name] to
 *     iframe.srcdoc instead). No storage, no console output, no history
 *     calls. The shell owns routing; this view never touches repository
 *     context.
 *   - Every frame is sandboxed exactly "allow-scripts" (opaque origin; no
 *     allow-same-origin, forms, popups, or top navigation). Document HTML
 *     never enters the Dashboard DOM.
 *   - A frame is created once per mount and never re-created or
 *     re-pointed while the mount lives, so returning to a topic does not
 *     reload it.
 *   - One message is accepted: {type:"gator-welcome", v:1,
 *     action:"copy-session-prompt"} from this mount's Start-a-session
 *     frame (opaque "null" origin). The Dashboard writes its own
 *     SESSION_PROMPT and replies to that frame only, without the prompt.
 *     Everything else is ignored: no write, reply, or state change.
 *   - The selected topic is module-local: it survives reopening Welcome
 *     while the page stays loaded and resets on a fresh page load.
 */

(function () {
  "use strict";

  window.GatorViews = window.GatorViews || {};

  var TOPICS = [
    { key: "how",      label: "How Gator works",            doc: "how-gator-works.html" },
    { key: "can",      label: "What Gator can do",          doc: "what-gator-can-do.html" },
    { key: "gatorize", label: "Gatorize a repo",            doc: "gatorize-a-repo.html" },
    { key: "session",  label: "Start a session with Gator", doc: "start-a-session.html" },
  ];

  var DOC_ROUTE = "/api/welcome/docs/";

  // Exact text from the #72 sketch. No layout-dependent path, no vendor.
  // One line by Architect direction (2026-10-10): a pasted newline can
  // submit early in terminal agent UIs. The Dashboard owns it: it is never
  // received from, or sent to, a Welcome document.
  var SESSION_PROMPT =
    "Run gator init in this repository. Treat its output, including the required "
    + "session-opening reads, as binding. Do not provide a substantive response until "
    + "those reads are complete.";

  // The one cross-frame message: the Start-a-session document asks the
  // Dashboard to copy SESSION_PROMPT. Exact shape, nothing else accepted.
  var MSG_TYPE = "gator-welcome";
  var COPY_REQUEST = "copy-session-prompt";
  var COPY_RESULT = "copy-session-prompt-result";

  var selectedTopic = "how";
  var root = null;
  // The current mount's frames, by topic key. Replaced on every mount.
  var frames = {};
  // The current mount's message listener (removed on the next mount, or by
  // itself once its root is detached).
  var copyListener = null;

  function keyIndex(key) {
    for (var i = 0; i < TOPICS.length; i++) if (TOPICS[i].key === key) return i;
    return -1;
  }

  // Creates the topic's frame once per mount. A snapshot entry that is
  // missing or null gets a text notice instead of a frame.
  function ensureFrame(key) {
    if (!root || frames[key]) return;
    var topic = TOPICS[keyIndex(key)];
    var panel = root.querySelector("#welcome-panel-" + key);
    var text = null;
    if (window.GATOR_SNAPSHOT) {
      var docs = window.GATOR_WELCOME_DOCS || {};
      text = docs[topic.doc];
      if (typeof text !== "string") {
        var notice = document.createElement("p");
        notice.className = "welcome-doc-status";
        notice.textContent = "“" + topic.label + "” is not available in this "
          + "snapshot. In a gatorized repository, read .gator/docs/" + topic.doc + ".";
        panel.appendChild(notice);
        frames[key] = notice;
        return;
      }
    }
    var frame = document.createElement("iframe");
    frame.className = "welcome-frame";
    frame.setAttribute("sandbox", "allow-scripts");
    frame.title = topic.label;
    if (window.GATOR_SNAPSHOT) frame.srcdoc = text;
    else frame.src = DOC_ROUTE + topic.doc;
    panel.appendChild(frame);
    frames[key] = frame;
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
    ensureFrame(selectedTopic);
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

  // ── Copy action (the only cross-frame message) ────────────────────────

  // A structured-clone plain object with exactly {type, v, action}.
  function isCopyRequest(d) {
    if (d === null || typeof d !== "object"
        || Object.getPrototypeOf(d) !== Object.prototype) return false;
    return Object.keys(d).length === 3
      && d.type === MSG_TYPE && d.v === 1 && d.action === COPY_REQUEST;
  }

  // Replies only to the requesting frame; never carries the prompt. An
  // opaque origin cannot be named, so the target origin is "*".
  function replyCopy(source, ok, reason) {
    var msg = { type: MSG_TYPE, v: 1, action: COPY_RESULT, ok: ok };
    if (!ok) msg.reason = reason;
    try { source.postMessage(msg, "*"); } catch (e) { /* frame gone */ }
  }

  async function handleCopyRequest(source) {
    if (!(navigator.clipboard && navigator.clipboard.writeText)) {
      replyCopy(source, false, "unavailable");
      return;
    }
    try {
      await navigator.clipboard.writeText(SESSION_PROMPT);
    } catch (e) {
      replyCopy(source, false, "denied");
      return;
    }
    replyCopy(source, true);
  }

  // One listener per mount. It acts only for this mount's connected
  // Start-a-session frame, an opaque ("null") origin, and the exact
  // request shape; anything else returns before any side effect.
  function bindCopyListener(mountRoot, mountFrames) {
    if (copyListener) window.removeEventListener("message", copyListener);
    var listener = function (event) {
      if (!mountRoot.isConnected) {
        window.removeEventListener("message", listener);
        if (copyListener === listener) copyListener = null;
        return;
      }
      var frame = mountFrames.session;
      if (!frame || frame.tagName !== "IFRAME" || !frame.isConnected) return;
      if (!event.source || event.source !== frame.contentWindow) return;
      if (event.origin !== "null") return;
      if (!isCopyRequest(event.data)) return;
      handleCopyRequest(event.source);
    };
    copyListener = listener;
    window.addEventListener("message", listener);
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
        + '</section>';
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
    frames = {};
    bindCopyListener(root, frames);

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

    applyTopic();
  };
})();
