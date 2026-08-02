#!/usr/bin/env python3
"""
gator policy-status — Policy sync status for governed repos.

Reports whether a repo's cached org policy matches its governance source.
Works with both local command posts and remote Git URLs.

Phase 1: no custom refs. Source truth is the last commit hash of
org-policy.md in the command post (local or remote).

Usage:
    python gator-command/scripts/gator-policy-status.py --path <repo>
    python gator-command/scripts/gator-policy-status.py --path <repo> --json
    python gator-command/scripts/gator-policy-status.py --path <repo> --sync
    python gator-command/scripts/gator-policy-status.py --path <repo> --init
    python gator-command/scripts/gator-policy-status.py --path <repo> --reinit

Modes:
    (default)   Report policy sync state
    --sync      Materialize/refresh the policy cache from source
    --init      Generate governance-source.json from existing thin link
    --reinit    Rebuild governance-source.json from thin link (repairs implicit-remote bug)
    --json      JSON output (combinable with other modes)

@reads: .gator/governance-source.json, .gator/policy-link.json,
        .gator/policy-cache/org-policy.md, .gator/command-post.md (fallback),
        command post org-policy.md (local or remote)
@writes: .gator/governance-source.json (--init, --reinit), .gator/policy-link.json (--sync),
         .gator/policy-cache/org-policy.md (--sync)
"""

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from gator_core import (
    get_version, find_gator_root, ensure_utf8_stdout,
    git, normalize_path, resolve_thin_link,
)

VERSION = get_version()

# The policy file path relative to the command post root
POLICY_REL_PATH = "gator-command/org-policy.md"


# ---------------------------------------------------------------------------
# Governance source resolution
# ---------------------------------------------------------------------------

def load_governance_source(gator_dir):
    """Load governance-source.json if it exists.

    Normalizes _local_path_hint into local_path for internal use.
    Returns dict or None.
    @reads: .gator/governance-source.json
    """
    src_file = gator_dir / "governance-source.json"
    if not src_file.exists():
        return None
    try:
        data = json.loads(src_file.read_text(encoding="utf-8"))
        # Normalize _local_path_hint → local_path for internal use
        if "_local_path_hint" in data and "local_path" not in data:
            hint = data["_local_path_hint"]
            if Path(normalize_path(hint)).is_dir():
                data["local_path"] = str(Path(normalize_path(hint)))
        return data
    except (OSError, json.JSONDecodeError):
        return None


def derive_governance_source(gator_dir):
    """Derive governance source from the existing thin link.

    Fallback for repos that don't have governance-source.json yet.
    Reads command-post.md to find the local path and any remote URL.

    @reads: .gator/command-post.md
    """
    cp_file = gator_dir / "command-post.md"
    if not cp_file.exists():
        return None

    try:
        text = cp_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    local_path = None
    remote_url = None

    for line in text.splitlines():
        if line.startswith("command-post-absolute:"):
            raw = line.split(":", 1)[1].strip().split("#")[0].strip()
            if raw:
                resolved = Path(normalize_path(raw))
                if resolved.is_dir():
                    local_path = str(resolved)

        elif line.startswith("command-post:") and not line.startswith("command-post-absolute:"):
            raw = line.split(":", 1)[1].strip()
            if raw and not local_path:
                resolved = (gator_dir.parent / raw).resolve()
                if resolved.is_dir():
                    local_path = str(resolved)

        elif line.startswith("remote:"):
            raw = line.split(":", 1)[1].strip().split("#")[0].strip()
            if raw:
                remote_url = raw

    if not local_path and not remote_url:
        return None

    source = {"policy_file": POLICY_REL_PATH}
    if local_path:
        source["local_path"] = local_path
    if remote_url:
        source["remote_url"] = remote_url

    return source


def get_governance_source(gator_dir):
    """Get governance source, trying governance-source.json first, then thin link.

    Returns (source_dict, is_derived) tuple.
    """
    source = load_governance_source(gator_dir)
    if source:
        return source, False

    derived = derive_governance_source(gator_dir)
    if derived:
        return derived, True

    return None, False


# ---------------------------------------------------------------------------
# Policy source queries
# ---------------------------------------------------------------------------

def query_local_policy(source):
    """Get the current policy commit and content from a local command post.

    Returns (commit_hash, content, error) tuple.
    @reads: local command post git log + file content
    """
    local_path = source.get("local_path")
    if not local_path or not Path(local_path).is_dir():
        return None, None, "local path not accessible"

    policy_file = source.get("policy_file", POLICY_REL_PATH)

    # Get the last commit hash for org-policy.md specifically
    commit_hash, ok = git(
        "log", "-1", "--format=%H", "--", policy_file,
        cwd=local_path,
    )
    if not ok or not commit_hash:
        return None, None, "git log failed for policy file"

    # Read the actual file content
    full_path = Path(local_path) / policy_file
    if not full_path.exists():
        return commit_hash, None, "policy file not found"

    try:
        content = full_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return commit_hash, None, str(e)

    return commit_hash, content, None


def fetch_remote_policy(source, repo_root):
    """Fetch the policy file from a remote command post.

    Uses `git fetch <url> HEAD --depth=1` into the fleet repo, then
    `git show FETCH_HEAD:<path>` to read the content. No named remote
    is created — FETCH_HEAD is temporary.

    Returns (content, error) tuple.
    @reads: remote Git URL via fetch + show
    """
    remote_url = source.get("remote_url")
    if not remote_url:
        return None, "no remote URL configured"

    policy_file = source.get("policy_file", POLICY_REL_PATH)

    try:
        # Shallow fetch HEAD into fleet repo's object store
        result = subprocess.run(
            ["git", "fetch", "--depth=1", remote_url, "HEAD"],
            capture_output=True, text=True, timeout=30,
            cwd=str(repo_root),
        )
        if result.returncode != 0:
            return None, f"fetch failed: {result.stderr.strip()}"

        # Read the policy file from FETCH_HEAD
        result = subprocess.run(
            ["git", "show", f"FETCH_HEAD:{policy_file}"],
            capture_output=True, text=True, timeout=10,
            cwd=str(repo_root),
        )
        if result.returncode != 0:
            return None, f"policy file not found in remote: {policy_file}"

        return result.stdout, None

    except subprocess.TimeoutExpired:
        return None, "remote fetch timed out"
    except Exception as e:
        return None, str(e)


# ---------------------------------------------------------------------------
# Policy link (provenance manifest)
# ---------------------------------------------------------------------------

def load_policy_link(gator_dir):
    """Load the existing policy-link.json manifest.

    @reads: .gator/policy-link.json
    """
    link_file = gator_dir / "policy-link.json"
    if not link_file.exists():
        return None
    try:
        return json.loads(link_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_policy_link(gator_dir, link_data):
    """Write the policy-link.json manifest.

    @writes: .gator/policy-link.json
    """
    link_file = gator_dir / "policy-link.json"
    link_file.write_text(
        json.dumps(link_data, indent=2) + "\n",
        encoding="utf-8",
    )


def sha256_of(content):
    """Compute SHA-256 hash of string content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Sync state computation
# ---------------------------------------------------------------------------

def compute_sync_state(gator_dir, source):
    """Determine the policy sync state for a repo.

    Returns a dict with state, details, and actionable info.
    """
    link = load_policy_link(gator_dir)
    cache_path = gator_dir / "policy-cache" / "org-policy.md"
    has_cache = cache_path.exists()

    result = {
        "state": "unknown",
        "source_type": None,
        "source_commit": None,
        "cached_commit": None,
        "cached_at": None,
        "has_cache": has_cache,
        "has_local_path": bool(source.get("local_path")),
        "has_remote_url": bool(source.get("remote_url")),
        "local_override": False,
        "error": None,
    }

    if link:
        result["cached_commit"] = link.get("source_commit")
        result["cached_at"] = link.get("cached_at")
        result["local_override"] = link.get("local_override", False)

    # Check for local override (cache was edited directly)
    if has_cache and link:
        try:
            cache_content = cache_path.read_text(encoding="utf-8", errors="replace")
            cache_hash = sha256_of(cache_content)
            if link.get("cache_sha256") and cache_hash != link["cache_sha256"]:
                result["state"] = "diverged"
                result["local_override"] = True
                return result
        except OSError:
            pass

    # Try local source first (fast, no network, per-file commit precision)
    if source.get("local_path"):
        commit, content, err = query_local_policy(source)
        if not err:
            result["source_type"] = "local"
            result["source_commit"] = commit
            if not link or not link.get("source_commit"):
                result["state"] = "no-cache" if not has_cache else "unknown"
            elif commit == link.get("source_commit"):
                result["state"] = "synced"
            else:
                result["state"] = "behind"
            return result
        # Local path failed — don't pollute result with stale error if remote works

    # Remote-only: status check cannot determine per-file freshness without
    # custom refs (Phase 2). Report cached state honestly.
    if source.get("remote_url"):
        if has_cache and link:
            result["source_type"] = "remote"
            result["state"] = "cached"  # Have cache, can't verify freshness without --sync
            return result
        elif not has_cache:
            result["source_type"] = "remote"
            result["state"] = "no-cache"
            return result

    # No source reachable
    if has_cache:
        result["state"] = "local-only"
    else:
        result["state"] = "no-source"
        result["error"] = "no local path or remote URL configured"

    return result


# ---------------------------------------------------------------------------
# Sync action
# ---------------------------------------------------------------------------

def sync_policy(gator_dir, source, repo_root):
    """Materialize the policy cache from source.

    Tries local source first (fast, per-file commit precision).
    Falls back to remote source (fetches file via git fetch + show).

    @reads: command post org-policy.md (local or remote)
    @writes: .gator/policy-cache/org-policy.md, .gator/policy-link.json
    """
    content = None
    commit = None
    source_type = None

    # Try local source first
    if source.get("local_path"):
        commit, content, err = query_local_policy(source)
        if not err and content:
            source_type = "local"

    # Fall back to remote source
    if content is None and source.get("remote_url"):
        content, err = fetch_remote_policy(source, repo_root)
        if err:
            return {"status": "error", "error": err}
        if content:
            source_type = "remote"
            # No per-file commit hash from remote — use content hash as identifier
            commit = "remote:" + sha256_of(content)[:16]

    if content is None:
        return {"status": "error", "error": "no source reachable"}

    # Write cache
    cache_dir = gator_dir / "policy-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "org-policy.md"
    cache_path.write_text(content, encoding="utf-8")

    # Write provenance manifest
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    link_data = {
        "source_commit": commit,
        "source_type": source_type,
        "policy_file": source.get("policy_file", POLICY_REL_PATH),
        "cached_at": now,
        "cache_path": ".gator/policy-cache/org-policy.md",
        "cache_sha256": sha256_of(content),
        "local_override": False,
    }

    if source.get("local_path"):
        link_data["source_path"] = source["local_path"]
    if source.get("remote_url"):
        link_data["remote_url"] = source["remote_url"]

    write_policy_link(gator_dir, link_data)

    return {"status": "ok", "commit": commit, "source_type": source_type, "cached_at": now}


# ---------------------------------------------------------------------------
# Init action
# ---------------------------------------------------------------------------

def init_governance_source(gator_dir, source, force=False):
    """Write governance-source.json from derived source info.

    Stores remote_url as the portable source (committable, works across
    machines) only if one was explicitly configured (e.g. in the registry
    or command-post.md). Stores local_path as a machine-local hint.

    Does NOT infer a remote URL from the command post's git origin —
    that would silently promote an unrelated upstream (e.g. a public
    GitHub repo) into fleet governance state.

    If force=True, overwrites an existing file (repair path for repos
    initialized before the implicit-remote bug was fixed).

    @writes: .gator/governance-source.json
    """
    src_file = gator_dir / "governance-source.json"
    if src_file.exists() and not force:
        return {"status": "exists", "message": "governance-source.json already exists"}

    # Structure: remote_url is the portable primary, local_path is a hint
    output = {"policy_file": source.get("policy_file", POLICY_REL_PATH)}
    if source.get("remote_url"):
        output["remote_url"] = source["remote_url"]
    if source.get("local_path"):
        output["_local_path_hint"] = source["local_path"]
        output["_local_path_note"] = "Machine-local — may not resolve on other machines"

    src_file.write_text(
        json.dumps(output, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"status": "ok" if not force else "repaired", "source": output}


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

_STATE_LABELS = {
    "synced":      ("Synced",       "Policy cache matches source"),
    "behind":      ("Behind",       "Source has newer policy"),
    "cached":      ("Cached",       "Remote-only — run --sync to verify freshness"),
    "diverged":    ("Diverged",     "Local cache was edited directly"),
    "no-cache":    ("No cache",     "Policy not yet materialized — run --sync"),
    "local-only":  ("Local only",   "No remote configured; cache present"),
    "offline":     ("Offline",      "Remote unreachable; using cached policy"),
    "unreachable": ("Unreachable",  "No source reachable and no cache"),
    "no-source":   ("No source",    "No governance source configured"),
    "unknown":     ("Unknown",      "Could not determine sync state"),
}


def print_status(status, source, is_derived):
    """Print human-readable policy status."""
    state = status["state"]
    label, description = _STATE_LABELS.get(state, (state, ""))

    print()
    print(f"  gator policy-status")
    print()
    print(f"  State:  {label}")
    print(f"          {description}")
    print()

    if source:
        if source.get("local_path"):
            print(f"  Source: {source['local_path']} (local)")
        if source.get("remote_url"):
            print(f"  Remote: {source['remote_url']}")
        if is_derived:
            print(f"  Note:   derived from thin link (run --init to persist)")

    print()

    if status.get("source_commit"):
        print(f"  Source commit:  {status['source_commit'][:12]}")
    if status.get("cached_commit"):
        print(f"  Cached commit: {status['cached_commit'][:12]}")
    if status.get("cached_at"):
        print(f"  Cached at:     {status['cached_at']}")
    if status.get("error"):
        print(f"  Error:         {status['error']}")

    print()


def print_json_status(status, source, is_derived):
    """Print JSON policy status."""
    output = {
        "version": VERSION,
        "governance_source": source,
        "governance_source_derived": is_derived,
        "policy_status": status,
    }
    print(json.dumps(output, indent=2))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ensure_utf8_stdout()

    parser = argparse.ArgumentParser(
        description="Gator policy-status — policy sync status for governed repos.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--path", "-p",
        help="Path to repo (default: current directory, walks up to find .gator/)",
    )
    parser.add_argument(
        "--sync", "-s", action="store_true",
        help="Materialize/refresh the policy cache from source",
    )
    parser.add_argument(
        "--init", action="store_true",
        help="Generate governance-source.json from existing thin link",
    )
    parser.add_argument(
        "--reinit", action="store_true",
        help="Rebuild governance-source.json from thin link (repairs implicit-remote bug)",
    )
    parser.add_argument(
        "--json", "-j", action="store_true",
        help="JSON output",
    )
    args = parser.parse_args()

    # Find repo root
    repo_root = find_gator_root(args.path)
    if not repo_root:
        print("  Error: no .gator/ found. Run from a gatorized repo.", file=sys.stderr)
        sys.exit(1)

    gator_dir = repo_root / ".gator"

    # --reinit: rebuild governance-source.json from thin link (repair path)
    # Must re-derive from command-post.md, not from the existing (possibly
    # corrupted) governance-source.json.
    if args.reinit:
        derived = derive_governance_source(gator_dir)
        if not derived:
            msg = "no thin link (command-post.md) found — cannot reinit"
            if args.json:
                print(json.dumps({"error": msg}))
            else:
                print(f"  Error: {msg}")
            sys.exit(1)
        result = init_governance_source(gator_dir, derived, force=True)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            written = result.get("source", {})
            print(f"  Rebuilt .gator/governance-source.json")
            if written.get("remote_url"):
                print(f"    remote_url: {written['remote_url']}")
            else:
                print(f"    remote_url: (none — local-path only)")
            if written.get("_local_path_hint"):
                print(f"    local hint: {written['_local_path_hint']}")
        return

    # Get governance source
    source, is_derived = get_governance_source(gator_dir)

    if not source:
        if args.json:
            print(json.dumps({"version": VERSION, "error": "no governance source found"}))
        else:
            print()
            print("  gator policy-status")
            print()
            print("  No governance source found.")
            print("  This repo has no .gator/governance-source.json and no thin link.")
            print()
        sys.exit(1)

    # --init: persist governance-source.json
    if args.init:
        result = init_governance_source(gator_dir, source)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result["status"] == "exists":
                print(f"  governance-source.json already exists.")
            else:
                written = result.get("source", {})
                print(f"  Created .gator/governance-source.json")
                if written.get("remote_url"):
                    print(f"    remote_url: {written['remote_url']}")
                if written.get("_local_path_hint"):
                    print(f"    local hint: {written['_local_path_hint']}")
        return

    # --sync: materialize policy cache
    if args.sync:
        result = sync_policy(gator_dir, source, repo_root)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result["status"] == "ok":
                print()
                print(f"  Policy cache synced")
                print(f"  Commit: {result['commit'][:12]}")
                print(f"  Cached: {result['cached_at']}")
                print()
            else:
                print(f"  Error: {result['error']}")
        return

    # Default: report status
    status = compute_sync_state(gator_dir, source)

    if args.json:
        print_json_status(status, source, is_derived)
    else:
        print_status(status, source, is_derived)


if __name__ == "__main__":
    main()
