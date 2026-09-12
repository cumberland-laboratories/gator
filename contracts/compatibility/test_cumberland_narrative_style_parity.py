"""Parity check for the Cumberland shared CSS core (Codex Sketch 2 Slice 3).

The Cumberland master template
(`src/gator_command/templates/gator-starter/reference-notes/cumberland-html-document-template.html`)
and the narrative-Blueprint specialization
(`.gator/blueprints/_template-narrative.html`) both carry the same
visual grammar. Slice 3 (2026-09-12) reconciles them by pinning the
CSS core between `CUMBERLAND-NARRATIVE-STYLE:BEGIN` and
`CUMBERLAND-NARRATIVE-STYLE:END` delimiters to be byte-for-byte
identical across the two files.

This test asserts:

    1. Both files contain the BEGIN and END markers (regression pin
       against accidentally removing them).
    2. The region enclosed by the markers — from `/* CUMBERLAND-
       NARRATIVE-STYLE:BEGIN` through the `*/` that closes the END
       delimiter — is byte-for-byte equal across the two files.

Both files are also mirrored to shipped-template copies under
`src/gator_command/templates/gator-starter/…`; those mirrors are pinned
identical by `tests/test_template_sync.py`, so this compat test
targets ONLY the source-repo/dogfood copies. The template-sync test
extends the parity to the shipped copies transitively.

Why byte-identical instead of a shared @import: HTML artifacts are
self-contained by contract (no external CSS/JS), so both files ship
the same CSS in-body. The parity check eliminates drift without
breaking self-containment.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

MASTER = (REPO_ROOT / "src" / "gator_command" / "templates"
          / "gator-starter" / "reference-notes"
          / "cumberland-html-document-template.html")

NARRATIVE = (REPO_ROOT / ".gator" / "blueprints"
             / "_template-narrative.html")

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
    the markers are absent (delegated to the per-file existence pins below,
    which give clearer failure messages).
    """
    text = _read(path)
    match = REGION_RE.search(text)
    assert match is not None, (
        f"{path}: shared region markers not found — expected "
        f"`/* CUMBERLAND-NARRATIVE-STYLE:BEGIN ... */` and "
        f"`/* CUMBERLAND-NARRATIVE-STYLE:END ... */` in the <style> block")
    return match.group(0)


@pytest.mark.skipif(not MASTER.is_file(),
                    reason="Cumberland master not present (fleet repo)")
def test_master_contains_begin_and_end_markers():
    """The master must carry both delimiter markers so the parity check
    has anchor points. Silent removal would let the two files drift
    without the check firing.
    """
    text = _read(MASTER)
    assert "CUMBERLAND-NARRATIVE-STYLE:BEGIN" in text, (
        f"{MASTER}: missing BEGIN marker")
    assert "CUMBERLAND-NARRATIVE-STYLE:END" in text, (
        f"{MASTER}: missing END marker")


@pytest.mark.skipif(not NARRATIVE.is_file(),
                    reason="Narrative Blueprint template not present")
def test_narrative_contains_begin_and_end_markers():
    """The narrative Blueprint specialization must carry the same markers."""
    text = _read(NARRATIVE)
    assert "CUMBERLAND-NARRATIVE-STYLE:BEGIN" in text, (
        f"{NARRATIVE}: missing BEGIN marker")
    assert "CUMBERLAND-NARRATIVE-STYLE:END" in text, (
        f"{NARRATIVE}: missing END marker")


@pytest.mark.skipif(
    not (MASTER.is_file() and NARRATIVE.is_file()),
    reason="Cumberland master or narrative Blueprint template not present")
def test_cumberland_shared_region_is_byte_identical():
    """The CSS core enclosed by CUMBERLAND-NARRATIVE-STYLE:BEGIN/END
    must be byte-for-byte equal between the master and the narrative
    Blueprint specialization. This is the parity invariant Codex Sketch
    2 Slice 3 pins — any edit inside the delimiters in either file
    without a matching edit in the other file fails this test.
    """
    master_region = _extract_shared_region(MASTER)
    narrative_region = _extract_shared_region(NARRATIVE)
    if master_region != narrative_region:
        # Show a compact diff summary instead of dumping 15 KB of CSS.
        master_lines = master_region.splitlines()
        narrative_lines = narrative_region.splitlines()
        diff_line = None
        for i, (m, n) in enumerate(zip(master_lines, narrative_lines)):
            if m != n:
                diff_line = i
                break
        if diff_line is None:
            diff_line = min(len(master_lines), len(narrative_lines))
        pytest.fail(
            f"CUMBERLAND-NARRATIVE-STYLE region differs.\n"
            f"  master:    {len(master_lines)} lines, {len(master_region)} chars\n"
            f"  narrative: {len(narrative_lines)} lines, {len(narrative_region)} chars\n"
            f"  first divergent line index: {diff_line}\n"
            f"  master[{diff_line}]:    {master_lines[diff_line] if diff_line < len(master_lines) else '<end>'!r}\n"
            f"  narrative[{diff_line}]: {narrative_lines[diff_line] if diff_line < len(narrative_lines) else '<end>'!r}\n"
            f"Fix: edit both files or run the Slice-3 substitution script "
            f"to re-sync the narrative template from the master.")
