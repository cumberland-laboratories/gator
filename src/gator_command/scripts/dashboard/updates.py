"""Self-update operations for gator-command via pipx.

Checks PyPI for the latest version and upgrades via pipx.
"""

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path


PYPI_URL = "https://pypi.org/pypi/gator-command/json"


def _get_current_version():
    """Get the currently running CLI version via canonical resolver."""
    try:
        from gator_core import get_version
        return get_version()
    except ImportError:
        return ""


def _get_pypi_version():
    """Fetch the latest version from PyPI. Returns version string or None."""
    try:
        req = urllib.request.Request(PYPI_URL, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("info", {}).get("version", None)
    except Exception:
        return None


def check_for_updates():
    """Check current version against PyPI latest.

    Returns dict with current_version, latest_version, update_available.
    """
    current = _get_current_version()
    latest = _get_pypi_version()

    return {
        "current_version": current or "unknown",
        "latest_version": latest or "unknown",
        "update_available": bool(latest and current and latest != current),
    }


def upgrade_and_restart():
    """Upgrade gator-command via pipx, then restart the dashboard.

    Spawns a detached helper process that:
      1. Waits for this dashboard process to exit (releasing gator.exe)
      2. Runs pipx upgrade gator-command
      3. Relaunches the dashboard

    Then exits the current process so the file lock is released.
    """
    import time
    import textwrap

    # Determine how to relaunch after upgrade.
    # If running from pipx ('gator dashboard'), use 'gator' entry point.
    # If running from source ('python gator-dashboard.py'), use script path.
    dashboard_script = str(Path(__file__).resolve().parent.parent / "gator-dashboard.py")
    gator_exe = shutil.which("gator")
    if gator_exe:
        relaunch_cmd = json.dumps([gator_exe, "dashboard", "--no-open"])
    else:
        restart_args = sys.argv[1:]
        if "--no-open" not in restart_args:
            restart_args = restart_args + ["--no-open"]
        relaunch_cmd = json.dumps([sys.executable, dashboard_script] + restart_args)

    # Capture the port so the relaunched dashboard uses the same one
    port_arg = ""
    for i, arg in enumerate(sys.argv):
        if arg == "--port" and i + 1 < len(sys.argv):
            port_arg = f'"--port", "{sys.argv[i + 1]}",'

    # Build a small inline Python script for the detached helper
    helper_script = textwrap.dedent(f"""\
        import subprocess, sys, time, os
        # Wait for the old dashboard to exit
        time.sleep(3)
        # Run pipx upgrade
        result = subprocess.run(
            ["pipx", "upgrade", "gator-command"],
            capture_output=True, text=True, timeout=120,
        )
        # Write result for the frontend to read on reconnect
        log_path = os.path.join(os.path.expanduser("~"), ".gator", "upgrade-log.txt")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "w") as f:
            f.write(result.stdout or "")
            if result.stderr:
                f.write(result.stderr)
            f.write("\\nexit_code: " + str(result.returncode) + "\\n")
        # Relaunch dashboard
        subprocess.Popen({relaunch_cmd})
    """)

    # Spawn helper as a fully detached process
    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW

    subprocess.Popen(
        [sys.executable, "-c", helper_script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=creation_flags,
    )

    # Give the response time to flush, then exit
    time.sleep(1)
    os._exit(0)


def restart_server():
    """Restart the dashboard server process.

    Waits briefly for the HTTP response to flush, then replaces the
    current process with a fresh invocation of the same script + args.
    On Windows, os.execv spawns a new process and exits the old one.
    On Unix, it replaces the process in-place.
    """
    import time
    time.sleep(1)  # let the HTTP response reach the browser
    # Find the main dashboard script (gator-dashboard.py in scripts/)
    dashboard_script = str(Path(__file__).resolve().parent.parent / "gator-dashboard.py")
    # Add --no-open so the restarted server doesn't open a new browser tab
    restart_args = sys.argv[1:]
    if "--no-open" not in restart_args:
        restart_args = restart_args + ["--no-open"]
    args = [sys.executable, dashboard_script] + restart_args
    try:
        os.execv(sys.executable, args)
    except OSError:
        # Fallback: spawn and exit
        subprocess.Popen(args)
        os._exit(0)
