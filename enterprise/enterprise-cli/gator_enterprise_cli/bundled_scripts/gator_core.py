#!/usr/bin/env python3
"""
gator_core.py — Shared infrastructure for Gator Command scripts.

Centralizes utilities that were previously duplicated across 6+ scripts:
version resolution, command-post discovery, registry parsing, path
normalization, git helpers, and stdout setup.

Usage (automatic — scripts/ is on sys.path when any sibling runs):
    from gator_core import get_version, find_command_post, parse_registry, git

Not a standalone script — imported by other gator-* scripts.

@reads: filesystem, git tags, registry.md, .gator/command-post.md
@writes: nothing (pure library)
"""

import io
import json
import re
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------

def _find_repo_root(start=None):
    """Walk up from start looking for .git or pyproject.toml."""
    d = start or Path(__file__).resolve().parent
    for _ in range(6):
        if (d / ".git").is_dir() or (d / "pyproject.toml").is_file():
            return d
        d = d.parent
    return start or Path(__file__).resolve().parent


def _read_pyproject_version(repo_root):
    """Read version from pyproject.toml if it exists."""
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        for line in pyproject.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("version") and "=" in line:
                ver = line.split("=", 1)[1].strip().strip('"').strip("'")
                if ver:
                    return ver
    except OSError:
        pass
    return None


def _read_version_file(start=None):
    """Read VERSION file by walking up from start (or this script's dir)."""
    d = start or Path(__file__).resolve().parent
    for _ in range(5):
        vf = d / "VERSION"
        if vf.is_file():
            text = vf.read_text(encoding="utf-8", errors="replace").strip()
            if text:
                return text if not text.startswith("v") else text[1:]
        d = d.parent
    return None


def get_version(cwd=None):
    """Canonical version resolver for gator-command.

    Resolution order:
        1. pyproject.toml version field (canonical for source checkouts)
        2. importlib.metadata (canonical for installed packages)
        3. git describe --tags --always (tag or tag+offset)
        4. VERSION file (for deployed repos without full git history)
        5. git rev-parse --short HEAD (bare hash as "dev-g<hash>")
        6. "dev"

    Returns a version string without "v" prefix (e.g. "1.7.1", "dev").
    """
    repo_root = _find_repo_root(cwd)

    # 1. pyproject.toml — canonical for source checkouts
    ver = _read_pyproject_version(repo_root)
    if ver:
        return ver

    # 2. importlib.metadata — canonical for installed packages
    try:
        from importlib.metadata import version as _pkg_version
        return _pkg_version("gator-command")
    except Exception:
        pass

    # 3. git describe
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            capture_output=True, text=True, cwd=repo_root, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            version = result.stdout.strip()
            if version.startswith("v"):
                return version[1:]  # strip v prefix
            return version
    except (OSError, subprocess.TimeoutExpired):
        pass

    # 4. VERSION file
    from_file = _read_version_file(repo_root)
    if from_file:
        return from_file

    # 5. git rev-parse
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=repo_root, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return f"dev-g{result.stdout.strip()}"
    except (OSError, subprocess.TimeoutExpired):
        pass

    return "dev"


def get_version_short(cwd=None):
    """Get just the version number, without commit count or hash.

    Returns "1.7.1" whether on the tag or after it.
    Falls back to "dev" if no version found.
    """
    version = get_version(cwd)
    # Strip git describe suffixes like "-14-g8ea4749"
    if "-" in version and not version.startswith("dev"):
        return version.split("-")[0]
    return version


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def normalize_path(raw_path):
    """Normalize MSYS2/Git Bash paths (/c/Users/...) to native Windows.

    Converts /c/Users/... to C:/Users/... for cross-platform compatibility.
    No-op on paths that don't match the MSYS2 pattern.
    """
    if re.match(r'^/[a-zA-Z]/', raw_path):
        raw_path = raw_path[1].upper() + ":" + raw_path[2:]
    return raw_path


def find_command_post(start_path=None):
    """Find the gator-command repo root.

    Walks up from start_path looking for a directory containing
    gator-command/mission.md. Used by command-post scripts (fleet-report,
    drift, audit, init-command-post).
    """
    path = Path(start_path) if start_path else Path.cwd()
    path = path.resolve()

    if (path / "gator-command" / "mission.md").exists():
        return path
    if (path / "mission.md").exists() and (path / "active-threads").is_dir():
        return path.parent
    for parent in path.parents:
        if (parent / "gator-command" / "mission.md").exists():
            return parent
    return None


def find_gator_root(start_path=None):
    """Walk up from start_path looking for .gator/ directory.

    Used by per-repo scripts (init, update) to find the governed repo root.
    """
    path = Path(start_path) if start_path else Path.cwd()
    path = path.resolve()
    if (path / ".gator").is_dir():
        return path
    for parent in path.parents:
        if (parent / ".gator").is_dir():
            return parent
    return None


def resolve_thin_link(gator_dir):
    """Read the command-post thin link and resolve the path.

    Used by per-repo scripts (update) to find the command post from
    a governed repo's .gator/command-post.md.
    """
    cp_file = gator_dir / "command-post.md"
    if not cp_file.exists():
        return None

    text = cp_file.read_text(encoding="utf-8", errors="replace")

    # Try command-post-absolute first (most reliable on same machine)
    for line in text.splitlines():
        if line.startswith("command-post-absolute:"):
            raw = line.split(":", 1)[1].strip().split("#")[0].strip()
            if raw:
                resolved = Path(normalize_path(raw))
                if resolved.is_dir():
                    return resolved

    # Fall back to command-post (relative or absolute)
    for line in text.splitlines():
        if line.startswith("command-post:") and not line.startswith("command-post-absolute:"):
            raw = line.split(":", 1)[1].strip()
            if raw:
                # Try as relative from repo root
                resolved = (gator_dir.parent / raw).resolve()
                if resolved.is_dir():
                    return resolved
                # Try as absolute
                resolved = Path(normalize_path(raw))
                if resolved.is_dir():
                    return resolved

    return None


# ---------------------------------------------------------------------------
# Product source and repo topology
# ---------------------------------------------------------------------------

def read_product_source(gator_dir):
    """Read .gator/product-source.json. Returns dict or None if missing/corrupt."""
    ps_file = Path(gator_dir) / "product-source.json"
    if not ps_file.exists():
        return None
    try:
        data = json.loads(ps_file.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def resolve_template_source(gator_dir, source_override=None):
    """Resolve the template source directory for product updates.

    Resolution order:
    1. Explicit --source override
    2. .gator/product-source.json (gator_root + template_dir)
    3. Thin link -> command post -> templates (legacy fallback)
    4. None (caller should fail with clear message)

    Returns (template_path, gator_root) or (None, None).
    """
    # 1. Explicit override
    if source_override:
        root = Path(source_override).resolve()
        for tpl_rel in ("gator-engine/templates/gator-starter",
                        "gator-command/templates/gator-starter",
                        "templates/gator-starter"):
            tpl = root / tpl_rel
            if tpl.is_dir():
                return tpl, root
        return None, None

    gator_dir = Path(gator_dir)

    # 2. product-source.json
    ps = read_product_source(gator_dir)
    if ps:
        root = Path(ps.get("gator_root", ""))
        tpl_rel = ps.get("template_dir", "")
        if root.is_dir() and tpl_rel:
            tpl = root / tpl_rel
            if tpl.is_dir():
                return tpl, root

    # 3. Thin link fallback
    cp = resolve_thin_link(gator_dir)
    if cp:
        for tpl_rel in ("gator-command/templates/gator-starter",
                        "gator-engine/templates/gator-starter",
                        "templates/gator-starter"):
            tpl = Path(cp) / tpl_rel
            if tpl.is_dir():
                return tpl, Path(cp)

    return None, None


def get_repo_topology(gator_dir):
    """Derive the governance topology of a repo.

    Returns one of:
      "policy-synced"  — active thin link, repo receives org policy
      "standalone"     — no thin link, no policy artifacts, template updates only
      "inconsistent"   — partial artifacts remain, needs repair
    """
    gator_dir = Path(gator_dir)
    cp_file = gator_dir / "command-post.md"
    gov_source = gator_dir / "governance-source.json"
    policy_link = gator_dir / "policy-link.json"
    policy_cache = gator_dir / "policy-cache"

    has_thin_link = cp_file.exists()
    has_policy_content = policy_link.exists() or (
        policy_cache.is_dir() and any(policy_cache.iterdir())
    )
    has_gov_source = gov_source.exists()

    # Thin link present and resolvable → policy-synced
    if has_thin_link:
        cp = resolve_thin_link(gator_dir)
        if cp:
            return "policy-synced"
        # Thin link exists but points nowhere
        return "inconsistent"

    # No thin link — check for orphaned policy artifacts
    if has_policy_content or has_gov_source:
        return "inconsistent"

    return "standalone"


def clear_policy_artifacts(gator_dir):
    """Remove all policy-source artifacts to make a repo standalone.

    Clears: command-post.md, governance-source.json, policy-link.json, policy-cache/.
    """
    import shutil
    gator_dir = Path(gator_dir)

    for name in ("command-post.md", "governance-source.json", "policy-link.json"):
        f = gator_dir / name
        if f.exists():
            f.unlink()

    cache = gator_dir / "policy-cache"
    if cache.is_dir():
        shutil.rmtree(cache)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def parse_registry(command_post):
    """Parse registry.md into a list of repo entries.

    Each entry is a dict with: name, path, remote, registered, status.
    """
    registry_file = command_post / "gator-command" / "registry.md"
    if not registry_file.exists():
        return []

    repos = []
    text = registry_file.read_text(encoding="utf-8", errors="replace")
    in_table = False

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("| Repo"):
            in_table = True
            continue
        if stripped.startswith("|---"):
            continue
        if in_table and stripped.startswith("|"):
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            if len(cells) >= 5:
                repos.append({
                    "name": cells[0],
                    "path": cells[1],
                    "remote": cells[2],
                    "registered": cells[3],
                    "status": cells[4],
                })

    return repos


# ---------------------------------------------------------------------------
# Machine-local dashboard registry
# ---------------------------------------------------------------------------

DASHBOARD_REGISTRY = Path.home() / ".gator" / "dashboard-repos.json"


def read_dashboard_registry():
    """Read the machine-local dashboard repo registry.

    Returns list of repo dicts [{name, path, added_at, source}, ...].
    Returns empty list if the file doesn't exist or is invalid.
    """
    if not DASHBOARD_REGISTRY.exists():
        return []
    try:
        data = json.loads(DASHBOARD_REGISTRY.read_text(encoding="utf-8"))
        return data.get("repos", [])
    except (json.JSONDecodeError, OSError):
        return []


def write_dashboard_registry(repos):
    """Write the machine-local dashboard repo registry."""
    DASHBOARD_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema": "gator-dashboard-registry-v1",
        "repos": repos,
    }
    DASHBOARD_REGISTRY.write_text(
        json.dumps(data, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def ensure_dashboard_registry_entry(repo_path, source="gator-init"):
    """Ensure a repo is present in the machine-local dashboard registry.

    Returns dict with:
      status: "added" | "already_registered" | "unavailable" | "error"
      detail: human-readable string
    """
    try:
        repo_path = Path(repo_path).resolve()
        if not repo_path.is_dir():
            return {"status": "unavailable", "detail": "repo path not found"}

        repos = read_dashboard_registry()
        path_str = str(repo_path)

        for r in repos:
            try:
                if str(Path(r["path"]).resolve()) == path_str:
                    return {"status": "already_registered", "detail": "already registered"}
            except (KeyError, OSError):
                continue

        from datetime import datetime, timezone
        repos.append({
            "name": repo_path.name,
            "path": path_str,
            "added_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": source,
        })
        write_dashboard_registry(repos)
        return {"status": "added", "detail": "added"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def add_dashboard_repo(repo_path):
    """Add a repo to the local dashboard registry. Idempotent by path."""
    result = ensure_dashboard_registry_entry(repo_path, source="gatorize")
    return result["status"] == "added"


def remove_dashboard_repo(name_or_path):
    """Remove a repo from the local dashboard registry by name or path."""
    repos = read_dashboard_registry()
    filtered = [r for r in repos
                if r.get("name") != name_or_path
                and str(Path(r.get("path", "")).resolve()) != str(Path(name_or_path).resolve())]
    if len(filtered) < len(repos):
        write_dashboard_registry(filtered)
        return True
    return False


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def git(*args, cwd=None):
    """Run a git command, return (stdout, success).

    Returns a tuple so callers can distinguish 'git returned nothing'
    from 'git failed'. Silent emptiness is the wrong failure mode for
    a product whose claim is trustworthy governance telemetry.
    """
    try:
        result = subprocess.run(
            ["git"] + list(args),
            capture_output=True, text=True, cwd=cwd, timeout=10,
        )
        return result.stdout.strip(), result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return "", False


# ---------------------------------------------------------------------------
# Stdout setup
# ---------------------------------------------------------------------------

def ensure_utf8_stdout():
    """Ensure stdout uses UTF-8 encoding (needed on Windows)."""
    if sys.stdout.encoding != "utf-8":
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )


# ---------------------------------------------------------------------------
# Script import helper
# ---------------------------------------------------------------------------

def import_sibling(name):
    """Import a sibling script by filename (handles hyphens).

    Example: import_sibling("gator-fleet-report") imports gator-fleet-report.py
    from the same directory as the calling script.

    Returns the module on success, None if the file doesn't exist.
    Raises ImportError with diagnostic context if the file exists but
    fails to load — callers should catch this if they want resilience.
    """
    import importlib.util

    scripts_dir = Path(__file__).resolve().parent
    path = scripts_dir / f"{name}.py"
    if not path.exists():
        return None

    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), path
    )
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        raise ImportError(
            f"Failed to load {path.name}: {type(e).__name__}: {e}"
        ) from e
    return mod


# ---------------------------------------------------------------------------
# Charter surface resolution
# ---------------------------------------------------------------------------

def resolve_charter_surface(repo_root=None):
    """Return the authoritative charter surface for this repo.

    Two modes:
    - source-command-post: the gator-command development repo.
      Charters at gator-command/charters/, cross-cutting is
      scripts-cross-cutting.md.
    - governed-repo: all other repos (fleet repos, deployed command posts).
      Charters at .gator/charters/, cross-cutting is cross-cutting.md.

    Returns dict with:
      mode: "source-command-post" | "governed-repo"
      charter_dir: Path to authoritative charter directory
      cross_cutting: filename of the cross-cutting charter (or None)
      index_file: Path to INDEX.md (or None if absent)
    """
    if repo_root is None:
        repo_root = Path.cwd()
    else:
        repo_root = Path(repo_root)

    # Detect source-command-post mode: gator-command/charters/ exists AND
    # scripts exist (at src/gator_command/scripts/ or legacy gator-command/scripts/).
    cp_charters = repo_root / "gator-command" / "charters"
    cp_scripts = repo_root / "src" / "gator_command" / "scripts"
    if not cp_scripts.is_dir():
        cp_scripts = repo_root / "gator-command" / "scripts"
    if cp_charters.is_dir() and cp_scripts.is_dir():
        cross_cutting = None
        for f in cp_charters.iterdir():
            if "cross-cutting" in f.name and f.suffix == ".md":
                cross_cutting = f.name
                break
        index_file = cp_charters / "INDEX.md"
        return {
            "mode": "source-command-post",
            "charter_dir": cp_charters,
            "cross_cutting": cross_cutting,
            "index_file": index_file if index_file.is_file() else None,
        }

    # Default: governed-repo mode
    charter_dir = repo_root / ".gator" / "charters"
    cross_cutting = None
    if charter_dir.is_dir():
        for f in charter_dir.iterdir():
            if "cross-cutting" in f.name and f.suffix == ".md":
                cross_cutting = f.name
                break
    index_file = charter_dir / "INDEX.md"
    return {
        "mode": "governed-repo",
        "charter_dir": charter_dir,
        "cross_cutting": cross_cutting,
        "index_file": index_file if index_file.is_file() else None,
    }


# ---------------------------------------------------------------------------
# Branding
# ---------------------------------------------------------------------------

# Template generation — single source of truth for Python scripts.
# gatorize.sh reads this value at runtime via grep.
# Gen 0: pre-gatorize.sh installs (no command-post.md, no .gator-version)
# Gen 1: first gatorize.sh installs (has command-post.md, no .gator-version)
# Gen 2: current (has .gator-version, overlay-not-replace upgrade logic)
CURRENT_GENERATION = 2

GATOR_MARK_LINES = [
    r"  ....    .  .....  ...  ....  ",
    r" / ___|  / \|_   _|/ _ \|  _ \    ....  ",
    r"| |  _  / _ \ | | | | | | |_) | ./( o )\_______",
    r"| |_/ \/ /_\ \| | | |_| |  _ <       _/vVvVvVvV",
    r" \____/m/   \m\_|  \___/|m| \m\  \__.---------",
]
