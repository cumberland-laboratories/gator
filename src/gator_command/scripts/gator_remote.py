#!/usr/bin/env python3
"""
gator_remote.py — Remote fleet scanning via bare clone cache.

Enables fleet reporting without local checkouts. Uses bare git clones
cached in ~/.gator/fleet-cache/ to read governance state from remote
refs using `git show` and `git log`.

Resolution order (in gator-fleet-report.py):
1. Try local path → full scan (existing behavior)
2. If local inaccessible AND remote exists → thin-fetch scan (this module)
3. If neither accessible → report as unreachable

Not a standalone script — imported by gator-fleet-report.py and gator-audit.py.

@reads: ~/.gator/fleet-cache/ (bare clones), remote git refs
@writes: ~/.gator/fleet-cache/ (creates/updates bare clones)
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

from gator_core import git


CACHE_DIR = Path.home() / ".gator" / "fleet-cache"


def _cache_key(repo_name: str, remote_url: str) -> str:
    """Collision-proof cache directory name.

    Incorporates a short hash of the remote URL so two different remotes
    with the same registry name (e.g., 'api' in two orgs) get separate
    bare clones instead of silently sharing/overwriting.
    """
    url_hash = hashlib.sha256(remote_url.encode()).hexdigest()[:8]
    return f"{repo_name}-{url_hash}.git"


def _git_bare(*args, git_dir: Path, timeout: int = 30):
    """Run a git command against a bare repo. Returns (stdout, success)."""
    try:
        result = subprocess.run(
            ["git", f"--git-dir={git_dir}"] + list(args),
            capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout.strip(), result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return "", False


def ensure_cache(repo_name: str, remote_url: str) -> Path | None:
    """Clone bare if not cached, fetch if cached. Returns cache path or None.

    Cache key incorporates a hash of the remote URL to prevent collisions
    when two different remotes share the same registry name.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / _cache_key(repo_name, remote_url)

    # Migration: if old-style name exists (no hash), rename it
    legacy_path = CACHE_DIR / f"{repo_name}.git"
    if legacy_path.is_dir() and not cache_path.is_dir():
        legacy_path.rename(cache_path)

    if cache_path.is_dir():
        # Verify the cached remote matches what we expect
        current_url, _ = _git_bare(
            "remote", "get-url", "origin", git_dir=cache_path
        )
        if current_url and current_url != remote_url:
            _git_bare(
                "remote", "set-url", "origin", remote_url,
                git_dir=cache_path,
            )
        # Update existing cache
        _, ok = _git_bare("fetch", "origin", "--prune", git_dir=cache_path)
        return cache_path if ok else None
    else:
        # Initial bare clone
        try:
            result = subprocess.run(
                ["git", "clone", "--bare", remote_url, str(cache_path)],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                return cache_path
        except (OSError, subprocess.TimeoutExpired):
            pass
        return None


def git_show(cache_path: Path, ref: str, filepath: str) -> str | None:
    """Read a file from a ref without checkout. Returns content or None."""
    content, ok = _git_bare("show", f"{ref}:{filepath}", git_dir=cache_path)
    if ok:
        return content
    return None


def git_ls_tree(cache_path: Path, ref: str, dirpath: str) -> list[str]:
    """List file names in a directory from a ref."""
    output, ok = _git_bare(
        "ls-tree", "--name-only", ref, dirpath + "/",
        git_dir=cache_path,
    )
    if not ok or not output:
        return []
    # ls-tree returns full paths relative to repo root
    return [line.split("/")[-1] for line in output.splitlines() if line.strip()]


def git_log_trailers(cache_path: Path, ref: str, count: int = 10) -> dict:
    """Extract Gator-* trailers from the most recent commit on ref."""
    raw, ok = _git_bare(
        "log", f"-{count}", "--format=%(trailers)", ref,
        git_dir=cache_path,
    )
    if not ok or not raw:
        return {}

    # Return trailers from the most recent commit that has them
    trailers = {}
    for line in raw.splitlines():
        if line.startswith("Gator-"):
            key, _, value = line.partition(":")
            trailers[key.strip()] = value.strip()
        elif trailers:
            # We found trailers, stop at the first empty block boundary
            break

    return trailers


def git_log_last_commit(cache_path: Path, ref: str) -> dict | None:
    """Get last commit info from a ref."""
    log_line, ok = _git_bare(
        "log", "-1", "--format=%h|%s|%cr|%ci", ref,
        git_dir=cache_path,
    )
    if not ok or not log_line:
        return None

    parts = log_line.split("|", 3)
    if len(parts) < 4:
        return None

    return {
        "hash": parts[0],
        "message": parts[1],
        "age": parts[2],
        "date": parts[3],
    }


def git_commit_count(cache_path: Path, ref: str, days: int = 30) -> int:
    """Count commits in the last N days on a ref."""
    count_str, ok = _git_bare(
        "rev-list", "--count", f"--since={days} days ago", ref,
        git_dir=cache_path,
    )
    try:
        return int(count_str)
    except ValueError:
        return 0


def _resolve_ref(cache_path: Path) -> str:
    """Find the best ref to read from in a bare clone.

    Bare clones from `git clone --bare` store refs as refs/heads/main
    (not origin/main). After `git fetch origin`, they may also have
    refs/remotes/origin/main. Try both patterns.
    """
    # Try origin/ refs first (populated after fetch)
    for ref in ("origin/main", "origin/master", "origin/dev"):
        _, ok = _git_bare("rev-parse", "--verify", ref, git_dir=cache_path)
        if ok:
            return ref
    # Try bare-clone native refs (refs/heads/)
    for ref in ("main", "master", "dev"):
        _, ok = _git_bare("rev-parse", "--verify", ref, git_dir=cache_path)
        if ok:
            return ref
    return "HEAD"


def read_gator_state_remote(cache_path: Path, ref: str | None = None) -> dict:
    """Read governance state from a bare cache. Parallel to read_gator_state()."""
    if ref is None:
        ref = _resolve_ref(cache_path)

    state = {
        "gatorized": False,
        "generation": 0,
        "policy_version": None,
        "charters": 0,
        "functions": 0,
        "threads": 0,
        "issues": 0,
        "mission_summary": None,
        "has_hooks": False,
        "hooks_sources": False,
        "hooks_installed": False,  # Cannot determine remotely
        "scan_mode": "remote",
        "ref": ref,
    }

    # Check if .gator/ exists
    ls_gator = git_ls_tree(cache_path, ref, ".gator")
    if not ls_gator:
        return state
    state["gatorized"] = True

    # Generation
    version_content = git_show(cache_path, ref, ".gator/.gator-version")
    if version_content:
        for line in version_content.splitlines():
            if line.startswith("generation:"):
                try:
                    state["generation"] = int(line.split(":", 1)[1].strip())
                except ValueError:
                    pass

    # Policy version
    cp_content = git_show(cache_path, ref, ".gator/command-post.md")
    if cp_content:
        for line in cp_content.splitlines():
            if line.startswith("version:"):
                state["policy_version"] = line.split(":", 1)[1].strip()
                break

    # Charters
    charter_files = git_ls_tree(cache_path, ref, ".gator/charters")
    skip = {"_template.md", "README.md", "INDEX.md", ".gitkeep"}
    real_charters = [f for f in charter_files if f.endswith(".md") and f not in skip]
    state["charters"] = len(real_charters)

    # Function count (read each charter)
    func_count = 0
    for charter_name in real_charters:
        content = git_show(cache_path, ref, f".gator/charters/{charter_name}")
        if content:
            for line in content.splitlines():
                if line.strip().startswith("### ") and "(" in line:
                    func_count += 1
    state["functions"] = func_count

    # Threads
    for subdir in ("active-threads", "threads"):
        entries = git_ls_tree(cache_path, ref, f".gator/{subdir}")
        state["threads"] += len([
            f for f in entries if f.endswith(".md") and f != ".gitkeep"
        ])

    # Issues
    issues_content = git_show(cache_path, ref, ".gator/issues.md")
    if issues_content:
        for line in issues_content.splitlines():
            if "**Status**: Open" in line or "**Status**: Working" in line:
                state["issues"] += 1

    # Mission summary
    mission_content = git_show(cache_path, ref, ".gator/mission.md")
    if mission_content:
        for line in mission_content.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("["):
                state["mission_summary"] = stripped[:80]
                break

    # Hook sources (can detect from committed files, not installed state)
    hook_files = git_ls_tree(cache_path, ref, ".gator/scripts/hooks")
    state["hooks_sources"] = len(hook_files) > 0
    state["has_hooks"] = state["hooks_sources"]

    return state


def scan_repo_remote(repo_entry: dict) -> dict:
    """Scan a repo via thin-fetch. Parallel to scan_repo() in fleet-report."""
    name = repo_entry["name"]
    remote = repo_entry.get("remote", "")

    report = {
        "name": name,
        "path": repo_entry.get("path", "—"),
        "remote": remote,
        "registered": repo_entry.get("registered", "—"),
        "accessible": False,
        "scan_mode": "remote",
    }

    if not remote or remote == "—":
        report["error"] = "no remote URL in registry"
        return report

    # Ensure bare cache exists and is current
    cache_path = ensure_cache(name, remote)
    if not cache_path:
        report["error"] = f"failed to fetch {remote}"
        return report

    report["accessible"] = True
    ref = _resolve_ref(cache_path)

    # Git state (from remote ref)
    report["branch"] = ref.split("/")[-1]  # Best guess from ref
    report["last_commit"] = git_log_last_commit(cache_path, ref)
    report["commits_30d"] = git_commit_count(cache_path, ref, 30)
    report["working_tree"] = "remote (unknown)"
    report["trailers"] = git_log_trailers(cache_path, ref)

    # .gator/ state
    gator = read_gator_state_remote(cache_path, ref)
    report.update(gator)

    return report


def list_committed_sessions_remote(
    cache_path: Path, ref: str | None = None
) -> list[str]:
    """List committed session summary filenames from a bare cache."""
    if ref is None:
        ref = _resolve_ref(cache_path)
    entries = git_ls_tree(cache_path, ref, ".gator/sessions")
    return [f for f in entries if f.endswith(".md")]


def read_session_summary_remote(
    cache_path: Path, filename: str, ref: str | None = None
) -> str | None:
    """Read a specific session summary from a bare cache."""
    if ref is None:
        ref = _resolve_ref(cache_path)
    return git_show(cache_path, ref, f".gator/sessions/{filename}")


def get_cache_status() -> list[dict]:
    """Report on all cached repos."""
    if not CACHE_DIR.is_dir():
        return []

    status = []
    for item in sorted(CACHE_DIR.iterdir()):
        if item.is_dir() and item.name.endswith(".git"):
            # Name format: "repo-name-abcdef12.git" (name + 8-char URL hash)
            # Strip .git suffix, then strip the last -hash segment
            bare_name = item.name[:-4]  # remove .git
            # Split on last dash to separate name from hash
            parts = bare_name.rsplit("-", 1)
            if len(parts) == 2 and len(parts[1]) == 8:
                repo_name = parts[0]
            else:
                repo_name = bare_name  # legacy format without hash
            # Get remote URL
            url, _ = _git_bare(
                "remote", "get-url", "origin", git_dir=item
            )
            # Get last fetch time (use FETCH_HEAD mtime)
            fetch_head = item / "FETCH_HEAD"
            last_fetch = None
            if fetch_head.exists():
                import datetime as dt
                mtime = fetch_head.stat().st_mtime
                last_fetch = dt.datetime.fromtimestamp(mtime).isoformat()

            status.append({
                "name": repo_name,
                "cache_path": str(item),
                "remote": url or "unknown",
                "last_fetch": last_fetch,
            })

    return status
