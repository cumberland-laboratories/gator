"""Gator Command — Git-native governance for AI-assisted engineering."""

from pathlib import Path


def _resolve_version():
    """Resolve package version via canonical resolver or fallback."""
    # Try gator_core canonical resolver (covers pyproject.toml, metadata, git, VERSION)
    try:
        import sys
        scripts_dir = str(Path(__file__).resolve().parent / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from gator_core import get_version
        return get_version()
    except (ImportError, Exception):
        pass

    # Fallback: importlib.metadata for installed packages
    try:
        from importlib.metadata import version
        return version("gator-command")
    except Exception:
        pass

    return "unknown"


__version__ = _resolve_version()
