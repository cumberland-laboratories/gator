"""Shared helpers for gatorize modules.

Leaf module with no project dependencies. All other gatorize modules
import from here. Prevents circular imports.
"""

import shutil
import subprocess
from pathlib import Path


# ── marker constants ──────────────────────────────────────────────────────────

GATOR_MARKER = "# --- Gator Navigation Coding ---"
COMMAND_POST_MARKER = "# --- Gator Command Post ---"


# ── auto-yes state (Stage 2 of retire-gator-install plan) ─────────────────────

AUTO_YES = False


def set_auto_yes(value):
    """Set the module-level AUTO_YES sentinel. Called once by gatorize.py:main()
    after argparse. Do not mutate AUTO_YES from anywhere else.
    """
    global AUTO_YES
    AUTO_YES = bool(value)


def get_auto_yes():
    """Read the AUTO_YES sentinel. Cheap boolean accessor for callers that
    want a stable API rather than reading the module attribute directly.
    """
    return AUTO_YES


# ── helpers ───────────────────────────────────────────────────────────────────

def git(*args, cwd=None):
    """Run a git command. Returns (stdout, success)."""
    try:
        result = subprocess.run(
            ["git"] + list(args),
            capture_output=True, text=True, timeout=30,
            cwd=str(cwd) if cwd else None,
        )
        return result.stdout.strip(), result.returncode == 0
    except Exception as e:
        return str(e), False


def log_step(msg):
    """Print an indented step message."""
    print(f"  {msg}")


def prompt(question, options="", default="", auto_yes=None):
    """Interactive prompt. Returns user input.

    auto_yes: opt-in short-circuit for --yes mode. When AUTO_YES is True AND
    the caller explicitly passes auto_yes=<value>, returns that value without
    reading stdin. Otherwise reads stdin as before. auto_yes=None (default)
    is a no-op regardless of the AUTO_YES flag.
    """
    if AUTO_YES and auto_yes is not None:
        return auto_yes
    suffix = f" [{options}]: " if options else ": "
    try:
        return input(f"  {question}{suffix}").strip()
    except (EOFError, KeyboardInterrupt):
        return default


def confirm(question, default="Y", auto_yes=None):
    """Y/N confirmation.

    auto_yes: opt-in short-circuit for --yes mode. When AUTO_YES is True AND
    the caller explicitly passes auto_yes=True/False, returns that bool
    without reading stdin. auto_yes=None (default) preserves the interactive
    read-stdin behavior regardless of the AUTO_YES flag.
    """
    if AUTO_YES and auto_yes is not None:
        return bool(auto_yes)
    choice = prompt(question, "Y/n" if default == "Y" else "y/N")
    if not choice:
        return default == "Y"
    return choice.lower().startswith("y")


def copy_tree_overlay(src, dest):
    """Copy files from src to dest, preserving extras in dest.

    Skips __pycache__ and .pyc files.
    """
    dest.mkdir(parents=True, exist_ok=True)
    for item in sorted(src.iterdir()):
        if item.name in ("__pycache__",) or item.suffix == ".pyc":
            continue
        target = dest / item.name
        if item.is_dir():
            copy_tree_overlay(item, target)
        else:
            shutil.copy2(item, target)
