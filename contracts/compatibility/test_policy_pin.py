"""Validate policy-pin fixtures against schemas/gator-policy-pin-v1.json.

The policy pin (.gator/policy-pin.json) is the committed record of which
org policy versions were in force in a governed repo — the policy
channel's Git proof surface (runtime-split Phase 5b). Written by
`gator-enterprise policies pull`; queried fleet-wide via Enterprise's
machine_policy_states (Migration 012).

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
    return _load(schemas_dir / "gator-policy-pin-v1.json")


@pytest.fixture(scope="module")
def validator(pin_schema: dict):
    return jsonschema.Draft202012Validator(pin_schema)


def test_schema_is_itself_valid(pin_schema: dict) -> None:
    jsonschema.Draft202012Validator.check_schema(pin_schema)


def test_schema_identifies_itself_as_v1(pin_schema: dict) -> None:
    assert pin_schema["title"] == "gator-policy-pin-v1"
    assert pin_schema["properties"]["schema"]["const"] == "gator-policy-pin-v1"


def test_schema_is_additive_friendly(pin_schema: dict) -> None:
    assert pin_schema.get("additionalProperties") is True


def test_valid_pin_passes(validator, fixtures_dir: Path) -> None:
    payload = _load(fixtures_dir / "valid_policy_pin.json")
    errors = sorted(validator.iter_errors(payload), key=lambda e: e.path)
    assert errors == [], "\n".join(str(e) for e in errors)


def test_empty_policies_array_is_legal(validator, fixtures_dir: Path) -> None:
    payload = _load(fixtures_dir / "valid_policy_pin.json")
    payload["policies"] = []
    assert list(validator.iter_errors(payload)) == []


def test_bad_hash_format_fails(validator, fixtures_dir: Path) -> None:
    payload = _load(fixtures_dir / "invalid_policy_pin_bad_hash.json")
    errors = list(validator.iter_errors(payload))
    assert errors, "expected a pattern violation on content_hash"


def test_missing_policies_fails(validator, fixtures_dir: Path) -> None:
    payload = _load(fixtures_dir / "valid_policy_pin.json")
    del payload["policies"]
    errors = list(validator.iter_errors(payload))
    assert any(e.validator == "required" for e in errors)


def test_live_repo_pin_conforms(validator) -> None:
    """If this repo carries a policy pin, it must satisfy the contract.
    New artifact class (first emission 2026-08-21) — no grandfathering."""
    repo_root = Path(__file__).resolve().parents[2]
    pin_file = repo_root / ".gator" / "policy-pin.json"
    if not pin_file.exists():
        pytest.skip("no policy pin in this repo yet")
    payload = _load(pin_file)
    errors = sorted(validator.iter_errors(payload), key=lambda e: e.path)
    assert errors == [], "\n".join(str(e) for e in errors)
