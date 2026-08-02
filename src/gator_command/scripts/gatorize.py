#!/usr/bin/env python3
"""
gatorize.py — The canonical Gator installer (Python).

Cross-platform: Windows CMD/PowerShell, Git Bash, macOS Terminal, Linux.

Usage:
    python gatorize.py <target-directory>
    python gatorize.py .

Handles five scenarios:
  1. Fresh directory (no git)        → git init + install
  2. Git repo, clean                 → install
  3. Git repo, has .gator/           → run update
  4. Git repo, has memex structure   → morph memex → gator
  5. Git repo, has both              → warn, let user choose

@reads: templates in gator-starter/
@writes: target .gator/, entry points, hooks, registry
"""

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
# Scripts are at src/gator_command/scripts/ — repo root is 3 levels up in a checkout.
REPO_ROOT = SCRIPTS_DIR.parent.parent.parent  # Best guess at repo root from script location

sys.path.insert(0, str(SCRIPTS_DIR))
from gator_core import ensure_utf8_stdout, import_sibling  # noqa: E402

# ── extracted modules ─────────────────────────────────────────────────────────
from gatorize import helpers  # noqa: E402  (for helpers.set_auto_yes)
from gatorize.helpers import (  # noqa: E402
    git, log_step, prompt, confirm, copy_tree_overlay,
    GATOR_MARKER, COMMAND_POST_MARKER,
)
from gatorize.vendor_hooks import (  # noqa: E402
    merge_hooks_into_settings, install_vendor_hooks,
    _extract_hook_commands, VENDOR_HOOK_CONFIGS,
)
from gatorize.entry_points import (  # noqa: E402
    render_entry_content, action_install_entry_points,
    GATOR_BEGIN, GATOR_END,
)
from gatorize.post_install import (  # noqa: E402
    action_install_outbox,
    action_install_product_source, action_register, print_summary,
)
from gatorize.morph import (  # noqa: E402
    detect_legacy_memex, action_morph_memex,
)

# ── constants ──────────────────────────────────────────────────────────────

TODAY = datetime.now().strftime("%Y-%m-%d")
NOW = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
# GATOR_MARKER, COMMAND_POST_MARKER: see gatorize/helpers.py

# Detect template directory
TEMPLATES = None
for tpl_rel in ("templates/gator-starter", "../templates/gator-starter"):
    candidate = (SCRIPTS_DIR.parent / tpl_rel).resolve()
    if candidate.is_dir():
        TEMPLATES = candidate
        break
if not TEMPLATES:
    # Try gator-engine layout
    for tpl_rel in ("gator-engine/templates/gator-starter",
                     "gator-command/templates/gator-starter"):
        candidate = (REPO_ROOT / tpl_rel).resolve()
        if candidate.is_dir():
            TEMPLATES = candidate
            break

# Read generation from gator_core.py
GATOR_GEN = 2
try:
    from gator_core import CURRENT_GENERATION
    GATOR_GEN = CURRENT_GENERATION
except ImportError:
    pass


# ── helpers: see gatorize/helpers.py


# ── detection ──────────────────────────────────────────────────────────────

def detect_scenario(target):
    """Returns scenario number 1-5."""
    has_git = (target / ".git").is_dir()
    has_gator = (target / ".gator").is_dir()
    has_memex = (target / "memex").is_dir() or (target / ".memex").is_dir()

    if not has_git and not has_memex and not has_gator:
        return 1
    if has_git and not has_memex and not has_gator:
        return 2
    if has_git and not has_memex and has_gator:
        return 3
    if has_git and has_memex and not has_gator:
        return 4
    if has_git and has_memex and has_gator:
        return 5
    # Edge: memex without git
    print("  Error: memex structure found but no git. Initialize git first.")
    sys.exit(1)


def detect_generation(target):
    """Returns generation number of existing .gator/."""
    version_file = target / ".gator" / ".gator-version"
    if version_file.exists():
        for line in version_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("generation:"):
                try:
                    return int(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
        return 2
    return 0


# ── git operations ─────────────────────────────────────────────────────────

def _git_default_branch():
    """Read git's init.defaultBranch setting, or 'main' if unset."""
    name, ok = git("config", "--get", "init.defaultBranch")
    return name if (ok and name) else "main"


def action_git_init(target):
    """Scenario 1: initialize git in a fresh directory.

    Creates the repo, makes an initial commit, and leaves the caller on
    git's default branch (init.defaultBranch or 'main'). Does NOT create a
    gator-install safety branch — that pattern was retired in v2.4.0 (see
    plan 2026-07-30-retire-gator-install-branch-implementation-plan.md,
    Stage 3).
    """
    default_branch = _git_default_branch()
    print()
    log_step(f"Initializing git in {target}...")
    git("init", cwd=target)
    # Ensure we are on the configured default branch
    branch, _ = git("branch", "--show-current", cwd=target)
    if branch != default_branch:
        git("branch", "-M", default_branch, cwd=target)
    # Initial commit
    files = [f for f in target.iterdir() if f.name != ".git"]
    if files:
        git("add", "-A", cwd=target)
        git("commit", "-m", "Initial commit (pre-Gator)", cwd=target)
    else:
        git("commit", "--allow-empty", "-m", "Initial commit (pre-Gator)", cwd=target)
    log_step(f"On '{default_branch}' (git initialized).")


# ── install ────────────────────────────────────────────────────────────────

def action_install_gator(target):
    """Fresh install of .gator/ from templates (v2 layout).

    v2 layout: user-authored content at .gator/ root, shipped Gator-native
    content in .gator/.includes/. See gator_layout.py for the ownership model.
    """
    log_step(f"Installing .gator/ (v2 layout) into {target}...")

    gator_dir = target / ".gator"
    includes = gator_dir / ".includes"

    # Create user-visible directory structure at .gator/ root
    for d in ["charters", "blueprints", "docs", "threads", "artifacts",
              "vault", "policies", "field-guides", "sessions", "procedures"]:
        (gator_dir / d).mkdir(parents=True, exist_ok=True)

    # Create .includes/ for shipped content
    includes.mkdir(parents=True, exist_ok=True)

    # Shipped root files → .includes/
    for name in ("constitution.md", "gator-start-up.md"):
        src = TEMPLATES / name
        if src.exists():
            shutil.copy2(src, includes / name)

    # Shipped .charterignore → .includes/
    charterignore_src = TEMPLATES / "charterignore"
    if charterignore_src.exists():
        shutil.copy2(charterignore_src, includes / ".charterignore")

    # Charter scaffolding (user-facing reference) → .gator/charters/ (root)
    for name in ("README.md", "_template.md"):
        src = TEMPLATES / "charters" / name
        if src.exists():
            shutil.copy2(src, gator_dir / "charters" / name)

    # Blueprint scaffolding (user-facing reference) → .gator/blueprints/ (root)
    for name in ("README.md", "_template.md"):
        src = TEMPLATES / "blueprints" / name
        if src.exists():
            shutil.copy2(src, gator_dir / "blueprints" / name)

    # Shipped reference-notes → .includes/reference-notes/
    refnotes_src = TEMPLATES / "reference-notes"
    if refnotes_src.is_dir():
        (includes / "reference-notes").mkdir(exist_ok=True)
        copy_tree_overlay(refnotes_src, includes / "reference-notes")

    # Shipped procedures → split: scaffolding to root, content to .includes/
    procedures_src = TEMPLATES / "procedures"
    if procedures_src.is_dir():
        (includes / "procedures").mkdir(exist_ok=True)
        for f in procedures_src.iterdir():
            if f.is_file():
                if f.name in ("README.md", "_template.md"):
                    # Scaffolding → user-visible root
                    shutil.copy2(str(f), str(gator_dir / "procedures" / f.name))
                else:
                    # Shipped procedure → .includes/
                    shutil.copy2(str(f), str(includes / "procedures" / f.name))

    # Scripts → .includes/scripts/ (including hooks/)
    scripts_src = TEMPLATES / "scripts"
    if scripts_src.is_dir():
        (includes / "scripts").mkdir(exist_ok=True)
        copy_tree_overlay(scripts_src, includes / "scripts")

    # User-content directories get template content directly (not shipped —
    # these are starter content like docs/, artifacts/, threads/)
    for subdir in ("docs", "artifacts", "threads", "policies", "field-guides", "vault"):
        src_dir = TEMPLATES / subdir
        if src_dir.is_dir():
            copy_tree_overlay(src_dir, gator_dir / subdir)

    # Slash commands (not in .gator/ — goes to .claude/commands/)
    commands_src = TEMPLATES / "commands"
    if commands_src.is_dir():
        claude_commands = target / ".claude" / "commands"
        claude_commands.mkdir(parents=True, exist_ok=True)
        copy_tree_overlay(commands_src, claude_commands)

    # Vendor SessionStart hook configs (merge-safe)
    install_vendor_hooks(TEMPLATES, target)

    # Install hooks (wrappers point to .includes/scripts/ for v2)
    install_hooks(target)

    # Write stubs (user-content stubs at .gator/ root)
    write_stubs(gator_dir)

    # Write layout version marker
    import json
    (gator_dir / "layout-version.json").write_text(
        json.dumps({"layout": "v2"}) + "\n", encoding="utf-8"
    )

    # Write version
    write_gator_version(gator_dir, "install")

    log_step(".gator/ installed (v2 layout).")


# ── vendor hooks: see gatorize/vendor_hooks.py


def install_hooks(target):
    """Install git hooks."""
    # Use the shared hook installer from gator-update.py — one definition of
    # "correctly installed hooks" across gatorize, gator-update, and gator-init.
    gator_update = import_sibling("gator-update")
    probe_dirs = gator_update.get_hook_probe_dirs(target)

    for hooks_dir in probe_dirs:
        for hook_name in ("pre-commit", "commit-msg", "post-commit"):
            dest = hooks_dir / hook_name
            if not dest.exists():
                continue
            content = dest.read_text(encoding="utf-8", errors="replace")
            if "Gator" in content or "gator" in content:
                continue
            backup = dest.with_suffix(".pre-gator")
            shutil.copy2(dest, backup)

    gator_update.install_git_hooks(target / ".gator", target)
    log_step("Git hooks installed.")


def write_stubs(gator_dir):
    """Write stub content files (only if missing)."""
    stubs = {
        "mission.md": "# Mission\n\n[What are we building and why?]\n",
        "roadmap.md": "# Roadmap\n\n[Priority-ordered. Updated as items complete.]\n\n"
                      "**Status key**: Done · Building · Designed · Considering · Deferred\n",
        "inbox.md": "# Inbox\n\nDrop anything here. No formatting needed.\n\n---\n\n",
        "identity.md": "---\noperating-mode: designer\n---\n\n# Identity\n\n"
                       "## Basics\n\n- **Name**: [Your name]\n- **Location**: [Your timezone]\n"
                       "- **Role**: [Your role]\n",
        "issues.md": "# Issues\n\nActive bugs, blockers, and known fragilities.\n\n"
                     "**Status key**: Open · Working · Resolved\n\n---\n\n",
        "commit_draft.md": "---\nmessage: \"\"\nchange-type:\nsignificance:\n"
                           "decision-tags: []\nagent:\narchitect:\n---\n\n"
                           "# Session Change Log\n\n",
        "patterns.md": "# Patterns\n\nRecurring rhythms, obligations, schedules.\n\n---\n\n",
        "whiteboard.md": "# Whiteboard\n\nNo findings.\n",
    }

    for name, content in stubs.items():
        path = gator_dir / name
        if not path.exists():
            path.write_text(content, encoding="utf-8")

    # JSON stubs
    lint_allow = gator_dir / "lint-allow.json"
    if not lint_allow.exists():
        lint_allow.write_text("[]", encoding="utf-8")

    commit_issues = gator_dir / "commit_issues.md"
    if not commit_issues.exists():
        commit_issues.write_text("# Commit Issues\n\nNo findings.\n", encoding="utf-8")

    config = gator_dir / "config.json"
    if not config.exists():
        config.write_text('{\n  "enforcement_level": "strict"\n}\n', encoding="utf-8")

    # Charter INDEX
    index = gator_dir / "charters" / "INDEX.md"
    if not index.exists():
        index.write_text(
            "# Charter Index\n\n**Always read first:** [Cross-Cutting](cross-cutting.md) (when it exists)\n\n"
            "| If you're changing... | Read these charters |\n|---|---|\n| | |\n",
            encoding="utf-8",
        )

    # Sessions .gitignore
    sessions_gi = gator_dir / "sessions" / ".gitignore"
    sessions_gi.parent.mkdir(exist_ok=True)
    if not sessions_gi.exists():
        sessions_gi.write_text("_active/\n", encoding="utf-8")

    # Vault — gitignored directory for sensitive material and large files
    vault_dir = gator_dir / "vault"
    vault_dir.mkdir(exist_ok=True)
    vault_gitkeep = vault_dir / ".gitkeep"
    if not vault_gitkeep.exists():
        vault_gitkeep.write_text("", encoding="utf-8")
    ensure_repo_gitignore(gator_dir.parent)


def ensure_repo_gitignore(repo_root):
    """Ensure standard gitignore rules exist in the repo's .gitignore.

    Called on both fresh install and upgrade paths so all governed repos
    converge on the same set of ignore rules.
    """
    repo_gi = repo_root / ".gitignore"
    gi_rules = {
        ".gator/vault/": "# Vault — sensitive material and large files",
        ".gator/active-vendor-session.json": "# Vendor session identity (machine-local)",
        ".gator/session-blocks/": "# Session blocks — local-only transcript evidence",
        ".gator/whiteboard.md": "# Hook ephemera — written and cleared each commit cycle",
        ".gator/commit_draft.md": "# Hook ephemera — commit message source, reset after commit",
        ".gator/status.json": "# Hook ephemera — pre-commit validation state",
        ".vscode/": "# IDE settings",
        "__pycache__/": "# Python cache",
        "AGENTS.local.md": "# Local agent companion — personal notes/skills (machine-local)",
        "CLAUDE.local.md": "# Local agent companion — personal notes/skills (machine-local)",
        "GEMINI.local.md": "# Local agent companion — personal notes/skills (machine-local)",
    }
    if repo_gi.exists():
        gi_text = repo_gi.read_text(encoding="utf-8", errors="replace")
    else:
        gi_text = ""
    additions = []
    for rule, comment in gi_rules.items():
        if rule not in gi_text:
            additions.append(f"{comment}\n{rule}")
    if additions:
        with open(repo_gi, "a" if gi_text else "w", encoding="utf-8") as f:
            f.write("\n" + "\n".join(additions) + "\n")


def write_gator_version(gator_dir, action):
    """Write .gator-version with generation and timestamps."""
    version_file = gator_dir / ".gator-version"

    # Preserve install date on upgrade
    installed = TODAY
    if version_file.exists():
        for line in version_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("installed:"):
                prev = line.split(":", 1)[1].strip()
                if prev:
                    installed = prev

    # Resolve CLI version for tracking
    cli_ver = ""
    try:
        from gator_core import get_version
        cli_ver = get_version()
    except ImportError:
        pass

    version_file.write_text(
        f"generation: {GATOR_GEN}\n"
        f"installed: {installed}\n"
        f"updated: {NOW}\n"
        f"action: {action}\n"
        f"installer: gatorize.py\n"
        f"cli-version: {cli_ver}\n",
        encoding="utf-8",
    )


# ── entry points: see gatorize/entry_points.py
# ── post-install: see gatorize/post_install.py
# ── memex morph: see gatorize/morph.py


# ── main ───────────────────────────────────────────────────────────────────

# ── Stage 3: pre-action preview + dirty-tree gate ─────────────────────────────

SCENARIO_DESCRIPTIONS = {
    1: "fresh directory — will initialize git",
    2: "existing git repo, no .gator/",
    3: "existing .gator/, upgrade in place",
    4: "legacy memex, migrate + install",
    5: "both memex and gator present",
}


def print_pre_action_summary(target, scenario):
    """Print a scenario-aware preview of what gatorize is about to do.

    Scenario 1 has no git repo yet, so it omits the branch name and the
    safety-branch hint. Scenarios 2-5 name the current branch and offer
    the safety-branch pattern as the honest recovery path.
    """
    description = SCENARIO_DESCRIPTIONS.get(scenario, "unknown scenario")
    print()
    if scenario == 1:
        print(f"  Gatorizing new directory at {target}.")
        print(f"  Scenario: {scenario} ({description})")
        print("  This will:")
        print("    - Initialize git and create the default branch "
              "(from git's init.defaultBranch config, or 'main')")
        print("    - Add .gator/")
        print("    - Install entry-point files (CLAUDE.md, AGENTS.md, GEMINI.md)")
        print("    - Install git hooks")
        print("    - Install vendor SessionStart hook configs (.claude, .codex, .gemini)")
        print("    - Add gitignore entries")
        print("  No safety-branch pattern applies here — the directory has no git history yet.")
    else:
        current_branch, _ = git("rev-parse", "--abbrev-ref", "HEAD", cwd=target)
        current_branch = current_branch or "(unknown)"
        print(f"  Gatorizing branch '{current_branch}' at {target}.")
        print(f"  Scenario: {scenario} ({description})")
        print("  This will:")
        print("    - Add or refresh .gator/")
        print("    - Install/refresh entry-point files (CLAUDE.md, AGENTS.md, GEMINI.md)")
        print("    - Install git hooks")
        print("    - Install vendor SessionStart hook configs (.claude, .codex, .gemini)")
        print("    - Add gitignore entries")
        print("  Want a safety branch? Cancel and run: "
              "git checkout -b my-gator-experiment")
    print()


def _check_dirty_tree_and_gate(target):
    """Refuse dirty tree under --yes, prompt continue/abort interactively.

    Returns None on proceed, calls sys.exit() on abort. Scenario 1 callers
    do not reach this — it's guarded on has-git in main().
    """
    status, _ = git("status", "--porcelain", cwd=target)
    if not status:
        return
    if helpers.get_auto_yes():
        print()
        print("  Error: gatorize refuses to run on a dirty tree in non-interactive mode.")
        print("  Commit or stash your changes first, then re-run.")
        sys.exit(1)
    print()
    print(f"  Warning: uncommitted changes detected in {target}.")
    print("  Strongly recommend committing or stashing before gatorizing.")
    print()
    choice = prompt("Continue anyway or abort?", "c/a")
    if choice.lower() == "a":
        print("  Aborted.")
        sys.exit(0)


def main():
    ensure_utf8_stdout()

    parser = argparse.ArgumentParser(
        description="Install Gator governance into a project repo.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("target", help="Target directory to gatorize")
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Non-interactive mode. Sites that opt in via helpers.prompt(auto_yes=) "
             "and helpers.confirm(auto_yes=) will auto-answer without reading stdin. "
             "Sites that do not opt in continue to prompt. See Stage 2/3 of "
             "2026-07-30-retire-gator-install-branch-implementation-plan.md.",
    )
    args = parser.parse_args()

    # Single write path for the module-level AUTO_YES sentinel. Do NOT mutate
    # helpers.AUTO_YES from anywhere else in the code base.
    helpers.set_auto_yes(args.yes)

    target = Path(args.target).resolve()

    # Create directory if it doesn't exist
    if not target.exists():
        print()
        print(f"  Directory does not exist: {target}")
        if confirm("Create it and gatorize?"):
            target.mkdir(parents=True)
        else:
            print("  Aborted.")
            sys.exit(0)

    # Self-gatorize guard (only meaningful when running from a checkout)
    if (REPO_ROOT / ".git").is_dir() and target.resolve() == REPO_ROOT.resolve():
        print("  Error: Target is the gator-command source repo itself. Gatorize a project repo instead.")
        sys.exit(1)

    # Check templates
    if not TEMPLATES or not TEMPLATES.is_dir():
        print("  Error: Templates not found.")
        print("  If installed via pipx, try: pipx upgrade gator-command")
        print("  If running from a clone, check the repo layout.")
        sys.exit(1)

    # Detect scenario
    scenario = detect_scenario(target)

    print()
    print("  ================================================================")
    print(f"  gatorize.py — {target.name}")
    print("  ================================================================")

    # Pre-action summary + dirty-tree gate + Y/n confirmation. Scenario 1
    # skips the dirty-tree check (no git repo yet).
    print_pre_action_summary(target, scenario)
    if scenario != 1:
        _check_dirty_tree_and_gate(target)
    if scenario == 1:
        proceed = confirm("Gatorize new directory?", default="Y", auto_yes=True)
    else:
        current_branch, _ = git("rev-parse", "--abbrev-ref", "HEAD", cwd=target)
        proceed = confirm(
            f"Gatorize branch '{current_branch or '(unknown)'}'?",
            default="Y", auto_yes=True,
        )
    if not proceed:
        print("  Aborted.")
        sys.exit(0)

    has_command_post = False  # Command-post architecture retired

    # Dispatch — no branch-dance. Every scenario operates on the current
    # branch in place (Scenario 1 initializes on git's default branch).
    if scenario == 1:
        print()
        print("  Scenario 1: Fresh directory (no git)")
        print()
        action_git_init(target)
        action_install_gator(target)
    elif scenario == 2:
        print()
        print("  Scenario 2: Git repo, clean")
        print()
        action_install_gator(target)
    elif scenario == 3:
        gen = detect_generation(target)
        print()
        print(f"  Scenario 3: Upgrade (generation {gen})")
        print()
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "gator-update.py"),
             "--path", str(target), "--source", str(SCRIPTS_DIR.parent), ],
            cwd=str(target),
        )
        if result.returncode != 0:
            print()
            print("  ================================================================")
            print("  UPDATE FAILED (exit code {})".format(result.returncode))
            print("  ================================================================")
            print()
            sys.exit(result.returncode)
        # Fall through to common tail — refreshes entry points, outbox, product-source
    elif scenario == 4:
        print()
        print("  Scenario 4: Legacy memex structure detected")
        print()
        action_morph_memex(target, action_install_gator, write_gator_version, SCRIPTS_DIR)
    elif scenario == 5:
        print()
        print("  Scenario 5: Both memex and gator found")
        print()
        legacy = detect_legacy_memex(target)
        print("  Legacy memex:")
        if legacy["memex"]:
            print("    memex/")
        if legacy["dot_memex"]:
            print("    .memex/")
        if legacy["root_constitution"]:
            print("    constitution.md (root)")
        print("  Gator:")
        print("    .gator/")
        print()
        print("  Options:")
        print("    [m] Morph — fold memex content into existing .gator/ (recommended)")
        print("    [u] Upgrade — refresh .gator/ templates, ignore memex dirs")
        print("    [x] Cancel")
        print()
        # Under --yes, Scenario 5 refuses: choosing between morph and upgrade is a
        # strategic decision with permanent data-shape consequences (folding memex
        # content vs. ignoring it). Auto-picking either path is dangerous; safest
        # default is to force an interactive session.
        choice = prompt("Choice", "m/u/x", auto_yes="x")
        if choice.lower() == "m":
            action_morph_memex(target, action_install_gator, write_gator_version, SCRIPTS_DIR)
        elif choice.lower() == "u":
            gen = detect_generation(target)
            print(f"  Running update (generation {gen})...")
            result = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "gator-update.py"),
                 "--path", str(target), "--source", str(SCRIPTS_DIR.parent), ],
                cwd=str(target),
            )
            if result.returncode != 0:
                print()
                print("  ================================================================")
                print("  UPDATE FAILED (exit code {})".format(result.returncode))
                print("  ================================================================")
                print()
                sys.exit(result.returncode)
            # Fall through to common tail
        else:
            if helpers.get_auto_yes():
                print()
                print("  Error: Scenario 5 (dual memex + gator) requires an interactive"
                      " decision.")
                print("  The choice between [m] Morph and [u] Upgrade has permanent"
                      " data-shape consequences.")
                print("  Re-run without --yes to make the decision interactively.")
                sys.exit(1)
            print("  Cancelled.")
            sys.exit(0)

    # Common tail (all scenarios except cancel/failure)
    # Always stamp .gator-version with current cli-version — even when
    # gator-update found no template changes to apply.
    write_gator_version(target / ".gator", "update" if scenario == 3 else "install")
    ensure_repo_gitignore(target)
    action_install_entry_points(target, has_command_post)
    action_install_outbox(target)
    action_install_product_source(target, SCRIPTS_DIR, TODAY)
    action_register(target, TODAY)

    # Capture current branch POST-dispatch (Codex Round-6 Finding 2). Every
    # scenario has a valid HEAD by now: Scenario 1's action_git_init() has
    # created the initial branch; Scenarios 2-5 never left the source branch.
    # Fall back to a placeholder if the read fails (detached HEAD, corrupted
    # repo mid-install) — the summary must not crash on the last mile.
    current_branch, ok = git("rev-parse", "--abbrev-ref", "HEAD", cwd=target)
    if not ok or not current_branch:
        current_branch = "(current branch)"
    print_summary(target, scenario, current_branch)


if __name__ == "__main__":
    main()
