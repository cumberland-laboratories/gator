/*
 * views/loop-markdown.js — closed display formatter for expanded Loop
 * artifacts (#45). Self-contained; no dependencies. Exposes:
 *   window.GatorLoopMarkdown.render(text)   -> DocumentFragment
 *   window.GatorLoopMarkdown.safeHref(url)  -> absolute http(s) href | null
 *   window.GatorLoopMarkdown.MAX_RENDER_CHARS
 *
 * TRIPWIRE: artifact text is hostile, model-authored input. It reaches the
 * DOM ONLY through createElement / createTextNode. Never innerHTML,
 * outerHTML, insertAdjacentHTML, setAttribute("style"), or on* handlers.
 * Elements: h3-h6 p ul li pre code strong a table thead tbody tr th td
 * blockquote hr div span. Attributes: class (constants below) and, on <a>
 * only, href / target / rel. Never style, id, on*, or src.
 *
 * Closed grammar (plan rev 2): one linear pass, no nesting, no recursion.
 * Anything not matched below is literal text. New rules need a plan
 * revision, not an implementation-time extension.
 */
(function () {
  "use strict";

  var MAX_RENDER_CHARS = 200000;
  var IMG = /^!\[[^\]]*\]\([^()\s]*\)/;          // inline rule 1 (literal guard)
  var LINK = /^\[([^\]]*)\]\(([^()\s]*)\)/;      // inline rule 3

  function el(tag, cls) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    return e;
  }

  function text(parent, s) {
    if (s) parent.appendChild(document.createTextNode(s));
  }

  function safeHref(url) {
    if (typeof url !== "string") return null;
    var u = url.trim();
    if (!u || /[\s\x00-\x1f\x7f\\]/.test(u)) return null;
    var parsed;
    try { parsed = new URL(u); } catch (e) { return null; }
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null;
    return parsed.href;
  }

  // One left-to-right scan; first matching rule wins; nothing nests.
  function renderInline(parent, s) {
    var buf = "";
    var i = 0;
    function flush() { text(parent, buf); buf = ""; }
    while (i < s.length) {
      var c = s.charAt(i);
      var rest = s.slice(i);
      if (c === "!") {                                   // 1. image -> literal
        var im = IMG.exec(rest);
        if (im) { buf += im[0]; i += im[0].length; continue; }
      } else if (c === "`") {                            // 2. code span
        var j = s.indexOf("`", i + 1);
        if (j > i) {
          flush();
          var code = el("code");
          text(code, s.slice(i + 1, j));
          parent.appendChild(code);
          i = j + 1;
          continue;
        }
      } else if (c === "[") {                            // 3. link
        var lm = LINK.exec(rest);
        if (lm) {
          flush();
          var href = safeHref(lm[2]);
          if (href) {
            var a = el("a");
            a.href = href;
            a.target = "_blank";
            a.rel = "noopener noreferrer nofollow";
            text(a, lm[1]);
            parent.appendChild(a);
          } else {
            var span = el("span", "loop-md-link-blocked");
            text(span, lm[1] + " (" + lm[2] + ")");
            parent.appendChild(span);
          }
          i += lm[0].length;
          continue;
        }
      } else if (c === "*" && s.charAt(i + 1) === "*") { // 4. bold
        var k = s.indexOf("**", i + 2);
        if (k >= i + 2) {
          flush();
          var strong = el("strong");
          text(strong, s.slice(i + 2, k));
          parent.appendChild(strong);
          i = k + 2;
          continue;
        }
      }
      buf += c;                                          // 5. literal
      i += 1;
    }
    flush();
  }

  function cells(line) {
    var parts = line.trim().split("|");
    if (parts.length && parts[0].trim() === "") parts.shift();
    if (parts.length && parts[parts.length - 1].trim() === "") parts.pop();
    return parts.map(function (p) { return p.trim(); });
  }

  function buildTable(header, rows) {
    var width = Math.min(32, Math.max(1, header.length));
    var wrap = el("div", "loop-md-tablewrap");
    var table = el("table");
    var thead = el("thead"), tbody = el("tbody");
    function row(values, tag, parent) {
      var tr = el("tr");
      for (var c = 0; c < width; c++) {
        var cell = el(tag);
        renderInline(cell, values[c] || "");
        tr.appendChild(cell);
      }
      parent.appendChild(tr);
    }
    row(header, "th", thead);
    rows.forEach(function (r) { row(r, "td", tbody); });
    table.appendChild(thead);
    table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
  }

  function render(input) {
    var frag = document.createDocumentFragment();
    if (typeof input !== "string" || !input) return frag;
    if (input.length > MAX_RENDER_CHARS) {
      var big = new Error("artifact too large to render");
      big.name = "TooLarge";
      throw big;
    }
    var lines = input.replace(/\r\n?/g, "\n").split("\n");
    var cur = null, curType = null;
    function close() { cur = null; curType = null; }
    function block(node) { close(); frag.appendChild(node); return node; }

    for (var n = 0; n < lines.length; n++) {
      var line = lines[n], m;
      if (/^\s*```/.test(line)) {                        // 1. fence
        var body = [];
        for (n += 1; n < lines.length && !/^\s*```/.test(lines[n]); n++) body.push(lines[n]);
        var pre = block(el("pre")), code = el("code");
        text(code, body.join("\n"));
        pre.appendChild(code);
      } else if ((m = /^(#{1,6})\s+(.*)$/.exec(line))) { // 2. heading
        renderInline(block(el("h" + Math.min(6, m[1].length + 2))), m[2]);
      } else if (/^\s*(---|\*\*\*|___)\s*$/.test(line)) { // 3. hr
        block(el("hr"));
      } else if ((m = /^>\s?(.*)$/.exec(line))) {       // 4. blockquote
        renderInline(block(el("blockquote")), m[1]);
      } else if ((m = /^(\s*)[-*+]\s+(.*)$/.exec(line))   // 5. bullet
                 || (m = /^(\s*)(\d+\.\s+.*)$/.exec(line))) { // 6. numbered
        if (curType !== "ul") { block(el("ul")); cur = frag.lastChild; curType = "ul"; }
        var li = el("li", "md-indent-" + Math.min(3, Math.floor(m[1].length / 2)));
        renderInline(li, m[2]);
        cur.appendChild(li);
      } else if (/^\s*\|/.test(line) && n + 1 < lines.length
                 && /^[\s|:-]+$/.test(lines[n + 1]) && lines[n + 1].indexOf("-") !== -1
                 && lines[n + 1].indexOf("|") !== -1) {  // 7. table
        var header = cells(line), rows = [];
        for (n += 2; n < lines.length && /^\s*\|/.test(lines[n]); n++) rows.push(cells(lines[n]));
        n -= 1;
        block(buildTable(header, rows));
      } else if (/^\s*$/.test(line)) {                   // 8. blank
        close();
      } else {                                           // paragraph
        if (curType !== "p") { block(el("p")); cur = frag.lastChild; curType = "p"; }
        else text(cur, " ");
        renderInline(cur, line.trim());
      }
    }
    return frag;
  }

  window.GatorLoopMarkdown = {
    render: render,
    safeHref: safeHref,
    MAX_RENDER_CHARS: MAX_RENDER_CHARS,
  };
})();
