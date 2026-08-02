/**
 * repo.js — Repo view for Gator Dashboard.
 *
 * Markdown file browser for a repo's .gator/ knowledge layer.
 * Secondary sidebar lists files, main content renders markdown.
 * Default document: pulse.md (if it exists), otherwise mission.md.
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

  // ── simple markdown renderer ──────────────────────────────────────────────
  // Handles: headers, bold, italic, links, code blocks, inline code,
  // lists, blockquotes, horizontal rules, tables. No external deps.

  function renderMarkdown(md) {
    let html = "";
    const lines = md.split("\n");
    let i = 0;
    let inCodeBlock = false;
    let codeLines = [];
    let inList = false;

    while (i < lines.length) {
      const line = lines[i];

      // Fenced code blocks
      if (line.trimStart().startsWith("```")) {
        if (inCodeBlock) {
          html += '<pre class="md-code-block">' + escHtml(codeLines.join("\n")) + "</pre>\n";
          codeLines = [];
          inCodeBlock = false;
        } else {
          if (inList) { html += "</ul>\n"; inList = false; }
          inCodeBlock = true;
        }
        i++;
        continue;
      }
      if (inCodeBlock) {
        codeLines.push(line);
        i++;
        continue;
      }

      // Blank line
      if (line.trim() === "") {
        if (inList) { html += "</ul>\n"; inList = false; }
        i++;
        continue;
      }

      // Horizontal rule
      if (/^---+$/.test(line.trim()) || /^\*\*\*+$/.test(line.trim())) {
        if (inList) { html += "</ul>\n"; inList = false; }
        html += "<hr>\n";
        i++;
        continue;
      }

      // Headers
      const hMatch = line.match(/^(#{1,6})\s+(.*)/);
      if (hMatch) {
        if (inList) { html += "</ul>\n"; inList = false; }
        const level = hMatch[1].length;
        html += `<h${level}>${inlineFormat(hMatch[2])}</h${level}>\n`;
        i++;
        continue;
      }

      // Blockquote
      if (line.startsWith(">")) {
        if (inList) { html += "</ul>\n"; inList = false; }
        const text = line.replace(/^>\s?/, "");
        html += `<blockquote class="md-blockquote">${inlineFormat(text)}</blockquote>\n`;
        i++;
        continue;
      }

      // Unordered list
      if (/^\s*[-*+]\s+/.test(line)) {
        if (!inList) { html += "<ul>\n"; inList = true; }
        const text = line.replace(/^\s*[-*+]\s+/, "");
        html += `<li>${inlineFormat(text)}</li>\n`;
        i++;
        continue;
      }

      // Ordered list
      if (/^\s*\d+\.\s+/.test(line)) {
        if (!inList) { html += "<ul>\n"; inList = true; }
        const text = line.replace(/^\s*\d+\.\s+/, "");
        html += `<li>${inlineFormat(text)}</li>\n`;
        i++;
        continue;
      }

      // Table detection
      if (line.includes("|") && i + 1 < lines.length && /^\|?\s*[-:]+/.test(lines[i + 1])) {
        if (inList) { html += "</ul>\n"; inList = false; }
        html += renderTable(lines, i);
        // Skip past table
        while (i < lines.length && lines[i].includes("|")) i++;
        continue;
      }

      // Paragraph — coalesce consecutive prose lines into a single <p> so that
      // soft-wrapped source lines flow naturally instead of stacking as narrow
      // one-line paragraphs. A source line ending in two-or-more spaces is an
      // intentional hard break (Markdown convention) and emits <br>.
      if (inList) { html += "</ul>\n"; inList = false; }
      const paraParts = [];
      while (i < lines.length) {
        const l = lines[i];
        // Stop at a blank line or the start of any non-paragraph block.
        if (l.trim() === "") break;
        if (l.trimStart().startsWith("```")) break;
        if (/^---+$/.test(l.trim()) || /^\*\*\*+$/.test(l.trim())) break;
        if (/^#{1,6}\s+/.test(l)) break;
        if (l.startsWith(">")) break;
        if (/^\s*[-*+]\s+/.test(l)) break;
        if (/^\s*\d+\.\s+/.test(l)) break;
        if (l.includes("|") && i + 1 < lines.length && /^\|?\s*[-:]+/.test(lines[i + 1])) break;
        const hardBreak = /\s{2,}$/.test(l);
        paraParts.push(inlineFormat(l) + (hardBreak ? "<br>" : ""));
        i++;
      }
      html += `<p>${paraParts.join(" ")}</p>\n`;
    }

    if (inList) html += "</ul>\n";
    if (inCodeBlock) {
      html += '<pre class="md-code-block">' + escHtml(codeLines.join("\n")) + "</pre>\n";
    }

    return html;
  }

  function inlineFormat(text) {
    // Order matters: bold before italic, links before other patterns
    let s = escHtml(text);
    // Images: ![alt](src) — must come before links
    s = s.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, function (_, alt, src) {
      // Resolve relative image paths through the file endpoint
      if (!src.startsWith("http") && window._gatorRepoContext) {
        const ctx = window._gatorRepoContext;
        let imgPath = src;
        if (ctx.currentDir && !src.startsWith("/")) {
          imgPath = ctx.currentDir + "/" + src;
        }
        imgPath = imgPath.replace(/^\.\//, "");
        // Route through binary file endpoint
        src = "/api/repo/" + encodeURIComponent(ctx.repoName) + "/raw/" + imgPath.split("/").map(encodeURIComponent).join("/");
      }
      return '<img src="' + src + '" alt="' + alt + '" style="max-width:100%;margin:8px 0">';
    });
    // Links: [text](url)
    s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
    // Bold: **text** or __text__
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/__([^_]+)__/g, "<strong>$1</strong>");
    // Italic: *text* or _text_
    s = s.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    // Inline code: `text`
    s = s.replace(/`([^`]+)`/g, '<code class="md-inline-code">$1</code>');
    return s;
  }

  function renderTable(lines, startIdx) {
    let html = '<table class="md-table"><thead><tr>';
    const headerCells = lines[startIdx].split("|").map(c => c.trim()).filter(Boolean);
    for (const cell of headerCells) {
      html += `<th>${inlineFormat(cell)}</th>`;
    }
    html += "</tr></thead><tbody>";

    for (let j = startIdx + 2; j < lines.length; j++) {
      if (!lines[j].includes("|")) break;
      const cells = lines[j].split("|").map(c => c.trim()).filter(Boolean);
      html += "<tr>";
      for (const cell of cells) {
        html += `<td>${inlineFormat(cell)}</td>`;
      }
      html += "</tr>";
    }
    html += "</tbody></table>\n";
    return html;
  }

  // ── file grouping ─────────────────────────────────────────────────────────

  // Priority order for file sidebar
  const FILE_ORDER = [
    "pulse.md", "mission.md", "roadmap.md", "inbox.md", "issues.md",
    "whiteboard.md", "identity.md", "patterns.md",
  ];

  // Top-level .gator/ files to show (knowledge base).
  // Everything else (json, infrastructure md) is hidden.
  const VISIBLE_FILES = new Set([
    "constitution.md", "pulse.md", "mission.md", "roadmap.md",
    "inbox.md", "issues.md", "patterns.md", "whiteboard.md",
  ]);

  // .gator/ subdirectories to show (user content).
  // Everything else (scripts, sessions, etc.) is hidden.
  const VISIBLE_DIRS = new Set([
    "charters", "threads", "artifacts", "blueprints", "vault",
    "field-guides", "docs", "reference-notes", "policies", "procedures",
    "loops",
  ]);

  // Gator-shipped default files in procedures/ and reference-notes/.
  // These are template content — hide them so only user-created files
  // and the README/_template show in the dashboard.
  const DEFAULT_TEMPLATE_FILES = new Set([
    "charter-alignment.md", "enforcer-review.md", "field-guide-generation.md",
    "knowledge-capture.md", "significance-check.md",
    "concierge-responses.md", "dangerous-patterns.md", "dashboard-operations.md",
    "enforcer-configuration.md", "example-project.md",
    "failure-modes-and-self-correction.md", "git-workflow.md",
    "identity-and-ownership.md", "refactor-approach.md",
    "what-gator-requires-from-a-model.md", "why-navigation-coding-feels-different.md",
    "workflow-profiles.md",
  ]);

  function filterFiles(files) {
    return files.filter(f => {
      const dir = f.dir || "";

      // gator-command/ source files (command-post mode) — keep existing logic
      if (dir.startsWith("gator-command/") || f.source === "gator-command") {
        return true;
      }

      // Source code files — always show
      if (f.source === "repo") return true;

      // .gator/ top-level files: whitelist only
      if (!dir || dir === ".gator/") {
        return VISIBLE_FILES.has(f.name);
      }

      // .gator/ subdirectories: whitelist only
      const normDir = dir.replace(/^\.gator\//, "");
      const topDir = normDir.split("/")[0];
      if (!VISIBLE_DIRS.has(topDir)) return false;

      // Hide shipped default template files in procedures/ and reference-notes/
      if ((topDir === "procedures" || topDir === "reference-notes") &&
          DEFAULT_TEMPLATE_FILES.has(f.name)) {
        return false;
      }

      return true;
    });
  }

  // ── sidebar tree model ────────────────────────────────────────────────────
  // Local browsing state, persisted across re-renders and view switches so
  // returning to a repo reopens where the user left off. Keyed by repo name;
  // reset only when the repo changes. teardown() (added with auto-refresh)
  // must NOT clear this — only lifecycle resources (timers/listeners).
  const _treeState = { repoName: null, expandedDirs: new Set(), selectedFile: null };

  function resetTreeStateFor(repoName) {
    if (_treeState.repoName !== repoName) {
      _treeState.repoName = repoName;
      _treeState.expandedDirs = new Set(["section:gator"]); // .gator open by default
      _treeState.selectedFile = null;
    }
  }

  function _isGcFile(f) {
    return f.source === "gator-command" || (f.dir || "").startsWith("gator-command") || (f.path || "").startsWith("gator-command/");
  }
  function _isSourceFile(f) { return f.source === "repo"; }

  // ── repo view lifecycle controller ────────────────────────────────────────
  // The dashboard shell (dashboard.js) owns view mount/unmount, not repo.js.
  // This controller holds the poll timer and global listeners so they are
  // registered once per mount and always cleared on view switch / repo change.
  // teardown() clears lifecycle resources ONLY — never _treeState (that
  // persistence is what restores the user's place when they return).
  const _repoView = {
    repoName: null, container: null, version: null, filter: null,
    timerId: null, popHandler: null, lastFp: null, pinnedFile: null,
  };
  const POLL_INTERVAL_MS = 5000;

  // Cheap change signal over the flat file list: count + newest mtime + a
  // rolling hash of paths. Equal fingerprints ⇒ nothing changed ⇒ no DOM work.
  function fingerprint(files) {
    let n = 0, maxM = 0, h = 0;
    for (const f of files) {
      n++;
      if (f.mtime && f.mtime > maxM) maxM = f.mtime;
      const p = f.path || "";
      for (let i = 0; i < p.length; i++) h = (h * 31 + p.charCodeAt(i)) | 0;
    }
    return n + ":" + maxM + ":" + h;
  }

  // A "pinned" view shows immutable history and must not be auto-refreshed or
  // have its sidebar reseated: branch-level (whole view on a commit via
  // _gatorRepoVersion) OR file-level (content pane at a file-history hash).
  function isPinnedView() {
    return !!window._gatorRepoVersion || !!_repoView.pinnedFile;
  }

  function teardownRepoView() {
    if (_repoView.timerId) { clearInterval(_repoView.timerId); _repoView.timerId = null; }
    if (_repoView.popHandler) { window.removeEventListener("popstate", _repoView.popHandler); _repoView.popHandler = null; }
    window._gatorRepoTeardown = null;
    // _treeState is intentionally preserved across teardown.
  }

  async function _fetchRepoFiles() {
    let url = `/api/repo/${encodeURIComponent(_repoView.repoName)}/files`;
    if (_repoView.version) url += `?version=${encodeURIComponent(_repoView.version)}`;
    const resp = await fetch(url);
    const data = await resp.json();
    if (data.error) return null;
    return data.files || [];
  }

  // Rebuild the sidebar from a fresh file list, preserving expansion +
  // selection. Does NOT touch the content pane. Drops a selection whose file
  // no longer exists (graceful — leaves the content pane as-is).
  function applyRefresh(files) {
    const container = _repoView.container;
    if (!container) return;
    const sidebar = container.querySelector("#repo-file-list");
    const content = container.querySelector("#repo-file-content");
    if (!sidebar) return;
    const filtered = filterFiles(files);
    if (_treeState.selectedFile && !filtered.some(f => f.path === _treeState.selectedFile)) {
      _treeState.selectedFile = null;
    }
    const scrollTop = sidebar.scrollTop;               // preserve sidebar scroll across refresh
    renderSidebarInto(sidebar, content, _repoView.repoName, filtered);
    sidebar.scrollTop = scrollTop;
    _repoView.lastFp = fingerprint(files);
  }

  // Background auto-refresh tick: silent, sidebar-only, heavily guarded.
  async function pollRepoFiles() {
    if (document.hidden) return;        // pause when the tab is not visible
    if (isPinnedView()) return;         // never reseat under a pinned history view
    if (_repoView.filter === "docs") return;
    try {
      const files = await _fetchRepoFiles();
      if (!files) return;
      if (fingerprint(files) === _repoView.lastFp) return;  // unchanged → no work
      applyRefresh(files);
    } catch (e) { /* transient — retry next tick */ }
  }

  // Build the sidebar tree + wire its handlers into an existing sidebar element.
  // Shared by the initial load and every refresh so both render identically.
  function renderSidebarInto(sidebar, content, repoName, filtered) {
    const gatorFiles = filtered.filter(f => !_isGcFile(f) && !_isSourceFile(f));
    const gcFiles = filtered.filter(_isGcFile);
    const sourceFiles = filtered.filter(_isSourceFile);

    const gatorTree = buildTree(gatorFiles, "");
    const gcTree = buildTree(gcFiles, "gator-command");
    const sourceTree = buildTree(sourceFiles, "source");
    sortGatorRoot(gatorTree);                 // landing docs above dirs at .gator root
    sortTreeNodes(gcTree, _mtimeCmp);
    sortTreeNodes(sourceTree, _mtimeCmp);

    // Preserve the commit-context badge on a version-scoped (history) view —
    // matches the header GatorViews.repo renders before files load.
    const version = _repoView.version;
    const verBadge = version
      ? '<span class="muted" style="font-size:10px;margin-left:6px;">' + escHtml(` @ ${version.substring(0, 8)}`) + '</span>'
      : "";
    let html = `<div class="repo-sidebar-header">${escHtml(repoName)}${verBadge}</div>`;
    html += renderSection(".gator/", "section:gator", gatorTree);
    html += renderSection("gator-command/", "section:gc", gcTree);
    html += renderSection("source/", "section:source", sourceTree);
    sidebar.innerHTML = html;

    // Section + directory expand/collapse. Each toggle button is emitted
    // immediately before its contents element, so nextElementSibling is the
    // contents — avoiding attribute-selector escaping on paths.
    sidebar.querySelectorAll(".repo-sidebar-section, .repo-tree-dir").forEach(btn => {
      btn.addEventListener("click", function () {
        const contents = this.nextElementSibling;
        if (!contents) return;
        const key = this.dataset.toggle || this.dataset.dir;
        const arrow = this.querySelector(".group-arrow");
        const willOpen = contents.style.display === "none";
        contents.style.display = willOpen ? "block" : "none";
        if (arrow) arrow.innerHTML = willOpen ? "&#9662;" : "&#9656;";
        if (willOpen) _treeState.expandedDirs.add(key);
        else _treeState.expandedDirs.delete(key);
      });
    });

    // File click handlers
    sidebar.querySelectorAll(".repo-file-item").forEach(item => {
      item.addEventListener("click", function () {
        sidebar.querySelectorAll(".repo-file-item").forEach(i => i.classList.remove("active"));
        this.classList.add("active");
        _treeState.selectedFile = this.dataset.path;
        _repoView.pinnedFile = null;            // live navigation clears the history pin
        loadFile(repoName, this.dataset.path, content, window._gatorRepoVersion);
      });
    });
  }

  // Build a real parent/child tree from a flat file list. basePrefix is the
  // section root ("" for .gator, "gator-command", "source"); node.path stays
  // the full canonical path (used for file identity and expansion keys).
  function buildTree(files, basePrefix) {
    const rootChildren = [];
    const dirIndex = new Map();

    function ensureDir(dirPath) {
      let node = dirIndex.get(dirPath);
      if (node) return node;
      node = { type: "dir", path: dirPath, name: dirPath.split("/").pop(), children: [], mtime: 0 };
      dirIndex.set(dirPath, node);
      const parent = dirPath.split("/").slice(0, -1).join("/");
      if (parent === basePrefix) rootChildren.push(node);
      else ensureDir(parent).children.push(node);
      return node;
    }

    for (const f of files) {
      const dirPath = f.path.split("/").slice(0, -1).join("/");
      const fileNode = { type: "file", path: f.path, name: f.name, mtime: f.mtime || 0 };
      if (dirPath === basePrefix) rootChildren.push(fileNode);
      else ensureDir(dirPath).children.push(fileNode);
    }
    return rootChildren;
  }

  const _mtimeCmp = (a, b) => (b.mtime || 0) - (a.mtime || 0); // files: newest first (O1)
  function _gatorFileCmp(a, b) {
    const ai = FILE_ORDER.indexOf(a.name), bi = FILE_ORDER.indexOf(b.name);
    const an = ai < 0 ? 999 : ai, bn = bi < 0 ? 999 : bi;
    return an !== bn ? an - bn : _mtimeCmp(a, b);
  }

  // Sort one level (dirs first alphabetically, then files via fileCmp), recurse.
  function sortTreeNodes(nodes, fileCmp) {
    nodes.sort((a, b) => {
      if (a.type !== b.type) return a.type === "dir" ? -1 : 1;
      if (a.type === "dir") return a.name.localeCompare(b.name);
      return fileCmp(a, b);
    });
    for (const n of nodes) if (n.type === "dir") sortTreeNodes(n.children, fileCmp);
  }

  // The .gator/ section root is special: the landing documents (pulse, mission,
  // roadmap, …) render ABOVE the directories, matching the knowledge-layer UX.
  // So at the root level only, files come first (FILE_ORDER then mtime), then
  // dirs (alpha). Deeper levels use the generic dirs-first sorter.
  function sortGatorRoot(nodes) {
    nodes.sort((a, b) => {
      if (a.type !== b.type) return a.type === "file" ? -1 : 1; // files first at root
      if (a.type === "dir") return a.name.localeCompare(b.name);
      return _gatorFileCmp(a, b);
    });
    for (const n of nodes) if (n.type === "dir") sortTreeNodes(n.children, _gatorFileCmp);
  }

  function expandAncestors(path) {
    if (path.startsWith("gator-command/")) _treeState.expandedDirs.add("section:gc");
    else if (path.startsWith("source/")) _treeState.expandedDirs.add("section:source");
    else _treeState.expandedDirs.add("section:gator");
    const segs = path.split("/");
    for (let k = 1; k < segs.length; k++) _treeState.expandedDirs.add(segs.slice(0, k).join("/"));
  }

  function renderTree(nodes, depth) {
    let html = "";
    for (const n of nodes) {
      if (n.type === "dir") {
        const open = _treeState.expandedDirs.has(n.path);
        const pad = 12 + depth * 14;
        html += `<button class="repo-tree-dir" data-dir="${escHtml(n.path)}" style="padding-left:${pad}px"><span class="group-arrow">${open ? "&#9662;" : "&#9656;"}</span> ${escHtml(n.name)}/</button>`;
        html += `<div class="repo-tree-children" style="display:${open ? "block" : "none"}">`;
        html += renderTree(n.children, depth + 1);
        html += `</div>`;
      } else {
        const pad = 12 + depth * 14 + 14;
        const active = _treeState.selectedFile === n.path ? " active" : "";
        const label = n.name.replace(/\.(md|json)$/, "");
        html += `<button class="repo-file-item${active}" data-path="${escHtml(n.path)}" style="padding-left:${pad}px">${escHtml(label)}</button>`;
      }
    }
    return html;
  }

  function renderSection(label, sectionKey, treeNodes) {
    if (!treeNodes.length) return "";
    const open = _treeState.expandedDirs.has(sectionKey);
    let h = `<button class="repo-sidebar-section" data-toggle="${sectionKey}"><span class="group-arrow">${open ? "&#9662;" : "&#9656;"}</span> ${escHtml(label)}</button>`;
    h += `<div class="repo-dir-contents" style="display:${open ? "block" : "none"}">`;
    h += renderTree(treeNodes, 0);
    h += `</div>`;
    return h;
  }

  // ── main render ───────────────────────────────────────────────────────────

  window.GatorViews.repo = function (data, container, repoName, version, filter) {
    // Clear any prior view's timer/listeners (idempotent) even if the shell
    // teardown hook is absent, then set up this mount.
    teardownRepoView();
    _repoView.repoName = repoName;
    _repoView.container = container;
    _repoView.version = version || null;
    _repoView.filter = filter || null;
    _repoView.pinnedFile = null;
    _repoView.lastFp = null;

    const verLabel = version ? ` @ ${version.substring(0, 8)}` : "";
    container.innerHTML = `
      <div class="repo-browser">
        <div class="repo-sidebar" id="repo-file-list">
          <div class="repo-sidebar-header">${escHtml(repoName)}${version ? '<span class="muted" style="font-size:10px;margin-left:6px;">' + escHtml(verLabel) + '</span>' : ''}</div>
          <div class="muted" style="padding:8px 12px;font-size:12px">Loading files...</div>
        </div>
        <div class="repo-sidebar-resize" id="repo-resize-handle"></div>
        <div class="repo-content" id="repo-file-content">
          <div class="muted" style="padding:40px;text-align:center">Select a file to view</div>
        </div>
      </div>
    `;

    loadFileList(repoName, container, version, filter);

    // Expose the teardown hook to the shell (dashboard.js) so it stops the
    // poll timer + listeners when the user navigates away from the repo view.
    window._gatorRepoTeardown = teardownRepoView;

    // Auto-refresh polling — live views only (skip docs filter and pinned
    // branch-version history, which is immutable).
    if (filter !== "docs" && !version) {
      _repoView.timerId = setInterval(pollRepoFiles, POLL_INTERVAL_MS);
    }
  };

  async function loadFileList(repoName, container, version, filter) {
    const sidebar = container.querySelector("#repo-file-list");
    const content = container.querySelector("#repo-file-content");

    try {
      let filesUrl = `/api/repo/${encodeURIComponent(repoName)}/files`;
      if (version) filesUrl += `?version=${encodeURIComponent(version)}`;
      const resp = await fetch(filesUrl);
      const data = await resp.json();

      if (data.error) {
        sidebar.innerHTML = `<div class="repo-sidebar-header">${escHtml(repoName)}</div><div class="muted" style="padding:8px 12px">${escHtml(data.error)}</div>`;
        return;
      }

      const files = data.files || [];
      const filtered = filterFiles(files);
      resetTreeStateFor(repoName);

      // ── Docs filter: show .gator/docs/ and repo-root docs/ files
      if (filter === "docs") {
        const docsFiles = filtered
          .filter(f => f.dir === "docs" || f.dir === "source/docs")
          .sort((a, b) => a.name.localeCompare(b.name));
        let html = `<div class="repo-sidebar-header">Docs</div>`;
        if (docsFiles.length === 0) {
          html += '<div class="muted" style="padding:8px 12px;font-size:12px">No docs found in .gator/docs/ or docs/</div>';
        } else {
          for (const f of docsFiles) html += fileItem(repoName, f, true);
        }
        sidebar.innerHTML = html;

        // File click handlers
        sidebar.querySelectorAll(".repo-file-item").forEach(item => {
          item.addEventListener("click", function () {
            sidebar.querySelectorAll(".repo-file-item").forEach(i => i.classList.remove("active"));
            this.classList.add("active");
            loadFile(repoName, this.dataset.path, content, window._gatorRepoVersion);
          });
        });

        // Auto-load first non-HTML doc. HTML files open in a new tab, which
        // browsers block when not triggered by a user gesture — never auto-load.
        const firstAutoloadable = docsFiles.find(f => !/\.html?$/i.test(f.path));
        if (firstAutoloadable) {
          const firstItem = sidebar.querySelector(`.repo-file-item[data-path="${firstAutoloadable.path.replace(/"/g, '&quot;')}"]`);
          if (firstItem) {
            firstItem.classList.add("active");
            loadFile(repoName, firstAutoloadable.path, content, window._gatorRepoVersion);
          }
        }

        // Resize handle
        initResizeHandle(sidebar);
        return;
      }

      // Choose the file to display: restore the prior selection if it still
      // exists, else the default document. Expand its ancestors before render
      // so the active item is visible.
      const gatorTopFiles = filtered.filter(f => !_isGcFile(f) && !_isSourceFile(f) && !f.dir);
      const nonHtml = f => !/\.html?$/i.test(f.path);
      const defaultFile = gatorTopFiles.find(f => f.name === "pulse.md")
        || gatorTopFiles.find(f => f.name === "mission.md")
        || gatorTopFiles.find(nonHtml) || filtered.find(nonHtml) || null;
      const restore = _treeState.selectedFile && filtered.some(f => f.path === _treeState.selectedFile);
      const loadPath = restore ? _treeState.selectedFile : (defaultFile && defaultFile.path) || null;
      if (loadPath) {
        _treeState.selectedFile = loadPath;
        expandAncestors(loadPath);
      }

      renderSidebarInto(sidebar, content, repoName, filtered);
      _repoView.lastFp = fingerprint(files);

      // Load the chosen file (its sidebar row is already marked active by render).
      if (loadPath) {
        _repoView.pinnedFile = null;
        loadFile(repoName, loadPath, content, window._gatorRepoVersion);
      }

      // Resize handle
      initResizeHandle(sidebar);

      // Cross-document search
      const searchInput = document.getElementById("repo-search-input");
      if (searchInput) {
        // Collect all file paths for searching
        const allFiles = files.map(f => f.path);

        let searchTimer = null;
        searchInput.addEventListener("input", function () {
          clearTimeout(searchTimer);
          const query = this.value.trim();
          if (!query || query.length < 2) {
            // Restore the default file or clear
            if (window._gatorSearchActive) {
              window._gatorSearchActive = false;
              history.pushState({ view: "repo", repo: repoName }, "");
              if (defaultFile) loadFile(repoName, defaultFile.path, content, window._gatorRepoVersion);
              else content.innerHTML = '<div class="muted" style="padding:40px;text-align:center">Select a file to view</div>';
            }
            return;
          }
          // Debounce 300ms
          searchTimer = setTimeout(() => runCrossDocSearch(repoName, query, allFiles, content), 300);
        });

        // Handle browser back button. Registered on the controller so
        // teardownRepoView() removes it — a window-level listener would
        // otherwise accumulate one per render (pre-existing leak).
        _repoView.popHandler = function (e) {
          if (e.state && e.state.searchQuery) {
            searchInput.value = e.state.searchQuery;
            runCrossDocSearch(repoName, e.state.searchQuery, allFiles, content);
          } else if (e.state && e.state.filePath) {
            searchInput.value = "";
            window._gatorSearchActive = false;
            loadFile(repoName, e.state.filePath, content, window._gatorRepoVersion);
          } else if (e.state && e.state.view === "repo") {
            searchInput.value = "";
            window._gatorSearchActive = false;
          }
        };
        window.addEventListener("popstate", _repoView.popHandler);
      }

    } catch (err) {
      sidebar.innerHTML = `<div class="repo-sidebar-header">${escHtml(repoName)}</div><div class="muted" style="padding:8px 12px">Failed to load files</div>`;
    }
  }

  async function runCrossDocSearch(repoName, query, allFiles, contentEl) {
    window._gatorSearchActive = true;
    history.pushState({ view: "repo", repo: repoName, searchQuery: query }, "", `?repo=${encodeURIComponent(repoName)}&q=${encodeURIComponent(query)}`);

    contentEl.innerHTML = '<div class="muted" style="padding:20px">Searching...</div>';

    try {
      const resp = await fetch(`/api/repo/${encodeURIComponent(repoName)}/search?q=${encodeURIComponent(query)}`);
      const data = await resp.json();

      if (data.error) {
        contentEl.innerHTML = `<div class="muted" style="padding:40px">${escHtml(data.error)}</div>`;
        return;
      }

      const results = data.results || [];
      if (results.length === 0) {
        contentEl.innerHTML = `<div class="muted" style="padding:40px;text-align:center">No results for "${escHtml(query)}"</div>`;
        return;
      }

      let html = `<div style="padding:16px"><div style="margin-bottom:12px;color:#666;font-size:13px">${results.length} file${results.length !== 1 ? 's' : ''} matching "${escHtml(query)}"</div>`;
      for (const r of results) {
        const label = r.path.replace(/\.(md|json)$/, "");
        const snippetHtml = escHtml(r.snippet).replace(
          new RegExp(escHtml(query).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), "gi"),
          m => `<mark class="search-hit">${m}</mark>`
        );
        html += `
          <div class="search-result" data-path="${escHtml(r.path)}">
            <div class="search-result-title">${escHtml(label)} <span class="muted" style="font-size:11px">(${r.match_count} match${r.match_count !== 1 ? 'es' : ''})</span></div>
            <div class="search-result-snippet">${snippetHtml}</div>
          </div>
        `;
      }
      html += "</div>";
      contentEl.innerHTML = html;

      // Click handlers for search results
      contentEl.querySelectorAll(".search-result").forEach(el => {
        el.style.cursor = "pointer";
        el.addEventListener("click", function () {
          const filePath = this.dataset.path;
          _treeState.selectedFile = filePath;  // keep persisted selection in sync
          _repoView.pinnedFile = null;         // live navigation clears the history pin
          history.pushState({ view: "repo", repo: repoName, filePath }, "");
          loadFile(repoName, filePath, contentEl, window._gatorRepoVersion);
          // Highlight in sidebar
          const sidebarItems = document.querySelectorAll(".repo-file-item");
          sidebarItems.forEach(i => i.classList.remove("active"));
          const match = document.querySelector(`[data-path="${filePath}"]`);
          if (match) match.classList.add("active");
        });
      });
    } catch (err) {
      contentEl.innerHTML = `<div class="muted" style="padding:40px">Search failed: ${escHtml(err.message)}</div>`;
    }
  }

  function initResizeHandle(sidebar) {
    const browser = sidebar.parentElement;
    if (!browser) return;
    const handle = browser.querySelector("#repo-resize-handle");
    if (!handle) return;
    let startX, startWidth;
    handle.addEventListener("mousedown", function (e) {
      startX = e.clientX;
      startWidth = sidebar.offsetWidth;
      e.preventDefault();
      function onMove(e) {
        const newWidth = startWidth + (e.clientX - startX);
        if (newWidth >= 120 && newWidth <= 500) {
          sidebar.style.width = newWidth + "px";
        }
      }
      function onUp() {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
      }
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    });
  }

  function fileItem(repoName, f, indented) {
    const label = f.name.replace(/\.(md|json)$/, "");
    const cls = indented ? "repo-file-item indented" : "repo-file-item";
    return `<button class="${cls}" data-path="${escHtml(f.path)}">${escHtml(label)}</button>`;
  }

  async function loadFile(repoName, filePath, contentEl, version) {
    // HTML files render themselves — open the raw endpoint in a new tab
    // instead of routing through the markdown renderer. Version-pinned
    // HTML is not supported (the raw endpoint has no ?version= handler).
    if (/\.html?$/i.test(filePath)) {
      const encoded = filePath.split("/").map(encodeURIComponent).join("/");
      const rawUrl = `/api/repo/${encodeURIComponent(repoName)}/raw/${encoded}`;
      window.open(rawUrl, "_blank", "noopener");
      contentEl.innerHTML = `<div class="muted" style="padding:24px 32px">Opened <code>${escHtml(filePath)}</code> in a new tab.</div>`;
      return;
    }
    contentEl.innerHTML = '<div class="muted" style="padding:40px;text-align:center">Loading...</div>';
    // Set context for image path resolution
    const currentDir = filePath.includes("/") ? filePath.substring(0, filePath.lastIndexOf("/")) : "";
    window._gatorRepoContext = { repoName: repoName, currentDir: currentDir };

    try {
      // Encode path segments individually — don't encode the slashes
      const encodedPath = filePath.split("/").map(encodeURIComponent).join("/");
      let fileUrl = `/api/repo/${encodeURIComponent(repoName)}/file/${encodedPath}`;
      if (version) fileUrl += `?version=${encodeURIComponent(version)}`;
      const resp = await fetch(fileUrl);
      const data = await resp.json();

      if (data.error) {
        contentEl.innerHTML = `<div class="muted" style="padding:40px">${escHtml(data.error)}</div>`;
        return;
      }

      const dateLabel = data.version
        ? `Viewing: ${escHtml(data.version.substring(0, 8))}${data.last_modified ? ' (' + escHtml(data.last_modified.substring(0, 19)) + ')' : ''}`
        : `Last updated: ${escHtml((data.last_modified || "").substring(0, 19))}`;
      const lastMod = data.last_modified || data.version
        ? `<span class="repo-file-date" style="position:relative;">${dateLabel}<button class="history-toggle-btn" title="Show file history">&#9662;</button><div class="history-dropdown" id="history-dropdown" style="display:none;"></div></span>`
        : "";
      // Build the repo-relative path for copying
      let copyPath;
      if (filePath.startsWith("source/")) {
        copyPath = filePath.substring("source/".length);  // strip source/ prefix — it's repo root
      } else if (filePath.startsWith("gator-command/")) {
        copyPath = filePath;  // already repo-relative
      } else {
        copyPath = ".gator/" + filePath;  // .gator/ files
      }
      // Store raw content for copy and in-doc search
      const rawContent = data.content || "";

      contentEl.innerHTML = `
        <div class="repo-file-header">
          <span>${escHtml(filePath)} <button class="copy-path-btn" title="Copy path" data-path="${escHtml(copyPath)}">&#9112;</button><button class="refresh-file-btn" title="Refresh file">&#8635;</button></span>
          <span class="file-header-right">
            <input type="text" class="in-doc-search" placeholder="Find in file..." />
            <button class="copy-content-btn" title="Copy file content">&#128203;</button>
            ${lastMod}
          </span>
        </div>
        <div class="repo-markdown">${filePath.endsWith(".md") ? renderMarkdown(rawContent) : '<pre class="md-code-block">' + escHtml(rawContent) + '</pre>'}</div>
      `;

      // Copy path button handler
      contentEl.querySelector(".copy-path-btn").addEventListener("click", function (e) {
        e.stopPropagation();
        const path = this.dataset.path;
        navigator.clipboard.writeText(path).then(() => {
          this.textContent = "\u2713";
          setTimeout(() => { this.innerHTML = "&#9112;"; }, 1500);
        });
      });

      // Refresh file button handler
      contentEl.querySelector(".refresh-file-btn").addEventListener("click", function (e) {
        e.stopPropagation();
        this.textContent = "\u23F3";
        loadFile(repoName, filePath, contentEl, version);
      });

      // Copy content button handler
      contentEl.querySelector(".copy-content-btn").addEventListener("click", function (e) {
        e.stopPropagation();
        navigator.clipboard.writeText(rawContent).then(() => {
          this.textContent = "\u2713";
          setTimeout(() => { this.textContent = "\uD83D\uDCCB"; }, 1500);
        });
      });

      // In-document search handler
      const inDocInput = contentEl.querySelector(".in-doc-search");
      const markdownEl = contentEl.querySelector(".repo-markdown");
      if (inDocInput && markdownEl) {
        let prevQuery = "";
        inDocInput.addEventListener("input", function () {
          const query = this.value.trim().toLowerCase();
          // Remove previous highlights
          markdownEl.querySelectorAll("mark.search-hit").forEach(m => {
            m.replaceWith(m.textContent);
          });
          markdownEl.normalize();
          if (!query || query.length < 2) { prevQuery = ""; return; }
          prevQuery = query;
          // Walk text nodes and wrap matches
          const walker = document.createTreeWalker(markdownEl, NodeFilter.SHOW_TEXT, null);
          const matches = [];
          let node;
          while (node = walker.nextNode()) {
            const idx = node.textContent.toLowerCase().indexOf(query);
            if (idx >= 0) matches.push({ node, idx });
          }
          // Highlight in reverse order to preserve offsets
          for (let i = matches.length - 1; i >= 0; i--) {
            const { node, idx } = matches[i];
            const range = document.createRange();
            range.setStart(node, idx);
            range.setEnd(node, idx + query.length);
            const mark = document.createElement("mark");
            mark.className = "search-hit";
            range.surroundContents(mark);
          }
          // Scroll to first match
          const first = markdownEl.querySelector("mark.search-hit");
          if (first) first.scrollIntoView({ behavior: "smooth", block: "center" });
        });
      }

      // History dropdown handler
      const histBtn = contentEl.querySelector(".history-toggle-btn");
      const histDropdown = contentEl.querySelector("#history-dropdown");
      if (histBtn && histDropdown) {
        let historyLoaded = false;

        histBtn.addEventListener("click", async function (e) {
          e.stopPropagation();

          // Toggle visibility
          if (histDropdown.style.display !== "none") {
            histDropdown.style.display = "none";
            return;
          }

          histDropdown.style.display = "block";

          if (historyLoaded) return;

          histDropdown.innerHTML = '<div style="padding:8px; color:#aaa;">Loading…</div>';
          try {
            const encodedHist = filePath.split("/").map(encodeURIComponent).join("/");
            const hResp = await fetch(`/api/repo/${encodeURIComponent(repoName)}/history/${encodedHist}`);
            const hData = await hResp.json();

            if (!hData.commits || !hData.commits.length) {
              histDropdown.innerHTML = '<div style="padding:8px; color:#aaa;">No history available</div>';
              historyLoaded = true;
              return;
            }

            let html = "";
            for (const c of hData.commits) {
              const dateStr = (c.date || "").substring(0, 19);
              const isActive = data.version === c.hash;
              html += `<div class="history-item${isActive ? " history-active" : ""}" data-hash="${escHtml(c.hash)}" title="${escHtml(c.message)}">
                <span class="history-hash">${escHtml(c.short_hash)}</span>
                <span class="history-date">${escHtml(dateStr)}</span>
                <span class="history-msg">${escHtml((c.message || "").substring(0, 50))}</span>
              </div>`;
            }
            histDropdown.innerHTML = html;
            historyLoaded = true;

            // Click handler on each history item
            histDropdown.querySelectorAll(".history-item").forEach(item => {
              item.addEventListener("click", function (e) {
                e.stopPropagation();
                histDropdown.style.display = "none";
                const hash = this.dataset.hash;
                _repoView.pinnedFile = filePath;  // pin to a history version — suspends auto-refresh
                loadFile(repoName, filePath, contentEl, hash);
              });
            });
          } catch (err) {
            histDropdown.innerHTML = `<div style="padding:8px; color:var(--color-critical);">Error: ${escHtml(err.message)}</div>`;
          }
        });

        // Close dropdown on outside click
        document.addEventListener("click", function closeHist() {
          histDropdown.style.display = "none";
        });
      }

      // Intercept .md links — load them in the file browser instead of navigating
      contentEl.querySelectorAll(".repo-markdown a").forEach(link => {
        const href = link.getAttribute("href") || "";
        if (href.endsWith(".md") && !href.startsWith("http")) {
          link.addEventListener("click", function (e) {
            e.preventDefault();
            // Resolve relative to current file's directory
            const currentDir = filePath.includes("/") ? filePath.substring(0, filePath.lastIndexOf("/")) : "";
            let target = href;
            if (currentDir && !href.startsWith("/")) {
              target = currentDir + "/" + href;
            }
            // Normalize: remove ./ and resolve ../
            target = target.replace(/^\.\//, "");
            while (target.includes("/../")) {
              target = target.replace(/[^/]+\/\.\.\//, "");
            }
            target = target.replace(/^\.\.\//, "");
            _treeState.selectedFile = target;  // keep persisted selection in sync
            _repoView.pinnedFile = null;       // live navigation clears the history pin
            loadFile(repoName, target, contentEl, window._gatorRepoVersion);
            // Update sidebar active state
            const sidebar = contentEl.parentElement.querySelector("#repo-file-list");
            if (sidebar) {
              sidebar.querySelectorAll(".repo-file-item").forEach(i => i.classList.remove("active"));
              const match = sidebar.querySelector(`[data-path="${target}"]`);
              if (match) match.classList.add("active");
            }
          });
        }
      });
    } catch (err) {
      contentEl.innerHTML = `<div class="muted" style="padding:40px">Failed to load file</div>`;
    }
  }
})();
