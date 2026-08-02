"""
gator_runtime.py — Runtime context resolver for Gator.

Answers the questions every Gator script needs:
  - What mode am I running in? (source-checkout, public-clone, installed-package)
  - Where are the scripts?
  - Where are the templates?
  - Where is the repo root I'm operating on?
  - Where is the command post, if any?

This module is the seam that makes pipx-installed Gator possible.
Scripts import this instead of doing SCRIPTS_DIR.parent.parent arithmetic.
"""

from pathlib import Path


# ---------------------------------------------------------------------------
# Runtime mode detection
# ---------------------------------------------------------------------------

def get_runtime_mode():
    """Detect how Gator is running.

    Returns one of:
      - 'source-checkout': running from the gator-command development repo
      - 'public-clone': running from a deployed gator clone (gator-engine/ layout)
      - 'installed-package': running from a pip/pipx installed package

    Detection order:
      1. If __file__ is inside a site-packages path → installed-package
      2. If the scripts dir has a sibling gator-engine/ → public-clone
      3. Otherwise → source-checkout
    """
    scripts_dir = Path(__file__).resolve().parent
    file_str = str(scripts_dir).lower()

    # Installed package: scripts live inside site-packages
    if "site-packages" in file_str or "dist-packages" in file_str:
        return "installed-package"

    # Public clone: gator-engine/ exists as a sibling to the scripts parent
    repo_root = scripts_dir.parent.parent
    if (repo_root / "gator-engine").is_dir():
        return "public-clone"

    return "source-checkout"


# ---------------------------------------------------------------------------
# Script and template resolution
# ---------------------------------------------------------------------------

def get_scripts_dir():
    """Return the directory containing Gator runtime scripts."""
    return Path(__file__).resolve().parent


def get_templates_dir():
    """Return the gator-starter templates directory, or None if not found.

    Resolution order:
      1. Source checkout: gator-command/templates/gator-starter/
      2. Public clone: gator-engine/templates/gator-starter/
      3. Installed package: package resources (future — returns None for now)
    """
    scripts_dir = Path(__file__).resolve().parent
    mode = get_runtime_mode()

    if mode == "source-checkout":
        candidate = scripts_dir.parent / "templates" / "gator-starter"
        if candidate.is_dir():
            return candidate

    elif mode == "public-clone":
        repo_root = scripts_dir.parent.parent
        candidate = repo_root / "gator-engine" / "templates" / "gator-starter"
        if candidate.is_dir():
            return candidate

    elif mode == "installed-package":
        # Future: use importlib.resources to resolve from package data
        # For now, fall through to None
        pass

    return None


# ---------------------------------------------------------------------------
# Repo root resolution
# ---------------------------------------------------------------------------

def get_repo_root(cwd=None):
    """Find the repo root by walking up from cwd to .git/.

    Returns Path or None. This answers "what repo am I operating on?"
    — not "where is Gator installed from."
    """
    candidate = Path(cwd).resolve() if cwd else Path.cwd().resolve()
    while candidate != candidate.parent:
        if (candidate / ".git").is_dir():
            return candidate
        candidate = candidate.parent
    return None


# ---------------------------------------------------------------------------
# Command post resolution
# ---------------------------------------------------------------------------

def get_command_post_root(cwd=None):
    """Find the command post root, if one exists.

    Resolution order:
      1. Source checkout mode: the repo root containing this script IS the command post
      2. Public clone mode: the repo root containing this script IS the command post
      3. Installed package mode: look for a command post via thin link in the target repo
      4. Fallback: use gator_core.find_command_post() if available

    Returns Path or None.
    """
    mode = get_runtime_mode()

    if mode in ("source-checkout", "public-clone"):
        # The repo this script lives in is the command post
        scripts_dir = Path(__file__).resolve().parent
        repo_root = scripts_dir.parent.parent
        if (repo_root / ".git").is_dir():
            return repo_root

    # For installed-package mode or fallback: try gator_core
    try:
        scripts_dir = get_scripts_dir()
        import sys
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        from gator_core import find_command_post
        return find_command_post()
    except (ImportError, Exception):
        pass

    return None
