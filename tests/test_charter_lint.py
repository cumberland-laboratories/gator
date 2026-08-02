"""
Tests for gator-charter-lint.py — Charter Schema v1 validator.

Tests the parser and validator using synthetic charter files.
"""

from pathlib import Path

import pytest

from conftest import load_script

lint = load_script("gator-charter-lint")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_CHARTER = """\
# Charter: Test Module

**Covers**: `src/test.py`

## Owns

Test module logic.

## Does Not Own

- Everything else

---

### parse_config(path)
File: src/test.py
Reads config file and returns dict.
@reads: config.json
← main()
→ validate_config()
! Config keys are case-sensitive — do not normalize.

### run_task(name)
File: src/test.py
Runs a named task from the registry.
← cli_handler()

---

## Before Changing This Module

- Config format is frozen. Do not add new keys without PI approval.

## Connections

→ [Other Charter](other.md) — shared config format
"""

SKELETON_CHARTER = """\
# Charter: Skeleton

**Covers**: `src/skeleton.py`

## Owns

Placeholder — to be filled in.

## Does Not Own

- TBD

---
"""

VALID_INDEX = """\
# Charter Index

**Always read first:** [Cross-Cutting](cross-cutting.md)

| If you're changing... | Read these charters |
|---|---|
| `src/main.py` | [Main](main.md) |
| `src/utils.py` | [Utils](utils.md) |
"""

VALID_CROSS_CUTTING = """\
# Charter: Cross-Cutting Patterns

**Read this first.** Patterns spanning multiple modules.

## Owns

Multi-module invariants.

## Does Not Own

Module-specific logic.

---

## TRIPWIRE: Config Format Sync

Config format in main.py and utils.py must stay synchronized.

## Pattern: Error Handling Convention

All errors go through the central handler.
"""


def _write(tmp_path, name, content):
    """Write a charter file and return its path."""
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------

class TestParseCharter:
    def test_parses_valid_charter(self, tmp_path):
        """Extracts all structural elements from a well-formed charter."""
        p = _write(tmp_path, "test.md", VALID_CHARTER)
        doc = lint.parse_charter(p)

        assert doc.title == "# Charter: Test Module"
        assert doc.has_covers
        assert "Owns" in doc.sections
        assert "Does Not Own" in doc.sections
        assert len(doc.separators) == 2
        assert len(doc.functions) == 2

    def test_parses_function_entries(self, tmp_path):
        """Extracts function entry details."""
        p = _write(tmp_path, "test.md", VALID_CHARTER)
        doc = lint.parse_charter(p)

        func = doc.functions[0]
        assert func.name == "parse_config(path)"
        assert func.has_file_line
        assert func.has_description
        assert func.has_annotations  # has ←, →, !, @reads

    def test_parses_index(self, tmp_path):
        """Detects INDEX.md structure."""
        p = _write(tmp_path, "INDEX.md", VALID_INDEX)
        doc = lint.parse_charter(p)

        assert doc.is_index
        assert doc.has_dispatch_table

    def test_parses_cross_cutting(self, tmp_path):
        """Detects cross-cutting charter patterns."""
        p = _write(tmp_path, "cross-cutting.md", VALID_CROSS_CUTTING)
        doc = lint.parse_charter(p)

        assert doc.is_cross_cutting

    def test_parses_skeleton(self, tmp_path):
        """Handles skeleton charters with no function entries."""
        p = _write(tmp_path, "skeleton.md", SKELETON_CHARTER)
        doc = lint.parse_charter(p)

        assert doc.title == "# Charter: Skeleton"
        assert len(doc.functions) == 0


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

class TestValidateCharter:
    def test_valid_charter_passes(self, tmp_path):
        """A well-formed charter produces no errors."""
        p = _write(tmp_path, "test.md", VALID_CHARTER)
        doc = lint.parse_charter(p)
        findings = lint.validate_charter(doc)

        errors = [f for f in findings if f.severity == "error"]
        assert len(errors) == 0

    def test_skeleton_charter_passes(self, tmp_path):
        """A skeleton charter with no functions is valid."""
        p = _write(tmp_path, "skeleton.md", SKELETON_CHARTER)
        doc = lint.parse_charter(p)
        findings = lint.validate_charter(doc)

        errors = [f for f in findings if f.severity == "error"]
        assert len(errors) == 0

    def test_missing_title_errors(self, tmp_path):
        """Missing '# Charter:' title is an error."""
        content = VALID_CHARTER.replace("# Charter: Test Module", "# Test Module")
        p = _write(tmp_path, "test.md", content)
        doc = lint.parse_charter(p)
        findings = lint.validate_charter(doc)

        checks = [f.check for f in findings if f.severity == "error"]
        assert "title-format" in checks

    def test_missing_covers_errors(self, tmp_path):
        """Missing **Covers**: line is an error."""
        content = VALID_CHARTER.replace("**Covers**: `src/test.py`", "")
        p = _write(tmp_path, "test.md", content)
        doc = lint.parse_charter(p)
        findings = lint.validate_charter(doc)

        checks = [f.check for f in findings if f.severity == "error"]
        assert "covers-present" in checks

    def test_cross_cutting_no_covers_ok(self, tmp_path):
        """Cross-cutting charters don't need **Covers**:."""
        p = _write(tmp_path, "cross-cutting.md", VALID_CROSS_CUTTING)
        doc = lint.parse_charter(p)
        findings = lint.validate_charter(doc)

        checks = [f.check for f in findings if f.severity == "error"]
        assert "covers-present" not in checks

    def test_missing_owns_errors(self, tmp_path):
        """Missing ## Owns is an error."""
        content = VALID_CHARTER.replace("## Owns", "## Ownership")
        p = _write(tmp_path, "test.md", content)
        doc = lint.parse_charter(p)
        findings = lint.validate_charter(doc)

        checks = [f.check for f in findings if f.severity == "error"]
        assert "owns-section" in checks

    def test_missing_does_not_own_errors(self, tmp_path):
        """Missing ## Does Not Own is an error."""
        content = VALID_CHARTER.replace("## Does Not Own", "## Exclusions")
        p = _write(tmp_path, "test.md", content)
        doc = lint.parse_charter(p)
        findings = lint.validate_charter(doc)

        checks = [f.check for f in findings if f.severity == "error"]
        assert "does-not-own-section" in checks

    def test_missing_separator_errors(self, tmp_path):
        """Function entries without --- separator is an error."""
        content = VALID_CHARTER.replace("---\n\n### parse_config", "### parse_config")
        # Remove all separators
        content = content.replace("---", "")
        p = _write(tmp_path, "test.md", content)
        doc = lint.parse_charter(p)
        findings = lint.validate_charter(doc)

        checks = [f.check for f in findings if f.severity == "error"]
        assert "separator-before-functions" in checks

    def test_function_without_file_line_warns(self, tmp_path):
        """Function entry missing File: line is a warning."""
        content = """\
# Charter: Test

**Covers**: `src/test.py`

## Owns

Stuff.

## Does Not Own

- Other stuff

---

### my_function()
Does something useful.
← caller()

---

## Before Changing This Module

Check first.

## Connections

→ [Other](other.md)
"""
        p = _write(tmp_path, "test.md", content)
        doc = lint.parse_charter(p)
        findings = lint.validate_charter(doc)

        warns = [f for f in findings if f.check == "file-line"]
        assert len(warns) == 1
        assert warns[0].severity == "warn"

    def test_before_changing_warn_when_functions_present(self, tmp_path):
        """Missing 'Before Changing' section warns when functions exist."""
        content = VALID_CHARTER.replace(
            "## Before Changing This Module\n\n- Config format is frozen. Do not add new keys without PI approval.\n\n",
            ""
        )
        p = _write(tmp_path, "test.md", content)
        doc = lint.parse_charter(p)
        findings = lint.validate_charter(doc)

        checks = [f.check for f in findings if f.severity == "warn"]
        assert "before-changing-section" in checks

    def test_no_warn_when_no_functions(self, tmp_path):
        """Skeleton charter without functions gets no 'Before Changing' warning."""
        p = _write(tmp_path, "skeleton.md", SKELETON_CHARTER)
        doc = lint.parse_charter(p)
        findings = lint.validate_charter(doc)

        checks = [f.check for f in findings]
        assert "before-changing-section" not in checks
        assert "connections-section" not in checks


class TestValidateIndex:
    def test_valid_index(self, tmp_path):
        """Well-formed INDEX.md passes."""
        p = _write(tmp_path, "INDEX.md", VALID_INDEX)
        doc = lint.parse_charter(p)
        findings = lint.validate_charter(doc)

        assert len([f for f in findings if f.severity == "error"]) == 0

    def test_missing_dispatch_table_warns(self, tmp_path):
        """INDEX.md without dispatch table warns."""
        content = "# Charter Index\n\nJust some text, no table.\n"
        p = _write(tmp_path, "INDEX.md", content)
        doc = lint.parse_charter(p)
        findings = lint.validate_charter(doc)

        checks = [f.check for f in findings if f.severity == "warn"]
        assert "dispatch-table" in checks
