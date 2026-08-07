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
    _MODE_LOOKUP,
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


class TestModeLookupIsWindowsSafe:
    """The wrapper's mode lookup crosses the shell/Python boundary. On
    Windows Git Bash, `$HOME` expands to `/c/Users/...` (MSYS path form)
    which Windows Python's `open()` can't resolve — the mode lookup then
    silently falls through to 'strict', defeating any `repo init --mode X`
    for X != strict. Two invariants preserved by _MODE_LOOKUP:
    (a) the policy path is computed inside Python via `Path.home()`, not
        shell-interpolated from `$HOME`;
    (b) the repo-id crosses the shell/Python boundary via env var
        (GATOR_REPO_ID), not string interpolation into the -c script
        (quote-safe, injection-safe).
    """

    @pytest.mark.parametrize(
        "template,name",
        [
            (PRE_COMMIT_HOOK, "PRE_COMMIT_HOOK"),
            (COMMIT_MSG_HOOK, "COMMIT_MSG_HOOK"),
            (POST_COMMIT_HOOK, "POST_COMMIT_HOOK"),
        ],
    )
    def test_template_embeds_mode_lookup(self, template, name):
        assert _MODE_LOOKUP in template, (
            f"{name} does not embed _MODE_LOOKUP — mode resolution will be "
            f"inconsistent or Windows-broken."
        )

    def test_mode_lookup_uses_pathlib_not_shell_home(self):
        """The FIX for the third Windows bug: Path.home() replaces $HOME
        shell interpolation. If someone reintroduces $HOME-into-Python
        the Windows mode lookup silently degrades to strict."""
        assert "Path.home()" in _MODE_LOOKUP, (
            "_MODE_LOOKUP must compute the policy path via Path.home() "
            "inside Python, NOT interpolate $HOME from the shell (Windows "
            "Git Bash returns /c/Users/... which Windows Python can't open)."
        )
        # Verify the anti-pattern is gone
        assert "'$POLICY_FILE'" not in _MODE_LOOKUP, (
            "shell-interpolated POLICY_FILE is the Windows failure mode; "
            "must not appear in the mode-lookup snippet"
        )
        assert "$POLICY_FILE" not in _MODE_LOOKUP, (
            "shell-interpolated POLICY_FILE is the Windows failure mode; "
            "must not appear in the mode-lookup snippet"
        )

    def test_mode_lookup_passes_repo_id_via_env(self):
        """Repo-id crosses the shell/Python boundary via env var
        (GATOR_REPO_ID), NOT via '$REPO_ID' string interpolation into
        the inline -c script. Env passing is quote-safe and doesn't
        risk python-syntax errors on unusual repo names."""
        assert "GATOR_REPO_ID" in _MODE_LOOKUP, (
            "repo-id must be passed via env var GATOR_REPO_ID; the "
            "shell-interpolation pattern is fragile and unsafe"
        )
        # Verify the anti-pattern is gone
        assert "'$REPO_ID'" not in _MODE_LOOKUP, (
            "shell-interpolated REPO_ID is the anti-pattern; must not "
            "appear in the mode-lookup snippet"
        )

    def test_mode_lookup_defaults_to_strict_on_error(self):
        """When policy is unreadable / repo not in policy / any error,
        the lookup MUST default to 'strict' — fail-safe posture."""
        assert "'strict'" in _MODE_LOOKUP, (
            "mode lookup must have 'strict' as fallback default"
        )
        assert "except" in _MODE_LOOKUP, (
            "Python side must have an except clause so unreadable "
            "policy falls through to the strict default"
        )
        assert "|| echo \"strict\"" in _MODE_LOOKUP, (
            "shell side must have `|| echo strict` so a Python launch "
            "failure also falls through to strict"
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


# --- Finding #2 regression pins ---
# `activate --force` must NOT rotate the machine keypair. Rotation only
# happens on explicit `--regenerate-keys`. Rationale: `--force` is used
# routinely to redeploy hooks (e.g., after a source change to the wrapper
# templates); rotating the keypair on every such redeploy would invalidate
# every previously-encrypted session block on this machine and desync the
# server's stored public key. See TRIPWIRE in scripts-enterprise.md.

from types import SimpleNamespace


class _FakeClient:
    """Minimal client stand-in for _do_activate/_do_sync tests.

    Records POST calls so tests can assert whether a machine key was
    re-registered with the server after regeneration."""

    def __init__(self, base="http://test", hook_policy=None, repos=None):
        self._base = base
        self._hook_policy = hook_policy if hook_policy is not None else {}
        self._repos = repos if repos is not None else []
        self.posts = []
        self.puts = []
        self.gets = []

    def post(self, path, json=None):
        self.posts.append((path, json))
        return {}

    def put(self, path, json=None):
        self.puts.append((path, json))
        return {}

    def get(self, path):
        self.gets.append(path)
        if path == "/api/v1/hook-policy":
            return self._hook_policy
        if path == "/api/v1/repos":
            return self._repos
        if path == "/api/v1/org-policies":
            return []
        return {}


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Redirect Path.home() to tmp_path so activate/sync tests can't touch
    the real ~/.gator/ on the developer's machine. Also stub git-config
    calls so we don't rewrite the developer's global core.hooksPath."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    # Stub the git-config subprocess call in _do_activate so it doesn't
    # touch the developer's real ~/.gitconfig. We don't care about
    # verifying git config here — that's not what these tests are about.
    real_subprocess_run = subprocess.run

    def stub_run(cmd, *args, **kwargs):
        if isinstance(cmd, list) and len(cmd) >= 2 and cmd[0] == "git" and "config" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return real_subprocess_run(cmd, *args, **kwargs)

    from gator_enterprise_cli.commands import activate as activate_mod
    monkeypatch.setattr(activate_mod.subprocess, "run", stub_run)
    return home


class TestActivateKeyPreservation:
    """Finding #2: `--force` must preserve the machine keypair; only
    `--regenerate-keys` rotates it."""

    def _run_activate(self, home, force=False, regenerate_keys=False):
        from gator_enterprise_cli.commands.activate import _do_activate
        args = SimpleNamespace(
            command="activate",
            force=force,
            regenerate_keys=regenerate_keys,
        )
        client = _FakeClient()
        _do_activate(args, client)
        return client

    def _read_private_key(self, home):
        return (home / ".gator" / "enterprise" / "keys" / "machine-private-key.pem").read_bytes()

    def test_first_activate_generates_keypair(self, isolated_home):
        client = self._run_activate(isolated_home)
        keys_dir = isolated_home / ".gator" / "enterprise" / "keys"
        assert (keys_dir / "machine-private-key.pem").exists()
        assert (keys_dir / "machine-public-key.pem").exists()
        # Server-side registration attempted
        assert any(path == "/api/v1/crypto/machine-keys" for path, _ in client.posts), (
            "expected POST to /api/v1/crypto/machine-keys on fresh install"
        )

    def test_reactivate_without_flags_preserves_keypair(self, isolated_home):
        self._run_activate(isolated_home)
        first = self._read_private_key(isolated_home)
        client2 = self._run_activate(isolated_home)
        second = self._read_private_key(isolated_home)
        assert first == second, "reactivate without flags rotated the key"
        # Second activate must NOT re-POST the key (nothing changed)
        assert not any(
            path == "/api/v1/crypto/machine-keys" for path, _ in client2.posts
        ), "reactivate without flags re-registered the key"

    def test_reactivate_with_force_preserves_keypair(self, isolated_home):
        """THE FIX: --force must NOT rotate the key. This test is the
        specific regression pin for Finding #2."""
        self._run_activate(isolated_home)
        first = self._read_private_key(isolated_home)
        client2 = self._run_activate(isolated_home, force=True)
        second = self._read_private_key(isolated_home)
        assert first == second, (
            "--force rotated the machine keypair — Finding #2 regressed. "
            "--force should redeploy hooks/config only; --regenerate-keys "
            "is the rotation gesture."
        )
        # Second activate with --force must NOT re-POST the key
        assert not any(
            path == "/api/v1/crypto/machine-keys" for path, _ in client2.posts
        ), "--force re-registered the key without a rotation reason"

    def test_regenerate_keys_flag_rotates_keypair(self, isolated_home):
        """--regenerate-keys is the explicit rotation gesture."""
        self._run_activate(isolated_home)
        first = self._read_private_key(isolated_home)
        client2 = self._run_activate(isolated_home, regenerate_keys=True)
        second = self._read_private_key(isolated_home)
        assert first != second, (
            "--regenerate-keys did NOT rotate the key — the explicit "
            "rotation gesture must actually rotate."
        )
        # After rotation, the new public key must be re-POSTed to server
        assert any(
            path == "/api/v1/crypto/machine-keys" for path, _ in client2.posts
        ), "--regenerate-keys did not re-register the new public key"

    def test_force_does_not_wipe_hook_policy(self, isolated_home):
        """--force must NOT wipe hook-policy.json (which may contain local
        intent modes from repo init for repos not yet server-registered).
        See TRIPWIRE in scripts-enterprise.md."""
        # First activate to create baseline
        self._run_activate(isolated_home)
        # Manually seed a local intent entry (simulating repo init)
        policy_path = isolated_home / ".gator" / "enterprise" / "hook-policy.json"
        import json as _json
        policy_path.write_text(
            _json.dumps({"local/sandbox": {"mode": "evidence_only"}}, indent=2),
            encoding="utf-8",
        )
        # Reactivate with --force
        self._run_activate(isolated_home, force=True)
        # Local intent must survive the --force reactivation. (The final
        # _do_sync call merges the server view — an empty {} from the
        # fake client — so the local intent is preserved by the merge.)
        merged = _json.loads(policy_path.read_text(encoding="utf-8"))
        assert "local/sandbox" in merged, (
            "--force wiped the local intent-mode entry from hook-policy.json"
        )
        assert merged["local/sandbox"]["mode"] == "evidence_only"


class TestSyncMerge:
    """Sync must merge server view with local intents, not replace wholesale.
    Load-bearing for Finding #3: repo init writes local intent; without
    merge, the very next sync (which activate runs at end) wipes it."""

    def _seed_local_policy(self, home, entries):
        import json as _json
        policy_path = home / ".gator" / "enterprise" / "hook-policy.json"
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        policy_path.write_text(_json.dumps(entries, indent=2), encoding="utf-8")
        return policy_path

    def _run_sync(self, home, server_policy):
        from gator_enterprise_cli.commands.activate import _do_sync
        args = SimpleNamespace(command="sync")
        client = _FakeClient(hook_policy=server_policy)
        _do_sync(args, client)
        return client

    def test_sync_preserves_local_intent_when_server_empty(self, isolated_home):
        """The exact scenario Finding #3 hinges on: repo init wrote local
        intent; sync fires (from activate's own tail-end call); merge
        keeps the intent because server doesn't know about the repo."""
        policy_path = self._seed_local_policy(
            isolated_home, {"local/sandbox": {"mode": "evidence_only"}}
        )
        self._run_sync(isolated_home, server_policy={})
        import json as _json
        merged = _json.loads(policy_path.read_text(encoding="utf-8"))
        assert merged == {"local/sandbox": {"mode": "evidence_only"}}, (
            "sync wiped local intent when server returned empty policy — "
            "the exact bug the merge semantics were introduced to fix"
        )

    def test_sync_server_wins_for_overlapping_keys(self, isolated_home):
        """Server is authoritative for repos it knows about. Local intent
        gets overwritten by the server's view — that's the whole point
        of eventual server-side registration."""
        policy_path = self._seed_local_policy(
            isolated_home, {"github.com/o/r": {"mode": "evidence_only"}}
        )
        self._run_sync(
            isolated_home,
            server_policy={"github.com/o/r": {"mode": "strict"}},
        )
        import json as _json
        merged = _json.loads(policy_path.read_text(encoding="utf-8"))
        assert merged["github.com/o/r"]["mode"] == "strict", (
            "sync merge did not let server win for a repo the server knows about"
        )

    def test_sync_merges_disjoint_local_and_server(self, isolated_home):
        """Local intents and server entries for DIFFERENT repos both survive."""
        policy_path = self._seed_local_policy(
            isolated_home, {"local/sandbox": {"mode": "evidence_only"}}
        )
        self._run_sync(
            isolated_home,
            server_policy={"github.com/o/r": {"mode": "strict"}},
        )
        import json as _json
        merged = _json.loads(policy_path.read_text(encoding="utf-8"))
        assert set(merged) == {"local/sandbox", "github.com/o/r"}
        assert merged["local/sandbox"]["mode"] == "evidence_only"
        assert merged["github.com/o/r"]["mode"] == "strict"
