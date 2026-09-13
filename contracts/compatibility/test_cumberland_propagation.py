"""Cumberland master propagation checks (Codex Sketch 2 Slice 4, F4).

Codex Sketch 2 Slice 4 requires the master to reach fleet repos through
the shipped delivery path. Codex enforcer 2026-09-13 F2 tightened this
from a source-existence + glob-literal check to a real wheel-content
inspection + real gatorize execution:

    1. The master file exists at the canonical shipped location under
       `src/gator_command/templates/gator-starter/reference-notes/`.
    2. A REAL wheel built from the current source tree contains the
       master at the expected package-data path — proves setuptools
       actually packages it, not just that the glob literal appears
       in pyproject.toml. This closes the class of failure where
       exclusions or packaging quirks would silently drop the file.
    3. `gator-update`'s `plan_updates` function, when run against an
       empty v2 repo with the current template source, produces a
       plan entry that adds the master to `.gator/.includes/reference-notes/`.
    4. A REAL `action_install_gator()` on a tmp_path places the master
       at that destination (pinned separately in test_gator_layout.py
       to avoid duplicating the fixture setup).

The wheel-build test is session-scoped so `python -m build` runs once
per test session; the resulting artifact is cached and re-inspected
by all wheel-content assertions.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

MASTER_SRC = (REPO_ROOT / "src" / "gator_command" / "templates"
              / "gator-starter" / "reference-notes"
              / "cumberland-html-document-template.html")

MASTER_FILENAME = "cumberland-html-document-template.html"


# ── 1. Wheel content (via canonical source path) ─────────────────

def test_cumberland_master_exists_at_shipped_path():
    """The master must exist at the exact path the wheel packages.
    This is the load-bearing existence check — everything else
    (packaging glob, gatorize walk, update plan) references this
    path."""
    assert MASTER_SRC.is_file(), (
        f"Cumberland master missing at canonical shipped path: {MASTER_SRC}\n"
        f"This is where gatorize + gator-update walk to find template "
        f"files. Missing here means every fleet repo would not receive "
        f"the master on install or update.")


@pytest.fixture(scope="session")
def built_wheel_members(tmp_path_factory):
    """Build a wheel from the current source tree once per test
    session and return the list of member paths inside it. Session-
    scoped because `python -m build --wheel` takes several seconds;
    all wheel-content assertions read the same cached listing.

    Skips gracefully when `build` is not importable (dev-only
    dependency) — the source-existence + gatorize + plan pins still
    give partial coverage on installs without `build`.
    """
    try:
        import build  # noqa: F401
    except ImportError:
        pytest.skip("`build` package not installed — skipping "
                    "wheel-content inspection")

    outdir = tmp_path_factory.mktemp("wheel_build")
    result = subprocess.run(
        [sys.executable, "-m", "build", "--wheel",
         "--outdir", str(outdir), str(REPO_ROOT)],
        capture_output=True, text=True,
        # Long enough for a fresh build; captured on failure.
        timeout=180,
    )
    assert result.returncode == 0, (
        f"wheel build failed (rc={result.returncode})\n"
        f"stdout tail:\n{result.stdout[-2000:]}\n"
        f"stderr tail:\n{result.stderr[-2000:]}")

    wheels = list(outdir.glob("gator_command-*.whl"))
    assert wheels, (
        f"no gator_command wheel produced in {outdir}. "
        f"Files present: {[p.name for p in outdir.iterdir()]!r}")
    with zipfile.ZipFile(wheels[0]) as zf:
        return zf.namelist()


def test_wheel_contains_cumberland_master(built_wheel_members):
    """A real wheel built from the current source tree must contain
    the Cumberland master at the exact package-data path setuptools
    should ship it at. Codex enforcer 2026-09-13 F2 called out that
    the prior glob-literal check would stay green even if setuptools
    exclusions dropped the file at build time — this pin closes the
    gap by actually building a wheel and inspecting its zip contents.
    """
    expected = ("gator_command/templates/gator-starter/reference-notes/"
                "cumberland-html-document-template.html")
    matching = [m for m in built_wheel_members if m == expected]
    if matching:
        return
    # Failure diagnostic — show any near-miss + the template surface
    # so a rename or path change is easy to spot.
    template_members = [m for m in built_wheel_members
                        if "templates/gator-starter" in m]
    near_miss = [m for m in built_wheel_members
                 if "cumberland" in m.lower()]
    pytest.fail(
        f"Cumberland master missing from built wheel.\n"
        f"  Expected member: {expected}\n"
        f"  Near-miss (any 'cumberland' in name): {near_miss!r}\n"
        f"  Total template-tree members shipped: {len(template_members)}\n"
        f"  First 10 template members: {template_members[:10]!r}")


def test_wheel_ships_full_cumberland_delivery_surface(built_wheel_members):
    """Companion to the master pin: the built wheel must also carry
    the narrative Blueprint template (which inherits the master's
    CSS core byte-for-byte) AND the two files Slice 2 edited
    (constitution + authoring-html-artifacts.md procedure). Any of
    these missing from the wheel means fleet repos would not receive
    the reconciled surface, breaking the routing rule the
    constitution HTML Documents section establishes.
    """
    expected = {
        "gator_command/templates/gator-starter/reference-notes/"
        "cumberland-html-document-template.html",
        "gator_command/templates/gator-starter/blueprints/"
        "_template-narrative.html",
        "gator_command/templates/gator-starter/constitution.md",
        "gator_command/templates/gator-starter/procedures/"
        "authoring-html-artifacts.md",
    }
    members = set(built_wheel_members)
    missing = expected - members
    assert not missing, (
        f"Wheel is missing Cumberland-arc shipped files:\n"
        f"  Missing: {sorted(missing)!r}\n"
        f"  Wheel has {len(members)} members total.")


# ── 2. Update plan routing ───────────────────────────────────────

@pytest.fixture(scope="module")
def gator_update_module():
    """Load `gator-update.py` as an importable module (its hyphenated
    filename prevents plain `import`)."""
    import importlib.util
    script = (REPO_ROOT / "src" / "gator_command"
              / "scripts" / "gator-update.py")
    if not script.is_file():
        pytest.skip(f"gator-update.py not found at {script}")
    # Make sibling modules (gator_layout, gator_core) importable
    scripts_dir = script.parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    spec = importlib.util.spec_from_file_location(
        "gator_update_under_test", str(script))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _seed_minimal_v2_repo(root: Path) -> None:
    """Create the minimum v2 layout `gator-update` will accept as a
    target: `.gator/.includes/` with `constitution.md` + `scripts/`,
    plus `layout-version.json` declaring v2. No user-content
    scaffolding required for the plan step."""
    gator = root / ".gator"
    gator.mkdir()
    includes = gator / ".includes"
    includes.mkdir()
    (includes / "constitution.md").write_text("# stub\n", encoding="utf-8")
    (includes / "scripts").mkdir()
    (gator / "layout-version.json").write_text(
        '{"layout": "v2"}\n', encoding="utf-8")


def test_gator_update_plans_master_into_v2_includes(
        gator_update_module, tmp_path):
    """On a v2 repo, `gator-update`'s `plan_updates` must produce an
    entry that puts the Cumberland master at
    `.gator/.includes/reference-notes/cumberland-html-document-template.html`.
    This is the propagation invariant Codex F4 asks for — proving the
    master travels through the update path to the correct destination
    on the layout every new install produces.
    """
    _seed_minimal_v2_repo(tmp_path)
    templates_dir = (REPO_ROOT / "src" / "gator_command" / "templates"
                     / "gator-starter")
    plan = gator_update_module.plan_updates(
        templates_dir, tmp_path / ".gator", tmp_path)

    # `plan` is a list of (action, source_path, dest_path) tuples.
    # Find any entry whose dest ends with the master filename.
    matching = [
        entry for entry in plan
        if isinstance(entry, tuple) and len(entry) >= 3
        and str(entry[2]).endswith(MASTER_FILENAME)
    ]
    assert matching, (
        f"gator-update plan does not include {MASTER_FILENAME}. "
        f"First 5 dests in plan: "
        f"{[str(e[2]) for e in plan[:5] if isinstance(e, tuple) and len(e) >= 3]!r}")

    action, _source, dest = matching[0]
    dest = Path(dest)
    # v2 layout puts shipped content under .gator/.includes/
    expected_dir = tmp_path / ".gator" / ".includes" / "reference-notes"
    assert dest.parent == expected_dir, (
        f"Cumberland master planned at {dest.parent}, expected "
        f"{expected_dir}. v2 shipped content must land under "
        f".includes/, not the user-visible root.")
    # Action is `add` since our seed repo has no reference-notes yet.
    assert action in ("add", "update"), (
        f"Unexpected action for master: {action!r}")
