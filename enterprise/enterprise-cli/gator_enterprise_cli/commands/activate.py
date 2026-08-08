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

# v2-first script discovery: shipped scripts live at
# `.gator/.includes/scripts/` in v2 layout, `.gator/scripts/` in v1.
# The plan's v2-only ratification (§ D-set) says v2 is authoritative,
# but the templates keep the v1 fallback so mixed-layout machines
# don't silently break during the transition. The old templates
# hardcoded the v1 path only, which meant every commit on a v2 repo
# hit `[ -f "$GATOR_SCRIPT" ] || exit 0` and governance silently
# no-op'd — exactly the failure mode Phase 5 §11 Change 2 corrects.
_GATOR_SCRIPT_RESOLVER = r'''
# Resolve pre-commit script — prefer v2 (.includes/scripts/), fall back
# to v1 (scripts/). Non-gatorized repos exit 0. TRIPWIRE: the v2-first
# order is load-bearing under the plan's v2-only ratification.
GATOR_SCRIPT=""
if [ -f ".gator/.includes/scripts/gator-pre-commit.py" ]; then
    GATOR_SCRIPT=".gator/.includes/scripts/gator-pre-commit.py"
elif [ -f ".gator/scripts/gator-pre-commit.py" ]; then
    GATOR_SCRIPT=".gator/scripts/gator-pre-commit.py"
fi
[ -n "$GATOR_SCRIPT" ] || exit 0
'''

PRE_COMMIT_HOOK = r'''#!/bin/sh
# Gator Enterprise — global pre-commit hook
# Installed by: gator-enterprise activate
''' + _GATOR_SCRIPT_RESOLVER + _PYTHON_RESOLVER + _MODE_LOOKUP + r'''
[ "$MODE" = "off" ] && exit 0
export GATOR_HOOK_MODE="$MODE"

"$PYTHON" "$GATOR_SCRIPT" --phase validate "$@"
'''

COMMIT_MSG_HOOK = r'''#!/bin/sh
# Gator Enterprise — global commit-msg hook
''' + _GATOR_SCRIPT_RESOLVER + _PYTHON_RESOLVER + _MODE_LOOKUP + r'''
[ "$MODE" = "off" ] && exit 0
export GATOR_HOOK_MODE="$MODE"

"$PYTHON" "$GATOR_SCRIPT" --phase trailers "$@"
'''

POST_COMMIT_HOOK = r'''#!/bin/sh
# Gator Enterprise — global post-commit hook
''' + _GATOR_SCRIPT_RESOLVER + _PYTHON_RESOLVER + _MODE_LOOKUP + r'''
[ "$MODE" = "off" ] && exit 0
export GATOR_HOOK_MODE="$MODE"

"$PYTHON" "$GATOR_SCRIPT" --phase cleanup "$@"

# Generate session block for the just-completed commit.
# TRANSITIONAL (per plan D10 OBSOLETE-FOR-TRANSCRIPTS-FIRST-MVP list):
# session-block generation is being retired post-MVP. Do NOT extend this
# block. The transcripts-first evidence path is `gator-enterprise
# transcripts pull` (operator-triggered), which reads the SAME snippets
# without needing per-commit block artifacts.
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
        # Fallback: repo-local script (plaintext v2 only) — v2-first path,
        # v1 fallback to match the pre-commit resolver's ordering.
        if [ "$BLOCK_GENERATED" = "0" ]; then
            BLOCK_SCRIPT=""
            if [ -f ".gator/.includes/scripts/gator-session-block.py" ]; then
                BLOCK_SCRIPT=".gator/.includes/scripts/gator-session-block.py"
            elif [ -f ".gator/scripts/gator-session-block.py" ]; then
                BLOCK_SCRIPT=".gator/scripts/gator-session-block.py"
            fi
            if [ -n "$BLOCK_SCRIPT" ]; then
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
    activate_parser.add_argument(
        "--yes", "-y", action="store_true",
        help=(
            "Skip the confirmation prompt when at-risk hooks are detected in "
            "known gatorized repos. Setting global core.hooksPath will cause "
            "these hooks to stop firing; use only after reviewing the printed "
            "at-risk-hook enumeration."
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


# ----------------------------------------------------------------------
# At-risk hook enumeration (Phase 5 §11 Change 1)
# ----------------------------------------------------------------------


# Non-`.sample` files in a repo's `.git/hooks/` are almost always
# something a human or a framework installed on purpose. Standard Git
# ships every default hook as `<name>.sample`; anything without that
# suffix is an active hook that will stop firing when `core.hooksPath`
# gets redirected. This is deliberately over-inclusive — Enterprise's
# job at activate time is to be honest about the blast radius, not to
# rank which hooks matter.
_HOOK_FRAMEWORK_MARKERS = (
    ".pre-commit-config.yaml",   # pre-commit.com Python framework
    ".pre-commit-hooks.yaml",    # provider-side config
    "lefthook.yml",              # Lefthook (Go)
    "lefthook.yaml",
    "husky.config.js",           # Husky (npm)
)


def _read_dashboard_repos() -> list[dict]:
    """Read ~/.gator/dashboard-repos.json. Returns [] on any error."""
    path = Path.home() / ".gator" / "dashboard-repos.json"
    if not path.exists():
        return []
    try:
        import json as _json
        data = _json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(data, dict):
        return data.get("repos", []) or []
    if isinstance(data, list):
        return data
    return []


def _enumerate_at_risk_hooks(repo_path: Path) -> dict:
    """Scan one repo for `.git/hooks/*` files that will stop firing under a global `core.hooksPath`.

    Returns a dict with:
      - path: str (the input, echoed back for the caller)
      - has_local_hookspath: bool (whether repo-local core.hooksPath is set;
        when True, the repo is immune to the global-hooksPath takeover
        and enumeration is informational)
      - hooks: list[{name, bytes, mtime_iso}] — active (non-.sample) files
        in .git/hooks/. Excludes .sample defaults + directories.
      - frameworks: list[str] — matched _HOOK_FRAMEWORK_MARKERS in repo root
    """
    result = {
        "path": str(repo_path),
        "has_local_hookspath": False,
        "hooks": [],
        "frameworks": [],
    }
    if not repo_path.exists() or not (repo_path / ".git").exists():
        return result

    # Check for repo-local core.hooksPath — if set, global hooksPath is
    # not consulted for this repo and the enumeration is informational.
    try:
        proc = subprocess.run(
            ["git", "config", "--local", "--get", "core.hooksPath"],
            cwd=str(repo_path),
            capture_output=True, text=True, timeout=5,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            result["has_local_hookspath"] = True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    hooks_dir = repo_path / ".git" / "hooks"
    if hooks_dir.exists() and hooks_dir.is_dir():
        import datetime as _dt
        for entry in sorted(hooks_dir.iterdir()):
            if not entry.is_file():
                continue
            if entry.name.endswith(".sample"):
                continue
            try:
                stat = entry.stat()
                result["hooks"].append({
                    "name": entry.name,
                    "bytes": stat.st_size,
                    "mtime_iso": _dt.datetime.fromtimestamp(
                        stat.st_mtime, tz=_dt.timezone.utc,
                    ).strftime("%Y-%m-%d"),
                })
            except OSError:
                continue

    for marker in _HOOK_FRAMEWORK_MARKERS:
        if (repo_path / marker).exists():
            result["frameworks"].append(marker)

    return result


def _warn_about_at_risk_hooks(
    repos: list[dict],
    *,
    assume_yes: bool = False,
    is_windows: bool = False,
    stream=None,
    prompt_fn=None,
) -> None:
    """Print at-risk-hook enumeration; block on confirmation unless --yes.

    On Linux/macOS this is a real blocking gate: when any repo has
    at-risk hooks and --yes was not passed, prompt for Y/n confirmation
    and sys.exit(1) on non-affirmative reply. On Windows the enumeration
    prints but does not block (base-gator's local core.hooksPath wins
    over global there).
    """
    stream = stream if stream is not None else sys.stderr
    scans = [_enumerate_at_risk_hooks(Path(r.get("path", ""))) for r in repos]
    # Only repos that WOULD have their hooks bypassed are "at risk".
    # A repo with local core.hooksPath keeps its hooks regardless.
    at_risk = [
        s for s in scans
        if (s["hooks"] or s["frameworks"]) and not s["has_local_hookspath"]
    ]

    if not at_risk:
        # Silent success — no need to spam the operator when the machine
        # has no gatorized repos or every repo is already protected.
        return

    print(
        "\n"
        "  Enterprise activate will take over the git-hook path on this machine\n"
        "  by setting `git config --global core.hooksPath ~/.gator/hooks`.\n"
        "  Git will consult that directory for every commit and will STOP\n"
        "  consulting each repo's `.git/hooks/*` entirely.\n\n"
        "  Enterprise's wrappers invoke base-gator's inner pre-commit script\n"
        "  as a delegate — so Gator's own governance behavior is PRESERVED.\n"
        "  Any OTHER hooks installed to `.git/hooks/*` in your repos will\n"
        "  STOP FIRING under Enterprise's global core.hooksPath. This includes:\n"
        "    - formatters (prettier, black, gofmt) wired to pre-commit\n"
        "    - non-Gator pre-commit frameworks (pre-commit.com, lefthook, husky)\n"
        "    - custom user hooks (any scripts operators wrote themselves)\n\n"
        f"  Scanned {len(scans)} known gatorized repo(s); {len(at_risk)} have at-risk hooks:",
        file=stream,
    )
    for scan in at_risk:
        print(f"\n  Repo: {scan['path']}", file=stream)
        if scan["hooks"]:
            print("    Custom hooks in .git/hooks/ that will stop firing:", file=stream)
            for hook in scan["hooks"]:
                print(
                    f"      - {hook['name']} ({hook['bytes']} bytes; last modified {hook['mtime_iso']})",
                    file=stream,
                )
        if scan["frameworks"]:
            print(
                f"    Non-Gator hook framework detected: {', '.join(scan['frameworks'])}",
                file=stream,
            )
        print(
            "    RECOMMENDATION: either move these hook responsibilities into\n"
            "    Gator's charter/lint layer, OR set repo-local core.hooksPath\n"
            "    BEFORE activating Enterprise\n"
            "    (`git config core.hooksPath .git/hooks`) so the repo keeps\n"
            "    consulting its own hook path.",
            file=stream,
        )

    if is_windows:
        print(
            "\n  Windows: base-gator's `gatorize` sets local core.hooksPath on\n"
            "  every gatorized repo, and Git prefers the local setting over the\n"
            "  global core.hooksPath this activate is about to set. The\n"
            "  enumeration above is informational; the hooks continue to fire\n"
            "  on gatorized repos. Non-gatorized repos with hooks may still be\n"
            "  affected — activate assumes you accept that trade.",
            file=stream,
        )
        return

    if assume_yes:
        print(
            "\n  --yes was passed; proceeding despite at-risk hooks above.",
            file=stream,
        )
        return

    prompt = prompt_fn or input
    try:
        reply = prompt("\n  Proceed with activate? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        reply = ""
    if reply not in ("y", "yes"):
        print("\n  Aborted by operator.", file=stream)
        sys.exit(1)


def _do_activate(args, client):
    """One-time machine activation."""
    home = Path.home()
    gator_dir = home / ".gator"
    hooks_dir = gator_dir / "hooks"
    enterprise_dir = gator_dir / "enterprise"
    policies_dir = enterprise_dir / "policies"

    # Enumerate at-risk hooks in known gatorized repos BEFORE setting
    # global core.hooksPath. On Linux/macOS this is a blocking prompt
    # unless --yes was passed (setting the global path stops the repo-
    # local hooks from firing). On Windows the enumeration is
    # informational only — base-gator's `gatorize` sets local
    # core.hooksPath on every repo it installs, and Git prefers the
    # local setting over the global, so those hooks keep firing.
    _warn_about_at_risk_hooks(
        _read_dashboard_repos(),
        # getattr fallback keeps legacy call sites that construct `args`
        # via SimpleNamespace (test scaffolding) working without a schema
        # update — argparse always supplies the attribute.
        assume_yes=getattr(args, "yes", False),
        is_windows=sys.platform == "win32",
    )

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
