"""Fixtures for the contracts pytest suite.

Plain helper functions live in _helpers.py — putting them in conftest.py
collides with tests/conftest.py under multi-dir collection because
`from conftest import ...` cannot disambiguate between two conftest
modules on sys.path. Fixtures are safe here because pytest resolves
them by scope, not by import path.

Run: `python -m pytest contracts/compatibility -v`
"""
from __future__ import annotations

from pathlib import Path

import pytest

CONTRACTS_DIR = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = CONTRACTS_DIR / "schemas"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
REFERENCE_DIR = CONTRACTS_DIR / "reference"


@pytest.fixture(scope="session")
def schemas_dir() -> Path:
    return SCHEMAS_DIR


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture(scope="session")
def reference_dir() -> Path:
    return REFERENCE_DIR
