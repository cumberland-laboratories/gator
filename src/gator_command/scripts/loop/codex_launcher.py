"""Opt-in Codex loop-participant launcher (`gator loop codex`, #37 follow-up).

Packages the verified #37 Phase 1 profile (reference note
`codex-routine-participant-profile.md`) as one explicit command. It prepares a
dedicated, loop-only `CODEX_HOME` containing exactly the verified
five-subcommand rule plus a Gator-owned trust/sandbox block in `config.toml`.

Boundaries (see scripts-loop.md):
- writes only inside the dedicated home; never reads the normal Codex home;
- never accepts, stores, prints, or passes a loop token;
- never starts, joins, or authorizes a loop;
- unfamiliar rules and config conflicts fail closed (manual-note pointer);
- approvals Codex saves after the Gator rule (#87) are kept byte-for-byte
  and listed, with recognised credentials hidden, before every launch.

This module has no imports from the loop state modules (session,
state_machine, submit, host), so it cannot affect loop authority.
"""

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from collections import namedtuple
from pathlib import Path


MANUAL_NOTE = "reference-notes/codex-routine-participant-profile.md"
VERIFIED_CODEX_VERSION = "0.144.1"

# The exact rule verified in #37 Phase 1. Must stay byte-identical (after the
# note's three-space indent is removed) to the rule in MANUAL_NOTE; pinned by
# tests/test_loop_codex_launcher.py. Written UTF-8 without a BOM, LF endings.
RULE_TEXT = (
    'prefix_rule(\n'
    '    pattern = ["gator", "loop", ["status", "wait", "submit-draft", "submit-review", "submit-implementation"]],\n'
    '    decision = "allow",\n'
    '    justification = "Gator loop participant routine commands; Gator enforces token, role, turn and candidate freshness.",\n'
    '    match = [\n'
    '        ["gator", "loop", "status", "--token", "glp_x"],\n'
    '        ["gator", "loop", "submit-review", "--token", "glp_x", "--file", "r.md", "--approve"],\n'
    '    ],\n'
    '    not_match = [\n'
    '        ["gator", "loop", "end", "--token", "glp_x"],\n'
    '        ["gator", "gatorize", "."],\n'
    '        ["git", "write-tree"],\n'
    '    ],\n'
    ')\n'
)
RULE_BYTES = RULE_TEXT.encode("utf-8")
# Earlier Gator-generated forms that may be normalized to RULE_BYTES.
KNOWN_GENERATED_RULES = frozenset({
    RULE_TEXT.replace("\n", "\r\n").encode("utf-8"),
})
RULE_FILE = "default.rules"

# Codex-saved approvals after RULE_BYTES (#87): a closed `prefix_rule` grammar.
SAVED_RULE_KEYS = frozenset({"pattern", "decision", "justification", "match", "not_match"})
SAVED_DECISIONS = ("allow", "prompt", "forbidden")
_GATOR_PATTERN = ("gator", "loop",
                  ("status", "wait", "submit-draft", "submit-review", "submit-implementation"))
SavedRule = namedtuple("SavedRule", "decision pattern shown")
SAVED_SANDBOX_NOTE = (
    "  These commands are outside the Codex sandbox with your full user rights.\n"
    "  They were saved by Codex in this dedicated home; Gator did not create them."
)
SAVED_LIMIT_NOTE = (
    "  Gator hides the credentials it recognises; a secret with no marker is shown as saved."
)

# Credential display policy: names whose values are never shown.
REDACTED = "<redacted>"
_SENSITIVE = re.compile(
    r"auth|bearer|basic|token|password|passwd|pwd|secret|api[-_]?key|cookie|credential|session",
    re.IGNORECASE)
_GLP = re.compile(r"glp_[A-Za-z0-9_=-]+")
_USERINFO = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*://)[^/@\s]+@")
_ASSIGN = re.compile(r"^(-{0,2}[^=\s]+)=(.*)$")
_FLAG = re.compile(r"^-{1,2}[A-Za-z][\w-]*$")
_HEADER = re.compile(r"^([A-Za-z][\w-]*):(.*)$")
_SCRIPT_VALUE = re.compile(r"([^\s'\"`;&|()]+)([;&|)]*)")
_SCRIPT_BREAK = re.compile(r"[;&|\n'\"`]")

TRUST_WARNING = (
    "  Trust cost: in this Codex session, `gator loop status | wait | submit-draft |\n"
    "  submit-review | submit-implementation` and every process they start (including\n"
    "  Gator's Git calls) run OUTSIDE the Codex sandbox with your full user rights,\n"
    "  without a prompt. Everything else stays subject to normal Codex policy.\n"
    "  Gator still enforces the token, role, turn and candidate freshness."
)
SANDBOX_TEMP_NOTE = (
    "  Tests: TEMP and TMP point at the sandbox temp root for every command in this\n"
    "  session, so pytest runs inside the sandbox without a prompt. A command you approve\n"
    "  to run outside the sandbox gets the same TEMP and cannot use pytest's shared folder\n"
    "  there, so run tests sandboxed."
)
SIGN_IN_NOTE = (
    "  Codex will ask you to sign in for this isolated Gator Loop profile.\n"
    "  Sign in there, then continue in the same session."
)

# (argv after `--`, expected) for the per-launch policy proof. Literal
# placeholder arguments only; no real token is ever passed.
POLICY_PROBES = (
    (["gator", "loop", "status", "--token", "x"], "allow"),
    (["git", "write-tree"], "no-match"),
    (["gator", "loop", "end", "--token", "x"], "no-match"),
)

BLOCK_BEGIN = "# BEGIN GATOR LOOP PROFILE — managed by `gator loop codex`; edit outside this block only"
BLOCK_END = "# END GATOR LOOP PROFILE"
_PROJECT_HEADER = re.compile(r"^\[projects\.'(?P<key>[^'\r\n]*)'\]$")
_TABLE_HEADER = re.compile(r"^\[\[?[^\[\],=]+\]\]?\s*(#.*)?$")
# Gator-owned tables inside the block and the only lines each may hold.
_GATOR_TABLES = {
    "[windows]": re.compile(r'^sandbox = "elevated"$'),
    "[shell_environment_policy.set]": re.compile(r"^(TEMP|TMP) = '[^'\r\n]*'$"),
    "[sandbox_workspace_write]": re.compile(r"^writable_roots = \['[^'\r\n]*'\]$"),
}
_PROJECT_BODY = re.compile(r'^trust_level = "trusted"$')
# Tables a user may not set outside the block (Windows), because Gator owns them.
_GATOR_OWNED_OUTSIDE = re.compile(
    r"^(\[\s*(windows|shell_environment_policy|sandbox_workspace_write)\b"
    r"|(windows|shell_environment_policy|sandbox_workspace_write)\s*\.)")

_BOM = b"\xef\xbb\xbf"


class ProfileError(Exception):
    """A refusal with a user-facing message. Nothing has been written."""

    def __init__(self, message):
        super().__init__(f"{message}\n  Manual setup and recovery: {MANUAL_NOTE}")


# ---------------------------------------------------------------------------
# Home and trust key
# ---------------------------------------------------------------------------

def default_home():
    """Machine-local default dedicated home (user-private, never repo content)."""
    return Path.home() / ".gator" / "adapters" / "codex" / "loop-home"


def _norm(path):
    return os.path.normcase(str(Path(path).expanduser().resolve(strict=False)))


def _within(child, parent):
    child, parent = _norm(child), _norm(parent)
    return child == parent or child.startswith(parent.rstrip("\\/") + os.sep)


def validate_home(home, repo_root, env, tempdir=None):
    """Return the resolved dedicated home, or raise ProfileError.

    Refuses the normal Codex home (`~/.codex` or the caller's CODEX_HOME), a
    home inside the governed repository, and a home under the temp directory
    (Codex refuses to create its helpers there). Read-only.
    """
    home = Path(home).expanduser().resolve(strict=False)
    normal_homes = [Path.home() / ".codex"]
    if env.get("CODEX_HOME"):
        normal_homes.append(Path(env["CODEX_HOME"]))
    for normal in normal_homes:
        if _within(home, normal):
            raise ProfileError(
                f"Refusing to use {home}: it is (inside) your normal Codex home {normal}. "
                "The loop rule must live in a dedicated home only.")
    if _within(home, repo_root):
        raise ProfileError(
            f"Refusing to use {home}: it is inside the repository {repo_root}. "
            "The dedicated home is machine-local state, never repository content.")
    temp = tempdir if tempdir is not None else tempfile.gettempdir()
    if _within(home, temp):
        raise ProfileError(
            f"Refusing to use {home}: it is under the temp directory {temp}, "
            "where Codex refuses to create its helpers.")
    return home


def _is_link(path):
    """True for a symlink or any Windows reparse point (junctions included)."""
    try:
        st = os.lstat(path)
    except OSError:
        return False
    return Path(path).is_symlink() or bool(getattr(st, "st_file_attributes", 0) & 0x400)


def validate_temp_root(root, home, repo_root, env, tempdir=None):
    """Return the sandbox temp root, or raise ProfileError. Read-only.

    The root becomes a sandbox-writable location, so a validated home is not
    proof that its sibling is safe. Refuses a symlink or junction, and any
    overlap (either direction) with the repository, the dedicated home, the
    normal Codex home, the caller's CODEX_HOME, or the temp directory.
    """
    root = Path(root)
    if _is_link(root):
        raise ProfileError(
            f"Refusing sandbox temp root {root}: it is a link or junction, so Gator cannot "
            "tell where the sandbox would be allowed to write.")
    protected = [("the repository", repo_root), ("the dedicated home", home),
                 ("your normal Codex home", Path.home() / ".codex"),
                 ("the temp directory", tempdir if tempdir is not None else tempfile.gettempdir())]
    if env.get("CODEX_HOME"):
        protected.append(("your CODEX_HOME", Path(env["CODEX_HOME"])))
    for name, path in protected:
        if _within(root, path) or _within(path, root):
            raise ProfileError(
                f"Refusing sandbox temp root {root}: it overlaps {name} ({path}). "
                "Use --home so that its sibling '<home>.sandbox-tmp' is a separate folder.")
    return root


def trust_key(repo_root, platform):
    """The `[projects.'<key>']` key for the repository.

    Windows: the form Codex itself writes (spike §8.8) — backslashes,
    lowercase, no `\\\\?\\` prefix. Elsewhere: the resolved POSIX path.
    """
    path = str(Path(repo_root).resolve(strict=False))
    if platform == "win32":
        path = path.replace("/", "\\")
        if path.startswith("\\\\?\\"):
            path = path[4:]
        path = path.lower()
    if "'" in path or "\n" in path or "\r" in path:
        raise ProfileError(
            f"Repository path {path!r} cannot be written as a literal TOML key.")
    return path


# ---------------------------------------------------------------------------
# config.toml: one Gator-owned block, always last
# ---------------------------------------------------------------------------

def _split_block(lines):
    """Return (outside_lines, block_keys, codex_lines) or raise.

    `lines` keep their own terminators, and the returned lines are the same
    objects, so retained content is never re-encoded.

    Inside the markers, `[projects.'<key>']` and the `_GATOR_TABLES` headers
    (`[windows]`, the sandbox temp-root tables) are Gator's and may hold only
    Gator's own lines, blanks and comments.
    Every other table section (header up to the next header) was written by
    Codex, which appends at the end of the file (#87 spike E5); it is
    returned verbatim, in order, for relocation above the block. Raises on
    malformed markers, a key before the first header, or an extra key in a
    Gator table: the owner is ambiguous.
    """
    begins = [i for i, l in enumerate(lines) if l.strip() == BLOCK_BEGIN]
    ends = [i for i, l in enumerate(lines) if l.strip() == BLOCK_END]
    if not begins and not ends:
        return list(lines), [], []
    if len(begins) != 1 or len(ends) != 1 or ends[0] < begins[0]:
        raise ProfileError(
            "config.toml has a malformed Gator loop profile block "
            "(missing, duplicated, or misordered markers).")
    b, e = begins[0], ends[0]
    keys, codex, owner = [], [], None
    for line in lines[b + 1:e]:
        text = line.strip()
        if _TABLE_HEADER.match(text):
            m = _PROJECT_HEADER.match(text)
            if m:
                owner = "projects"
                keys.append(m.group("key"))
            elif text in _GATOR_TABLES:
                owner = text
            else:
                owner = "codex"
        if owner == "codex":
            codex.append(line)
        elif text and not text.startswith("#") and not _TABLE_HEADER.match(text):
            if owner is None:
                raise ProfileError(
                    "config.toml has a setting inside the Gator loop profile block before "
                    "any table; Gator cannot tell who owns it, so it will not edit the file.")
            body = _PROJECT_BODY if owner == "projects" else _GATOR_TABLES[owner]
            if not body.match(text):
                shown = "[projects…]" if owner == "projects" else owner
                raise ProfileError(
                    f"config.toml has a setting Gator does not own inside its {shown} "
                    "table in the Gator loop profile block; move it outside the block.")
    while codex and not codex[-1].strip():
        codex.pop()
    return lines[:b] + lines[e + 1:], keys, codex


def _outside_conflicts(outside, repo_key, platform):
    fold = (lambda s: s.lower()) if platform == "win32" else (lambda s: s)
    for line in outside:
        text = line.strip()
        if platform == "win32" and _GATOR_OWNED_OUTSIDE.match(text):
            return f"a user-managed setting Gator owns exists outside the Gator block: {text!r}"
        if text.startswith("[projects") and fold(repo_key) in fold(text):
            return f"a user-managed trust entry for this repository exists outside the Gator block: {text!r}"
    return None


def sandbox_temp_root(home):
    """The sandbox temp root: a sibling of the dedicated home (#87 spike Q2).

    Inside the home, every test temp path would fall under CODEX_HOME and the
    launcher's own home check would refuse it. The sibling is not safe by
    construction: `validate_temp_root` checks it before anything is planned.
    """
    home = Path(home)
    return home.parent / (home.name + ".sandbox-tmp")


def render_config(existing_text, repo_key, platform, temp_root=None):
    """Return the new config.toml text. Pure; raises ProfileError on conflict.

    Every byte outside the Gator block is kept; the block is regenerated at
    the end of the file with the union of its trusted repositories and the
    current one, plus `[windows] sandbox = "elevated"` on Windows. With
    `temp_root` (Windows), the block also sets TEMP/TMP for the session's
    commands and makes that root a sandbox writable root. Tables Codex wrote
    inside the block are moved, unchanged, to just above it.
    """
    nl = "\r\n" if "\r\n" in existing_text else "\n"
    # Keep each retained line's own terminator; only Gator's block uses `nl`.
    lines = existing_text.splitlines(keepends=True)
    outside, keys, codex = _split_block(lines)
    while outside and not outside[-1].strip():
        outside.pop()
    if codex:
        outside = _terminated(outside, nl) + ([nl] if outside else []) + _terminated(codex, nl)
    conflict = _outside_conflicts(outside, repo_key, platform)
    if conflict:
        raise ProfileError(f"Refusing to edit config.toml: {conflict}.")
    if repo_key not in keys:
        keys.append(repo_key)
    for key in keys:
        if "'" in key:
            raise ProfileError("config.toml Gator block holds an unquotable key.")

    block = [BLOCK_BEGIN]
    if platform == "win32":
        block += ["[windows]", 'sandbox = "elevated"', ""]
        if temp_root is not None:
            root = str(temp_root)
            if "'" in root or "\n" in root or "\r" in root:
                raise ProfileError(f"Sandbox temp root {root!r} cannot be written as a TOML literal.")
            block += ["[shell_environment_policy.set]", f"TEMP = '{root}'", f"TMP = '{root}'", "",
                      "[sandbox_workspace_write]", f"writable_roots = ['{root}']", ""]
    for key in keys:
        block += [f"[projects.'{key}']", 'trust_level = "trusted"', ""]
    if block[-1] == "":
        block.pop()
    block.append(BLOCK_END)

    while outside and not outside[-1].strip():
        outside.pop()
    kept = "".join(_terminated(outside, nl)) + (nl if outside else "")
    text = kept + "".join(line + nl for line in block)
    _parse_check(text, existing_text, keys)
    return text


def _terminated(lines, nl):
    """`lines` (with their own terminators) where the last one ends a line."""
    if lines and not lines[-1].endswith(("\n", "\r")):
        return lines[:-1] + [lines[-1] + nl]
    return list(lines)


def _without_gator(data, keys):
    """Parsed config minus the tables Gator regenerates."""
    data = dict(data)
    for table in ("windows", "shell_environment_policy", "sandbox_workspace_write"):
        data.pop(table, None)  # Gator-owned; a user copy outside the block is refused
    projects = {k: v for k, v in data.get("projects", {}).items() if k not in keys}
    data.pop("projects", None)
    if projects:
        data["projects"] = projects
    return data


def _parse_check(text, existing_text="", keys=()):
    """On Python >= 3.11, prove the rendered file is valid TOML and that every
    setting Gator does not own parses to the same value as before."""
    try:
        import tomllib
    except ImportError:  # 3.9 / 3.10: the closed generator + scan is the guard
        return
    try:
        new = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ProfileError(f"config.toml would not be valid TOML ({exc}); not writing it.")
    try:
        old = tomllib.loads(existing_text)
    except tomllib.TOMLDecodeError:
        raise ProfileError("config.toml is not valid TOML now; not editing it.")
    if _without_gator(old, keys) != _without_gator(new, keys):
        raise ProfileError(
            "Moving Codex settings out of the Gator block would change their meaning; "
            "not writing config.toml.")


# ---------------------------------------------------------------------------
# Codex-saved approvals after the Gator rule (#87)
# ---------------------------------------------------------------------------

def _hide(word):
    """A credential value inside a script, hidden, or None when its extent is
    ambiguous. Only one unquoted word qualifies; a trailing shell separator is
    kept so a following command stays visible."""
    m = _SCRIPT_VALUE.fullmatch(word)
    return REDACTED + m.group(2) if m else None


def _safe_text(text, pending):
    """Apply the credential display policy to one pattern string.

    Returns (shown, pending) or None when the string cannot be shown safely.
    `pending` means a credential flag came last, so this whole argument is
    its value and is hidden whole. Inside a string, a value must be one
    unquoted word (`_hide`), and a `Name:` header must be the string's first
    word with no shell separator or quote after it; otherwise None.
    """
    if pending:
        return REDACTED, False
    out, seen = [], False
    parts = re.split(r"(\s+)", text)
    for j, part in enumerate(parts):
        if not part or part.isspace():
            out.append(part)
            continue
        first, seen = not seen, True
        word = _USERINFO.sub(r"\1" + REDACTED + "@", _GLP.sub("glp_" + REDACTED, part))
        if pending:
            hidden = _hide(word)
            if hidden is None:
                return None
            out.append(hidden)
            pending = False
            continue
        m = _ASSIGN.match(word)
        if m and _SENSITIVE.search(m.group(1)):
            hidden = _hide(m.group(2))
            if hidden is None:
                return None
            out.append(f"{m.group(1)}={hidden}")
            continue
        if _FLAG.match(word) and _SENSITIVE.search(word):
            out.append(word)
            pending = True
            continue
        m = _HEADER.match(word)
        if m and _SENSITIVE.search(m.group(1)) and "//" not in m.group(2):
            rest = m.group(2) + "".join(parts[j + 1:])
            if not first or not rest.strip() or _SCRIPT_BREAK.search(rest):
                return None
            return f"{m.group(1)}: {REDACTED}", False
        if word.lower() in ("bearer", "basic"):
            out.append(word)
            pending = True
            continue
        out.append(word)
    return "".join(out), pending


def _safe_pattern(pattern):
    """The pattern as shown under the credential display policy, or None.

    A credential flag that ends an element hides the whole next element;
    inside a `powershell -Command` script it hides the next unquoted word.
    None (unrenderable) when the program element itself would be hidden, a
    value-taking form ends the stream, or a script value is ambiguous.
    """
    shown, pending = [], False
    for i, el in enumerate(pattern):
        alts = el if isinstance(el, tuple) else (el,)
        results = [_safe_text(alt, pending) for alt in alts]
        if any(r is None for r in results):
            return None
        if i == 0 and any(r[0] != alt for r, alt in zip(results, alts)):
            return None
        pending = any(r[1] for r in results)
        texts = [r[0] for r in results]
        shown.append(texts if isinstance(el, tuple) else texts[0])
    return None if pending else shown


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _strings(v)


def _is_argv(value, allow_alternatives):
    """A non-empty list of strings (or, for a pattern, of string lists)."""
    if not isinstance(value, list) or not value:
        return False
    for el in value:
        if isinstance(el, str):
            continue
        if not (allow_alternatives and isinstance(el, list) and el
                and all(isinstance(a, str) for a in el)):
            return False
    return True


def _saved_rule(stmt):
    """One top-level statement -> SavedRule, or a fixed-text reason string."""
    call = stmt.value if isinstance(stmt, ast.Expr) else None
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
            and call.func.id == "prefix_rule"):
        return "it is not a prefix_rule(...) call"
    if call.args or any(kw.arg is None for kw in call.keywords):
        return "it has positional or ** arguments"
    names = [kw.arg for kw in call.keywords]
    if len(set(names)) != len(names) or not set(names) <= SAVED_RULE_KEYS:
        return "it has a duplicate or unknown argument"
    if not {"pattern", "decision"} <= set(names):
        return "it has no pattern or no decision"
    try:
        values = {kw.arg: ast.literal_eval(kw.value) for kw in call.keywords}
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return "an argument is not a literal"
    if values["decision"] not in SAVED_DECISIONS:
        return "its decision is not allow, prompt or forbidden"
    if not _is_argv(values["pattern"], allow_alternatives=True):
        return "its pattern is not a list of strings"
    if not isinstance(values.get("justification", ""), str):
        return "its justification is not a string"
    for key in ("match", "not_match"):
        examples = values.get(key, [])
        if not (isinstance(examples, list)
                and all(isinstance(e, str) or _is_argv(e, False) for e in examples)):
            return f"its {key} is not a list of examples"
    for s in _strings(list(values.values())):
        if any(unicodedata.category(c) in ("Cc", "Cf") for c in s):
            return "it holds a control or invisible formatting character"
    pattern = tuple(tuple(el) if isinstance(el, list) else el for el in values["pattern"])
    if pattern == _GATOR_PATTERN:
        return "it repeats Gator's own rule"
    shown = _safe_pattern(pattern)
    if shown is None:
        return "Gator cannot show it without exposing a credential"
    return SavedRule(values["decision"], pattern, shown)


def parse_saved_rules(suffix, rule_path):
    """Parse the bytes after RULE_BYTES into SavedRule records. Pure.

    Accepts only complete `prefix_rule(...)` calls with literal arguments
    (comments and blank lines allowed); nothing is evaluated. Raises
    ProfileError naming only the approval's position, never its text.
    """
    def refuse(reason):
        return ProfileError(
            f"{rule_path} has content after Gator's rule that is not a readable "
            f"Codex-saved approval ({reason}). Gator will not launch with a permission "
            "rule it cannot read and show safely; remove that content.")

    try:
        text = suffix.decode("utf-8")
    except UnicodeDecodeError:
        raise refuse("not UTF-8")
    try:
        tree = ast.parse(text, mode="exec")
    except (SyntaxError, ValueError) as exc:
        line = getattr(exc, "lineno", None)
        raise refuse("a syntax error" + (f" near line {line} after Gator's rule" if line else ""))
    rules = []
    for n, stmt in enumerate(tree.body, 1):
        rule = _saved_rule(stmt)
        if isinstance(rule, str):
            raise refuse(f"saved approval {n} of {len(tree.body)}: {rule}")
        rules.append(rule)
    return tuple(rules)


def render_saved_rules(saved):
    """Disclosure lines for the kept saved approvals. Pure; empty when none."""
    if not saved:
        return []
    lines = ["  saved approvals (kept; saved by Codex in this home, not by Gator):"]
    for rule in saved:
        lines.append(f"    {rule.decision:<9} {json.dumps(rule.shown, ensure_ascii=False)}")
    if any(rule.decision == "allow" for rule in saved):
        lines += SAVED_SANDBOX_NOTE.splitlines()
    lines += SAVED_LIMIT_NOTE.splitlines()
    return lines


def saved_rules_of(actions):
    """The SavedRule records planned for `rules/default.rules`, or ()."""
    for act in actions:
        if act["path"].name == RULE_FILE and act["path"].parent.name == "rules":
            return act.get("saved", ())
    return ()


# ---------------------------------------------------------------------------
# Plan / apply
# ---------------------------------------------------------------------------

def plan_preparation(home, repo_root, platform):
    """Return the ordered preparation actions. Read-only.

    Each action is a dict: {"action": "mkdir"|"write"|"keep", "path": Path,
    "content": bytes|None}; the rule-file action also carries "saved", the
    SavedRule records Codex appended after RULE_BYTES (kept, never
    rewritten). Raises ProfileError (nothing written) when the home holds an
    unfamiliar rule, extra rule files, or a conflicting config.
    """
    home = Path(home)
    rules_dir = home / "rules"
    rule_path = rules_dir / RULE_FILE
    config_path = home / "config.toml"
    actions = []

    temp_root = sandbox_temp_root(home) if platform == "win32" else None
    for d in (home, rules_dir, temp_root):
        if d is None:
            continue
        if d.exists() and not d.is_dir():
            raise ProfileError(f"{d} exists and is not a directory.")
        actions.append({"action": "keep" if d.is_dir() else "mkdir", "path": d, "content": None})

    if rules_dir.is_dir():
        extra = sorted(p.name for p in rules_dir.iterdir() if p.name != RULE_FILE)
        if extra:
            raise ProfileError(
                f"{rules_dir} contains files Gator did not write ({', '.join(extra)}). "
                "Codex may load them and widen the allow-list.")
    if rule_path.exists():
        current = rule_path.read_bytes()
        if current == RULE_BYTES:
            actions.append({"action": "keep", "path": rule_path, "content": None, "saved": ()})
        elif current in KNOWN_GENERATED_RULES:
            actions.append({"action": "write", "path": rule_path, "content": RULE_BYTES,
                            "saved": ()})
        elif current.startswith(RULE_BYTES):
            saved = parse_saved_rules(current[len(RULE_BYTES):], rule_path)
            actions.append({"action": "keep", "path": rule_path, "content": None,
                            "saved": saved})
        else:
            raise ProfileError(
                f"{rule_path} is not the rule Gator generates, followed only by "
                "Codex-saved prefix_rule approvals (unfamiliar or edited rule). "
                "Gator will not overwrite a permission rule it does not recognize.")
    else:
        actions.append({"action": "write", "path": rule_path, "content": RULE_BYTES,
                        "saved": ()})

    existing = config_path.read_bytes() if config_path.exists() else b""
    if existing.startswith(_BOM):  # Codex expects UTF-8 without a BOM
        existing = existing[len(_BOM):]
    try:
        existing_text = existing.decode("utf-8")
    except UnicodeDecodeError:
        raise ProfileError(f"{config_path} is not UTF-8; not editing it.")
    new = render_config(existing_text, trust_key(repo_root, platform), platform,
                        temp_root=temp_root).encode("utf-8")
    if config_path.exists() and config_path.read_bytes() == new:
        actions.append({"action": "keep", "path": config_path, "content": None})
    else:
        actions.append({"action": "write", "path": config_path, "content": new})
    return actions


def apply_preparation(actions):
    """Execute exactly the planned actions (UTF-8 bytes, atomic replace)."""
    for act in actions:
        path = act["path"]
        if act["action"] == "mkdir":
            path.mkdir(parents=True, exist_ok=True)
        elif act["action"] == "write":
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".gator-tmp")
            tmp.write_bytes(act["content"])
            os.replace(tmp, path)


def render_dry_run(actions, home, repo_root, platform):
    """Human-readable preview of what a real launch would do. Pure."""
    key = trust_key(repo_root, platform)
    lines = [
        "  gator loop codex (dry run) — nothing is written or launched",
        "",
        f"  dedicated CODEX_HOME: {home}",
        f"  repository:           {repo_root}",
        f"  trust entry:          [projects.'{key}'] trust_level = \"trusted\"",
    ]
    if platform == "win32":
        lines += [f"  sandbox temp root:    {sandbox_temp_root(home)}", SANDBOX_TEMP_NOTE]
    lines += [
        "",
        "  planned actions:",
    ]
    for act in actions:
        lines.append(f"    {act['action']:<5} {act['path']}")
    lines += ["", f"  rule ({Path(home) / 'rules' / RULE_FILE}):", ""]
    lines += [f"    {l}" for l in RULE_TEXT.splitlines()]
    saved = render_saved_rules(saved_rules_of(actions))
    if saved:
        lines += [""] + saved
    lines += [
        "",
        f"  launch: codex (from PATH), cwd={repo_root}, CODEX_HOME={home} for that process only",
        "  remove later by deleting the dedicated home directory.",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Verification and launch
# ---------------------------------------------------------------------------

def child_env(env, home):
    """A copy of `env` with CODEX_HOME set. The caller's mapping is untouched."""
    out = dict(env)
    out["CODEX_HOME"] = str(home)
    return out


def codex_version(codex, run):
    """Return the `x.y.z` Codex version string, or None if it cannot be read."""
    try:
        res = run([codex, "--version"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"(\d+\.\d+\.\d+)", (res.stdout or "") + (res.stderr or ""))
    return m.group(1) if m else None


def _policy_result(data):
    """(decision, matched prefixes) from execpolicy JSON, or None when the
    shape or a decision value is not the known one. Nothing else is read."""
    if not isinstance(data, dict) or not isinstance(data.get("matchedRules"), list):
        return None
    decision = data.get("decision")
    if decision is not None and decision not in SAVED_DECISIONS:
        return None
    prefixes = []
    for rule in data["matchedRules"]:
        match = rule.get("prefixRuleMatch") if isinstance(rule, dict) else None
        prefix = match.get("matchedPrefix") if isinstance(match, dict) else None
        if not (isinstance(prefix, list) and prefix and all(isinstance(p, str) for p in prefix)):
            return None
        if match.get("decision") not in SAVED_DECISIONS:
            return None
        prefixes.append(tuple(prefix))
    return decision, prefixes


def _matches(pattern, argv):
    """Local prefix match, for naming a culprit only (Codex stays the authority)."""
    if len(pattern) > len(argv):
        return False
    return all(arg in el if isinstance(el, tuple) else arg == el
               for el, arg in zip(pattern, argv))


def _shown(pattern):
    shown = _safe_pattern(pattern)
    return json.dumps(shown, ensure_ascii=False) if shown is not None else "(a prefix Gator cannot show safely)"


def check_policy(codex, rules_path, env, run, saved=(), shown_path=None):
    """Prove the rule boundary with `codex execpolicy check`, or raise.

    `gator loop status` must be allowed; `git write-tree` and `gator loop end`
    must match no rule. Any other result, a non-zero exit, or unparseable
    output raises ProfileError before launch. Codex output is never echoed:
    only a validated decision and matched prefixes (through the credential
    display policy) are shown, and a failure names the saved approval that
    matches the probe. `shown_path` is the rule file named in messages (the
    probes may run on a temporary copy of it).
    """
    shown_path = shown_path or rules_path
    for argv, expected in POLICY_PROBES:
        cmd = [codex, "execpolicy", "check", "--rules", str(rules_path), "--", *argv]
        shown = " ".join(argv)
        manual = (f"To see the details, run: codex execpolicy check --rules {shown_path} "
                  f"-- {shown}")
        try:
            res = run(cmd, capture_output=True, text=True, env=env, timeout=120)
        except (OSError, subprocess.SubprocessError) as exc:
            raise ProfileError(
                f"`codex execpolicy check` could not run for `{shown}` ({type(exc).__name__}).")
        if res.returncode != 0:
            raise ProfileError(
                f"`codex execpolicy check` failed for `{shown}` (exit {res.returncode}); "
                f"details not shown. {manual}")
        try:
            result = _policy_result(json.loads(res.stdout))
        except (TypeError, ValueError):
            result = None
        if result is None:
            raise ProfileError(
                f"`codex execpolicy check` printed unexpected output for `{shown}` (not shown). "
                f"{manual}")
        decision, prefixes = result
        ok = decision == "allow" if expected == "allow" else prefixes == []
        if ok:
            continue
        message = (
            f"Rule boundary check failed: `{shown}` should be "
            f"{'allowed' if expected == 'allow' else 'unmatched'}; Codex reports decision "
            f"{decision or 'none'} from {', '.join(_shown(p) for p in prefixes) or 'no rule'}.")
        culprits = [(i, rule) for i, rule in enumerate(saved, 1) if _matches(rule.pattern, argv)]
        for i, rule in culprits:
            message += (f" It matches saved approval {i} of {len(saved)}: "
                        f"{rule.decision} {_shown(rule.pattern)}.")
        if culprits:
            message += f" Remove or narrow that saved approval in {shown_path}, then rerun."
        raise ProfileError(message)


def planned_rule_bytes(actions):
    """The exact `default.rules` bytes Codex will load after preparation."""
    for act in actions:
        if act["path"].name == RULE_FILE and act["path"].parent.name == "rules":
            return act["content"] if act["action"] == "write" else act["path"].read_bytes()
    raise ProfileError("No rule-file action was planned.")


def launch(codex, repo_root, env, run):
    """Run interactive Codex with `env` (already holding CODEX_HOME). Returns its exit code."""
    return run([codex], cwd=str(repo_root), env=env).returncode


def main(args, *, env=None, platform=None, which=shutil.which, run=subprocess.run,
         cwd=None, tempdir=None):
    """`gator loop codex [--dry-run] [--home PATH]`. Returns an exit code."""
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    try:
        from gator_core import find_gator_root
        repo_root = find_gator_root(cwd)
        if repo_root is None:
            raise ProfileError("Not inside a Gator-governed repository (no .gator/ found).")
        if platform != "win32":
            raise ProfileError(
                f"`gator loop codex` is verified only on Windows; this platform is {platform}. "
                "Use the manual setup and its validation checklist.")
        home = validate_home(getattr(args, "home", None) or default_home(), repo_root, env,
                             tempdir=tempdir)
        validate_temp_root(sandbox_temp_root(home), home, repo_root, env, tempdir=tempdir)
        actions = plan_preparation(home, repo_root, platform)
        if getattr(args, "dry_run", False):
            sys.stdout.write(render_dry_run(actions, home, repo_root, platform))
            return 0

        codex = which("codex")
        if not codex:
            raise ProfileError("`codex` was not found on PATH. Install Codex CLI first.")
        version = codex_version(codex, run)
        if version != VERIFIED_CODEX_VERSION:
            print(f"  warning: Codex {version or 'version unknown'} is unverified "
                  f"(verified: {VERIFIED_CODEX_VERSION}); the rule boundary is re-checked below.")

        # Prove the exact file Codex will load before anything is written.
        launch_env = child_env(env, home)
        rule_path = home / "rules" / RULE_FILE
        with tempfile.TemporaryDirectory() as probe_dir:
            probe_rules = Path(probe_dir) / RULE_FILE
            probe_rules.write_bytes(planned_rule_bytes(actions))
            check_policy(codex, probe_rules, launch_env, run,
                         saved=saved_rules_of(actions), shown_path=rule_path)
        apply_preparation(actions)
    except ProfileError as exc:
        print(f"  gator loop codex: {exc}", file=sys.stderr)
        return 1

    key = trust_key(repo_root, platform)
    print(f"  dedicated CODEX_HOME: {home}")
    print(f"  trusted repository:   [projects.'{key}']")
    print("  rule boundary:        verified (status allowed; git write-tree and loop end unmatched)")
    print(f"  sandbox temp root:    {sandbox_temp_root(home)}")
    print(TRUST_WARNING)
    print(SANDBOX_TEMP_NOTE)
    for line in render_saved_rules(saved_rules_of(actions)):
        print(line)
    auth = home / "auth.json"
    if not auth.exists():
        print(SIGN_IN_NOTE)
    print("  Next: run `gator loop join` with your role prompt, then optionally `/goal`.")
    sys.stdout.flush()

    rc = launch(codex, repo_root, launch_env, run)
    if rc != 0 and not auth.exists():
        print(f"  Codex exited ({rc}) without a sign-in for CODEX_HOME={home}.", file=sys.stderr)
        print("  Recovery: in a new terminal, set CODEX_HOME to that path for that terminal only "
              "and run `codex login`, then rerun `gator loop codex`.", file=sys.stderr)
    return rc
