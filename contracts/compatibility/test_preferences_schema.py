"""Validate preferences fixtures against schemas/gator-preferences-v1.json.

The unified machine-local preferences file (~/.gator/preferences.json) is
the machine-scoped counterpart to the runtime pin. First user is the
Windows Python-launcher preference (v2.10.0); the schema also reserves a
`hooks:` section for the follow-on machine-scoped hook-mode plan.

Requires `jsonschema`. Skips cleanly if not installed so the rest of the
compatibility suite still runs on a bare interpreter.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip(
    "jsonschema",
    reason="pip install jsonschema to run the JSON-Schema-backed contract tests",
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def preferences_schema(schemas_dir: Path) -> dict:
    return _load(schemas_dir / "gator-preferences-v1.json")


@pytest.fixture(scope="module")
def validator(preferences_schema: dict):
    return jsonschema.Draft202012Validator(preferences_schema)


def test_schema_is_itself_valid(preferences_schema: dict) -> None:
    """The schema must be a legal Draft 2020-12 document."""
    jsonschema.Draft202012Validator.check_schema(preferences_schema)


def test_schema_identifies_itself_as_v1(preferences_schema: dict) -> None:
    """The schema's own version tag must match its filename."""
    assert preferences_schema["title"] == "gator-preferences-v1"
    assert preferences_schema["properties"]["schema"]["const"] == "gator-preferences-v1"


def test_schema_is_additive_friendly(preferences_schema: dict) -> None:
    """Contracts-layer invariant: additionalProperties must stay true at
    top level AND on every section so new fields (and future sections)
    land without a version bump."""
    assert preferences_schema.get("additionalProperties") is True
    assert preferences_schema["properties"]["python"].get("additionalProperties") is True
    assert preferences_schema["properties"]["hooks"].get("additionalProperties") is True


def test_hooks_section_is_reserved_stub(preferences_schema: dict) -> None:
    """The `hooks:` section is defined in v1 as a forward-compat stub for
    the hook-mode follow-on plan. It must exist so callers can rely on the
    file layout being stable; its shape is intentionally open (no required
    properties, additionalProperties true)."""
    hooks = preferences_schema["properties"]["hooks"]
    assert hooks["type"] == "object"
    assert hooks.get("additionalProperties") is True
    assert "required" not in hooks or hooks["required"] == []


def test_valid_preferences_pass(validator, fixtures_dir: Path) -> None:
    payload = _load(fixtures_dir / "valid_preferences.json")
    errors = sorted(validator.iter_errors(payload), key=lambda e: e.path)
    assert errors == [], "\n".join(str(e) for e in errors)


def test_wrong_schema_tag_fails(validator, fixtures_dir: Path) -> None:
    payload = _load(fixtures_dir / "valid_preferences.json")
    payload["schema"] = "gator-preferences-v999"
    errors = list(validator.iter_errors(payload))
    assert errors, "expected a const violation on the schema tag"


def test_missing_schema_fails(validator, fixtures_dir: Path) -> None:
    payload = _load(fixtures_dir / "valid_preferences.json")
    del payload["schema"]
    errors = list(validator.iter_errors(payload))
    assert errors, "expected a missing-required-field error for schema"
    assert any(e.validator == "required" for e in errors)


def test_python_section_optional(validator, fixtures_dir: Path) -> None:
    """A file with only `schema:` is legal — a machine may have preferences
    for other sections (e.g. future `hooks:`) but no launcher opinion, or
    may hold a stub file created by future tooling."""
    payload = {"schema": "gator-preferences-v1"}
    errors = list(validator.iter_errors(payload))
    assert errors == [], "\n".join(str(e) for e in errors)


def test_hooks_section_only_is_legal(validator) -> None:
    """Forward-compat: a file with only the reserved `hooks:` section and
    no `python:` section must validate — the follow-on plan writes here."""
    payload = {
        "schema": "gator-preferences-v1",
        "hooks": {"_": "reserved stub"},
    }
    errors = list(validator.iter_errors(payload))
    assert errors == [], "\n".join(str(e) for e in errors)


def test_unknown_top_level_section_tolerated(validator, fixtures_dir: Path) -> None:
    """additionalProperties: true — a future section (e.g. `enterprise:`)
    added by a newer CLI must not fail validation against v1."""
    payload = _load(fixtures_dir / "valid_preferences.json")
    payload["future_section"] = {"anything": "goes"}
    errors = list(validator.iter_errors(payload))
    assert errors == [], "\n".join(str(e) for e in errors)


def test_python_source_enum_enforced(validator, fixtures_dir: Path) -> None:
    """python.source must be one of the documented values when present."""
    payload = _load(fixtures_dir / "valid_preferences.json")
    payload["python"]["source"] = "not-a-real-source"
    errors = list(validator.iter_errors(payload))
    assert errors, "expected an enum violation on python.source"


def test_updated_at_pattern_enforced(validator, fixtures_dir: Path) -> None:
    """updated_at must be ISO-8601 with Z suffix, seconds precision."""
    payload = _load(fixtures_dir / "valid_preferences.json")
    payload["updated_at"] = "2026-08-29"
    errors = list(validator.iter_errors(payload))
    assert errors, "expected a pattern violation on updated_at"


def test_live_machine_preferences_conforms(validator) -> None:
    """If this machine carries a preferences file, it must satisfy v1.

    Skips cleanly when absent — the default state for most machines
    until an operator explicitly configures a preference.
    """
    prefs_file = Path.home() / ".gator" / "preferences.json"
    if not prefs_file.exists():
        pytest.skip("no ~/.gator/preferences.json on this machine (default state)")
    payload = _load(prefs_file)
    errors = sorted(validator.iter_errors(payload), key=lambda e: e.path)
    assert errors == [], "\n".join(str(e) for e in errors)
