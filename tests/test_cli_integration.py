"""
CP3: every ordinary `gator` command connects the machine's AI tools
(`machine_integration.ensure()`), except `hook`, `integration`, `--help`,
`--version` and bare `gator`; and `gator integration status|remove|
dismiss-codex-reminder`.

conftest sets GATOR_NO_VENDOR_INTEGRATION=1 for the whole suite; these
tests delete it where the trigger must run, and stub `ensure()` and the
script runner, so nothing touches the real machine.
"""

import json
import sys
from pathlib import Path

import pytest

import machine_integration
from conftest import load_script
from gator_command import cli

integration = load_script("gator-integration")


@pytest.fixture
def run_cli(monkeypatch):
    """Run cli.main() with argv; returns (ensure_calls, script_runs, exit)."""
    monkeypatch.delenv("GATOR_NO_VENDOR_INTEGRATION", raising=False)
    calls, runs = [], []

    def fake_ensure(*a, **k):
        calls.append(True)
        return {"messages": ["Gator connected to Claude Code."],
                "problems": [], "changed": ["claude"], "recorded": ["claude"],
                "codex_newly_connected": False}

    def fake_run(scripts_dir, script_name, args):
        runs.append(script_name)
        sys.exit(7)

    monkeypatch.setattr(machine_integration, "ensure", fake_ensure)
    monkeypatch.setattr(cli, "_run_script", fake_run)

    def go(*argv):
        monkeypatch.setattr(sys, "argv", ["gator", *argv])
        with pytest.raises(SystemExit) as exc:
            cli.main()
        return calls, runs, exc.value.code
    return go


@pytest.mark.parametrize("argv", [("init",), ("dashboard",), ("version",),
                                  ("update", "--dry-run"), ("--explain",)])
def test_ordinary_commands_connect(run_cli, argv):
    calls, runs, code = run_cli(*argv)
    assert calls == [True]
    assert len(runs) == 1 and code == 7, "the command still runs, exit unchanged"


@pytest.mark.parametrize("argv", [("hook", "session-open"),
                                  ("integration", "status"),
                                  ("integration", "remove"),
                                  ("integration", "dismiss-codex-reminder")])
def test_hook_and_integration_never_connect(run_cli, argv):
    calls, runs, _ = run_cli(*argv)
    assert calls == [] and len(runs) == 1


@pytest.mark.parametrize("argv", [("--version",), ("--help",), ()])
def test_help_version_and_bare_never_connect(run_cli, argv):
    calls, runs, code = run_cli(*argv)
    assert calls == [] and runs == [] and code == 0


def test_opt_out_skips(run_cli, monkeypatch):
    monkeypatch.setenv("GATOR_NO_VENDOR_INTEGRATION", "1")
    calls, runs, _ = run_cli("init")
    assert calls == [] and runs == ["gator-init.py"]


def test_output_goes_to_stderr_only(run_cli, capsys):
    run_cli("init")
    out, err = capsys.readouterr()
    assert out == ""
    assert "Gator connected to Claude Code." in err


def test_failure_never_changes_exit_code(run_cli, monkeypatch, capsys):
    def boom(*a, **k):
        raise PermissionError("settings locked")
    monkeypatch.setattr(machine_integration, "ensure", boom)
    _, runs, code = run_cli("init")
    out, err = capsys.readouterr()
    assert runs == ["gator-init.py"] and code == 7
    assert out == ""
    assert err.strip() == ("Gator: vendor integration skipped "
                           "(PermissionError: settings locked)")


def test_integration_verb_is_routed():
    assert cli.COMMANDS["integration"][0] == "gator-integration.py"
    assert {"hook", "integration"} == set(cli.NO_ENSURE_VERBS)


# ---------------------------------------------------------------------------
# gator integration (temporary home via Path.home)
# ---------------------------------------------------------------------------

@pytest.fixture
def home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".codex").mkdir()
    monkeypatch.setattr(machine_integration.Path, "home", lambda: home)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setattr(integration, "ensure_utf8_stdout", lambda: None)
    return home


def test_status_json(home, capsys):
    machine_integration.ensure()
    assert integration.main(["status", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["state"] == "ok"
    assert report["vendors"]["claude"]["connected"] is True
    assert report["vendors"]["gemini"]["present"] is False
    assert report["codex_reminder_due"] is True


def test_status_text_names_states_in_words(home, capsys):
    machine_integration.ensure()
    assert integration.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "Claude Code" in out and "Connected" in out
    assert "Not installed" in out
    assert "/hooks" in out and "dismiss-codex-reminder" in out


def test_status_unreadable_state_exits_1(home, capsys):
    (home / ".gator").mkdir()
    (home / ".gator" / "vendor-integration.json").write_text("{bad", encoding="utf-8")
    assert integration.main(["status"]) == 1
    assert "UNREADABLE" in capsys.readouterr().out


def test_status_does_not_connect(home):
    integration.main(["status", "--json"])
    assert not (home / ".claude" / "settings.json").exists()


def test_remove(home, capsys):
    machine_integration.ensure()
    assert integration.main(["remove"]) == 0
    out = capsys.readouterr().out
    assert not (home / ".claude" / "settings.json").exists()
    assert not (home / ".gator" / "vendor-integration.json").exists()
    assert "GATOR_NO_VENDOR_INTEGRATION=1" in out


def test_remove_reports_unreadable_file_and_exits_1(home, capsys):
    (home / ".codex" / "hooks.json").write_text("{bad", encoding="utf-8")
    assert integration.main(["remove"]) == 1
    assert "Left unchanged" in capsys.readouterr().out
    assert (home / ".codex" / "hooks.json").read_text(encoding="utf-8") == "{bad"


def test_dismiss(home, capsys):
    assert integration.main(["dismiss-codex-reminder"]) == 1
    machine_integration.ensure()
    assert integration.main(["dismiss-codex-reminder"]) == 0
    assert machine_integration.status()["codex_reminder_due"] is False


def test_usage_error_exits_2(home):
    with pytest.raises(SystemExit) as exc:
        integration.main(["bogus"])
    assert exc.value.code == 2
