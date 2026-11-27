"""
#109 and on-demand folders: authoring templates live in `.gator/.includes/`,
and `threads/`, `policies/`, `field-guides/` (and user `reference-notes/`)
appear only on first use. The fresh-install shape is pinned by
`contracts/compatibility/test_gator_layout.py`.
"""

import subprocess
from pathlib import Path

import pytest

from conftest import load_script

update = load_script("gator-update")
gatorize = load_script("gatorize")
init = load_script("gator-init")

import gator_layout  # noqa: E402  (on sys.path via conftest)

TEMPLATES = Path(__file__).resolve().parent.parent / "src" / "gator_command" / "templates" / "gator-starter"


def _git(cwd, *args):
    r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                        "-c", "commit.gpgsign=false", *args],
                       cwd=cwd, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return r.stdout


def _v2_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".gator" / ".includes").mkdir(parents=True)
    (repo / ".gator" / "layout-version.json").write_text('{"layout": "v2"}\n', encoding="utf-8")
    _git(tmp_path, "init", "-q", str(repo))
    _git(repo, "config", "core.hooksPath", str(tmp_path / "no-hooks"))
    return repo


def _write(repo, rel, text="x\n"):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


class TestPlacementRule:

    @pytest.mark.parametrize("dirname,filename,managed", [
        ("charters", "_template.md", True),
        ("artifacts", "_template.md", True),
        ("procedures", "_template.md", True),
        ("charters", "README.md", False),
        ("artifacts", "README.md", False),
        ("blueprints", "_template.html", False),        # #96, unchanged
        ("threads", "README.md", True),
        ("policies", "README.md", True),
        ("field-guides", "README.md", True),
        ("reference-notes", "README.md", True),
        ("docs", "gator-overview.html", False),
    ])
    def test_scaffolding_in_managed_space(self, dirname, filename, managed):
        assert update.scaffolding_in_managed_space(dirname, filename) is managed

    def test_update_plans_no_root_scaffolding_on_v2(self, tmp_path, monkeypatch):
        repo = tmp_path / "installed"
        repo.mkdir()
        _git(tmp_path, "init", "-q", str(repo))
        monkeypatch.setattr(gatorize, "install_hooks", lambda target: None)
        gatorize.action_install_gator(repo)
        gator = repo / ".gator"
        assert not [p for p in gator.glob("*/_template.md")]
        assert not (gator / "threads").exists() and not (gator / "policies").exists()
        plan = update.plan_updates(TEMPLATES, gator, repo)
        dests = {Path(d).relative_to(repo / ".gator").as_posix() for _, _, d in plan}
        root = {d for d in dests if not d.startswith(".includes/")}
        assert not [d for d in root if d.endswith("/_template.md")]
        for folder in ("threads", "policies", "field-guides", "reference-notes"):
            assert not [d for d in root if d.startswith(folder + "/")], folder
        for managed in (".includes/threads/README.md", ".includes/threads/_template.md",
                        ".includes/artifacts/_template.md", ".includes/charters/_template.md",
                        ".includes/procedures/_template.md"):
            assert managed in dests, managed
        assert "artifacts/README.md" in dests


class TestScaffoldCleanup:

    def _legacy(self, tmp_path):
        repo = _v2_repo(tmp_path)
        for rel in (".gator/charters/_template.md", ".gator/charters/README.md",
                    ".gator/artifacts/_template.md", ".gator/procedures/_template.md",
                    ".gator/threads/README.md", ".gator/threads/_template.md",
                    ".gator/policies/README.md", ".gator/policies/_template.md",
                    ".gator/policies/.gitkeep",
                    ".gator/field-guides/README.md", ".gator/field-guides/_template.md",
                    ".gator/field-guides/python-patterns.md"):
            _write(repo, rel)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "legacy")
        return repo

    def test_plan_lists_templates_and_empty_on_demand_folders(self, tmp_path):
        repo = self._legacy(tmp_path)
        actions = gatorize.plan_scaffold_cleanup(repo)
        assert [a["path"] for a in actions] == [
            ".gator/artifacts/_template.md",
            ".gator/charters/_template.md",
            ".gator/field-guides/_template.md",
            ".gator/policies/.gitkeep",
            ".gator/policies/README.md",
            ".gator/policies/_template.md",
            ".gator/procedures/_template.md",
            ".gator/threads/README.md",
            ".gator/threads/_template.md",
        ]
        assert all(a["action"] == "delete" and a["tracked"] for a in actions)

    def test_apply_stages_deletions_and_removes_empty_folders(self, tmp_path):
        repo = self._legacy(tmp_path)
        applied = gatorize.apply_scaffold_cleanup(repo, gatorize.plan_scaffold_cleanup(repo))
        assert len(applied) == 9
        gator = repo / ".gator"
        assert not (gator / "threads").exists() and not (gator / "policies").exists()
        # A folder with real content keeps it and its README.
        assert sorted(p.name for p in (gator / "field-guides").iterdir()) == \
            ["README.md", "python-patterns.md"]
        assert (gator / "charters" / "README.md").is_file()
        staged = _git(repo, "diff", "--cached", "--name-only").split()
        assert ".gator/threads/README.md" in staged and ".gator/charters/_template.md" in staged
        # Nothing left to do.
        assert gatorize.plan_scaffold_cleanup(repo) == []

    def test_untracked_copies_are_unlinked(self, tmp_path):
        repo = _v2_repo(tmp_path)
        _write(repo, ".gator/threads/_template.md")
        actions = gatorize.plan_scaffold_cleanup(repo)
        assert actions == [{"path": ".gator/threads/_template.md", "action": "delete",
                            "tracked": False}]
        gatorize.apply_scaffold_cleanup(repo, actions)
        assert not (repo / ".gator" / "threads").exists()

    def test_v1_layout_is_left_alone(self, tmp_path):
        repo = tmp_path / "v1"
        _write(repo, ".gator/threads/_template.md")
        assert gatorize.plan_scaffold_cleanup(repo) == []

    def test_report_wording(self):
        actions = [{"path": ".gator/threads/README.md", "action": "delete", "tracked": True}]
        assert gatorize.format_scaffold_cleanup(actions, predicted=True) == [
            "  Scaffolding Gator will remove (templates now live in .gator/.includes/):",
            "    - .gator/threads/README.md"]
        assert gatorize.format_scaffold_cleanup(actions)[1] == \
            "    - .gator/threads/README.md (deletion staged)"


class TestInitWorkingSet:

    def test_readme_and_template_are_not_threads(self, tmp_path):
        repo = _v2_repo(tmp_path)
        _write(repo, ".gator/threads/README.md", "a\nb\n")
        _write(repo, ".gator/threads/_template.md", "a\n")
        paths = gator_layout.get_gator_paths(repo)
        assert init.count_working_set(paths) == (0, 0)
        _write(repo, ".gator/threads/topic.md", "one\ntwo\nthree\n")
        assert init.count_working_set(paths) == (1, 3)
