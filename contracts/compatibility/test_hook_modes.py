"""Verify that the hook-mode enum in the shipped code matches the contract.

The reference doc names the canonical values. This test grep-verifies
the value set in the code that actually reads and validates them.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

CANONICAL_MODES = {"strict", "warn", "off"}


def test_reference_doc_declares_canonical_enum(reference_dir: Path) -> None:
    text = (reference_dir / "hook-mode-vocabulary.md").read_text(encoding="utf-8")
    for mode in CANONICAL_MODES:
        assert mode in text, f"hook-mode-vocabulary.md must mention '{mode}'"


def test_gator_enforce_uses_canonical_enum() -> None:
    """gator-enforce.py must define VALID_LEVELS = the three canonical modes."""
    path = (REPO_ROOT / "src" / "gator_command" / "templates"
            / "gator-starter" / "scripts" / "gator-enforce.py")
    if not path.exists():
        # accept the deployed .gator/ path as a fallback
        path = REPO_ROOT / ".gator" / ".includes" / "scripts" / "gator-enforce.py"
    assert path.exists(), f"gator-enforce.py not found at expected paths"

    source = path.read_text(encoding="utf-8")
    match = re.search(r"VALID_LEVELS\s*=\s*\{([^}]+)\}", source)
    assert match, "VALID_LEVELS constant not found in gator-enforce.py"

    declared = {v.strip().strip('"').strip("'")
                for v in match.group(1).split(",") if v.strip()}
    assert declared == CANONICAL_MODES, (
        f"gator-enforce.py declares {declared}, contract requires {CANONICAL_MODES}"
    )


def test_pre_commit_hook_validates_against_canonical_enum() -> None:
    """The pre-commit reader must not accept values outside the canonical set."""
    candidates = [
        REPO_ROOT / "src" / "gator_command" / "templates" / "gator-starter"
        / "scripts" / "gator-pre-commit.py",
        REPO_ROOT / ".gator" / ".includes" / "scripts" / "gator-pre-commit.py",
    ]
    path = next((p for p in candidates if p.exists()), None)
    assert path is not None, "gator-pre-commit.py not found"

    source = path.read_text(encoding="utf-8")
    # The reader must reference every canonical mode in its validation logic.
    for mode in CANONICAL_MODES:
        assert f'"{mode}"' in source or f"'{mode}'" in source, (
            f"gator-pre-commit.py does not reference '{mode}'"
        )


def test_default_config_stub_uses_strict() -> None:
    """gatorize's config stub must default to enforcement_level: strict."""
    candidates = [
        REPO_ROOT / "src" / "gator_command" / "scripts" / "gatorize.py",
        REPO_ROOT / ".gator" / ".includes" / "scripts" / "gatorize.py",
    ]
    path = next((p for p in candidates if p.exists()), None)
    assert path is not None, "gatorize.py not found"

    source = path.read_text(encoding="utf-8")
    assert '"enforcement_level": "strict"' in source, (
        "gatorize.py config stub must default enforcement_level to 'strict'"
    )
