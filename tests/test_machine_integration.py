"""
Tests for machine_integration.py — Gator's SessionStart hooks in each
vendor's user-level settings (machine-level vendor integration, CP2).

Every test uses a temporary home and an explicit env; none touches the
real machine.
"""

import json
from pathlib import Path

import pytest

from conftest import load_script

mi = load_script("machine_integration")

OPEN = "gator hook session-open"
START = "gator hook session-start"
USER_VERB = {"type": "command", "command": "gator hook override status"}
USER_GATOR_PATH = {"type": "command", "command": "python .gator/tools/mine.py"}
TIMEOUTS = {"claude": 10, "codex": 10, "gemini": 10000}
CONFIG = {"claude": (".claude", "settings.json"),
          "codex": (".codex", "hooks.json"),
          "gemini": (".gemini", "settings.json")}


def _entries(timeout):
    return [{"type": "command", "command": OPEN, "timeout": timeout},
            {"type": "command", "command": START, "timeout": timeout}]


def _home(tmp_path, *vendors):
    home = tmp_path / "home"
    home.mkdir()
    for key in vendors:
        (home / CONFIG[key][0]).mkdir()
    return home


def _cfg(home, key):
    return home / CONFIG[key][0] / CONFIG[key][1]


def _write(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _state(home):
    return _read(home / ".gator" / "vendor-integration.json")


def _session(doc):
    return doc["hooks"]["SessionStart"]


# ---------------------------------------------------------------------------
# Grammar
# ---------------------------------------------------------------------------

SHIPPED = [
    "python .gator/scripts/gator-session-open.py",
    "python .gator/scripts/gator-session-start.py",
    "python .gator/.includes/scripts/gator-session-open.py",
    "python .gator/.includes/scripts/gator-session-start.py",
    OPEN,
    START,
    "gator hook session-open || python .gator/.includes/scripts/gator-session-open.py",
    "gator hook session-start || python .gator/.includes/scripts/gator-session-start.py",
    "gator hook session-open || python .gator/.includes/scripts/gator-session-open.py"
    " || python3 .gator/.includes/scripts/gator-session-open.py"
    " || py -3 .gator/.includes/scripts/gator-session-open.py",
    '"/home/u/.local/bin/gator" hook session-open',
    '"C:\\Users\\u\\.local\\bin\\gator.exe" hook session-start',
    '"C:\\Users\\u\\.local\\bin\\GATOR.EXE" hook session-open',
]

NOT_GATOR = [
    "gator hook override status",
    "gator hook enforcer-review",
    "gator hook pre-commit",
    "gator hook session-open --x",
    "gator session-open",
    "python .gator/tools/mine.py",
    "bash .gator/x.sh",
    "python .gator/scripts/gator-session-open.py --debug",
    "node .gator/scripts/gator-session-open.py",
    "gator hook session-open || echo hi",
    "gator hook session-open || python .gator/scripts/gator-session-start.py",
    '"/usr/bin/notgator" hook session-open',
    '"/usr/bin/gator"hook session-open',
    "",
    None,
]


@pytest.mark.parametrize("cmd", SHIPPED)
def test_grammar_accepts_every_shipped_shape(cmd):
    assert mi.is_gator_hook_command(cmd)


@pytest.mark.parametrize("cmd", NOT_GATOR)
def test_grammar_rejects_user_content(cmd):
    assert not mi.is_gator_hook_command(cmd)


@pytest.mark.parametrize("key", ["claude", "codex", "gemini"])
def test_machine_templates(key):
    vendor = mi.VENDORS_BY_KEY[key]
    hooks = mi.template_hooks(mi.load_template(vendor))
    assert [h["command"] for h in hooks] == [OPEN, START]
    assert all(mi.is_gator_hook_command(h["command"]) for h in hooks)
    assert all(h["timeout"] == TIMEOUTS[key] for h in hooks)


def test_gemini_timeout_is_milliseconds():
    hooks = mi.template_hooks(mi.load_template(mi.VENDORS_BY_KEY["gemini"]))
    assert all(h["timeout"] >= 1000 for h in hooks)


def test_fingerprint_changes_when_only_a_timeout_changes():
    a = {"hooks": {"SessionStart": [{"hooks": _entries(5)}]}}
    b = {"hooks": {"SessionStart": [{"hooks": _entries(10000)}]}}
    assert mi.fingerprint(a) != mi.fingerprint(b)


# ---------------------------------------------------------------------------
# ensure()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key", ["claude", "codex", "gemini"])
def test_ensure_connects_present_vendor_only(tmp_path, key):
    home = _home(tmp_path, key)
    result = mi.ensure(home=home, env={})
    assert result["changed"] == [key]
    assert _session(_read(_cfg(home, key))) == [{"hooks": _entries(TIMEOUTS[key])}]
    for other in CONFIG:
        if other != key:
            assert not (home / CONFIG[other][0]).exists(), "vendor home created"
    assert set(_state(home)["vendors"]) == {key}


@pytest.mark.parametrize("key", ["claude", "codex", "gemini"])
def test_ensure_is_idempotent(tmp_path, key):
    home = _home(tmp_path, key)
    mi.ensure(home=home, env={})
    cfg, state = _cfg(home, key), home / ".gator" / "vendor-integration.json"
    before = (cfg.read_bytes(), state.read_bytes())
    result = mi.ensure(home=home, env={})
    assert (cfg.read_bytes(), state.read_bytes()) == before
    assert result["changed"] == [] and result["recorded"] == []
    assert result["messages"] == []


def test_ensure_honors_codex_home(tmp_path):
    home = _home(tmp_path)
    codex_home = tmp_path / "custom-codex"
    codex_home.mkdir()
    mi.ensure(home=home, env={"CODEX_HOME": str(codex_home)})
    assert (codex_home / "hooks.json").is_file()
    assert not (home / ".codex").exists()


def test_ensure_with_no_vendor_writes_nothing(tmp_path):
    home = _home(tmp_path)
    result = mi.ensure(home=home, env={})
    assert result["messages"] == []
    assert not (home / ".gator").exists()


def test_user_settings_survive(tmp_path):
    home = _home(tmp_path, "claude")
    cfg = _cfg(home, "claude")
    _write(cfg, {"permissions": {"allow": ["Bash(ls)"]}, "model": "x",
                 "hooks": {"Stop": [{"hooks": [USER_VERB]}],
                           "SessionStart": [{"matcher": "startup",
                                             "hooks": [USER_GATOR_PATH]}]}})
    mi.ensure(home=home, env={})
    doc = _read(cfg)
    assert doc["permissions"] == {"allow": ["Bash(ls)"]} and doc["model"] == "x"
    assert doc["hooks"]["Stop"] == [{"hooks": [USER_VERB]}]
    assert _session(doc) == [{"matcher": "startup", "hooks": [USER_GATOR_PATH]},
                             {"hooks": _entries(10)}]


def test_old_generation_entries_are_replaced_not_duplicated(tmp_path):
    home = _home(tmp_path, "claude")
    cfg = _cfg(home, "claude")
    legacy = [{"type": "command", "timeout": 5,
               "command": "gator hook session-open || python "
                          ".gator/.includes/scripts/gator-session-open.py"},
              {"type": "command", "timeout": 5,
               "command": '"C:\\x\\gator.exe" hook session-start'}]
    _write(cfg, {"hooks": {"SessionStart": [{"hooks": legacy + [USER_VERB]}]}})
    mi.ensure(home=home, env={})
    assert _session(_read(cfg)) == [{"hooks": _entries(10) + [USER_VERB]}]


def test_hand_deleted_entries_are_restored(tmp_path):
    home = _home(tmp_path, "claude")
    mi.ensure(home=home, env={})
    _write(_cfg(home, "claude"), {"hooks": {}})
    result = mi.ensure(home=home, env={})
    assert result["changed"] == ["claude"]
    assert _session(_read(_cfg(home, "claude"))) == [{"hooks": _entries(10)}]


# --- full-entry convergence (round 1, Finding 2) ---------------------------

def test_stale_gemini_timeout_converges(tmp_path):
    home = _home(tmp_path, "gemini")
    cfg = _cfg(home, "gemini")
    _write(cfg, {"hooks": {"SessionStart": [
        {"matcher": "*", "hooks": _entries(5) + [USER_VERB]}]}})
    result = mi.ensure(home=home, env={})
    assert result["changed"] == ["gemini"]
    assert _session(_read(cfg)) == [
        {"matcher": "*", "hooks": _entries(10000) + [USER_VERB]}]


def test_other_stale_managed_field_converges(tmp_path):
    home = _home(tmp_path, "claude")
    cfg = _cfg(home, "claude")
    stale = _entries(10)
    stale[0]["type"] = "prompt"
    _write(cfg, {"hooks": {"SessionStart": [{"hooks": stale}]}})
    mi.ensure(home=home, env={})
    assert _session(_read(cfg)) == [{"hooks": _entries(10)}]


def test_split_managed_entries_collapse_to_one_group(tmp_path):
    home = _home(tmp_path, "claude")
    cfg = _cfg(home, "claude")
    e = _entries(10)
    _write(cfg, {"hooks": {"SessionStart": [
        {"hooks": [USER_GATOR_PATH, e[0]]},
        {"hooks": [e[1]]}]}})
    mi.ensure(home=home, env={})
    assert _session(_read(cfg)) == [{"hooks": e + [USER_GATOR_PATH]}]


# --- state bootstrap (round 1, Finding 3) ----------------------------------

def test_missing_state_with_exact_files_is_bootstrapped(tmp_path, monkeypatch):
    home = _home(tmp_path, "claude", "codex")
    for key in ("claude", "codex"):
        _write(_cfg(home, key), {"hooks": {"SessionStart": [
            {"hooks": _entries(10)}]}})
    vendor_bytes = {k: _cfg(home, k).read_bytes() for k in ("claude", "codex")}
    vendor_mtimes = {k: _cfg(home, k).stat().st_mtime_ns for k in ("claude", "codex")}

    replaced = []
    real_replace = mi.os.replace
    monkeypatch.setattr(mi.os, "replace",
                        lambda a, b: (replaced.append(Path(b).name), real_replace(a, b)))

    result = mi.ensure(home=home, env={})
    assert result["changed"] == []
    assert replaced == ["vendor-integration.json"]
    for k in ("claude", "codex"):
        assert _cfg(home, k).read_bytes() == vendor_bytes[k]
        assert _cfg(home, k).stat().st_mtime_ns == vendor_mtimes[k]
    assert set(_state(home)["vendors"]) == {"claude", "codex"}

    report = mi.status(home=home, env={})
    assert report["vendors"]["claude"]["connected"]
    assert report["vendors"]["codex"]["connected"]
    assert report["codex_reminder_due"] is True
    assert result["codex_newly_connected"] is True

    replaced.clear()
    mi.ensure(home=home, env={})
    assert replaced == []


# --- malformed files ---------------------------------------------------------

@pytest.mark.parametrize("content", ["{not json", "[]", '{"hooks": []}',
                                     '{"hooks": {"SessionStart": {}}}'])
def test_malformed_vendor_file_untouched_others_proceed(tmp_path, content):
    home = _home(tmp_path, "claude", "gemini")
    bad = _cfg(home, "claude")
    bad.write_text(content, encoding="utf-8")
    result = mi.ensure(home=home, env={})
    assert bad.read_text(encoding="utf-8") == content
    assert any(str(bad) in p for p in result["problems"])
    assert set(_state(home)["vendors"]) == {"gemini"}
    assert mi.status(home=home, env={})["vendors"]["claude"]["problem"] == "malformed"


def test_malformed_vendor_file_loses_its_record(tmp_path):
    home = _home(tmp_path, "claude")
    mi.ensure(home=home, env={})
    _cfg(home, "claude").write_text("{broken", encoding="utf-8")
    mi.ensure(home=home, env={})
    assert _state(home)["vendors"] == {}


@pytest.mark.parametrize("content", ["{broken", '{"schema": "other-v9", "vendors": {}}',
                                     '{"schema": "gator-vendor-integration-v1"}'])
def test_unreadable_state_changes_nothing(tmp_path, content):
    home = _home(tmp_path, "claude")
    state = home / ".gator" / "vendor-integration.json"
    state.parent.mkdir()
    state.write_text(content, encoding="utf-8")
    result = mi.ensure(home=home, env={})
    assert state.read_text(encoding="utf-8") == content
    assert not _cfg(home, "claude").exists()
    assert result["problems"] and "gator integration remove" in result["problems"][0]
    assert mi.status(home=home, env={})["state"] == "unreadable"


def test_vendor_home_removed_drops_record(tmp_path):
    home = _home(tmp_path, "claude", "gemini")
    mi.ensure(home=home, env={})
    for p in (home / ".gemini").iterdir():
        p.unlink()
    (home / ".gemini").rmdir()
    mi.ensure(home=home, env={})
    assert set(_state(home)["vendors"]) == {"claude"}


def test_writes_are_atomic(tmp_path, monkeypatch):
    home = _home(tmp_path, "claude")
    replaced = []
    real_replace = mi.os.replace
    monkeypatch.setattr(mi.os, "replace",
                        lambda a, b: (replaced.append(Path(b).name), real_replace(a, b)))
    mi.ensure(home=home, env={})
    assert sorted(replaced) == ["settings.json", "vendor-integration.json"]
    assert not [p for p in (home / ".claude").iterdir() if p.suffix == ".tmp"]


# ---------------------------------------------------------------------------
# Preservation through every path (round 1, Finding 1)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("operation", ["ensure", "remove"])
def test_neighbouring_user_gator_commands_survive(tmp_path, operation):
    home = _home(tmp_path, "claude")
    cfg = _cfg(home, "claude")
    _write(cfg, {"hooks": {"SessionStart": [
        {"hooks": [USER_VERB] + _entries(5) + [USER_GATOR_PATH]}]}})
    getattr(mi, operation)(home=home, env={})
    hooks = _session(_read(cfg))[0]["hooks"]
    user = [h for h in hooks if h["command"] in
            (USER_VERB["command"], USER_GATOR_PATH["command"])]
    assert user == [USER_VERB, USER_GATOR_PATH]


# ---------------------------------------------------------------------------
# remove(), status(), dismiss_codex_reminder()
# ---------------------------------------------------------------------------

def test_remove_deletes_gator_only_file_and_state(tmp_path):
    home = _home(tmp_path, "claude", "codex")
    mi.ensure(home=home, env={})
    actions = mi.remove(home=home, env={})
    assert not _cfg(home, "claude").exists()
    assert not _cfg(home, "codex").exists()
    assert not (home / ".gator" / "vendor-integration.json").exists()
    assert (home / ".claude").is_dir(), "vendor home is never removed"
    assert {a["action"] for a in actions} == {"deleted"}


def test_remove_strips_mixed_file(tmp_path):
    home = _home(tmp_path, "gemini")
    cfg = _cfg(home, "gemini")
    _write(cfg, {"theme": "dark", "hooks": {"SessionStart": [
        {"hooks": _entries(5)}], "Stop": [{"hooks": [USER_VERB]}]}})
    actions = mi.remove(home=home, env={})
    assert _read(cfg) == {"theme": "dark", "hooks": {"Stop": [{"hooks": [USER_VERB]}]}}
    assert actions[0]["action"] == "stripped"


def test_remove_works_without_state_and_leaves_malformed(tmp_path):
    home = _home(tmp_path, "claude", "codex")
    _write(_cfg(home, "claude"), {"hooks": {"SessionStart": [{"hooks": _entries(10)}]}})
    _cfg(home, "codex").write_text("{broken", encoding="utf-8")
    actions = mi.remove(home=home, env={})
    assert not _cfg(home, "claude").exists()
    assert _cfg(home, "codex").read_text(encoding="utf-8") == "{broken"
    assert {(a["vendor"], a["action"]) for a in actions} == {
        ("claude", "deleted"), ("codex", "malformed")}


def test_remove_leaves_files_without_gator_entries(tmp_path):
    home = _home(tmp_path, "claude")
    cfg = _cfg(home, "claude")
    _write(cfg, {"hooks": {"SessionStart": [{"hooks": [USER_VERB]}]}})
    before = cfg.read_bytes()
    assert mi.remove(home=home, env={}) == []
    assert cfg.read_bytes() == before


def test_status_reads_connection_from_vendor_file(tmp_path):
    home = _home(tmp_path, "claude")
    report = mi.status(home=home, env={})
    assert report["state"] == "missing"
    assert report["vendors"]["claude"] == {
        "display": "Claude Code", "present": True, "connected": False,
        "config_path": str(_cfg(home, "claude")), "problem": None,
        "connected_at": None}
    assert report["vendors"]["gemini"]["present"] is False
    mi.ensure(home=home, env={})
    report = mi.status(home=home, env={})
    assert report["state"] == "ok"
    assert report["vendors"]["claude"]["connected"]
    assert report["vendors"]["claude"]["connected_at"]
    assert report["codex_reminder_due"] is False


def test_status_is_read_only(tmp_path):
    home = _home(tmp_path, "claude")
    mi.status(home=home, env={})
    assert not _cfg(home, "claude").exists()
    assert not (home / ".gator").exists()


def test_codex_reminder_due_until_dismissed_and_again_on_change(tmp_path):
    home = _home(tmp_path, "codex")
    result = mi.ensure(home=home, env={})
    assert result["codex_newly_connected"]
    assert any("/hooks" in m for m in result["messages"])
    assert mi.status(home=home, env={})["codex_reminder_due"] is True

    assert mi.dismiss_codex_reminder(home=home, env={}) is True
    assert mi.status(home=home, env={})["codex_reminder_due"] is False

    # A changed hook definition is exactly when Codex asks again.
    templates = tmp_path / "templates"
    templates.mkdir()
    for vendor in mi.VENDORS:
        data = mi.load_template(vendor)
        if vendor.key == "codex":
            for h in mi.template_hooks(data):
                h["timeout"] = 20
        _write(templates / vendor.template_name, data)
    result = mi.ensure(home=home, env={}, templates_dir=templates)
    assert result["codex_newly_connected"]
    assert mi.status(home=home, env={}, templates_dir=templates)["codex_reminder_due"] is True


def test_dismiss_without_state_writes_nothing(tmp_path):
    home = _home(tmp_path, "codex")
    assert mi.dismiss_codex_reminder(home=home, env={}) is False
    assert not (home / ".gator").exists()


def test_connected_at_kept_while_fingerprint_unchanged(tmp_path):
    home = _home(tmp_path, "claude")
    mi.ensure(home=home, env={})
    first = _state(home)["vendors"]["claude"]["connected_at"]
    _write(_cfg(home, "claude"), {})
    mi.ensure(home=home, env={})
    assert _state(home)["vendors"]["claude"]["connected_at"] == first


def test_messages_name_connected_tools(tmp_path):
    home = _home(tmp_path, "claude", "codex")
    result = mi.ensure(home=home, env={})
    assert result["messages"][0] == "Gator connected to Claude Code and Codex."
