"""
Dashboard UI harness fixtures (Plan A, v2.13.0, §4).

Fixtures only — implementation helpers live in `_harness.py` so
this file does not shadow `tests/conftest.py` (which other test
files import from as `from conftest import load_script`). Both
files must be able to be resolved as `conftest` on sys.path with
pytest's import machinery; keeping this one narrow (only pytest
fixtures) avoids the shadow.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

from ._harness import build_dashboard_fleet
# B1 Slice 2 (v2.13.0) — deterministic module-scope import
# registers `seed_content_fixtures` + `seed_history_commits` on
# the harness BEFORE any fixture builds the fleet.
from . import content_transport_seed  # noqa: F401
# Plan C Slice 3 (v2.13.0) — module-scope import registers
# `seed_sidebar_fixtures` on the harness BEFORE any fixture
# builds the fleet.
from . import test_responsive_shell_seed  # noqa: F401
# Read-only syntax-highlight increment (2026-09-12) — module-scope
# import registers `seed_syntax_fixtures` on the harness BEFORE
# any fixture builds the fleet.
from . import test_syntax_highlight_seed  # noqa: F401


# ── §4.1: in-process dashboard module loader ──────────────────────


@pytest.fixture(scope="session")
def dashboard_module():
    """Load gator-dashboard.py as an importable module under a safe
    alias. Session-scoped: the module loads once per session; its
    state is not per-test. Tests that need to reset module state
    should monkeypatch, not reimport.
    """
    import gator_command  # requires `pip install -e .`
    script = (Path(gator_command.__file__).parent
              / "scripts" / "gator-dashboard.py")
    assert script.is_file(), f"gator-dashboard.py not found at {script}"

    spec = importlib.util.spec_from_file_location(
        "gator_dashboard_test", str(script))
    module = importlib.util.module_from_spec(spec)
    sys.modules["gator_dashboard_test"] = module
    spec.loader.exec_module(module)
    return module


# ── §4.2 / §4.3: fleet fixtures ───────────────────────────────────


@pytest.fixture(scope="session")
def dashboard_fleet(tmp_path_factory):
    yield from build_dashboard_fleet(
        tmp_path_factory, extra_registry_size=15, debug=True)


@pytest.fixture(scope="function")
def dashboard_fleet_mutable(tmp_path_factory):
    yield from build_dashboard_fleet(
        tmp_path_factory, extra_registry_size=0, debug=True)


@pytest.fixture(scope="session")
def dashboard_fleet_debug_off(tmp_path_factory):
    yield from build_dashboard_fleet(
        tmp_path_factory, extra_registry_size=0, debug=False)


# ── §4.4: page fixtures ───────────────────────────────────────────


@pytest.fixture
def gator_page_readonly(page, dashboard_fleet):
    page.goto(dashboard_fleet["url"])
    return page


@pytest.fixture
def gator_page_mutable(page, dashboard_fleet_mutable):
    page.goto(dashboard_fleet_mutable["url"])
    return page


# ── §4.5: deterministic teardown probe ───────────────────────────


@pytest.fixture
def dashboard_fleet_lifecycle_probe(tmp_path_factory):
    """Drives the SAME `build_dashboard_fleet` every other fixture
    consumes, exposing internal handles via a plain-dict observer.
    In teardown, drives the generator to completion (running the
    real success-path finally block) and then asserts sequentially
    — no pytest finalizer LIFO involved.
    """
    observer = {}
    gen = build_dashboard_fleet(
        tmp_path_factory,
        extra_registry_size=0,
        debug=False,
        lifecycle_observer=observer,
    )
    fleet = next(gen)
    try:
        yield fleet, observer
    finally:
        try:
            next(gen)
        except StopIteration:
            pass
        assert observer["stdout_thread"].is_alive() is False, (
            "stdout reader thread still alive after fixture teardown")
        assert observer["stderr_thread"].is_alive() is False, (
            "stderr reader thread still alive after fixture teardown")
        assert observer["stdout"].closed is True, (
            "proc.stdout not closed after fixture teardown")
        assert observer["stderr"].closed is True, (
            "proc.stderr not closed after fixture teardown")
