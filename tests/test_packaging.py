"""
Tests for the gator-command package — verifies the CLI, wheel contents,
and installed-artifact behavior.
"""

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent


class TestCLIDispatch:
    """Test that the gator CLI entry point resolves scripts."""

    def test_help(self):
        """gator --help exits 0 and shows usage."""
        result = subprocess.run(
            [sys.executable, "-m", "gator_command.cli", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "gator" in result.stdout.lower()
        assert "version" in result.stdout

    def test_version_flag(self):
        """gator -V shows the package version — the same one the package metadata reports.

        Previous form hardcoded "1." which broke silently on the v2.x bump.
        Comparing against the imported __version__ makes the test survive
        every future bump automatically.
        """
        from gator_command import __version__
        result = subprocess.run(
            [sys.executable, "-m", "gator_command.cli", "-V"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert __version__ in result.stdout, (
            f"expected {__version__!r} in output, got: {result.stdout!r}"
        )

    def test_scripts_dir_resolvable(self):
        """The CLI can find its scripts directory."""
        from gator_command.cli import _find_scripts_dir
        scripts_dir = _find_scripts_dir()
        assert scripts_dir is not None
        assert (scripts_dir / "gator_core.py").exists()

    def test_all_dispatched_scripts_exist(self):
        """Every script referenced in COMMANDS actually exists."""
        from gator_command.cli import COMMANDS, _find_scripts_dir
        scripts_dir = _find_scripts_dir()
        assert scripts_dir is not None
        for cmd_name, (script_name, _) in COMMANDS.items():
            script_path = scripts_dir / script_name
            assert script_path.exists(), f"Missing script for '{cmd_name}': {script_name}"


class TestWheelBuildAndContents:
    """Build a wheel and verify its contents — no skipping."""

    @pytest.fixture(scope="class")
    def built_wheel(self, tmp_path_factory):
        """Build a wheel into a temp directory."""
        dist_dir = tmp_path_factory.mktemp("dist")
        result = subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist_dir)],
            capture_output=True, text=True, timeout=120,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, f"Wheel build failed:\n{result.stderr}"
        wheels = list(dist_dir.glob("*.whl"))
        assert len(wheels) == 1, f"Expected 1 wheel, found {len(wheels)}"
        return wheels[0]

    def test_wheel_has_scripts(self, built_wheel):
        """Wheel contains runtime scripts."""
        with zipfile.ZipFile(built_wheel) as z:
            script_files = [n for n in z.namelist()
                           if n.startswith("gator_command/scripts/") and n.endswith(".py")]
            assert len(script_files) >= 10, f"Expected 10+ scripts, found {len(script_files)}"
            names = {Path(n).name for n in script_files}
            assert "gator_core.py" in names
            assert "gator-dashboard.py" in names
            assert "gator_runtime.py" in names

    def test_wheel_has_dashboard(self, built_wheel):
        """Wheel contains dashboard static files."""
        with zipfile.ZipFile(built_wheel) as z:
            dashboard_files = [n for n in z.namelist()
                              if "dashboard/" in n and not n.endswith("/")]
            assert len(dashboard_files) >= 5

    def test_wheel_has_templates(self, built_wheel):
        """Wheel contains gator-starter templates."""
        with zipfile.ZipFile(built_wheel) as z:
            template_files = [n for n in z.namelist()
                             if "templates/" in n and not n.endswith("/")]
            assert len(template_files) >= 20, f"Expected 20+ templates, found {len(template_files)}"
            names = {Path(n).name for n in template_files}
            assert "constitution.md" in names
            assert "gator-pre-commit.py" in names

    def test_wheel_has_gator_enterprise_script(self, built_wheel):
        """Phase 3a → 4e: the thin `gator enterprise` dispatcher ships in the wheel."""
        with zipfile.ZipFile(built_wheel) as z:
            names = {Path(n).name for n in z.namelist()
                     if n.startswith("gator_command/scripts/")}
            assert "gator-enterprise.py" in names, (
                "gator-enterprise.py must ship in the wheel"
            )

    def test_wheel_does_not_ship_enterprise_cli_modules(self, built_wheel):
        """Phase 4e consolidation: base wheel MUST NOT ship the enterprise-cli
        modules that lived at src/gator_command/scripts/enterprise_*.py before
        4e. They now live under enterprise/enterprise-cli/ and are installed
        separately.
        """
        forbidden = {
            "enterprise_client.py",
            "enterprise_credentials.py",
            "enterprise_vendor_hooks.py",
        }
        with zipfile.ZipFile(built_wheel) as z:
            names = {Path(n).name for n in z.namelist()
                     if n.startswith("gator_command/scripts/")}
        leaked = forbidden & names
        assert not leaked, (
            f"Base wheel leaked Phase 4e-consolidated enterprise modules: {leaked}. "
            f"These belong in enterprise/enterprise-cli/, not the base wheel."
        )

    def test_wheel_metadata_declares_enterprise_server_extra(self, built_wheel):
        """Phase 3a: [enterprise-server] optional extra + all 5 server deps present in METADATA.

        Ratified as Decision C Option 2 in
        gator-command/artifacts/2026-07-31-monorepo-product-contract-decisions.md
        — pipx install "gator-command[enterprise-server]" is the operator
        install path. This test pins the METADATA contract so a
        pyproject.toml regression is caught at build time.
        """
        expected_deps = {
            "fastapi", "sqlalchemy", "alembic",
            "uvicorn[standard]", "psycopg[binary]",
        }
        with zipfile.ZipFile(built_wheel) as z:
            metadata_paths = [n for n in z.namelist()
                              if n.endswith(".dist-info/METADATA")]
            assert len(metadata_paths) == 1, f"Unexpected METADATA files: {metadata_paths}"
            metadata = z.read(metadata_paths[0]).decode("utf-8")

        assert "Provides-Extra: enterprise-server" in metadata, (
            "METADATA must advertise the enterprise-server optional extra"
        )

        # Collect the dist names from Requires-Dist lines scoped to
        # extra == "enterprise-server".
        found = set()
        for line in metadata.splitlines():
            if not line.startswith("Requires-Dist: "):
                continue
            if 'extra == "enterprise-server"' not in line:
                continue
            # Format: "Requires-Dist: <name>[<extras>][<constraint>]; extra == ..."
            spec = line[len("Requires-Dist: "):].split(";", 1)[0].strip()
            # Strip version constraint (>=x.y, ==x, etc.)
            for op in (">=", "==", "<=", ">", "<", "~="):
                idx = spec.find(op)
                if idx != -1:
                    spec = spec[:idx].strip()
                    break
            found.add(spec.lower())

        missing = {d.lower() for d in expected_deps} - found
        assert not missing, (
            f"enterprise-server extra missing deps: {missing}. "
            f"Found: {sorted(found)}"
        )


class TestInstalledArtifact:
    """Install the built wheel into a temp venv and verify gator works."""

    @pytest.fixture(scope="class")
    def installed_venv(self, tmp_path_factory):
        """Build wheel, create venv, install, return venv python path."""
        base = tmp_path_factory.mktemp("install_test")
        dist_dir = base / "dist"
        dist_dir.mkdir()
        venv_dir = base / "venv"

        # Build wheel
        result = subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist_dir)],
            capture_output=True, text=True, timeout=120,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, f"Wheel build failed:\n{result.stderr}"
        wheel = list(dist_dir.glob("*.whl"))[0]

        # Create venv
        result = subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, f"Venv creation failed:\n{result.stderr}"

        # Find venv python
        if sys.platform == "win32":
            venv_python = venv_dir / "Scripts" / "python.exe"
        else:
            venv_python = venv_dir / "bin" / "python"
        assert venv_python.exists(), f"Venv python not found at {venv_python}"

        # Install wheel
        result = subprocess.run(
            [str(venv_python), "-m", "pip", "install", str(wheel)],
            capture_output=True, text=True, timeout=120,
        )
        assert result.returncode == 0, f"Install failed:\n{result.stderr}"

        return venv_python

    @staticmethod
    def _gator_exe(venv_python):
        """Return the path to the installed gator executable in the venv."""
        venv_dir = venv_python.parent.parent
        if sys.platform == "win32":
            return venv_dir / "Scripts" / "gator.exe"
        return venv_dir / "bin" / "gator"

    def test_entry_point_exists(self, installed_venv):
        """The gator console script was installed into the venv."""
        gator = self._gator_exe(installed_venv)
        assert gator.exists(), f"gator entry point not found at {gator}"

    def test_gator_version_flag(self, installed_venv):
        """gator -V matches the installed package metadata version."""
        gator = self._gator_exe(installed_venv)
        expected = subprocess.run(
            [str(installed_venv), "-c", "from importlib.metadata import version; print(version('gator-command'))"],
            capture_output=True, text=True, timeout=10,
        )
        assert expected.returncode == 0
        result = subprocess.run(
            [str(gator), "-V"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == f"gator {expected.stdout.strip()}"

    def test_gator_help(self, installed_venv):
        """gator --help works via the real entry point."""
        gator = self._gator_exe(installed_venv)
        result = subprocess.run(
            [str(gator), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "version" in result.stdout
        assert "dashboard" in result.stdout

    def test_gator_version_subcommand(self, installed_venv):
        """gator version dispatches to the real script and runs."""
        gator = self._gator_exe(installed_venv)
        result = subprocess.run(
            [str(gator), "version"],
            capture_output=True, text=True, timeout=10,
        )
        # gator-version.py may return "dev" without git, but it should not crash
        assert result.returncode == 0

    def test_gator_enterprise_help(self, installed_venv):
        """Phase 3a: `gator enterprise --help` works via the installed entry point.

        Help output shape stays stable across Phase 4e (delegation) + the
        2026-08-09 Phase 4 (3.0 stabilization P2.1) verb-set reconciliation.
        The verb NAMES were rewritten in P2.1 to reflect real enterprise-cli
        commands — this test now iterates the reconciled set.
        """
        gator = self._gator_exe(installed_venv)
        result = subprocess.run(
            [str(gator), "enterprise", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        # Real client-side + server-side verbs post-P2.1 reconciliation.
        # Sync obligation: match CLIENT_SUBCOMMANDS + SERVER_SUBCOMMANDS in
        # src/gator_command/scripts/gator-enterprise.py.
        for verb in ("activate", "sync", "repo", "transcripts", "commits",
                     "auth", "repos", "providers", "policies", "reports",
                     "machines", "blocks"):
            assert verb in result.stdout, (
                f"gator enterprise --help does not list subcommand '{verb}'"
            )

    def test_gator_enterprise_all_verbs_exit_unavailable_in_base_install(self, installed_venv):
        """Released contract: with only the base wheel installed (no
        `gator_enterprise_cli` package), every ADVERTISED enterprise
        subcommand prints the degraded-mode notice and exits 69
        (EX_UNAVAILABLE).

        Phase 4e (2026-08-02) consolidated all Enterprise code under
        enterprise/enterprise-cli/, so the base install uniformly returns
        "not available" for every verb it advertises. Phase 4 (3.0
        stabilization, 2026-08-09) reconciled CLIENT_SUBCOMMANDS +
        SERVER_SUBCOMMANDS to reflect real enterprise-cli verbs — this
        test now iterates the reconciled set. Verbs no longer advertised
        (setup/status/audit/disconnect/server/db/policy/org/fleet) get
        rejected by argparse with rc=2 upstream of the dispatcher, which
        is the correct behavior; only advertised verbs reach the
        degraded-mode notice.

        Real behavior is tested against the enterprise-cli package in
        enterprise/tests/.
        """
        gator = self._gator_exe(installed_venv)
        # Sync obligation: match CLIENT_SUBCOMMANDS + SERVER_SUBCOMMANDS
        # in src/gator_command/scripts/gator-enterprise.py.
        for verb in ("activate", "sync", "repo", "transcripts", "commits",
                     "auth", "repos", "providers", "policies", "reports",
                     "machines", "blocks"):
            result = subprocess.run(
                [str(gator), "enterprise", verb],
                capture_output=True, text=True, timeout=10,
            )
            assert result.returncode == 69, (
                f"`gator enterprise {verb}` returned {result.returncode}, "
                f"expected 69 (EX_UNAVAILABLE). Base install must fail closed."
            )
            assert "[gator-enterprise-unavailable]" in result.stdout, (
                f"`gator enterprise {verb}` output missing sentinel prefix; "
                f"got: {result.stdout!r}"
            )
