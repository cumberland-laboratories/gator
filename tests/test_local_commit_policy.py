"""Machine-local commit policy (precommit_local_policy.py).

The policy is per engineer and per clone: Git's private area, never the
repository. These tests pin the shipped copies, the Enterprise check, and
the read/write behaviour; the hook integration lives in
test_precommit_override.py.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "src" / "gator_command" / "templates" / "gator-starter" / "scripts"
SCRIPTS = ROOT / "src" / "gator_command" / "scripts"

if str(TEMPLATE) not in sys.path:
    sys.path.insert(0, str(TEMPLATE))
import precommit_local_policy as lp  # noqa: E402


def _git_repo(tmp_path, name="repo"):
    repo = tmp_path / name
    (repo / ".gator").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    return repo


@pytest.mark.parametrize("name", ["precommit_local_policy.py", "gator-enforce.py"])
def test_shipped_copies_are_byte_identical(name):
    assert (TEMPLATE / name).read_bytes() == (SCRIPTS / name).read_bytes()


@pytest.mark.parametrize("marker", [
    None, '{"enabled": true}', '{"enabled": false}', '{"enabled": "true"}',
    "{not json", "[]", "42",
])
def test_enterprise_check_matches_gator_core(tmp_path, marker):
    """The starter scripts do not ship gator_core.is_enterprise_active();
    the module's own check must give the same answer."""
    sys.path.insert(0, str(SCRIPTS))
    try:
        from gator_core import is_enterprise_active
    finally:
        sys.path.remove(str(SCRIPTS))
    repo = tmp_path / "r"
    (repo / ".gator").mkdir(parents=True)
    if marker is not None:
        (repo / ".gator" / "enterprise.json").write_text(marker, encoding="utf-8")
    assert lp.enterprise_managed(repo) is is_enterprise_active(repo / ".gator")


def test_default_is_strict_and_warn_round_trips_outside_the_repository(tmp_path):
    repo = _git_repo(tmp_path)
    assert lp.read_level(repo) == "strict"
    path = lp.write_level(repo, "warn")
    assert path == lp.policy_path(repo) and path.is_file()
    assert ".git" in path.parts and not (repo / ".gator" / lp.POLICY_FILENAME).exists()
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "schema": lp.POLICY_SCHEMA, "level": "warn"}
    assert lp.read_level(repo) == "warn"
    status = subprocess.run(["git", "status", "--porcelain", "--ignored"], cwd=repo,
                            capture_output=True, text=True).stdout
    assert lp.POLICY_FILENAME not in status
    lp.write_level(repo, "strict")
    assert not path.exists() and lp.read_level(repo) == "strict"


@pytest.mark.parametrize("content", ["{bad", '{"level": "off"}', '{"level": "loose"}', "[]"])
def test_invalid_file_reads_as_strict(tmp_path, content):
    repo = _git_repo(tmp_path)
    lp.policy_path(repo).write_text(content, encoding="utf-8")
    assert lp.read_level(repo) == "strict"


def test_off_is_not_a_local_level(tmp_path):
    repo = _git_repo(tmp_path)
    with pytest.raises(ValueError):
        lp.write_level(repo, "off")
    assert not lp.policy_path(repo).exists()


def test_enterprise_managed_is_strict_and_refuses_writes(tmp_path):
    repo = _git_repo(tmp_path)
    lp.write_level(repo, "warn")
    (repo / ".gator" / "enterprise.json").write_text('{"enabled": true}', encoding="utf-8")
    assert lp.read_level(repo) == "strict"
    with pytest.raises(lp.LocalPolicyError):
        lp.write_level(repo, "strict")


@pytest.mark.parametrize("config,expected", [
    ({"enforcement_level": "warn"}, "warn"), ({"enforcement_level": "off"}, "off"),
    ({"enforcement_level": "strict"}, None), ({}, None),
])
def test_tracked_relaxation_is_only_reported(tmp_path, config, expected):
    repo = _git_repo(tmp_path)
    (repo / ".gator" / "config.json").write_text(json.dumps(config), encoding="utf-8")
    assert lp.tracked_relaxation(repo / ".gator") == expected
    assert lp.read_level(repo) == "strict"   # never applied


def test_gator_enforce_writes_only_the_local_file(tmp_path):
    repo = _git_repo(tmp_path)
    (repo / ".gator" / "config.json").write_text('{"enforcement_level": "strict"}\n',
                                                 encoding="utf-8")
    before = (repo / ".gator" / "config.json").read_bytes()
    r = subprocess.run([sys.executable, str(SCRIPTS / "gator-enforce.py"), "--level", "warn",
                        "--repo", str(repo)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert lp.read_level(repo) == "warn"
    assert (repo / ".gator" / "config.json").read_bytes() == before
    r = subprocess.run([sys.executable, str(SCRIPTS / "gator-enforce.py"), "--level", "off",
                        "--repo", str(repo)], capture_output=True, text=True)
    assert r.returncode != 0
