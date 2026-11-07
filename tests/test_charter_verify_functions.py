"""Charter verifier function checks under the #105 significance policy.

Each test proves one acceptance risk from the approved plan, on a small
temporary repository: default `function-gap` reports only seams (with a
`reason`); a grouped entry with `File:` documents every name it lists
and still goes stale when one is renamed; the README's plain `File:`
line enables stale checks; JavaScript registrations are not stale; and
strict mode adds `function-candidate` without changing default output.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "src" / "gator_command" / "scripts"


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _charter(name, covers, body=""):
    return (f"# Charter: {name}\n\n**Covers**: {covers}\n\n## Owns\n\n- x\n\n"
            f"## Does Not Own\n\n- y\n\n---\n\n{body}")


def _verify(repo, *extra):
    out = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "gator-charter-verify.py"),
         "--path", str(repo), "--json", *extra],
        capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def _classes(data, cls):
    return {(f["file"], f.get("function")) for f in data["findings"] if f["class"] == cls}


@pytest.fixture
def repo(tmp_path):
    """Two charters: `core` owns src/core.py, `ui` owns src/ui.py and web/view.js."""
    _git(tmp_path, "init", "-q")
    _write(tmp_path, "src/core.py",
           '__all__ = ["exported"]\n\n\n'
           'def exported():\n    pass\n\n\n'
           'def shared_helper():\n    pass\n\n\n'
           'def build_local_thing(a, b, c, d):\n    """Action name, docstring, four args."""\n\n\n'
           'def documented_one():\n    pass\n\n\n'
           'def documented_two():\n    pass\n')
    _write(tmp_path, "src/ui.py",
           "from core import shared_helper\n\n\ndef page():\n    return shared_helper()\n")
    _write(tmp_path, "web/view.js",
           "(function () {\n"
           "  function renderRow() {}\n"
           "  window.GatorViews.view = function (data) {};\n"
           "})();\n")
    charters = tmp_path / ".gator" / "charters"
    charters.mkdir(parents=True)
    (charters / "core.md").write_text(_charter(
        "core", "`src/core.py`",
        "### documented_one() / documented_two()\nFile: src/core.py\nTwo helpers, one boundary.\n"),
        encoding="utf-8")
    (charters / "ui.md").write_text(_charter(
        "ui", "`src/ui.py`, `web/view.js`",
        "### GatorViews.view()\nFile: web/view.js\nThe view.\n"),
        encoding="utf-8")
    _git(tmp_path, "add", "-A")
    return tmp_path


def test_default_reports_only_seams_with_reason(repo):
    data = _verify(repo)
    gaps = {(f["file"], f["function"], f["reason"])
            for f in data["findings"] if f["class"] == "function-gap"}
    # `page` and `renderRow` are local; `build_local_thing` is not a seam by name.
    assert gaps == {("src/core.py", "exported", "entry"),
                    ("src/core.py", "shared_helper", "cross-module")}
    assert data["function_policy"] == "default"
    assert "function-candidate" not in data["summary"]


def test_grouped_entry_documents_every_name_and_goes_stale_on_rename(repo):
    assert not _classes(_verify(repo), "stale-structure")
    core = repo / "src/core.py"
    core.write_text(core.read_text(encoding="utf-8").replace(
        "def documented_two", "def renamed_two"), encoding="utf-8")
    assert _classes(_verify(repo), "stale-structure") == {("src/core.py", "documented_two")}


def test_backticked_file_line_still_enables_stale_checks(repo):
    md = repo / ".gator/charters/core.md"
    md.write_text(md.read_text(encoding="utf-8").replace(
        "File: src/core.py", "File: `src/core.py`").replace(
        "documented_two()", "missing_fn()"), encoding="utf-8")
    assert ("src/core.py", "missing_fn") in _classes(_verify(repo), "stale-structure")


def test_anonymous_javascript_registration_is_not_stale(repo):
    stale = _classes(_verify(repo), "stale-structure")
    assert ("web/view.js", "GatorViews.view") not in stale
    assert ("web/view.js", "view") not in stale


def test_strict_adds_candidates_and_keeps_default_findings(repo):
    default = _verify(repo)
    strict = _verify(repo, "--functions", "strict")
    assert strict["function_policy"] == "strict"
    assert [f for f in strict["findings"] if f["class"] != "function-candidate"] == default["findings"]
    assert ("src/core.py", "build_local_thing") in _classes(strict, "function-candidate")


def _add_internal(repo, charter, line):
    md = repo / ".gator/charters" / f"{charter}.md"
    text = md.read_text(encoding="utf-8")
    md.write_text(text.replace("\n\n## Owns", f"\n{line}\n\n## Owns", 1), encoding="utf-8")


def test_internal_line_clears_its_gap(repo):
    _add_internal(repo, "core", "**Internal**: `shared_helper`")
    data = _verify(repo)
    assert ("src/core.py", "shared_helper") not in _classes(data, "function-gap")
    assert ("src/core.py", "exported") in _classes(data, "function-gap")
    assert not _classes(data, "stale-exclusion")


def test_internal_name_also_suppresses_strict_candidates(repo):
    _add_internal(repo, "core", "**Internal**: `build_local_thing`")
    assert ("src/core.py", "build_local_thing") not in _classes(
        _verify(repo, "--functions", "strict"), "function-candidate")


@pytest.mark.parametrize("charter,name", [
    ("core", "never_defined"),   # absent everywhere
    ("core", "page"),            # defined only in src/ui.py, which another charter covers
])
def test_stale_exclusion(repo, charter, name):
    _add_internal(repo, charter, f"**Internal**: `{name}`")
    data = _verify(repo)
    stale = [f for f in data["findings"] if f["class"] == "stale-exclusion"]
    assert [(f["charter"], f["function"], f["file"]) for f in stale] == [
        (charter, name, f".gator/charters/{charter}.md")]
    # An out-of-scope name never clears another charter's gap either.
    if name == "page":
        assert ("src/ui.py", "page") not in _classes(data, "function-gap")  # local, not a seam


def test_consecutive_file_lines_all_belong_to_the_entry(repo):
    """A name may live in any of an entry's File: files; it is stale only
    when none of them defines it, and is reported once."""
    md = repo / ".gator/charters/ui.md"
    md.write_text(md.read_text(encoding="utf-8") +
                  "\n### page() / renderRow()\nFile: src/ui.py\nFile: web/view.js\nPage and rows.\n",
                  encoding="utf-8")
    assert not _classes(_verify(repo), "stale-structure")
    view = repo / "web/view.js"
    view.write_text(view.read_text(encoding="utf-8").replace("renderRow", "renderLine"),
                    encoding="utf-8")
    stale = [f for f in _verify(repo)["findings"] if f["class"] == "stale-structure"]
    assert [(f["file"], f["function"]) for f in stale] == [("src/ui.py", "renderRow")]
