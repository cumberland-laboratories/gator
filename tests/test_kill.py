"""
Tests for `gator kill` (gator-kill.py).

Tests the parseable helpers directly with mocked subprocess output. Actual
process killing / discovery is exercised via the module's helpers with fixture
strings; end-to-end (real process kill) is covered by the demo workspace's
manual verification and not in this suite (would require spawning real
subprocesses in the test host, which is flaky in CI).
"""

from pathlib import Path

import pytest

from conftest import load_script

SCRIPTS_DIR = Path(__file__).parent.parent / "src" / "gator_command" / "scripts"
kill_mod = load_script("gator-kill", search_dir=SCRIPTS_DIR)


class TestParseWmicOutput:
    """Windows: wmic /format:list output → list of dashboard process dicts."""

    def test_single_dashboard_process(self):
        text = (
            "\r\n"
            "CommandLine=C:\\Python313\\python.exe C:\\Users\\me\\gator-dashboard.py --no-open\r\n"
            "ProcessId=12345\r\n"
            "\r\n"
        )
        result = kill_mod._parse_wmic_output(text)
        assert len(result) == 1
        assert result[0]["pid"] == 12345
        assert "gator-dashboard.py" in result[0]["cmdline"]

    def test_multiple_dashboard_processes(self):
        text = (
            "CommandLine=python.exe gator-dashboard.py\r\n"
            "ProcessId=100\r\n"
            "\r\n"
            "CommandLine=python.exe gator-dashboard.py --port 8421\r\n"
            "ProcessId=200\r\n"
            "\r\n"
            "CommandLine=python.exe gator-dashboard.py --no-open\r\n"
            "ProcessId=300\r\n"
        )
        result = kill_mod._parse_wmic_output(text)
        assert [p["pid"] for p in result] == [100, 200, 300]

    def test_filters_non_dashboard_python_processes(self):
        text = (
            "CommandLine=python.exe some-other-script.py\r\n"
            "ProcessId=100\r\n"
            "\r\n"
            "CommandLine=python.exe gator-dashboard.py\r\n"
            "ProcessId=200\r\n"
            "\r\n"
            "CommandLine=python.exe gatorize.py .\r\n"
            "ProcessId=300\r\n"
        )
        result = kill_mod._parse_wmic_output(text)
        assert len(result) == 1
        assert result[0]["pid"] == 200

    def test_empty_output_returns_empty_list(self):
        assert kill_mod._parse_wmic_output("") == []

    def test_malformed_block_ignored(self):
        # missing ProcessId → block should be dropped, no crash
        text = (
            "CommandLine=python.exe gator-dashboard.py\r\n"
            "\r\n"
            "CommandLine=python.exe gator-dashboard.py\r\n"
            "ProcessId=500\r\n"
        )
        result = kill_mod._parse_wmic_output(text)
        assert len(result) == 1
        assert result[0]["pid"] == 500

    def test_wmic_double_blank_line_endings(self):
        """Regression guard: wmic emits `\\r\\r\\n` which Python's text mode
        converts to double-blank lines between fields. Parser must NOT treat
        blank lines as record boundaries, or every ProcessId gets orphaned.
        """
        text = (
            "\n\n\n"
            "CommandLine=python.exe gator-dashboard.py --no-open\n"
            "\n"
            "ProcessId=17200\n"
            "\n\n\n"
            "CommandLine=python.exe gator-dashboard.py --port 8425\n"
            "\n"
            "ProcessId=27608\n"
            "\n\n\n"
        )
        result = kill_mod._parse_wmic_output(text)
        assert len(result) == 2
        assert [p["pid"] for p in result] == [17200, 27608]


class TestParsePgrepOutput:
    """Unix: pgrep -af output → list of dashboard process dicts."""

    def test_single_process(self):
        text = "12345 /usr/bin/python3 /home/user/gator-dashboard.py --no-open\n"
        result = kill_mod._parse_pgrep_output(text)
        assert len(result) == 1
        assert result[0]["pid"] == 12345
        assert "gator-dashboard.py" in result[0]["cmdline"]

    def test_multiple_processes(self):
        text = (
            "100 python3 gator-dashboard.py\n"
            "200 python3 gator-dashboard.py --port 8421\n"
            "300 python3 gator-dashboard.py\n"
        )
        result = kill_mod._parse_pgrep_output(text)
        assert [p["pid"] for p in result] == [100, 200, 300]

    def test_empty_output(self):
        assert kill_mod._parse_pgrep_output("") == []

    def test_malformed_line_skipped(self):
        text = (
            "not-a-pid gator-dashboard.py\n"
            "200 python3 gator-dashboard.py\n"
        )
        result = kill_mod._parse_pgrep_output(text)
        assert len(result) == 1
        assert result[0]["pid"] == 200


class TestParseNetstatWindows:
    """Windows: netstat -ano → {pid: port} within dashboard port range."""

    def test_matches_listening_port_in_range(self):
        text = (
            "  Proto  Local Address     Foreign Address    State       PID\n"
            "  TCP    127.0.0.1:8420    0.0.0.0:0          LISTENING   12345\n"
        )
        result = kill_mod._parse_netstat_windows(text)
        assert result == {12345: 8420}

    def test_multiple_ports(self):
        text = (
            "  TCP    127.0.0.1:8420    0.0.0.0:0    LISTENING    100\n"
            "  TCP    127.0.0.1:8421    0.0.0.0:0    LISTENING    200\n"
            "  TCP    127.0.0.1:8425    0.0.0.0:0    LISTENING    300\n"
        )
        result = kill_mod._parse_netstat_windows(text)
        assert result == {100: 8420, 200: 8421, 300: 8425}

    def test_ignores_ports_outside_range(self):
        # 3000, 80, 8419, 8430, 22 — all outside 8420-8429 range
        text = (
            "  TCP    127.0.0.1:3000    0.0.0.0:0    LISTENING    100\n"
            "  TCP    127.0.0.1:80      0.0.0.0:0    LISTENING    200\n"
            "  TCP    127.0.0.1:8419    0.0.0.0:0    LISTENING    300\n"
            "  TCP    127.0.0.1:8430    0.0.0.0:0    LISTENING    400\n"
            "  TCP    127.0.0.1:22      0.0.0.0:0    LISTENING    500\n"
        )
        assert kill_mod._parse_netstat_windows(text) == {}

    def test_ignores_non_listening_connections(self):
        text = (
            "  TCP    127.0.0.1:8420    127.0.0.1:12345    ESTABLISHED  100\n"
            "  TCP    127.0.0.1:8421    0.0.0.0:0          LISTENING    200\n"
        )
        result = kill_mod._parse_netstat_windows(text)
        assert result == {200: 8421}


class TestIsDashboard:
    """Filter predicate for parsed process dicts."""

    def test_true_when_has_pid_and_marker(self):
        assert kill_mod._is_dashboard({
            "pid": 100,
            "cmdline": "python.exe gator-dashboard.py",
        })

    def test_false_when_no_marker(self):
        assert not kill_mod._is_dashboard({
            "pid": 100,
            "cmdline": "python.exe gatorize.py",
        })

    def test_false_when_no_pid(self):
        assert not kill_mod._is_dashboard({
            "cmdline": "python.exe gator-dashboard.py",
        })

    def test_false_when_no_cmdline(self):
        assert not kill_mod._is_dashboard({"pid": 100})

    def test_false_when_empty_dict(self):
        assert not kill_mod._is_dashboard({})


class TestFormatProcLine:
    """One-line human-readable summary."""

    def test_with_port(self):
        line = kill_mod._format_proc_line({"pid": 100, "port": 8420})
        assert "100" in line
        assert "8420" in line

    def test_without_port(self):
        line = kill_mod._format_proc_line({"pid": 100, "port": None})
        assert "100" in line
        assert "unknown" in line

    def test_port_missing_key(self):
        line = kill_mod._format_proc_line({"pid": 100})
        assert "100" in line
        assert "unknown" in line


class TestSelectorSemanticsAtCliBoundary:
    """The `gator kill dashboard` CLI has two selectors (--all, --port N) and
    one modifier (--dry-run). Boundary rules pinned here so the CLI can't
    silently accept nonsense combinations:

    - --all + --port together        → argparse mutual-exclusion error (exit 2)
    - --dry-run alone (no selector)  → explicit error, exit 2
    - --port outside 8420-8429       → explicit error, exit 2

    Uses subprocess to invoke the script directly so argparse's usage errors
    and post-parse validation are both exercised at the real CLI boundary.
    """

    import subprocess
    import sys

    SCRIPT = SCRIPTS_DIR / "gator-kill.py"

    def _run(self, *args):
        import subprocess
        import sys
        return subprocess.run(
            [sys.executable, str(self.SCRIPT), "dashboard", *args],
            capture_output=True, text=True, timeout=15,
        )

    def test_all_and_port_together_is_mutual_exclusion_error(self):
        result = self._run("--all", "--port", "8420")
        assert result.returncode == 2
        # argparse's own mutual-exclusion phrasing
        assert "not allowed with" in result.stderr.lower() or \
               "mutually exclusive" in result.stderr.lower()

    def test_dry_run_alone_rejected(self):
        result = self._run("--dry-run")
        assert result.returncode == 2
        assert "requires --all or --port" in result.stderr

    def test_dry_run_with_all_accepted(self):
        # Should NOT exit 2 — dry-run + selector is the intended combo.
        # Either 0 (nothing to preview) or 0 (previewed things). Not 2.
        result = self._run("--all", "--dry-run")
        assert result.returncode == 0

    def test_dry_run_with_port_in_range_accepted(self):
        result = self._run("--port", "8425", "--dry-run")
        # 0 or 1 both fine — 1 means "no dashboard on this port" which is
        # a runtime state, not a CLI-boundary error.
        assert result.returncode in (0, 1)

    def test_port_below_range_rejected(self):
        result = self._run("--port", "3000")
        assert result.returncode == 2
        assert "outside the dashboard range" in result.stderr

    def test_port_above_range_rejected(self):
        result = self._run("--port", "8430")
        assert result.returncode == 2
        assert "outside the dashboard range" in result.stderr

    def test_port_at_range_boundary_accepted(self):
        # Boundary: 8420 and 8429 must both be inside the range.
        for port in ("8420", "8429"):
            result = self._run("--port", port)
            # Should not error at the CLI boundary — either finds a process
            # or reports "no dashboard on that port" but doesn't reject.
            assert result.returncode in (0, 1), \
                f"port {port} should be accepted, got {result.returncode}: {result.stderr}"

    def test_no_flags_lists_and_returns_zero(self):
        """The safe default (no flags) must not error even when no processes
        are running — it just prints "no processes found" and exits 0.
        """
        result = self._run()
        assert result.returncode == 0
