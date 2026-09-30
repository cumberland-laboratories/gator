/**
 * loop.js — Loop workspace view for Gator Dashboard.
 *
 * Secondary sidebar (Create / Active / History) with mode-driven
 * main content: creation workspace, participant handoff, or
 * selected-loop inspection (live or historical).
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

  // Mirrors loop/session.py TURN_TIMEOUT_MIN/MAX; the server re-validates.
  var TURN_TIMEOUT_MIN = 30;
  var TURN_TIMEOUT_MAX = 3600;

  // Mirrors loop/session.py ROUNDS_MIN/MAX (per-extension increment, #39).
  var ROUNDS_MIN = 1;
  var ROUNDS_MAX = 20;
  var EXTENDABLE_STAGE = "max_rounds_exceeded";

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

  var OUTCOME_LABELS = {
    plan_approved:        "Approved",
    max_rounds_exceeded:  "Max Rounds Reached",
    turn_timed_out:       "Timed Out",
    ended_by_architect:   "Ended by Architect",
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
    loop_extended:          "Extended",
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
    mode: "create",       // "create" | "handoff" | "inspect"
    handoffId: null,       // loop_id during handoff
    promptEpoch: 0,        // incremented on terminal — invalidates in-flight copies
    loops: [],             // cached loop list
    render: null,          // incremental-render snapshot for the selected loop (#38)
  };

  // ── teardown ───────────────────────────────────────────────────────────────

  function teardownLoopView() {
    if (_state.timerId) {
      clearInterval(_state.timerId);
      _state.timerId = null;
    }
    _state.generation++;
    _state.mountId++;
    _state.mode = "create";
    _state.handoffId = null;
    _state.loops = [];
    _state.render = null;
    var ws = _state.container && _state.container.querySelector(".loop-workspace");
    if (ws) ws.dataset.polling = "0";
    window._gatorRepoTeardown = null;
  }

  // ── data fetching ──────────────────────────────────────────────────────────

  function apiBase() {
    return "/api/repo-by-key/" + encodeURIComponent(_state.repoKey) + "/loops";
  }

  function sketchSourcesUrl() {
    return "/api/repo-by-key/" + encodeURIComponent(_state.repoKey)
      + "/sketch-sources";
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

  // Participant liveness (#36): Architect-only, never cached. Returns the
  // allowlisted view, or {_error: status} when the route denies/fails.
  async function fetchLiveness(loopId) {
    try {
      var resp = await fetch(
        apiBase() + "/" + encodeURIComponent(loopId) + "/liveness",
        { cache: "no-store" });
      if (!resp.ok) return { _error: resp.status };
      return await resp.json();
    } catch (e) {
      return { _error: 0 };
    }
  }

  async function postRenotify(loopId, role, reason) {
    try {
      var resp = await fetch(
        apiBase() + "/" + encodeURIComponent(loopId) + "/renotify",
        {
          method: "POST",
          cache: "no-store",
          headers: {
            "Content-Type": "application/json",
            "X-Gator-Dashboard": "1",
          },
          body: JSON.stringify({ role: role, reason: reason }),
        }
      );
      var data = await resp.json();
      if (!resp.ok) {
        return { _failed: true, _status: resp.status, code: data.code || null,
                 error: data.error || "Request failed (" + resp.status + ")" };
      }
      return data;
    } catch (e) {
      return { _failed: true, code: null, error: String(e) };
    }
  }

  async function fetchArtifact(loopId, filename) {
    try {
      // no-store: plan.current.md / findings.current.md are rewritten in
      // place, and incremental refresh must not read a stale cached copy.
      var resp = await fetch(
        apiBase() + "/" + encodeURIComponent(loopId)
        + "/artifact/" + encodeURIComponent(filename),
        { cache: "no-store" }
      );
      if (!resp.ok) return null;
      return await resp.text();
    } catch (e) {
      return null;
    }
  }

  async function fetchSketchSources() {
    try {
      var resp = await fetch(sketchSourcesUrl());
      if (!resp.ok) return [];
      var data = await resp.json();
      return data.sources || [];
    } catch (e) {
      return [];
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

  function formatTimeoutHuman(seconds) {
    if (seconds >= 60 && seconds % 60 === 0) return (seconds / 60) + " min";
    if (seconds >= 60) return Math.floor(seconds / 60) + "m " + (seconds % 60) + "s";
    return seconds + "s";
  }

  function stageBadge(stage) {
    var label = STAGE_LABELS[stage] || stage;
    var cls = STAGE_BADGE_CLASS[stage] || "loop-badge-active";
    return '<span class="loop-badge ' + cls + '">' + escHtml(label) + '</span>';
  }

  function isTerminal(stage) {
    return !!TERMINAL_STAGES[stage];
  }

  // ── POST helper ────────────────────────────────────────────────────────────

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
        return { _failed: true, _status: resp.status, error: data.error || "Request failed (" + resp.status + ")" };
      }
      return data;
    } catch (e) {
      return { _failed: true, error: String(e) };
    }
  }

  async function postStart(body) {
    try {
      var resp = await fetch(
        apiBase() + "/start",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Gator-Dashboard": "1",
          },
          body: JSON.stringify(body),
        }
      );
      var data = await resp.json();
      if (!resp.ok) {
        return { _failed: true, _status: resp.status, error: data.error || "Request failed (" + resp.status + ")", loop_id: data.loop_id };
      }
      return data;
    } catch (e) {
      return { _failed: true, error: String(e) };
    }
  }

  async function fetchPrompt(loopId, role) {
    try {
      var resp = await fetch(
        apiBase() + "/" + encodeURIComponent(loopId) + "/prompt",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Gator-Dashboard": "1",
          },
          body: JSON.stringify({ role: role }),
        }
      );
      if (!resp.ok) return null;
      var data = await resp.json();
      return data.prompt || null;
    } catch (e) {
      return null;
    }
  }

  // ── Module 1: Secondary sidebar ────────────────────────────────────────────

  function classifyLoops(loops) {
    var active = [];
    var history = [];
    for (var i = 0; i < loops.length; i++) {
      if (isTerminal(loops[i].stage)) {
        history.push(loops[i]);
      } else {
        active.push(loops[i]);
      }
    }
    history.sort(function (a, b) {
      return (b.created_at || "").localeCompare(a.created_at || "");
    });
    return { active: active, history: history };
  }

  function renderLoopSidebar(loops, container) {
    var listEl = container.querySelector("#loop-sidebar-nav");
    if (!listEl) return;

    var classified = classifyLoops(loops);
    var hasActive = classified.active.length > 0;
    var html = "";

    // Create Loop action
    if (hasActive) {
      html += '<div class="loop-sidebar-create loop-sidebar-create-disabled">'
        + '<span class="loop-sidebar-create-label">Create Loop</span>'
        + '<div class="loop-sidebar-create-conflict">Active loop in progress &mdash; '
        + '<a class="loop-sidebar-open-active" href="#">Open active loop</a>'
        + '</div></div>';
    } else {
      var createSelected = _state.mode === "create" || _state.mode === "handoff"
        ? " loop-sidebar-item-selected" : "";
      html += '<button class="loop-sidebar-create' + createSelected + '">'
        + '<span class="loop-sidebar-create-label">+ Create Loop</span>'
        + '</button>';
    }

    // Active section
    html += '<div class="loop-sidebar-section">'
      + '<div class="loop-sidebar-section-header">Active</div>';
    if (classified.active.length === 0) {
      html += '<div class="loop-sidebar-empty">No active loop</div>';
    } else {
      for (var a = 0; a < classified.active.length; a++) {
        html += renderSidebarCard(classified.active[a]);
      }
    }
    html += '</div>';

    // History section
    html += '<div class="loop-sidebar-section">'
      + '<div class="loop-sidebar-section-header">History</div>';
    if (classified.history.length === 0) {
      html += '<div class="loop-sidebar-empty">No completed loops</div>';
    } else {
      for (var h = 0; h < classified.history.length; h++) {
        html += renderSidebarCard(classified.history[h]);
      }
    }
    html += '</div>';

    listEl.innerHTML = html;

    // Wire Create Loop click
    var createBtn = listEl.querySelector(".loop-sidebar-create:not(.loop-sidebar-create-disabled)");
    if (createBtn) {
      createBtn.addEventListener("click", function () {
        _state.mode = "create";
        _state.selectedLoopId = null;
        _state.handoffId = null;
        _state.generation++;
        renderLoopSidebar(loops, container);
        renderMainContent(container);
      });
    }

    // Wire "Open active loop" link in conflict state
    var openActiveLink = listEl.querySelector(".loop-sidebar-open-active");
    if (openActiveLink && classified.active.length > 0) {
      openActiveLink.addEventListener("click", function (e) {
        e.preventDefault();
        _state.mode = "inspect";
        _state.selectedLoopId = classified.active[0].loop_id;
        _state.handoffId = null;
        _state.generation++;
        renderLoopSidebar(loops, container);
        loadSelectedLoop();
      });
    }

    // Wire loop card clicks
    listEl.querySelectorAll(".loop-sidebar-card").forEach(function (card) {
      card.addEventListener("click", function () {
        _state.mode = "inspect";
        _state.selectedLoopId = card.dataset.loopId;
        _state.handoffId = null;
        _state.generation++;
        renderLoopSidebar(loops, container);
        loadSelectedLoop();
      });
    });
  }

  function renderSidebarCard(loop) {
    var selected = loop.loop_id === _state.selectedLoopId && _state.mode === "inspect"
      ? " loop-sidebar-item-selected" : "";
    return '<div class="loop-sidebar-card loop-card' + selected + '" data-loop-id="' + escHtml(loop.loop_id) + '">'
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

  // ── Module 3: Creation workspace ───────────────────────────────────────────

  function renderCreateWorkspace(container) {
    var mainEl = container.querySelector("#loop-main-content");
    if (!mainEl) return;

    var html = '<div class="loop-create-workspace">'
      + '<h3 class="loop-create-title">Create Loop</h3>';

    // Section 1: Define the work
    html += '<div class="loop-create-section">'
      + '<div class="loop-create-section-title">1. Define the work</div>'
      + '<div class="loop-create-field">'
      + '<label class="loop-create-label" for="loop-feature-input">Feature name</label>'
      + '<input type="text" id="loop-feature-input" class="loop-create-input" placeholder="e.g., input-validation">'
      + '</div>'
      + '<div class="loop-create-field">'
      + '<label class="loop-create-label">Sketch source</label>'
      + '<div id="loop-sketch-picker">'
      + '<div class="muted" style="padding:8px 0;">Loading sketch sources…</div>'
      + '</div>'
      + '</div>'
      + '<div class="loop-create-context">'
      + '<span class="loop-create-context-label">Repository:</span> ' + escHtml(_state.repoName || "")
      + '</div>'
      + '</div>';

    // Section 2: Loop settings
    html += '<div class="loop-create-section">'
      + '<div class="loop-create-section-title">2. Loop settings</div>'
      + '<details class="loop-create-advanced">'
      + '<summary>Advanced settings</summary>'
      + '<div class="loop-create-advanced-body">'
      + '<div class="loop-create-field">'
      + '<label class="loop-create-label" for="loop-max-rounds">Max rounds</label>'
      + '<input type="number" id="loop-max-rounds" class="loop-create-input loop-create-input-small" value="3" min="1" max="20">'
      + '</div>'
      + '<div class="loop-create-field">'
      + '<label class="loop-create-label" for="loop-turn-timeout">Turn timeout (seconds)</label>'
      + '<input type="number" id="loop-turn-timeout" class="loop-create-input loop-create-input-small" value="300" min="30" max="3600">'
      + '<div class="loop-create-hint" id="loop-timeout-hint">5 min</div>'
      + '</div>'
      + '</div>'
      + '</details>'
      + '</div>';

    // Section 3: What happens next
    html += '<div class="loop-create-section">'
      + '<div class="loop-create-section-title">3. What happens next</div>'
      + '<ol class="loop-create-steps">'
      + '<li>Gator creates the loop residue and begins monitoring it.</li>'
      + '<li>You manually open the chosen Draftor and Reviewer model sessions.</li>'
      + '<li>The Dashboard supplies one complete, role-specific entry prompt for each participant.</li>'
      + '<li>You observe and intervene from the loop workspace.</li>'
      + '</ol>'
      + '</div>';

    // Action
    html += '<button class="loop-create-btn" id="loop-create-action">Create Loop</button>'
      + '<div id="loop-create-error" class="loop-create-error" style="display:none;"></div>';

    html += '</div>';
    mainEl.innerHTML = html;

    // Load sketch sources
    loadSketchPicker(container);

    // Wire timeout hint
    var timeoutInput = mainEl.querySelector("#loop-turn-timeout");
    var timeoutHint = mainEl.querySelector("#loop-timeout-hint");
    if (timeoutInput && timeoutHint) {
      timeoutInput.addEventListener("input", function () {
        var val = parseInt(timeoutInput.value, 10);
        timeoutHint.textContent = isNaN(val) ? "" : formatTimeoutHuman(val);
      });
    }

    // Wire Escape to close advanced settings disclosure
    var advancedDetails = mainEl.querySelector(".loop-create-advanced");
    if (advancedDetails) {
      advancedDetails.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && advancedDetails.open) {
          advancedDetails.open = false;
          e.stopPropagation();
        }
      });
    }

    // Wire Create action
    var createBtn = mainEl.querySelector("#loop-create-action");
    createBtn.addEventListener("click", function () {
      handleCreateSubmit(container);
    });
  }

  async function loadSketchPicker(container) {
    var pickerEl = container.querySelector("#loop-sketch-picker");
    if (!pickerEl) return;

    var sources = await fetchSketchSources();

    var html = '';
    var hasSourceFiles = sources.length > 0;

    // Mode toggle
    html += '<div class="loop-sketch-mode">';
    if (hasSourceFiles) {
      html += '<a class="loop-sketch-toggle" id="loop-sketch-toggle" href="#">Enter path manually</a>';
    }
    html += '</div>';

    // Browse dropdown (shown by default if sources exist)
    if (hasSourceFiles) {
      html += '<select id="loop-sketch-select" class="loop-create-input">'
        + '<option value="">Select a sketch file…</option>';
      for (var i = 0; i < sources.length; i++) {
        var src = sources[i];
        html += '<option value="' + escHtml(src.path) + '">'
          + escHtml(src.path) + '</option>';
      }
      html += '</select>';
    }

    // Manual path input (hidden by default if sources exist)
    html += '<input type="text" id="loop-sketch-manual" class="loop-create-input" '
      + 'placeholder="Repo-relative path, e.g. .gator/artifacts/my-sketch.md"'
      + (hasSourceFiles ? ' style="display:none;"' : '') + '>';

    if (!hasSourceFiles) {
      html += '<div class="loop-create-hint">No sketch files found in standard locations. Enter a repo-relative path.</div>';
    }

    pickerEl.innerHTML = html;

    // Wire mode toggle
    var toggle = pickerEl.querySelector("#loop-sketch-toggle");
    var selectEl = pickerEl.querySelector("#loop-sketch-select");
    var manualEl = pickerEl.querySelector("#loop-sketch-manual");
    if (toggle && selectEl && manualEl) {
      toggle.addEventListener("click", function (e) {
        e.preventDefault();
        if (manualEl.style.display === "none") {
          manualEl.style.display = "";
          selectEl.style.display = "none";
          toggle.textContent = "Browse files";
        } else {
          selectEl.style.display = "";
          manualEl.style.display = "none";
          toggle.textContent = "Enter path manually";
        }
      });
    }
  }

  function getSketchPath(container) {
    var selectEl = container.querySelector("#loop-sketch-select");
    var manualEl = container.querySelector("#loop-sketch-manual");
    if (selectEl && selectEl.style.display !== "none" && selectEl.value) {
      return selectEl.value;
    }
    if (manualEl && manualEl.style.display !== "none" && manualEl.value.trim()) {
      return manualEl.value.trim();
    }
    return "";
  }

  async function handleCreateSubmit(container) {
    var errorEl = container.querySelector("#loop-create-error");
    var featureEl = container.querySelector("#loop-feature-input");
    var feature = (featureEl.value || "").trim();
    var sketchPath = getSketchPath(container);

    // Clear previous errors
    errorEl.style.display = "none";
    errorEl.textContent = "";
    featureEl.classList.remove("loop-create-input-error");

    // Client-side validation
    if (!feature) {
      featureEl.classList.add("loop-create-input-error");
      errorEl.textContent = "Feature name is required.";
      errorEl.style.display = "block";
      featureEl.focus();
      return;
    }

    if (!sketchPath) {
      errorEl.textContent = "A sketch source is required.";
      errorEl.style.display = "block";
      return;
    }

    var maxRoundsEl = container.querySelector("#loop-max-rounds");
    var timeoutEl = container.querySelector("#loop-turn-timeout");
    var maxRounds = parseInt(maxRoundsEl.value, 10);
    var turnTimeout = parseInt(timeoutEl.value, 10);

    if (isNaN(maxRounds) || maxRounds < 1 || maxRounds > 20) {
      errorEl.textContent = "Max rounds must be between 1 and 20.";
      errorEl.style.display = "block";
      return;
    }
    if (isNaN(turnTimeout) || turnTimeout < 30 || turnTimeout > 3600) {
      errorEl.textContent = "Turn timeout must be between 30 and 3600 seconds.";
      errorEl.style.display = "block";
      return;
    }

    var createBtn = container.querySelector("#loop-create-action");
    createBtn.disabled = true;
    createBtn.textContent = "Creating…";

    var result = await postStart({
      feature: feature,
      sketch_path: sketchPath,
      max_rounds: maxRounds,
      turn_timeout: turnTimeout,
    });

    createBtn.disabled = false;
    createBtn.textContent = "Create Loop";

    if (result._failed) {
      if (result._status === 409 && result.error === "active loop exists") {
        // Race recovery: a loop started elsewhere
        errorEl.innerHTML = 'A loop is already active. '
          + '<a class="loop-create-open-active" href="#">Open active loop</a>';
        errorEl.style.display = "block";
        var openLink = errorEl.querySelector(".loop-create-open-active");
        openLink.addEventListener("click", function (e) {
          e.preventDefault();
          var activeId = result.loop_id;
          _state.mode = "inspect";
          _state.selectedLoopId = activeId;
          _state.handoffId = null;
          _state.generation++;
          refreshSidebarAndMain();
        });
      } else {
        errorEl.textContent = result.error || "Failed to create loop.";
        errorEl.style.display = "block";
      }
      return;
    }

    // Success — transition to handoff
    var newLoopId = result.loop_id;
    _state.mode = "handoff";
    _state.handoffId = newLoopId;
    _state.selectedLoopId = newLoopId;
    _state.generation++;
    refreshSidebarAndMain();
  }

  // ── Module 4: Participant handoff ──────────────────────────────────────────

  function renderHandoff(container) {
    var mainEl = container.querySelector("#loop-main-content");
    if (!mainEl) return;

    var loopId = _state.handoffId;

    var html = '<div class="loop-handoff">'
      + '<h3 class="loop-handoff-title">Loop created</h3>'
      + '<div class="loop-handoff-subtitle" id="loop-handoff-status">Starting…</div>';

    // Draftor card
    html += '<div class="loop-handoff-card">'
      + '<div class="loop-handoff-card-header">'
      + '<span class="loop-handoff-role">1. Draftor</span>'
      + '<span class="loop-handoff-join" id="loop-handoff-draftor-join">Waiting to join</span>'
      + '</div>'
      + '<button class="loop-handoff-copy" data-role="draftor">Copy Draftor entry prompt</button>'
      + '</div>';

    // Reviewer card
    html += '<div class="loop-handoff-card">'
      + '<div class="loop-handoff-card-header">'
      + '<span class="loop-handoff-role">2. Reviewer</span>'
      + '<span class="loop-handoff-join" id="loop-handoff-reviewer-join">Waiting to join</span>'
      + '</div>'
      + '<button class="loop-handoff-copy" data-role="reviewer">Copy Reviewer entry prompt</button>'
      + '</div>';

    // Security guidance
    html += '<div class="loop-handoff-guidance">'
      + 'The copied prompt carries a role credential. Paste only into the intended participant session.'
      + '</div>';

    // Open loop workspace
    html += '<button class="loop-handoff-open" id="loop-handoff-open">Open loop workspace &rarr;</button>';

    html += '</div>';
    mainEl.innerHTML = html;

    // Wire copy buttons
    mainEl.querySelectorAll(".loop-handoff-copy").forEach(function (btn) {
      btn.addEventListener("click", function () {
        copyPrompt(loopId, btn.dataset.role, btn);
      });
    });

    // Wire Open loop workspace
    var openBtn = mainEl.querySelector("#loop-handoff-open");
    openBtn.addEventListener("click", function () {
      _state.mode = "inspect";
      _state.handoffId = null;
      _state.generation++;
      renderLoopSidebar(_state.loops, container);
      loadSelectedLoop();
    });

    // Start polling for join state
    updateHandoffStatus(container);
  }

  async function copyPrompt(loopId, role, btn) {
    var origText = btn.textContent;
    var epoch = _state.promptEpoch;
    btn.disabled = true;
    btn.textContent = "Fetching…";

    var promptText = await fetchPrompt(loopId, role);

    // Race guard: loop became terminal while fetch was in flight
    if (epoch !== _state.promptEpoch) {
      promptText = null;
      btn.disabled = true;
      btn.textContent = "Loop ended";
      return;
    }

    if (!promptText) {
      btn.textContent = "Failed";
      setTimeout(function () {
        btn.textContent = origText;
        btn.disabled = false;
      }, 2000);
      return;
    }

    if (navigator.clipboard && navigator.clipboard.writeText) {
      try {
        if (epoch !== _state.promptEpoch) {
          promptText = null;
          btn.disabled = true;
          btn.textContent = "Loop ended";
          return;
        }
        await navigator.clipboard.writeText(promptText);
        promptText = null;
        btn.textContent = "Copied";
        btn.disabled = false;
        setTimeout(function () { btn.textContent = origText; }, 2000);
      } catch (e) {
        if (epoch !== _state.promptEpoch) {
          promptText = null;
          btn.disabled = true;
          btn.textContent = "Loop ended";
          return;
        }
        showPromptFallback(promptText, btn);
        promptText = null;
      }
    } else {
      if (epoch !== _state.promptEpoch) {
        promptText = null;
        btn.disabled = true;
        btn.textContent = "Loop ended";
        return;
      }
      showPromptFallback(promptText, btn);
      promptText = null;
    }
  }

  function showPromptFallback(text, btn) {
    var existing = btn.parentNode.querySelector(".loop-handoff-fallback");
    if (existing) existing.remove();
    var fb = document.createElement("div");
    fb.className = "loop-handoff-fallback";
    fb.innerHTML = '<textarea class="loop-handoff-fallback-text" readonly rows="6"></textarea>'
      + '<div class="loop-handoff-fallback-hint">Select all and copy manually.</div>'
      + '<button class="loop-handoff-fallback-dismiss">Dismiss</button>';
    fb.querySelector("textarea").value = text;
    btn.parentNode.appendChild(fb);
    fb.querySelector("textarea").select();
    fb.querySelector(".loop-handoff-fallback-dismiss").addEventListener("click", function () {
      fb.remove();
    });
    btn.textContent = "Copy " + btn.dataset.role.charAt(0).toUpperCase()
      + btn.dataset.role.slice(1) + " entry prompt";
    btn.disabled = false;
  }

  async function updateHandoffStatus(container) {
    if (_state.mode !== "handoff" || !_state.handoffId) return;
    var gen = _state.generation;
    var loopId = _state.handoffId;

    var status = await fetchStatus(loopId);
    if (gen !== _state.generation) return;
    if (!status) return;

    var s = status.status || {};
    var roles = status.roles || {};
    var feature = status.feature || loopId;

    var subtitle = container.querySelector("#loop-handoff-status");
    if (subtitle) {
      subtitle.textContent = escHtml(feature)
        + " — " + (STAGE_LABELS[s.stage] || s.stage)
        + " — round " + (s.round || 0) + " of " + (s.max_rounds || 0);
    }

    var draftorJoin = container.querySelector("#loop-handoff-draftor-join");
    if (draftorJoin) {
      draftorJoin.textContent = (roles.draftor && roles.draftor.joined) ? "Joined" : "Waiting to join";
      draftorJoin.className = "loop-handoff-join" + ((roles.draftor && roles.draftor.joined) ? " loop-handoff-joined" : "");
    }
    var reviewerJoin = container.querySelector("#loop-handoff-reviewer-join");
    if (reviewerJoin) {
      reviewerJoin.textContent = (roles.reviewer && roles.reviewer.joined) ? "Joined" : "Waiting to join";
      reviewerJoin.className = "loop-handoff-join" + ((roles.reviewer && roles.reviewer.joined) ? " loop-handoff-joined" : "");
    }

    // Terminal during handoff: disable copy buttons, show outcome,
    // refresh sidebar once, stop polling. Architect navigates explicitly.
    if (isTerminal(s.stage)) {
      _state.promptEpoch++;
      var copyBtns = container.querySelectorAll(".loop-handoff-copy");
      copyBtns.forEach(function (btn) {
        btn.disabled = true;
        btn.textContent = "Loop ended";
      });
      // Remove any open fallback textareas
      var fallbacks = container.querySelectorAll(".loop-handoff-fallback");
      fallbacks.forEach(function (fb) { fb.remove(); });

      var outcomeLabel = OUTCOME_LABELS[s.stage] || s.stage;
      var subtitle2 = container.querySelector("#loop-handoff-status");
      if (subtitle2) {
        subtitle2.innerHTML = escHtml(feature)
          + ' — <span class="loop-badge loop-badge-outcome">'
          + escHtml(outcomeLabel) + '</span>';
      }

      if (_state.timerId) {
        clearInterval(_state.timerId);
        _state.timerId = null;
      }
      var ws = _state.container && _state.container.querySelector(".loop-workspace");
      if (ws) ws.dataset.polling = "0";
      refreshSidebarOnly();
    }
  }

  // ── Module 5: Live vs history workspace ────────────────────────────────────

  function pendingDecision(status) {
    var decisions = (status && status.decisions) || [];
    var pending = null;
    for (var i = 0; i < decisions.length; i++) {
      if (!decisions[i].response) {
        pending = decisions[i];
      }
    }
    return pending;
  }

  function collectArtifactPaths(events, decisions) {
    var seen = {};
    var paths = [];
    function add(p) {
      if (p && !seen[p]) { seen[p] = true; paths.push(p); }
    }
    for (var i = 0; i < events.length; i++) {
      if (events[i].artifact_path) add(events[i].artifact_path);
    }
    for (var d = 0; d < (decisions || []).length; d++) {
      var req = decisions[d].request;
      if (req && req.artifact_path) add(req.artifact_path);
      var resp = decisions[d].response;
      if (resp && resp.artifact_path) add(resp.artifact_path);
    }
    return paths;
  }

  // ── incremental selected-loop rendering (#38) ─────────────────────────────
  //
  // The selected-loop panel is built once per selection (a stable skeleton of
  // named regions) and then patched per region on each poll:
  //   1. `_state.render` snapshot — root node + per-region fingerprints +
  //      timeline cursor. Keyed to `_state.generation`, so any selection,
  //      mount, or mode change rebuilds the skeleton.
  //   2. A region is rewritten only when its fingerprint changes; an
  //      unchanged poll performs no main-panel DOM writes except the
  //      countdown text (patched only when its text differs).
  //   3. Timeline appends strictly-new events; artifacts reconcile by name,
  //      preserving expanded/loaded sections.
  // Fingerprints come from returned data only, never wall-clock time.

  function eventKey(ev) {
    return [ev.ts || "", ev.event || ev.type || "",
            ev.round === undefined ? "" : ev.round].join("|");
  }

  function headerFingerprint(status, terminal) {
    var s = status.status || {};
    var roles = status.roles || {};
    return JSON.stringify([
      terminal, s.stage, s.round, s.max_rounds, s.next_role, s.blocked,
      s.last_updated, s.turn_deadline, status.feature, status.loop_id,
      status.created_at,
      !!(roles.draftor && roles.draftor.joined),
      !!(roles.reviewer && roles.reviewer.joined),
    ]);
  }

  function blockedFingerprint(status) {
    var s = status.status || {};
    var pd = pendingDecision(status);
    return JSON.stringify([
      !!s.blocked, s.escalation_reason || null,
      pd ? pd.id : null,
      pd && pd.request ? pd.request.artifact_path || null : null,
    ]);
  }

  function controlsFingerprint(status, terminal) {
    // Only inputs renderControls() actually reads: which buttons exist
    // (including the max-rounds Continue control, #39), whether unblock
    // needs a response, and the turn-window default.
    var s = status.status || {};
    var pd = pendingDecision(status);
    return JSON.stringify([
      terminal, !!PAUSED_STAGES[s.stage || ""], s.stage === EXTENDABLE_STAGE,
      pd ? pd.id : null, s.turn_timeout_seconds || null,
    ]);
  }

  function artifactsFingerprint(status, events) {
    var decisions = (status && status.decisions) || [];
    var n = events.length;
    return JSON.stringify([
      n, n ? eventKey(events[n - 1]) : null,
      collectArtifactPaths([], decisions),
    ]);
  }

  function patchRegion(snap, name, fingerprint, render) {
    if (snap.fp[name] === fingerprint) return false;
    render();
    snap.fp[name] = fingerprint;
    return true;
  }

  function buildLoopSkeleton(mainEl) {
    mainEl.innerHTML = '<div class="loop-detail">'
      + '<div id="loop-region-header"></div>'
      + '<div id="loop-region-blocked"></div>'
      + '<div id="loop-region-prompts"></div>'
      + '<div id="loop-region-notice"></div>'
      + '<div id="loop-region-liveness"></div>'
      + '<div id="loop-controls"></div>'
      + '<div class="section-title" style="margin-top:20px;">Timeline</div>'
      + '<div id="loop-timeline"></div>'
      + '<div id="loop-artifacts"></div>'
      + '</div>';
    return {
      generation: _state.generation,
      loopId: _state.selectedLoopId,
      root: mainEl.querySelector(".loop-detail"),
      fp: {},
      eventCount: 0,
      lastEventKey: null,
      timelineRendered: false,
      liveness: { built: false, actionFp: {}, lastView: null, lastGood: false },
    };
  }

  function renderSelectedLoop(status, events, container) {
    var mainEl = container.querySelector("#loop-main-content");
    if (!mainEl) return;
    if (!status) {
      _state.render = null;
      mainEl.innerHTML = '<div class="muted" style="padding:24px;text-align:center;">'
        + 'Select a loop to view details.</div>';
      return;
    }
    events = events || [];

    var snap = _state.render;
    if (!snap || snap.generation !== _state.generation
        || snap.loopId !== _state.selectedLoopId
        || !snap.root || !snap.root.isConnected) {
      snap = _state.render = buildLoopSkeleton(mainEl);
    }
    var root = snap.root;
    var firstRender = !snap.timelineRendered;

    var s = status.status || {};
    var terminal = isTerminal(s.stage || "");

    patchRegion(snap, "header", headerFingerprint(status, terminal), function () {
      root.querySelector("#loop-region-header").innerHTML =
        terminal ? renderOutcomeHeader(status) : renderLiveHeader(status);
    });
    if (!terminal) updateTimeRemaining(root, s);

    patchRegion(snap, "blocked", blockedFingerprint(status), function () {
      renderBlockedCard(status, root, container);
    });

    patchRegion(snap, "prompts", terminal ? "terminal" : "live", function () {
      renderPromptSection(terminal, root);
    });

    patchRegion(snap, "controls", controlsFingerprint(status, terminal), function () {
      renderControls(status, root);
    });

    updateTimeline(snap, events, root);

    patchRegion(snap, "artifacts", artifactsFingerprint(status, events), function () {
      renderArtifacts(status, events, root, !firstRender);
    });
  }

  function renderBlockedCard(status, root, container) {
    var region = root.querySelector("#loop-region-blocked");
    var s = status.status || {};
    if (!(s.blocked && s.escalation_reason)) {
      region.innerHTML = "";
      return;
    }
    var pd = pendingDecision(status);
    var html = '<div class="loop-blocked-card">'
      + '<div class="loop-blocked-title">Blocked on Architect</div>'
      + '<div class="loop-blocked-reason">' + escHtml(s.escalation_reason) + '</div>';
    if (pd && pd.request && pd.request.artifact_path) {
      html += '<a class="loop-blocked-artifact-link" data-artifact="'
        + escHtml(pd.request.artifact_path) + '" href="#">View decision request</a>';
    }
    html += '</div>';
    region.innerHTML = html;

    var blockedLink = region.querySelector(".loop-blocked-artifact-link");
    if (blockedLink) {
      blockedLink.addEventListener("click", function (e) {
        e.preventDefault();
        var target = container.querySelector(
          '.loop-artifact-section[data-artifact="' + blockedLink.dataset.artifact + '"] .loop-artifact-toggle');
        if (target) {
          target.scrollIntoView({ behavior: "smooth", block: "center" });
          target.click();
        }
      });
    }
  }

  function renderPromptSection(terminal, root) {
    var region = root.querySelector("#loop-region-prompts");
    if (terminal) {
      region.innerHTML = "";
      return;
    }
    region.innerHTML = '<div class="loop-prompt-section">'
      + '<button class="loop-prompt-copy" data-role="draftor">Copy Draftor prompt</button>'
      + '<button class="loop-prompt-copy" data-role="reviewer">Copy Reviewer prompt</button>'
      + '</div>';
    region.querySelectorAll(".loop-prompt-copy").forEach(function (btn) {
      btn.addEventListener("click", function () {
        copyPrompt(_state.selectedLoopId, btn.dataset.role, btn);
      });
    });
  }

  function timeRemainingText(s) {
    if (!s.turn_deadline) return "";
    var diffMs = new Date(s.turn_deadline) - new Date();
    if (diffMs <= 0) return "overdue";
    var mins = Math.floor(diffMs / 60000);
    var secs = Math.floor((diffMs % 60000) / 1000);
    return mins + "m " + secs + "s";
  }

  function updateTimeRemaining(root, s) {
    // Text-only patch: the countdown must never force a region rebuild.
    var el = root.querySelector(".loop-time-remaining");
    if (!el) return;
    var text = timeRemainingText(s);
    if (el.textContent !== text) el.textContent = text;
  }

  function renderLiveHeader(status) {
    var s = status.status || {};
    var stage = s.stage || "";
    var roles = status.roles || {};
    var draftorJoined = roles.draftor && roles.draftor.joined;
    var reviewerJoined = roles.reviewer && roles.reviewer.joined;

    var timeRemaining = timeRemainingText(s);

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
        + '<div class="loop-status-value loop-time-remaining">' + escHtml(timeRemaining) + '</div>'
        + '</div>';
    }
    html += '</div>';
    return html;
  }

  function renderOutcomeHeader(status) {
    var s = status.status || {};
    var stage = s.stage || "";
    var outcomeLabel = OUTCOME_LABELS[stage] || stage;

    var html = '<div class="loop-status-header">'
      + '<h3>' + escHtml(status.feature || status.loop_id || "") + '</h3>'
      + '<span class="loop-badge loop-badge-outcome">' + escHtml(outcomeLabel) + '</span>'
      + '</div>';

    html += '<div class="loop-outcome-meta">';
    if (status.created_at) {
      html += '<span>Completed: ' + escHtml(formatDate(status.created_at)) + '</span>';
    }
    html += '<span>Final round: ' + (s.round || 0) + ' / ' + (s.max_rounds || 0) + '</span>';
    html += '</div>';

    return html;
  }

  // ── architect controls ──────────────────────────────────────────────────────

  // ── continue after max rounds (#39) ────────────────────────────────────────

  // ── participant liveness panel (#36) ───────────────────────────────────
  //
  // Built once per selected loop, then patched field by field: status and
  // notification lines update via textContent; the per-role action area
  // (Re-notify button / inline reason form) is rebuilt only when its
  // eligibility changes AND no form is open, so a typed reason survives
  // polling. Every state is encoded as text + a distinct glyph + weight,
  // never hue alone.

  var LIVENESS_STATES = {
    connected:      { glyph: "●", label: "Connected" },
    stale:          { glyph: "◐", label: "Stale" },
    released:       { glyph: "◇", label: "Released — watcher exited after delivery" },
    closed:         { glyph: "■", label: "Closed — loop ended" },
    not_registered: { glyph: "○", label: "Not registered" },
  };
  var LIVENESS_KINDS = {
    "turn-ready": "Turn ready",
    "architect-block": "Paused / waiting on Architect",
    "terminal": "Loop ended",
  };
  var RENOTIFY_REFUSALS = {
    terminal: "The loop has ended; there is nothing to re-notify.",
    already_acknowledged: "The last notification was already acknowledged.",
    not_actionable: "This role has no current turn or undelivered notification.",
    rate_limited: "Re-notify was sent moments ago; wait a few seconds.",
    unavailable: "Liveness delivery is unavailable; the loop runs normally.",
  };
  var LIVENESS_FOOTNOTE = "A notification only tells a watcher it may act. "
    + "Acknowledged means received — not that the model read, worked on, "
    + "or will submit anything. A background watcher works only under a runtime "
    + "that relaunches the agent when the watcher exits (Claude Code background "
    + "tasks, open session); other participants use gator loop wait.";

  // Text and attributes are written only when they differ, and rendered
  // text comes from returned data only (absolute times, never "Ns ago"),
  // so an identical poll produces zero DOM mutations (#38).
  function setText(el, text) {
    if (el && el.textContent !== text) el.textContent = text;
  }

  function setHidden(el, hidden) {
    if (el && el.hidden !== hidden) el.hidden = hidden;
  }

  function livenessStateText(role) {
    var st = LIVENESS_STATES[role.state] || { glyph: "?", label: role.state };
    var text = st.glyph + " " + st.label;
    if (role.state === "stale" && role.last_seen_at) {
      text += " — last seen " + formatTime(role.last_seen_at);
    } else if (role.state === "connected" && role.last_seen_at) {
      text += " · seen " + formatTime(role.last_seen_at);
    }
    return text;
  }

  function livenessNoteText(role) {
    var n = role.last_notification;
    if (!n) return "No notifications yet.";
    var parts = [LIVENESS_KINDS[n.kind] || n.kind];
    if (n.created_by === "architect") parts.push("re-notified by Architect");
    parts.push("created " + formatTime(n.created_at));
    parts.push(n.delivered_at ? "delivered " + formatTime(n.delivered_at)
                              : "not delivered");
    parts.push(n.acked_at ? "acknowledged " + formatTime(n.acked_at)
                          : "not acknowledged");
    if (n.expired_reason) {
      parts.push("expired (" + (n.expired_reason === "state_changed"
        ? "loop moved on" : n.expired_reason) + ")");
    }
    if (role.pending > 1) parts.push(role.pending + " pending");
    return parts.join(" · ");
  }

  function buildLivenessPanel(region) {
    var rows = ["draftor", "reviewer"].map(function (r) {
      var name = r === "draftor" ? "Draftor" : "Reviewer";
      return '<div class="loop-liveness-row" data-role="' + r + '">'
        + '<div class="loop-liveness-line">'
        + '<span class="loop-liveness-role">' + name + '</span> '
        + '<span class="loop-liveness-state"></span></div>'
        + '<div class="loop-liveness-note"></div>'
        + '<div class="loop-liveness-action" data-open="0"></div>'
        + '</div>';
    }).join("");
    region.innerHTML = '<div class="loop-liveness">'
      + '<div class="section-title" style="margin-top:16px;">Participant watchers</div>'
      + '<div class="loop-liveness-degraded" hidden></div>'
      + '<div class="loop-liveness-rows">' + rows + '</div>'
      + '<div class="loop-liveness-footnote"></div>'
      + '</div>';
    setText(region.querySelector(".loop-liveness-footnote"), LIVENESS_FOOTNOTE);
  }

  function showLivenessNotice(root, text, isError) {
    var region = root && root.querySelector("#loop-region-notice");
    if (!region) return;
    region.innerHTML = '<div class="loop-liveness-notice'
      + (isError ? ' loop-liveness-notice-error' : '') + '">'
      + (isError ? '<strong>Re-notify not sent:</strong> '
                 : '<strong>Re-notify sent:</strong> ')
      + escHtml(text) + '</div>';
  }

  function renderRenotifyAction(action, role, eligible, snap) {
    action.innerHTML = "";
    if (!eligible) return;
    var btn = document.createElement("button");
    btn.className = "loop-ctrl-btn loop-liveness-renotify";
    btn.type = "button";
    btn.textContent = "Re-notify";
    btn.addEventListener("click", function () { openRenotifyForm(action, role, snap); });
    action.appendChild(btn);
  }

  function openRenotifyForm(action, role, snap) {
    action.dataset.open = "1";
    var roleName = role === "draftor" ? "Draftor" : "Reviewer";
    action.innerHTML = '<div class="loop-liveness-form">'
      + '<label class="loop-ctrl-label">Reason for re-notifying the ' + roleName
      + ' (optional)</label>'
      + '<input class="loop-ctrl-input loop-liveness-reason" type="text" maxlength="200">'
      + '<div class="loop-ctrl-actions">'
      + '<button type="button" class="loop-ctrl-btn loop-liveness-send">Send re-notify</button>'
      + '<button type="button" class="loop-ctrl-btn loop-liveness-cancel">Cancel</button>'
      + '</div></div>';
    var loopId = snap.loopId;
    function close() {
      action.dataset.open = "0";
      // Force a rebuild from the latest view on the next patch.
      delete snap.liveness.actionFp[role];
      if (snap.liveness.lastView) applyLiveness(snap, snap.liveness.lastView);
    }
    action.querySelector(".loop-liveness-cancel").addEventListener("click", close);
    var send = action.querySelector(".loop-liveness-send");
    send.addEventListener("click", function () {
      send.disabled = true;
      var reason = action.querySelector(".loop-liveness-reason").value.trim();
      var gen = _state.generation;
      postRenotify(loopId, role, reason).then(function (result) {
        if (gen !== _state.generation || _state.render !== snap) return;
        if (result._failed) {
          showLivenessNotice(snap.root, RENOTIFY_REFUSALS[result.code]
            || result.error, true);
          send.disabled = false;
          return;
        }
        showLivenessNotice(snap.root, roleName + " was sent a new “"
          + (LIVENESS_KINDS[result.kind] || result.kind)
          + "” notification. This does not change the loop or prove any work.",
          false);
        close();
        refreshLiveness(snap);
      });
    });
  }

  function applyLiveness(snap, view) {
    var root = snap.root;
    var region = root && root.querySelector("#loop-region-liveness");
    if (!region || !view) return;
    var L = snap.liveness;
    if (!L.built) {
      buildLivenessPanel(region);
      L.built = true;
    }
    var degradedEl = region.querySelector(".loop-liveness-degraded");
    var rowsEl = region.querySelector(".loop-liveness-rows");

    if (view._error !== undefined || view.available === false) {
      var msg;
      if (view._error === 403 || view._error === 404) {
        msg = "Liveness unavailable for this loop (no Architect authority "
          + "on record). The loop runs normally; participants use gator loop wait.";
      } else if (view.degraded === "retry" && L.lastGood) {
        return;  // transient: keep showing the last good view
      } else {
        msg = "Delivery unavailable — the loop runs normally; "
          + "participants use gator loop wait.";
      }
      setText(degradedEl, msg);
      setHidden(degradedEl, false);
      setHidden(rowsEl, true);
      return;
    }
    L.lastGood = true;
    L.lastView = view;
    setHidden(rowsEl, false);
    if (view.degraded === "corrupt") {
      setText(degradedEl, "Liveness record unreadable; delivery degraded. "
        + "The loop runs normally.");
      setHidden(degradedEl, false);
    } else {
      setHidden(degradedEl, true);
    }

    ["draftor", "reviewer"].forEach(function (r) {
      var role = (view.roles || {})[r];
      var row = region.querySelector('.loop-liveness-row[data-role="' + r + '"]');
      if (!role || !row) return;
      var stateEl = row.querySelector(".loop-liveness-state");
      setText(stateEl, livenessStateText(role));
      if (stateEl.dataset.state !== role.state) stateEl.dataset.state = role.state;
      setText(row.querySelector(".loop-liveness-note"), livenessNoteText(role));
      var action = row.querySelector(".loop-liveness-action");
      var fp = String(!!role.renotify_eligible);
      if (action.dataset.open !== "1" && L.actionFp[r] !== fp) {
        renderRenotifyAction(action, r, !!role.renotify_eligible, snap);
        L.actionFp[r] = fp;
      }
    });
  }

  async function refreshLiveness(snap) {
    snap = snap || _state.render;
    if (!snap || !snap.loopId) return;
    var gen = _state.generation;
    var loopId = snap.loopId;
    var view = await fetchLiveness(loopId);
    if (gen !== _state.generation || _state.render !== snap
        || snap.loopId !== loopId) return;
    applyLiveness(snap, view);
  }

  function ensurePolling() {
    // Polling stops when a loop turns terminal; an extension makes it live
    // again, so the view must resume polling.
    if (!_state.timerId) {
      _state.timerId = setInterval(pollLoop, POLL_INTERVAL_MS);
    }
    var ws = _state.container && _state.container.querySelector(".loop-workspace");
    if (ws) ws.dataset.polling = "1";
  }

  function showExtendNotice(root, data) {
    // Lives in #loop-region-notice, which incremental rendering never
    // patches, so it survives the terminal-to-live region updates.
    var region = root && root.querySelector("#loop-region-notice");
    if (!region) return;
    var html = '<div class="loop-extend-notice">'
      + '<div class="loop-extend-notice-text">Extended: max rounds '
      + escHtml(String(data.previous_max_rounds)) + ' → '
      + escHtml(String(data.max_rounds))
      + '. Give the Draftor and Reviewer fresh join prompts to re-engage them.</div>';
    if (data.watcher === "failed") {
      html += '<div class="loop-extend-warning"><strong>Warning:</strong> '
        + 'Turn timeouts are not being enforced. '
        + escHtml(data.watcher_detail || "The watcher could not attach.") + '</div>';
    } else if (data.watcher === "already_hosted") {
      html += '<div class="loop-extend-hosted">Hosted by an existing watcher ('
        + escHtml(data.watcher_detail || "host.lock held") + ').</div>';
    }
    html += '</div>';
    region.innerHTML = html;
  }

  function renderContinueControl(panel, loopId, parentEl) {
    panel.innerHTML = '<div class="loop-controls-bar">'
      + '<button class="loop-ctrl-btn loop-ctrl-continue" data-action="continue">Continue loop</button>'
      + '</div>'
      + '<div class="loop-ctrl-input-area loop-continue-area" style="display:none;">'
      + '<label class="loop-ctrl-timeout-label">Additional rounds '
      + '<input type="number" class="loop-ctrl-timeout loop-continue-rounds" min="' + ROUNDS_MIN
      + '" max="' + ROUNDS_MAX + '" step="1" value="2">'
      + '</label>'
      + '<label class="loop-ctrl-label">Reason (required)</label>'
      + '<input type="text" class="loop-ctrl-input loop-continue-reason" '
      + 'placeholder="Why continue? Shown to the Draftor">'
      + '<button class="loop-ctrl-confirm">Confirm</button>'
      + '<button class="loop-ctrl-cancel">Cancel</button>'
      + '</div>';

    var area = panel.querySelector(".loop-continue-area");
    var roundsInput = panel.querySelector(".loop-continue-rounds");
    var reasonInput = panel.querySelector(".loop-continue-reason");
    var confirmBtn = panel.querySelector(".loop-ctrl-confirm");

    function clearError() {
      var el = panel.querySelector(".loop-ctrl-error");
      if (el) el.remove();
    }
    function showError(text) {
      var el = panel.querySelector(".loop-ctrl-error");
      if (!el) {
        el = document.createElement("div");
        el.className = "loop-ctrl-error";
        area.parentNode.insertBefore(el, area.nextSibling);
      }
      el.textContent = text;
    }
    function syncConfirm() {
      confirmBtn.disabled = !reasonInput.value.trim();
    }

    panel.querySelector(".loop-ctrl-continue").addEventListener("click", function () {
      clearError();
      roundsInput.value = "2";
      reasonInput.value = "";
      roundsInput.classList.remove("loop-ctrl-input-error");
      reasonInput.classList.remove("loop-ctrl-input-error");
      area.style.display = "flex";
      syncConfirm();
    });

    panel.querySelector(".loop-ctrl-cancel").addEventListener("click", function () {
      clearError();
      area.style.display = "none";
    });

    confirmBtn.addEventListener("click", function () {
      var reason = reasonInput.value.trim();
      if (!reason) {
        reasonInput.classList.add("loop-ctrl-input-error");
        showError("A reason is required to continue the loop.");
        return;
      }
      var raw = roundsInput.value.trim();
      var rounds = Number(raw);
      if (!/^\d+$/.test(raw) || rounds < ROUNDS_MIN || rounds > ROUNDS_MAX) {
        roundsInput.classList.add("loop-ctrl-input-error");
        showError("Additional rounds must be a whole number between "
          + ROUNDS_MIN + " and " + ROUNDS_MAX + ".");
        return;
      }
      confirmBtn.disabled = true;
      postAction(loopId, "extend", { rounds: rounds, message: reason }).then(function (result) {
        if (result && result._failed) {
          showError(result.error || "Could not continue the loop.");
          syncConfirm();
          return;
        }
        area.style.display = "none";
        var root = parentEl && parentEl.closest ? parentEl.closest(".loop-detail") || parentEl : parentEl;
        showExtendNotice(root, result);
        ensurePolling();
        refreshSidebarOnly();
        loadSelectedLoop();
      });
    });

    reasonInput.addEventListener("input", function () {
      reasonInput.classList.remove("loop-ctrl-input-error");
      syncConfirm();
    });
    roundsInput.addEventListener("input", function () {
      roundsInput.classList.remove("loop-ctrl-input-error");
    });
  }

  function renderControls(status, parentEl) {
    var panel = parentEl.querySelector("#loop-controls");
    if (!panel) return;

    if (!status || !_state.selectedLoopId) {
      panel.innerHTML = "";
      return;
    }

    var s = status.status || {};
    var stage = s.stage || "";
    var loopId = _state.selectedLoopId;

    if (isTerminal(stage)) {
      if (stage === EXTENDABLE_STAGE) {
        renderContinueControl(panel, loopId, parentEl);
      } else {
        panel.innerHTML = "";
      }
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

    // An escalation leaves a pending decision; an ordinary Architect pause
    // does not. Only the former requires a response to unblock.
    var pd = pendingDecision(status);
    var currentTimeout = s.turn_timeout_seconds || 300;

    html += '</div>';
    html += '<div class="loop-ctrl-input-area" style="display:none;">'
      + '<label class="loop-ctrl-label"></label>'
      + '<input type="text" class="loop-ctrl-input" placeholder="Message (optional)">'
      + '<label class="loop-ctrl-timeout-label" style="display:none;">Turn window (s) '
      + '<input type="number" class="loop-ctrl-timeout" min="' + TURN_TIMEOUT_MIN
      + '" max="' + TURN_TIMEOUT_MAX + '" step="1" value="' + escHtml(String(currentTimeout)) + '">'
      + '</label>'
      + '<button class="loop-ctrl-confirm">Confirm</button>'
      + '<button class="loop-ctrl-cancel">Cancel</button>'
      + '</div>';
    panel.innerHTML = html;

    var inputArea = panel.querySelector(".loop-ctrl-input-area");
    var input = panel.querySelector(".loop-ctrl-input");
    var label = panel.querySelector(".loop-ctrl-label");
    var timeoutLabel = panel.querySelector(".loop-ctrl-timeout-label");
    var timeoutInput = panel.querySelector(".loop-ctrl-timeout");
    var confirmBtn = panel.querySelector(".loop-ctrl-confirm");
    var pendingAction = null;
    var responseRequired = false;

    function syncConfirmEnabled() {
      confirmBtn.disabled = responseRequired && !input.value.trim();
    }

    function showInput(action, labelText, placeholder, required) {
      pendingAction = action;
      responseRequired = required;
      label.textContent = labelText;
      input.placeholder = placeholder;
      input.value = "";
      input.classList.remove("loop-ctrl-input-error");
      timeoutLabel.style.display = action === "unblock" ? "" : "none";
      timeoutInput.value = String(currentTimeout);
      timeoutInput.classList.remove("loop-ctrl-input-error");
      inputArea.style.display = "flex";
      syncConfirmEnabled();
    }

    function showCtrlError(text) {
      var errEl = panel.querySelector(".loop-ctrl-error");
      if (!errEl) {
        errEl = document.createElement("div");
        errEl.className = "loop-ctrl-error";
        inputArea.parentNode.insertBefore(errEl, inputArea.nextSibling);
      }
      errEl.textContent = text;
    }

    function clearCtrlError() {
      var el = panel.querySelector(".loop-ctrl-error");
      if (el) el.remove();
    }

    panel.querySelectorAll(".loop-ctrl-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        clearCtrlError();
        var action = btn.dataset.action;
        if (action === "interject") {
          showInput(action, "", "Message (required)", false);
        } else if (action === "pause") {
          showInput(action, "", "Message (optional)", false);
        } else if (action === "unblock") {
          if (pd) {
            showInput(action, "Response to participant (required)",
              "Answer the escalation (" + pd.id + ")", true);
          } else {
            showInput(action, "Message (optional)", "Message (optional)", false);
          }
        } else if (action === "end") {
          showInput(action, "", "Reason (optional)", false);
        }
      });
    });

    panel.querySelector(".loop-ctrl-cancel").addEventListener("click", function () {
      clearCtrlError();
      inputArea.style.display = "none";
      pendingAction = null;
      responseRequired = false;
    });

    confirmBtn.addEventListener("click", function () {
      if (!pendingAction) return;
      var action = pendingAction;
      var msg = input.value.trim();

      if ((action === "interject" || responseRequired) && !msg) {
        input.classList.add("loop-ctrl-input-error");
        showCtrlError(responseRequired
          ? "A response is required to resolve the escalation."
          : "A message is required.");
        return;
      }

      var body = {};
      if (action === "end") {
        if (msg) body.reason = msg;
      } else {
        if (msg) body.message = msg;
      }

      if (action === "unblock") {
        var raw = timeoutInput.value.trim();
        var t = Number(raw);
        if (!/^\d+$/.test(raw) || t < TURN_TIMEOUT_MIN || t > TURN_TIMEOUT_MAX) {
          timeoutInput.classList.add("loop-ctrl-input-error");
          showCtrlError("Turn window must be a whole number of seconds between "
            + TURN_TIMEOUT_MIN + " and " + TURN_TIMEOUT_MAX + ".");
          return;
        }
        if (t !== currentTimeout) body.timeout = t;
      }

      postAction(loopId, action, body).then(function (result) {
        if (result && result._failed) {
          showCtrlError(result.error || "Action failed");
          return;
        }
        inputArea.style.display = "none";
        pendingAction = null;
        responseRequired = false;
        loadSelectedLoop();
      });
    });

    input.addEventListener("input", function () {
      input.classList.remove("loop-ctrl-input-error");
      syncConfirmEnabled();
    });
    timeoutInput.addEventListener("input", function () {
      timeoutInput.classList.remove("loop-ctrl-input-error");
    });
  }

  // ── rendering: event timeline ──────────────────────────────────────────────

  function eventCardHtml(ev) {
    var eventType = ev.event || ev.type || "unknown";
    var label = EVENT_LABELS[eventType] || eventType;
    var isTerminalEv = !!TERMINAL_STAGES[eventType];
    var artifact = ev.artifact_path || null;

    var detail = "";
    if (ev.round !== undefined) detail = "round " + ev.round;
    if (ev.role) detail = ev.role;
    if (ev.detail) detail = ev.detail;
    if (ev.reason) detail = ev.reason;

    var html = '<div class="loop-event' + (isTerminalEv ? " loop-event-terminal" : "") + '"'
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
    return html;
  }

  function updateTimeline(snap, events, root) {
    // Returns true when the timeline changed. Appends strictly-new events
    // when the previously rendered tail is still the same event; otherwise
    // redraws only the timeline container.
    var n = events.length;
    var lastKey = n ? eventKey(events[n - 1]) : null;
    if (snap.timelineRendered && snap.eventCount === n && snap.lastEventKey === lastKey) {
      return false;
    }
    var timeline = root.querySelector("#loop-timeline");
    var canAppend = snap.timelineRendered && snap.eventCount > 0
      && n > snap.eventCount
      && eventKey(events[snap.eventCount - 1]) === snap.lastEventKey;
    if (canAppend && timeline) {
      var before = timeline.children.length;
      var html = "";
      for (var i = snap.eventCount; i < n; i++) html += eventCardHtml(events[i]);
      timeline.insertAdjacentHTML("beforeend", html);
      var added = Array.prototype.slice.call(timeline.children, before);
      wireTimelineCards(added, root);
    } else {
      renderTimeline(events, root);
    }
    snap.eventCount = n;
    snap.lastEventKey = lastKey;
    snap.timelineRendered = true;
    return true;
  }

  function renderTimeline(events, parentEl) {
    var timeline = parentEl.querySelector("#loop-timeline");
    if (!timeline) return;

    if (!events.length) {
      timeline.innerHTML = '<div class="muted" style="padding:12px;">No events yet.</div>';
      return;
    }

    var html = "";
    for (var i = 0; i < events.length; i++) html += eventCardHtml(events[i]);
    timeline.innerHTML = html;
    wireTimelineCards(Array.prototype.slice.call(timeline.children), parentEl);
  }

  function wireTimelineCards(cards, parentEl) {
    var clickGen = _state.generation;
    var clickLoopId = _state.selectedLoopId;
    cards.forEach(function (card) {
      if (!card.matches || !card.matches(".loop-event[data-artifact]")) return;
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
            var target = parentEl.querySelector(
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

  // Current artifacts are overwritten in place by each submission; their
  // loaded content/summaries are refreshed when the event log advances.
  var MUTABLE_ARTIFACTS = ["plan.current.md", "findings.current.md"];

  function isSummaryArtifact(name) {
    return name.indexOf("plan.") === 0 || name.indexOf("findings.") === 0;
  }

  // Per-node request revisions: every summary/body fetch bumps its node's
  // revision, and a completion is applied only if it is still the latest
  // for that node. Without this, an older in-flight fetch of a mutable
  // artifact (plan.current.md / findings.current.md) that resolves after a
  // newer one would overwrite fresh content with stale content.
  function nextRequestRev(node, key) {
    node[key] = (node[key] || 0) + 1;
    return node[key];
  }

  function loadArtifactSummary(section) {
    var filename = section.dataset.artifact;
    var clickGen = _state.generation;
    var clickLoopId = _state.selectedLoopId;
    var rev = nextRequestRev(section, "_gatorSummaryRev");
    fetchArtifact(clickLoopId, filename).then(function (text) {
      if (clickGen !== _state.generation) return;
      if (!section.isConnected) return;
      if (section._gatorSummaryRev !== rev) return;
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
  }

  function loadArtifactContent(section, content) {
    var filename = section.dataset.artifact;
    var clickGen = _state.generation;
    var clickLoopId = _state.selectedLoopId;
    var rev = nextRequestRev(content, "_gatorContentRev");
    fetchArtifact(clickLoopId, filename).then(function (text) {
      if (clickGen !== _state.generation) return;
      if (!content.isConnected) return;
      if (content._gatorContentRev !== rev) return;
      content.dataset.loaded = "1";
      if (text === null) {
        content.innerHTML = '<div class="muted">Not available.</div>';
      } else {
        content.innerHTML = '<pre class="loop-artifact-pre">' + escHtml(text) + '</pre>';
      }
    });
  }

  function createArtifactSection(name) {
    var section = document.createElement("div");
    section.className = "loop-artifact-section";
    section.dataset.artifact = name;
    section.innerHTML = '<button class="loop-artifact-toggle">' + escHtml(name) + '</button>'
      + '<div class="loop-artifact-summary"></div>'
      + '<div class="loop-artifact-content" style="display:none;"></div>';
    var btn = section.querySelector(".loop-artifact-toggle");
    var content = section.querySelector(".loop-artifact-content");
    btn.addEventListener("click", function () {
      if (content.style.display === "none") {
        content.style.display = "block";
        if (!content.dataset.loaded) {
          content.innerHTML = '<div class="muted">Loading…</div>';
          loadArtifactContent(section, content);
        }
      } else {
        content.style.display = "none";
      }
    });
    return section;
  }

  function renderArtifacts(status, events, parentEl, refreshMutable) {
    var inspector = parentEl.querySelector("#loop-artifacts");
    if (!inspector) return;

    if (!status) {
      inspector.innerHTML = "";
      return;
    }

    // Stable current artifacts first
    var artifacts = ["sketch.md", "plan.current.md", "findings.current.md"];

    // Event-driven immutable artifacts (includes round-zero)
    var immutable = collectArtifactPaths(events || [], (status && status.decisions) || []);
    for (var i = 0; i < immutable.length; i++) {
      if (artifacts.indexOf(immutable[i]) === -1) {
        artifacts.push(immutable[i]);
      }
    }

    // Reconcile by data-artifact: existing section nodes (with their
    // expanded state and loaded content) are kept and only re-ordered.
    var title = inspector.querySelector(":scope > .section-title");
    if (!title) {
      inspector.innerHTML = '<div class="section-title">Artifacts</div>';
      title = inspector.firstChild;
    }
    var existing = {};
    inspector.querySelectorAll(":scope > .loop-artifact-section").forEach(function (sec) {
      existing[sec.dataset.artifact] = sec;
    });

    var prev = title;
    var added = [];
    for (var j = 0; j < artifacts.length; j++) {
      var name = artifacts[j];
      var section = existing[name];
      if (section) {
        delete existing[name];
      } else {
        section = createArtifactSection(name);
        added.push(section);
      }
      if (prev.nextSibling !== section) {
        inspector.insertBefore(section, prev.nextSibling);
      }
      prev = section;
    }
    Object.keys(existing).forEach(function (stale) { existing[stale].remove(); });

    added.forEach(function (sec) {
      if (isSummaryArtifact(sec.dataset.artifact)) loadArtifactSummary(sec);
    });

    if (refreshMutable) {
      MUTABLE_ARTIFACTS.forEach(function (name) {
        var sec = inspector.querySelector(
          ':scope > .loop-artifact-section[data-artifact="' + name + '"]');
        if (!sec || added.indexOf(sec) !== -1) return;
        loadArtifactSummary(sec);
        var content = sec.querySelector(".loop-artifact-content");
        if (!content) return;
        if (content.style.display === "none") {
          // Refetch on next expand, and invalidate any body fetch still in
          // flight so it cannot mark the section loaded with stale text.
          nextRequestRev(content, "_gatorContentRev");
          delete content.dataset.loaded;
        } else {
          // Expanded (loaded or still loading): a fresh fetch supersedes.
          loadArtifactContent(sec, content); // refresh in place, stays expanded
        }
      });
    }
  }

  // ── main content router ────────────────────────────────────────────────────

  function renderMainContent(container) {
    if (_state.mode === "create") {
      renderCreateWorkspace(container);
    } else if (_state.mode === "handoff") {
      renderHandoff(container);
    }
    // "inspect" is handled by loadSelectedLoop
  }

  // ── main load ──────────────────────────────────────────────────────────────

  async function loadSelectedLoop() {
    var gen = _state.generation;
    if (!_state.selectedLoopId || !_state.container) return;

    var status = await fetchStatus(_state.selectedLoopId);
    if (gen !== _state.generation) return;

    var events = await fetchEvents(_state.selectedLoopId);
    if (gen !== _state.generation) return;

    renderSelectedLoop(status, events, _state.container);
    if (status) refreshLiveness(_state.render);
  }

  async function pollLoop() {
    var gen = _state.generation;
    if (document.hidden) return;

    // In handoff mode, update join indicators
    if (_state.mode === "handoff" && _state.handoffId) {
      updateHandoffStatus(_state.container);
    }

    if (_state.mode !== "inspect" || !_state.selectedLoopId) return;

    var status = await fetchStatus(_state.selectedLoopId);
    if (gen !== _state.generation) return;
    if (!status) return;

    var stage = (status.status || {}).stage || "";

    if (isTerminal(stage)) {
      _state.promptEpoch++;
    }

    var events = await fetchEvents(_state.selectedLoopId);
    if (gen !== _state.generation) return;

    // Incremental: unchanged regions (including an open control input) are
    // not touched; see renderSelectedLoop().
    renderSelectedLoop(status, events, _state.container);
    refreshLiveness(_state.render);

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
    _state.loops = loops;
    renderLoopSidebar(loops, _state.container);
  }

  async function refreshSidebarOnly() {
    var gen = _state.generation;
    var loops = await fetchLoops();
    if (gen !== _state.generation) return;
    _state.loops = loops;
    renderLoopSidebar(loops, _state.container);
  }

  async function refreshSidebarAndMain() {
    var gen = _state.generation;
    var loops = await fetchLoops();
    if (gen !== _state.generation) return;
    _state.loops = loops;
    renderLoopSidebar(loops, _state.container);
    if (_state.mode === "inspect") {
      loadSelectedLoop();
    } else {
      renderMainContent(_state.container);
    }
  }

  // ── Module 6: Entry point + state transitions ─────────────────────────────

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
      + '<div class="loop-sidebar" id="loop-sidebar-nav">'
      +   '<div class="muted" style="padding:24px;text-align:center;">Loading…</div>'
      + '</div>'
      + '<div class="loop-main" id="loop-main-content">'
      +   '<div class="muted" style="padding:24px;text-align:center;">Select a loop to view details.</div>'
      + '</div>'
      + '</div>';

    var loops = await fetchLoops();
    if (myMount !== _state.mountId) return;
    _state.loops = loops;

    var classified = classifyLoops(loops);

    if (classified.active.length > 0) {
      // Active loop exists — select it
      _state.mode = "inspect";
      _state.selectedLoopId = classified.active[0].loop_id;
    } else {
      // No active loop — default to create
      _state.mode = "create";
      _state.selectedLoopId = null;
    }

    renderLoopSidebar(loops, container);

    if (_state.mode === "inspect") {
      await loadSelectedLoop();
      if (myMount !== _state.mountId) return;
    } else {
      renderMainContent(container);
    }

    window._gatorRepoTeardown = teardownLoopView;
    _state.timerId = setInterval(pollLoop, POLL_INTERVAL_MS);
    var ws = container.querySelector(".loop-workspace");
    if (ws) ws.dataset.polling = "1";
  };

  window.GatorViews._extractSummary = extractSummary;
})();
