"""activate command — one-time machine setup for Gator Enterprise governance.

Creates ~/.gator/ structure, installs global git hooks, saves Enterprise config.
"""

import os
import stat
import subprocess
import sys
from pathlib import Path

from gator_enterprise_cli.output import print_kv


# --- Hook wrapper templates ---
#
# TRIPWIRE: Windows Git Bash has `python` and `py -3` but NOT `python3` as a
# real interpreter. Stock Windows installs an App Execution Alias for
# `python3` that points at a Microsoft Store stub — it "exists" on PATH,
# passes `[ -x ]` and `command -v` checks, but exits non-zero (typically 126
# "Permission denied" or 9009 "command not found") when actually invoked.
# Any hook wrapper that hardcodes `python3` OR trusts `command -v python3`
# without probing that it actually runs fails silently on the first commit
# on Windows, blocking every governed commit with an opaque error.
#
# All Python invocations in these templates MUST go through the resolved
# `$PYTHON` (via `_PYTHON_RESOLVER` below). The resolver:
#   1. Prefers `~/.gator/enterprise/cli-python-path` (written by activate,
#      always present after `gator-enterprise activate`)
#   2. Falls back to `command -v python3`, then `command -v python`
#   3. SANITY-PROBES each candidate with `-V` before accepting — a bare
#      `command -v` result is NOT trustworthy on Windows (see stub above)
#   4. Fails loudly with a message that names the Windows stub pitfall
#      when no candidate probes clean

_PYTHON_RESOLVER = r'''
# Resolve Python interpreter — prefer cli-python-path (written by activate);
# fall back to python3 then python on PATH. See TRIPWIRE in activate.py.
# Each candidate is sanity-probed with `-V` because "discoverable" ≠ "usable":
# on Windows the App Execution Alias for python3 passes `command -v`/`[ -x ]`
# but exits non-zero on invocation. Trusting `command -v` alone re-creates
# the exact bug this resolver was written to prevent.
_gator_py_ok() {
    [ -n "$1" ] && "$1" -V >/dev/null 2>&1
}
PYTHON=""
CLI_PYTHON_FILE="$HOME/.gator/enterprise/cli-python-path"
if [ -f "$CLI_PYTHON_FILE" ]; then
    CANDIDATE=$(cat "$CLI_PYTHON_FILE")
    _gator_py_ok "$CANDIDATE" && PYTHON="$CANDIDATE"
fi
if [ -z "$PYTHON" ]; then
    CANDIDATE=$(command -v python3 2>/dev/null)
    _gator_py_ok "$CANDIDATE" && PYTHON="$CANDIDATE"
fi
if [ -z "$PYTHON" ]; then
    CANDIDATE=$(command -v python 2>/dev/null)
    _gator_py_ok "$CANDIDATE" && PYTHON="$CANDIDATE"
fi
if [ -z "$PYTHON" ]; then
    echo "gator: no working Python interpreter found" >&2
    echo "  (probed: \$HOME/.gator/enterprise/cli-python-path, python3, python)" >&2
    echo "  each candidate must respond to '-V'. On Windows, python3 is often a" >&2
    echo "  Microsoft Store shim; ensure 'python' or 'py -3' is installed and on PATH." >&2
    exit 1
fi
'''

_MODE_LOOKUP = r'''
# Read repo identity and resolve hook enforcement mode from the local
# hook-policy.json. TRIPWIRE (see activate.py header): the policy path
# MUST be computed inside Python via `Path.home()`, NOT shell-interpolated
# from `$HOME`. On Git Bash for Windows, `$HOME` expands to `/c/Users/...`
# (an MSYS path) which Windows Python's `open()` cannot resolve, causing
# the mode lookup to silently fall through to 'strict' and defeat the
# whole Finding #3 fix. Repo-id crosses the shell/Python boundary via
# an env var (GATOR_REPO_ID), not string interpolation into the -c
# script — safer and quote-proof.
REPO_ID_FILE=".gator/repo-id"
MODE="strict"
if [ -f "$REPO_ID_FILE" ]; then
    export GATOR_REPO_ID=$(cat "$REPO_ID_FILE" | tr -d '[:space:]')
    MODE=$("$PYTHON" -c "
import json, os
from pathlib import Path
try:
    policy_path = Path.home() / '.gator' / 'enterprise' / 'hook-policy.json'
    p = json.loads(policy_path.read_text(encoding='utf-8'))
    print(p.get(os.environ.get('GATOR_REPO_ID', ''), {}).get('mode', 'strict'))
except Exception: print('strict')
" 2>/dev/null || echo "strict")
fi
'''

PRE_COMMIT_HOOK = r'''#!/bin/sh
# Gator Enterprise — global pre-commit hook
# Installed by: gator-enterprise activate
GATOR_SCRIPT=".gator/scripts/gator-pre-commit.py"
[ -f "$GATOR_SCRIPT" ] || exit 0
''' + _PYTHON_RESOLVER + _MODE_LOOKUP + r'''
[ "$MODE" = "off" ] && exit 0
export GATOR_HOOK_MODE="$MODE"

"$PYTHON" "$GATOR_SCRIPT" --phase validate "$@"
'''

COMMIT_MSG_HOOK = r'''#!/bin/sh
# Gator Enterprise — global commit-msg hook
GATOR_SCRIPT=".gator/scripts/gator-pre-commit.py"
[ -f "$GATOR_SCRIPT" ] || exit 0
''' + _PYTHON_RESOLVER + _MODE_LOOKUP + r'''
[ "$MODE" = "off" ] && exit 0
export GATOR_HOOK_MODE="$MODE"

"$PYTHON" "$GATOR_SCRIPT" --phase trailers "$@"
'''

POST_COMMIT_HOOK = r'''#!/bin/sh
# Gator Enterprise — global post-commit hook
GATOR_SCRIPT=".gator/scripts/gator-pre-commit.py"
[ -f "$GATOR_SCRIPT" ] || exit 0
''' + _PYTHON_RESOLVER + _MODE_LOOKUP + r'''
[ "$MODE" = "off" ] && exit 0
export GATOR_HOOK_MODE="$MODE"

"$PYTHON" "$GATOR_SCRIPT" --phase cleanup "$@"

# Generate session block for the just-completed commit
if [ "$MODE" != "off" ]; then
    COMMIT_SHA=$(git rev-parse HEAD 2>/dev/null)
    if [ -n "$COMMIT_SHA" ]; then
        # Prefer CLI interpreter (has cryptography for encrypted blocks);
        # fall back to repo-local script under resolved $PYTHON.
        BLOCK_GENERATED=0
        if [ -n "$CLI_PYTHON_FILE" ] && [ -f "$CLI_PYTHON_FILE" ]; then
            CLI_PYTHON=$(cat "$CLI_PYTHON_FILE")
            if [ -x "$CLI_PYTHON" ]; then
                "$CLI_PYTHON" -m gator_enterprise_cli.block_generate \
                    --commit "$COMMIT_SHA" --repo-root "$(pwd)" 2>/dev/null && BLOCK_GENERATED=1
            fi
        fi
        # Fallback: repo-local script (plaintext v2 only)
        if [ "$BLOCK_GENERATED" = "0" ]; then
            BLOCK_SCRIPT=".gator/scripts/gator-session-block.py"
            if [ -f "$BLOCK_SCRIPT" ]; then
                "$PYTHON" "$BLOCK_SCRIPT" generate --commit "$COMMIT_SHA" 2>/dev/null || true
            fi
        fi
        # Stage generated blocks (both v2 .json.gz and v3 .block.json)
        BLOCKS_DIR=".gator/session-blocks"
        if [ -d "$BLOCKS_DIR" ]; then
            git add "$BLOCKS_DIR"/*.json.gz "$BLOCKS_DIR"/*.block.json 2>/dev/null || true
        fi
    fi
fi
'''


def register(subparsers):
    """Register activate subcommand."""
    activate_parser = subparsers.add_parser(
        "activate",
        help="Activate Gator Enterprise on this machine (one-time setup)",
    )
    activate_parser.add_argument(
        "--force", action="store_true",
        help=(
            "Overwrite existing hooks and config. Does NOT rotate the machine "
            "keypair (use --regenerate-keys for that) and does NOT wipe "
            "hook-policy.json (local intent modes from `repo init` are preserved)."
        ),
    )
    activate_parser.add_argument(
        "--regenerate-keys", action="store_true",
        help=(
            "Rotate the machine keypair. Old encrypted session blocks become "
            "undecryptable and the new public key is re-registered with "
            "Enterprise. Rarely needed; use only when the private key is "
            "compromised or a fresh identity is required."
        ),
    )

    sync_parser = subparsers.add_parser(
        "sync",
        help="Sync hook policy and org policies from Enterprise",
    )


def handle(args, client):
    """Handle activate and sync commands."""
    if args.command == "activate":
        _do_activate(args, client)
    elif args.command == "sync":
        _do_sync(args, client)


def _do_activate(args, client):
    """One-time machine activation."""
    home = Path.home()
    gator_dir = home / ".gator"
    hooks_dir = gator_dir / "hooks"
    enterprise_dir = gator_dir / "enterprise"
    policies_dir = enterprise_dir / "policies"

    # Create directory structure
    hooks_dir.mkdir(parents=True, exist_ok=True)
    enterprise_dir.mkdir(parents=True, exist_ok=True)
    policies_dir.mkdir(parents=True, exist_ok=True)

    # Write hook wrappers
    hooks = {
        "pre-commit": PRE_COMMIT_HOOK,
        "commit-msg": COMMIT_MSG_HOOK,
        "post-commit": POST_COMMIT_HOOK,
    }
    for name, content in hooks.items():
        hook_path = hooks_dir / name
        if hook_path.exists() and not args.force:
            print(f"  Hook exists: {hook_path} (use --force to overwrite)")
        else:
            hook_path.write_text(content, encoding="utf-8")
            # Make executable
            hook_path.chmod(hook_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
            print(f"  Installed: {hook_path}")

    # Set global core.hooksPath
    current = subprocess.run(
        ["git", "config", "--global", "core.hooksPath"],
        capture_output=True, text=True,
    )
    target = str(hooks_dir)
    if current.stdout.strip() == target and not args.force:
        print(f"  core.hooksPath already set: {target}")
    else:
        subprocess.run(
            ["git", "config", "--global", "core.hooksPath", target],
            check=True,
        )
        print(f"  Set core.hooksPath: {target}")

    # Save Enterprise config
    import json
    config_path = enterprise_dir / "config.json"
    config_data = {
        "url": client._base,
        "activated_at": __import__("datetime").datetime.now().isoformat(),
    }
    config_path.write_text(json.dumps(config_data, indent=2), encoding="utf-8")
    print(f"  Config saved: {config_path}")

    # Initialize empty hook policy — ONLY when missing. --force does NOT
    # wipe existing policy; that would destroy locally-written intent modes
    # from `repo init --mode X` for repos not yet registered with Enterprise.
    # (See TRIPWIRE in scripts-enterprise.md.)
    policy_path = enterprise_dir / "hook-policy.json"
    if not policy_path.exists():
        policy_path.write_text("{}", encoding="utf-8")
        print(f"  Hook policy initialized: {policy_path}")

    # Generate machine keypair for envelope encryption.
    #
    # Key preservation contract (see TRIPWIRE in scripts-enterprise.md):
    # `--force` does NOT rotate keys. Rotation is a semantically distinct
    # operation that (a) invalidates every previously-encrypted session
    # block on this machine, (b) breaks the server's stored public key
    # until re-registered, (c) is almost never what someone re-running
    # activate for hook/config redeployment actually wants. Explicit
    # `--regenerate-keys` is the rotation gesture.
    keys_dir = enterprise_dir / "keys"
    keys_dir.mkdir(parents=True, exist_ok=True)
    org_keys_dir = enterprise_dir / "org-keys"
    org_keys_dir.mkdir(parents=True, exist_ok=True)

    private_key_path = keys_dir / "machine-private-key.pem"
    public_key_path = keys_dir / "machine-public-key.pem"

    if not private_key_path.exists() or args.regenerate_keys:
        rotation = args.regenerate_keys and private_key_path.exists()
        try:
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.hazmat.primitives import serialization

            private_key = rsa.generate_private_key(
                public_exponent=65537, key_size=2048,
            )
            private_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            ).decode("utf-8")
            public_pem = private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode("utf-8")

            private_key_path.write_text(private_pem, encoding="utf-8")
            public_key_path.write_text(public_pem, encoding="utf-8")
            if rotation:
                print(f"  Machine keypair ROTATED: {keys_dir}")
                print(f"    Previously-encrypted session blocks on this")
                print(f"    machine are no longer decryptable.")
            else:
                print(f"  Machine keypair generated: {keys_dir}")

            # Register public key with Enterprise
            machine_id = _get_machine_id()
            try:
                client.post("/api/v1/crypto/machine-keys", json={
                    "machine_id": machine_id,
                    "machine_label": _get_machine_label(),
                    "public_key_pem": public_pem,
                    "algorithm": "rsa-oaep",
                })
                print(f"  Machine key registered with Enterprise: {machine_id}")
            except Exception as e:
                print(f"  Machine key registration: not available ({e})")

        except ImportError:
            print(f"  Machine keypair: skipped (cryptography library not available)")
    else:
        print(f"  Machine keypair preserved: {keys_dir}")
        print(f"    (use --regenerate-keys to rotate — rarely needed)")

    # Record CLI interpreter path for post-commit hook
    cli_python_path = enterprise_dir / "cli-python-path"
    cli_python_path.write_text(sys.executable, encoding="utf-8")

    # Sync policies from Enterprise
    print()
    _do_sync(args, client)

    print()
    print("Gator Enterprise active on this machine.")
    print("All repos with .gator/ are now governed.")
    print()
    print("Next steps:")
    print("  gator-enterprise repo init <path>   — provision a repo")
    print("  gator-enterprise sync               — refresh policies")


def _get_machine_id():
    """Read or generate machine ID.

    The ~/.gator/machine-id file uses key: value format:
      id: <uuid>
      hostname: <hostname>
      label: <label>
      created: <timestamp>
    """
    machine_id_path = Path.home() / ".gator" / "machine-id"
    if machine_id_path.exists():
        for line in machine_id_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("id:"):
                return line.partition(":")[2].strip()

    # Generate in the canonical format (matches gator-machine-id.py)
    import platform
    import uuid as uuid_mod
    from datetime import datetime as dt, timezone as tz

    mid = str(uuid_mod.uuid4())
    hostname = platform.node()
    created = dt.now(tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    machine_id_path.parent.mkdir(parents=True, exist_ok=True)
    machine_id_path.write_text(
        f"id: {mid}\nhostname: {hostname}\nlabel: {hostname}\ncreated: {created}\n",
        encoding="utf-8",
    )
    return mid


def _get_machine_label():
    """Read machine label from ~/.gator/machine-id."""
    machine_id_path = Path.home() / ".gator" / "machine-id"
    if machine_id_path.exists():
        for line in machine_id_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("label:"):
                return line.partition(":")[2].strip()
    return os.environ.get("COMPUTERNAME", os.environ.get("HOSTNAME", ""))


def _do_sync(args, client):
    """Sync hook policy and org policies from Enterprise."""
    home = Path.home()
    enterprise_dir = home / ".gator" / "enterprise"
    policies_dir = enterprise_dir / "policies"

    if not enterprise_dir.exists():
        print("Error: run 'gator-enterprise activate' first", file=sys.stderr)
        sys.exit(1)

    import json

    # Sync hook policy — MERGE server view with local intent, don't replace.
    #
    # Rationale (see TRIPWIRE in scripts-enterprise.md): `repo init --mode X`
    # writes a local intent entry to hook-policy.json[canonical_id] so the
    # very first commit honors the requested mode, even when the repo isn't
    # yet server-registered. A wholesale replace here would wipe that intent
    # on every sync (which activate itself runs unconditionally at end),
    # producing the same silent-fall-through-to-strict UX the intent write
    # was designed to fix. Merge semantics: server wins for repos it knows
    # about; locally-intended entries for server-unknown repos are preserved.
    try:
        data = client.get("/api/v1/hook-policy")
        policy_path = enterprise_dir / "hook-policy.json"
        existing = {}
        if policy_path.exists():
            try:
                existing = json.loads(policy_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                existing = {}
        if not isinstance(existing, dict):
            existing = {}
        if not isinstance(data, dict):
            data = {}
        merged = {**existing, **data}  # server wins for overlapping keys
        policy_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        server_count = len(data)
        preserved = len(set(existing) - set(data))
        if preserved:
            print(
                f"  Hook policy synced: {server_count} repo(s) from server, "
                f"{preserved} local intent(s) preserved"
            )
        else:
            print(f"  Hook policy synced: {server_count} repo(s)")
    except Exception as e:
        print(f"  Hook policy: not available ({e})")

    # Sync org policies
    try:
        data = client.get("/api/v1/org-policies")
        policies = data if isinstance(data, list) else data.get("policies", [])
        policies_dir.mkdir(parents=True, exist_ok=True)
        for policy in policies:
            slug = policy.get("slug", "")
            content = policy.get("content", "")
            if slug and content:
                (policies_dir / f"{slug}.md").write_text(content, encoding="utf-8")
        print(f"  Org policies synced: {len(policies)} document(s)")
    except Exception as e:
        print(f"  Org policies: not available ({e})")

    # Sync crypto policy + org public key
    try:
        data = client.get("/api/v1/crypto/policy")
        crypto_path = enterprise_dir / "crypto-policy.json"
        crypto_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        # Write org public key if present
        org_key = data.get("org_key")
        if org_key and org_key.get("public_key_pem"):
            org_keys_dir = enterprise_dir / "org-keys"
            org_keys_dir.mkdir(parents=True, exist_ok=True)
            (org_keys_dir / "org-public-key.pem").write_text(
                org_key["public_key_pem"], encoding="utf-8"
            )
            print(f"  Crypto policy synced: mode={data.get('session_blocks', {}).get('mode', '?')}, key={org_key.get('key_id', '?')}")
        else:
            print(f"  Crypto policy synced: mode=plaintext (no org key)")
    except Exception as e:
        print(f"  Crypto policy: not available ({e})")
    except Exception as e:
        print(f"  Org policies: not available ({e})")
