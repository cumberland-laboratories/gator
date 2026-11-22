"""
#16: the `stale-charter-refs` warning reads charter headings the way the
other charter checks do, and searches every file the charter covers.

Before, it took the text before a heading's first `(` as one name (so
`### Vendor cleanup in _run() / print_plan()` became "Vendor cleanup in
_run") and read `Covers` globs as literal paths (so every function in a
glob-covered file looked stale).
"""

import subprocess
from pathlib import Path

import pytest

from conftest import load_script

TEMPLATE_SCRIPTS = (
    Path(__file__).parent.parent
    / "src" / "gator_command" / "templates"
    / "gator-starter" / "scripts"
)
charter = load_script("precommit_charter", search_dir=TEMPLATE_SCRIPTS)


def _write(repo, rel, text):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    _write(tmp_path, "src/app/core.py",
           "AUTO_YES = False\n\ndef set_auto_yes(v):\n    pass\n\n"
           "def get_auto_yes():\n    return AUTO_YES\n\ndef _run():\n    pass\n")
    _write(tmp_path, "src/app/views/fleet.js",
           "window.gatorNavToRepo = function () {};\nfunction registerRepo() {}\n")
    _write(tmp_path, "tools/extra.py", "def helper():\n    pass\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    return tmp_path


def stale(repo, body, covers="`src/app/*.py`"):
    _write(repo, ".gator/charters/c.md",
           f"# Charter: c\n\n**Covers**: {covers}\n\n## Owns\n\n- x\n\n{body}\n")
    return charter._check_charter_function_refs([".gator/charters/c.md"], repo)


class TestHeadings:

    def test_compound_heading_with_a_constant(self, repo):
        assert stale(repo, "### AUTO_YES / set_auto_yes(value) / get_auto_yes()") == []

    def test_prose_prefix_heading(self, repo):
        assert stale(repo, "### Vendor cleanup in _run() / set_auto_yes()") == []

    def test_prose_and_tripwire_headings_are_ignored(self, repo):
        assert stale(repo, "### TRIPWIRE: Charter Surface Resolution\n"
                           "### Add Repository dialog") == []

    def test_a_removed_function_is_still_reported(self, repo):
        assert stale(repo, "### set_auto_yes() / removed_helper()") == ["removed_helper"]


class TestCoveredFiles:

    def test_glob_entry_covers_the_matching_files(self, repo):
        """The #16 parse_search_query case: a function in a glob-covered file."""
        assert stale(repo, "### get_auto_yes()", covers="`src/app/*.py`") == []

    def test_directory_prefix_entry(self, repo):
        body = "### registerRepo() / window.gatorNavToRepo()"
        assert stale(repo, body, covers="`src/app/`") == []

    def test_dotted_name_is_found_by_its_last_part(self, repo):
        assert stale(repo, "### window.gatorNavToRepo()", covers="`src/app/views/fleet.js`") == []

    def test_file_lines_are_searched_too(self, repo):
        body = "### helper()\nFile: `tools/extra.py`\n"
        assert stale(repo, body, covers="`src/app/core.py`") == []

    def test_names_outside_every_searched_file_are_stale(self, repo):
        assert stale(repo, "### helper()", covers="`src/app/core.py`") == ["helper"]

    def test_no_searchable_file_reports_nothing(self, repo):
        """As before: a charter whose files are all missing is not judged."""
        assert stale(repo, "### anything()", covers="`missing/*.py`") == []


def test_legacy_reader_is_the_fallback_shape():
    assert charter._legacy_heading_names("### foo_bar(args)") == ["foo_bar"]
    assert charter._legacy_heading_names("### Not a function") == []
