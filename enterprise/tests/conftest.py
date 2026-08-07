"""Test configuration — environment setup and SQLite JSONB compatibility.

IMPORTANT: The DATABASE_URL env var must be set before any app module is imported,
because app.config.get_settings() validates it at import time. We set a dummy
value here so tests can collect without a real PostgreSQL instance.

sys.path setup: enterprise/ is not a Python package (no __init__.py at that
level) and the root pytest.ini scopes collection to the base wheel's tests/
+ contracts/, so pytest's default sys.path does not include enterprise/.
Running enterprise tests via `pytest enterprise/tests/` from repo root
would then fail at collection with `ModuleNotFoundError: No module named
'app'` — the four tests that import `from app.<X> import Y` (api_contract,
error_envelope, rate_limit, views) all hit this. Fix: put enterprise/
first on sys.path so `app` and `gator_enterprise_cli` both resolve
regardless of invocation cwd. Individual test files can drop their own
one-off sys.path inserts once this conftest is picked up.
"""

import os
import sys
import warnings
from pathlib import Path

# Make enterprise/'s children (`app`, `enterprise-cli/gator_enterprise_cli`)
# importable regardless of pytest invocation directory.
_ENTERPRISE_ROOT = Path(__file__).resolve().parent.parent
if str(_ENTERPRISE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ENTERPRISE_ROOT))
_ENTERPRISE_CLI_ROOT = _ENTERPRISE_ROOT / "enterprise-cli"
if str(_ENTERPRISE_CLI_ROOT) not in sys.path:
    sys.path.insert(0, str(_ENTERPRISE_CLI_ROOT))

# Silence StarletteDeprecationWarning about httpx2 (starlette 1.4+ prefers
# the httpx2 package over httpx and warns when it falls back to httpx).
# `httpx2` is a real successor package but adding it just to silence a
# testclient warning would introduce two new runtime deps (httpx2 +
# httpcore2) without any functional benefit — testclient works fine with
# httpx. When we do a real dep bump / migration in the future, either the
# dep swap happens or the filter goes away naturally; until then, the
# filter keeps test output clean without churn.
#
# The filter needs BOTH a `warnings.filterwarnings` call (for import-time
# warnings raised before pytest's own warning-capture takes over) AND the
# pytest_configure hook to register it with pytest's capture system.
# Neither alone suffices: pytest re-enables warnings via its
# catch_warnings context and shows them in the summary regardless of the
# Python-level filter.
warnings.filterwarnings(
    "ignore",
    message="Using `httpx` with `starlette.testclient` is deprecated",
    category=UserWarning,
)


def pytest_configure(config):
    config.addinivalue_line(
        "filterwarnings",
        "ignore:Using `httpx` with `starlette.testclient` is deprecated",
    )

# Set dummy DATABASE_URL before any app imports trigger get_settings()
if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "postgresql://test:test@localhost/test"

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles


# Teach SQLite how to compile JSONB columns — render as JSON (stored as TEXT)
@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"
