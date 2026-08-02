"""Shared constants and utilities for dashboard modules.

Centralizes path resolution, script runners, and git helpers so that
extracted dashboard modules (updates, snapshot, data) can import them
without circular dependencies back to gator-dashboard.py.
"""

import json
import subprocess
import sys
from pathlib import Path


# ── paths ─────────────────────────────────────────────────────────────────────

SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # scripts/ (one up from dashboard/)
DASHBOARD_DIR = Path(__file__).resolve().parent       # dashboard/
COMMAND_POST_ROOT = SCRIPTS_DIR.parent.parent.parent  # repo root


# ── script runners ────────────────────────────────────────────────────────────

def run_json(script_name, *extra_args, timeout=90):
    """Run a sibling script with --json. Returns parsed dict or {"error": "..."}."""
    script_path = SCRIPTS_DIR / f"{script_name}.py"
    if not script_path.exists():
        return {"error": f"{script_name}.py not found at {script_path}"}

    cmd = [sys.executable, str(script_path), "--json"] + list(extra_args)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        stdout = result.stdout.strip()
        if not stdout:
            stderr = result.stderr.strip()
            return {"error": stderr or f"{script_name} produced no output (exit {result.returncode})"}
        return json.loads(stdout)
    except subprocess.TimeoutExpired:
        return {"error": f"{script_name} timed out after {timeout}s"}
    except json.JSONDecodeError as e:
        return {"error": f"{script_name} produced invalid JSON: {e}"}
    except Exception as e:
        return {"error": str(e)}


def run_text(script_name, *extra_args, timeout=60):
    """Run a sibling script without --json. Returns (stdout, stderr, exit_code)."""
    script_path = SCRIPTS_DIR / f"{script_name}.py"
    if not script_path.exists():
        return "", f"{script_name}.py not found", 1
    cmd = [sys.executable, str(script_path)] + list(extra_args)
    try:
        result = subprocess.run(
            cmd, capture_output=True, encoding="utf-8", errors="replace",
            timeout=timeout,
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", f"timed out after {timeout}s", 1
    except Exception as e:
        return "", str(e), 1


# ── git helper ────────────────────────────────────────────────────────────────

def git_run(*args, cwd=None):
    """Run a git command, return (stdout_or_stderr, ok).

    Uses utf-8 encoding to avoid Windows cp1252 crashes on non-ASCII content.
    Defaults to COMMAND_POST_ROOT as cwd.
    """
    try:
        result = subprocess.run(
            ["git"] + list(args),
            capture_output=True, encoding="utf-8", errors="replace", timeout=30,
            cwd=cwd or str(COMMAND_POST_ROOT),
        )
        if result.returncode == 0:
            return result.stdout.strip(), True
        return (result.stderr.strip() or result.stdout.strip()), False
    except Exception as e:
        return str(e), False
