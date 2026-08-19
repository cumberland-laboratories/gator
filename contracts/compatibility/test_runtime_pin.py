"""Validate runtime-pin fixtures against schemas/gator-runtime-pin-v1.json.

The runtime pin (.gator/runtime-pin.json) is the committed record of which
shipped runtime is in force in a governed repo — the repo-side half of the
runtime split (roadmap item 19, Variant A). Emitted by gator-update and
gatorize (Phase 1); read by the runtime resolver (Phase 2+).

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
def pin_schema(schemas_dir: Path) -> dict:
    return _load(schemas_dir / "gator-runtime-pin-v1.json")


@pytest.fixture(scope="module")
def validator(pin_schema: dict):
    return jsonschema.Draft202012Validator(pin_schema)


def test_schema_is_itself_valid(pin_schema: dict) -> None:
    """The schema must be a legal Draft 2020-12 document."""
    jsonschema.Draft202012Validator.check_schema(pin_schema)


def test_schema_identifies_itself_as_v1(pin_schema: dict) -> None:
    """The schema's own version tag must match its filename."""
    assert pin_schema["title"] == "gator-runtime-pin-v1"
    assert pin_schema["properties"]["schema"]["const"] == "gator-runtime-pin-v1"


def test_schema_is_additive_friendly(pin_schema: dict) -> None:
    """Contracts-layer invariant: additionalProperties must stay true so
    new fields land without a version bump."""
    assert pin_schema.get("additionalProperties") is True


def test_valid_pin_passes(validator, fixtures_dir: Path) -> None:
    payload = _load(fixtures_dir / "valid_runtime_pin.json")
    errors = sorted(validator.iter_errors(payload), key=lambda e: e.path)
    assert errors == [], "\n".join(str(e) for e in errors)


def test_missing_manifest_fails(validator, fixtures_dir: Path) -> None:
    payload = _load(fixtures_dir / "invalid_runtime_pin_missing_manifest.json")
    errors = list(validator.iter_errors(payload))
    assert errors, "expected a missing-required-field error for manifest"
    assert any(e.validator == "required" for e in errors)


def test_wrong_schema_tag_fails(validator, fixtures_dir: Path) -> None:
    payload = _load(fixtures_dir / "valid_runtime_pin.json")
    payload["schema"] = "gator-runtime-pin-v999"
    errors = list(validator.iter_errors(payload))
    assert errors, "expected a const violation on the schema tag"


def test_malformed_manifest_digest_fails(validator, fixtures_dir: Path) -> None:
    payload = _load(fixtures_dir / "valid_runtime_pin.json")
    payload["manifest"]["gator-pre-commit.py"] = "md5:abc123"
    errors = list(validator.iter_errors(payload))
    assert errors, "expected a pattern violation on the digest value"


def test_live_repo_pin_conforms(validator) -> None:
    """If this repo carries a runtime pin, it must satisfy the contract.

    No filename-date grandfathering needed: the pin is a new artifact
    class (first emission 2026-08-18) — every instance postdates the
    contract.
    """
    repo_root = Path(__file__).resolve().parents[2]
    pin_file = repo_root / ".gator" / "runtime-pin.json"
    if not pin_file.exists():
        pytest.skip("no runtime pin in this repo yet (pre-Phase-1 state)")
    payload = _load(pin_file)
    errors = sorted(validator.iter_errors(payload), key=lambda e: e.path)
    assert errors == [], "\n".join(str(e) for e in errors)
