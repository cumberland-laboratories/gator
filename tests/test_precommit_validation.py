"""
Tests for gator-pre-commit.py hard-rule validation, specifically the
change-type enum check added 2026-08-02 after the monorepo cutover
surfaced a "bugfix" value that read plausibly but wasn't in the
gator-session-snippet-v2 schema enum.

The template lives at src/gator_command/templates/gator-starter/scripts/;
that's the version shipped to fleet repos and used for validation.
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


class TestChangeTypeValidation:
    """change-type frontmatter must be in the schema-legal enum."""

    def test_valid_change_types_pass(self, tmp_path):
        """Every enum value in VALID_CHANGE_TYPES must pass validation."""
        gator_dir = tmp_path / ".gator"
        gator_dir.mkdir()
        for value in pre_commit.VALID_CHANGE_TYPES:
            frontmatter = {"message": "test", "change-type": value}
            failures = pre_commit.validate_hard_rules(
                staged_files=[], frontmatter=frontmatter, body="",
                parse_error=None, gator_dir=gator_dir,
            )
            invalid = [f for f in failures if f[0] == "invalid-change-type"]
            assert not invalid, (
                f"Valid change-type {value!r} unexpectedly flagged as "
                f"invalid: {invalid}"
            )

    def test_omitted_change_type_passes(self, tmp_path):
        """`None` (field omitted entirely) is allowed — trailer assembly
        infers a value later."""
        gator_dir = tmp_path / ".gator"
        gator_dir.mkdir()
        frontmatter = {"message": "test"}  # no change-type key
        failures = pre_commit.validate_hard_rules(
            staged_files=[], frontmatter=frontmatter, body="",
            parse_error=None, gator_dir=gator_dir,
        )
        invalid = [f for f in failures if f[0] == "invalid-change-type"]
        assert not invalid

    @pytest.mark.parametrize("bad_value", [
        "bugfix",         # the actual value that motivated this validation
        "chore",          # common conventional-commits value; not in enum
        "style",          # ditto
        "hotfix",         # plausible but not in enum
        "FEATURE",        # capitalization differs from enum
        " fix ",          # whitespace
        "fix,refactor",   # multi-value not allowed
    ])
    def test_invalid_change_types_fail_with_helpful_message(
        self, tmp_path, bad_value,
    ):
        """Invalid values fail with a clear error naming the valid set."""
        gator_dir = tmp_path / ".gator"
        gator_dir.mkdir()
        frontmatter = {"message": "test", "change-type": bad_value}
        failures = pre_commit.validate_hard_rules(
            staged_files=[], frontmatter=frontmatter, body="",
            parse_error=None, gator_dir=gator_dir,
        )
        invalid = [f for f in failures if f[0] == "invalid-change-type"]
        assert invalid, (
            f"Invalid change-type {bad_value!r} was NOT flagged; would "
            f"pass through and fail schema validation on the emitted "
            f"session snippet."
        )
        # Error message should include valid values so the agent can fix
        msg = invalid[0][1]
        assert "fix" in msg
        assert "feature" in msg
        assert bad_value in msg or repr(bad_value) in msg

    def test_bugfix_specifically_suggests_fix(self, tmp_path):
        """The most common typo — 'bugfix' — should have a hint pointing
        at the correct enum value 'fix'."""
        gator_dir = tmp_path / ".gator"
        gator_dir.mkdir()
        frontmatter = {"message": "test", "change-type": "bugfix"}
        failures = pre_commit.validate_hard_rules(
            staged_files=[], frontmatter=frontmatter, body="",
            parse_error=None, gator_dir=gator_dir,
        )
        invalid = [f for f in failures if f[0] == "invalid-change-type"]
        assert invalid
        msg = invalid[0][1]
        assert "'bugfix' -> 'fix'" in msg or "bugfix -> fix" in msg


class TestSchemaEnumSyncObligation:
    """The pre-commit's VALID_CHANGE_TYPES set MUST match the enum in
    contracts/schemas/gator-session-snippet-v2.json.

    If either changes, this test fails — a byte-consistency check that
    prevents the exact drift class this whole validation exists to catch.
    """

    def test_enum_matches_schema(self):
        import json
        schema_path = (
            Path(__file__).parent.parent
            / "contracts" / "schemas" / "gator-session-snippet-v2.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema_enum = frozenset(schema["properties"]["change_type"]["enum"])
        assert schema_enum == pre_commit.VALID_CHANGE_TYPES, (
            f"Pre-commit enum drifted from schema.\n"
            f"  Schema: {sorted(schema_enum)}\n"
            f"  Hook:   {sorted(pre_commit.VALID_CHANGE_TYPES)}\n"
            f"Update both to match (see the sync-obligation comment above "
            f"VALID_CHANGE_TYPES in gator-pre-commit.py)."
        )
