"""
gator — unified CLI for Gator Command.

Dispatches to existing Gator scripts. This is the thin wrapper that makes
`pipx install gator-command` → `gator <command>` work.

For source-checkout and public-clone modes, scripts are resolved from the
filesystem relative to gator_runtime.py. For installed-package mode,
scripts are resolved from the package installation.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Script resolution
# ---------------------------------------------------------------------------

def _find_scripts_dir():
    """Find the Gator scripts directory.

    Resolution order:
    1. Package-bundled scripts (works for pip install and pipx install)
    2. Source checkout: gator-command/scripts/ relative to repo root
    3. Public clone: gator-engine/scripts/ relative to repo root
    """
    cli_dir = Path(__file__).resolve().parent

    # Installed package: scripts bundled as package data
    candidate = cli_dir / "scripts"
    if candidate.is_dir() and (candidate / "gator_core.py").exists():
        return candidate

    # Source checkout: cli.py is at src/gator_command/cli.py → repo root is ../../
    repo_root = cli_dir.parent.parent
    candidate = repo_root / "gator-command" / "scripts"
    if candidate.is_dir() and (candidate / "gator_core.py").exists():
        return candidate

    # Public clone: gator-engine/scripts/
    candidate = repo_root / "gator-engine" / "scripts"
    if candidate.is_dir() and (candidate / "gator_core.py").exists():
        return candidate

    return None


def _run_script(scripts_dir, script_name, args):
    """Run a Gator script by name, forwarding arguments."""
    script_path = scripts_dir / script_name
    if not script_path.exists():
        print(f"  Error: script not found: {script_name}", file=sys.stderr)
        print(f"  Looked in: {scripts_dir}", file=sys.stderr)
        sys.exit(1)
    result = subprocess.run(
        [sys.executable, str(script_path)] + args,
    )
    sys.exit(result.returncode)


# ---------------------------------------------------------------------------
# Command definitions
# ---------------------------------------------------------------------------

COMMANDS = {
    "version":    ("gator-version.py",       "Show Gator version"),
    "gatorize":   ("gatorize.py",            "Install or upgrade Gator in a repo"),
    "update":     ("gator-update.py",        "Refresh templates and hooks"),
    "init":       ("gator-init.py",          "Run session-opening procedure"),
    "pulse":      ("gator-pulse.py",         "Generate strategic operations brief"),
    "dashboard":  ("gator-dashboard.py",     "Start the governance dashboard"),
    "kill":       ("gator-kill.py",          "Kill Gator processes (dashboard, ...)"),
    "hook":       ("gator-hook.py",          "Dispatch a governance hook via the runtime resolver"),
    "loop":       ("gator-loop.py",          "Run a governed planning loop"),
    "enterprise": ("gator-enterprise.py",    "Manage Enterprise capability (setup, status, sync, ...)"),
    "state":      ("gator-state.py",         "Report repo state (constitution drift, native agent files)"),
    "charters":   ("gator-charters.py",      "Report charter health (read-only)"),
    "integration": ("gator-integration.py",  "Show or remove Gator's connection to AI tools on this machine"),
}

# Verbs that never connect the machine's AI tools: `hook` runs inside every
# vendor session (hot path), and `integration` must not re-add what
# `remove` removes.
NO_ENSURE_VERBS = frozenset({"hook", "integration"})


def _ensure_machine_integration(scripts_dir):
    """Connect Gator to the AI tools installed on this machine.

    Idempotent and cheap (a few small JSON reads; writes only on change).
    Output goes to stderr only, so `--json` stdout stays parseable, and no
    failure ever changes the command's exit code.
    `GATOR_NO_VENDOR_INTEGRATION=1` skips it.
    """
    if os.environ.get("GATOR_NO_VENDOR_INTEGRATION") == "1":
        return
    try:
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        import machine_integration
        result = machine_integration.ensure()
        lines = result["messages"] + result["problems"]
    except Exception as exc:  # noqa: BLE001 — never block the command
        lines = [f"Gator: vendor integration skipped ({type(exc).__name__}: {exc})"]
    for line in lines:
        print(line, file=sys.stderr)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="gator",
        description="Gator — Git-native governance for AI-assisted engineering",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  gator --explain        Orient an AI session (what Gator is, where you are)\n"
            "  gator version          Show installed version\n"
            "  gator init             Start a governed session\n"
            "  gator dashboard        Launch the governance dashboard\n"
            "  gator pulse            Generate the strategic operations brief\n"
            "  gator charters report  Report charter health (add --json for JSON)\n"
            "  gator enterprise       Manage Enterprise capability\n"
        ),
    )
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"%(prog)s {_get_version()}",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="orient an AI session: what Gator is, which documents to read, and where you are",
    )

    sub = parser.add_subparsers(dest="command")
    for cmd_name, (_, help_text) in COMMANDS.items():
        sub.add_parser(cmd_name, help=help_text, add_help=False)

    args, remaining = parser.parse_known_args()

    if args.explain:
        scripts_dir = _find_scripts_dir()
        if not scripts_dir:
            print("  Error: Gator scripts directory not found.", file=sys.stderr)
            sys.exit(1)
        _ensure_machine_integration(scripts_dir)
        _run_script(scripts_dir, "gator-explain.py", [])

    if not args.command:
        parser.print_help()
        sys.exit(0)

    scripts_dir = _find_scripts_dir()
    if not scripts_dir:
        print("  Error: Gator scripts directory not found.", file=sys.stderr)
        print("  Run from a Gator checkout, or install with: pipx install gator-command", file=sys.stderr)
        sys.exit(1)

    if args.command not in NO_ENSURE_VERBS:
        _ensure_machine_integration(scripts_dir)

    script_name, _ = COMMANDS[args.command]
    _run_script(scripts_dir, script_name, remaining)


def _get_version():
    """Get version from the package's single-source version resolver."""
    try:
        from gator_command import __version__
        return __version__
    except ImportError:
        return "unknown"


if __name__ == "__main__":
    main()
