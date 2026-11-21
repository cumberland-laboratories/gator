"""
#18: the `charter-index-gap` rule treats INDEX.md as a reading list.

For each changed code file and each INDEX row that matches it, at least one
of the row's domain charters must be staged. The cross-cutting charter is a
domain charter only on a row that lists nothing else, and is otherwise
required only for a file its own `Covers` line names.
"""

from pathlib import Path

import pytest

from conftest import load_script

TEMPLATE_SCRIPTS = (
    Path(__file__).parent.parent
    / "src" / "gator_command" / "templates"
    / "gator-starter" / "scripts"
)
pre_commit = load_script("gator-pre-commit", search_dir=TEMPLATE_SCRIPTS)
charter = load_script("precommit_charter", search_dir=TEMPLATE_SCRIPTS)

INDEX = """# Charter Index

| If you're changing... | Read these charters |
|---|---|
| `web/view.js`, `web/style.css` | [UI](ui.md) · [Server](server.md) · [Cross-Cutting](cross-cutting.md) |
| `server/app.py` | [Server](server.md) · [Cross-Cutting](cross-cutting.md) |
| `src/core.py`, `src/shared/*.py` | [Core](core.md) · [Cross-Cutting](cross-cutting.md) |
| `src/cli.py` | [Cross-Cutting](cross-cutting.md) |
"""

CROSS_CUTTING = """# Charter: Cross-Cutting

**Covers**: `src/core.py`, `src/shared/*.py`

## Owns
"""


@pytest.fixture
def repo(tmp_path):
    charters = tmp_path / ".gator" / "charters"
    charters.mkdir(parents=True)
    (charters / "INDEX.md").write_text(INDEX, encoding="utf-8")
    (charters / "cross-cutting.md").write_text(CROSS_CUTTING, encoding="utf-8")
    for name in ("ui.md", "server.md", "core.md"):
        (charters / name).write_text(f"# Charter: {name}\n", encoding="utf-8")
    return tmp_path


def _staged(*names):
    return [f".gator/charters/{n}" for n in names]


def gaps(repo, files, *charters):
    return charter.charter_index_gaps(files, _staged(*charters), repo)


class TestDomainCharters:

    def test_ui_only_change_needs_only_the_ui_charter(self, repo):
        assert gaps(repo, ["web/view.js"], "ui.md") == []

    def test_server_only_change_on_a_layered_row(self, repo):
        assert gaps(repo, ["web/view.js"], "server.md") == []

    def test_cross_layer_change_with_both_charters(self, repo):
        assert gaps(repo, ["web/view.js", "server/app.py"], "ui.md", "server.md") == []

    def test_no_domain_charter_staged_is_a_gap(self, repo):
        result = gaps(repo, ["web/view.js"], "cross-cutting.md")
        assert result == [{"kind": "domain", "files": ["web/view.js"],
                           "charters": ["server.md", "ui.md"]}]

    def test_each_matched_row_needs_its_own_domain_charter(self, repo):
        """A UI charter does not satisfy the server row."""
        result = gaps(repo, ["web/view.js", "server/app.py"], "ui.md")
        assert result == [{"kind": "domain", "files": ["server/app.py"],
                           "charters": ["server.md"]}]

    def test_files_on_one_row_are_reported_together(self, repo):
        result = gaps(repo, ["web/view.js", "web/style.css"], "core.md")
        assert result == [{"kind": "domain",
                           "files": ["web/view.js", "web/style.css"],
                           "charters": ["server.md", "ui.md"]}]


class TestCrossCutting:

    def test_not_required_for_a_file_it_does_not_cover(self, repo):
        """The old rule required it on every row that listed it."""
        assert gaps(repo, ["server/app.py"], "server.md") == []

    def test_required_for_a_file_its_covers_line_names(self, repo):
        result = gaps(repo, ["src/core.py"], "core.md")
        assert result == [{"kind": "cross-cutting", "files": ["src/core.py"],
                           "charters": ["cross-cutting.md"]}]
        assert gaps(repo, ["src/core.py"], "core.md", "cross-cutting.md") == []

    def test_covers_globs_use_the_shared_grammar(self, repo):
        result = gaps(repo, ["src/shared/util.py"], "core.md")
        assert [g["kind"] for g in result] == ["cross-cutting"]

    def test_covered_file_still_needs_its_domain_charter(self, repo):
        result = gaps(repo, ["src/core.py"], "cross-cutting.md")
        assert result == [{"kind": "domain", "files": ["src/core.py"],
                           "charters": ["core.md"]}]

    def test_row_with_only_cross_cutting_requires_it(self, repo):
        result = gaps(repo, ["src/cli.py"], "ui.md")
        assert result == [{"kind": "domain", "files": ["src/cli.py"],
                           "charters": ["cross-cutting.md"]}]
        assert gaps(repo, ["src/cli.py"], "cross-cutting.md") == []


class TestEdges:

    def test_unrouted_file_has_no_gap(self, repo):
        assert gaps(repo, ["tests/test_x.py"], "ui.md") == []

    def test_no_index_means_no_gap(self, repo):
        (repo / ".gator" / "charters" / "INDEX.md").unlink()
        assert gaps(repo, ["web/view.js"], "core.md") == []

    def test_staged_charter_paths_match_by_file_name(self, repo):
        result = charter.charter_index_gaps(
            ["web/view.js"], [".gator\\charters\\ui.md"], repo)
        assert result == []


class TestHookMessage:

    def test_validate_reports_one_charter_index_gap(self, repo, monkeypatch):
        monkeypatch.setattr(
            pre_commit, "classify_staged_files",
            lambda staged: (True, True, ["web/view.js", "src/core.py"],
                            _staged("cross-cutting.md")))
        monkeypatch.setattr(pre_commit, "charter_index_gaps",
                            charter.charter_index_gaps)
        failures = pre_commit.validate_hard_rules(
            staged_files=[], frontmatter={"message": "m"}, body="b",
            parse_error=None, gator_dir=repo / ".gator")
        gap = [msg for rule, msg in failures if rule == "charter-index-gap"]
        assert gap == [
            "INDEX.md routes src/core.py to core.md; update it. "
            "INDEX.md routes web/view.js to server.md or ui.md; update at least "
            "one of them. Then retry."]

    def test_satisfied_routing_adds_no_failure(self, repo, monkeypatch):
        monkeypatch.setattr(
            pre_commit, "classify_staged_files",
            lambda staged: (True, True, ["web/view.js"], _staged("ui.md")))
        monkeypatch.setattr(pre_commit, "charter_index_gaps",
                            charter.charter_index_gaps)
        failures = pre_commit.validate_hard_rules(
            staged_files=[], frontmatter={"message": "m"}, body="b",
            parse_error=None, gator_dir=repo / ".gator")
        assert not [f for f in failures if f[0] == "charter-index-gap"]

    def test_cross_cutting_message(self):
        text = pre_commit.format_charter_index_gaps(
            [{"kind": "cross-cutting", "files": ["src/core.py"],
              "charters": ["cross-cutting.md"]}])
        assert text == "cross-cutting.md covers src/core.py; update it. Then retry."
