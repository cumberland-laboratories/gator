"""Parity checks for the Cumberland shared CSS core and Slice-2 mirrors.

The Cumberland master template ships in a canonical source at
`src/gator_command/templates/gator-starter/reference-notes/cumberland-html-document-template.html`
with a dogfood mirror at `.gator/.includes/reference-notes/…`. The
narrative-Blueprint specialization ships at
`src/gator_command/templates/gator-starter/blueprints/_template-narrative.html`
with a user-visible-scaffolding-root mirror at
`.gator/blueprints/_template-narrative.html`. Codex Sketch 2 Slice 3
(2026-09-12) reconciled the two anchor files by pinning the CSS core
between `CUMBERLAND-NARRATIVE-STYLE:BEGIN` and `CUMBERLAND-NARRATIVE-STYLE:END`
delimiters to be byte-for-byte identical.

Codex enforcer follow-up (2026-09-13 F3) — this module also owns
Slice-2 constitution and authoring-procedure source↔dogfood parity,
because the original claim that `tests/test_template_sync.py` supplied
those checks was false (that test only covers `gator-update.py`).

Coverage:

    * Master ↔ master-mirror: byte-identical file.
    * Narrative-source ↔ narrative-scaffolding-root: byte-identical file.
    * Master ↔ narrative shared region: byte-identical inside the
      `CUMBERLAND-NARRATIVE-STYLE:BEGIN/END` delimiters (all four copies
      participate transitively).
    * Constitution source ↔ dogfood: byte-identical.
    * Authoring-procedure source ↔ dogfood: byte-identical.
    * Both anchor files carry the shared-region markers (regression pin
      against accidental delimiter removal).

Why byte-identical instead of a shared @import: HTML artifacts are
self-contained by contract (no external CSS/JS), so both files ship
the same CSS in-body. The parity check eliminates drift without
breaking self-containment. Constitution + authoring-procedure use the
same mirror pattern (shipped template + `.gator/.includes/` dogfood)
and inherit the same drift risk, which is why Slice 2's mirrors are
pinned here rather than left to hope that
`tests/test_template_sync.py` covers them (it does not).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# ── Cumberland anchor files ──────────────────────────────────────

MASTER_SRC = (REPO_ROOT / "src" / "gator_command" / "templates"
              / "gator-starter" / "reference-notes"
              / "cumberland-html-document-template.html")
MASTER_MIRROR = (REPO_ROOT / ".gator" / ".includes"
                 / "reference-notes"
                 / "cumberland-html-document-template.html")
NARRATIVE_SRC = (REPO_ROOT / "src" / "gator_command" / "templates"
                 / "gator-starter" / "blueprints"
                 / "_template-narrative.html")
NARRATIVE_MIRROR = (REPO_ROOT / ".gator" / "blueprints"
                    / "_template-narrative.html")

# ── Slice-2 mirror pairs ─────────────────────────────────────────

CONSTITUTION_SRC = (REPO_ROOT / "src" / "gator_command" / "templates"
                    / "gator-starter" / "constitution.md")
CONSTITUTION_MIRROR = (REPO_ROOT / ".gator" / ".includes" / "constitution.md")
AUTHORING_SRC = (REPO_ROOT / "src" / "gator_command" / "templates"
                 / "gator-starter" / "procedures"
                 / "authoring-html-artifacts.md")
AUTHORING_MIRROR = (REPO_ROOT / ".gator" / ".includes" / "procedures"
                    / "authoring-html-artifacts.md")


REGION_RE = re.compile(
    r'/\*\s*CUMBERLAND-NARRATIVE-STYLE:BEGIN'
    r'.*?'
    r'CUMBERLAND-NARRATIVE-STYLE:END[^*]*\*/',
    re.DOTALL,
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_shared_region(path: Path) -> str:
    """Return the shared CSS core enclosed by the CUMBERLAND-NARRATIVE-STYLE
    markers, INCLUDING both delimiter comments. Raises AssertionError if
    the markers are absent — marker-existence has its own pin below with
    a clearer failure message.
    """
    text = _read(path)
    match = REGION_RE.search(text)
    assert match is not None, (
        f"{path}: shared region markers not found — expected "
        f"`/* CUMBERLAND-NARRATIVE-STYLE:BEGIN ... */` and "
        f"`/* CUMBERLAND-NARRATIVE-STYLE:END ... */` in the <style> block")
    return match.group(0)


def _shared_region_diff_message(paths_a: str, paths_b: str,
                                region_a: str, region_b: str) -> str:
    """Compact diff summary — first divergent line index + surrounding
    context — instead of a 15 KB byte-diff dump."""
    lines_a = region_a.splitlines()
    lines_b = region_b.splitlines()
    diff_line = None
    for i, (a, b) in enumerate(zip(lines_a, lines_b)):
        if a != b:
            diff_line = i
            break
    if diff_line is None:
        diff_line = min(len(lines_a), len(lines_b))
    return (
        f"CUMBERLAND-NARRATIVE-STYLE region differs.\n"
        f"  {paths_a}:  {len(lines_a)} lines, {len(region_a)} chars\n"
        f"  {paths_b}:  {len(lines_b)} lines, {len(region_b)} chars\n"
        f"  first divergent line index: {diff_line}\n"
        f"  {paths_a}[{diff_line}]:  "
        f"{lines_a[diff_line] if diff_line < len(lines_a) else '<end>'!r}\n"
        f"  {paths_b}[{diff_line}]:  "
        f"{lines_b[diff_line] if diff_line < len(lines_b) else '<end>'!r}\n"
        f"Fix: edit both files or re-sync the mirror pair.")


# ── Marker-existence pins (all four Cumberland copies) ────────────

@pytest.mark.parametrize("path", [MASTER_SRC, MASTER_MIRROR,
                                  NARRATIVE_SRC, NARRATIVE_MIRROR],
                         ids=["master-src", "master-mirror",
                              "narrative-src", "narrative-mirror"])
def test_file_contains_begin_and_end_markers(path: Path):
    """Every Cumberland copy carries both delimiter markers. Silent
    removal would let the shared region drift without any parity pin
    firing (the region extraction would return None and the compare
    would skip via AssertionError instead of surfacing the real
    problem).
    """
    if not path.is_file():
        pytest.skip(f"{path} not present (fleet repo before first update?)")
    text = _read(path)
    assert "CUMBERLAND-NARRATIVE-STYLE:BEGIN" in text, (
        f"{path}: missing BEGIN marker")
    assert "CUMBERLAND-NARRATIVE-STYLE:END" in text, (
        f"{path}: missing END marker")


# ── Cumberland mirror-pair byte-equality ──────────────────────────

@pytest.mark.skipif(
    not (MASTER_SRC.is_file() and MASTER_MIRROR.is_file()),
    reason="Cumberland master or master mirror not present")
def test_master_source_and_mirror_are_byte_identical():
    """Master ships in two copies: source-of-truth at
    `templates/gator-starter/reference-notes/…` and dogfood mirror at
    `.gator/.includes/reference-notes/…`. Both must be byte-identical.

    Codex enforcer follow-up 2026-09-13 F3: prior parity coverage
    implicitly assumed `tests/test_template_sync.py` pinned this
    mirror pair; it does not (that test only covers `gator-update.py`).
    Explicit pin here closes the drift channel."""
    assert MASTER_SRC.read_bytes() == MASTER_MIRROR.read_bytes(), (
        f"Cumberland master source ({MASTER_SRC}) and dogfood mirror "
        f"({MASTER_MIRROR}) have drifted — one was edited without the "
        f"other. Re-copy from whichever is canonical.")


@pytest.mark.skipif(
    not (NARRATIVE_SRC.is_file() and NARRATIVE_MIRROR.is_file()),
    reason="Narrative Blueprint source or scaffolding-root mirror not present")
def test_narrative_source_and_mirror_are_byte_identical():
    """Narrative Blueprint template ships at
    `templates/gator-starter/blueprints/…` (shipped source) and lives
    at `.gator/blueprints/…` in dogfood (scaffolding-root — per
    USER_VISIBLE_SCAFFOLDING). Both must be byte-identical.

    Codex enforcer follow-up 2026-09-13 F3: this pin closes the same
    drift channel as the master mirror pin above."""
    assert NARRATIVE_SRC.read_bytes() == NARRATIVE_MIRROR.read_bytes(), (
        f"Narrative Blueprint template source ({NARRATIVE_SRC}) and "
        f"scaffolding-root mirror ({NARRATIVE_MIRROR}) have drifted. "
        f"Re-copy from whichever is canonical.")


# ── Shared-region byte-equality across all four Cumberland files ─

@pytest.mark.skipif(
    not (MASTER_SRC.is_file() and NARRATIVE_SRC.is_file()),
    reason="Cumberland master or narrative Blueprint source not present")
def test_cumberland_shared_region_master_vs_narrative_source():
    """The Slice-3 parity invariant, held at the canonical source pair
    (both shipped sources). Master mirror ↔ master source and narrative
    mirror ↔ narrative source are pinned separately above, so this
    single source-pair check transitively covers all four copies."""
    master_region = _extract_shared_region(MASTER_SRC)
    narrative_region = _extract_shared_region(NARRATIVE_SRC)
    if master_region != narrative_region:
        pytest.fail(_shared_region_diff_message(
            "master-src", "narrative-src", master_region, narrative_region))


@pytest.mark.skipif(
    not (MASTER_MIRROR.is_file() and NARRATIVE_MIRROR.is_file()),
    reason="Cumberland dogfood mirrors not present")
def test_cumberland_shared_region_master_vs_narrative_mirrors():
    """Parallel to the source-pair check above but on the dogfood
    mirrors. Belt-and-suspenders against the theoretical case where a
    mirror pair pin passes (both mirrors updated together) but only
    ONE of the mirrors got the shared-region edit."""
    master_region = _extract_shared_region(MASTER_MIRROR)
    narrative_region = _extract_shared_region(NARRATIVE_MIRROR)
    if master_region != narrative_region:
        pytest.fail(_shared_region_diff_message(
            "master-mirror", "narrative-mirror",
            master_region, narrative_region))


# ── Slice-2 constitution + authoring-procedure mirror pairs ──────

@pytest.mark.skipif(
    not (CONSTITUTION_SRC.is_file() and CONSTITUTION_MIRROR.is_file()),
    reason="Constitution source or mirror not present")
def test_constitution_source_and_mirror_are_byte_identical():
    """Slice 2 added the `## HTML Documents` section to both copies
    of the constitution. They must stay byte-identical — the constitution
    is the always-read routing rule; drift between the shipped copy
    (what fleet repos receive) and the dogfood copy (what this repo
    uses) means agents in the source repo would read a different rule
    than agents in a gatorized fleet repo.

    Codex enforcer follow-up 2026-09-13 F3: `tests/test_template_sync.py`
    was falsely claimed to cover this; it does not. Explicit pin here."""
    assert CONSTITUTION_SRC.read_bytes() == CONSTITUTION_MIRROR.read_bytes(), (
        f"Constitution source ({CONSTITUTION_SRC}) and dogfood mirror "
        f"({CONSTITUTION_MIRROR}) have drifted.")


@pytest.mark.skipif(
    not (AUTHORING_SRC.is_file() and AUTHORING_MIRROR.is_file()),
    reason="Authoring-procedure source or mirror not present")
def test_authoring_procedure_source_and_mirror_are_byte_identical():
    """Slice 2 broadened `authoring-html-artifacts.md` to medium-first
    triage in both copies. The procedure is referenced from the
    constitution's `## HTML Documents` section — drift between the
    shipped and dogfood copies means the routing rule would land agents
    at inconsistent instructions."""
    assert AUTHORING_SRC.read_bytes() == AUTHORING_MIRROR.read_bytes(), (
        f"Authoring-procedure source ({AUTHORING_SRC}) and dogfood "
        f"mirror ({AUTHORING_MIRROR}) have drifted.")
