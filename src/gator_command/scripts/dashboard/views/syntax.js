/*
 * views/syntax.js — read-only Python and SQL syntax highlighter.
 *
 * Self-contained; no external library. Exposes:
 *   window.gatorHighlight(source, lang) → HTML string of token spans.
 *   window.gatorHighlight.langFor(path) → "python" | "sql" | null.
 *
 * TRIPWIRE: escape happens INSIDE toHtml(). The tokenizers see raw
 * source and emit token objects with unescaped values; toHtml() is
 * the ONLY thing that concatenates HTML, and it always escapes each
 * token value before wrapping. Never route raw token values into
 * innerHTML from outside toHtml().
 */
(function () {
  "use strict";

  const T_TEXT = "text";
  const T_KEYWORD = "keyword";
  const T_STRING = "string";
  const T_COMMENT = "comment";
  const T_NUMBER = "number";
  const T_BUILTIN = "builtin";
  const T_DECORATOR = "decorator";

  // ── Python vocabulary ────────────────────────────────────────

  const PY_KEYWORDS = new Set([
    "False", "None", "True", "and", "as", "assert", "async", "await",
    "break", "class", "continue", "def", "del", "elif", "else",
    "except", "finally", "for", "from", "global", "if", "import",
    "in", "is", "lambda", "nonlocal", "not", "or", "pass", "raise",
    "return", "try", "while", "with", "yield", "match", "case",
  ]);

  const PY_BUILTINS = new Set([
    "abs", "all", "any", "ascii", "bin", "bool", "bytearray", "bytes",
    "callable", "chr", "classmethod", "compile", "complex", "delattr",
    "dict", "dir", "divmod", "enumerate", "eval", "exec", "filter",
    "float", "format", "frozenset", "getattr", "globals", "hasattr",
    "hash", "help", "hex", "id", "input", "int", "isinstance",
    "issubclass", "iter", "len", "list", "locals", "map", "max",
    "memoryview", "min", "next", "object", "oct", "open", "ord",
    "pow", "print", "property", "range", "repr", "reversed", "round",
    "set", "setattr", "slice", "sorted", "staticmethod", "str", "sum",
    "super", "tuple", "type", "vars", "zip", "self", "cls",
  ]);

  const RE_ID_START = /[a-zA-Z_]/;
  const RE_ID_CONT = /[a-zA-Z0-9_]/;
  const RE_DIGIT = /[0-9]/;
  const RE_PY_STRING_PREFIX = /^[rRbBuUfF]{1,2}$/;

  function tokenizePython(src) {
    const tokens = [];
    const n = src.length;
    let i = 0;
    while (i < n) {
      const c = src[i];

      // `#` line comment.
      if (c === "#") {
        let j = i;
        while (j < n && src[j] !== "\n") j++;
        tokens.push({ t: T_COMMENT, v: src.substring(i, j) });
        i = j;
        continue;
      }

      // Triple-quoted string.
      if ((c === "\"" || c === "'")
          && src[i + 1] === c && src[i + 2] === c) {
        const end = scanTripleString(src, i);
        tokens.push({ t: T_STRING, v: src.substring(i, end) });
        i = end;
        continue;
      }

      // Single- or double-quoted string.
      if (c === "\"" || c === "'") {
        const end = scanPyString(src, i);
        tokens.push({ t: T_STRING, v: src.substring(i, end) });
        i = end;
        continue;
      }

      // Decorator `@name.path` — only at logical line start.
      if (c === "@" && atLineStart(src, i)) {
        let j = i + 1;
        while (j < n && (RE_ID_CONT.test(src[j]) || src[j] === ".")) j++;
        tokens.push({ t: T_DECORATOR, v: src.substring(i, j) });
        i = j;
        continue;
      }

      // Number literal (int / float / hex / oct / bin / complex).
      if (RE_DIGIT.test(c)
          || (c === "." && i + 1 < n && RE_DIGIT.test(src[i + 1]))) {
        const end = scanPyNumber(src, i);
        tokens.push({ t: T_NUMBER, v: src.substring(i, end) });
        i = end;
        continue;
      }

      // Identifier / keyword / builtin. May be a string prefix.
      if (RE_ID_START.test(c)) {
        let j = i + 1;
        while (j < n && RE_ID_CONT.test(src[j])) j++;
        const word = src.substring(i, j);
        // String prefix followed by quote → identifier + string as
        // one span so `f"…"` doesn't split visually.
        if (j < n && (src[j] === "\"" || src[j] === "'")
            && RE_PY_STRING_PREFIX.test(word)) {
          let strEnd;
          if (src[j + 1] === src[j] && src[j + 2] === src[j]) {
            strEnd = scanTripleString(src, j);
          } else {
            strEnd = scanPyString(src, j);
          }
          tokens.push({ t: T_STRING, v: src.substring(i, strEnd) });
          i = strEnd;
          continue;
        }
        if (PY_KEYWORDS.has(word)) {
          tokens.push({ t: T_KEYWORD, v: word });
        } else if (PY_BUILTINS.has(word)) {
          tokens.push({ t: T_BUILTIN, v: word });
        } else {
          tokens.push({ t: T_TEXT, v: word });
        }
        i = j;
        continue;
      }

      // Everything else — consume a run of "boring" chars as text so
      // we don't emit one span per character.
      let j = i;
      while (j < n) {
        const cc = src[j];
        if (cc === "#" || cc === "\"" || cc === "'" || cc === "@"
            || RE_ID_START.test(cc) || RE_DIGIT.test(cc)) break;
        j++;
      }
      if (j === i) j = i + 1;
      tokens.push({ t: T_TEXT, v: src.substring(i, j) });
      i = j;
    }
    return tokens;
  }

  function scanPyString(src, i) {
    const quote = src[i];
    const n = src.length;
    let j = i + 1;
    while (j < n) {
      const c = src[j];
      if (c === "\\") { j += 2; continue; }
      if (c === quote) { j++; break; }
      if (c === "\n") break;  // unterminated single-line string
      j++;
    }
    return j;
  }

  function scanTripleString(src, i) {
    const quote = src[i];
    const n = src.length;
    let j = i + 3;
    while (j < n) {
      if (src[j] === "\\") { j += 2; continue; }
      if (src[j] === quote && src[j + 1] === quote
          && src[j + 2] === quote) {
        return j + 3;
      }
      j++;
    }
    return n;
  }

  function scanPyNumber(src, i) {
    const n = src.length;
    // 0x… / 0o… / 0b…
    if (src[i] === "0" && i + 1 < n
        && /[xXoObB]/.test(src[i + 1])) {
      let j = i + 2;
      while (j < n && /[0-9a-fA-F_]/.test(src[j])) j++;
      return j;
    }
    let j = i;
    while (j < n && /[0-9_]/.test(src[j])) j++;
    if (j < n && src[j] === ".") {
      j++;
      while (j < n && /[0-9_]/.test(src[j])) j++;
    }
    if (j < n && /[eE]/.test(src[j])) {
      j++;
      if (j < n && (src[j] === "+" || src[j] === "-")) j++;
      while (j < n && /[0-9_]/.test(src[j])) j++;
    }
    if (j < n && /[jJ]/.test(src[j])) j++;  // complex
    return j;
  }

  function atLineStart(src, i) {
    let k = i - 1;
    while (k >= 0 && (src[k] === " " || src[k] === "\t")) k--;
    return k < 0 || src[k] === "\n";
  }

  // ── SQL vocabulary ───────────────────────────────────────────

  const SQL_KEYWORDS_UPPER = new Set([
    "ADD", "ALL", "ALTER", "AND", "AS", "ASC", "AUTOINCREMENT",
    "BEGIN", "BETWEEN", "BY", "CASCADE", "CASE", "CAST", "CHECK",
    "COLLATE", "COLUMN", "COMMIT", "CONSTRAINT", "CREATE", "CROSS",
    "CURRENT_DATE", "CURRENT_TIME", "CURRENT_TIMESTAMP", "DATABASE",
    "DEFAULT", "DELETE", "DESC", "DISTINCT", "DROP", "ELSE", "END",
    "EXCEPT", "EXISTS", "FALSE", "FOR", "FOREIGN", "FROM", "FULL",
    "GRANT", "GROUP", "HAVING", "IF", "IN", "INDEX", "INNER",
    "INSERT", "INTERSECT", "INTO", "IS", "ISNULL", "JOIN", "KEY",
    "LEFT", "LIKE", "LIMIT", "NATURAL", "NOT", "NOTNULL", "NULL",
    "OFFSET", "ON", "OR", "ORDER", "OUTER", "PRAGMA", "PRIMARY",
    "REFERENCES", "REPLACE", "RETURNING", "REVOKE", "RIGHT",
    "ROLLBACK", "SELECT", "SET", "TABLE", "THEN", "TO",
    "TRANSACTION", "TRIGGER", "TRUE", "UNION", "UNIQUE", "UPDATE",
    "USING", "VALUES", "VIEW", "WHEN", "WHERE", "WITH",
  ]);

  function tokenizeSql(src) {
    const tokens = [];
    const n = src.length;
    let i = 0;
    while (i < n) {
      const c = src[i];

      // Line comment `-- …`.
      if (c === "-" && src[i + 1] === "-") {
        let j = i;
        while (j < n && src[j] !== "\n") j++;
        tokens.push({ t: T_COMMENT, v: src.substring(i, j) });
        i = j;
        continue;
      }

      // Block comment `/* … */`.
      if (c === "/" && src[i + 1] === "*") {
        let j = i + 2;
        while (j < n) {
          if (src[j] === "*" && src[j + 1] === "/") { j += 2; break; }
          j++;
        }
        tokens.push({ t: T_COMMENT, v: src.substring(i, j) });
        i = j;
        continue;
      }

      // Single-quoted string, with '' escape.
      if (c === "'") {
        let j = i + 1;
        while (j < n) {
          if (src[j] === "'") {
            if (src[j + 1] === "'") { j += 2; continue; }
            j++;
            break;
          }
          j++;
        }
        tokens.push({ t: T_STRING, v: src.substring(i, j) });
        i = j;
        continue;
      }

      // Number.
      if (RE_DIGIT.test(c)
          || (c === "." && i + 1 < n && RE_DIGIT.test(src[i + 1]))) {
        let j = i;
        while (j < n && RE_DIGIT.test(src[j])) j++;
        if (j < n && src[j] === ".") {
          j++;
          while (j < n && RE_DIGIT.test(src[j])) j++;
        }
        tokens.push({ t: T_NUMBER, v: src.substring(i, j) });
        i = j;
        continue;
      }

      // Identifier / keyword (case-insensitive keyword match).
      if (RE_ID_START.test(c)) {
        let j = i + 1;
        while (j < n && RE_ID_CONT.test(src[j])) j++;
        const word = src.substring(i, j);
        if (SQL_KEYWORDS_UPPER.has(word.toUpperCase())) {
          tokens.push({ t: T_KEYWORD, v: word });
        } else {
          tokens.push({ t: T_TEXT, v: word });
        }
        i = j;
        continue;
      }

      // Coalesce runs of non-special chars.
      let j = i;
      while (j < n) {
        const cc = src[j];
        if (cc === "-" || cc === "/" || cc === "'"
            || RE_ID_START.test(cc) || RE_DIGIT.test(cc)) break;
        j++;
      }
      if (j === i) j = i + 1;
      tokens.push({ t: T_TEXT, v: src.substring(i, j) });
      i = j;
    }
    return tokens;
  }

  // ── Rendering ────────────────────────────────────────────────

  function escHtml(s) {
    return s.replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
  }

  function toHtml(tokens) {
    let out = "";
    for (const tok of tokens) {
      if (tok.t === T_TEXT) {
        out += escHtml(tok.v);
      } else {
        out += "<span class=\"tok-" + tok.t + "\">"
             + escHtml(tok.v) + "</span>";
      }
    }
    return out;
  }

  // ── Public API ───────────────────────────────────────────────

  function highlight(source, lang) {
    if (typeof source !== "string") return "";
    let tokens;
    if (lang === "python") tokens = tokenizePython(source);
    else if (lang === "sql") tokens = tokenizeSql(source);
    else return escHtml(source);
    return toHtml(tokens);
  }

  highlight.langFor = function (filePath) {
    if (/\.py$/i.test(filePath)) return "python";
    if (/\.sql$/i.test(filePath)) return "sql";
    return null;
  };

  window.gatorHighlight = highlight;
})();
