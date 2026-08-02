"""Unit tests for the base-wheel gator-enterprise.py THIN DISPATCHER
(Phase 4e — 2026-08-02).

Prior to Phase 4e, this script hosted real command bodies for
setup/status/disconnect/sync/audit. Phase 4e moved all real work into
the `gator_enterprise_cli` package under `enterprise/enterprise-cli/`
and reduced this script to a backwards-compat dispatcher:

  - Help text and subcommand names preserved (so scripts/docs don't break).
  - Attempts `import gator_enterprise_cli`.
    - If present → delegates to `gator_enterprise_cli.main.main(argv)`.
    - If absent (bare `pip install gator-command`) → prints a clean
      degraded-mode notice and exits 69 (EX_UNAVAILABLE).

These tests cover the dispatcher shape only. The real command behavior
is tested inside `enterprise/tests/` against the enterprise-cli package.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

from conftest import load_script

GATOR_SCRIPTS = Path(__file__).parent.parent / "src" / "gator_command" / "scripts"
gator_enterprise = load_script("gator-enterprise", search_dir=GATOR_SCRIPTS)


class TestConstants:
    """The script's exported constants ARE the CLI contract."""

    def test_ex_unavailable_is_sysexits_69(self):
        assert gator_enterprise.EX_UNAVAILABLE == 69

    def test_unavailable_sentinel_present(self):
        assert gator_enterprise.UNAVAILABLE_SENTINEL == "[gator-enterprise-unavailable]"

    def test_client_subcommands_include_expected_verbs(self):
        names = [name for name, _ in gator_enterprise.CLIENT_SUBCOMMANDS]
        assert set(names) >= {"setup", "status", "sync", "audit", "disconnect"}

    def test_server_subcommands_include_expected_verbs(self):
        names = [name for name, _ in gator_enterprise.SERVER_SUBCOMMANDS]
        assert set(names) >= {"server", "db", "policy", "org", "fleet"}

    def test_all_subcommands_is_client_plus_server(self):
        assert (
            gator_enterprise.ALL_SUBCOMMANDS
            == gator_enterprise.CLIENT_SUBCOMMANDS + gator_enterprise.SERVER_SUBCOMMANDS
        )


class TestHelp:
    """`gator enterprise` with no args prints help and exits 0."""

    def test_no_args_prints_help_and_returns_zero(self, capfd):
        rc = gator_enterprise.main([])
        out, _err = capfd.readouterr()
        assert rc == 0
        assert "gator enterprise" in out
        assert "client-side commands" in out
        assert "server-side commands" in out

    def test_help_lists_every_client_subcommand(self, capfd):
        gator_enterprise.main([])
        out, _err = capfd.readouterr()
        for name, _ in gator_enterprise.CLIENT_SUBCOMMANDS:
            assert name in out, f"help missing client subcommand `{name}`"

    def test_help_lists_every_server_subcommand(self, capfd):
        gator_enterprise.main([])
        out, _err = capfd.readouterr()
        for name, _ in gator_enterprise.SERVER_SUBCOMMANDS:
            assert name in out, f"help missing server subcommand `{name}`"


class TestUnavailableNotice:
    """When gator_enterprise_cli is not importable, every subcommand
    must return EX_UNAVAILABLE with a clean notice."""

    @pytest.fixture(autouse=True)
    def force_unavailable(self, monkeypatch):
        """Force the dispatcher's import attempt to fail — simulates a
        base `pip install gator-command` with no enterprise-cli present."""
        monkeypatch.setattr(
            gator_enterprise, "_try_import_enterprise_cli", lambda: None,
        )

    @pytest.mark.parametrize("verb", ["setup", "status", "sync", "audit", "disconnect"])
    def test_client_subcommand_exits_ex_unavailable(self, verb, capfd):
        rc = gator_enterprise.main([verb])
        out, _err = capfd.readouterr()
        assert rc == gator_enterprise.EX_UNAVAILABLE
        assert gator_enterprise.UNAVAILABLE_SENTINEL in out
        assert "Enterprise features not available" in out

    @pytest.mark.parametrize("verb", ["server", "db", "policy", "org", "fleet"])
    def test_server_subcommand_exits_ex_unavailable(self, verb, capfd):
        rc = gator_enterprise.main([verb])
        out, _err = capfd.readouterr()
        assert rc == gator_enterprise.EX_UNAVAILABLE
        assert gator_enterprise.UNAVAILABLE_SENTINEL in out

    def test_notice_names_install_path(self, capfd):
        gator_enterprise.main(["setup"])
        out, _err = capfd.readouterr()
        assert "enterprise/enterprise-cli/" in out

    def test_notice_names_exit_code_and_plan_ref(self, capfd):
        gator_enterprise.main(["status"])
        out, _err = capfd.readouterr()
        assert "69" in out
        assert "EX_UNAVAILABLE" in out
        assert gator_enterprise.PLAN_REF in out


class TestDelegation:
    """When gator_enterprise_cli IS importable, dispatcher delegates."""

    def test_delegates_to_enterprise_cli_main(self, monkeypatch, capfd):
        calls = []

        class FakeCliMain:
            @staticmethod
            def main(argv):
                calls.append(list(argv))
                return 0

        fake_pkg = type("FakePkg", (), {})()

        def fake_import_pkg():
            return fake_pkg

        def fake_import_main():
            return FakeCliMain.main

        monkeypatch.setattr(
            gator_enterprise, "_try_import_enterprise_cli", fake_import_pkg,
        )
        # Inject the fake main into the module namespace so the dispatcher's
        # `from gator_enterprise_cli.main import main` sees our stub.
        import types
        pkg_mod = types.ModuleType("gator_enterprise_cli")
        pkg_main = types.ModuleType("gator_enterprise_cli.main")
        pkg_main.main = FakeCliMain.main
        pkg_mod.main = pkg_main
        monkeypatch.setitem(sys.modules, "gator_enterprise_cli", pkg_mod)
        monkeypatch.setitem(sys.modules, "gator_enterprise_cli.main", pkg_main)

        # Use `sync` -- the one advertised verb that overlaps with
        # enterprise-cli's registered set (ENTERPRISE_CLI_VERBS), so
        # the verb-mapping pre-check passes and delegation runs.
        rc = gator_enterprise.main(["sync", "--api-url", "https://ent.example"])
        assert rc == 0
        assert calls == [["sync", "--api-url", "https://ent.example"]]

    def test_incomplete_install_prints_stderr_and_returns_unavailable(
        self, monkeypatch, capfd
    ):
        """Package importable but its `.main` submodule is missing —
        the dispatcher must not raise, but return EX_UNAVAILABLE."""
        import types

        # Package importable...
        monkeypatch.setattr(
            gator_enterprise,
            "_try_import_enterprise_cli",
            lambda: types.ModuleType("gator_enterprise_cli"),
        )
        # ...but .main is not.
        monkeypatch.setitem(
            sys.modules,
            "gator_enterprise_cli",
            types.ModuleType("gator_enterprise_cli"),
        )
        # Ensure the .main submodule cannot be imported.
        if "gator_enterprise_cli.main" in sys.modules:
            monkeypatch.delitem(sys.modules, "gator_enterprise_cli.main")

        rc = gator_enterprise.main(["setup"])
        _out, err = capfd.readouterr()

        assert rc == gator_enterprise.EX_UNAVAILABLE
        assert gator_enterprise.UNAVAILABLE_SENTINEL in err


class TestIntegrationGap:
    """Codex Phase 4e finding 1 regression guard.

    When enterprise-cli IS importable but its parser doesn't recognize
    the dispatcher's advertised verb, the dispatcher MUST catch the
    resulting SystemExit and translate it into a clean EX_UNAVAILABLE
    notice -- NOT let mvp's raw argparse "invalid choice" error escape
    as the caller's exit code. Shell chains that pipe on `gator
    enterprise setup` should see a stable exit 69 regardless of whether
    the enterprise-cli package is missing OR present-but-verb-unmapped.
    """

    @staticmethod
    def _install_mvp_style_main(monkeypatch, verbs):
        """Install a stub gator_enterprise_cli whose main() argparses a
        specific verb allow-list -- mimicking the real mvp shape."""
        import argparse as _argparse
        import types

        def _mvp_style_main(argv=None):
            _argv = argv if argv is not None else sys.argv[1:]
            p = _argparse.ArgumentParser(prog="gator-enterprise")
            p.add_argument("command", choices=verbs)
            p.parse_args(_argv)
            return 0

        pkg = types.ModuleType("gator_enterprise_cli")
        pkg_main = types.ModuleType("gator_enterprise_cli.main")
        pkg_main.main = _mvp_style_main
        pkg.main = pkg_main
        monkeypatch.setattr(
            gator_enterprise, "_try_import_enterprise_cli", lambda: pkg,
        )
        monkeypatch.setitem(sys.modules, "gator_enterprise_cli", pkg)
        monkeypatch.setitem(sys.modules, "gator_enterprise_cli.main", pkg_main)

    @pytest.mark.parametrize("advertised_but_unmapped", [
        "setup", "status", "audit", "disconnect",
        "server", "db", "policy", "org", "fleet",
    ])
    def test_unmapped_verb_returns_ex_unavailable_not_argparse_exit(
        self, monkeypatch, capfd, advertised_but_unmapped,
    ):
        # Install a stub main() that only accepts the mvp verb set.
        MVP_VERBS = ["auth", "repos", "providers", "policies", "reports",
                     "blocks", "machines", "activate", "sync", "repo"]
        self._install_mvp_style_main(monkeypatch, MVP_VERBS)

        rc = gator_enterprise.main([advertised_but_unmapped])
        out, _err = capfd.readouterr()

        assert rc == gator_enterprise.EX_UNAVAILABLE, (
            f"Verb '{advertised_but_unmapped}' escaped with rc={rc}; "
            f"expected 69 (EX_UNAVAILABLE). Raw argparse errors from "
            f"mvp MUST NOT surface as the caller's exit code."
        )
        assert gator_enterprise.UNAVAILABLE_SENTINEL in out
        assert "not yet integrated" in out

    def test_verb_that_mvp_accepts_still_delegates_cleanly(
        self, monkeypatch, capfd,
    ):
        """When the advertised verb DOES happen to overlap with mvp's
        parser (e.g. `sync`), delegation must succeed (rc 0), not be
        swallowed by the SystemExit catch."""
        MVP_VERBS = ["sync"]  # overlaps with dispatcher's advertised sync
        self._install_mvp_style_main(monkeypatch, MVP_VERBS)

        rc = gator_enterprise.main(["sync"])
        assert rc == 0

    @staticmethod
    def _install_failing_main(monkeypatch, exit_code):
        """Install a stub gator_enterprise_cli whose main() raises
        SystemExit(exit_code) unconditionally -- simulates a real
        command-body failure inside a mapped verb."""
        import types

        def _failing_main(argv=None):
            raise SystemExit(exit_code)

        pkg = types.ModuleType("gator_enterprise_cli")
        pkg_main = types.ModuleType("gator_enterprise_cli.main")
        pkg_main.main = _failing_main
        pkg.main = pkg_main
        monkeypatch.setattr(
            gator_enterprise, "_try_import_enterprise_cli", lambda: pkg,
        )
        monkeypatch.setitem(sys.modules, "gator_enterprise_cli", pkg)
        monkeypatch.setitem(sys.modules, "gator_enterprise_cli.main", pkg_main)

    def test_mapped_verb_runtime_failure_propagates_exit_code(
        self, monkeypatch, capfd,
    ):
        """Codex whiteboard finding 1 (2026-08-02) regression guard.

        Before the pre-check fix, ANY nonzero SystemExit from delegation
        was translated to the integration-gap notice. That masked real
        command failures on mapped verbs. Post-fix: `sync` is in
        ENTERPRISE_CLI_VERBS, so delegation runs; a SystemExit(1) from
        the delegated main is a real failure and must surface as rc=1,
        NOT rc=69 with the "not yet integrated" notice."""
        self._install_failing_main(monkeypatch, exit_code=1)

        rc = gator_enterprise.main(["sync"])
        out, _err = capfd.readouterr()

        assert rc == 1, (
            f"Mapped-verb SystemExit(1) mislabeled: got rc={rc}. "
            f"Real runtime errors on integrated verbs must not be "
            f"translated to the integration-gap notice (Finding 1)."
        )
        assert "not yet integrated" not in out
        assert gator_enterprise.UNAVAILABLE_SENTINEL not in out

    def test_mapped_verb_argparse_subcommand_error_propagates(
        self, monkeypatch, capfd,
    ):
        """A mapped verb's per-subcommand argparse rejection (SystemExit(2)
        for an invalid flag) must reach the caller as rc=2, not be
        rewritten to the integration-gap notice. Different failure mode
        from the runtime-error test above, same principle: the pre-check
        already handled verb-mismatch upstream, so any SystemExit from
        the delegated main is real."""
        self._install_failing_main(monkeypatch, exit_code=2)

        rc = gator_enterprise.main(["sync", "--nonexistent-flag"])
        out, _err = capfd.readouterr()

        assert rc == 2
        assert "not yet integrated" not in out

    def test_mapped_verb_systemexit_none_returns_zero(
        self, monkeypatch, capfd,
    ):
        """Bare `sys.exit()` / `SystemExit(None)` from delegated main
        conventionally means "clean exit" — normalize to rc=0."""
        self._install_failing_main(monkeypatch, exit_code=None)

        rc = gator_enterprise.main(["sync"])
        assert rc == 0
