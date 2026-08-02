"""Verify the post-gatorize `.gator/` layout against the contract.

Runs a real `gatorize` install into a temp directory (via importing
the script by path — no CLI) and asserts required directories, stub
files, and layout markers exist. Also validates the machine-identity
file format.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "src" / "gator_command" / "scripts"


REQUIRED_DIRS_ROOT = {
    "charters", "blueprints", "docs", "threads", "artifacts",
    "vault", "policies", "field-guides", "sessions", "procedures",
    ".includes",
}

REQUIRED_DIRS_INCLUDES = {
    "reference-notes",
    "procedures",
    "scripts",
}

REQUIRED_STUBS = {
    "mission.md",
    "roadmap.md",
    "inbox.md",
    "identity.md",
    "issues.md",
    "commit_draft.md",
    "patterns.md",
    "whiteboard.md",
    "commit_issues.md",
    "lint-allow.json",
    "config.json",
    "layout-version.json",
    ".gator-version",
}


def _load_gatorize_module():
    """Import gatorize.py under its own name for testing."""
    path = SCRIPTS_DIR / "gatorize.py"
    if not path.exists():
        pytest.skip(f"gatorize.py not present at {path}")

    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))

    spec = importlib.util.spec_from_file_location("gatorize", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gatorize_mod():
    return _load_gatorize_module()


def test_layout_reference_declares_required_dirs(reference_dir: Path) -> None:
    text = (reference_dir / "gator-directory-layout.md").read_text(encoding="utf-8")
    for d in REQUIRED_DIRS_ROOT:
        assert d in text, f"layout doc must mention required dir '{d}'"
    for d in REQUIRED_DIRS_INCLUDES:
        assert d in text, f"layout doc must mention includes dir '{d}'"


def test_layout_reference_declares_required_stubs(reference_dir: Path) -> None:
    text = (reference_dir / "gator-directory-layout.md").read_text(encoding="utf-8")
    stubs_referenced = {s for s in REQUIRED_STUBS if s in text}
    missing = REQUIRED_STUBS - stubs_referenced
    assert not missing, f"layout doc missing stub references: {missing}"


def test_gatorize_install_produces_required_layout(tmp_path: Path, gatorize_mod) -> None:
    """Full install into a real tmp git repo — assert every required entry exists.

    A real `git init` is required (not a stubbed `.git/` dir) because
    `install_git_hooks` calls `git config --local core.hooksPath` and
    reads `.git/hooks/`. A real installer regression MUST fail this
    test loudly — never convert exceptions to skips.
    """
    target = tmp_path / "sample-repo"
    target.mkdir()

    git_init = subprocess.run(
        ["git", "init", "--quiet", str(target)],
        capture_output=True, text=True,
    )
    assert git_init.returncode == 0, (
        f"git init failed in isolated env — cannot run layout contract: "
        f"{git_init.stderr}"
    )

    # Any exception below is a real contract violation and must surface.
    gatorize_mod.action_install_gator(target)

    gator_dir = target / ".gator"
    assert gator_dir.is_dir(), "gator install did not create .gator/"

    # Required root directories
    for d in REQUIRED_DIRS_ROOT:
        assert (gator_dir / d).is_dir(), f"missing required dir: .gator/{d}"

    # Required .includes/ subdirectories
    for d in REQUIRED_DIRS_INCLUDES:
        assert (gator_dir / ".includes" / d).is_dir(), (
            f"missing required includes dir: .gator/.includes/{d}"
        )

    # Required stubs at root
    for name in REQUIRED_STUBS:
        assert (gator_dir / name).exists(), f"missing stub: .gator/{name}"

    # Layout marker payload
    layout = json.loads((gator_dir / "layout-version.json").read_text(encoding="utf-8"))
    assert layout == {"layout": "v2"}, f"layout marker is {layout}, expected v2"

    # config.json default
    config = json.loads((gator_dir / "config.json").read_text(encoding="utf-8"))
    assert config.get("enforcement_level") == "strict", (
        "default enforcement_level must be 'strict'"
    )


# ── machine-identity file format ────────────────────────────────────

def _parse_kv(text: str) -> dict[str, str]:
    result = {}
    for line in text.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result


UUID_RE = __import__("re").compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def test_valid_machine_id_fixture_parses(fixtures_dir: Path) -> None:
    text = (fixtures_dir / "valid_machine_id.txt").read_text(encoding="utf-8")
    kv = _parse_kv(text)

    assert {"id", "hostname", "label", "created"} <= kv.keys(), (
        f"machine-id fixture missing required keys: got {kv.keys()}"
    )
    assert UUID_RE.match(kv["id"]), f"id must be a UUID: {kv['id']}"


def test_machine_id_reference_declares_kv_format(reference_dir: Path) -> None:
    text = (reference_dir / "machine-identity.md").read_text(encoding="utf-8")
    assert "key: value" in text or "key-value" in text.lower() or "kv" in text.lower()
    assert "uuid" in text.lower()
    assert "~/.gator/machine-id" in text
