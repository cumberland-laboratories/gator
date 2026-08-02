"""
Shared fixtures for Gator Command test suite.

Provides mock directory structures for command-post and governed-repo
scenarios, plus an import helper for hyphenated script names.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

# Ensure scripts/ is on sys.path for gator_core imports
SCRIPTS_DIR = Path(__file__).parent.parent / "src" / "gator_command" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def load_script(name, search_dir=None):
    """Import a gator script by hyphenated filename.

    Handles the hyphen-to-underscore problem for Python imports.
    """
    scripts_dir = search_dir or SCRIPTS_DIR
    path = scripts_dir / f"{name}.py"
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), path
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mock_command_post(tmp_path):
    """Create a minimal command-post directory tree.

    Returns the command-post root path (parent of gator-command/).
    """
    cp = tmp_path / "cp"
    gc = cp / "gator-command"

    # Core files
    (gc / "active-threads").mkdir(parents=True)
    (gc / "artifacts").mkdir()
    (gc / "templates" / "gator-starter" / "scripts").mkdir(parents=True)

    (gc / "mission.md").write_text("# Mission\n\nTest mission.\n")
    (gc / "inbox.md").write_text("# Inbox\n\n---\n\n- Item one\n- Item two\n")
    (gc / "issues.md").write_text(
        "# Issues\n\n"
        "### Bug A\n**Status**: Open\n\n"
        "### Bug B\n**Status**: Resolved\n\n"
        "### Bug C\n**Status**: Working\n"
    )
    (gc / "org-policy.md").write_text("version: 2026-05-29\n\n# Org Policy\n")

    # Registry with two repos
    (gc / "registry.md").write_text(
        "# Registry\n\n"
        "| Repo | Path | Remote | Registered | Status |\n"
        "|------|------|--------|------------|--------|\n"
        f"| test-repo | {tmp_path / 'repos' / 'test-repo'} | — | 2026-05-25 | active |\n"
        f"| other-repo | {tmp_path / 'repos' / 'other-repo'} | github.com/org/other | 2026-05-26 | active |\n"
    )

    return cp


@pytest.fixture
def mock_gator_repo(tmp_path):
    """Create a minimal governed repo with .gator/ directory.

    Returns (repo_root, gator_dir).
    """
    repo = tmp_path / "repos" / "test-repo"
    gator = repo / ".gator"

    # Directory structure
    (gator / "charters").mkdir(parents=True)
    (gator / "active-threads").mkdir()
    (gator / "scripts" / "hooks").mkdir(parents=True)

    # .gator-version
    (gator / ".gator-version").write_text(
        "generation: 2\ninstalled: 2026-05-25\nsource: gator-command\n"
    )

    # command-post.md (thin link)
    (gator / "command-post.md").write_text(
        "command-post: ../../cp\n"
        f"command-post-absolute: {tmp_path / 'cp'}\n"
        "version: 2026-05-29\n"
    )

    # Constitution with known rule patterns
    (gator / "constitution.md").write_text(
        "# Constitution\n\n"
        "1. **Before changing code**: read the charter\n"
        "2. **After changing code**: update the charter\n"
        "- **BRANCHING**: use dev branch\n"
        "- **COMMITS**: use commit_draft.md\n"
        "**The agent always asks before committing.**\n"
    )

    # One charter with function entries
    (gator / "charters" / "core.md").write_text(
        "# Core Module\n\n"
        "### parse_config(path)\nReads config file.\n\n"
        "### validate_input(data)\nValidates user input.\n\n"
        "### process_data(records)\nProcesses a batch of records.\n"
    )
    (gator / "charters" / "README.md").write_text("# Charters\n")
    (gator / "charters" / "_template.md").write_text("# Template\n")

    # One active thread
    (gator / "active-threads" / "design.md").write_text(
        "# Design Thread\n\nSome design notes.\n"
    )

    # Issues
    (gator / "issues.md").write_text(
        "# Issues\n\n"
        "### Issue 1\n**Status**: Open\n\n"
        "### Issue 2\n**Status**: Resolved\n"
    )

    # commit_draft.md with frontmatter
    (gator / "commit_draft.md").write_text(
        "---\n"
        "message: Test commit\n"
        "significance: routine\n"
        "change-type: fix\n"
        "decision-tags: [bugfix, testing]\n"
        "---\n\n"
        "Fixed the parsing bug in core module.\n"
    )

    # Hook source (presence marker)
    (gator / "scripts" / "hooks" / "pre-commit").write_text("#!/bin/sh\nexit 0\n")

    # Pre-commit script (required by plan_hook_updates)
    (gator / "scripts" / "gator-pre-commit.py").write_text("# gator pre-commit script\n")

    # Enforcer files
    (gator / "scripts" / "enforcer-prompt.md").write_text("# Enforcer\n")
    (gator / "scripts" / "enforcer-review.py").write_text("# review\n")

    # Real git repo so core.hooksPath config works in tests
    import subprocess
    result = subprocess.run(
        ["git", "init", str(repo)],
        capture_output=True, timeout=10,
    )
    assert result.returncode == 0, f"git init failed: {result.stderr}"
    # Seed a dummy hook in legacy location for stale-hook tests
    (repo / ".git" / "hooks").mkdir(parents=True, exist_ok=True)
    (repo / ".git" / "hooks" / "pre-commit").write_text("#!/bin/sh\nexit 0\n")

    return repo, gator
