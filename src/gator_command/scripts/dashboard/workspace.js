/**
 * workspace.js — Dashboard workspace contexts (#80).
 *
 * Owns the ordered list of workspace contexts for one browser tab and its
 * session-scoped cache. A context is {id, repo, repoKey, view, sub}: an
 * optional repository and the last view to restore for it.
 *
 * It also draws the workspace strip (renderStrip) and reports clicks to
 * the shell's callbacks. It never renders a view, never calls history,
 * and never fetches: dashboard.js is the only router. The active context is a recorded copy
 * of what the shell shows (syncActive), so it is never a second authority.
 *
 * Storage: sessionStorage only (per browser tab), versioned, bounded,
 * defensively parsed. No tokens, prompts, artifact text, filesystem paths
 * or API responses. The page works when storage is blocked or corrupt.
 */

(function () {
  "use strict";

  const STORAGE_KEY = "gator.dashboard.workspace";
  const VERSION = 1;
  const MAX_CONTEXTS = 12;
  const MAX_BYTES = 16384;
  const REPO_MAX = 200;
  const LOOP_ID_MAX = 200;
  const ID_RE = /^[a-z0-9]{1,16}$/;
  const KEY_RE = /^[A-Za-z0-9_-]{1,128}$/;

  // Supplied by the shell (configure): which view names exist, and its
  // Loop sub-state cleaner.
  let isView = function () { return false; };
  let cleanSub = function () { return null; };

  const ws = { contexts: [], activeId: null, hydrated: false };

  // ── records ───────────────────────────────────────────────────────────────

  function cleanRepo(repo) {
    return typeof repo === "string" && repo.length > 0 && repo.length <= REPO_MAX
      ? repo : null;
  }

  function cleanKey(key) {
    return typeof key === "string" && KEY_RE.test(key) ? key : null;
  }

  function cleanContextSub(view, sub) {
    if (view !== "loop") return null;
    const s = cleanSub(sub);
    if (s && s.loopId !== null && s.loopId.length > LOOP_ID_MAX) s.loopId = null;
    return s;
  }

  // A stored record → a context, or null when any field is invalid.
  function sanitize(raw) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
    if (typeof raw.id !== "string" || !ID_RE.test(raw.id)) return null;
    if (!isView(raw.view)) return null;
    const repo = raw.repo === null ? null : cleanRepo(raw.repo);
    if (raw.repo !== null && repo === null) return null;
    const repoKey = raw.repoKey === null ? null : cleanKey(raw.repoKey);
    if (raw.repoKey !== null && repoKey === null) return null;
    if (repo === null && repoKey !== null) return null;
    return { id: raw.id, repo: repo, repoKey: repoKey, view: raw.view,
             sub: cleanContextSub(raw.view, raw.sub) };
  }

  function newId() {
    let id;
    do {
      id = Math.random().toString(36).slice(2, 10) || "w";
    } while (ws.contexts.some(c => c.id === id));
    return id;
  }

  // Same repository: by key when both keys are known, else by name.
  function sameRepo(ctx, repo, repoKey) {
    if (ctx.repo === null || repo === null) return false;
    if (ctx.repoKey && repoKey) return ctx.repoKey === repoKey;
    return ctx.repo === repo;
  }

  function findByRepo(repo, repoKey, exceptId) {
    return ws.contexts.find(c => c.id !== exceptId && sameRepo(c, repo, repoKey)) || null;
  }

  function byId(id) {
    return ws.contexts.find(c => c.id === id) || null;
  }

  function copy(ctx) {
    return ctx ? JSON.parse(JSON.stringify(ctx)) : null;
  }

  function assign(ctx, fields) {
    ctx.repo = cleanRepo(fields.repo);
    ctx.repoKey = ctx.repo === null ? null : cleanKey(fields.repoKey);
    ctx.view = isView(fields.view) ? fields.view : "welcome";
    ctx.sub = cleanContextSub(ctx.view, fields.sub);
  }

  // One context per repository: the active context wins over an inactive
  // duplicate.
  function dropDuplicatesOf(active) {
    if (active.repo === null) return;
    ws.contexts = ws.contexts.filter(
      c => c === active || !sameRepo(c, active.repo, active.repoKey));
  }

  // ── storage ───────────────────────────────────────────────────────────────

  // The size limit is in UTF-8 bytes, not string length: a non-ASCII
  // name or loop id takes several bytes per character. A string longer
  // than MAX_BYTES characters is over the limit without encoding it.
  function overLimit(text) {
    if (text.length > MAX_BYTES) return true;
    return new TextEncoder().encode(text).length > MAX_BYTES;
  }

  function readCache() {
    let raw;
    try {
      raw = window.sessionStorage.getItem(STORAGE_KEY);
    } catch (_) {
      return null;
    }
    if (typeof raw !== "string" || overLimit(raw)) return null;
    let data;
    try {
      data = JSON.parse(raw);
    } catch (_) {
      return null;
    }
    if (!data || typeof data !== "object" || data.v !== VERSION
        || !Array.isArray(data.contexts) || data.contexts.length > MAX_CONTEXTS) {
      return null;
    }
    const contexts = [];
    for (const record of data.contexts) {
      const ctx = sanitize(record);
      if (!ctx || contexts.some(c => c.id === ctx.id)) continue;
      if (ctx.repo !== null && contexts.some(c => sameRepo(c, ctx.repo, ctx.repoKey))) continue;
      contexts.push(ctx);
    }
    return {
      contexts: contexts,
      activeId: typeof data.activeId === "string" ? data.activeId : null,
    };
  }

  function save() {
    if (!ws.hydrated) return;
    let text;
    try {
      text = JSON.stringify({ v: VERSION, activeId: ws.activeId, contexts: ws.contexts });
    } catch (_) {
      return;
    }
    if (overLimit(text)) return;
    try {
      window.sessionStorage.setItem(STORAGE_KEY, text);
    } catch (_) { /* storage blocked or full: the page still works */ }
  }

  // ── public model ──────────────────────────────────────────────────────────

  // Record what the shell shows as the active context. A no-op until
  // load(): the landing hydration reads the cache first.
  function syncActive(fields) {
    if (!ws.hydrated) return;
    let active = byId(ws.activeId);
    if (!active) {
      active = { id: newId(), repo: null, repoKey: null, view: "welcome", sub: null };
      ws.contexts.push(active);
      ws.activeId = active.id;
    }
    assign(active, fields);
    dropDuplicatesOf(active);
    save();
  }

  // After the landing view: the shell's on-screen context becomes the
  // active one; cached contexts survive only if their repository is still
  // registered (validateRepo(repo, repoKey) → {repo, repoKey} | null).
  function load(current, validateRepo) {
    const cached = readCache() || { contexts: [], activeId: null };
    const kept = [];
    for (const ctx of cached.contexts) {
      if (ctx.repo !== null) {
        const known = validateRepo(ctx.repo, ctx.repoKey);
        if (!known) continue;
        ctx.repo = cleanRepo(known.repo);
        ctx.repoKey = cleanKey(known.repoKey);
        if (ctx.repo === null) continue;
      }
      kept.push(ctx);
    }
    ws.contexts = kept;
    const repo = cleanRepo(current.repo);
    let active = repo !== null
      ? findByRepo(repo, cleanKey(current.repoKey), null)
      : (function () {
          const prior = byId(cached.activeId);
          return prior && prior.repo === null ? prior : null;
        })();
    if (!active) {
      if (ws.contexts.length >= MAX_CONTEXTS) ws.contexts.pop();
      active = { id: newId(), repo: null, repoKey: null, view: "welcome", sub: null };
      ws.contexts.push(active);
    }
    ws.activeId = active.id;
    ws.hydrated = true;
    syncActive(current);
  }

  function list() {
    return { activeId: ws.activeId, contexts: ws.contexts.map(copy) };
  }

  // ── context operations (checkpoint 4) ─────────────────────────────────────
  //
  // These change only the list. The shell renders and records history.

  // Append a context; null at the limit.
  function create(fields) {
    if (!ws.hydrated || ws.contexts.length >= MAX_CONTEXTS) return null;
    const ctx = { id: newId(), repo: null, repoKey: null, view: "welcome", sub: null };
    assign(ctx, fields);
    ws.contexts.push(ctx);
    save();
    return copy(ctx);
  }

  // Make an existing context active; returns its copy, or null.
  function select(id) {
    const ctx = byId(id);
    if (!ctx) return null;
    ws.activeId = id;
    save();
    return copy(ctx);
  }

  // The context to show after closing `id`: right neighbour, else left.
  function neighbourOf(id) {
    const i = ws.contexts.findIndex(c => c.id === id);
    if (i < 0) return null;
    return copy(ws.contexts[i + 1] || ws.contexts[i - 1] || null);
  }

  function remove(id) {
    ws.contexts = ws.contexts.filter(c => c.id !== id);
    if (ws.activeId === id) ws.activeId = null;
    save();
  }

  // ── strip (checkpoint 4) ──────────────────────────────────────────────────
  //
  // Native buttons only; labels through textContent. Manual activation:
  // arrows / Home / End move focus, Enter / Space select (a selection
  // remounts a view and records history). Rebuilt only when what it shows
  // changes; focus inside the strip is restored across a rebuild.

  let stripPrint = null;

  function tabLabel(ctx) {
    return ctx.repo === null ? "Gator" : ctx.repo;
  }

  function closeLabel(ctx) {
    return ctx.repo === null ? "Close workspace without repository"
      : "Close " + ctx.repo + " workspace";
  }

  function el(tag, attrs, text) {
    const node = document.createElement(tag);
    for (const name in attrs) node.setAttribute(name, attrs[name]);
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function onStripKey(e) {
    const tabs = Array.from(e.currentTarget.querySelectorAll(".workspace-tab"));
    const i = tabs.indexOf(document.activeElement);
    if (i < 0) return;
    let next = -1;
    if (e.key === "ArrowRight") next = (i + 1) % tabs.length;
    else if (e.key === "ArrowLeft") next = (i - 1 + tabs.length) % tabs.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = tabs.length - 1;
    if (next < 0) return;
    e.preventDefault();
    tabs.forEach((t, j) => t.setAttribute("tabindex", j === next ? "0" : "-1"));
    tabs[next].focus();
  }

  // callbacks: {onSelect(id), onClose(id), onNew()}. Returns the active
  // tab's element id (for #app-shell's aria-labelledby), or null.
  function renderStrip(container, callbacks, opts) {
    if (!container || !ws.hydrated) return null;
    const print = JSON.stringify([ws.activeId, ws.contexts.map(c => [c.id, c.repo])]);
    const activeTabId = ws.activeId ? "ws-tab-" + ws.activeId : null;
    if (print === stripPrint && container.firstChild && !(opts && opts.force)) {
      // Unchanged strip: only honour an explicit focus request.
      if (opts && opts.focusActive) {
        const tab = container.querySelector('.workspace-tab[aria-selected="true"]');
        if (tab) tab.focus();
      }
      return activeTabId;
    }
    stripPrint = print;

    // Remember focus inside the strip: {id, kind}.
    const focused = document.activeElement;
    let restore = null;
    if (focused && container.contains(focused)) {
      restore = focused.classList.contains("workspace-new") ? { kind: "new" }
        : { kind: focused.classList.contains("workspace-tab-close") ? "close" : "tab",
            id: focused.dataset.ctx };
    }
    if (opts && opts.focusActive) restore = { kind: "tab", id: ws.activeId };

    container.textContent = "";
    const list = el("div", { role: "tablist", "aria-label": "Open workspaces",
                             class: "workspace-tablist" });
    for (const ctx of ws.contexts) {
      const active = ctx.id === ws.activeId;
      const item = el("div", { class: "workspace-item", role: "presentation" });
      const tab = el("button", {
        type: "button", class: "workspace-tab", role: "tab", id: "ws-tab-" + ctx.id,
        "aria-selected": active ? "true" : "false", "aria-controls": "app-shell",
        tabindex: active ? "0" : "-1", "data-ctx": ctx.id,
      }, ctx.repo === null ? undefined : tabLabel(ctx));
      if (ctx.repo === null) {
        // No repository: the white Gator mark, with "Gator" kept as the
        // tab's text (visually hidden) for its accessible name.
        tab.classList.add("workspace-tab-gator");
        tab.appendChild(el("img", { class: "workspace-tab-logo",
                                    src: "gator-logo.png", alt: "" }));
        tab.appendChild(el("span", { class: "workspace-tab-text" }, tabLabel(ctx)));
        tab.title = "No repository";
      }
      tab.addEventListener("click", function () { callbacks.onSelect(ctx.id); });
      const close = el("button", {
        type: "button", class: "workspace-tab-close", "aria-label": closeLabel(ctx),
        title: closeLabel(ctx), tabindex: active ? "0" : "-1", "data-ctx": ctx.id,
      }, "×");
      close.addEventListener("click", function () { callbacks.onClose(ctx.id); });
      item.appendChild(tab);
      item.appendChild(close);
      list.appendChild(item);
    }
    list.addEventListener("keydown", onStripKey);
    container.appendChild(list);

    const full = ws.contexts.length >= MAX_CONTEXTS;
    const add = el("button", { type: "button", class: "workspace-new",
                               "aria-label": "New workspace" }, "+");
    add.title = full ? "Workspace limit reached (" + MAX_CONTEXTS + ")" : "New workspace";
    add.disabled = full;
    add.addEventListener("click", function () { callbacks.onNew(); });
    container.appendChild(add);

    if (restore) {
      const target = restore.kind === "new" ? add
        : container.querySelector((restore.kind === "close" ? ".workspace-tab-close" : ".workspace-tab")
            + '[data-ctx="' + restore.id + '"]')
          || container.querySelector('.workspace-tab[aria-selected="true"]');
      if (target && !target.disabled) target.focus();
    }
    const activeTab = container.querySelector('.workspace-tab[aria-selected="true"]');
    if (activeTab && activeTab.scrollIntoView) {
      activeTab.scrollIntoView({ inline: "nearest", block: "nearest" });
    }
    return activeTabId;
  }

  window.GatorWorkspace = {
    MAX_CONTEXTS: MAX_CONTEXTS,
    configure: function (opts) {
      if (opts && typeof opts.isView === "function") isView = opts.isView;
      if (opts && typeof opts.cleanSub === "function") cleanSub = opts.cleanSub;
    },
    load: load,
    syncActive: syncActive,
    findByRepo: function (repo, repoKey) { return copy(findByRepo(repo, repoKey, null)); },
    active: function () { return copy(byId(ws.activeId)); },
    list: list,
    isHydrated: function () { return ws.hydrated; },
    create: create,
    select: select,
    neighbourOf: neighbourOf,
    remove: remove,
    count: function () { return ws.contexts.length; },
    renderStrip: renderStrip,
  };
})();
