"""Shared charter `Covers` matcher (`charter_covers.py`, grammar `gator-covers-v1`).

Each test proves one risk named by the approved plan: the closed grammar
answers every supported and unsupported entry form; Charter Sync's matcher
is the shared one and keeps its previous answers; and the charter verifier
no longer reports glob-covered files as uncovered (#88).
"""

import fnmatch
import json
import subprocess
import sys
from pathlib import Path

import pytest

import charter_covers
from dashboard import charter_sync

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "src" / "gator_command" / "scripts"

# (path, entry, expected). The last group is newly rejected by the grammar.
MATRIX = [
    ("src/a.py", "src/a.py", True),                          # exact
    ("src/a.py", "src/b.py", False),
    ("src/a.py", "src/", True),                              # directory prefix
    ("srcx/a.py", "src/", False),
    ("src/a.py", "src/*.py", True),                          # full-path glob
    ("x/src/a.py", "src/*.py", False),                       # never basename-only
    ("a.py", "*.py", True),
    ("src/a.py", "a.py", False),
    ("src/d/e.py", "src/*.py", True),                        # `*` crosses `/`
    ("enterprise/app/m.py", "enterprise/app/**", True),
    ("src/a1.py", "src/a?.py", True),
    ("src/ab.py", "src/a[bc].py", True),
    ("src/a.py", "src\\a.py", True),                         # entry normalization
    ("src\\a.py", "src/a.py", True),                         # path normalization
    ("src/a.py", "./src/a.py", True),
    ("src/a.py", "  src/a.py  ", True),
    ("Src/A.py", "src/a.py", False),                         # case-sensitive everywhere
    ("src/a.py", "", False),
    ("src/a.py", "   ", False),
    # Rejected: absolute, drive-letter and `..` entries match nothing.
    ("src/a.py", "/src/a.py", False),
    ("src/a.py", "C:/repo/src/a.py", False),
    ("src/a.py", "c:src/a.py", False),
    ("src/a.py", "lib/../src/a.py", False),
    ("src/a.py", "../*", False),
]
NEWLY_REJECTED = {"/src/a.py", "C:/repo/src/a.py", "c:src/a.py", "lib/../src/a.py", "../*"}


def _previous_sync_match(path, entry):
    """Charter Sync's matcher before the shared grammar (the compatibility baseline)."""
    entry = entry.strip().replace("\\", "/")
    if entry.startswith("./"):
        entry = entry[2:]
    if not entry:
        return False
    if any(c in entry for c in "*?["):
        return fnmatch.fnmatchcase(path, entry)
    if entry.endswith("/"):
        return path.startswith(entry)
    return path == entry


@pytest.mark.parametrize("path, entry, expected", MATRIX)
def test_grammar(path, entry, expected):
    assert charter_covers.covers_match(path, entry) is expected


@pytest.mark.parametrize("path, entry, expected",
                         [m for m in MATRIX if m[1] not in NEWLY_REJECTED and "\\" not in m[0]])
def test_charter_sync_uses_the_shared_matcher_with_unchanged_answers(path, entry, expected):
    assert charter_sync.covers_match is charter_covers.covers_match
    assert _previous_sync_match(path, entry) is expected


def test_coverage_index_resolves_every_entry_form_in_charter_order():
    charters = [{"name": "b", "covers": ["src/*.py"]},
                {"name": "a", "covers": ["src/x.py", "lib/"]}]
    index = charter_covers.coverage_index(["src/x.py", "lib/y.py", "tools/z.py"], charters)
    assert index == {"src/x.py": ["b", "a"], "lib/y.py": ["a"]}


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def test_verifier_honours_glob_covers(tmp_path):
    """#88: a glob-covered file is covered, and the other checks now see it."""
    _git(tmp_path, "init", "-q")
    charters = tmp_path / ".gator" / "charters"
    charters.mkdir(parents=True)
    (charters / "mod.md").write_text(
        "# Charter: mod\n\n**Covers**: `src/*.py`, `lib/`\n", encoding="utf-8")
    for rel in ("src/a.py", "lib/d/b.py"):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('def build_widget():\n    """Build one."""\n    return 1\n', encoding="utf-8")
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "u.py").write_text("X = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")

    out = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "gator-charter-verify.py"),
         "--path", str(tmp_path), "--json"],
        capture_output=True, text=True, check=True).stdout
    findings = json.loads(out)["findings"]
    gaps = {f["file"] for f in findings if f["class"] == "coverage-gap"}
    assert gaps == {"tools/u.py"}
    function_gaps = {(f["file"], f["charter"]) for f in findings if f["class"] == "function-gap"}
    assert function_gaps == {("src/a.py", "mod"), ("lib/d/b.py", "mod")}
