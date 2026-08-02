"""Data collection and transformation for the dashboard.

Handles registry loading, standalone data collection, repo path
resolution, search, history, and repo key injection.
"""

import os
import re
from datetime import datetime, timezone
from pathlib import Path

from dashboard.helpers import run_json, run_text, git_run

from gator_core import (
    import_sibling,
    normalize_path, git,
)


# ── discovery roots ───────────────────────────────────────────────────────────

# Default home-relative directories to scan for local Git repositories when
# the "Add Repository" modal fetches auto-discovery candidates.
DEFAULT_DISCOVERY_ROOTS = ("code", "code2", "projects", "repos", "src", "dev")


def resolve_discovery_roots():
    """Return the list of directory paths to scan for local Git repositories.

    Resolution order:
    1. `GATOR_DASHBOARD_DISCOVERY_ROOTS` environment variable, if set and
       non-empty — a list of paths separated by the OS path separator
       (`:` on Unix, `;` on Windows). Tilde is expanded per entry.
    2. Default home-relative set: `~/code`, `~/code2`, `~/projects`,
       `~/repos`, `~/src`, `~/dev`.

    Only returns paths that exist as directories — non-existent entries
    are filtered out silently. Env-var override is exclusive: when set,
    the defaults are NOT unioned in.

    The env-var override exists so the Dashboard can be pointed at an
    isolated fleet for screenshot capture, demo sessions, or repos
    organized outside the default home-relative layout (e.g. `~/work`,
    `/mnt/repos`).
    """
    env_roots = os.environ.get("GATOR_DASHBOARD_DISCOVERY_ROOTS", "").strip()
    if env_roots:
        candidates = [
            Path(p.strip()).expanduser()
            for p in env_roots.split(os.pathsep)
            if p.strip()
        ]
    else:
        home = Path.home()
        candidates = [home / name for name in DEFAULT_DISCOVERY_ROOTS]
    return [c for c in candidates if c.is_dir()]


# ── registry ──────────────────────────────────────────────────────────────────

def load_registry_repos(command_post_root):
    """Load repo list from machine-local dashboard registry.

    Args:
        command_post_root: Unused (kept for call-site compatibility).
    """
    try:
        from gator_core import read_dashboard_registry
        repos = read_dashboard_registry()
    except ImportError:
        repos = []
    # Normalize MSYS-style paths (/c/Users/...) to Windows-native
    for r in repos:
        raw = r.get("path", "")
        if raw:
            r["path"] = normalize_path(raw)
    return repos


# ── repo path resolution ─────────────────────────────────────────────────────

def resolve_repo_path(repo_name, registry_repos):
    """Resolve a repo name to its absolute path from the registry.

    Returns a normalized path (Windows-native on Windows) so Path.is_dir()
    works correctly. Registry may contain MSYS-style /c/ paths.
    """
    for r in registry_repos:
        if r.get("name") == repo_name:
            raw = r.get("path", "")
            return normalize_path(raw) if raw else ""
    return ""


# ── git history ───────────────────────────────────────────────────────────────

def get_repo_history(repo_path, limit=20):
    """Get recent commit history from a repo via git log.

    Returns list of commit dicts with hash, short_hash, date, author,
    subject, body, and trailers. Pure git — no session dependency.
    """
    fmt = "%H%x00%h%x00%aI%x00%an%x00%s%x00%b%x00%(trailers:key=Gator-Agent)%x00%(trailers:key=Gator-Architect)%x01"
    out, ok = git(
        "log", f"--max-count={limit}", f"--format={fmt}",
        cwd=repo_path,
    )
    if not ok or not out:
        return []

    commits = []
    for record in out.split("\x01"):
        record = record.strip()
        if not record:
            continue
        parts = record.split("\x00")
        if len(parts) < 6:
            continue
        commits.append({
            "hash": parts[0],
            "short_hash": parts[1],
            "date": parts[2],
            "author": parts[3],
            "subject": parts[4],
            "body": parts[5].strip(),
            "agent": parts[6].strip().replace("Gator-Agent: ", "") if len(parts) > 6 else "",
            "architect": parts[7].strip().replace("Gator-Architect: ", "") if len(parts) > 7 else "",
        })
    return commits


# ── audit sessions ────────────────────────────────────────────────────────────

def resolve_audit_sessions(repo_hash=None, fleet=False, refresh=False,
                           registry_repos=None):
    """Resolve and return session summaries for the audit endpoint.

    Returns {"data": ..., "status": ...} dict. Testable without HTTP.
    """
    try:
        aggregator = import_sibling("gator-session-aggregator")
    except Exception as exc:
        return {"data": {"error": f"aggregator not available: {exc}"}, "status": 500}

    if fleet:
        summaries = aggregator.get_fleet_summaries(force_refresh=refresh)
        return {"data": summaries, "status": 200}

    if repo_hash:
        repo_path = None
        for r in (registry_repos or []):
            raw = r.get("path", "")
            resolved = normalize_path(raw) if raw else ""
            if resolved and aggregator.session_cache_key(resolved) == repo_hash:
                repo_path = resolved
                break
        if not repo_path:
            return {"data": {"error": f"repo not found for key: {repo_hash}"}, "status": 404}
        summaries = aggregator.get_session_summaries(repo_path, force_refresh=refresh)
        return {"data": summaries, "status": 200}

    summaries = aggregator.get_fleet_summaries(force_refresh=refresh)
    return {"data": summaries, "status": 200}


# ── repo update ───────────────────────────────────────────────────────────────

def resolve_repo_update(repo_name, registry_repos=None, fleet_data=None,
                        run_text_fn=None):
    """Resolve a repo update request and run gator-update against it.

    Returns {"data": ..., "status": ...} dict. Testable without HTTP.
    Pre-checks that the repo path exists and contains a .gator/ dir —
    ungatorized repos get HTTP 400 pointing at the Gatorize button.
    """
    if not repo_name:
        return {"data": {"error": "repo name required"}, "status": 400}

    repo_path = resolve_repo_path(repo_name, registry_repos or [])
    if not repo_path:
        repos = (fleet_data or {}).get("repos", [])
        repo = next((r for r in repos if r.get("name") == repo_name), None)
        if not repo:
            return {"data": {"error": f"repo '{repo_name}' not found"}, "status": 404}
        if not repo.get("accessible"):
            return {"data": {"error": "repo not accessible locally"}, "status": 400}
        repo_path = normalize_path(repo.get("path", ""))

    if not repo_path or not Path(repo_path).is_dir():
        return {"data": {"error": "repo path not accessible"}, "status": 400}

    if not (Path(repo_path) / ".gator").is_dir():
        return {
            "data": {"error": "not gatorized — use Gatorize button (Fleet row) instead of Update"},
            "status": 400,
        }

    runner = run_text_fn or run_text
    stdout, stderr, exit_code = runner(
        "gator-update", "--path", repo_path, timeout=60,
    )
    return {
        "data": {
            "status": "ok" if exit_code == 0 else "error",
            "output": stdout or stderr,
            "exit_code": exit_code,
        },
        "status": 200,
    }


# ── repo gatorize (Stage 3 fold-in of retire-gator-install plan) ──────────────

def resolve_repo_gatorize(repo_name, registry_repos=None, fleet_data=None,
                          run_text_fn=None):
    """Resolve a repo gatorize request and run `gator gatorize --yes` against it.

    Returns {"status": ..., "data": ...} dict. Testable without HTTP.
    Called when the Fleet-row 'Gatorize' button POSTs to
    /api/repo/<name>/gatorize on an ungoverned repo. Unlike resolve_repo_update,
    this endpoint EXPECTS the target repo to have no .gator/ dir yet — it's
    the install path, not the refresh path. Runs non-interactively via --yes
    because the Dashboard cannot answer prompts.
    """
    if not repo_name:
        return {"data": {"error": "repo name required"}, "status": 400}

    repo_path = resolve_repo_path(repo_name, registry_repos or [])
    if not repo_path:
        repos = (fleet_data or {}).get("repos", [])
        repo = next((r for r in repos if r.get("name") == repo_name), None)
        if not repo:
            return {"data": {"error": f"repo '{repo_name}' not found"}, "status": 404}
        if not repo.get("accessible"):
            return {"data": {"error": "repo not accessible locally"}, "status": 400}
        repo_path = normalize_path(repo.get("path", ""))

    if not repo_path or not Path(repo_path).is_dir():
        return {"data": {"error": "repo path not accessible"}, "status": 400}

    # If already gatorized, deflect to the update endpoint — no need to re-run
    # the installer against an already-governed repo.
    if (Path(repo_path) / ".gator").is_dir():
        return {
            "data": {"error": "already gatorized — use Update button instead"},
            "status": 400,
        }

    runner = run_text_fn or run_text
    stdout, stderr, exit_code = runner(
        "gatorize", "--yes", repo_path, timeout=120,
    )
    return {
        "data": {
            "status": "ok" if exit_code == 0 else "error",
            "output": stdout or stderr,
            "exit_code": exit_code,
        },
        "status": 200,
    }


# ── data injection ────────────────────────────────────────────────────────────

def inject_repo_keys(fast_data):
    """Add repo_key (path-hash) to each fleet repo entry for session identity."""
    try:
        agg = import_sibling("gator-session-aggregator")
    except Exception:
        return fast_data
    fleet = fast_data.get("fleet") or {}
    repos = fleet.get("repos") or fast_data.get("repos") or []
    for r in repos:
        if r.get("repo_key"):
            continue
        raw = r.get("path", "")
        resolved = normalize_path(raw) if raw else ""
        r["repo_key"] = agg.session_cache_key(resolved) if resolved else ""
    return fast_data


# ── search ────────────────────────────────────────────────────────────────────

def parse_search_query(query):
    """Parse a search query with AND/OR boolean operators.

    Returns (mode, terms) where mode is "and", "or", or "phrase".
    """
    and_parts = re.split(r'\s+AND\s+', query, flags=re.IGNORECASE)
    if len(and_parts) > 1:
        terms = [t.strip().lower() for t in and_parts if t.strip()]
        return ("and", terms)
    or_parts = re.split(r'\s+OR\s+', query, flags=re.IGNORECASE)
    if len(or_parts) > 1:
        terms = [t.strip().lower() for t in or_parts if t.strip()]
        return ("or", terms)
    return ("phrase", [query.lower()])


def search_repo_files(repo_path, query, max_results=50):
    """Search .gator/ and gator-command/ files for a query string.

    Supports boolean operators: AND (all terms), OR (any term), or plain phrase.
    Returns list of {path, snippet, match_count} dicts.
    """
    repo_root = Path(repo_path)
    mode, terms = parse_search_query(query)
    results = []

    scan_dirs = []
    gator_dir = repo_root / ".gator"
    gc_dir = repo_root / "gator-command"
    if gator_dir.is_dir():
        scan_dirs.append((gator_dir, ".gator"))
    if gc_dir.is_dir():
        scan_dirs.append((gc_dir, "gator-command"))

    for base_dir, prefix in scan_dirs:
        for ext in ("*.md", "*.json"):
            for f in sorted(base_dir.rglob(ext)):
                if len(results) >= max_results:
                    break
                rel = str(f.relative_to(base_dir)).replace("\\", "/")
                if rel.startswith("sessions/_active/"):
                    continue
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                lower_content = content.lower()

                if mode == "and":
                    if not all(t in lower_content for t in terms):
                        continue
                elif mode == "or":
                    if not any(t in lower_content for t in terms):
                        continue
                else:
                    if terms[0] not in lower_content:
                        continue

                match_count = 0
                first_idx = len(content)
                for t in terms:
                    match_count += lower_content.count(t)
                    idx = lower_content.find(t)
                    if 0 <= idx < first_idx:
                        first_idx = idx

                start = max(0, first_idx - 60)
                end = min(len(content), first_idx + 80)
                snippet = content[start:end].replace("\n", " ")
                if start > 0:
                    snippet = "..." + snippet
                if end < len(content):
                    snippet = snippet + "..."

                file_path = rel if prefix == ".gator" else prefix + "/" + rel
                results.append({
                    "path": file_path,
                    "snippet": snippet,
                    "match_count": match_count,
                })

    results.sort(key=lambda r: r["match_count"], reverse=True)
    return results[:max_results]


# ── data collection ───────────────────────────────────────────────────────────

def collect_standalone_data(registry_repos):
    """Standalone startup: per-repo governance data from gator-repo-status."""
    repos = []
    for r in registry_repos:
        repo_path = r.get("path", "")
        accessible = bool(repo_path and Path(repo_path).is_dir())
        repo_key = ""
        if accessible:
            try:
                agg = import_sibling("gator-session-aggregator")
                repo_key = agg.session_cache_key(repo_path)
            except Exception:
                pass
        repo_data = {
            "name": r.get("name", ""),
            "path": repo_path,
            "repo_key": repo_key,
            "remote": r.get("remote", ""),
            "registered": r.get("registered", r.get("added_at", "")),
            "status": r.get("status", "current"),
            "accessible": accessible,
            "gatorized": (Path(repo_path) / ".gator").is_dir() if repo_path else False,
        }
        if accessible:
            status = run_json("gator-repo-status", "--path", repo_path, timeout=15)
            if status and not status.get("error"):
                repo_data.update({
                    "branch": status.get("branch", ""),
                    "charters": status.get("charter_count", 0),
                    "charter_coverage_pct": status.get("charter_coverage_pct", 0),
                    "hook_status": status.get("hook_status", "unknown"),
                    "config": status.get("config", {}),
                    "topology": status.get("topology", "standalone"),
                    "last_governed_commit": status.get("last_governed_commit"),
                    "session_summary_count": status.get("session_summary_count", 0),
                    "override_events": status.get("override_events", []),
                    "cli_version": status.get("cli_version", ""),
                })
            elif status and status.get("error"):
                repo_data["status_error"] = status["error"]
        repos.append(repo_data)
    # Resolve current CLI version for frontend version comparison
    cli_ver = ""
    try:
        from gator_core import get_version
        cli_ver = get_version()
    except ImportError:
        pass

    return {
        "standalone": True,
        "generated_at": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gator_cli_version": cli_ver,
        "repos": repos,
    }
