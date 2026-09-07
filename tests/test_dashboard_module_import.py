"""
Python-3.9 dashboard-import pin (Plan A, v2.13.0, §8.7).

Runs in the ordinary `fast` matrix cell (no Playwright dep) so the
py3.9 CI cell is the authoritative dashboard-import pin. If
gator-dashboard.py adopts a py3.10+ syntax (walrus in comprehension
context, PEP 604 unions, match, ...), this pin fails there.
"""

import importlib.util
import sys
from pathlib import Path

import pytest


def test_dashboard_module_imports_on_current_interpreter():
    script = (Path(__file__).parent.parent
              / "src" / "gator_command" / "scripts"
              / "gator-dashboard.py")
    assert script.is_file(), f"gator-dashboard.py not found at {script}"

    spec = importlib.util.spec_from_file_location(
        "gator_dashboard_import_pin", str(script))
    module = importlib.util.module_from_spec(spec)
    sys.modules["gator_dashboard_import_pin"] = module
    try:
        spec.loader.exec_module(module)
    except (SyntaxError, TypeError, ImportError) as exc:
        pytest.fail(
            f"gator-dashboard.py failed to import on Python "
            f"{sys.version_info.major}.{sys.version_info.minor}: "
            f"{exc}")
    assert callable(getattr(module, "main", None))
    assert callable(getattr(module, "DashboardHandler", None))
