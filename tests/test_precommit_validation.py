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


class TestSignificanceValidation:
    """significance frontmatter must be in the schema-legal enum. Added
    2026-08-10 (v2.6.0) after the smoke test surfaced 5 pre-existing
    snippets with `medium` (not in enum, typo for `notable`) and 8 with
    `architectural` (semantically legit; enum extended to include it)."""

    def test_valid_significance_values_pass(self, tmp_path):
        """Every enum value in VALID_SIGNIFICANCE must pass validation."""
        gator_dir = tmp_path / ".gator"
        gator_dir.mkdir()
        for value in pre_commit.VALID_SIGNIFICANCE:
            frontmatter = {"message": "test", "significance": value}
            failures = pre_commit.validate_hard_rules(
                staged_files=[], frontmatter=frontmatter, body="",
                parse_error=None, gator_dir=gator_dir,
            )
            invalid = [f for f in failures if f[0] == "invalid-significance"]
            assert not invalid, (
                f"Valid significance {value!r} unexpectedly flagged as "
                f"invalid: {invalid}"
            )

    def test_omitted_significance_passes(self, tmp_path):
        """`None` (field omitted entirely) is allowed — trailer assembly
        infers a value later."""
        gator_dir = tmp_path / ".gator"
        gator_dir.mkdir()
        frontmatter = {"message": "test"}  # no significance key
        failures = pre_commit.validate_hard_rules(
            staged_files=[], frontmatter=frontmatter, body="",
            parse_error=None, gator_dir=gator_dir,
        )
        invalid = [f for f in failures if f[0] == "invalid-significance"]
        assert not invalid

    @pytest.mark.parametrize("bad_value", [
        "medium",         # the actual value that motivated this validation
        "major",          # plausible but not in enum
        "trivial",        # plausible but not in enum
        "HIGH",           # capitalization differs from enum
        " notable ",      # whitespace
        "notable,high",   # multi-value not allowed
    ])
    def test_invalid_significance_fails_with_helpful_message(
        self, tmp_path, bad_value,
    ):
        """Invalid values fail with a clear error naming the valid set."""
        gator_dir = tmp_path / ".gator"
        gator_dir.mkdir()
        frontmatter = {"message": "test", "significance": bad_value}
        failures = pre_commit.validate_hard_rules(
            staged_files=[], frontmatter=frontmatter, body="",
            parse_error=None, gator_dir=gator_dir,
        )
        invalid = [f for f in failures if f[0] == "invalid-significance"]
        assert invalid, (
            f"Invalid significance {bad_value!r} was NOT flagged; would "
            f"pass through and fail schema validation on the emitted "
            f"session snippet."
        )
        msg = invalid[0][1]
        assert "notable" in msg
        assert "high" in msg
        assert bad_value in msg or repr(bad_value) in msg

    def test_medium_specifically_suggests_notable(self, tmp_path):
        """The most common typo — 'medium' — should have a hint pointing
        at the correct enum value 'notable'."""
        gator_dir = tmp_path / ".gator"
        gator_dir.mkdir()
        frontmatter = {"message": "test", "significance": "medium"}
        failures = pre_commit.validate_hard_rules(
            staged_files=[], frontmatter=frontmatter, body="",
            parse_error=None, gator_dir=gator_dir,
        )
        invalid = [f for f in failures if f[0] == "invalid-significance"]
        assert invalid
        msg = invalid[0][1]
        assert "'medium' -> 'notable'" in msg or "medium -> notable" in msg


class TestSchemaEnumSyncObligation:
    """The pre-commit's VALID_CHANGE_TYPES + VALID_SIGNIFICANCE sets MUST
    match their enums in contracts/schemas/gator-session-snippet-v2.json.

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
            f"Pre-commit change-type enum drifted from schema.\n"
            f"  Schema: {sorted(schema_enum)}\n"
            f"  Hook:   {sorted(pre_commit.VALID_CHANGE_TYPES)}\n"
            f"Update both to match (see the sync-obligation comment above "
            f"VALID_CHANGE_TYPES in gator-pre-commit.py)."
        )

    def test_significance_enum_matches_schema(self):
        """Added 2026-08-10 (v2.6.0) alongside VALID_SIGNIFICANCE."""
        import json
        schema_path = (
            Path(__file__).parent.parent
            / "contracts" / "schemas" / "gator-session-snippet-v2.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema_enum = frozenset(schema["properties"]["significance"]["enum"])
        assert schema_enum == pre_commit.VALID_SIGNIFICANCE, (
            f"Pre-commit significance enum drifted from schema.\n"
            f"  Schema: {sorted(schema_enum)}\n"
            f"  Hook:   {sorted(pre_commit.VALID_SIGNIFICANCE)}\n"
            f"Update both to match (see the sync-obligation comment above "
            f"VALID_SIGNIFICANCE in gator-pre-commit.py)."
        )


class TestMachineIdTrailer:
    """assemble_trailers emits `Gator-Machine-Id: <id>` sourced from
    ~/.gator/machine-id (2026-08-08 transcripts-first MVP Phase 6).

    The trailer is emitted only when the file exists and contains an
    `id:` line — silent no-op keeps standalone base-gator use on a
    machine that never activated Enterprise working without a hook
    failure.

    Enterprise-side consumer: `enterprise/app/routes/ingest.py`'s
    commit ingest reads Gator-Machine-Id from the trailer bag to
    populate `commits.machine_id`, which the linkage algorithm's
    `strong_machine_repo_time` basis (Phase 3) matches against
    transcript_sessions.machine_id.
    """

    def _base_frontmatter(self):
        # Minimal, spec-legal frontmatter so assemble_trailers proceeds
        # past its own required-fields short-circuits.
        return {
            "message": "test",
            "change-type": "feature",
            "significance": "routine",
            "decision-tags": [],
            "agent": "test-agent",
            "architect": "test-architect",
        }

    def test_trailer_emitted_when_machine_id_file_present(
        self, tmp_path, monkeypatch,
    ):
        # Mock $HOME so _read_machine_id reads our fixture, not the
        # developer's real ~/.gator/machine-id.
        fake_home = tmp_path / "home"
        (fake_home / ".gator").mkdir(parents=True)
        (fake_home / ".gator" / "machine-id").write_text(
            "id: 11111111-2222-3333-4444-555555555555\n"
            "hostname: test-host\n"
            "label: test-machine\n"
            "created: 2026-08-08T00:00:00Z\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)

        gator_dir = tmp_path / "repo" / ".gator"
        gator_dir.mkdir(parents=True)

        trailers = pre_commit.assemble_trailers(
            frontmatter=self._base_frontmatter(),
            body="",
            gator_dir=gator_dir,
            staged_files=[],
        )
        machine_id_trailers = [
            t for t in trailers if t.startswith("Gator-Machine-Id:")
        ]
        assert len(machine_id_trailers) == 1
        assert machine_id_trailers[0] == (
            "Gator-Machine-Id: 11111111-2222-3333-4444-555555555555"
        )

    def test_trailer_omitted_when_machine_id_file_missing(
        self, tmp_path, monkeypatch,
    ):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        # Deliberately do NOT create ~/.gator/machine-id
        monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)

        gator_dir = tmp_path / "repo" / ".gator"
        gator_dir.mkdir(parents=True)

        trailers = pre_commit.assemble_trailers(
            frontmatter=self._base_frontmatter(),
            body="",
            gator_dir=gator_dir,
            staged_files=[],
        )
        assert not any(t.startswith("Gator-Machine-Id:") for t in trailers)

    def test_trailer_omitted_when_id_line_missing(
        self, tmp_path, monkeypatch,
    ):
        # File exists but has no `id:` line — silent no-op, not a crash.
        fake_home = tmp_path / "home"
        (fake_home / ".gator").mkdir(parents=True)
        (fake_home / ".gator" / "machine-id").write_text(
            "hostname: test-host\nlabel: test-machine\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)

        gator_dir = tmp_path / "repo" / ".gator"
        gator_dir.mkdir(parents=True)

        trailers = pre_commit.assemble_trailers(
            frontmatter=self._base_frontmatter(),
            body="",
            gator_dir=gator_dir,
            staged_files=[],
        )
        assert not any(t.startswith("Gator-Machine-Id:") for t in trailers)
