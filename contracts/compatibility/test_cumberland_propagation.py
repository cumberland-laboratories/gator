"""Cumberland master propagation checks (Codex Sketch 2 Slice 4, F4;
CI-topology-corrected 2026-09-13 F1 round-3 re-review).

The master must reach fleet repos through the shipped delivery path.
This module owns the pieces of that seam that fit the fast
compatibility matrix (no `build` package required, no wheel build):

    1. The master file exists at the canonical shipped location under
       `src/gator_command/templates/gator-starter/reference-notes/`.
    2. `gator-update`'s `plan_updates` function, when run against an
       empty v2 repo with the current template source, produces a
       plan entry that adds the master to `.gator/.includes/reference-notes/`.

The other two seams live in the CI job that actually runs them:

    * Actual wheel content — pinned in
      `tests/test_packaging.py::TestWheelBuildAndContents` alongside
      the other wheel-content assertions. That is the ONLY job in CI
      that installs `build` and runs its test file, so wheel-content
      pins in the compatibility suite would silently skip on the
      fast matrix and never run on the packaging matrix.
    * A REAL `action_install_gator()` on tmp_path places the master
      at `.gator/.includes/reference-notes/…` — pinned in
      `contracts/compatibility/test_gator_layout.py::test_gatorize_install_produces_required_layout`
      which reuses the existing install fixture.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

MASTER_SRC = (REPO_ROOT / "src" / "gator_command" / "templates"
              / "gator-starter" / "reference-notes"
              / "cumberland-html-document-template.html")

MASTER_FILENAME = "cumberland-html-document-template.html"


# ── 1. Source existence at canonical shipped path ────────────────

def test_cumberland_master_exists_at_shipped_path():
    """The master must exist at the exact path the wheel packages.
    This is the load-bearing existence check — everything else
    (wheel-content pin in test_packaging.py, gatorize walk, update
    plan) references this path."""
    assert MASTER_SRC.is_file(), (
        f"Cumberland master missing at canonical shipped path: {MASTER_SRC}\n"
        f"This is where gatorize + gator-update walk to find template "
        f"files. Missing here means every fleet repo would not receive "
        f"the master on install or update.")


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
