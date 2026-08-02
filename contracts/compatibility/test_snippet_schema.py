"""Validate snippet fixtures against schemas/gator-session-snippet-v2.json.

Requires `jsonschema`. Skips cleanly if not installed so the rest of
the compatibility suite still runs on a bare interpreter.
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
def snippet_schema(schemas_dir: Path) -> dict:
    return _load(schemas_dir / "gator-session-snippet-v2.json")


@pytest.fixture(scope="module")
def validator(snippet_schema: dict):
    return jsonschema.Draft202012Validator(snippet_schema)


def test_schema_is_itself_valid(snippet_schema: dict) -> None:
    """The schema must be a legal Draft 2020-12 document."""
    jsonschema.Draft202012Validator.check_schema(snippet_schema)


def test_schema_identifies_itself_as_v2(snippet_schema: dict) -> None:
    """The schema's own version tag must match its filename."""
    assert snippet_schema["title"] == "gator-session-snippet-v2"
    assert snippet_schema["properties"]["schema"]["const"] == "gator-session-snippet-v2"


def test_valid_snippet_passes(validator, fixtures_dir: Path) -> None:
    payload = _load(fixtures_dir / "valid_snippet.json")
    errors = sorted(validator.iter_errors(payload), key=lambda e: e.path)
    assert errors == [], "\n".join(str(e) for e in errors)


def test_missing_required_fails(validator, fixtures_dir: Path) -> None:
    payload = _load(fixtures_dir / "invalid_snippet_missing_required.json")
    errors = list(validator.iter_errors(payload))
    assert errors, "expected at least one missing-required-field error"
    missing = {e.message.split(" ")[0].strip("'") for e in errors if e.validator == "required"}
    assert missing, "expected required-field errors specifically"


def test_wrong_schema_tag_fails(validator, fixtures_dir: Path) -> None:
    payload = _load(fixtures_dir / "invalid_snippet_wrong_schema.json")
    errors = list(validator.iter_errors(payload))
    assert any(e.validator == "const" for e in errors), (
        "wrong schema version tag should fail the const check"
    )


# Snippets with a filename-date prefix earlier than this are grandfathered —
# they carry the v2 tag but predate the current emitter invariants
# (e.g. transcript_ref started being scrubbed to null in early July 2026).
SNIPPET_LOCKDOWN_DATE = "2026-07-01"


def test_live_repo_snippets_conform(validator) -> None:
    """Every recent snippet in .gator/session-snippets/ must validate.

    Snippets older than SNIPPET_LOCKDOWN_DATE are grandfathered — they
    carry the v2 tag but predate current emitter invariants. New
    emissions must pass the schema clean.
    """
    repo_root = Path(__file__).resolve().parents[2]
    snippets_dir = repo_root / ".gator" / "session-snippets"
    if not snippets_dir.is_dir():
        pytest.skip("no live session-snippets/ directory in this checkout")

    checked = 0
    for path in sorted(snippets_dir.glob("*.json")):
        if path.name[:10] < SNIPPET_LOCKDOWN_DATE:
            continue
        checked += 1
        payload = _load(path)
        errors = sorted(validator.iter_errors(payload), key=lambda e: e.path)
        assert errors == [], f"{path.name}:\n" + "\n".join(str(e) for e in errors)

    if checked == 0:
        pytest.skip(
            f"no post-{SNIPPET_LOCKDOWN_DATE} snippets present to check"
        )
