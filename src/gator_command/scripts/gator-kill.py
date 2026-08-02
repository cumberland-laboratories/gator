#!/usr/bin/env python3
"""
gator kill — kill Gator-related processes.

Subcommands:
  gator kill dashboard    Kill running Gator Dashboard process(es)

Motivated by an operational failure mode: when the Dashboard restarts itself
during self-upgrade or when it's launched in the background (no visible
terminal, e.g. from a spawned helper), stale Dashboard processes accumulate.
The port scanner grabs 8420-8429 sequentially, so a stale process on 8420
forces the fresh launch to a higher port — and the user's browser is still
talking to the stale one. Symptoms: env-var overrides don't take effect,
in-flight code changes appear ignored, "Add Repository" scans yesterday's
roots.

Structured to invite more `gator kill <target>` subverbs later (loop,
enforcer, etc.) without restructuring the CLI.
"""

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from gator_core import ensure_utf8_stdout


DASHBOARD_MARKER = "gator-dashboard.py"
DASHBOARD_PORT_RANGE = range(8420, 8430)


# ── process discovery ─────────────────────────────────────────────────────────

def find_dashboard_processes():
    """Return a list of dicts describing running gator-dashboard.py processes.

    Each dict contains:
        pid:     int — the process ID
        cmdline: str — the full command line (for display / debugging)
        port:    int or None — the port it's listening on (best-effort;
                 populated when netstat/lsof can resolve it, None otherwise).

    Cross-platform: Windows uses tasklist + netstat via subprocess; Unix uses
    pgrep + lsof. Empty list on any failure (missing tools, timeouts).
    """
    if sys.platform == "win32":
        procs = _find_dashboards_windows()
    else:
        procs = _find_dashboards_unix()

    port_map = _port_map()
    for p in procs:
        p["port"] = port_map.get(p["pid"])
    return procs


def _find_dashboards_windows():
    """Windows process discovery via wmic (deprecated but still shipping)."""
    try:
        result = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'",
             "get", "processid,commandline", "/format:list"],
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []
    return _parse_wmic_output(result.stdout)


def _parse_wmic_output(text):
    """Parse wmic /format:list output. Testable in isolation.

    Uses "next CommandLine= starts a new record" as the boundary, not blank
    lines. wmic emits `\\r\\r\\n` line endings on Windows which Python's text
    mode converts to double-blank lines — using blank lines as boundaries
    would end each record before the ProcessId line lands.
    """
    procs = []
    current = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("CommandLine="):
            # Flush the previous record before starting the next
            if _is_dashboard(current):
                procs.append(current)
            current = {"cmdline": line[len("CommandLine="):]}
        elif line.startswith("ProcessId="):
            try:
                current["pid"] = int(line[len("ProcessId="):])
            except ValueError:
                pass
    # Flush the final record
    if _is_dashboard(current):
        procs.append(current)
    return procs


def _is_dashboard(proc_dict):
    """A parsed process dict is a dashboard iff it has both pid and cmdline
    containing the DASHBOARD_MARKER."""
    return (
        "pid" in proc_dict
        and proc_dict.get("cmdline")
        and DASHBOARD_MARKER in proc_dict["cmdline"]
    )


def _find_dashboards_unix():
    """Unix process discovery via pgrep -af."""
    try:
        result = subprocess.run(
            ["pgrep", "-af", DASHBOARD_MARKER],
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []
    return _parse_pgrep_output(result.stdout)


def _parse_pgrep_output(text):
    """Parse pgrep -af output (one 'PID cmdline' per line). Testable."""
    procs = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pid_str, cmdline = line.split(None, 1)
            procs.append({"pid": int(pid_str), "cmdline": cmdline})
        except ValueError:
            continue
    return procs


# ── port discovery ────────────────────────────────────────────────────────────

def _port_map():
    """Return {pid: port} for LISTENING sockets in the dashboard port range.

    Cross-platform. Falls back to {} on missing tools.
    """
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, text=True, timeout=10,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return {}
        return _parse_netstat_windows(result.stdout)
    else:
        try:
            result = subprocess.run(
                ["lsof", "-nP", "-i", "TCP", "-sTCP:LISTEN"],
                capture_output=True, text=True, timeout=10,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return {}
        return _parse_lsof_output(result.stdout)


def _parse_netstat_windows(text):
    """Parse `netstat -ano` output. Windows-style columns."""
    port_map = {}
    for line in text.splitlines():
        line = line.strip()
        if "LISTENING" not in line:
            continue
        # Format: "TCP    127.0.0.1:8420    0.0.0.0:0    LISTENING    12345"
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            pid = int(parts[-1])
            addr = parts[1]
            if ":" not in addr:
                continue
            port = int(addr.rsplit(":", 1)[1])
            if port in DASHBOARD_PORT_RANGE:
                port_map[pid] = port
        except (ValueError, IndexError):
            continue
    return port_map


def _parse_lsof_output(text):
    """Parse `lsof -nP -i TCP -sTCP:LISTEN` output. Unix-style columns."""
    port_map = {}
    lines = text.splitlines()
    if not lines:
        return port_map
    # First line is the header; skip it
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 9:
            continue
        try:
            pid = int(parts[1])
            # NAME column (last useful field) — e.g. "127.0.0.1:8420 (LISTEN)"
            # or just "127.0.0.1:8420" depending on the lsof version.
            for part in parts[8:]:
                if ":" not in part:
                    continue
                port_str = part.rsplit(":", 1)[1].split()[0]
                try:
                    port = int(port_str)
                    if port in DASHBOARD_PORT_RANGE:
                        port_map[pid] = port
                        break
                except ValueError:
                    continue
        except (ValueError, IndexError):
            continue
    return port_map


# ── kill ──────────────────────────────────────────────────────────────────────

def kill_process(pid):
    """Kill a process by PID. Returns True on success, False otherwise.

    Windows uses `taskkill /F` (SIGKILL-equivalent). Unix sends SIGTERM.
    Both return False on missing process / permission denied / any error.
    """
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                capture_output=True, text=True, timeout=5,
            )
            return result.returncode == 0
        else:
            os.kill(pid, signal.SIGTERM)
            return True
    except (subprocess.TimeoutExpired, ProcessLookupError,
            PermissionError, OSError):
        return False


# ── command handlers ──────────────────────────────────────────────────────────

def _format_proc_line(p):
    """One-line human-readable summary of a dashboard process."""
    port = p.get("port")
    port_str = f"port {port}" if port else "port unknown"
    return f"    PID {p['pid']} — {port_str}"


def cmd_dashboard_kill(args):
    """Handle `gator kill dashboard [--all | --port N | --dry-run]`.

    Default (no flag): list running processes with usage hint — safe default.
    --all: kill every dashboard process.
    --port N: kill only the one on port N.
    --dry-run: with --all or --port, list targets without killing.
    """
    procs = find_dashboard_processes()

    if not procs:
        print("  No gator-dashboard.py processes found.")
        return 0

    if args.port is not None:
        targets = [p for p in procs if p.get("port") == args.port]
        if not targets:
            print(f"  No dashboard process found on port {args.port}.")
            print(f"  Found {len(procs)} dashboard process(es) on other ports:")
            for p in procs:
                print(_format_proc_line(p))
            return 1
    elif args.all:
        targets = procs
    else:
        # Safe default: list what's out there, don't kill
        print(f"  Found {len(procs)} gator-dashboard.py process(es):")
        for p in procs:
            print(_format_proc_line(p))
        print()
        print("  To kill all:               gator kill dashboard --all")
        print("  To kill one by port:       gator kill dashboard --port <N>")
        print("  To preview without killing:")
        print("                             gator kill dashboard --all --dry-run")
        return 0

    if args.dry_run:
        print(f"  DRY RUN — would kill {len(targets)} process(es):")
        for p in targets:
            print(_format_proc_line(p))
        return 0

    print(f"  Killing {len(targets)} dashboard process(es)...")
    killed = 0
    failed = 0
    for p in targets:
        if kill_process(p["pid"]):
            print(f"    OK  PID {p['pid']}")
            killed += 1
        else:
            print(f"    !!  PID {p['pid']} — kill failed")
            failed += 1
    print()
    print(f"  Done: {killed} killed, {failed} failed.")
    return 0 if failed == 0 else 1


# ── entry point ──────────────────────────────────────────────────────────────

def main():
    ensure_utf8_stdout()

    parser = argparse.ArgumentParser(
        prog="gator kill",
        description="Kill Gator-related processes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  gator kill dashboard              list running dashboards\n"
            "  gator kill dashboard --all        kill every dashboard process\n"
            "  gator kill dashboard --port 8420  kill the dashboard on port 8420\n"
        ),
    )
    sub = parser.add_subparsers(dest="target")

    dashboard_parser = sub.add_parser(
        "dashboard",
        help="Kill running Gator Dashboard process(es)",
    )
    # --all and --port are mutually exclusive selectors. Enforcing at the
    # argparse layer surfaces the conflict as a usage error, not as silent
    # precedence (which was the pre-remediation behavior).
    selector = dashboard_parser.add_mutually_exclusive_group()
    selector.add_argument(
        "--all", action="store_true",
        help="Kill every gator-dashboard.py process",
    )
    selector.add_argument(
        "--port", type=int, metavar="N",
        help=f"Kill only the dashboard on port N "
             f"(N must be in {DASHBOARD_PORT_RANGE.start}-{DASHBOARD_PORT_RANGE.stop - 1})",
    )
    dashboard_parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be killed, don't actually kill "
             "(requires --all or --port)",
    )

    args = parser.parse_args()

    if not args.target:
        parser.print_help()
        sys.exit(0)

    if args.target == "dashboard":
        # --dry-run without a selector is meaningless — user asked for a
        # preview of something they haven't selected. Refuse rather than
        # silently list processes (which is what "no flag" does).
        if args.dry_run and not args.all and args.port is None:
            print("  Error: --dry-run requires --all or --port.", file=sys.stderr)
            print("  Run `gator kill dashboard` (no flags) to list running processes.",
                  file=sys.stderr)
            sys.exit(2)
        # --port must be in the range gator-dashboard actually scans.
        # Any other value can never match a dashboard, so refuse loudly.
        if args.port is not None and args.port not in DASHBOARD_PORT_RANGE:
            print(
                f"  Error: --port {args.port} is outside the dashboard range "
                f"({DASHBOARD_PORT_RANGE.start}-{DASHBOARD_PORT_RANGE.stop - 1}).",
                file=sys.stderr,
            )
            print("  The dashboard's port scanner never lands outside that range.",
                  file=sys.stderr)
            sys.exit(2)
        sys.exit(cmd_dashboard_kill(args))

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
