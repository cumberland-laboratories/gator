"""
Repository vendor cleanup (machine-level vendor integration, CP4).

Gator keeps no AI-tool files in repositories. `gatorize` writes none, and
`gator update` removes what earlier versions left: Gator's hook entries in
`.claude/settings.json`, `.codex/hooks.json`, `.gemini/settings.json`, and
the four retired command files when their content is a shipped version.
User-owned content stays.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import load_script

cleanup = load_script("vendor_cleanup", search_dir=Path(__file__).parent.parent
                      / "src" / "gator_command" / "scripts" / "gatorize")

PACKAGE_ROOT = Path(__file__).parent.parent / "src" / "gator_command"
PACKAGE_UPDATE = PACKAGE_ROOT / "scripts" / "gator-update.py"
TEMPLATE_UPDATE = PACKAGE_ROOT / "templates" / "gator-starter" / "scripts" / "gator-update.py"

# The last shipped `update.md` (2026-11-08 … 2026-11-11), verbatim.
SHIPPED_UPDATE_MD = (
    "Run the Gator template update by executing: `gator update` (requires the "
    "Gator CLI — `pipx install gator-command`; pre-2.9 repos may still carry a "
    "runnable `gator-update.py` in `.gator/scripts/` or `.gator/.includes/scripts/`).\n"
    "\n"
    "This refreshes template-derived files (constitution, procedures, scripts, "
    "reference-notes, charter templates, slash commands) without touching any "
    "user content (charters, threads, artifacts, mission, roadmap, etc.).\n"
    "\n"
    "Display the output showing what was added, updated, or unchanged. If the "
    "Architect wants to preview first, use `--dry-run`.\n"
)

LEGACY_CHAIN = ("gator hook session-open || python .gator/.includes/scripts/"
                "gator-session-open.py || python3 .gator/.includes/scripts/"
                "gator-session-open.py || py -3 .gator/.includes/scripts/"
                "gator-session-open.py")
GATOR_ENTRIES = [{"type": "command", "command": LEGACY_CHAIN, "timeout": 5},
                 {"type": "command", "command": "gator hook session-start", "timeout": 5}]
USER_VERB = {"type": "command", "command": "gator hook override status"}
USER_PATH = {"type": "command", "command": "python .gator/tools/mine.py"}


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=str(repo), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "T")
    return repo


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, (dict, list)):
        data = json.dumps(data, indent=2) + "\n"
    path.write_text(data, encoding="utf-8", newline="\n")


def _commit_all(repo):
    _git(repo, "add", "-A")
    r = _git(repo, "-c", "core.hooksPath=/dev/null", "commit", "-q", "--no-verify", "-m", "x")
    assert r.returncode == 0, r.stderr


def _settings(entries):
    return {"hooks": {"SessionStart": [{"hooks": entries}]}}


# ---------------------------------------------------------------------------
# plan_vendor_cleanup()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rel", list(cleanup.ELIGIBLE_SETTINGS))
@pytest.mark.parametrize("content, action", [
    (_settings(GATOR_ENTRIES), "delete"),
    (_settings(GATOR_ENTRIES + [USER_VERB]), "strip"),
    (_settings(GATOR_ENTRIES + [USER_PATH]), "strip"),
    (dict(_settings(GATOR_ENTRIES), permissions={"allow": ["Bash(ls)"]}), "strip"),
    (_settings([USER_VERB, USER_PATH]), None),
    ({"theme": "dark"}, None),
    ("{not json", None),
], ids=["gator-only", "user-verb", "user-gator-path", "user-settings",
        "gator-free", "no-hooks", "invalid-json"])
def test_settings_classification(tmp_path, rel, content, action):
    repo = _repo(tmp_path)
    _write(repo / rel, content)
    actions = cleanup.plan_vendor_cleanup(repo)
    if action is None:
        assert actions == []
    else:
        assert [(a["path"], a["action"]) for a in actions] == [(rel, action)]


@pytest.mark.parametrize("content, action", [
    (SHIPPED_UPDATE_MD, "delete"),
    (SHIPPED_UPDATE_MD.replace("\n", "\r\n"), "delete"),
    (SHIPPED_UPDATE_MD + "\nMy own extra line.\n", "user-owned"),
], ids=["shipped", "shipped-crlf", "user-edited"])
def test_command_classification(tmp_path, content, action):
    repo = _repo(tmp_path)
    path = repo / ".claude" / "commands" / "update.md"
    path.parent.mkdir(parents=True)
    path.write_bytes(content.encode("utf-8"))
    assert [(a["path"], a["action"]) for a in cleanup.plan_vendor_cleanup(repo)] == [
        (".claude/commands/update.md", action)]


def test_other_command_files_are_never_touched(tmp_path):
    repo = _repo(tmp_path)
    _write(repo / ".claude" / "commands" / "review.md", SHIPPED_UPDATE_MD)
    assert cleanup.plan_vendor_cleanup(repo) == []


def test_retired_digests_cover_every_command_and_the_last_shipped_version():
    assert set(cleanup.RETIRED_COMMANDS) == {
        ".claude/commands/init.md", ".claude/commands/update.md",
        ".claude/commands/commit.md", ".claude/commands/loop-join.md"}
    assert sum(len(v) for v in cleanup.RETIRED_COMMANDS.values()) == 36
    import hashlib
    digest = hashlib.sha256(SHIPPED_UPDATE_MD.encode("utf-8")).hexdigest()
    assert digest in cleanup.RETIRED_COMMANDS[".claude/commands/update.md"]


def test_plan_is_read_only_and_reports_tracking(tmp_path):
    repo = _repo(tmp_path)
    _write(repo / ".claude" / "settings.json", _settings(GATOR_ENTRIES))
    _commit_all(repo)
    _write(repo / ".codex" / "hooks.json", _settings(GATOR_ENTRIES))
    before = {p: p.read_bytes() for p in repo.rglob("*.json")}
    actions = cleanup.plan_vendor_cleanup(repo)
    assert {a["path"]: a["tracked"] for a in actions} == {
        ".claude/settings.json": True, ".codex/hooks.json": False}
    assert {p: p.read_bytes() for p in repo.rglob("*.json")} == before


# ---------------------------------------------------------------------------
# apply_vendor_cleanup() — the staging rule
# ---------------------------------------------------------------------------

def test_apply_staging_rule(tmp_path):
    repo = _repo(tmp_path)
    _write(repo / ".claude" / "settings.json", _settings(GATOR_ENTRIES))
    _write(repo / ".claude" / "settings.local.json", {"permissions": {}})
    _write(repo / ".claude" / "commands" / "update.md", SHIPPED_UPDATE_MD)
    _write(repo / ".gemini" / "settings.json",
           dict(_settings(GATOR_ENTRIES + [USER_VERB]), theme="dark"))
    _commit_all(repo)
    _write(repo / ".codex" / "hooks.json", _settings(GATOR_ENTRIES))  # untracked

    applied = cleanup.apply_vendor_cleanup(repo, cleanup.plan_vendor_cleanup(repo))
    assert sorted((a["path"], a["action"]) for a in applied) == [
        (".claude/commands/update.md", "delete"),
        (".claude/settings.json", "delete"),
        (".codex/hooks.json", "delete"),
        (".gemini/settings.json", "strip")]

    staged = _git(repo, "diff", "--cached", "--name-status").stdout.splitlines()
    assert sorted(staged) == ["D\t.claude/commands/update.md", "D\t.claude/settings.json"]
    unstaged = _git(repo, "diff", "--name-only").stdout.splitlines()
    assert unstaged == [".gemini/settings.json"], "a stripped file is left for review"
    assert json.loads((repo / ".gemini" / "settings.json").read_text(encoding="utf-8")) == {
        "hooks": {"SessionStart": [{"hooks": [USER_VERB]}]}, "theme": "dark"}
    assert not (repo / ".codex").exists(), "an emptied vendor folder is removed"
    assert not (repo / ".claude" / "commands").exists()
    assert (repo / ".claude" / "settings.local.json").is_file(), "user file keeps .claude/"


def test_apply_deletes_a_locally_modified_gator_only_file(tmp_path):
    repo = _repo(tmp_path)
    _write(repo / ".claude" / "settings.json", _settings(GATOR_ENTRIES))
    _commit_all(repo)
    edited = [dict(e, timeout=9) for e in GATOR_ENTRIES]
    _write(repo / ".claude" / "settings.json", _settings(edited))
    cleanup.apply_vendor_cleanup(repo, cleanup.plan_vendor_cleanup(repo))
    assert not (repo / ".claude" / "settings.json").exists()
    assert "D\t.claude/settings.json" in _git(repo, "diff", "--cached", "--name-status").stdout


def test_user_owned_note_is_never_applied(tmp_path):
    repo = _repo(tmp_path)
    _write(repo / ".claude" / "commands" / "init.md", "my own init\n")
    actions = cleanup.plan_vendor_cleanup(repo)
    assert cleanup.apply_vendor_cleanup(repo, actions) == []
    assert (repo / ".claude" / "commands" / "init.md").read_text(encoding="utf-8") == "my own init\n"


def test_format_lines():
    actions = [{"path": ".claude/settings.json", "action": "delete", "tracked": True},
               {"path": ".gemini/settings.json", "action": "strip", "tracked": True},
               {"path": ".claude/commands/init.md", "action": "user-owned", "tracked": True}]
    text = "\n".join(cleanup.format_vendor_cleanup(actions))
    assert "- .claude/settings.json (deletion staged)" in text
    assert "review and commit" in text
    assert "left in place (user-edited)" in text
    assert cleanup.format_vendor_cleanup([]) == []


# ---------------------------------------------------------------------------
# gator update end to end (subprocess, temporary HOME)
# ---------------------------------------------------------------------------

def _legacy_repo(tmp_path):
    gatorize = load_script("gatorize")
    repo = _repo(tmp_path)
    gatorize.action_install_gator(repo)
    _write(repo / ".claude" / "settings.json", _settings(GATOR_ENTRIES))
    _write(repo / ".claude" / "commands" / "update.md", SHIPPED_UPDATE_MD)
    _write(repo / ".gemini" / "settings.json",
           dict(_settings(GATOR_ENTRIES + [USER_VERB])))
    _commit_all(repo)
    return repo


def _update(tmp_path, script, repo, *flags, source=True):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home),
               PYTHONIOENCODING="utf-8")
    src = ["--source", str(PACKAGE_ROOT)] if source else []
    return subprocess.run(
        [sys.executable, str(script), "--path", str(repo), *src, *flags],
        cwd=str(repo), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180)


def test_gatorize_writes_no_vendor_files(tmp_path):
    gatorize = load_script("gatorize")
    repo = _repo(tmp_path)
    gatorize.action_install_gator(repo)
    for folder in (".claude", ".codex", ".gemini"):
        assert not (repo / folder).exists(), folder


def test_update_dry_run_and_json_change_nothing(tmp_path):
    repo = _legacy_repo(tmp_path)
    index = _git(repo, "ls-files", "--stage").stdout
    r = _update(tmp_path, PACKAGE_UPDATE, repo, "--dry-run")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "AI-tool files Gator will remove" in r.stdout
    assert "- .claude/settings.json" in r.stdout
    assert "Everything is current" not in r.stdout
    r = _update(tmp_path, PACKAGE_UPDATE, repo, "--json", source=False)
    assert r.returncode == 0, r.stdout + r.stderr
    plan = json.loads(r.stdout)
    assert plan["vendor_cleanup"]["count"] == 3
    assert plan["summary"]["vendor_cleanup"] == 3
    assert {a["path"]: a["action"] for a in plan["vendor_cleanup"]["actions"]} == {
        ".claude/commands/update.md": "delete", ".claude/settings.json": "delete",
        ".gemini/settings.json": "strip"}
    assert _git(repo, "ls-files", "--stage").stdout == index
    assert (repo / ".claude" / "settings.json").is_file()


def test_update_executes_exactly_the_plan_then_is_quiet(tmp_path):
    repo = _legacy_repo(tmp_path)
    r = _update(tmp_path, PACKAGE_UPDATE, repo, "--result-json")
    assert r.returncode == 0, r.stdout + r.stderr
    result = json.loads(r.stdout)
    assert sorted((a["path"], a["action"]) for a in result["vendor_cleanup"]) == [
        (".claude/commands/update.md", "delete"), (".claude/settings.json", "delete"),
        (".gemini/settings.json", "strip")]
    assert "AI-tool files Gator removed" in result["output"]
    staged = _git(repo, "diff", "--cached", "--name-status").stdout
    assert "D\t.claude/settings.json" in staged and "D\t.claude/commands/update.md" in staged
    assert ".gemini/settings.json" not in staged
    assert not (repo / ".claude").exists()
    # Nothing left: a second run reports no cleanup.
    r = _update(tmp_path, PACKAGE_UPDATE, repo, "--result-json")
    assert json.loads(r.stdout)["vendor_cleanup"] is None
    assert "AI-tool files" not in json.loads(r.stdout)["output"]


def test_update_never_writes_vendor_files(tmp_path):
    gatorize = load_script("gatorize")
    repo = _repo(tmp_path)
    gatorize.action_install_gator(repo)
    _commit_all(repo)
    r = _update(tmp_path, PACKAGE_UPDATE, repo)
    assert r.returncode == 0, r.stdout + r.stderr
    for folder in (".claude", ".codex", ".gemini"):
        assert not (repo / folder).exists(), folder


def test_template_copy_standalone_plans_and_does_nothing(tmp_path):
    repo = _legacy_repo(tmp_path)
    r = _update(tmp_path, TEMPLATE_UPDATE, repo, "--result-json")
    assert r.returncode == 0, r.stdout + r.stderr
    assert json.loads(r.stdout)["vendor_cleanup"] is None
    assert (repo / ".claude" / "settings.json").is_file()
    r = _update(tmp_path, TEMPLATE_UPDATE, repo, "--json", source=False)
    assert json.loads(r.stdout)["vendor_cleanup"] == {"actions": [], "count": 0}


def test_update_scripts_no_longer_carry_merge_code():
    for script in (PACKAGE_UPDATE, TEMPLATE_UPDATE):
        text = script.read_text(encoding="utf-8")
        for name in ("install_vendor_hooks", "merge_hooks_into_settings",
                     "VENDOR_HOOK_CONFIGS", "CLAUDE_COMMANDS_DIR"):
            assert name not in text, (script.name, name)
