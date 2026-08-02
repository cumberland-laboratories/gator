"""Validate commit-summary and session-summary markdown fixtures.

Both schemas are markdown-with-frontmatter — we assert required keys
are present, the schema tag is correct, and canonical section headers
appear in the body. Structural, not typed-YAML.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ._helpers import parse_frontmatter

COMMIT_REQUIRED_KEYS = {
    "schema", "type", "date", "timestamp", "repo", "vendor",
    "message", "change-type", "significance", "decision-tags",
    "agent", "charter-changed",
}
COMMIT_ARCHITECT_KEYS = {"architect", "pi"}  # either accepted (legacy)

COMMIT_ALLOWED_SECTIONS = {"## Decisions", "## Session Notes"}

SESSION_REQUIRED_KEYS = {
    "schema", "session-id", "date", "start", "end", "repo",
    "agent", "vendor", "machine-id", "machine-label",
    "transcript", "turns", "tools", "branch",
}
SESSION_ARCHITECT_KEYS = {"architect", "pi"}  # either accepted (legacy)

SESSION_REQUIRED_SECTIONS = {
    "## Goal",
    "## Decisions",
    "## Files Changed",
    "## Evidence Location",
}

# Session-summary files with a filename-date prefix earlier than this
# are grandfathered — they carry the tag but predate the current field
# set. New emissions must have the full required set.
SESSION_SUMMARY_LOCKDOWN_DATE = "2026-07-01"


def _read_md(path: Path) -> tuple[dict, str]:
    return parse_frontmatter(path.read_text(encoding="utf-8"))


# ── gator-commit-summary-v1 ─────────────────────────────────────────

@pytest.mark.parametrize("fixture", [
    "valid_commit_summary.md",
    "valid_commit_summary_legacy_pi.md",
])
def test_commit_summary_frontmatter(fixture: str, fixtures_dir: Path) -> None:
    fm, body = _read_md(fixtures_dir / fixture)

    assert fm.get("schema") == "gator-commit-summary-v1", (
        f"{fixture}: schema tag must be gator-commit-summary-v1"
    )
    assert fm.get("type") == "commit", f"{fixture}: type must be 'commit'"

    missing = COMMIT_REQUIRED_KEYS - fm.keys()
    assert not missing, f"{fixture}: missing required keys: {missing}"

    # architect OR legacy pi must be present
    assert fm.keys() & COMMIT_ARCHITECT_KEYS, (
        f"{fixture}: must have either 'architect' or legacy 'pi' key"
    )


def test_commit_summary_body_sections(fixtures_dir: Path) -> None:
    """H2 sections in the body must be from the allowed set."""
    _, body = _read_md(fixtures_dir / "valid_commit_summary.md")
    headers = {line for line in body.splitlines()
               if line.startswith("## ") and not line.startswith("### ")}
    unknown = headers - COMMIT_ALLOWED_SECTIONS
    assert not unknown, f"unexpected H2 sections: {unknown}"


# Files with a filename-date prefix earlier than this are grandfathered —
# they carry the schema tag but predate the current field set. New
# emissions must conform.
COMMIT_SUMMARY_LOCKDOWN_DATE = "2026-07-01"


def test_live_commit_summaries_conform(fixtures_dir: Path) -> None:
    """Recent .gator/sessions/*commit*.md files must conform to the schema.

    Files older than COMMIT_SUMMARY_LOCKDOWN_DATE are grandfathered — they
    carry the tag but predate the current field set. New emissions must
    have the full required set.
    """
    repo_root = Path(__file__).resolve().parents[2]
    sessions_dir = repo_root / ".gator" / "sessions"
    if not sessions_dir.is_dir():
        pytest.skip("no live .gator/sessions/ directory in this checkout")

    checked = 0
    for path in sorted(sessions_dir.glob("*commit*.md")):
        # Filename prefix is YYYY-MM-DD-...; grandfather anything older.
        if path.name[:10] < COMMIT_SUMMARY_LOCKDOWN_DATE:
            continue
        fm, _ = _read_md(path)
        if fm.get("schema") != "gator-commit-summary-v1":
            continue
        checked += 1
        missing = COMMIT_REQUIRED_KEYS - fm.keys()
        assert not missing, f"{path.name}: missing required keys: {missing}"
        assert fm.keys() & COMMIT_ARCHITECT_KEYS, (
            f"{path.name}: must have architect or legacy pi"
        )

    if checked == 0:
        pytest.skip(
            f"no post-{COMMIT_SUMMARY_LOCKDOWN_DATE} commit-summary files "
            "declare gator-commit-summary-v1"
        )


# ── gator-session-summary-v1 ────────────────────────────────────────

def test_session_summary_frontmatter(fixtures_dir: Path) -> None:
    fm, _ = _read_md(fixtures_dir / "valid_session_summary.md")

    assert fm.get("schema") == "gator-session-summary-v1"
    missing = SESSION_REQUIRED_KEYS - fm.keys()
    assert not missing, f"missing required keys: {missing}"
    assert fm.keys() & SESSION_ARCHITECT_KEYS, (
        "must have either 'architect' or legacy 'pi' key"
    )


def test_session_summary_body_sections(fixtures_dir: Path) -> None:
    _, body = _read_md(fixtures_dir / "valid_session_summary.md")
    headers = {line for line in body.splitlines()
               if line.startswith("## ") and not line.startswith("### ")}
    missing = SESSION_REQUIRED_SECTIONS - headers
    assert not missing, f"missing required sections: {missing}"


def test_live_session_summaries_conform() -> None:
    """Any recent in-repo file carrying gator-session-summary-v1 must conform.

    Session summaries are canonically written to `~/.gator/session-transcripts/`
    (per-machine, off-repo), but files carrying the schema tag sometimes
    land in `.gator/sessions/` as well (legacy or copy-in). Any such file
    with a post-lockdown filename-date must conform to the schema. Pre-
    lockdown files are grandfathered.
    """
    repo_root = Path(__file__).resolve().parents[2]
    sessions_dir = repo_root / ".gator" / "sessions"
    if not sessions_dir.is_dir():
        pytest.skip("no live .gator/sessions/ directory in this checkout")

    checked = 0
    for path in sorted(sessions_dir.glob("*.md")):
        if path.name[:10] < SESSION_SUMMARY_LOCKDOWN_DATE:
            continue
        fm, body = _read_md(path)
        if fm.get("schema") != "gator-session-summary-v1":
            continue
        checked += 1
        missing = SESSION_REQUIRED_KEYS - fm.keys()
        assert not missing, f"{path.name}: missing required keys: {missing}"
        assert fm.keys() & SESSION_ARCHITECT_KEYS, (
            f"{path.name}: must have architect or legacy pi"
        )
        headers = {line for line in body.splitlines()
                   if line.startswith("## ") and not line.startswith("### ")}
        section_missing = SESSION_REQUIRED_SECTIONS - headers
        assert not section_missing, (
            f"{path.name}: missing required sections: {section_missing}"
        )

    if checked == 0:
        pytest.skip(
            f"no post-{SESSION_SUMMARY_LOCKDOWN_DATE} session-summary files "
            "present in .gator/sessions/ to validate"
        )


# ── schema spec files themselves ────────────────────────────────────

def test_commit_summary_spec_present(schemas_dir: Path) -> None:
    spec = (schemas_dir / "gator-commit-summary-v1.md").read_text(encoding="utf-8")
    assert "schema-id: gator-commit-summary-v1" in spec


def test_session_summary_spec_present(schemas_dir: Path) -> None:
    spec = (schemas_dir / "gator-session-summary-v1.md").read_text(encoding="utf-8")
    assert "schema-id: gator-session-summary-v1" in spec
