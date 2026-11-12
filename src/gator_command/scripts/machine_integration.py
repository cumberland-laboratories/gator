"""
machine_integration.py — Gator's connection to the AI tools on this machine.

Gator's two SessionStart hooks (`gator hook session-open`,
`gator hook session-start`) live in each vendor's USER-level settings,
not in repositories:

  Claude Code  ~/.claude/settings.json
  Codex        $CODEX_HOME/hooks.json, else ~/.codex/hooks.json
  Gemini CLI   ~/.gemini/settings.json

A vendor is "present" when its home directory exists. Gator never creates
a vendor home, writes only its own entries, never touches Codex trust
state, and never overwrites a vendor or state file it cannot parse.

Machine state: ~/.gator/vendor-integration.json
(schema `gator-vendor-integration-v1`).

Every public function takes `home` and `env` (defaults: `Path.home()`,
`os.environ`) so tests use temporary homes and never touch the machine.

@reads:  vendor user settings, templates/machine/*.json, the state file
@writes: vendor user settings (Gator's entries only), the state file
"""

import copy
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "gator-vendor-integration-v1"
STATE_FILENAME = "vendor-integration.json"
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "machine"


class Vendor:
    """One supported AI tool: where its user settings live and which
    machine template holds Gator's entries for it."""

    def __init__(self, key, display, home_dir, config_name, template_name):
        self.key = key
        self.display = display
        self._home_dir = home_dir
        self.config_name = config_name
        self.template_name = template_name

    def home(self, home, env):
        return self._home_dir(Path(home), env)

    def config_path(self, home, env):
        return self.home(home, env) / self.config_name


def _codex_home(home, env):
    custom = env.get("CODEX_HOME")
    return Path(custom) if custom else home / ".codex"


# Closed list. A new vendor is a code change, not configuration.
VENDORS = (
    Vendor("claude", "Claude Code", lambda h, e: h / ".claude",
           "settings.json", "claude-settings.json"),
    Vendor("codex", "Codex", _codex_home,
           "hooks.json", "codex-hooks.json"),
    Vendor("gemini", "Gemini CLI", lambda h, e: h / ".gemini",
           "settings.json", "gemini-settings.json"),
)
VENDORS_BY_KEY = {v.key: v for v in VENDORS}


# ---------------------------------------------------------------------------
# Managed-hook grammar
# ---------------------------------------------------------------------------
#
# The ONLY commands Gator treats as its own. Every command Gator has
# shipped in a vendor hook file:
#   python .gator/scripts/gator-session-{open,start}.py
#   python .gator/.includes/scripts/gator-session-{open,start}.py
#   gator hook session-{open,start}
#   "<abs>/gator[.exe]" hook session-{open,start}   (Enterprise installer)
#   `||` chains of these with python / python3 / py -3 script fallbacks
# Everything else — other `gator hook` verbs, any other `.gator/` command,
# a chain mixing a Gator clause with anything else — is user content.
# Widening this grammar can delete user hooks machine-wide.

_SESSION_VERBS = ("open", "start")
_INTERPRETERS = (("python",), ("python3",), ("py", "-3"))
_SCRIPT_DIRS = (".gator/scripts/", ".gator/.includes/scripts/")
_LAUNCHERS = ("gator", "gator.exe")


def _hook_verb(tokens):
    """`hook session-X` exactly → X, else None."""
    if len(tokens) == 2 and tokens[0] == "hook":
        for verb in _SESSION_VERBS:
            if tokens[1] == f"session-{verb}":
                return verb
    return None


def _script_verb(tokens):
    """`<interpreter> .gator/[.includes/]scripts/gator-session-X.py` → X."""
    for interp in _INTERPRETERS:
        n = len(interp)
        if tuple(tokens[:n]) == interp and len(tokens) == n + 1:
            for script_dir in _SCRIPT_DIRS:
                for verb in _SESSION_VERBS:
                    if tokens[n] == f"{script_dir}gator-session-{verb}.py":
                        return verb
    return None


def _clause_verb(clause):
    """The session verb one clause runs, or None when it is not Gator's."""
    s = clause.strip()
    if s.startswith('"'):
        end = s.find('"', 1)
        rest = s[end + 1:] if end != -1 else ""
        if end == -1 or not rest[:1].isspace():
            return None
        exe = s[1:end].replace("\\", "/").rsplit("/", 1)[-1].lower()
        return _hook_verb(rest.split()) if exe in _LAUNCHERS else None
    tokens = s.split()
    if tokens and tokens[0] == "gator":
        return _hook_verb(tokens[1:])
    return _script_verb(tokens)


def is_gator_hook_command(cmd):
    """True only for a command in Gator's closed session-hook grammar:
    every `||` clause is a Gator clause, and all name the same session
    verb."""
    if not isinstance(cmd, str) or not cmd.strip():
        return False
    verbs = {_clause_verb(clause) for clause in cmd.split("||")}
    return len(verbs) == 1 and None not in verbs


# ---------------------------------------------------------------------------
# Templates, managed form, fingerprint
# ---------------------------------------------------------------------------

def load_template(vendor, templates_dir=None):
    path = Path(templates_dir or TEMPLATES_DIR) / vendor.template_name
    return json.loads(path.read_text(encoding="utf-8"))


def template_hooks(template):
    """The template's SessionStart hook dictionaries, in order."""
    return template["hooks"]["SessionStart"][0]["hooks"]


def managed_form(hooks):
    """Canonical form of complete hook dictionaries. The fingerprint, the
    short-circuit and the merge all compare this — never commands alone."""
    return json.dumps(list(hooks), sort_keys=True, separators=(",", ":"))


def fingerprint(template):
    return hashlib.sha256(
        managed_form(template_hooks(template)).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Pure document operations
# ---------------------------------------------------------------------------

class _Malformed(Exception):
    """The settings document's shape is not one Gator may edit."""


def _session_groups(doc, create):
    """The document's `hooks.SessionStart` list. Missing keys are created
    only when `create`; otherwise None. A wrong shape raises _Malformed."""
    if not isinstance(doc, dict):
        raise _Malformed()
    hooks = doc.get("hooks")
    if hooks is None:
        if not create:
            return None
        hooks = doc["hooks"] = {}
    if not isinstance(hooks, dict):
        raise _Malformed()
    groups = hooks.get("SessionStart")
    if groups is None:
        if not create:
            return None
        groups = hooks["SessionStart"] = []
    if not isinstance(groups, list):
        raise _Malformed()
    return groups


def _is_managed(entry):
    return isinstance(entry, dict) and is_gator_hook_command(entry.get("command"))


def _group_hooks(group):
    """A group's hook list, or None when the group is not a dict with a
    list of hooks (such a group is user content and is never edited)."""
    if isinstance(group, dict) and isinstance(group.get("hooks"), list):
        return group["hooks"]
    return None


def _managed_entries(groups):
    """[(group_index, entry)] for every managed entry, in document order."""
    found = []
    for gi, group in enumerate(groups or []):
        for entry in _group_hooks(group) or []:
            if _is_managed(entry):
                found.append((gi, entry))
    return found


def _is_exact(groups, hooks):
    """Gator's managed entries equal `hooks` and sit in one group."""
    found = _managed_entries(groups)
    return (bool(found) and len({gi for gi, _ in found}) == 1
            and managed_form([e for _, e in found]) == managed_form(hooks))


def merge_document(doc, hooks):
    """Converge `doc`'s managed SessionStart entries to `hooks` (complete
    dictionaries). Returns True when `doc` changed. User hooks, other
    groups, other events and other settings keep their order and values.
    Raises _Malformed on a shape Gator may not edit."""
    groups = _session_groups(doc, create=True)
    if _is_exact(groups, hooks):
        return False
    group_ids = {gi for gi, _ in _managed_entries(groups)}
    first = min(group_ids) if group_ids else None
    rebuilt = []
    for gi, group in enumerate(groups):
        if gi not in group_ids:
            rebuilt.append(group)
            continue
        user = [e for e in group["hooks"] if not _is_managed(e)]
        if gi == first:
            group["hooks"] = copy.deepcopy(list(hooks)) + user
            rebuilt.append(group)
        elif user:
            group["hooks"] = user
            rebuilt.append(group)
        # else: the group held only Gator's entries — dropped.
    if first is None:
        rebuilt.append({"hooks": copy.deepcopy(list(hooks))})
    groups[:] = rebuilt
    return True


def strip_managed_entries(doc):
    """Remove Gator's managed entries. Returns (doc, removed_count).

    A group left empty is dropped, then `SessionStart` if empty, then
    `hooks` if empty. Shared by `remove()` and the repository cleanup so
    the two cannot diverge. Raises _Malformed on a shape Gator may not
    edit."""
    groups = _session_groups(doc, create=False)
    if groups is None:
        return doc, 0
    removed = 0
    kept_groups = []
    for group in groups:
        entries = _group_hooks(group)
        if entries is not None:
            keep = [e for e in entries if not _is_managed(e)]
            if len(keep) != len(entries):
                removed += len(entries) - len(keep)
                if not keep:
                    continue
                group["hooks"] = keep
        kept_groups.append(group)
    if removed:
        groups[:] = kept_groups
        if not groups:
            del doc["hooks"]["SessionStart"]
        if not doc["hooks"]:
            del doc["hooks"]
    return doc, removed


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

def _read_json(path):
    """("missing", None) | ("ok", value) | ("malformed", None)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return "missing", None
    except (OSError, UnicodeDecodeError):
        return "malformed", None
    try:
        return "ok", json.loads(text)
    except ValueError:
        return "malformed", None


def _atomic_write_json(path, data):
    """Write through a temporary file in the same directory, then
    `os.replace()`, so a reader never sees a partial file."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.",
                               suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(data, indent=2) + "\n")
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def merge_hooks_into_settings(settings_path, template):
    """Converge one vendor settings file to `template`'s managed entries.

    Returns "add" (file created), "update", "unchanged" (no write) or
    "malformed" (never written). Creates no directory: callers pass only
    present vendors."""
    status, doc = _read_json(settings_path)
    if status == "malformed":
        return "malformed"
    created = status == "missing"
    if created:
        doc = {}
    try:
        changed = merge_document(doc, template_hooks(template))
    except _Malformed:
        return "malformed"
    if not changed:
        return "unchanged"
    _atomic_write_json(settings_path, doc)
    return "add" if created else "update"


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def _resolve(home, env):
    return (Path(home) if home is not None else Path.home(),
            env if env is not None else os.environ)


def state_path(home=None):
    home, _ = _resolve(home, {})
    return home / ".gator" / STATE_FILENAME


def _read_state(home):
    """("missing", None) | ("ok", dict) | ("unreadable", None). An unknown
    schema is unreadable, never treated as missing."""
    status, data = _read_json(state_path(home))
    if status == "missing":
        return "missing", None
    if (status == "ok" and isinstance(data, dict)
            and data.get("schema") == SCHEMA
            and isinstance(data.get("vendors"), dict)):
        return "ok", data
    return "unreadable", None


def _gator_version():
    try:
        from gator_core import get_version
        return get_version()
    except Exception:
        return "unknown"


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_state(home, state):
    path = state_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(path, state)


def _join_names(names):
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


# ---------------------------------------------------------------------------
# Public operations
# ---------------------------------------------------------------------------

def ensure(home=None, env=None, templates_dir=None):
    """Connect Gator to every present vendor, idempotently.

    Returns {"changed", "recorded", "codex_newly_connected", "problems",
    "messages"}. `messages` and `problems` are lines for stderr. An
    unreadable state file changes nothing at all."""
    home, env = _resolve(home, env)
    result = {"changed": [], "recorded": [], "codex_newly_connected": False,
              "problems": [], "messages": []}

    status, state = _read_state(home)
    if status == "unreadable":
        result["problems"].append(
            f"Gator: {state_path(home)} is unreadable or has an unknown "
            f"schema, so Gator did not connect any AI tool. "
            f"Reset it with: gator integration remove")
        return result
    old_vendors = dict(state["vendors"]) if state else {}

    desired = {}
    for vendor in VENDORS:
        if not vendor.home(home, env).is_dir():
            continue
        template = load_template(vendor, templates_dir)
        config = vendor.config_path(home, env)
        outcome = merge_hooks_into_settings(config, template)
        if outcome == "malformed":
            result["problems"].append(
                f"Gator: {config} could not be read as {vendor.display} "
                f"settings; Gator left it unchanged.")
            continue
        if outcome in ("add", "update"):
            result["changed"].append(vendor.key)
        fp = fingerprint(template)
        previous = old_vendors.get(vendor.key)
        same = isinstance(previous, dict) and previous.get("fingerprint") == fp
        desired[vendor.key] = {
            "config_path": str(config),
            "fingerprint": fp,
            "connected_at": (previous.get("connected_at") if same
                             and previous.get("connected_at") else _now()),
        }
        if not same:
            result["recorded"].append(vendor.key)

    # State recording is independent of vendor writes: a missing or
    # different record is written even when every vendor file was exact.
    if desired != old_vendors:
        new_state = dict(state) if state else {
            "codex_review_reminder_dismissed_for": None}
        new_state.update({"schema": SCHEMA, "gator_version": _gator_version(),
                          "vendors": desired})
        _write_state(home, new_state)

    result["codex_newly_connected"] = "codex" in result["recorded"]
    news = [VENDORS_BY_KEY[k].display for k in
            dict.fromkeys(result["recorded"] + result["changed"])]
    if news:
        result["messages"].append(f"Gator connected to {_join_names(news)}.")
    if result["codex_newly_connected"]:
        result["messages"].append(
            "In Codex, approve Gator's hook once: /hooks.")
    return result


def remove(home=None, env=None):
    """Remove Gator's entries from every vendor's settings and delete the
    state file. Does not depend on the state file. Returns a list of
    {"vendor", "path", "action"} with action deleted|stripped|malformed."""
    home, env = _resolve(home, env)
    actions = []
    for vendor in VENDORS:
        config = vendor.config_path(home, env)
        if not config.is_file():
            continue
        status, doc = _read_json(config)
        try:
            if status != "ok":
                raise _Malformed()
            doc, removed = strip_managed_entries(doc)
        except _Malformed:
            actions.append({"vendor": vendor.key, "path": str(config),
                            "action": "malformed"})
            continue
        if not removed:
            continue
        if doc == {}:
            config.unlink()
            action = "deleted"
        else:
            _atomic_write_json(config, doc)
            action = "stripped"
        actions.append({"vendor": vendor.key, "path": str(config),
                        "action": action})
    path = state_path(home)
    if path.exists():
        path.unlink()
        actions.append({"vendor": None, "path": str(path),
                        "action": "deleted"})
    return actions


def status(home=None, env=None, templates_dir=None):
    """Read-only report. `connected` is read from each vendor file; the
    state file supplies only `connected_at` and the Codex reminder."""
    home, env = _resolve(home, env)
    state_status, state = _read_state(home)
    recorded = state["vendors"] if state else {}
    vendors = {}
    for vendor in VENDORS:
        config = vendor.config_path(home, env)
        present = vendor.home(home, env).is_dir()
        connected, problem = False, None
        if present and config.is_file():
            file_status, doc = _read_json(config)
            try:
                if file_status != "ok":
                    raise _Malformed()
                groups = _session_groups(doc, create=False)
                connected = _is_exact(groups, template_hooks(
                    load_template(vendor, templates_dir)))
            except _Malformed:
                problem = "malformed"
        record = recorded.get(vendor.key)
        vendors[vendor.key] = {
            "display": vendor.display,
            "present": present,
            "connected": connected,
            "config_path": str(config),
            "problem": problem,
            "connected_at": (record.get("connected_at")
                             if isinstance(record, dict) else None),
        }
    dismissed = state.get("codex_review_reminder_dismissed_for") if state else None
    codex_fp = fingerprint(load_template(VENDORS_BY_KEY["codex"], templates_dir))
    return {
        "state": state_status,
        "state_path": str(state_path(home)),
        "vendors": vendors,
        "codex_reminder_due": vendors["codex"]["connected"] and dismissed != codex_fp,
    }


def dismiss_codex_reminder(home=None, env=None, templates_dir=None):
    """Record that the user approved Gator's Codex hook for the current
    definition. Returns False (and writes nothing) without a readable
    state file."""
    home, env = _resolve(home, env)
    state_status, state = _read_state(home)
    if state_status != "ok":
        return False
    state["codex_review_reminder_dismissed_for"] = fingerprint(
        load_template(VENDORS_BY_KEY["codex"], templates_dir))
    _write_state(home, state)
    return True
