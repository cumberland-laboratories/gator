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

  function renderSelectedLoop(status, events, container) {
    var mainEl = container.querySelector("#loop-main-content");
    if (!mainEl) return;
    if (!status) {
      mainEl.innerHTML = '<div class="muted" style="padding:24px;text-align:center;">'
        + 'Select a loop to view details.</div>';
      return;
    }

    var s = status.status || {};
    var stage = s.stage || "";
    var terminal = isTerminal(stage);

    var html = '<div class="loop-detail">';

    // Status/outcome header
    if (terminal) {
      html += renderOutcomeHeader(status);
    } else {
      html += renderLiveHeader(status);
    }

    // Blocked-on-Architect card (between header and controls)
    if (s.blocked && s.escalation_reason) {
      var pd = pendingDecision(status);
      html += '<div class="loop-blocked-card">'
        + '<div class="loop-blocked-title">Blocked on Architect</div>'
        + '<div class="loop-blocked-reason">' + escHtml(s.escalation_reason) + '</div>';
      if (pd && pd.request && pd.request.artifact_path) {
        html += '<a class="loop-blocked-artifact-link" data-artifact="'
          + escHtml(pd.request.artifact_path) + '" href="#">View decision request</a>';
      }
      html += '</div>';
    }

    // Prompt copy section (active loops only)
    if (!terminal) {
      html += '<div class="loop-prompt-section">'
        + '<button class="loop-prompt-copy" data-role="draftor">Copy Draftor prompt</button>'
        + '<button class="loop-prompt-copy" data-role="reviewer">Copy Reviewer prompt</button>'
        + '</div>';
    }

    // Controls placeholder (active loops only)
    if (!terminal) {
      html += '<div id="loop-controls"></div>';
    }

    // Timeline
    html += '<div class="section-title" style="margin-top:20px;">Timeline</div>'
      + '<div id="loop-timeline"></div>';

    // Artifacts
    html += '<div id="loop-artifacts"></div>';

    html += '</div>';
    mainEl.innerHTML = html;

    // Wire blocked-card artifact link
    var blockedLink = mainEl.querySelector(".loop-blocked-artifact-link");
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

    // Wire prompt copy buttons
    mainEl.querySelectorAll(".loop-prompt-copy").forEach(function (btn) {
      btn.addEventListener("click", function () {
        copyPrompt(_state.selectedLoopId, btn.dataset.role, btn);
      });
    });

    // Render sub-sections
    if (!terminal) {
      renderControls(status, mainEl);
    }
    renderTimeline(events, mainEl);
    renderArtifacts(status, events, mainEl);
  }

  function renderLiveHeader(status) {
    var s = status.status || {};
    var stage = s.stage || "";
    var roles = status.roles || {};
    var draftorJoined = roles.draftor && roles.draftor.joined;
    var reviewerJoined = roles.reviewer && roles.reviewer.joined;

    var timeRemaining = "";
    if (s.turn_deadline) {
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

  function renderTimeline(events, parentEl) {
    var timeline = parentEl.querySelector("#loop-timeline");
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
      var artifact = ev.artifact_path || null;

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

  function renderArtifacts(status, events, parentEl) {
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

    var html = '<div class="section-title">Artifacts</div>';
    for (var j = 0; j < artifacts.length; j++) {
      var name = artifacts[j];
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

    renderSelectedLoop(status, events, _state.container);

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
