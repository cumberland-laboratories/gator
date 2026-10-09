"""Tests for loop/codex_launcher.py — `gator loop codex` (#37 follow-up).

No test launches an interactive Codex. Preparation tests call the pure /
plan / apply seams directly on temp directories (validate_home's temp-dir
refusal is exercised separately with an injected tempdir).
"""

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
LOOP_DIR = REPO_ROOT / "src" / "gator_command" / "scripts" / "loop"
if str(LOOP_DIR) not in sys.path:
    sys.path.insert(0, str(LOOP_DIR))

import codex_launcher as cl  # noqa: E402

NOTE_PAIR = [
    REPO_ROOT / "src" / "gator_command" / "templates" / "gator-starter" / "reference-notes"
    / "codex-routine-participant-profile.md",
    REPO_ROOT / ".gator" / ".includes" / "reference-notes" / "codex-routine-participant-profile.md",
]


def _repo(tmp_path):
    repo = tmp_path / "Repo Dir"
    (repo / ".gator").mkdir(parents=True)
    return repo


def _snapshot(root):
    return {p.relative_to(root).as_posix(): (p.read_bytes() if p.is_file() else None)
            for p in sorted(root.rglob("*"))}


def _prepare(home, repo, platform="win32"):
    cl.apply_preparation(cl.plan_preparation(home, repo, platform))


# ---------------------------------------------------------------------------
# Canonical rule
# ---------------------------------------------------------------------------

def _note_rule(note_path):
    text = note_path.read_text(encoding="utf-8")
    block = text.split("   ```python\n", 1)[1].split("\n   ```", 1)[0]
    return "\n".join(line[3:] if line.startswith("   ") else line
                     for line in block.splitlines()) + "\n"


@pytest.mark.parametrize("note", NOTE_PAIR, ids=["template", "dogfood"])
def test_prepare_rule_matches_reference_note(note):
    """RULE_TEXT is exactly the verified rule documented in the manual note."""
    assert cl.RULE_TEXT == _note_rule(note)
    assert not cl.RULE_BYTES.startswith(b"\xef\xbb\xbf")


# ---------------------------------------------------------------------------
# Preparation
# ---------------------------------------------------------------------------

def test_prepare_fresh_home_writes_only_rule_and_config(tmp_path):
    home, repo = tmp_path / "home", _repo(tmp_path)
    _prepare(home, repo)
    assert sorted(_snapshot(home)) == ["config.toml", "rules", "rules/default.rules"]
    assert (home / "rules" / "default.rules").read_bytes() == cl.RULE_BYTES
    config = (home / "config.toml").read_text(encoding="utf-8")
    key = cl.trust_key(repo, "win32")
    assert config == (
        f"{cl.BLOCK_BEGIN}\n[windows]\nsandbox = \"elevated\"\n\n"
        f"[projects.'{key}']\ntrust_level = \"trusted\"\n{cl.BLOCK_END}\n")
    assert key == key.lower() and "/" not in key


def test_prepare_is_idempotent_and_preserves_user_config(tmp_path):
    home, repo = tmp_path / "home", _repo(tmp_path)
    _prepare(home, repo)
    config = home / "config.toml"
    user_top = 'model = "x"\n\n'
    user_tail = '\n[profiles.p]\nmodel = "y"\n'
    config.write_text(user_top + config.read_text(encoding="utf-8") + user_tail, encoding="utf-8")

    _prepare(home, repo)
    text = config.read_text(encoding="utf-8")
    assert text.startswith(user_top)
    assert '[profiles.p]\nmodel = "y"' in text
    assert text.rstrip("\n").endswith(cl.BLOCK_END)
    assert text.index('[profiles.p]') < text.index(cl.BLOCK_BEGIN)

    before = _snapshot(home)
    plan = cl.plan_preparation(home, repo, "win32")
    assert {a["action"] for a in plan} == {"keep"}
    cl.apply_preparation(plan)
    assert _snapshot(home) == before

    other = tmp_path / "Other"
    (other / ".gator").mkdir(parents=True)
    _prepare(home, other)
    text = config.read_text(encoding="utf-8")
    assert f"[projects.'{cl.trust_key(repo, 'win32')}']" in text
    assert f"[projects.'{cl.trust_key(other, 'win32')}']" in text
    assert text.count(cl.BLOCK_BEGIN) == 1


def test_prepare_normalizes_known_generated_rule(tmp_path):
    home, repo = tmp_path / "home", _repo(tmp_path)
    (home / "rules").mkdir(parents=True)
    (home / "rules" / "default.rules").write_bytes(cl.RULE_TEXT.replace("\n", "\r\n").encode())
    _prepare(home, repo)
    assert (home / "rules" / "default.rules").read_bytes() == cl.RULE_BYTES


def test_config_non_windows_has_no_windows_table(tmp_path):
    text = cl.render_config("", "/srv/repo", "linux")
    assert "[windows]" not in text
    assert "[projects.'/srv/repo']" in text


def _seed(home, rule=None, extra=None, config=None):
    (home / "rules").mkdir(parents=True)
    if rule is not None:
        (home / "rules" / "default.rules").write_bytes(rule)
    if extra:
        (home / "rules" / extra).write_text("prefix_rule(pattern=['x'], decision='allow')\n")
    if config is not None:
        (home / "config.toml").write_text(config, encoding="utf-8")


@pytest.mark.parametrize("case", [
    "unfamiliar-rule", "extra-rule-file", "user-windows", "user-windows-dotted",
    "user-trust-entry", "begin-without-end", "duplicate-begin",
])
def test_prepare_fails_closed_without_writing(tmp_path, case):
    home, repo = tmp_path / "home", _repo(tmp_path)
    key = cl.trust_key(repo, "win32")
    if case == "unfamiliar-rule":
        _seed(home, rule=b"prefix_rule(pattern=['gator'], decision='allow')\n")
    elif case == "extra-rule-file":
        _seed(home, rule=cl.RULE_BYTES, extra="mine.rules")
    elif case == "user-windows":
        _seed(home, config='[windows]\nsandbox = "unelevated"\n')
    elif case == "user-windows-dotted":
        _seed(home, config='windows.sandbox = "unelevated"\n')
    elif case == "user-trust-entry":
        _seed(home, config=f"[projects.'{key.upper()}']\ntrust_level = \"untrusted\"\n")
    elif case == "begin-without-end":
        _seed(home, config=f"{cl.BLOCK_BEGIN}\n[windows]\n")
    elif case == "duplicate-begin":
        _seed(home, config=f"{cl.BLOCK_BEGIN}\n{cl.BLOCK_BEGIN}\n{cl.BLOCK_END}\n")
    before = _snapshot(home)
    with pytest.raises(cl.ProfileError) as exc:
        cl.plan_preparation(home, repo, "win32")
    assert cl.MANUAL_NOTE in str(exc.value)
    assert _snapshot(home) == before


def test_config_refuses_unquotable_repo_path(tmp_path):
    with pytest.raises(cl.ProfileError):
        cl.trust_key(tmp_path / "it's", "win32")


def test_config_strips_bom_and_keeps_line_endings(tmp_path):
    home, repo = tmp_path / "home", _repo(tmp_path)
    (home / "rules").mkdir(parents=True)
    (home / "config.toml").write_bytes(b"\xef\xbb\xbfmodel = \"x\"\r\n")
    _prepare(home, repo)
    data = (home / "config.toml").read_bytes()
    assert data.startswith(b'model = "x"\r\n')
    assert b"\r\n" + cl.BLOCK_END.encode("utf-8") + b"\r\n" in data


# ---------------------------------------------------------------------------
# Home validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("where", ["normal-codex", "caller-codex-home", "inside-repo", "under-temp"])
def test_home_validation_refuses(tmp_path, monkeypatch, where):
    fake_user = tmp_path / "user"
    monkeypatch.setattr(cl.Path, "home", classmethod(lambda cls: fake_user))
    repo = _repo(tmp_path)
    env, tempdir = {}, tmp_path / "temp"
    home = {
        "normal-codex": fake_user / ".codex",
        "caller-codex-home": tmp_path / "elsewhere",
        "inside-repo": repo / ".codex-loop",
        "under-temp": tempdir / "loop-home",
    }[where]
    if where == "caller-codex-home":
        env["CODEX_HOME"] = str(tmp_path / "elsewhere")
    with pytest.raises(cl.ProfileError):
        cl.validate_home(home, repo, env, tempdir=tempdir)


def test_home_default_is_machine_local_and_accepted(tmp_path, monkeypatch):
    fake_user = tmp_path / "user"
    monkeypatch.setattr(cl.Path, "home", classmethod(lambda cls: fake_user))
    home = cl.default_home()
    assert home == fake_user / ".gator" / "adapters" / "codex" / "loop-home"
    assert cl.validate_home(home, _repo(tmp_path), {}, tempdir=tmp_path / "temp") == home.resolve()


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------

def test_dry_run_preview_is_read_only(tmp_path):
    home, repo = tmp_path / "home", _repo(tmp_path)
    before_home, before_repo = home.exists(), _snapshot(repo)
    actions = cl.plan_preparation(home, repo, "win32")
    text = cl.render_dry_run(actions, home, repo, "win32")
    assert not home.exists() and before_home is False
    assert _snapshot(repo) == before_repo
    assert str(home) in text and str(repo) in text
    assert f"[projects.'{cl.trust_key(repo, 'win32')}']" in text
    assert 'pattern = ["gator", "loop", ["status", "wait"' in text
    assert "CODEX_HOME=" in text and "nothing is written or launched" in text
    assert {a["action"] for a in actions} == {"mkdir", "write"}


def test_prepare_module_has_no_loop_state_imports():
    """The launcher cannot affect loop authority: no state-module imports."""
    src = (LOOP_DIR / "codex_launcher.py").read_text(encoding="utf-8")
    for mod in ("session", "state_machine", "submit", "host"):
        assert f"import {mod}" not in src and f"from {mod} " not in src


# ---------------------------------------------------------------------------
# Verification and launch (checkpoint 2)
# ---------------------------------------------------------------------------

import json as _json
import shutil as _shutil
import subprocess as _subprocess
import types as _types

ALLOW_OUT = _json.dumps({"matchedRules": [{"prefixRuleMatch": {
    "matchedPrefix": ["gator", "loop", "status"], "decision": "allow"}}], "decision": "allow"})
NO_MATCH_OUT = '{"matchedRules":[]}'


class FakeRun:
    """Records calls; answers `--version`, `execpolicy check`, and the launch."""

    def __init__(self, policy=None, launch_rc=0, version="codex-cli 0.144.1"):
        self.calls = []
        self.policy = policy or {}
        self.launch_rc = launch_rc
        self.version = version

    def __call__(self, cmd, **kw):
        self.calls.append((list(cmd), kw))
        if cmd[1:] == ["--version"]:
            return _types.SimpleNamespace(returncode=0, stdout=self.version, stderr="")
        if cmd[1:3] == ["execpolicy", "check"]:
            probe = tuple(cmd[cmd.index("--") + 1:])
            key = probe[:2] if probe[0] == "git" else probe[:3]
            default = ALLOW_OUT if key == ("gator", "loop", "status") else NO_MATCH_OUT
            rc, out = self.policy.get(key, (0, default))
            return _types.SimpleNamespace(returncode=rc, stdout=out, stderr="")
        return _types.SimpleNamespace(returncode=self.launch_rc, stdout="", stderr="")

    def launches(self):
        return [(c, kw) for c, kw in self.calls if c[1:2] not in (["--version"], ["execpolicy"])]


def _args(**kw):
    return _types.SimpleNamespace(dry_run=kw.get("dry_run", False), home=kw.get("home"))


def _run_main(tmp_path, monkeypatch, *, run=None, which=lambda name: "C:/bin/codex.CMD",
              platform="win32", governed=True, dry_run=False, env=None):
    fake_user = tmp_path / "user"
    monkeypatch.setattr(cl.Path, "home", classmethod(lambda cls: fake_user))
    repo = _repo(tmp_path) if governed else (tmp_path / "plain")
    repo.mkdir(exist_ok=True)
    home = tmp_path / "home"
    run = run or FakeRun()
    rc = cl.main(_args(dry_run=dry_run, home=str(home)), env=dict(env or {"PATH": "x"}),
                 platform=platform, which=which, run=run, cwd=repo, tempdir=tmp_path / "temp")
    return rc, run, repo, home


def test_launch_passes_codex_home_to_child_only(tmp_path, monkeypatch, capsys):
    before = dict(os.environ)
    rc, run, repo, home = _run_main(tmp_path, monkeypatch, run=FakeRun(launch_rc=7))
    assert rc == 7
    assert dict(os.environ) == before
    (cmd, kw), = run.launches()
    assert cmd == ["C:/bin/codex.CMD"]
    assert kw["cwd"] == str(repo)
    assert kw["env"]["CODEX_HOME"] == str(home.resolve())
    assert "shell" not in kw
    probes = [c for c, _ in run.calls if c[1:3] == ["execpolicy", "check"]]
    assert len(probes) == 3
    assert all(kw2["env"]["CODEX_HOME"] == str(home.resolve())
               for c, kw2 in run.calls if c[1:3] == ["execpolicy", "check"])
    out = capsys.readouterr().out
    assert "Trust cost" in out and "OUTSIDE the Codex sandbox" in out
    assert "sign in for this isolated Gator Loop profile" in out
    assert "warning: Codex" not in out


@pytest.mark.parametrize("probe,result", [
    (("gator", "loop", "status"), (0, NO_MATCH_OUT)),
    (("git", "write-tree"), (0, ALLOW_OUT)),
    (("gator", "loop", "end"), (0, ALLOW_OUT)),
    (("gator", "loop", "status"), (1, "")),
    (("git", "write-tree"), (0, "not json")),
], ids=["status-not-allowed", "write-tree-matched", "loop-end-matched", "nonzero-exit", "non-json"])
def test_launch_policy_gate_blocks_launch(tmp_path, monkeypatch, capsys, probe, result):
    run = FakeRun(policy={probe: result})
    rc, run, _repo_, _home = _run_main(tmp_path, monkeypatch, run=run)
    assert rc == 1
    assert run.launches() == []
    assert cl.MANUAL_NOTE in capsys.readouterr().err


@pytest.mark.parametrize("case", ["codex-missing", "non-windows", "not-governed"])
def test_launch_refusals_are_non_destructive(tmp_path, monkeypatch, capsys, case):
    kwargs = {
        "codex-missing": {"which": lambda name: None},
        "non-windows": {"platform": "linux"},
        "not-governed": {"governed": False},
    }[case]
    rc, run, _repo_, home = _run_main(tmp_path, monkeypatch, **kwargs)
    assert rc == 1
    assert not home.exists()
    assert run.calls == []
    assert cl.MANUAL_NOTE in capsys.readouterr().err


def test_launch_warns_on_unverified_version(tmp_path, monkeypatch, capsys):
    rc, run, _r, _h = _run_main(tmp_path, monkeypatch, run=FakeRun(version="codex-cli 0.150.0"))
    assert rc == 0
    assert "warning: Codex 0.150.0 is unverified" in capsys.readouterr().out
    assert len(run.launches()) == 1


def test_launch_recovery_hint_when_sign_in_did_not_complete(tmp_path, monkeypatch, capsys):
    rc, _run, _r, home = _run_main(tmp_path, monkeypatch, run=FakeRun(launch_rc=2))
    assert rc == 2
    err = capsys.readouterr().err
    assert f"CODEX_HOME={home.resolve()}" in err and "codex login" in err


def test_launch_skips_sign_in_note_when_home_has_login(tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    home.mkdir()
    (home / "auth.json").write_text("{}")
    for name in ("read_text", "read_bytes"):
        real = getattr(cl.Path, name)

        def guarded(self, *a, _real=real, **k):
            assert self.name != "auth.json", "auth.json must never be read"
            return _real(self, *a, **k)

        monkeypatch.setattr(cl.Path, name, guarded)
    rc, _run, _r, _h = _run_main(tmp_path, monkeypatch, run=FakeRun(launch_rc=0))
    assert rc == 0
    assert "sign in for this isolated" not in capsys.readouterr().out


def test_launch_dry_run_via_cli_routing_writes_nothing(tmp_path, monkeypatch, capsys):
    """`gator loop codex --dry-run --home H` routes through loop.cli to the launcher."""
    import cli as loop_cli
    repo = _repo(tmp_path)
    home = tmp_path / "home"
    monkeypatch.chdir(repo)
    called = {}
    real_main = cl.main

    def spy(args, **kw):
        called["args"] = args
        return real_main(args, tempdir=tmp_path / "temp", platform="win32", **kw)

    monkeypatch.setattr(cl, "main", spy)
    with pytest.raises(SystemExit) as exc:
        loop_cli.main(["codex", "--dry-run", "--home", str(home)])
    assert exc.value.code == 0
    assert called["args"].dry_run is True and called["args"].home == str(home)
    assert not home.exists()
    assert "nothing is written or launched" in capsys.readouterr().out


def test_launch_cli_has_no_token_argument():
    import cli as loop_cli
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), pytest.raises(SystemExit):
        loop_cli.main(["codex", "--help"])
    assert "--token" not in buf.getvalue()
    assert "--dry-run" in buf.getvalue() and "--home" in buf.getvalue()


@pytest.mark.skipif(_shutil.which("codex") is None, reason="Codex CLI not installed")
def test_launch_real_codex_execpolicy_proves_boundary(tmp_path):
    """Real `codex execpolicy check` against the canonical rule (no launch)."""
    rules = tmp_path / "rules" / cl.RULE_FILE
    rules.parent.mkdir()
    rules.write_bytes(cl.RULE_BYTES)
    env = cl.child_env(os.environ, tmp_path / "codex-home-unused")
    cl.check_policy(_shutil.which("codex"), rules, env, _subprocess.run)


@pytest.mark.parametrize("note", NOTE_PAIR, ids=["template", "dogfood"])
def test_launch_reference_note_documents_quick_setup(note):
    text = note.read_text(encoding="utf-8")
    assert "## Quick Setup: `gator loop codex`" in text
    assert "gator loop codex --dry-run" in text
    assert "~/.gator/adapters/codex/loop-home" in text


def test_launch_reference_note_pair_is_byte_identical():
    assert NOTE_PAIR[0].read_bytes() == NOTE_PAIR[1].read_bytes()
