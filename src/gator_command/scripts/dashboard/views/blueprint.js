/**
 * blueprint.js — Blueprints view for Gator Dashboard.
 *
 * Renders the Level 1 charter map: a canvas of charter nodes + labeled
 * edges (SVG cubic-Bezier), click-to-isolate interaction, and a right-side
 * detail panel that shows the clicked node's summary, covered files,
 * representative functions, depends-on / used-by neighbors.
 *
 * v2.11.0 Release A of the Blueprints 2.0 track. Data source:
 *   GET /api/repo/<name>/blueprint?level=1
 *
 * Endpoint returns one of two shapes:
 *   {level, generated_at, source, nodes:[...], edges:[...], canvas:{...}}
 *     — success (Gator source repo only in Release A)
 *   {level, status:"unavailable", reason:"release-b-pending", message:"..."}
 *     — every other repo in Release A; view renders an information card.
 *
 * DO NOT teach users wrong data by rendering the Gator dataset under
 * another repo's name (r2 whiteboard finding). If status === "unavailable",
 * show the message; never fall back to shipped data.
 *
 * Registration matches the shell's callable contract:
 *   window.GatorViews.blueprint = function(data, container, repoName)
 * dashboard.js::showView() clears the shared #view-slot and calls this.
 * No {init, render, cleanup} object — plain function per dashboard.js:11.
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

  // ── skeleton -------------------------------------------------------------

  function renderEmptyState(container, payload) {
    container.innerHTML = "";
    const card = document.createElement("div");
    card.className = "bp-empty-state";
    card.innerHTML =
      '<div class="bp-empty-icon">◇</div>' +
      '<h2>Blueprints for this repo aren\'t available yet</h2>' +
      '<p class="bp-empty-message">' + escHtml(payload.message || "") + '</p>' +
      '<p class="bp-empty-hint">In v2.11.0 (Release A), Blueprints ships pre-authored ' +
      'for the Gator source repo only, so you can see the surface the charter ' +
      'parser will populate. Release B lands the parser and any gatorized repo ' +
      'will get its own charter map.</p>';
    container.appendChild(card);
  }

  function renderErrorState(container, message) {
    container.innerHTML = "";
    const card = document.createElement("div");
    card.className = "bp-empty-state bp-error-state";
    card.innerHTML =
      '<div class="bp-empty-icon">!</div>' +
      '<h2>Couldn\'t load the blueprint</h2>' +
      '<p class="bp-empty-message">' + escHtml(message) + '</p>';
    container.appendChild(card);
  }

  // ── data helpers ----------------------------------------------------------

  function computeNeighborhood(activeId, edges) {
    // 1-hop in + out. `activeId` is always included.
    const set = new Set([activeId]);
    for (const e of edges) {
      if (e.from === activeId) set.add(e.to);
      if (e.to === activeId) set.add(e.from);
    }
    return set;
  }

  function outNeighbors(nodeId, nodesById, edges) {
    return edges
      .filter(e => e.from === nodeId)
      .map(e => ({ target: nodesById[e.to], label: e.label }));
  }

  function inNeighbors(nodeId, nodesById, edges) {
    return edges
      .filter(e => e.to === nodeId)
      .map(e => ({ target: nodesById[e.from], label: e.label }));
  }

  // ── SVG edge geometry -----------------------------------------------------
  // Matches the vault HTML's approach: cubic-Bezier with midpoint control
  // for gentle horizontal-ish curves. Endpoints approximate the node
  // rectangle edges, not centers.

  function edgePath(fromNode, toNode) {
    const fx = fromNode.x + 100;
    const fy = fromNode.y + 30;
    const tx = toNode.x + 100;
    const ty = toNode.y + 30;
    const mx = (fx + tx) / 2;
    return "M " + fx + " " + fy + " C " + mx + " " + fy + ", " + mx + " " + ty + ", " + tx + " " + ty;
  }

  // ── main render -----------------------------------------------------------

  function renderCanvas(container, payload) {
    const canvasSize = payload.canvas || { width: 1180, height: 880 };
    const nodes = payload.nodes || [];
    const edges = payload.edges || [];
    const nodesById = {};
    for (const n of nodes) nodesById[n.id] = n;

    container.innerHTML = "";

    const wrap = document.createElement("div");
    wrap.className = "bp-wrap";
    container.appendChild(wrap);

    // Left: canvas + edges
    const canvas = document.createElement("div");
    canvas.className = "bp-canvas";
    canvas.style.width = canvasSize.width + "px";
    canvas.style.height = canvasSize.height + "px";
    wrap.appendChild(canvas);

    // SVG for edges — full canvas overlay, pointer-events on paths only.
    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("class", "bp-edges");
    svg.setAttribute("width", String(canvasSize.width));
    svg.setAttribute("height", String(canvasSize.height));

    // Arrow marker (one, reused)
    const defs = document.createElementNS(svgNS, "defs");
    const marker = document.createElementNS(svgNS, "marker");
    marker.setAttribute("id", "bp-arrow");
    marker.setAttribute("viewBox", "0 0 10 10");
    marker.setAttribute("refX", "10");
    marker.setAttribute("refY", "5");
    marker.setAttribute("markerWidth", "8");
    marker.setAttribute("markerHeight", "8");
    marker.setAttribute("orient", "auto-start-reverse");
    const arrowPath = document.createElementNS(svgNS, "path");
    arrowPath.setAttribute("d", "M 0 0 L 10 5 L 0 10 z");
    arrowPath.setAttribute("class", "bp-arrow-head");
    marker.appendChild(arrowPath);
    defs.appendChild(marker);
    svg.appendChild(defs);

    for (let i = 0; i < edges.length; i++) {
      const e = edges[i];
      const from = nodesById[e.from];
      const to = nodesById[e.to];
      if (!from || !to) continue;
      const pathId = "bp-edge-path-" + i;
      const p = document.createElementNS(svgNS, "path");
      p.setAttribute("id", pathId);
      p.setAttribute("d", edgePath(from, to));
      p.setAttribute("class", "bp-edge");
      p.setAttribute("marker-end", "url(#bp-arrow)");
      p.dataset.from = e.from;
      p.dataset.to = e.to;
      svg.appendChild(p);

      if (e.label) {
        const text = document.createElementNS(svgNS, "text");
        text.setAttribute("class", "bp-edge-label");
        text.setAttribute("dy", "-4");
        const tp = document.createElementNS(svgNS, "textPath");
        tp.setAttributeNS("http://www.w3.org/1999/xlink", "xlink:href", "#" + pathId);
        tp.setAttribute("href", "#" + pathId);
        tp.setAttribute("startOffset", "50%");
        tp.setAttribute("text-anchor", "middle");
        tp.textContent = e.label;
        text.appendChild(tp);
        svg.appendChild(text);
      }
    }
    canvas.appendChild(svg);

    // Nodes
    for (const n of nodes) {
      const art = document.createElement("article");
      art.className = "bp-node";
      art.dataset.nodeId = n.id;
      art.style.left = n.x + "px";
      art.style.top = n.y + "px";
      if (n.color) art.style.setProperty("--bp-node-accent", n.color);
      const kind = n.kind ? '<span class="bp-node-kind">' + escHtml(n.kind) + '</span>' : "";
      art.innerHTML =
        '<div class="bp-node-title">' + escHtml(n.title || n.id) + '</div>' +
        kind;
      canvas.appendChild(art);
    }

    // Right: detail panel
    const detail = document.createElement("aside");
    detail.className = "bp-detail";
    detail.innerHTML =
      '<h3 class="bp-detail-title">Level 1: charter map</h3>' +
      '<p class="bp-detail-hint">Click any node to isolate its 1-hop neighborhood. ' +
      'Double-click the canvas (or click here) to reset.</p>' +
      '<div class="bp-detail-body" id="bp-detail-body"></div>';
    wrap.appendChild(detail);

    // Interaction
    function isolate(nodeId) {
      const set = computeNeighborhood(nodeId, edges);
      canvas.querySelectorAll(".bp-node").forEach(el => {
        const id = el.dataset.nodeId;
        el.classList.toggle("bp-active", id === nodeId);
        el.classList.toggle("bp-faded", !set.has(id));
      });
      svg.querySelectorAll(".bp-edge").forEach(p => {
        const on = p.dataset.from === nodeId || p.dataset.to === nodeId;
        p.classList.toggle("bp-active", on);
        p.classList.toggle("bp-faded", !on);
      });
      renderDetail(nodeId);
    }
    function reset() {
      canvas.querySelectorAll(".bp-node").forEach(el => {
        el.classList.remove("bp-active", "bp-faded");
      });
      svg.querySelectorAll(".bp-edge").forEach(p => {
        p.classList.remove("bp-active", "bp-faded");
      });
      const body = document.getElementById("bp-detail-body");
      if (body) body.innerHTML = "";
    }
    function renderDetail(nodeId) {
      const n = nodesById[nodeId];
      if (!n) return;
      const body = document.getElementById("bp-detail-body");
      if (!body) return;
      const parts = [];
      parts.push('<h4 class="bp-detail-node-title">' + escHtml(n.title || nodeId) + '</h4>');
      if (n.kind) parts.push('<div class="bp-detail-kind">' + escHtml(n.kind) + '</div>');
      if (n.summary) parts.push('<p class="bp-detail-summary">' + escHtml(n.summary) + '</p>');
      if (n.covers && n.covers.length) {
        parts.push('<div class="bp-detail-section-label">Covers</div><ul class="bp-detail-list">');
        for (const c of n.covers) parts.push('<li><code>' + escHtml(c) + '</code></li>');
        parts.push('</ul>');
      }
      if (n.functions && n.functions.length) {
        parts.push('<div class="bp-detail-section-label">Representative functions</div><ul class="bp-detail-list">');
        for (const f of n.functions) parts.push('<li><code>' + escHtml(f) + '</code></li>');
        parts.push('</ul>');
      }
      const outs = outNeighbors(nodeId, nodesById, edges);
      if (outs.length) {
        parts.push('<div class="bp-detail-section-label">Depends on</div><ul class="bp-detail-list">');
        for (const o of outs) parts.push('<li>' + escHtml(o.target ? o.target.title : "?") + ' <span class="muted">— ' + escHtml(o.label || "") + '</span></li>');
        parts.push('</ul>');
      }
      const ins = inNeighbors(nodeId, nodesById, edges);
      if (ins.length) {
        parts.push('<div class="bp-detail-section-label">Used by</div><ul class="bp-detail-list">');
        for (const i of ins) parts.push('<li>' + escHtml(i.target ? i.target.title : "?") + ' <span class="muted">— ' + escHtml(i.label || "") + '</span></li>');
        parts.push('</ul>');
      }
      body.innerHTML = parts.join("");
    }

    canvas.addEventListener("click", function (e) {
      const node = e.target.closest(".bp-node");
      if (node) {
        isolate(node.dataset.nodeId);
      }
    });
    canvas.addEventListener("dblclick", function (e) {
      if (!e.target.closest(".bp-node")) {
        reset();
      }
    });
    detail.querySelector(".bp-detail-hint").addEventListener("click", reset);
  }

  // ── entry point -----------------------------------------------------------

  window.GatorViews.blueprint = function (data, container, repoName) {
    container.innerHTML = '<p class="muted" style="padding:24px;">Loading blueprint…</p>';
    if (!repoName) {
      renderErrorState(container, "No repo selected.");
      return;
    }
    fetch("/api/repo/" + encodeURIComponent(repoName) + "/blueprint?level=1")
      .then(function (resp) {
        if (!resp.ok) throw new Error("Endpoint returned " + resp.status);
        return resp.json();
      })
      .then(function (payload) {
        if (payload.status === "unavailable") {
          renderEmptyState(container, payload);
          return;
        }
        if (payload.error) {
          renderErrorState(container, payload.error);
          return;
        }
        renderCanvas(container, payload);
      })
      .catch(function (err) {
        renderErrorState(container, err.message || String(err));
      });
  };
})();
