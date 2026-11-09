"""`gator --explain` and session orientation outside a governed repository.

Each test proves one risk from the 2026-11-09 sketch, using a fake home
directory so the real `~/.gator/` is never touched:
- `~/.gator/` is Gator's machine state, never a repository's Gator layer, in
  every copy of `find_gator_root()` (wheel, starter, Enterprise bundle, Loop,
  both hooks), while a real repository under home is still found;
- `gator init` from an ungoverned folder under home exits non-zero, never
  claims to be oriented, and points to `gator --explain` (the observed
  mis-orientation: "found .gator/ … oriented. the terrain is mapped.");
- `gator --explain` prints the three Welcome documents in the Architect's
  order with paths that exist, a correct live section in each situation,
  lists only real governed repositories (never home), and writes nothing.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import load_script

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "src" / "gator_command" / "scripts"
TEMPLATE = ROOT / "src" / "gator_command" / "templates" / "gator-starter" / "scripts"
BUNDLED = ROOT / "enterprise" / "enterprise-cli" / "gator_enterprise_cli" / "bundled_scripts"

FINDERS = {
    "wheel gator_core": lambda: load_script("gator_core").find_gator_root,
    "starter gator_core": lambda: load_script("gator_core", search_dir=TEMPLATE).find_gator_root,
    "bundled gator_core": lambda: load_script("gator_core", search_dir=BUNDLED).find_gator_root,
    "starter hook": lambda: load_script("gator-pre-commit", search_dir=TEMPLATE).find_gator_root,
    "bundled hook": lambda: load_script("gator-pre-commit", search_dir=BUNDLED).find_gator_root,
    "loop session": lambda: load_script("session", search_dir=SCRIPTS / "loop").find_gator_root,
}


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A fake home with Gator's machine-state directory in it."""
    h = tmp_path / "home"
    (h / ".gator").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.setenv("USERPROFILE", str(h))
    return h


def _call(find, start):
    try:
        return find(str(start))
    except FileNotFoundError:          # loop/session.py raises instead of returning None
        return None


@pytest.mark.parametrize("name", sorted(FINDERS))
def test_machine_state_is_never_a_repository(home, name):
    find = FINDERS[name]()
    elsewhere = home / "Downloads" / "notes"
    elsewhere.mkdir(parents=True)
    assert _call(find, home) is None
    assert _call(find, elsewhere) is None
    repo = home / "code" / "proj"
    (repo / ".gator").mkdir(parents=True)
    (repo / "src").mkdir()
    assert Path(_call(find, repo / "src")).resolve() == repo.resolve()


def _env(home):
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), PYTHONIOENCODING="utf-8")
    return env


def test_init_outside_a_governed_repository_points_to_explain(home):
    folder = home / "Downloads"
    folder.mkdir()
    r = subprocess.run([sys.executable, str(SCRIPTS / "gator-init.py")], cwd=folder,
                       env=_env(home), capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 1
    assert "gator --explain" in r.stdout
    assert "not a governed repository" in r.stdout
    assert "oriented" not in r.stdout and "found .gator/" not in r.stdout
    assert not (home / ".git").exists()


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def explain(home, monkeypatch):
    """gator-explain loaded against a registry inside the fake home."""
    gator_core = load_script("gator_core")
    monkeypatch.setitem(sys.modules, "gator_core", gator_core)   # restored after the test
    registry = home / ".gator" / "dashboard-repos.json"
    monkeypatch.setattr(gator_core, "DASHBOARD_REGISTRY", registry)
    governed = home / "code" / "governed"
    (governed / ".gator").mkdir(parents=True)
    registry.write_text(json.dumps({"schema": "gator-dashboard-registry-v1", "repos": [
        {"name": "governed", "path": str(governed)},
        {"name": "home-by-mistake", "path": str(home)},
        {"name": "gone", "path": str(home / "code" / "deleted")},
    ]}), encoding="utf-8")
    return load_script("gator-explain"), governed


def test_explain_lists_the_documents_in_order_and_they_exist(explain, home):
    mod, _ = explain
    out = mod.render(home)
    names = [n for n, _ in mod.READING_ORDER]
    assert names == ["gator-overview.html", "gatorize-a-repo.html", "what-gator-can-do.html"]
    positions = [out.index(str(mod.DOCS_DIR / n)) for n in names]
    assert positions == sorted(positions)
    assert all((mod.DOCS_DIR / n).is_file() for n in names)
    assert "missing from this install" not in out
    assert "start-a-session.html" not in out


@pytest.mark.parametrize("where", ["outside", "ungoverned-git", "governed"])
def test_explain_where_you_are(explain, home, where):
    mod, governed = explain
    if where == "outside":
        cwd = home / "Downloads"; cwd.mkdir()
    elif where == "ungoverned-git":
        cwd = home / "code" / "plain"; cwd.mkdir(parents=True); _git(cwd, "init", "-q")
    else:
        cwd = governed
    before = sorted(p.relative_to(home) for p in home.rglob("*"))
    out = mod.render(cwd)
    if where == "governed":
        assert f"Governed repository: {governed.resolve()}" in out
        assert "run `gator init` here" in out
    else:
        assert f"    - governed: {governed}" in out
        assert "home-by-mistake" not in out and "gone" not in out
        assert "ask the Architect which repository" in out
        assert ("(not governed by Gator)" in out) == (where == "ungoverned-git")
    assert sorted(p.relative_to(home) for p in home.rglob("*")) == before   # writes nothing


def test_cli_flag_runs_explain():
    r = subprocess.run([sys.executable, str(ROOT / "src" / "gator_command" / "cli.py"), "--explain"],
                       capture_output=True, text=True, encoding="utf-8",
                       env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    assert r.returncode == 0
    assert "Read these documents, in order:" in r.stdout
    assert "Where you are:" in r.stdout
