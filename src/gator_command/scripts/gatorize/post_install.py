"""Post-install wiring: outbox, product source, registry, summary.

These run in the common tail of every gatorize scenario.
All functions that need startup globals receive them as parameters.
"""

import json
from pathlib import Path

from gatorize.helpers import git, log_step


def action_install_outbox(target):
    """Create outbox.md stub."""
    outbox = target / "outbox.md"
    if outbox.exists():
        text = outbox.read_text(encoding="utf-8", errors="replace")
        lines = [l for l in text.splitlines() if l.strip() and not l.startswith("#") and not l.startswith("---")]
        if lines:
            log_step("outbox.md already exists with content — preserved")
            return
    outbox.write_text(
        "# Outbox\n\n"
        "Messages for Gator Command. The Architect triages these during command post sessions.\n"
        "Do not clear this file from the project repo — the command post session clears\n"
        "entries after processing.\n\n---\n\n",
        encoding="utf-8",
    )
    log_step("Created outbox.md")


def action_install_product_source(target, scripts_dir, today):
    """Write .gator/product-source.json.

    Args:
        target: Path to the repo being gatorized.
        scripts_dir: Path to the scripts directory.
        today: Date string (YYYY-MM-DD).
    """
    pkg_root = scripts_dir.parent  # src/gator_command/ or site-packages/gator_command/
    gator_root = str(pkg_root)
    template_dir = ""
    root = Path(gator_root)
    if (root / "gator-engine" / "templates" / "gator-starter").is_dir():
        template_dir = "gator-engine/templates/gator-starter"
    elif (root / "templates" / "gator-starter").is_dir():
        template_dir = "templates/gator-starter"
    elif (root / "gator-command" / "templates" / "gator-starter").is_dir():
        template_dir = "gator-command/templates/gator-starter"

    (target / ".gator" / "product-source.json").write_text(
        json.dumps({
            "gator_root": gator_root,
            "template_dir": template_dir,
            "installed": today,
            "updated": today,
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    log_step(f"Wrote product-source.json (source: {gator_root})")


def action_register(target, today):
    """Register repo in the machine-local dashboard registry.

    Args:
        target: Path to the repo being gatorized.
        today: Date string (YYYY-MM-DD).
    """
    try:
        from gator_core import add_dashboard_repo
        if add_dashboard_repo(target):
            log_step(f"Added to dashboard registry")
        else:
            log_step(f"{target.name} already registered.")
    except Exception:
        pass  # non-critical — dashboard registry is a convenience


def print_summary(target, scenario, current_branch):
    """Print SUCCESS banner.

    Args:
        target: Path to the repo being gatorized.
        scenario: Install scenario number (1-5).
        current_branch: Branch the user is now on (captured post-dispatch by
            the caller via `git rev-parse --abbrev-ref HEAD`). Every scenario
            has a valid current branch by the time this runs — Scenario 1's
            `action_git_init()` has already created the initial branch.
            Fallback string like "(current branch)" is acceptable if the
            caller could not read the branch (detached HEAD, mid-install
            corruption); the summary still prints.
    """
    repo_name = target.name
    print()
    print("  ================================================================")
    print(f"  Gatorized: {repo_name}")
    print("  ================================================================")
    print()

    # Finalization — describe the branch the user is now on and how to keep
    # the changes. No branch merge/delete dance: gatorize operates on the
    # current branch in place as of v2.4.0.
    print(f"  You are on the '{current_branch}' branch. To keep the changes:")
    print()
    print(f"      cd {target}")
    print(f"      git add -A && git commit -m 'Gatorize: install .gator/ governance layer'")
    print()

    # Honest recovery paragraph. The safety-branch pattern is the load-bearing
    # recommendation. `git checkout .` doesn't remove untracked new files, and
    # `git reset --hard` is risky once dirty-tree continuation is a supported
    # path — so we do NOT promise clean rollback for a fresh install; we
    # describe git-native recipes scoped to what they actually undo.
    print("  Not what you wanted?")
    print("    - If you created your own experiment branch BEFORE running gatorize")
    print("      (e.g., git checkout -b my-gator-experiment), switch back and delete it:")
    print(f"        git checkout <original-branch> && git branch -D <experiment-branch>")
    print("    - If you ran gatorize directly on your working branch, undo depends on what happened:")
    print("        * uncommitted new files (.gator/, entry-point files): git clean -fd <specific paths>")
    print("          Review with `git clean -nd` first — clean also removes any OTHER untracked files.")
    print("        * uncommitted edits inside existing tracked files: git checkout -- <path>")
    print("        * committed changes: git reset --hard HEAD~<N>, but only if HEAD~<N> is safe.")
    print("    - The safety-branch pattern (create-your-own-branch-first) is the supported clean-undo path.")
    print("      Anything else is scenario-dependent and requires knowing exactly what gatorize touched.")
    print()

    print("  ================================================================")
    print("  SUCCESS")
    print("  ================================================================")
    print()
    print("  What to do now:")
    print()
    print(f"    1. cd {target}")
    print(f"    2. Launch your AI coding tool (Claude Code, Codex, Gemini, etc.)")
    print(f"    3. Type: gator init")
    print(f"    4. The agent will read the constitution and orient to the project.")
    print(f"       Your first git commit fires the governance hooks.")
    print()
    print(f"  Enforcement: strict (commit gate active)")
    print()
