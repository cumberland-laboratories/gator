"""Pre-commit new-seam warning (`precommit_charter.new_seam_functions`, #105).

Each test proves one risk from the approved plan, on temporary Git
repositories: the hook judges a new function against the full staged
tree, including unchanged tracked importers; only the index counts, so an
unstaged edit to an importer, a charter's Internal line or INDEX.md changes
nothing; the hook and the charter verifier agree on seams, exclusions and
ordinary helpers; and the warning is advisory, never a block.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import load_script

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_SCRIPTS = ROOT / "src" / "gator_command" / "templates" / "gator-starter" / "scripts"
SCRIPTS_DIR = ROOT / "src" / "gator_command" / "scripts"
charter = load_script("precommit_charter", search_dir=TEMPLATE_SCRIPTS)
pre_commit = load_script("gator-pre-commit", search_dir=TEMPLATE_SCRIPTS)

INDEX = """# Charter Index

| If you're changing... | Read these charters |
|---|---|
| `src/core.py`, `src/core_util.py` | [Core](core.md) · [Cross-Cutting](cross-cutting.md) |
| `src/ui.py`, `web/view.js` | [UI](ui.md) · [Cross-Cutting](cross-cutting.md) |
"""


def _md(name, covers, extra=""):
    return (f"# Charter: {name}\n\n**Covers**: {covers}\n{extra}\n## Owns\n\n- x\n\n"
            "## Does Not Own\n\n- y\n\n---\n")


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                          text=True).stdout


def _write(repo, rel, text):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    _git(tmp_path, "config", "core.hooksPath", str(tmp_path / "no-hooks"))
    _write(tmp_path, ".gator/charters/INDEX.md", INDEX)
    _write(tmp_path, ".gator/charters/core.md", _md("core", "`src/core.py`, `src/core_util.py`"))
    _write(tmp_path, ".gator/charters/ui.md", _md("ui", "`src/ui.py`, `web/view.js`"))
    _write(tmp_path, ".gator/charters/cross-cutting.md", _md("cross", "`none.py`"))
    _write(tmp_path, "src/core.py", "def existing():\n    pass\n")
    _write(tmp_path, "src/core_util.py", "X = 1\n")
    # An unchanged, already-tracked importer under another charter.
    _write(tmp_path, "src/ui.py", "from core import helper\n\n\ndef page():\n    return helper()\n")
    _write(tmp_path, "web/view.js", "(function () {})();\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def _stage_new_helper(repo):
    _write(repo, "src/core.py", "def existing():\n    pass\n\n\ndef helper():\n    pass\n")
    _git(repo, "add", "src/core.py")


def test_unchanged_tracked_importer_under_another_charter_makes_a_seam(repo):
    _stage_new_helper(repo)
    assert charter.new_seam_functions(repo) == ["helper"]


def test_importer_under_the_same_charter_does_not(repo):
    _write(repo, "src/ui.py", "def page():\n    return 1\n")
    _write(repo, "src/core_util.py", "from core import helper\n")
    _git(repo, "add", "src/ui.py", "src/core_util.py")
    _stage_new_helper(repo)
    assert charter.new_seam_functions(repo) == []


@pytest.mark.parametrize("rel,unstaged_text,expected_after_staging", [
    # Removing the only cross-charter importer: unstaged, the staged importer still counts.
    ("src/ui.py", "def page():\n    return 1\n", []),
    # Listing the name as internal.
    (".gator/charters/core.md", _md("core", "`src/core.py`, `src/core_util.py`",
                                    "**Internal**: `helper`\n"), []),
    # Re-routing the importer to the defining file's charter.
    (".gator/charters/INDEX.md", INDEX.replace("`src/ui.py`, `web/view.js` | [UI](ui.md)",
                                               "`src/ui.py`, `web/view.js` | [Core](core.md)"), []),
])
def test_only_the_index_counts(repo, rel, unstaged_text, expected_after_staging):
    _stage_new_helper(repo)
    _write(repo, rel, unstaged_text)
    assert charter.new_seam_functions(repo) == ["helper"]      # working tree ignored
    _git(repo, "add", rel)
    assert charter.new_seam_functions(repo) == expected_after_staging


def test_hook_and_verifier_agree(repo):
    """Same staged Python and JavaScript fixture: seam, excluded seam,
    ordinary action-named helper. INDEX and Covers agree."""
    _write(repo, ".gator/charters/core.md", _md(
        "core", "`src/core.py`, `src/core_util.py`", "**Internal**: `excluded_seam`\n"))
    _write(repo, "src/core.py",
           '__all__ = ["exported_seam", "excluded_seam"]\n\n\n'
           "def existing():\n    pass\n\n\n"
           "def helper():\n    pass\n\n\n"
           "def exported_seam():\n    pass\n\n\n"
           "def excluded_seam():\n    pass\n\n\n"
           'def build_everything(a, b, c, d):\n    """Docstring and verb prefix."""\n')
    _write(repo, "web/view.js",
           "export function jsSeam() {}\n(function () {\n  function renderLocal() {}\n})();\n")
    _git(repo, "add", "-A")

    hook = set(charter.new_seam_functions(repo))
    out = subprocess.run([sys.executable, str(SCRIPTS_DIR / "gator-charter-verify.py"),
                          "--path", str(repo), "--json"],
                         capture_output=True, text=True, check=True).stdout
    verifier = {f["function"] for f in json.loads(out)["findings"]
                if f["class"] == "function-gap"} - {"existing"}
    assert hook == verifier == {"helper", "exported_seam", "jsSeam"}


def test_git_failure_gives_no_warning(tmp_path):
    assert charter.new_seam_functions(tmp_path) == []


def test_warning_is_advisory_never_a_block(repo, monkeypatch):
    _stage_new_helper(repo)
    _write(repo, ".gator/charters/core.md", _md("core", "`src/core.py`, `src/core_util.py`") + "\n")
    _git(repo, "add", "-A")
    monkeypatch.chdir(repo)
    staged = _git(repo, "diff", "--cached", "--name-only").split()
    gator_dir = repo / ".gator"
    warnings = pre_commit.validate_soft_rules(staged, {"message": "m"}, "", gator_dir)
    seam = [msg for rule, msg in warnings if rule == "new-functions-undocumented"]
    assert len(seam) == 1 and "helper" in seam[0] and "Internal" in seam[0]
    failures = pre_commit.validate_hard_rules(
        staged_files=staged, frontmatter={"message": "m"}, body="",
        parse_error=None, gator_dir=gator_dir)
    assert not [f for f in failures if f[0] == "new-functions-undocumented"]
