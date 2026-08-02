"""Test configuration — environment setup and SQLite JSONB compatibility.

IMPORTANT: The DATABASE_URL env var must be set before any app module is imported,
because app.config.get_settings() validates it at import time. We set a dummy
value here so tests can collect without a real PostgreSQL instance.
"""

import os

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
