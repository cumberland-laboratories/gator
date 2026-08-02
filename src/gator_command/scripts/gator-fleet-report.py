#!/usr/bin/env python3
"""
gator fleet-report — Cross-repo governance status from git + .gator/ state.

Reads the fleet registry, visits each repo's local path, and produces a
governance status report from git history and .gator/ file state. When
Gator-* trailers are present in commits, those are included as richer
metadata. The report works without trailers — they're a bonus layer.

Resolution order per repo:
1. Try local path → full scan (working tree + git history + .gator/)
2. If local inaccessible AND remote URL exists → thin-fetch scan
   (bare clone cache, git show/log against remote refs)
3. If neither → report as unreachable

Use --remote to force thin-fetch for ALL repos (skip local checkouts entirely).

Usage:
    python gator-command/scripts/gator-fleet-report.py
    python gator-command/scripts/gator-fleet-report.py --json
    python gator-command/scripts/gator-fleet-report.py --repo dangerous-golf
    python gator-command/scripts/gator-fleet-report.py --remote

@reads: gator-command/registry.md, .gator/ in each registered repo, git history,
        ~/.gator/fleet-cache/ (bare clones for remote scanning)
@writes: ~/.gator/fleet-cache/ (creates/updates bare clones when remote scanning)
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from gator_core import (
    get_version, find_command_post, normalize_path, parse_registry,
    git, ensure_utf8_stdout,
)
from gator_layout import get_gator_paths
from gator_remote import scan_repo_remote

VERSION = get_version()

# Policy status integration — graceful degradation if module unavailable
try:
    from gator_core import import_sibling
    _ps = import_sibling("gator-policy-status")
    if _ps:
        _compute_sync_state = _ps.compute_sync_state
        _get_governance_source = _ps.get_governance_source
        _load_policy_link = _ps.load_policy_link
        _HAS_POLICY_STATUS = True
    else:
        _HAS_POLICY_STATUS = False
except Exception:
    _HAS_POLICY_STATUS = False


def _hook_probe_dirs(repo_path):
    """Return hook directories to probe, preferring the managed strategy."""
    try:
        from gator_core import import_sibling
        update = import_sibling("gator-update")
        if update:
            return update.get_hook_probe_dirs(repo_path)
    except Exception:
        pass
    return [repo_path / ".git" / "hooks"]


def get_last_commit(repo_path):
    """Get last commit info from a repo."""
    log_line, ok = git(
        "log", "-1", "--format=%h|%s|%cr|%ci", "dev",
        cwd=repo_path,
    )
    if not ok or not log_line:
        # Try current branch if dev doesn't exist
        log_line, ok = git(
            "log", "-1", "--format=%h|%s|%cr|%ci",
            cwd=repo_path,
        )
    if not ok:
        return {"error": "git log failed"}
    if not log_line:
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


def get_commit_count(repo_path, days=30):
    """Count commits in the last N days."""
    count, ok = git(
        "rev-list", "--count", f"--since={days} days ago", "HEAD",
        cwd=repo_path,
    )
    try:
        return int(count)
    except ValueError:
        return 0


def get_current_branch(repo_path):
    """Get current branch name."""
    branch, ok = git("branch", "--show-current", cwd=repo_path)
    if not ok:
        return "error: git failed"
    return branch or "detached"


def get_working_tree_status(repo_path):
    """Check if working tree is clean."""
    status, ok = git("status", "--porcelain", cwd=repo_path)
    if not ok:
        return "error: git failed"
    if not status:
        return "clean"
    lines = [l for l in status.splitlines() if l.strip()]
    return f"{len(lines)} changed"


def get_latest_trailers(repo_path):
    """Extract Gator-* trailers from the latest commit."""
    raw, ok = git("log", "-1", "--format=%(trailers)", "dev", cwd=repo_path)
    if not raw:
        raw, ok = git("log", "-1", "--format=%(trailers)", cwd=repo_path)
    if not raw:
        return {}

    trailers = {}
    for line in raw.splitlines():
        if line.startswith("Gator-"):
            key, _, value = line.partition(":")
            trailers[key.strip()] = value.strip()

    return trailers


# ---------------------------------------------------------------------------
# .gator/ state readers
# ---------------------------------------------------------------------------

def read_gator_state(repo_path):
    """Read governance state from .gator/ files."""
    paths = get_gator_paths(repo_path)
    state = {
        "gatorized": paths.layout != "invalid",
        "generation": 0,
        "policy_version": None,
        "charters": 0,
        "functions": 0,
        "threads": 0,
        "issues": 0,
        "mission_summary": None,
        "has_hooks": False,
    }

    if not state["gatorized"]:
        return state

    # Generation and last-updated timestamp
    version_file = paths.gator_root / ".gator-version"
    if version_file.exists():
        for line in version_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("generation:"):
                try:
                    state["generation"] = int(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif line.startswith("updated:"):
                state["gator_updated"] = line.split(":", 1)[1].strip()
            elif line.startswith("cli-version:"):
                state["cli_version"] = line.split(":", 1)[1].strip()

    # Policy version
    cp_file = paths.gator_root / "command-post.md"
    if cp_file.exists():
        for line in cp_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("version:"):
                state["policy_version"] = line.split(":", 1)[1].strip()
                break

    # Charters
    charters_dir = paths.charters_dir
    if charters_dir.is_dir():
        skip = {"_template.md", "README.md", "INDEX.md", ".gitkeep"}
        charter_files = [
            f for f in charters_dir.iterdir()
            if f.suffix == ".md" and f.name not in skip
        ]
        state["charters"] = len(charter_files)

        func_count = 0
        for cf in charter_files:
            try:
                text = cf.read_text(encoding="utf-8", errors="replace")
                for line in text.splitlines():
                    if line.strip().startswith("### ") and "(" in line:
                        func_count += 1
            except OSError:
                continue
        state["functions"] = func_count

    # Threads
    for tdir in (paths.active_threads_dir, paths.threads_dir):
        if tdir.is_dir():
            state["threads"] += len([
                f for f in tdir.iterdir()
                if f.suffix == ".md" and f.name != ".gitkeep"
            ])

    # Issues
    issues_file = paths.issues
    if issues_file.exists():
        text = issues_file.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if "**Status**: Open" in line or "**Status**: Working" in line:
                state["issues"] += 1

    # Mission one-liner
    mission_file = paths.mission
    if mission_file.exists():
        text = mission_file.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("["):
                state["mission_summary"] = stripped[:80]
                break

    # Hook presence — check both sources (.gator/scripts/hooks/) and
    # installed (.git/hooks/pre-commit, commit-msg)
    hooks_src = paths.scripts_dir / "hooks"
    git_hooks = _hook_probe_dirs(repo_path)
    has_sources = hooks_src.is_dir() and any(hooks_src.iterdir())
    has_installed = any(
        hooks_dir.is_dir() and (
            (hooks_dir / "pre-commit").exists() or
            (hooks_dir / "commit-msg").exists()
        )
        for hooks_dir in git_hooks
    )
    state["has_hooks"] = has_sources or has_installed
    state["hooks_sources"] = has_sources
    state["hooks_installed"] = has_installed

    return state


# ---------------------------------------------------------------------------
# Policy link
# ---------------------------------------------------------------------------

def get_policy_link_local(repo_path):
    """Get policy sync status for a local repo.

    Returns a dict with state, authority, and provenance fields.
    Falls back gracefully if policy-status module is unavailable.
    """
    if not _HAS_POLICY_STATUS:
        return {"state": "unavailable", "authority": "none"}

    paths = get_gator_paths(repo_path)
    if paths.layout == "invalid":
        return {"state": "unavailable", "authority": "none"}

    # Legacy policy functions take raw gator_dir
    gator_dir = paths.gator_root
    try:
        source, is_derived = _get_governance_source(gator_dir)
        if not source:
            return {"state": "unknown", "authority": "none"}

        status = _compute_sync_state(gator_dir, source)
        state = status.get("state", "unknown")

        # Authoritative = we actually compared against the source.
        # synced/behind/diverged always require a source comparison.
        # no-cache is only authoritative when source_type is "local"
        # (we verified against the local source and confirmed no cache).
        # Remote-only no-cache means we haven't done a freshness check.
        source_type = status.get("source_type")
        authoritative = state in ("synced", "behind", "diverged") or (
            state == "no-cache" and source_type == "local"
        )
        return {
            "state": state,
            "authority": "authoritative" if authoritative else "non-authoritative",
            "source_type": status.get("source_type"),
            "remote_url": source.get("remote_url"),
            "cached_at": status.get("cached_at"),
            "source_commit": status.get("source_commit"),
            "cached_commit": status.get("cached_commit"),
        }
    except Exception:
        return {"state": "unavailable", "authority": "none"}


def get_policy_link_remote(repo_path):
    """Get policy link info for a remote repo from cached policy-link.json.

    Remote repos cannot compute authoritative sync state — we can only
    report what's cached.
    """
    if not _HAS_POLICY_STATUS:
        return {"state": "unavailable", "authority": "none"}

    paths = get_gator_paths(repo_path)
    if paths.layout == "invalid":
        return {"state": "unknown", "authority": "none"}

    # Legacy policy function takes raw gator_dir
    gator_dir = paths.gator_root
    try:
        link = _load_policy_link(gator_dir)
        if link:
            return {
                "state": "cached",
                "authority": "non-authoritative",
                "source_type": link.get("source_type"),
                "remote_url": link.get("remote_url"),
                "cached_at": link.get("cached_at"),
                "cached_commit": link.get("source_commit"),
            }
        return {"state": "unknown", "authority": "none"}
    except Exception:
        return {"state": "unavailable", "authority": "none"}


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------

def scan_repo(repo_entry, force_remote=False):
    """Scan a single registered repo. Returns full status dict.

    If force_remote is True, skip local checkout and use thin-fetch.
    Otherwise, try local first and fall back to remote if inaccessible.
    """
    repo_path = Path(normalize_path(repo_entry["path"]))

    if force_remote:
        return scan_repo_remote(repo_entry)

    report = {
        "name": repo_entry["name"],
        "path": str(repo_path),
        "remote": repo_entry.get("remote", "—"),
        "registered": repo_entry.get("registered", "—"),
        "accessible": repo_path.is_dir(),
        "scan_mode": "local",
    }

    if not report["accessible"]:
        # Fallback: try remote if URL available
        remote = repo_entry.get("remote", "—")
        if remote and remote != "—":
            return scan_repo_remote(repo_entry)
        return report

    # Git state
    report["branch"] = get_current_branch(repo_path)
    report["last_commit"] = get_last_commit(repo_path)
    report["commits_30d"] = get_commit_count(repo_path, 30)
    report["working_tree"] = get_working_tree_status(repo_path)
    report["trailers"] = get_latest_trailers(repo_path)

    # .gator/ state
    gator = read_gator_state(repo_path)
    report.update(gator)

    # Policy link (authoritative for local repos)
    report["policy_link"] = get_policy_link_local(repo_path)

    return report


def _add_remote_policy_link(report):
    """Add policy_link for remote-scanned repos.

    Remote repos can't compute authoritative sync state. Check if the
    remote has a policy-link.json via the bare cache.
    """
    if report.get("policy_link"):
        return  # Already set (local scan)
    if not report.get("accessible"):
        report["policy_link"] = {"state": "unavailable", "authority": "none"}
        return
    if report.get("scan_mode") != "remote":
        report.setdefault("policy_link", {"state": "unavailable", "authority": "none"})
        return

    # Try reading policy-link.json from bare cache
    if _HAS_POLICY_STATUS:
        try:
            from gator_remote import CACHE_DIR, _cache_key, _resolve_ref, git_show
            import json as _json
            name = report["name"]
            remote = report.get("remote", "")
            if remote and remote != "—":
                cache_path = CACHE_DIR / _cache_key(name, remote)
                if cache_path.is_dir():
                    ref = _resolve_ref(cache_path)
                    content = git_show(cache_path, ref, ".gator/policy-link.json")
                    if content:
                        link = _json.loads(content)
                        report["policy_link"] = {
                            "state": "cached",
                            "authority": "non-authoritative",
                            "source_type": link.get("source_type"),
                            "remote_url": link.get("remote_url"),
                            "cached_at": link.get("cached_at"),
                            "cached_commit": link.get("source_commit"),
                        }
                        return
        except Exception:
            pass

    report["policy_link"] = {"state": "unknown", "authority": "none"}


def scan_fleet(repos, force_remote=False):
    """Scan all registered repos."""
    results = [scan_repo(r, force_remote=force_remote) for r in repos]
    for r in results:
        if r.get("scan_mode") == "remote" or not r.get("policy_link"):
            _add_remote_policy_link(r)
    return results


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def _compute_policy_summary(reports):
    """Compute policy sync summary counts from fleet reports."""
    current = stale = needs_action = 0
    for r in reports:
        link = r.get("policy_link", {})
        state = link.get("state", "unknown")
        if state == "synced":
            current += 1
        elif state in ("behind", "diverged"):
            stale += 1
        elif state == "no-cache":
            needs_action += 1
        # cached, local-only, unknown, unavailable — not counted
    return {
        "policy_current": current,
        "policy_stale": stale,
        "policy_needs_action": needs_action,
    }


def print_fleet_report(reports):
    """Print formatted fleet report."""
    print()
    print("  gator fleet-report")
    print(f"  {len(reports)} repos registered")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print()

    for r in reports:
        name = r["name"]

        if not r["accessible"]:
            print(f"  ✗ {name}")
            error = r.get("error", f"NOT ACCESSIBLE — {r['path']}")
            print(f"    {error}")
            print()
            continue

        # Status indicator
        issues = r.get("issues", 0)
        has_trailers = bool(r.get("trailers"))
        scan_mode = r.get("scan_mode", "local")
        indicator = "✓" if issues == 0 else "!"
        mode_tag = " (remote)" if scan_mode == "remote" else ""

        print(f"  {indicator} {name}{mode_tag}")

        # Git info
        commit = r.get("last_commit")
        if commit and "error" in commit:
            print(f"    last commit: {commit['error']}")
        elif commit:
            print(f"    last commit: {commit['hash']} {commit['message'][:50]} ({commit['age']})")
        print(f"    branch: {r.get('branch', '?')}  |  tree: {r.get('working_tree', '?')}  |  commits (30d): {r.get('commits_30d', 0)}")

        # Governance info
        gen = r.get("generation", 0)
        policy = r.get("policy_version", "—")
        charters = r.get("charters", 0)
        functions = r.get("functions", 0)
        threads = r.get("threads", 0)
        if r.get("hooks_sources") and r.get("hooks_installed"):
            hooks = "yes"
        elif r.get("hooks_installed"):
            hooks = "installed (no sources)"
        elif r.get("hooks_sources"):
            hooks = "sources only (not installed)"
        else:
            hooks = "no"

        print(f"    gen {gen}  |  policy: {policy}  |  charters: {charters} ({functions} fn)  |  threads: {threads}")
        print(f"    issues: {issues}  |  hooks: {hooks}")

        # Trailers (if present)
        trailers = r.get("trailers", {})
        if trailers:
            trailer_parts = []
            if "Gator-Significance" in trailers:
                trailer_parts.append(f"sig: {trailers['Gator-Significance']}")
            if "Gator-Change-Type" in trailers:
                trailer_parts.append(f"type: {trailers['Gator-Change-Type']}")
            if "Gator-Charter-Changed" in trailers:
                trailer_parts.append(f"charter: {trailers['Gator-Charter-Changed']}")
            if "Gator-Agent" in trailers:
                trailer_parts.append(f"agent: {trailers['Gator-Agent']}")
            if trailer_parts:
                print(f"    trailers: {' | '.join(trailer_parts)}")

        # Mission
        mission = r.get("mission_summary")
        if mission:
            print(f"    mission: {mission}")

        print()

    # Fleet summary
    accessible = [r for r in reports if r.get("accessible")]
    local_scanned = sum(1 for r in accessible if r.get("scan_mode") == "local")
    remote_scanned = sum(1 for r in accessible if r.get("scan_mode") == "remote")
    total_charters = sum(r.get("charters", 0) for r in accessible)
    total_functions = sum(r.get("functions", 0) for r in accessible)
    total_issues = sum(r.get("issues", 0) for r in accessible)
    with_hooks = sum(1 for r in accessible if r.get("has_hooks"))
    with_trailers = sum(1 for r in accessible if r.get("trailers"))

    # Policy summary (authoritative repos only)
    policy_counts = _compute_policy_summary(reports)

    print(f"  fleet totals: {total_charters} charters, {total_functions} functions, {total_issues} issues")
    print(f"  hooks: {with_hooks}/{len(accessible)} repos  |  trailers: {with_trailers}/{len(accessible)} repos")
    pc = policy_counts
    print(f"  policy: {pc['policy_current']} synced, {pc['policy_stale']} stale, {pc['policy_needs_action']} need cache")
    if remote_scanned:
        print(f"  scan: {local_scanned} local, {remote_scanned} remote (thin-fetch)")
    print()


def print_json_report(reports):
    """Output fleet report as JSON."""
    summary = {
        "total": len(reports),
        "accessible": sum(1 for r in reports if r.get("accessible")),
        "total_charters": sum(r.get("charters", 0) for r in reports),
        "total_functions": sum(r.get("functions", 0) for r in reports),
        "total_issues": sum(r.get("issues", 0) for r in reports),
        "with_hooks": sum(1 for r in reports if r.get("has_hooks")),
        "with_trailers": sum(1 for r in reports if r.get("trailers")),
    }
    summary.update(_compute_policy_summary(reports))
    output = {
        "version": VERSION,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repos": reports,
        "summary": summary,
    }
    print(json.dumps(output, indent=2))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    ensure_utf8_stdout()

    parser = argparse.ArgumentParser(
        description="Gator fleet-report — cross-repo governance status."
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON",
    )
    parser.add_argument(
        "--repo", "-r",
        help="Report on a single repo by name",
    )
    parser.add_argument(
        "--remote",
        action="store_true",
        help="Force remote scanning for all repos (thin-fetch via bare cache)",
    )
    args = parser.parse_args()

    command_post = find_command_post()
    if not command_post:
        print("  Error: not in a gator-command repo.", file=sys.stderr)
        sys.exit(1)

    repos = parse_registry(command_post)
    if not repos:
        print("  No repos in registry.", file=sys.stderr)
        sys.exit(1)

    # Filter to single repo if requested
    if args.repo:
        repos = [r for r in repos if r["name"] == args.repo]
        if not repos:
            print(f"  Error: repo '{args.repo}' not found in registry.", file=sys.stderr)
            sys.exit(1)

    # Scan
    reports = scan_fleet(repos, force_remote=args.remote)

    # Output
    if args.json:
        print_json_report(reports)
    else:
        print_fleet_report(reports)


if __name__ == "__main__":
    main()
