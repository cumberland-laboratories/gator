"""Legacy memex morph — scenario 4/5 migration.

Renames legacy memex directories to *.pre-gator, installs or upgrades
.gator/, migrates content, and archives root constitution files.
"""

import shutil
import subprocess
import sys
from pathlib import Path

from gatorize.helpers import git, log_step, confirm, copy_tree_overlay


def detect_legacy_memex(target):
    """Detect what legacy memex structure exists."""
    return {
        "memex": (target / "memex").is_dir(),
        "dot_memex": (target / ".memex").is_dir(),
        "root_constitution": (target / "constitution.md").is_file(),
        "root_constitution_core": (target / "constitution-core.md").is_file(),
    }


def action_morph_memex(target, action_install_gator, write_gator_version, scripts_dir):
    """Morph legacy memex structure into .gator/.

    Args:
        target: Path to the repo being morphed.
        action_install_gator: Callable for fresh install (avoids circular import).
        write_gator_version: Callable to stamp .gator-version.
        scripts_dir: Path to scripts directory (for gator-update.py fallback).
    """
    legacy = detect_legacy_memex(target)

    print("  Legacy memex structure detected:")
    if legacy["memex"]:
        print("    memex/                  (content layer)")
    if legacy["dot_memex"]:
        print("    .memex/                 (system layer)")
    if legacy["root_constitution"]:
        print("    constitution.md         (root)")
    if legacy["root_constitution_core"]:
        print("    constitution-core.md    (root)")
    print()
    print("  Gatorize will morph this into .gator/ structure:")
    print("    1. Rename legacy dirs to *.pre-gator/")
    print("    2. Install fresh .gator/ from templates")
    print("    3. Copy your content into .gator/")
    print("    4. Archive root constitution files")
    print()
    # Under --yes, auto-proceed: only Scenario 4 (memex → morph) reaches this
    # confirm under batch mode. Scenario 5's morph path refuses earlier at the
    # m/u/x prompt (auto_yes="x"). Scenario 4 is unambiguous — the user chose
    # to gatorize a memex repo; proceeding with morph is the intent.
    if not confirm("Proceed with morph?", auto_yes=True):
        print("  Cancelled.")
        sys.exit(0)

    # Step 1: Rename legacy dirs
    if legacy["memex"]:
        pre = target / "memex.pre-gator"
        if pre.exists():
            log_step("memex.pre-gator/ already exists — skipping rename")
        else:
            _, ok = git("mv", "memex", "memex.pre-gator", cwd=target)
            if not ok:
                shutil.move(str(target / "memex"), str(pre))
            log_step("Renamed memex/ -> memex.pre-gator/")

    if legacy["dot_memex"]:
        pre = target / ".memex.pre-gator"
        if pre.exists():
            log_step(".memex.pre-gator/ already exists — skipping rename")
        else:
            _, ok = git("mv", ".memex", ".memex.pre-gator", cwd=target)
            if not ok:
                shutil.move(str(target / ".memex"), str(pre))
            log_step("Renamed .memex/ -> .memex.pre-gator/")

    # Step 2: Install .gator/ (or upgrade if it exists)
    if (target / ".gator").is_dir():
        log_step("Existing .gator/ found — upgrading templates.")
        subprocess.run(
            [sys.executable, str(scripts_dir / "gator-update.py"),
             "--path", str(target), "--source", str(scripts_dir.parent)],
            cwd=str(target),
        )
    else:
        action_install_gator(target)

    # Step 3: Migrate content from memex.pre-gator/
    src = target / "memex.pre-gator"
    gator_dir = target / ".gator"

    if src.is_dir():
        log_step("Migrating content from memex.pre-gator/ into .gator/...")

        # Direct-copy content files
        for name in ("mission.md", "roadmap.md", "identity.md", "inbox.md",
                      "issues.md", "commit_draft.md", "whiteboard.md",
                      "friction.md", "audit-tracker.md"):
            f = src / name
            if f.is_file():
                shutil.copy2(f, gator_dir / name)
                log_step(f"  Migrated {name}")

        # Patterns
        if (src / "patterns").is_dir():
            (gator_dir / "patterns").mkdir(exist_ok=True)
            copy_tree_overlay(src / "patterns", gator_dir / "patterns")
            log_step("  Migrated patterns/")
        elif (src / "patterns.md").is_file():
            shutil.copy2(src / "patterns.md", gator_dir / "patterns.md")
            log_step("  Migrated patterns.md")

        # Active threads -> threads/ (demoted)
        _migrate_md_dir(src / "active-threads", gator_dir / "threads", "active threads -> threads/ (demoted)")

        # Threads -> threads/ (merge)
        _migrate_md_dir(src / "threads", gator_dir / "threads", "threads")

        # Artifacts
        _migrate_md_dir(src / "artifacts", gator_dir / "artifacts", "artifacts")

        # Charters (skip templates)
        if (src / "charters").is_dir():
            count = 0
            for f in sorted((src / "charters").glob("*.md")):
                if f.name in ("_template.md", "README.md"):
                    continue
                shutil.copy2(f, gator_dir / "charters" / f.name)
                count += 1
            if count:
                log_step(f"  Migrated {count} charters")

        # Vault
        if (src / "vault").is_dir() and any((src / "vault").iterdir()):
            (gator_dir / "vault").mkdir(exist_ok=True)
            copy_tree_overlay(src / "vault", gator_dir / "vault")
            log_step("  Migrated vault/")

        # Reference notes (conflict-aware)
        if (src / "reference-notes").is_dir():
            rn_count = 0
            rn_conflict = 0
            for f in sorted((src / "reference-notes").glob("*.md")):
                dest = gator_dir / "reference-notes" / f.name
                if dest.exists():
                    if f.read_bytes() != dest.read_bytes():
                        conflict_name = f.stem + "-project.md"
                        shutil.copy2(f, gator_dir / "reference-notes" / conflict_name)
                        rn_conflict += 1
                else:
                    shutil.copy2(f, dest)
                    rn_count += 1
            if rn_count:
                log_step(f"  Migrated {rn_count} reference notes")
            if rn_conflict:
                log_step(f"  Preserved {rn_conflict} conflicting notes with -project suffix")

    # Migrate from .memex.pre-gator/
    dotsrc = target / ".memex.pre-gator"
    if dotsrc.is_dir():
        log_step("Migrating system layer from .memex.pre-gator/...")
        if (dotsrc / "roles.yaml").is_file():
            shutil.copy2(dotsrc / "roles.yaml", gator_dir / "roles.yaml")
            log_step("  Migrated roles.yaml")
        if (dotsrc / "policies").is_dir():
            (gator_dir / "policies").mkdir(exist_ok=True)
            copy_tree_overlay(dotsrc / "policies", gator_dir / "policies")
            log_step("  Migrated policies/")

    # Step 4: Archive root constitution files
    if legacy["root_constitution"] and (target / "constitution.md").is_file():
        _, ok = git("mv", "constitution.md", ".gator/legacy-constitution.md", cwd=target)
        if not ok:
            shutil.move(str(target / "constitution.md"),
                        str(gator_dir / "legacy-constitution.md"))
        log_step("Archived constitution.md -> .gator/legacy-constitution.md")

    if legacy["root_constitution_core"] and (target / "constitution-core.md").is_file():
        _, ok = git("mv", "constitution-core.md", ".gator/legacy-constitution-core.md", cwd=target)
        if not ok:
            shutil.move(str(target / "constitution-core.md"),
                        str(gator_dir / "legacy-constitution-core.md"))
        log_step("Archived constitution-core.md -> .gator/legacy-constitution-core.md")

    # Clean up .gitkeep in dirs that now have content
    for d in ("threads", "artifacts"):
        gitkeep = gator_dir / d / ".gitkeep"
        if gitkeep.exists() and any((gator_dir / d).glob("*.md")):
            gitkeep.unlink()

    write_gator_version(gator_dir, "morph")

    print()
    log_step("Morph complete. Pre-gator directories preserved for review:")
    if legacy["memex"]:
        log_step("  memex.pre-gator/    — your original content")
    if legacy["dot_memex"]:
        log_step("  .memex.pre-gator/   — your original system layer")
    log_step("Review .gator/, then delete pre-gator dirs when satisfied.")


def _migrate_md_dir(src_dir, dest_dir, label):
    """Migrate .md files from src to dest, handling name collisions."""
    if not src_dir.is_dir():
        return
    count = 0
    dest_dir.mkdir(exist_ok=True)
    for f in sorted(src_dir.glob("*.md")):
        if f.name in ("_TEMPLATE.md", "_template.md"):
            continue
        dest = dest_dir / f.name
        if dest.exists():
            dest = dest_dir / (f.stem + "-legacy.md")
        shutil.copy2(f, dest)
        count += 1
    if count:
        log_step(f"  Migrated {count} {label}")
