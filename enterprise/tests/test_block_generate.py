"""Regression tests for block_generate.py — Finding #4 from the 2026-08-06
Enterprise Local Bring-Up (Phase 5).

Finding: the post-commit hook wrapper redirects this module's stderr via
`2>/dev/null` (to keep terminal output clean on every commit). That
suppression made real failures invisible during bring-up — session blocks
were silently not emitted and diagnosis required running the command
manually with stderr visible. Fix: structured diagnostic logging to
`~/.gator/diagnostics/block-gen.log` (bounded ~500 lines) on every
non-happy-path outcome, so silent failures leave machine-local evidence.

Tests cover:
- `_diag_log` writes properly-formatted entries and never raises
- `_diag_log_rotate` bounds file size and keeps the recent tail
- Main-flow branches (plaintext-delegate-failed, unknown-mode-fallback,
  encrypted-v2-gen-failed, encryption-failed) each emit a diagnostic
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

# Ensure gator_enterprise_cli is importable from source.
ENTERPRISE_CLI_ROOT = Path(__file__).resolve().parent.parent / "enterprise-cli"
if str(ENTERPRISE_CLI_ROOT) not in sys.path:
    sys.path.insert(0, str(ENTERPRISE_CLI_ROOT))

from gator_enterprise_cli import block_generate as bg


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


class TestDiagLog:
    def _log_path(self, home):
        return home / ".gator" / "diagnostics" / "block-gen.log"

    def test_creates_parent_dir_and_appends(self, isolated_home):
        bg._diag_log("a" * 12, "test-event", "hello")
        path = self._log_path(isolated_home)
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "event=test-event" in content
        assert "commit=aaaaaaaaaaaa" in content
        assert "'hello'" in content, (
            "message should be quoted (repr-style) so a multiline "
            "or control-char message stays on one line"
        )

    def test_multiple_entries_append(self, isolated_home):
        bg._diag_log("a" * 12, "first")
        bg._diag_log("b" * 12, "second")
        content = self._log_path(isolated_home).read_text(encoding="utf-8")
        lines = [l for l in content.splitlines() if l.strip()]
        assert len(lines) == 2
        assert "event=first" in lines[0]
        assert "event=second" in lines[1]

    def test_never_raises_on_unwritable_path(self, isolated_home, monkeypatch):
        """Diagnostic logging must be strictly best-effort — it can never
        break the hook flow, since introducing new failure modes to a
        function whose whole job is exposing hidden failures would be
        the opposite of what the fix is for."""
        def _explode(*a, **kw):
            raise OSError("simulated disk full")
        monkeypatch.setattr(bg, "_diag_log_path", _explode)
        # Must not raise
        bg._diag_log("a" * 12, "test-event", "hello")

    def test_truncates_long_messages(self, isolated_home):
        """Messages are capped to keep the log tidy — a stderr flood from
        a broken script shouldn't fill the log with one entry."""
        bg._diag_log("a" * 12, "test-event", "x" * 5000)
        content = self._log_path(isolated_home).read_text(encoding="utf-8")
        # One line, at most ~700 chars (timestamp + headers + capped msg)
        assert len(content.splitlines()) == 1
        assert len(content) < 1000


class TestDiagLogRotate:
    def test_no_op_when_below_trigger(self, isolated_home):
        path = isolated_home / ".gator" / "diagnostics" / "block-gen.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        # 100 lines — well under the 750-line trigger
        path.write_text("\n".join(f"line {i}" for i in range(100)) + "\n",
                        encoding="utf-8")
        before = path.read_text(encoding="utf-8")
        bg._diag_log_rotate(path)
        after = path.read_text(encoding="utf-8")
        assert before == after, "rotate ran below trigger threshold"

    def test_trims_to_last_max_lines(self, isolated_home):
        path = isolated_home / ".gator" / "diagnostics" / "block-gen.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        # 800 lines — over the 750 trigger, should trim to last 500
        path.write_text(
            "\n".join(f"line {i}" for i in range(800)) + "\n",
            encoding="utf-8",
        )
        bg._diag_log_rotate(path)
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == bg._DIAG_LOG_MAX_LINES
        # Last line preserved
        assert lines[-1] == "line 799"
        # Earliest kept is line (800 - 500) = 300
        assert lines[0] == "line 300"

    def test_never_raises_on_read_failure(self, isolated_home, tmp_path):
        # Path that doesn't exist and can't be opened for read
        nonexistent = tmp_path / "does-not-exist" / "block-gen.log"
        bg._diag_log_rotate(nonexistent)  # must not raise


class TestMainFlowLogging:
    """Verifies that each non-happy-path branch in main() and
    _generate_encrypted_block emits a diagnostic entry."""

    def _log_content(self, home):
        path = home / ".gator" / "diagnostics" / "block-gen.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def _sandbox_repo(self, tmp_path):
        """Build a minimal repo that block_generate can operate on."""
        repo = tmp_path / "repo"
        (repo / ".gator" / "scripts").mkdir(parents=True)
        (repo / ".gator" / "session-blocks").mkdir(parents=True)
        # A dummy script that block_generate delegates to. Content doesn't
        # matter — we mock subprocess.run in the tests below.
        (repo / ".gator" / "scripts" / "gator-session-block.py").write_text(
            "# stub\n", encoding="utf-8"
        )
        return repo

    def test_plaintext_delegate_failure_is_logged(
        self, isolated_home, tmp_path, monkeypatch
    ):
        repo = self._sandbox_repo(tmp_path)
        # No crypto-policy.json → mode defaults to "plaintext"

        commit = "c" * 40

        def stub_run(*args, **kwargs):
            return subprocess.CompletedProcess(
                args=args[0] if args else [],
                returncode=42,
                stdout="",
                stderr="simulated: transcript missing",
            )

        monkeypatch.setattr(bg.subprocess, "run", stub_run)
        monkeypatch.setattr(
            sys, "argv",
            ["block_generate", "--commit", commit, "--repo-root", str(repo)],
        )
        with pytest.raises(SystemExit) as exc:
            bg.main()
        assert exc.value.code == 42

        content = self._log_content(isolated_home)
        assert "event=plaintext-delegate-failed" in content
        assert "rc=42" in content
        assert "simulated: transcript missing" in content

    def test_unknown_crypto_mode_is_logged(
        self, isolated_home, tmp_path, monkeypatch
    ):
        repo = self._sandbox_repo(tmp_path)
        # Seed a crypto-policy with an unknown mode
        (isolated_home / ".gator" / "enterprise").mkdir(parents=True, exist_ok=True)
        (isolated_home / ".gator" / "enterprise" / "crypto-policy.json").write_text(
            json.dumps({"session_blocks": {"mode": "quantum"}}),
            encoding="utf-8",
        )

        commit = "d" * 40

        # Delegate succeeds — we're testing the "unknown mode fallback"
        # log entry, not the delegate failure log entry.
        def stub_run(*args, **kwargs):
            return subprocess.CompletedProcess(
                args=args[0] if args else [],
                returncode=0,
                stdout="", stderr="",
            )

        monkeypatch.setattr(bg.subprocess, "run", stub_run)
        monkeypatch.setattr(
            sys, "argv",
            ["block_generate", "--commit", commit, "--repo-root", str(repo)],
        )
        with pytest.raises(SystemExit) as exc:
            bg.main()
        assert exc.value.code == 0

        content = self._log_content(isolated_home)
        assert "event=unknown-crypto-mode-fallback" in content
        assert "quantum" in content
