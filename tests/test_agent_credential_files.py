"""Agent-tool credential files stay out of commits (2.37.1).

Claude Code saves approved commands, credentials included, into
`.claude/settings.local.json`; Codex keeps its login in `auth.json` under
CODEX_HOME; Gemini CLI loads secrets from `.gemini/.env`. Each test proves
one risk: governed repositories ignore those files after install or update;
the commit hook flags a staged credential file by path, in both hook
copies; and it never flags removing one (the fix), or an unrelated file
that merely shares a basename.
"""

import subprocess
from pathlib import Path

import pytest

from conftest import load_script

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "src" / "gator_command" / "templates" / "gator-starter" / "scripts"
BUNDLED = ROOT / "enterprise" / "enterprise-cli" / "gator_enterprise_cli" / "bundled_scripts"
gatorize = load_script("gatorize")
LINTS = {"template": load_script("precommit_lint", search_dir=TEMPLATE),
         "bundled": load_script("precommit_lint", search_dir=BUNDLED)}

CREDENTIAL_FILES = [".claude/settings.local.json", ".gemini/.env", ".codex/auth.json"]


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                          text=True).stdout


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    _git(tmp_path, "config", "core.hooksPath", str(tmp_path / "no-hooks"))
    return tmp_path


def _write(repo, rel, text="{}\n"):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_governed_repos_ignore_agent_credential_files(repo):
    """After install/update convergence Git really ignores each file, and a
    second run adds nothing."""
    gatorize.ensure_repo_gitignore(repo, untrack=False)
    gatorize.ensure_repo_gitignore(repo, untrack=False)
    gi = (repo / ".gitignore").read_text(encoding="utf-8")
    for rel in CREDENTIAL_FILES:
        assert gi.count(rel) == 1
        _write(repo, rel)
        assert subprocess.run(["git", "check-ignore", "-q", rel], cwd=repo).returncode == 0, rel


def _hyg(lint, repo):
    staged = _git(repo, "diff", "--cached", "--name-only").split()
    return sorted(f["file"] for f in lint.run_layer1_lint(staged, repo)
                  if f["rule"] == "HYG-002")


@pytest.mark.parametrize("copy", sorted(LINTS))
def test_hook_flags_staged_credential_files_by_path(repo, copy):
    for rel in [".claude/settings.local.json", ".codex/auth.json",
                "sub/project/.claude/settings.local.json", ".gemini/.env",
                "config/auth.json", "settings.local.json", ".claude/settings.json"]:
        _write(repo, rel)
    _git(repo, "add", "-f", ".")
    assert _hyg(LINTS[copy], repo) == [".claude/settings.local.json", ".codex/auth.json",
                                       ".gemini/.env",
                                       "sub/project/.claude/settings.local.json"]


@pytest.mark.parametrize("copy", sorted(LINTS))
def test_hook_never_flags_removing_a_credential_file(repo, copy):
    for rel in [".claude/settings.local.json", ".env"]:
        _write(repo, rel)
    _git(repo, "add", "-f", ".")
    _git(repo, "commit", "-q", "-m", "mistake")
    _git(repo, "rm", "-q", "--cached", ".claude/settings.local.json", ".env")
    assert _hyg(LINTS[copy], repo) == []
