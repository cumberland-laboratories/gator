#!/usr/bin/env python3
"""
gator drift — Policy drift detection across the fleet.

Compares each registered repo's governance state against the command post's
current policy version, template generation, and structural expectations.
Reports which repos are stale, missing hooks, or diverging from org standards.

This is the first chargeable feature — the free engine produces the data,
drift detection produces the judgment.

Usage:
    python gator-command/scripts/gator-drift.py
    python gator-command/scripts/gator-drift.py --json
    python gator-command/scripts/gator-drift.py --repo dangerous-golf

@reads: gator-command/registry.md, gator-command/org-policy.md,
        .gator/ in each registered repo, git history
@writes: nothing (read-only, display only)
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from gator_core import (
    get_version, find_command_post, normalize_path, parse_registry,
    git, ensure_utf8_stdout, CURRENT_GENERATION,
)
from gator_layout import get_gator_paths
from gator_remote import (
    ensure_cache, read_gator_state_remote, git_show, CACHE_DIR,
    _resolve_ref, _cache_key,
)

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


# ---------------------------------------------------------------------------
# Command post state (the source of truth)
# ---------------------------------------------------------------------------

def read_command_post_policy(command_post):
    """Read the current org policy version from the command post.

    The policy version is the date in org-policy.md or the last
    modification date of that file.
    """
    gc_dir = command_post / "gator-command"

    # Read policy version from org-policy.md git history
    policy_date, ok = git(
        "log", "-1", "--format=%ci", "--", "gator-command/org-policy.md",
        cwd=command_post,
    )
    git_failed = not ok

    if ok and policy_date:
        policy_date = policy_date[:10]  # YYYY-MM-DD
    else:
        policy_date = None

    # Read the version field from org-policy if it has one
    org_policy = gc_dir / "org-policy.md"
    version_field = None
    if org_policy.exists():
        for line in org_policy.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("version:"):
                version_field = line.split(":", 1)[1].strip()
                break

    return {
        "policy_date": policy_date,
        "policy_version": version_field,
        "generation": CURRENT_GENERATION,
        "git_failed": git_failed,
    }


# ---------------------------------------------------------------------------
# Remote drift check (thin-fetch fallback)
# ---------------------------------------------------------------------------

def check_repo_drift_remote(repo_entry, command_post_state):
    """Check a remote repo for drift via bare cache. Subset of local checks."""
    name = repo_entry["name"]
    remote = repo_entry["remote"]

    result = {
        "name": name,
        "accessible": False,
        "scan_mode": "remote",
        "findings": [],
        "severity": "ok",
    }

    cache_path = CACHE_DIR / _cache_key(name, remote)
    if not cache_path.is_dir():
        cache_path = ensure_cache(name, remote)
    if not cache_path:
        result["findings"].append({
            "check": "remote-fetch",
            "severity": "drift",
            "message": f"Cannot fetch remote: {remote}",
        })
        result["severity"] = "drift"
        return result

    result["accessible"] = True
    ref = _resolve_ref(cache_path)
    state = read_gator_state_remote(cache_path, ref)

    if not state["gatorized"]:
        result["findings"].append({
            "check": "gatorized",
            "severity": "drift",
            "message": "Repo is registered but not gatorized (no .gator/ on remote)",
        })
        result["severity"] = "drift"
        return result

    # Generation check
    if state["generation"] < command_post_state["generation"]:
        result["findings"].append({
            "check": "generation",
            "severity": "drift",
            "message": f"Generation {state['generation']}, command post is {command_post_state['generation']}. Run gator update.",
        })

    # Policy version check
    if not command_post_state.get("git_failed") and command_post_state["policy_date"]:
        if state["policy_version"] and state["policy_version"] < command_post_state["policy_date"]:
            result["findings"].append({
                "check": "policy-version",
                "severity": "drift",
                "message": f"Policy version {state['policy_version']}, command post updated {command_post_state['policy_date']}. Run gator update.",
            })
        elif not state["policy_version"]:
            result["findings"].append({
                "check": "policy-version",
                "severity": "warn",
                "message": "No policy version in command-post.md.",
            })

    # Hook sources check (can't check installed remotely)
    if not state["hooks_sources"]:
        result["findings"].append({
            "check": "hooks",
            "severity": "warn",
            "message": "No hook sources in .gator/scripts/hooks/ (cannot verify installed hooks remotely).",
        })

    # Charter presence
    if state["charters"] == 0:
        result["findings"].append({
            "check": "charters",
            "severity": "warn",
            "message": "No charters. The governance loop requires at least one charter.",
        })

    # Constitution check
    constitution = git_show(cache_path, ref, ".gator/constitution.md")
    if not constitution:
        result["findings"].append({
            "check": "constitution",
            "severity": "drift",
            "message": "No constitution.md found on remote.",
        })

    # Policy link check (remote — informational only)
    policy_link_content = git_show(cache_path, ref, ".gator/policy-link.json")
    if policy_link_content:
        result["findings"].append({
            "check": "policy-cached",
            "severity": "info",
            "message": "Policy cache present on remote (cannot verify freshness remotely).",
        })
    else:
        result["findings"].append({
            "check": "policy-unknown",
            "severity": "info",
            "message": "No policy-link.json on remote — policy sync state unknown.",
        })

    # Set overall severity
    severities = [f["severity"] for f in result["findings"]]
    if "drift" in severities:
        result["severity"] = "drift"
    elif "warn" in severities:
        result["severity"] = "warn"

    return result


# ---------------------------------------------------------------------------
# Per-repo drift checks (local)
# ---------------------------------------------------------------------------

def check_repo_drift(repo_entry, command_post_state):
    """Check a single repo for drift against command post state.

    Returns a dict with drift findings.
    """
    repo_path = Path(normalize_path(repo_entry["path"]))

    result = {
        "name": repo_entry["name"],
        "accessible": repo_path.is_dir(),
        "findings": [],
        "severity": "ok",  # ok, warn, drift
    }

    if not result["accessible"]:
        # Try remote fallback
        remote = repo_entry.get("remote", "—")
        if remote and remote != "—":
            return check_repo_drift_remote(repo_entry, command_post_state)
        result["findings"].append({
            "check": "accessible",
            "severity": "drift",
            "message": f"Repo not accessible at {repo_path}",
        })
        result["severity"] = "drift"
        return result

    paths = get_gator_paths(repo_path)
    if paths.layout == "invalid":
        result["findings"].append({
            "check": "gatorized",
            "severity": "drift",
            "message": "Repo is registered but not gatorized (no .gator/ directory)",
        })
        result["severity"] = "drift"
        return result

    # Legacy policy functions need raw gator_dir
    gator_dir = paths.gator_root

    # --- Generation check ---
    repo_gen = 0
    version_file = gator_dir / ".gator-version"
    if version_file.exists():
        for line in version_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("generation:"):
                try:
                    repo_gen = int(line.split(":", 1)[1].strip())
                except ValueError:
                    pass

    if repo_gen < command_post_state["generation"]:
        result["findings"].append({
            "check": "generation",
            "severity": "drift",
            "message": f"Generation {repo_gen}, command post is {command_post_state['generation']}. Run gator update.",
        })

    # --- Policy sync check (new system) ---
    _policy_authoritative = False
    if _HAS_POLICY_STATUS:
        try:
            source, _ = _get_governance_source(gator_dir)
            if source:
                status = _compute_sync_state(gator_dir, source)
                state = status.get("state", "unknown")
                source_type = status.get("source_type")
                _policy_authoritative = state in ("synced", "behind", "diverged") or (
                    state == "no-cache" and source_type == "local"
                )

                if state == "behind":
                    result["findings"].append({
                        "check": "policy-behind",
                        "severity": "drift",
                        "message": "Policy cache is behind source. Run gator policy-status --sync.",
                    })
                elif state == "diverged":
                    result["findings"].append({
                        "check": "policy-diverged",
                        "severity": "drift",
                        "message": "Policy cache was edited locally — diverged from source. Run gator policy-status --sync to reset.",
                    })
                elif state == "no-cache" and _policy_authoritative:
                    result["findings"].append({
                        "check": "policy-no-cache",
                        "severity": "warn",
                        "message": "Policy not yet cached. Run gator policy-status --sync to materialize.",
                    })
                # synced → no finding (good state)
                # remote-only no-cache → not authoritative, old check handles it
        except Exception:
            pass  # Fall through to old check

    # --- Policy version check (old system, suppressed when new system is authoritative) ---
    if not _policy_authoritative:
        repo_policy = None
        cp_file = gator_dir / "command-post.md"
        if cp_file.exists():
            for line in cp_file.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("version:"):
                    repo_policy = line.split(":", 1)[1].strip()
                    break

        if command_post_state.get("git_failed"):
            result["findings"].append({
                "check": "policy-version",
                "severity": "warn",
                "message": "Could not read command post policy date (git failed). Policy comparison skipped.",
            })
        elif command_post_state["policy_date"] and repo_policy:
            if repo_policy < command_post_state["policy_date"]:
                result["findings"].append({
                    "check": "policy-version",
                    "severity": "drift",
                    "message": f"Policy version {repo_policy}, command post updated {command_post_state['policy_date']}. Run gator update.",
                })
        elif not repo_policy:
            result["findings"].append({
                "check": "policy-version",
                "severity": "warn",
                "message": "No policy version in command-post.md.",
            })

    # --- Hook presence ---
    hooks_dir = paths.scripts_dir / "hooks"
    has_hooks = hooks_dir.is_dir() and any(hooks_dir.iterdir())
    probe_dirs = _hook_probe_dirs(repo_path)
    pre_commit_installed = any(
        hooks_dir.is_dir() and (hooks_dir / "pre-commit").exists()
        for hooks_dir in probe_dirs
    )
    commit_msg_installed = any(
        hooks_dir.is_dir() and (hooks_dir / "commit-msg").exists()
        for hooks_dir in probe_dirs
    )

    if not has_hooks and not pre_commit_installed and not commit_msg_installed:
        # No hooks anywhere — full drift
        result["findings"].append({
            "check": "hooks",
            "severity": "drift",
            "message": "No governance hooks (sources or installed). Run gator update.",
        })
    else:
        if not has_hooks:
            # Installed but no sources — functional but fragile
            result["findings"].append({
                "check": "hook-sources",
                "severity": "warn",
                "message": "Hooks installed in the managed Git hook path but no sources in .gator/scripts/hooks/. Run gator update to add sources.",
            })
        if not pre_commit_installed or not commit_msg_installed:
            missing = []
            if not pre_commit_installed:
                missing.append("pre-commit")
            if not commit_msg_installed:
                missing.append("commit-msg")
            result["findings"].append({
                "check": "hook-installed",
                "severity": "drift",
                "message": f"Git hooks not installed: {', '.join(missing)}. Run gator update or gator gatorize.",
            })

    # --- Charter presence ---
    charters_dir = paths.charters_dir
    skip = {"_template.md", "README.md", "INDEX.md", ".gitkeep"}
    charter_count = 0
    if charters_dir.is_dir():
        charter_count = len([
            f for f in charters_dir.iterdir()
            if f.suffix == ".md" and f.name not in skip
        ])

    if charter_count == 0:
        result["findings"].append({
            "check": "charters",
            "severity": "warn",
            "message": "No charters. The governance loop requires at least one charter to be meaningful.",
        })

    # --- Commit_draft format check ---
    draft_file = paths.commit_draft
    if draft_file.exists():
        text = draft_file.read_text(encoding="utf-8", errors="replace")
        if not text.startswith("---"):
            result["findings"].append({
                "check": "commit-draft-format",
                "severity": "warn",
                "message": "commit_draft.md lacks YAML frontmatter. Run gator update to refresh template.",
            })

    # --- Constitution freshness ---
    # Compare repo constitution to template
    repo_constitution = paths.constitution
    if not repo_constitution.exists():
        result["findings"].append({
            "check": "constitution",
            "severity": "drift",
            "message": "No constitution.md found.",
        })

    # --- Branch check ---
    branch_out, branch_ok = git("branch", "--show-current", cwd=repo_path)
    if not branch_ok:
        result["findings"].append({
            "check": "branch",
            "severity": "warn",
            "message": "Could not read branch (git failed).",
        })
    else:
        branch = branch_out or "detached"
        if branch not in ("dev", "main", "master"):
            result["findings"].append({
                "check": "branch",
                "severity": "warn",
                "message": f"On branch '{branch}', expected 'dev'. May be mid-install or mid-feature.",
            })

    # --- Trailer presence (informational) ---
    raw, trailer_ok = git("log", "-1", "--format=%(trailers)", "dev", cwd=repo_path)
    if not trailer_ok:
        result["findings"].append({
            "check": "trailers",
            "severity": "warn",
            "message": "Could not read trailers (git failed).",
        })
    elif not raw or "Gator-" not in raw:
        result["findings"].append({
            "check": "trailers",
            "severity": "warn",
            "message": "No Gator-* trailers in latest dev commit. Commits made before hook installation.",
        })

    # --- Compute overall severity ---
    severities = [f["severity"] for f in result["findings"]]
    if "drift" in severities:
        result["severity"] = "drift"
    elif "warn" in severities:
        result["severity"] = "warn"
    else:
        result["severity"] = "ok"

    return result


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def print_drift_report(results, command_post_state):
    """Print formatted drift report."""
    print()
    print("  gator drift")
    policy_display = command_post_state['policy_date'] or ('error: git failed' if command_post_state.get('git_failed') else 'unknown')
    print(f"  command post: gen {command_post_state['generation']}, policy {policy_display}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print()

    drift_count = sum(1 for r in results if r["severity"] == "drift")
    warn_count = sum(1 for r in results if r["severity"] == "warn")
    ok_count = sum(1 for r in results if r["severity"] == "ok")

    for r in results:
        name = r["name"]
        sev = r["severity"]

        if sev == "ok":
            print(f"  ✓ {name} — current")
        elif sev == "warn":
            print(f"  ⚠ {name} — warnings")
        else:
            print(f"  ✗ {name} — DRIFT")

        for f in r["findings"]:
            if f["severity"] == "drift":
                marker = "✗"
            elif f["severity"] == "info":
                marker = "ℹ"
            else:
                marker = "⚠"
            print(f"    {marker} {f['check']}: {f['message']}")

        if not r["findings"]:
            print(f"    No findings.")

        print()

    # Summary
    print(f"  summary: {ok_count} current, {warn_count} warnings, {drift_count} drifted")
    if drift_count > 0:
        print(f"  action: run 'gator update' in drifted repos to align with command post")
    print()


def print_json_report(results, command_post_state):
    """Output drift report as JSON."""
    output = {
        "version": VERSION,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "command_post": command_post_state,
        "repos": results,
        "summary": {
            "total": len(results),
            "ok": sum(1 for r in results if r["severity"] == "ok"),
            "warn": sum(1 for r in results if r["severity"] == "warn"),
            "drift": sum(1 for r in results if r["severity"] == "drift"),
        },
    }
    print(json.dumps(output, indent=2))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    ensure_utf8_stdout()

    parser = argparse.ArgumentParser(
        description="Gator drift — policy drift detection across the fleet."
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON",
    )
    parser.add_argument(
        "--repo", "-r",
        help="Check a single repo by name",
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

    if args.repo:
        repos = [r for r in repos if r["name"] == args.repo]
        if not repos:
            print(f"  Error: repo '{args.repo}' not found in registry.", file=sys.stderr)
            sys.exit(1)

    # Read command post state
    cp_state = read_command_post_policy(command_post)

    # Check each repo
    results = [check_repo_drift(r, cp_state) for r in repos]

    if args.json:
        print_json_report(results, cp_state)
    else:
        print_drift_report(results, cp_state)


if __name__ == "__main__":
    main()
