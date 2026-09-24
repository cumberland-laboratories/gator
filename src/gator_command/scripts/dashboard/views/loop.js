/**
 * loop.js — Loop workspace view for Gator Dashboard.
 *
 * Read-only view of governed planning loops. Shows loop list,
 * selected loop status, event timeline, and artifact inspector.
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

  // ── constants ──────────────────────────────────────────────────────────────

  var POLL_INTERVAL_MS = 3000;

  var TERMINAL_STAGES = {
    plan_approved: true,
    max_rounds_exceeded: true,
    turn_timed_out: true,
    ended_by_architect: true,
  };

  var PAUSED_STAGES = {
    blocked_on_architect: true,
    paused_by_architect: true,
  };

  var STAGE_LABELS = {
    plan_drafting:        "Drafting",
    plan_review:          "Review",
    plan_revision:        "Revision",
    blocked_on_architect: "Blocked",
    paused_by_architect:  "Paused",
    plan_approved:        "Approved",
    max_rounds_exceeded:  "Max Rounds",
    turn_timed_out:       "Timed Out",
    ended_by_architect:   "Ended",
  };

  var STAGE_BADGE_CLASS = {
    plan_drafting:        "loop-badge-active",
    plan_review:          "loop-badge-active",
    plan_revision:        "loop-badge-active",
    blocked_on_architect: "loop-badge-blocked",
    paused_by_architect:  "loop-badge-paused",
    plan_approved:        "loop-badge-terminal",
    max_rounds_exceeded:  "loop-badge-terminal",
    turn_timed_out:       "loop-badge-terminal",
    ended_by_architect:   "loop-badge-terminal",
  };

  var EVENT_LABELS = {
    loop_started:           "Loop started",
    draft_submitted:        "Draft submitted",
    review_submitted:       "Review submitted",
    plan_approved:          "Plan APPROVED",
    revision_requested:     "Revision requested",
    escalated:              "ESCALATED",
    max_rounds_exceeded:    "MAX ROUNDS",
    turn_timed_out:         "TIMED OUT",
    loop_unblocked:         "Unblocked",
    loop_paused:            "PAUSED",
    architect_interjection: "ARCHITECT",
    loop_ended_by_architect:"ENDED",
  };

  // ── view state ─────────────────────────────────────────────────────────────

  var _state = {
    repoKey: null,
    repoName: null,
    selectedLoopId: null,
    container: null,
    timerId: null,
    generation: 0,
    mountId: 0,
  };

  // ── teardown ───────────────────────────────────────────────────────────────

  function teardownLoopView() {
    if (_state.timerId) {
      clearInterval(_state.timerId);
      _state.timerId = null;
    }
    _state.generation++;
    _state.mountId++;
    var ws = _state.container && _state.container.querySelector(".loop-workspace");
    if (ws) ws.dataset.polling = "0";
    window._gatorRepoTeardown = null;
  }

  // ── data fetching ──────────────────────────────────────────────────────────

  function apiBase() {
    return "/api/repo-by-key/" + encodeURIComponent(_state.repoKey) + "/loops";
  }

  async function fetchLoops() {
    try {
      var resp = await fetch(apiBase());
      var data = await resp.json();
      return data.loops || [];
    } catch (e) {
      return [];
    }
  }

  async function fetchStatus(loopId) {
    try {
      var resp = await fetch(apiBase() + "/" + encodeURIComponent(loopId) + "/status");
      if (!resp.ok) return null;
      return await resp.json();
    } catch (e) {
      return null;
    }
  }

  async function fetchEvents(loopId) {
    try {
      var resp = await fetch(apiBase() + "/" + encodeURIComponent(loopId) + "/events");
      var data = await resp.json();
      return data.events || [];
    } catch (e) {
      return [];
    }
  }

  async function fetchArtifact(loopId, filename) {
    try {
      var resp = await fetch(
        apiBase() + "/" + encodeURIComponent(loopId)
        + "/artifact/" + encodeURIComponent(filename)
      );
      if (!resp.ok) return null;
      return await resp.text();
    } catch (e) {
      return null;
    }
  }

  // ── formatting helpers ─────────────────────────────────────────────────────

  function formatTime(isoStr) {
    if (!isoStr) return "";
    try {
      var d = new Date(isoStr);
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    } catch (e) {
      return "";
    }
  }

  function formatDate(isoStr) {
    if (!isoStr) return "";
    try {
      var d = new Date(isoStr);
      return d.toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" });
    } catch (e) {
      return "";
    }
  }

  function stageBadge(stage) {
    var label = STAGE_LABELS[stage] || stage;
    var cls = STAGE_BADGE_CLASS[stage] || "loop-badge-active";
    return '<span class="loop-badge ' + cls + '">' + escHtml(label) + '</span>';
  }

  function isTerminal(stage) {
    return !!TERMINAL_STAGES[stage];
  }

  // ── rendering: loop list ───────────────────────────────────────────────────

  function renderLoopList(loops, container) {
    var listEl = container.querySelector("#loop-list");
    if (!listEl) return;

    if (!loops.length) {
      listEl.innerHTML = '<div class="muted" style="padding:24px;text-align:center;">'
        + 'No loops found for this repository.</div>';
      return;
    }

    var sorted = loops.slice().sort(function (a, b) {
      var aTerminal = isTerminal(a.stage) ? 1 : 0;
      var bTerminal = isTerminal(b.stage) ? 1 : 0;
      if (aTerminal !== bTerminal) return aTerminal - bTerminal;
      return (b.created_at || "").localeCompare(a.created_at || "");
    });

    var html = "";
    for (var i = 0; i < sorted.length; i++) {
      var loop = sorted[i];
      var selected = loop.loop_id === _state.selectedLoopId ? " loop-card-selected" : "";
      html += '<div class="loop-card' + selected + '" data-loop-id="' + escHtml(loop.loop_id) + '">'
        + '<div class="loop-card-header">'
        + '<span class="loop-card-feature">' + escHtml(loop.feature || loop.loop_id) + '</span>'
        + stageBadge(loop.stage)
        + '</div>'
        + '<div class="loop-card-meta">'
        + '<span>Round ' + loop.round + '/' + loop.max_rounds + '</span>'
        + '<span>' + escHtml(formatDate(loop.created_at)) + '</span>'
        + '</div>'
        + '</div>';
    }
    listEl.innerHTML = html;

    listEl.querySelectorAll(".loop-card").forEach(function (card) {
      card.addEventListener("click", function () {
        _state.selectedLoopId = card.dataset.loopId;
        _state.generation++;
        renderLoopList(loops, container);
        loadSelectedLoop();
      });
    });
  }

  // ── rendering: status panel ────────────────────────────────────────────────

  function renderStatusPanel(status, container) {
    var panel = container.querySelector("#loop-status-panel");
    if (!panel) return;

    if (!status) {
      panel.innerHTML = '<div class="muted" style="padding:24px;text-align:center;">'
        + 'Select a loop to view details.</div>';
      return;
    }

    var s = status.status || {};
    var stage = s.stage || "";
    var roles = status.roles || {};
    var draftorJoined = roles.draftor && roles.draftor.joined;
    var reviewerJoined = roles.reviewer && roles.reviewer.joined;

    var timeRemaining = "";
    if (!isTerminal(stage) && s.turn_deadline) {
      var deadline = new Date(s.turn_deadline);
      var now = new Date();
      var diffMs = deadline - now;
      if (diffMs > 0) {
        var mins = Math.floor(diffMs / 60000);
        var secs = Math.floor((diffMs % 60000) / 1000);
        timeRemaining = mins + "m " + secs + "s";
      } else {
        timeRemaining = "overdue";
      }
    }

    var html = '<div class="loop-status-header">'
      + '<h3>' + escHtml(status.feature || status.loop_id || "") + '</h3>'
      + stageBadge(stage)
      + '</div>';

    html += '<div class="loop-status-grid">';

    html += '<div class="loop-status-item">'
      + '<div class="loop-status-label">Round</div>'
      + '<div class="loop-status-value">' + (s.round || 0) + ' / ' + (s.max_rounds || 0) + '</div>'
      + '</div>';

    html += '<div class="loop-status-item">'
      + '<div class="loop-status-label">Active Role</div>'
      + '<div class="loop-status-value">' + escHtml(s.next_role || "—") + '</div>'
      + '</div>';

    html += '<div class="loop-status-item">'
      + '<div class="loop-status-label">Draftor</div>'
      + '<div class="loop-status-value">' + (draftorJoined ? "Joined" : "Waiting") + '</div>'
      + '</div>';

    html += '<div class="loop-status-item">'
      + '<div class="loop-status-label">Reviewer</div>'
      + '<div class="loop-status-value">' + (reviewerJoined ? "Joined" : "Waiting") + '</div>'
      + '</div>';

    if (timeRemaining) {
      html += '<div class="loop-status-item">'
        + '<div class="loop-status-label">Time Remaining</div>'
        + '<div class="loop-status-value">' + escHtml(timeRemaining) + '</div>'
        + '</div>';
    }

    html += '</div>';

    if (s.blocked && s.escalation_reason) {
      html += '<div class="loop-blocked-card">'
        + '<div class="loop-blocked-title">Blocked on Architect</div>'
        + '<div class="loop-blocked-reason">' + escHtml(s.escalation_reason) + '</div>'
        + '</div>';
    }

    panel.innerHTML = html;
  }

  // ── architect controls ──────────────────────────────────────────────────────

  async function postAction(loopId, action, body) {
    try {
      var resp = await fetch(
        apiBase() + "/" + encodeURIComponent(loopId) + "/" + action,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Gator-Dashboard": "1",
          },
          body: JSON.stringify(body || {}),
        }
      );
      var data = await resp.json();
      if (!resp.ok) {
        return { _failed: true, error: data.error || "Request failed (" + resp.status + ")" };
      }
      return data;
    } catch (e) {
      return { _failed: true, error: String(e) };
    }
  }

  function renderControls(status, container) {
    var panel = container.querySelector("#loop-controls");
    if (!panel) return;

    if (!status || !_state.selectedLoopId) {
      panel.innerHTML = "";
      return;
    }

    var s = status.status || {};
    var stage = s.stage || "";
    var loopId = _state.selectedLoopId;

    if (isTerminal(stage)) {
      panel.innerHTML = "";
      return;
    }

    var html = '<div class="loop-controls-bar">';
    var isActive = !TERMINAL_STAGES[stage] && !PAUSED_STAGES[stage];

    if (isActive) {
      html += '<button class="loop-ctrl-btn loop-ctrl-pause" data-action="pause">Pause</button>';
      html += '<button class="loop-ctrl-btn loop-ctrl-interject" data-action="interject">Interject</button>';
      html += '<button class="loop-ctrl-btn loop-ctrl-end" data-action="end">End</button>';
    } else {
      html += '<button class="loop-ctrl-btn loop-ctrl-unblock" data-action="unblock">Unblock</button>';
      html += '<button class="loop-ctrl-btn loop-ctrl-end" data-action="end">End</button>';
    }

    html += '</div>';
    html += '<div class="loop-ctrl-input-area" style="display:none;">'
      + '<input type="text" class="loop-ctrl-input" placeholder="Message (optional)">'
      + '<button class="loop-ctrl-confirm">Confirm</button>'
      + '<button class="loop-ctrl-cancel">Cancel</button>'
      + '</div>';
    panel.innerHTML = html;

    var inputArea = panel.querySelector(".loop-ctrl-input-area");
    var input = panel.querySelector(".loop-ctrl-input");
    var pendingAction = null;

    function clearCtrlError() {
      var el = panel.querySelector(".loop-ctrl-error");
      if (el) el.remove();
    }

    panel.querySelectorAll(".loop-ctrl-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        clearCtrlError();
        var action = btn.dataset.action;
        if (action === "interject") {
          pendingAction = action;
          input.placeholder = "Message (required)";
          input.value = "";
          inputArea.style.display = "flex";
        } else if (action === "pause" || action === "unblock") {
          pendingAction = action;
          input.placeholder = "Message (optional)";
          input.value = "";
          inputArea.style.display = "flex";
        } else if (action === "end") {
          pendingAction = action;
          input.placeholder = "Reason (optional)";
          input.value = "";
          inputArea.style.display = "flex";
        }
      });
    });

    panel.querySelector(".loop-ctrl-cancel").addEventListener("click", function () {
      clearCtrlError();
      inputArea.style.display = "none";
      pendingAction = null;
    });

    panel.querySelector(".loop-ctrl-confirm").addEventListener("click", function () {
      if (!pendingAction) return;
      var action = pendingAction;
      var msg = input.value.trim();

      if (action === "interject" && !msg) {
        input.classList.add("loop-ctrl-input-error");
        return;
      }

      var body = {};
      if (action === "end") {
        if (msg) body.reason = msg;
      } else {
        if (msg) body.message = msg;
      }

      postAction(loopId, action, body).then(function (result) {
        if (result && result._failed) {
          var errEl = panel.querySelector(".loop-ctrl-error");
          if (!errEl) {
            errEl = document.createElement("div");
            errEl.className = "loop-ctrl-error";
            inputArea.parentNode.insertBefore(errEl, inputArea.nextSibling);
          }
          errEl.textContent = result.error || "Action failed";
          return;
        }
        inputArea.style.display = "none";
        pendingAction = null;
        loadSelectedLoop();
      });
    });

    input.addEventListener("input", function () {
      input.classList.remove("loop-ctrl-input-error");
    });
  }

  // ── rendering: event timeline ──────────────────────────────────────────────

  function _artifactForEvent(ev) {
    if (ev.artifact_path) return ev.artifact_path;
    return null;
  }

  function renderTimeline(events, container) {
    var timeline = container.querySelector("#loop-timeline");
    if (!timeline) return;

    if (!events.length) {
      timeline.innerHTML = '<div class="muted" style="padding:12px;">No events yet.</div>';
      return;
    }

    var html = "";
    for (var i = 0; i < events.length; i++) {
      var ev = events[i];
      var eventType = ev.event || ev.type || "unknown";
      var label = EVENT_LABELS[eventType] || eventType;
      var isTerminalEv = !!TERMINAL_STAGES[eventType];
      var artifact = _artifactForEvent(ev);

      var detail = "";
      if (ev.round !== undefined) detail = "round " + ev.round;
      if (ev.role) detail = ev.role;
      if (ev.detail) detail = ev.detail;
      if (ev.reason) detail = ev.reason;

      html += '<div class="loop-event' + (isTerminalEv ? " loop-event-terminal" : "") + '"'
        + (artifact ? ' data-artifact="' + escHtml(artifact) + '"' : '')
        + '>'
        + '<span class="loop-event-time">' + escHtml(formatTime(ev.ts)) + '</span>'
        + '<span class="loop-event-label">' + escHtml(label) + '</span>';
      if (detail) {
        html += '<span class="loop-event-detail">' + escHtml(detail) + '</span>';
      }
      if (artifact) {
        html += '<div class="loop-event-summary"></div>';
      }
      html += '</div>';
    }
    timeline.innerHTML = html;

    var clickGen = _state.generation;
    var clickLoopId = _state.selectedLoopId;
    timeline.querySelectorAll(".loop-event[data-artifact]").forEach(function (card) {
      var filename = card.dataset.artifact;
      fetchArtifact(clickLoopId, filename).then(function (text) {
        if (clickGen !== _state.generation) return;
        if (!card.isConnected) return;
        var summaryEl = card.querySelector(".loop-event-summary");
        if (!summaryEl) return;
        var summary = extractSummary(text);
        if (summary) {
          summaryEl.innerHTML = '<div class="loop-timeline-summary-text">'
            + escHtml(summary) + '</div>'
            + '<a class="loop-timeline-artifact-link" data-artifact="'
            + escHtml(filename) + '">View full artifact</a>';
        } else if (text !== null) {
          summaryEl.innerHTML = '<div class="loop-timeline-summary-absent">'
            + 'No executive summary supplied</div>'
            + '<a class="loop-timeline-artifact-link" data-artifact="'
            + escHtml(filename) + '">View full artifact</a>';
        }
        var link = summaryEl.querySelector(".loop-timeline-artifact-link");
        if (link) {
          link.addEventListener("click", function (e) {
            e.preventDefault();
            var target = container.querySelector(
              '.loop-artifact-section[data-artifact="' + filename + '"] .loop-artifact-toggle');
            if (target) {
              target.scrollIntoView({ behavior: "smooth", block: "center" });
              target.click();
            }
          });
        }
      });
    });
  }

  // ── executive summary extraction ────────────────────────────────────────────

  var SUMMARY_MAX_CHARS = 500;
  var SUMMARY_RE = /^\s*##\s+executive\s+summary\s*$/im;

  function extractSummary(text) {
    if (!text) return null;
    var match = SUMMARY_RE.exec(text);
    if (!match) return null;
    var start = match.index + match[0].length;
    var rest = text.slice(start);
    var nextHeading = rest.search(/^##\s/m);
    var body = nextHeading >= 0 ? rest.slice(0, nextHeading) : rest;
    body = body.trim();
    if (!body) return null;
    if (body.length > SUMMARY_MAX_CHARS) {
      return body.slice(0, SUMMARY_MAX_CHARS) + "…";
    }
    return body;
  }

  // ── rendering: artifact inspector ──────────────────────────────────────────

  function renderArtifacts(status, container) {
    var inspector = container.querySelector("#loop-artifacts");
    if (!inspector) return;

    if (!status) {
      inspector.innerHTML = "";
      return;
    }

    var artifacts = ["sketch.md", "plan.current.md", "findings.current.md"];
    var s = status.status || {};
    var round = s.round || 0;
    for (var r = 1; r <= round; r++) {
      artifacts.push("plan.round-" + r + ".md");
      artifacts.push("findings.round-" + r + ".md");
    }

    var html = '<div class="section-title">Artifacts</div>';
    for (var i = 0; i < artifacts.length; i++) {
      var name = artifacts[i];
      html += '<div class="loop-artifact-section" data-artifact="' + escHtml(name) + '">'
        + '<button class="loop-artifact-toggle">' + escHtml(name) + '</button>'
        + '<div class="loop-artifact-summary"></div>'
        + '<div class="loop-artifact-content" style="display:none;"></div>'
        + '</div>';
    }
    inspector.innerHTML = html;

    var summaryArtifacts = artifacts.filter(function (n) {
      return n.indexOf("plan.") === 0 || n.indexOf("findings.") === 0;
    });
    summaryArtifacts.forEach(function (filename) {
      var clickGen = _state.generation;
      var clickLoopId = _state.selectedLoopId;
      fetchArtifact(clickLoopId, filename).then(function (text) {
        if (clickGen !== _state.generation) return;
        var section = inspector.querySelector(
          '.loop-artifact-section[data-artifact="' + filename + '"]');
        if (!section || !section.isConnected) return;
        var summaryEl = section.querySelector(".loop-artifact-summary");
        if (!summaryEl) return;
        var summary = extractSummary(text);
        if (summary) {
          summaryEl.innerHTML = '<div class="loop-summary-text">'
            + escHtml(summary) + '</div>';
        } else if (text !== null) {
          summaryEl.innerHTML = '<div class="loop-summary-absent">'
            + 'No executive summary supplied</div>';
        }
      });
    });

    inspector.querySelectorAll(".loop-artifact-toggle").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var section = btn.closest(".loop-artifact-section");
        var content = section.querySelector(".loop-artifact-content");
        if (content.style.display === "none") {
          content.style.display = "block";
          if (!content.dataset.loaded) {
            content.innerHTML = '<div class="muted">Loading…</div>';
            var filename = section.dataset.artifact;
            var clickGen = _state.generation;
            var clickLoopId = _state.selectedLoopId;
            fetchArtifact(clickLoopId, filename).then(function (text) {
              if (clickGen !== _state.generation) return;
              if (!content.isConnected) return;
              content.dataset.loaded = "1";
              if (text === null) {
                content.innerHTML = '<div class="muted">Not available.</div>';
              } else {
                content.innerHTML = '<pre class="loop-artifact-pre">' + escHtml(text) + '</pre>';
              }
            });
          }
        } else {
          content.style.display = "none";
        }
      });
    });
  }

  // ── main load ──────────────────────────────────────────────────────────────

  async function loadSelectedLoop() {
    var gen = _state.generation;
    if (!_state.selectedLoopId || !_state.container) return;

    var status = await fetchStatus(_state.selectedLoopId);
    if (gen !== _state.generation) return;

    var events = await fetchEvents(_state.selectedLoopId);
    if (gen !== _state.generation) return;

    renderStatusPanel(status, _state.container);
    renderControls(status, _state.container);
    renderTimeline(events, _state.container);
    renderArtifacts(status, _state.container);
  }

  async function pollLoop() {
    var gen = _state.generation;
    if (document.hidden) return;
    if (!_state.selectedLoopId) return;

    var status = await fetchStatus(_state.selectedLoopId);
    if (gen !== _state.generation) return;
    if (!status) return;

    var stage = (status.status || {}).stage || "";
    renderStatusPanel(status, _state.container);
    renderControls(status, _state.container);

    var events = await fetchEvents(_state.selectedLoopId);
    if (gen !== _state.generation) return;
    renderTimeline(events, _state.container);

    if (isTerminal(stage)) {
      if (_state.timerId) {
        clearInterval(_state.timerId);
        _state.timerId = null;
      }
      var ws = _state.container && _state.container.querySelector(".loop-workspace");
      if (ws) ws.dataset.polling = "0";
    }

    var loops = await fetchLoops();
    if (gen !== _state.generation) return;
    renderLoopList(loops, _state.container);
  }

  // ── entry point ────────────────────────────────────────────────────────────

  window.GatorViews.loop = async function (data, container, repoName, repoKey) {
    teardownLoopView();

    _state.repoKey = repoKey;
    _state.repoName = repoName;
    _state.container = container;
    _state.selectedLoopId = null;
    _state.generation++;
    var myMount = _state.mountId;

    container.innerHTML =
      '<div class="loop-workspace">'
      + '<div class="loop-sidebar" id="loop-list">'
      +   '<div class="muted" style="padding:24px;text-align:center;">Loading…</div>'
      + '</div>'
      + '<div class="loop-main">'
      +   '<div id="loop-status-panel">'
      +     '<div class="muted" style="padding:24px;text-align:center;">Select a loop to view details.</div>'
      +   '</div>'
      +   '<div id="loop-controls"></div>'
      +   '<div class="section-title" style="margin-top:20px;">Timeline</div>'
      +   '<div id="loop-timeline">'
      +     '<div class="muted" style="padding:12px;">Select a loop to view events.</div>'
      +   '</div>'
      +   '<div id="loop-artifacts"></div>'
      + '</div>'
      + '</div>';

    var loops = await fetchLoops();
    if (myMount !== _state.mountId) return;

    renderLoopList(loops, container);

    if (loops.length > 0) {
      var firstNonTerminal = loops.find(function (l) { return !isTerminal(l.stage); });
      _state.selectedLoopId = firstNonTerminal ? firstNonTerminal.loop_id : loops[0].loop_id;
      _state.generation++;
      renderLoopList(loops, container);
      await loadSelectedLoop();
      if (myMount !== _state.mountId) return;
    }

    window._gatorRepoTeardown = teardownLoopView;
    _state.timerId = setInterval(pollLoop, POLL_INTERVAL_MS);
    var ws = container.querySelector(".loop-workspace");
    if (ws) ws.dataset.polling = "1";
  };

  window.GatorViews._extractSummary = extractSummary;
})();
