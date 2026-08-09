"""repo init command — provision a local repo for Gator Enterprise governance.

Generates the .gator/ folder structure, installs hook scripts from the bundled
package, creates agent config files (CLAUDE.md, AGENTS.md), and auto-stages
everything. Optionally commits.
"""

import importlib.resources
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


# --- Templates ---

ORG_POLICY_MD = """# Org Policy

This repo is governed by Gator Enterprise.

Org policies are synced to your machine and available at:
  ~/.gator/enterprise/policies/

To update policies: run `gator-enterprise sync`
To view current policies: run `gator-enterprise policies list`

These policies are maintained by your organization's admin
and apply to all governed repos on this machine.
"""

CLAUDE_MD = """# Claude Code Instructions

This repo is governed by Gator Enterprise.

## Org Policies

Read `.gator/org-policy.md` for the pointer to organizational policies.
Follow all org policies when writing code in this repo.

Org policies are at `~/.gator/enterprise/policies/` on your machine.
Read them before making changes.
"""

AGENTS_MD = """# Agent Instructions

This repo is governed by Gator Enterprise.

Read `.gator/org-policy.md` for organizational policies.
Org policies are at `~/.gator/enterprise/policies/` on your machine.
Follow all org policies when writing code in this repo.
"""


def register(subparsers):
    """Register repo subcommand."""
    repo_parser = subparsers.add_parser("repo", help="Repository provisioning")
    repo_sub = repo_parser.add_subparsers(dest="repo_command")

    init_parser = repo_sub.add_parser("init", help="Provision a repo for Enterprise governance")
    init_parser.add_argument("path", nargs="?", default=".", help="Path to repo (default: current directory)")
    init_parser.add_argument("--mode", default="strict",
                            choices=["off", "evidence_only", "warning", "strict"],
                            help=(
                                "Hook enforcement mode (default: strict). "
                                "'strict' requires commit_draft.md on every commit "
                                "and blocks otherwise — commits explain themselves. "
                                "'warning' requires the same but downgrades failures "
                                "to warnings (useful for CI/bot repos that can't "
                                "respond to a block). 'evidence_only' captures "
                                "machine-generated evidence without requiring "
                                "commit_draft. 'off' disables governance entirely. "
                                "See docs for the tradeoffs."
                            ))
    init_parser.add_argument("--canonical-id", default=None,
                            help="Canonical repo identifier (default: derived from git remote)")
    init_parser.add_argument("--commit", action="store_true",
                            help="Automatically commit the provisioned files")
    init_parser.add_argument("--scripts-source", default=None,
                            help="Path to copy .gator/scripts/ from (default: bundled scripts)")

    upgrade_parser = repo_sub.add_parser("upgrade", help="Update hook scripts in an existing repo")
    upgrade_parser.add_argument("path", nargs="?", default=".", help="Path to repo (default: current directory)")
    upgrade_parser.add_argument("--commit", action="store_true", help="Automatically commit the updated scripts")


def handle(args, client):
    """Handle repo commands."""
    if args.repo_command == "init":
        _do_repo_init(args, client)
    elif args.repo_command == "upgrade":
        _do_repo_upgrade(args)


def _do_repo_init(args, client):
    """Provision a local repo for Enterprise governance."""
    repo_path = Path(args.path).resolve()

    # Verify it's a git repo
    git_dir = repo_path / ".git"
    if not git_dir.exists():
        print(f"Error: {repo_path} is not a git repository", file=sys.stderr)
        sys.exit(1)

    gator_dir = repo_path / ".gator"

    # Derive canonical identifier
    canonical_id = args.canonical_id
    if not canonical_id:
        canonical_id = _derive_canonical_id(repo_path)
    if not canonical_id:
        print("Error: cannot derive canonical repo identifier. Use --canonical-id", file=sys.stderr)
        sys.exit(1)

    print(f"Provisioning: {canonical_id}")
    print(f"Mode: {args.mode}")
    print()

    # Create .gator/ structure. Note: .gator/session-blocks/ is intentionally
    # NOT created here — evidence lives in Enterprise-managed storage (DB +
    # blob store), not in Git, per the transcripts-first MVP (2026-08-08).
    # See MVP plan §2 D2 OBSOLETE list.
    gator_dir.mkdir(exist_ok=True)
    (gator_dir / "session-snippets").mkdir(exist_ok=True)

    # Write repo-id
    repo_id_path = gator_dir / "repo-id"
    repo_id_path.write_text(canonical_id + "\n", encoding="utf-8")
    print(f"  Created: .gator/repo-id")

    # Write org-policy.md (thin pointer)
    org_policy_path = gator_dir / "org-policy.md"
    org_policy_path.write_text(ORG_POLICY_MD, encoding="utf-8")
    print(f"  Created: .gator/org-policy.md")

    # Install hook scripts
    scripts_dir = gator_dir / "scripts"
    if args.scripts_source:
        # Copy from explicit source
        source = Path(args.scripts_source)
        if not source.exists():
            print(f"Error: scripts source not found: {source}", file=sys.stderr)
            sys.exit(1)
        if scripts_dir.exists():
            shutil.rmtree(scripts_dir)
        shutil.copytree(source, scripts_dir)
        print(f"  Installed: .gator/scripts/ (from {source})")
    else:
        # Install from bundled package data
        _install_bundled_scripts(scripts_dir)

    # Write agent config files
    claude_md = repo_path / "CLAUDE.md"
    if not claude_md.exists():
        claude_md.write_text(CLAUDE_MD, encoding="utf-8")
        print(f"  Created: CLAUDE.md")
    else:
        print(f"  Exists: CLAUDE.md (keeping existing)")

    agents_md = repo_path / "AGENTS.md"
    if not agents_md.exists():
        agents_md.write_text(AGENTS_MD, encoding="utf-8")
        print(f"  Created: AGENTS.md")
    else:
        print(f"  Exists: AGENTS.md (keeping existing)")

    # Auto-stage everything
    print()
    _git_add(repo_path, [
        ".gator/",
        "CLAUDE.md",
        "AGENTS.md",
    ])
    print("  Staged: .gator/, CLAUDE.md, AGENTS.md")

    # Optionally commit
    if args.commit:
        result = subprocess.run(
            ["git", "commit", "-m", "Add Gator Enterprise governance"],
            cwd=str(repo_path),
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print("  Committed: Add Gator Enterprise governance")
        else:
            print(f"  Commit failed: {result.stderr.strip()}")
    else:
        print()
        print("Ready to commit:")
        print(f"  git commit -m 'Add Gator Enterprise governance'")
        print(f"  git push")

    # ALWAYS write local hook-policy intent first — this is what the global
    # hook wrapper reads at commit time, and it's the only way the wrapper
    # can honor `--mode X` for a repo that isn't yet tracked by Enterprise
    # (fresh repo, no git provider integration, air-gapped setup, etc.).
    # Without this, the wrapper's lookup misses and defaults to `strict`,
    # silently ignoring the requested mode — the exact bug this call fixes.
    # (See TRIPWIRE in scripts-enterprise.md.)
    _write_local_hook_policy_intent(canonical_id, args.mode)

    # Register hook policy with Enterprise (best-effort). If the server
    # doesn't yet know about the repo, that's fine — the local intent
    # written above keeps the first commit honoring the requested mode
    # until server-side registration succeeds and a subsequent `sync`
    # overwrites the local intent with the server's authoritative value.
    if client:
        server_registered = _register_hook_policy(client, canonical_id, args.mode)
        if not server_registered:
            print(
                f"  Local intent-mode written: {canonical_id} -> {args.mode} "
                f"(honored by hooks until server registration succeeds)"
            )
        # Sync local cache. With merge semantics (see _do_sync), the local
        # intent survives the sync when the repo is still server-unknown.
        from gator_enterprise_cli.commands.activate import _do_sync
        _do_sync(args, client)
    else:
        print(
            f"  Local intent-mode written: {canonical_id} -> {args.mode} "
            f"(no Enterprise client configured; hooks will honor local intent)"
        )


def _write_local_hook_policy_intent(canonical_id, mode):
    """Write requested mode to ~/.gator/enterprise/hook-policy.json so the
    global hook wrapper honors it even before/if server-side registration
    succeeds. The local file merges non-destructively with any prior state
    (server-synced entries and other local intents are preserved).

    See TRIPWIRE in scripts-enterprise.md — this write is what makes
    `repo init --mode X` produce a first commit that runs in mode X for
    repos not yet known to Enterprise. Without it, the wrapper's lookup
    misses and every commit runs in default `strict`.
    """
    home = Path.home()
    enterprise_dir = home / ".gator" / "enterprise"
    policy_path = enterprise_dir / "hook-policy.json"

    policy = {}
    if policy_path.exists():
        try:
            loaded = json.loads(policy_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                policy = loaded
        except (json.JSONDecodeError, OSError):
            policy = {}

    policy[canonical_id] = {"mode": mode}

    # Ensure parent exists. `activate` creates it, but a user could run
    # `repo init` before `activate` (misordered flow); handle it gracefully.
    enterprise_dir.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(json.dumps(policy, indent=2), encoding="utf-8")


def _register_hook_policy(client, canonical_id, mode):
    """Register the hook enforcement mode for this repo with Enterprise.

    Returns True if the server-side registration succeeded (repo was known
    and PUT completed); False otherwise (repo not yet tracked, network
    error, etc.). The local intent write in _write_local_hook_policy_intent
    ensures the requested mode is honored regardless of the return value.
    """
    try:
        # Find the repo in Enterprise by canonical identifier
        repos = client.get("/api/v1/repos")
        repo_id = None
        for r in repos:
            if r.get("canonical_identifier") == canonical_id:
                repo_id = r["id"]
                break

        if repo_id:
            client.put(f"/api/v1/hook-policy/{repo_id}", json={"mode": mode})
            print(f"  Registered hook policy: {canonical_id} -> {mode}")
            return True
        else:
            print(
                f"  Note: repo not yet tracked by Enterprise "
                f"(canonical_id={canonical_id})."
            )
            print(
                f"  Push the repo and run 'gator-enterprise providers reconcile' "
                f"to register it. Hooks will honor local intent-mode "
                f"({mode}) meanwhile."
            )
            return False
    except Exception as e:
        print(f"  Note: could not register hook policy with server ({e}).")
        print(f"  Hooks will honor local intent-mode ({mode}) meanwhile.")
        return False


def _install_bundled_scripts(scripts_dir):
    """Install hook scripts from the bundled package data."""
    scripts_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Python 3.9+ importlib.resources
        bundled = importlib.resources.files("gator_enterprise_cli") / "bundled_scripts"
        script_count = 0
        for item in bundled.iterdir():
            if item.name.endswith(".py") and item.name != "__init__.py":
                content = item.read_text(encoding="utf-8")
                (scripts_dir / item.name).write_text(content, encoding="utf-8")
                script_count += 1
        if script_count > 0:
            print(f"  Installed: .gator/scripts/ ({script_count} scripts from bundled package)")
        else:
            print(f"  Warning: no bundled scripts found in package")
    except Exception as e:
        print(f"  Warning: could not install bundled scripts ({e})")
        print(f"  Use --scripts-source to provide scripts manually")


def _git_add(repo_path, paths):
    """Stage files in the repo."""
    for path in paths:
        subprocess.run(
            ["git", "add", path],
            cwd=str(repo_path),
            capture_output=True,
        )


def _derive_canonical_id(repo_path):
    """Derive canonical repo identifier from git remote origin URL."""
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True, text=True, cwd=str(repo_path),
    )
    if result.returncode != 0:
        return None

    url = result.stdout.strip()

    # git@github.com:org/repo.git → github.com/org/repo
    if url.startswith("git@"):
        url = url.replace("git@", "").replace(":", "/")

    # https://github.com/org/repo.git → github.com/org/repo
    for prefix in ("https://", "http://"):
        if url.startswith(prefix):
            url = url[len(prefix):]

    # Remove trailing .git
    if url.endswith(".git"):
        url = url[:-4]

    # Remove trailing /
    url = url.rstrip("/")

    return url


def _do_repo_upgrade(args):
    """Upgrade hook scripts in an existing governed repo."""
    repo_path = Path(args.path).resolve()

    gator_dir = repo_path / ".gator"
    if not gator_dir.exists():
        print(f"Error: {repo_path} is not a governed repo (no .gator/ folder)", file=sys.stderr)
        sys.exit(1)

    scripts_dir = gator_dir / "scripts"
    print(f"Upgrading scripts: {repo_path}")
    print()

    _install_bundled_scripts(scripts_dir)

    # Auto-stage
    _git_add(repo_path, [".gator/scripts/"])
    print("  Staged: .gator/scripts/")

    if args.commit:
        result = subprocess.run(
            ["git", "commit", "-m", "Upgrade Gator Enterprise hook scripts"],
            cwd=str(repo_path),
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print("  Committed: Upgrade Gator Enterprise hook scripts")
        else:
            print(f"  Commit failed: {result.stderr.strip()}")
    else:
        print()
        print("Ready to commit:")
        print("  git commit -m 'Upgrade Gator Enterprise hook scripts'")
        print("  git push")
