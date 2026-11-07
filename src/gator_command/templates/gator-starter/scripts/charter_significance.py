#!/usr/bin/env python3
"""
charter_significance — which functions need a charter entry (#105).

One decision shared by the charter verifier, the charter linter and the
pre-commit new-function warning. It reads source text and charter text
only; it never imports or executes the code it inspects.

Default policy (`POLICY = "gator-significance-v1"`, closed): a public
function is `document` when it is an entry point (route/CLI decorator,
`func=` registration, `__all__`, JavaScript export or global assignment)
or when a file owned by a different charter imports it. Everything else
is `internal`; private and conventional names are `not-applicable`.
A charter's `**Internal**:` line (`parse_internal()`) records names that
are deliberately internal; callers apply it after coverage resolution.

Standard library only, imported by plain name like `charter_covers`.
"""

import ast
import re

POLICY = "gator-significance-v1"

# Conventionally not charter-worthy (formerly the verifier's skip list).
CONVENTIONAL_NAMES = frozenset({
    "main", "setup", "teardown",
    "print_report", "print_json", "print_json_report", "print_result",
    "print_plan", "print_json_plan", "print_findings", "print_json_findings",
    "print_scaffolds", "print_index_suggestions",
    "escHtml", "fmtTs", "fmtDate",
})

# Final decorator attribute (or bare name) that marks a route or CLI command.
ENTRY_DECORATORS = frozenset({
    "get", "post", "put", "patch", "delete", "route", "api_route",
    "websocket", "command", "group",
})

# Calls whose first string argument names a sibling module.
_LOADER_CALLS = frozenset({"import_sibling", "import_module"})

_IDENT = re.compile(r"[A-Za-z_$][\w$]*")
_DOTTED = re.compile(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*")
_FILE_TICKED = re.compile(r"^File:\s*`([^`]+)`")
_FILE_PLAIN = re.compile(r"^File:\s*(\S+)")


# ---------------------------------------------------------------------------
# Charter-side parsing
# ---------------------------------------------------------------------------

def heading_names(line):
    """Names a `###` / `####` charter heading documents, in order.

    Grouped entries (`### a() / b(x) / Cls.c()`) name every identifier
    written directly before a top-level `(`; text inside parentheses is
    ignored. A heading that is only a (dotted) identifier, optionally
    after `class `, names that identifier. Prose headings name nothing.
    """
    m = re.match(r"^#{3,4}\s+(.*)$", line)
    if not m:
        return []
    text = m.group(1).replace("`", "").strip()
    names = []
    depth = 0
    start = None  # start of the current dotted-identifier run at depth 0
    for i, ch in enumerate(text):
        if ch == "(":
            if depth == 0 and start is not None:
                word = text[start:i]
                if _DOTTED.fullmatch(word) and word not in names:
                    names.append(word)
            depth += 1
            start = None
        elif ch == ")":
            depth = max(0, depth - 1)
            start = None
        elif depth == 0 and (ch.isalnum() or ch in "_$."):
            if start is None:
                start = i
        else:
            start = None
    if not names:
        bare = text[6:].strip() if text.startswith("class ") else text
        if _DOTTED.fullmatch(bare):
            names.append(bare)
    return names


def parse_file_line(line):
    """The path on a `File:` line, written with or without backticks, or None."""
    m = _FILE_TICKED.match(line) or _FILE_PLAIN.match(line)
    return m.group(1) if m else None


INTERNAL_PREFIX = "**Internal**:"
_INTERNAL_ITEM = re.compile(r"`([A-Za-z_$][A-Za-z0-9_$]*)`")


def parse_internal(text):
    """Read a charter's optional `**Internal**:` line.

    Contract: at most one line, before the first `## ` heading, listing
    backticked identifiers separated by commas — no globs, dots or prose.
    Returns `(names, problems)`: `names` are the unique valid names, in
    order, from the first well-placed line (a misplaced or repeated line
    suppresses nothing); `problems` are `{"code", "line", "detail"}` with
    codes `malformed`, `duplicate`, `multiple-lines` and `misplaced`.
    """
    names, problems = [], []
    seen_line = False
    in_header = True
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("## "):
            in_header = False
        if not stripped.startswith(INTERNAL_PREFIX):
            continue
        if seen_line:
            problems.append({"code": "multiple-lines", "line": lineno,
                             "detail": "only one **Internal**: line is allowed"})
            continue
        seen_line = True
        if not in_header:
            problems.append({"code": "misplaced", "line": lineno,
                             "detail": "**Internal**: must come before the first ## heading"})
            continue
        rest = stripped[len(INTERNAL_PREFIX):].strip()
        items = [item.strip() for item in rest.split(",")] if rest else []
        if not items:
            problems.append({"code": "malformed", "line": lineno,
                             "detail": "empty **Internal**: list"})
        for item in items:
            m = _INTERNAL_ITEM.fullmatch(item)
            if not m:
                problems.append({"code": "malformed", "line": lineno,
                                 "detail": f"not a backticked identifier: {item[:60]!r}"})
            elif m.group(1) in names:
                problems.append({"code": "duplicate", "line": lineno,
                                 "detail": f"`{m.group(1)}` is listed twice"})
            else:
                names.append(m.group(1))
    return names, problems


# ---------------------------------------------------------------------------
# Source-side signals
# ---------------------------------------------------------------------------

def _empty_signals():
    return {"entries": set(), "imports": set(), "registered": set()}


def _stem(module):
    """`a.b.c` -> `c`; `gator-charter-draft.py` -> `gator-charter-draft`."""
    module = module[:-3] if module.endswith(".py") else module
    return module.rsplit(".", 1)[-1]


def python_signals(source):
    """Entry points and cross-module imports of one Python source text.

    Returns `{"entries", "imports", "registered"}`: `entries` are names
    registered as routes/commands or listed in `__all__`; `imports` are
    `(module_stem, name)` pairs this file uses from other modules;
    `registered` are other module-level bindings (assignments and imported
    names), which exist as code for stale checks but are never candidates.
    Unparseable source gives empty signals.
    """
    out = _empty_signals()
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return out

    aliases = {}  # local name -> module stem
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            stem = _stem(node.module)
            for a in node.names:
                out["imports"].add((stem, a.name))
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    aliases[a.asname] = _stem(a.name)
                elif "." not in a.name:
                    aliases[a.name] = a.name
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            func = node.value.func
            fname = getattr(func, "id", None) or getattr(func, "attr", None)
            args = node.value.args
            if (fname in _LOADER_CALLS and args and isinstance(args[0], ast.Constant)
                    and isinstance(args[0].value, str)):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        aliases[target.id] = _stem(args[0].value)

    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id in aliases):
            out["imports"].add((aliases[node.value.id], node.attr))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                target = dec.func if isinstance(dec, ast.Call) else dec
                word = getattr(target, "attr", None) or getattr(target, "id", None)
                if word in ENTRY_DECORATORS:
                    out["entries"].add(node.name)
        elif (isinstance(node, ast.keyword) and node.arg == "func"
                and isinstance(node.value, ast.Name)):
            out["entries"].add(node.value.id)

    for node in tree.body:
        targets, value = [], None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                out["registered"].add(a.asname or a.name.split(".")[0])
        for target in targets:
            if isinstance(target, ast.Name):
                out["registered"].add(target.id)
        if (any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets)
                and isinstance(value, (ast.List, ast.Tuple))):
            for elt in value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    out["entries"].add(elt.value)
    return out


_JS_EXPORT_DECL = re.compile(
    r"^\s*export\s+(?:default\s+)?(?:async\s+)?(?:function\s*\*?|const|let|var|class)\s+([A-Za-z_$][\w$]*)",
    re.MULTILINE)
_JS_EXPORT_LIST = re.compile(r"\bexport\s*\{([^}]*)\}")
_JS_MODULE_EXPORTS = re.compile(r"\bmodule\.exports\s*=\s*\{([^}]*)\}")
_JS_MODULE_EXPORT_PROP = re.compile(
    r"\bmodule\.exports\.([A-Za-z_$][\w$]*)\s*=\s*([A-Za-z_$][\w$]*)?")
_JS_GLOBAL_ASSIGN = re.compile(
    r"\bwindow((?:\.[A-Za-z_$][\w$]*)+)\s*=(?!=)\s*([^\n;]*)")
_JS_IMPORT_LIST = re.compile(r"\bimport\s*\{([^}]*)\}\s*from\s*[\"']([^\"']+)[\"']")
# Object-literal members: `name: function (`, `name: async (...) =>`, `name(args) {`.
_JS_MEMBER_FUNCTION = re.compile(
    r"^\s*([A-Za-z_$][\w$]*)\s*:\s*(?:async\s+)?(?:function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)",
    re.MULTILINE)
_JS_SHORTHAND_METHOD = re.compile(
    r"^\s+(?:async\s+)?([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{", re.MULTILINE)
_JS_KEYWORDS = frozenset({"function", "async", "class", "new", "true", "false",
                          "null", "undefined", "this", "if", "for", "while",
                          "switch", "catch", "return", "else", "do", "try",
                          "with", "typeof", "await"})


def _js_list_names(body, take_value=False):
    """Names in `{a, b as c}` (local name) or `{a, b: c}` (value when take_value)."""
    names = []
    for part in body.split(","):
        part = part.strip()
        if not part:
            continue
        if take_value and ":" in part:
            part = part.split(":", 1)[1].strip()
        part = part.split(" as ", 1)[0].strip()
        if _IDENT.fullmatch(part):
            names.append(part)
    return names


def javascript_signals(source):
    """Entry points, imports and global registrations of one JavaScript text.

    `entries`: exported declarations and lists, `module.exports` members,
    and named functions assigned to a `window.<path>`. `imports`:
    `(module_stem, name)` from `import { name } from "./stem.js"`.
    `registered`: every assigned `window.<path>` and its last segment, and
    object-literal member functions, so an anonymous registration or a
    method of an exported object counts as existing code for stale checks.
    Ordinary helpers never qualify by name.
    """
    out = _empty_signals()
    for m in _JS_EXPORT_DECL.finditer(source):
        out["entries"].add(m.group(1))
    for m in _JS_EXPORT_LIST.finditer(source):
        out["entries"].update(_js_list_names(m.group(1)))
    for m in _JS_MODULE_EXPORTS.finditer(source):
        out["entries"].update(_js_list_names(m.group(1), take_value=True))
    for m in _JS_MODULE_EXPORT_PROP.finditer(source):
        out["entries"].add(m.group(1))
        if m.group(2) and m.group(2) not in _JS_KEYWORDS:
            out["entries"].add(m.group(2))
    for m in _JS_GLOBAL_ASSIGN.finditer(source):
        path = m.group(1)[1:]
        out["registered"].add(path)
        out["registered"].add(path.rsplit(".", 1)[-1])
        value = m.group(2).strip()
        if _IDENT.fullmatch(value) and value not in _JS_KEYWORDS:
            out["entries"].add(value)
    for pattern in (_JS_MEMBER_FUNCTION, _JS_SHORTHAND_METHOD):
        for m in pattern.finditer(source):
            if m.group(1) not in _JS_KEYWORDS:
                out["registered"].add(m.group(1))
    for m in _JS_IMPORT_LIST.finditer(source):
        base = m.group(2).rsplit("/", 1)[-1]
        stem = re.sub(r"\.(?:m?js|jsx|ts|tsx)$", "", base)
        for name in _js_list_names(m.group(1)):
            out["imports"].add((stem, name))
    return out


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------

def decide(name, is_private, entries, importer_owners, file_owners):
    """Return `(decision, reason)` for one public-or-private function.

    `entries`: the defining file's entry names. `importer_owners`: for each
    other file that imports this name, the charters that own it (an empty
    collection — an unowned importer — is ignored). `file_owners`: the
    charters that own the defining file.

    Decisions: `document` (reasons `entry`, `cross-module`), `internal`
    (`local`), `not-applicable` (`private`, `conventional`).
    """
    if is_private:
        return "not-applicable", "private"
    if name in CONVENTIONAL_NAMES:
        return "not-applicable", "conventional"
    if name in entries:
        return "document", "entry"
    own = set(file_owners)
    for owners in importer_owners:
        owners = set(owners)
        if owners and not (owners & own):
            return "document", "cross-module"
    return "internal", "local"
