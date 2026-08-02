"""Validate the .gator/enterprise.json marker schema + presence-detection.

Two guarantees:
1. The JSON Schema itself is valid, and known fixtures pass/fail as
   documented.
2. Presence-detection behavior: an empty repo without the marker MUST
   look Enterprise-inactive; a repo with `enabled: true` MUST look
   Enterprise-active. Any base-Gator code path this suite exercises
   must not touch the marker.
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
def marker_schema(schemas_dir: Path) -> dict:
    return _load(schemas_dir / "enterprise-config.json")


@pytest.fixture(scope="module")
def validator(marker_schema: dict):
    return jsonschema.Draft202012Validator(marker_schema)


def test_marker_schema_is_valid(marker_schema: dict) -> None:
    jsonschema.Draft202012Validator.check_schema(marker_schema)


def test_marker_schema_self_identifies(marker_schema: dict) -> None:
    assert marker_schema["title"] == "gator-enterprise-config-v1"


def test_valid_enabled_marker(validator, fixtures_dir: Path) -> None:
    payload = _load(fixtures_dir / "valid_enterprise_config.json")
    errors = list(validator.iter_errors(payload))
    assert errors == [], "\n".join(str(e) for e in errors)


def test_valid_disabled_marker(validator, fixtures_dir: Path) -> None:
    """enabled=false with no api_url is legal — it's the temporary-disable case."""
    payload = _load(fixtures_dir / "valid_enterprise_config_disabled.json")
    errors = list(validator.iter_errors(payload))
    assert errors == [], "\n".join(str(e) for e in errors)


def test_enabled_without_api_url_fails(validator, fixtures_dir: Path) -> None:
    """enabled=true requires api_url + org_id via the allOf/if branch."""
    payload = _load(fixtures_dir / "invalid_enterprise_config_missing_api_url.json")
    errors = list(validator.iter_errors(payload))
    assert errors, "expected validation failure when enabled=true without api_url"


# ── Presence-detection behavior ─────────────────────────────────────

def _is_marker_present(gator_dir: Path) -> bool:
    return (gator_dir / "enterprise.json").exists()


def _is_enterprise_active(gator_dir: Path) -> bool:
    """Reference implementation of the enterprise-active check.

    This is the canonical logic that Phase 4 Enterprise gating code
    MUST implement — production impl lives at
    `src/gator_command/scripts/gator_core.py::is_enterprise_active`
    and must stay byte-behaviorally identical to this reference.
    Failing this test signals a contract violation.
    """
    marker = gator_dir / "enterprise.json"
    if not marker.exists():
        return False
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False  # fail closed on malformed JSON
    # Fail-closed on wrong-shape JSON root — a valid-but-non-object marker
    # (e.g. `[]`, `42`, `"foo"`) would crash `.get()` with AttributeError.
    # Codex Phase 4b review flagged that both this reference impl and the
    # production impl had this hole.
    if not isinstance(payload, dict):
        return False
    return payload.get("enabled") is True


def test_bare_gator_dir_is_not_enterprise_active(tmp_path: Path) -> None:
    gator_dir = tmp_path / ".gator"
    gator_dir.mkdir()
    assert not _is_marker_present(gator_dir)
    assert not _is_enterprise_active(gator_dir)


def test_marker_disabled_is_not_enterprise_active(tmp_path: Path, fixtures_dir: Path) -> None:
    gator_dir = tmp_path / ".gator"
    gator_dir.mkdir()
    (gator_dir / "enterprise.json").write_text(
        (fixtures_dir / "valid_enterprise_config_disabled.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    assert _is_marker_present(gator_dir)
    assert not _is_enterprise_active(gator_dir)


def test_marker_enabled_is_enterprise_active(tmp_path: Path, fixtures_dir: Path) -> None:
    gator_dir = tmp_path / ".gator"
    gator_dir.mkdir()
    (gator_dir / "enterprise.json").write_text(
        (fixtures_dir / "valid_enterprise_config.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    assert _is_marker_present(gator_dir)
    assert _is_enterprise_active(gator_dir)


def test_malformed_marker_fails_closed(tmp_path: Path) -> None:
    gator_dir = tmp_path / ".gator"
    gator_dir.mkdir()
    (gator_dir / "enterprise.json").write_text("{ not json", encoding="utf-8")
    assert _is_marker_present(gator_dir)
    assert not _is_enterprise_active(gator_dir)


@pytest.mark.parametrize("non_object_json", ["[]", '["enabled"]', "42", "true", '"foo"', "null"])
def test_non_object_marker_fails_closed(tmp_path: Path, non_object_json: str) -> None:
    """Valid JSON that isn't a JSON object MUST fail closed.

    Codex Phase 4b review flagged that both the reference impl and the
    production impl called `.get("enabled")` unconditionally after
    `json.loads()`, crashing with AttributeError on `[]`/`42`/`"foo"`.
    Fail-closed extends to shape, not just to parseability.
    """
    gator_dir = tmp_path / ".gator"
    gator_dir.mkdir()
    (gator_dir / "enterprise.json").write_text(non_object_json, encoding="utf-8")
    assert _is_marker_present(gator_dir)
    assert not _is_enterprise_active(gator_dir)


def test_reference_doc_names_the_canonical_signal(reference_dir: Path) -> None:
    """The presence-detection reference doc must name .gator/enterprise.json."""
    text = (reference_dir / "presence-detection.md").read_text(encoding="utf-8")
    assert ".gator/enterprise.json" in text
    assert "enabled" in text.lower()
