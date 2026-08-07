"""Regression tests for activate.py's hook wrapper templates.

Covers the Windows-safe Python resolver added in commit 3afe7e3 (Windows
python3 → $PYTHON fix) and hardened in the follow-up (sanity-probe every
candidate before accepting).

Two test classes:
- TestHookTemplatesUseResolver — string-shape assertions on the constants
  (resolver present, no bare `python3` invocations that would bypass it)
- TestResolverBehavior — actually executes the resolver in an isolated
  bash shell with mocked HOME + PATH to prove each fallback branch works
  and the Windows-stub failure mode is correctly rejected. These tests
  require `bash` on PATH (Git Bash on Windows CI, /usr/bin/bash on Linux);
  they are skipped if bash is unavailable.

TRIPWIRE reminder from activate.py: on stock Windows, `python3` on PATH is
a Microsoft Store App Execution Alias stub that passes `command -v` and
`[ -x ]` but exits non-zero when invoked. Any resolver that trusts
`command -v python3` without probing execution recreates the original bug.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# Ensure gator_enterprise_cli is importable from source (same pattern as
# test_vendor_hooks.py).
ENTERPRISE_CLI_ROOT = Path(__file__).resolve().parent.parent / "enterprise-cli"
if str(ENTERPRISE_CLI_ROOT) not in sys.path:
    sys.path.insert(0, str(ENTERPRISE_CLI_ROOT))

from gator_enterprise_cli.commands.activate import (
    _PYTHON_RESOLVER,
    COMMIT_MSG_HOOK,
    POST_COMMIT_HOOK,
    PRE_COMMIT_HOOK,
)


BASH = shutil.which("bash")
requires_bash = pytest.mark.skipif(
    BASH is None, reason="bash not on PATH (needed to execute the resolver snippet)"
)


class TestHookTemplatesUseResolver:
    """String-shape assertions on the three deployed hook templates."""

    @pytest.mark.parametrize(
        "template,name",
        [
            (PRE_COMMIT_HOOK, "PRE_COMMIT_HOOK"),
            (COMMIT_MSG_HOOK, "COMMIT_MSG_HOOK"),
            (POST_COMMIT_HOOK, "POST_COMMIT_HOOK"),
        ],
    )
    def test_template_embeds_resolver(self, template, name):
        assert _PYTHON_RESOLVER in template, (
            f"{name} does not embed _PYTHON_RESOLVER — any Python invocation "
            f"in the template will hit a bare `python3` and break on Windows."
        )

    @pytest.mark.parametrize(
        "template,name",
        [
            (PRE_COMMIT_HOOK, "PRE_COMMIT_HOOK"),
            (COMMIT_MSG_HOOK, "COMMIT_MSG_HOOK"),
            (POST_COMMIT_HOOK, "POST_COMMIT_HOOK"),
        ],
    )
    def test_no_bare_python3_invocation(self, template, name):
        """The specific bug pattern we fixed: `python3 <thing>` invoking the
        interpreter with a script path, module, or inline code — bypassing
        the resolved `$PYTHON`. Comments and error-message mentions of the
        token `python3` are fine; only actual invocations are the bug.
        """
        BUG_PATTERNS = (
            'python3 "$',    # `python3 "$GATOR_SCRIPT"` — the original bug
            "python3 '",     # single-quoted arg
            "python3 -c",    # inline `python3 -c '...'`
            "python3 -m",    # module `python3 -m ...`
            "$(python3 ",    # command substitution
            "`python3 ",     # backtick substitution
        )
        offenders = []
        for i, line in enumerate(template.splitlines(), start=1):
            for pattern in BUG_PATTERNS:
                if pattern in line:
                    offenders.append((i, pattern, line))
        assert not offenders, (
            f"{name} has bare python3 invocation(s) that bypass $PYTHON:\n"
            + "\n".join(f"  line {i} matches {p!r}: {line}" for i, p, line in offenders)
        )

    def test_resolver_contains_sanity_probe(self):
        """The resolver MUST probe each candidate with `-V` before accepting.
        Trusting `command -v` alone is the exact bug the Windows fix and its
        follow-up were written to prevent.
        """
        assert "_gator_py_ok" in _PYTHON_RESOLVER, (
            "resolver missing the _gator_py_ok probe helper — Windows App "
            "Execution Alias stub for python3 will silently pass through."
        )
        assert '"$1" -V' in _PYTHON_RESOLVER, (
            "resolver's probe helper must invoke `-V` on candidates to prove "
            "they actually run; presence on PATH is not enough."
        )


@requires_bash
class TestResolverBehavior:
    """Execute the resolver in an isolated bash shell with mocked env.

    Each test writes `_PYTHON_RESOLVER` + a small echo suffix to a tempfile,
    then runs it under `bash` with a controlled HOME (for cli-python-path)
    and PATH (for python/python3 fallback). Asserts against the resolved
    `$PYTHON` echoed to stdout.
    """

    @pytest.fixture
    def run_resolver(self, tmp_path):
        script = tmp_path / "resolver_test.sh"
        script.write_text(
            _PYTHON_RESOLVER + '\necho "RESOLVED_PYTHON=$PYTHON"\n',
            encoding="utf-8",
        )

        # Discover the minimal PATH the resolver itself needs (for `cat`,
        # `command`, `[`, etc). On Git Bash for Windows this is `/usr/bin`;
        # on Linux/macOS bash builtins cover it but external `cat` still lives
        # under /usr/bin or /bin. Discover from the running bash so the tests
        # aren't hardcoded to any single environment.
        probe = subprocess.run(
            [BASH, "-c", "dirname \"$(command -v cat)\""],
            capture_output=True, text=True,
        )
        cat_dir = probe.stdout.strip() or "/usr/bin"

        def _run(home_dir: Path, path_override: str):
            # Prepend the caller's PATH override, then the discovered bash
            # utility dir. The override wins for `python`/`python3` lookups;
            # the utility dir keeps `cat` and friends available.
            full_path = f"{path_override}{os.pathsep}{cat_dir}"
            env = {
                "HOME": str(home_dir),
                "PATH": full_path,
                "SHELL": os.environ.get("SHELL", "/bin/sh"),
            }
            # On Windows, subprocess needs SYSTEMROOT for bash to start.
            if "SYSTEMROOT" in os.environ:
                env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
            return subprocess.run(
                [BASH, str(script)],
                capture_output=True,
                text=True,
                env=env,
            )

        return _run

    @staticmethod
    def _resolved_python(stdout: str) -> str:
        """Extract the RESOLVED_PYTHON= line's value from stdout. Returns
        empty string if not present."""
        for line in stdout.splitlines():
            if line.startswith("RESOLVED_PYTHON="):
                return line[len("RESOLVED_PYTHON="):]
        return ""

    @pytest.fixture
    def broken_python3(self, tmp_path):
        """A `python3` executable that exits 126 on any invocation — the
        Windows App Execution Alias stub failure mode.
        """
        bindir = tmp_path / "broken_bin"
        bindir.mkdir()
        stub = bindir / "python3"
        stub.write_text("#!/bin/sh\nexit 126\n", encoding="utf-8")
        stub.chmod(0o755)
        return bindir

    @pytest.fixture
    def working_python_shim(self, tmp_path):
        """A `python` shim that delegates to the current interpreter."""
        bindir = tmp_path / "working_bin"
        bindir.mkdir()
        real = sys.executable
        shim = bindir / "python"
        # Use shell to exec — on Windows, `real` has backslashes; quote it.
        shim.write_text(
            f'#!/bin/sh\nexec "{real}" "$@"\n', encoding="utf-8"
        )
        shim.chmod(0o755)
        return bindir

    def _empty_home(self, tmp_path) -> Path:
        home = tmp_path / "empty_home"
        home.mkdir()
        return home

    def _home_with_cli_python(self, tmp_path, interpreter: str) -> Path:
        home = tmp_path / "home_with_cli_python"
        (home / ".gator" / "enterprise").mkdir(parents=True)
        (home / ".gator" / "enterprise" / "cli-python-path").write_text(
            interpreter, encoding="utf-8"
        )
        return home

    def test_cli_python_path_present_and_working_wins(self, tmp_path, run_resolver):
        """Happy path: cli-python-path exists and its target runs -> resolver
        binds to it and never touches PATH fallbacks."""
        home = self._home_with_cli_python(tmp_path, sys.executable)
        # Deliberately empty user-supplied PATH so any fallback would fail;
        # the fixture still adds the bash utility dir so `cat` etc. work.
        result = run_resolver(home_dir=home, path_override="/nonexistent")
        assert result.returncode == 0, (
            f"expected success; got rc={result.returncode}, stderr={result.stderr!r}"
        )
        # Bash may report a POSIX-normalized version of sys.executable
        # (e.g. C:\Python313\python.exe -> /c/Python313/python.exe under
        # Git Bash). Compare on basename which is stable across mappings.
        resolved = self._resolved_python(result.stdout)
        assert resolved.endswith(Path(sys.executable).name), (
            f"expected resolved python to end with {Path(sys.executable).name!r}, "
            f"got {resolved!r}"
        )

    def test_broken_python3_falls_through_to_python(
        self, tmp_path, run_resolver, broken_python3, working_python_shim
    ):
        """The Windows App Execution Alias failure mode: `python3` on PATH
        exits non-zero. Resolver MUST reject it via -V probe and fall through
        to `python`."""
        # Combined PATH: broken python3 first, working python second
        path_override = f"{broken_python3}{os.pathsep}{working_python_shim}"
        home = self._empty_home(tmp_path)
        result = run_resolver(home_dir=home, path_override=path_override)
        assert result.returncode == 0, (
            f"expected fall-through success; got rc={result.returncode}, "
            f"stderr={result.stderr!r}"
        )
        resolved = self._resolved_python(result.stdout)
        # Must NOT be bound to the broken stub
        assert not resolved.endswith("python3"), (
            f"resolver bound to broken python3 stub instead of falling through: "
            f"{resolved!r}"
        )
        # Must be bound to a `python` (basename) in the working shim dir.
        # Basename compare survives Git Bash's Windows->POSIX path mapping.
        assert resolved.endswith("/python") or resolved.endswith("\\python"), (
            f"expected resolver to bind to `python` shim, got {resolved!r}"
        )
        # Extra guard: must be inside our working_python_shim dir, not some
        # other `python` that leaked in from ambient PATH.
        assert "working_bin" in resolved

    def test_only_broken_python3_available_exits_1(
        self, tmp_path, run_resolver, broken_python3
    ):
        """If the only candidate is the broken python3 stub, resolver must
        exit 1 with a clear message rather than silently binding to it."""
        home = self._empty_home(tmp_path)
        result = run_resolver(home_dir=home, path_override=str(broken_python3))
        assert result.returncode == 1
        assert "no working Python interpreter found" in result.stderr
        # Message should name the Windows pitfall
        assert "Microsoft Store" in result.stderr

    def test_no_candidates_at_all_exits_1(self, tmp_path, run_resolver):
        """No cli-python-path, no python3 on PATH, no python on PATH — the
        resolver must exit 1 loudly rather than continue with empty $PYTHON."""
        home = self._empty_home(tmp_path)
        result = run_resolver(home_dir=home, path_override="/nonexistent")
        assert result.returncode == 1
        assert "no working Python interpreter found" in result.stderr

    def test_cli_python_path_broken_falls_through(
        self, tmp_path, run_resolver, working_python_shim
    ):
        """If cli-python-path points at a broken interpreter, resolver must
        reject it via -V probe and fall through — same protection as the
        PATH candidates."""
        broken = tmp_path / "broken_cli_python.sh"
        broken.write_text("#!/bin/sh\nexit 126\n", encoding="utf-8")
        broken.chmod(0o755)
        home = self._home_with_cli_python(tmp_path, str(broken))
        result = run_resolver(
            home_dir=home, path_override=str(working_python_shim)
        )
        assert result.returncode == 0
        resolved = self._resolved_python(result.stdout)
        # Must have fallen through — not the broken cli-python-path target
        assert "broken_cli_python" not in resolved
        # Must be bound to the working `python` shim
        assert resolved.endswith("/python") or resolved.endswith("\\python")
        assert "working_bin" in resolved
