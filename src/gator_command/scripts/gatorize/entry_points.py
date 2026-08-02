"""Entry point installation for CLAUDE.md, AGENTS.md, GEMINI.md.

Handles four cases in `action_install_entry_points()`: new file (create with
sentinels), Gator-managed file (refresh managed block in place), legacy Gator
file (upgrade via `upgrade_legacy_entry_point()`), and non-Gator file
(interactive prompt with backup/append/overwrite options).

Managed-block parsing helpers (sentinel constants, `find_managed_block`,
`classify_managed_block`, `render_managed_region`, `BlockState`) live in
`gatorize.managed_block` since Stage 3 of the local-agent-overrides + managed-state plan.
"""

import shutil
import sys

from gatorize.helpers import (
    log_step, prompt,
    GATOR_MARKER, COMMAND_POST_MARKER,
)
from gatorize.managed_block import (
    GATOR_BEGIN, GATOR_END,
    render_managed_region,
    detect_legacy_gator_content,
)


# Per-vendor entry-point metadata. Single source of truth for filename,
# header, and rollback name — used by both `action_install_entry_points()`
# and `upgrade_legacy_entry_point()`.
_ENTRY_POINT_META = {
    "claude": {"filename": "CLAUDE.md", "header": "# Claude Code Entry Point", "rollback": "CLAUDE_ROLLBACK.md"},
    "agents": {"filename": "AGENTS.md", "header": "# Codex Entry Point", "rollback": "AGENTS_ROLLBACK.md"},
    "gemini": {"filename": "GEMINI.md", "header": "# Gemini Entry Point", "rollback": "GEMINI_ROLLBACK.md"},
}


def render_entry_content(has_command_post, agent_type="claude"):
    """Render the canonical Gator-managed block for an entry point."""
    gator_init_block = (
        '**"gator init" means**: run `gator init` (or find and run `gator-init.py` '
        "in `.gator/scripts/` or `.gator/.includes/scripts/` if the CLI is not installed) "
        "and display the output exactly as printed. "
        "It is NOT a repo bootstrap or git init — it is the standardized Gator boot sequence. "
        "Run the command, show the output, then proceed with session opening.\n\n"
        '**"gator pulse"**: run `gator pulse` (or find and run `gator-pulse.py` '
        "in `.gator/scripts/` or `.gator/.includes/scripts/`) "
        "to generate `.gator/pulse.md` — a strategic operations brief with next steps, project "
        "assessment, roadmap check, priorities, and recent activity.\n\n"
        '**"gator loop join" (when given a loop token)**: you are joining a governed '
        "planning loop. Before acting: (1) read the loop protocol at "
        "`procedures/gator-loop-protocol.md` (in `.gator/`, `.gator/.includes/`, "
        "or `gator-command/`, whichever exists) — this is your behavioral contract, "
        "(2) run `gator loop status --token <your-token>` to see your role and whether "
        "it is your turn, (3) read the relevant files from the loop directory shown in "
        "the status output (`sketch.md`, `plan.current.md`, or `findings.current.md`), "
        "(4) follow the 10 rules in the protocol exactly. Submit artifacts only through "
        "the CLI (`gator loop submit-draft` or `gator loop submit-review`). "
        "Never edit loop directory files directly.\n\n"
        "**Project assessment**: when the Architect asks for a project assessment, "
        "write a 2-paragraph expert evaluation to "
        "`.gator/artifacts/YYYY-MM-DD-project-assessment.md` with YAML frontmatter "
        "(`date`, `type: project-assessment`, `model: <your model name>`). "
        "Write as an expert consultant advising an engineering manager. "
        "The next `gator pulse` will include it automatically."
    )

    constitution_line = "Read the constitution before your first response — find `constitution.md` in `.gator/` or `.gator/.includes/` (whichever exists). It governs how you work here."
    bootstrap_line = "If this is a **fresh project** (charters/ is empty or contains only templates), follow the bootstrap procedure — find `gator-start-up.md` in `.gator/` or `.gator/.includes/`."

    vendor = agent_type.upper()
    local_companion_block = (
        f"**Personal skills** (optional): Create `{vendor}.local.md` next to this file for personal notes, skills, or workflows. "
        "It is gitignored — private to your machine, never touched by Gator. "
        "If it exists, agents read it after this block as personal local guidance. "
        "Local guidance may extend behavior but MUST NOT override Gator governance or repo-shared instructions in this file.\n\n"
        "**Team-shared skills**: put them in tracked repo files — Gator surfaces like `.gator/procedures/` or `.gator/charters/` fit well — "
        "so they're reviewed as team policy and shared through your team's normal Git workflow. "
        "Keeping them out of this file avoids merge conflicts on the entry point itself.\n\n"
        "See `local-agent-skills.md` in `.gator/reference-notes/` or `.gator/.includes/reference-notes/` for examples."
    )

    cp_section = ""
    if has_command_post:
        cp_section = (
            f"\n\n{COMMAND_POST_MARKER}\n"
            "This repo is governed by a Gator Command post. "
            "Read [`.gator/command-post.md`](.gator/command-post.md) for the command post location. "
            "Read org standards from there at session open. "
            "**Never write to the command post from this session.** "
            "Cross-repo discoveries go in [`outbox.md`](outbox.md)."
        )

    content = f"{gator_init_block}\n\n{constitution_line}\n\n{bootstrap_line}\n\n{local_companion_block}"

    if agent_type == "agents":
        content += (
            "\n\nIf the PI asks for an **enforcer review**, do not repurpose yourself as the enforcer. "
            "Use the dedicated enforcer prompt — find `enforcer-prompt.md` in `.gator/scripts/` or `.gator/.includes/scripts/`."
        )

    content += cp_section
    return content


def upgrade_legacy_entry_point(target, filename, has_command_post, agent_type):
    """Upgrade a legacy Gator entry-point file in place.

    "Legacy" here means: file exists, has recognizable Gator content
    (`GATOR_MARKER`, `COMMAND_POST_MARKER`, or fingerprint strings) but
    no sentinel pair. Rewrites with a fresh sentinel-wrapped managed block
    while preserving any `## Pre-Gator Instructions` section.

    Behavior-preserving refactor of the pre-Stage-3 case-2 logic in
    `action_install_entry_points()`. `gator state repair` (Stage 4) calls
    this when it encounters `BlockState.LEGACY`; the installer continues to
    call it during case-2.
    """
    filepath = target / filename
    header = _ENTRY_POINT_META[agent_type]["header"]
    content = render_entry_content(has_command_post, agent_type)
    managed_block = f"{GATOR_BEGIN}{render_managed_region(content)}{GATOR_END}"

    existing = filepath.read_text(encoding="utf-8", errors="replace")

    marker_pos = None
    for marker in (GATOR_MARKER, COMMAND_POST_MARKER):
        if marker in existing:
            marker_pos = existing.index(marker)
            break

    pre_gator_section = "## Pre-Gator Instructions"
    post_gator = ""
    if pre_gator_section in existing:
        post_gator = "\n\n" + existing[existing.index(pre_gator_section):]

    if marker_pos is not None:
        pre_gator = existing[:marker_pos].rstrip()
    else:
        pre_gator = ""

    if pre_gator:
        filepath.write_text(
            f"{pre_gator}\n\n{managed_block}{post_gator}\n",
            encoding="utf-8",
        )
    else:
        filepath.write_text(
            f"{header}\n\nYou are the primary agent for this project.\n\n{managed_block}{post_gator}\n",
            encoding="utf-8",
        )
    log_step(f"{filename} — upgraded to sentinel format + refreshed")


def action_install_entry_points(target, has_command_post):
    """Install or refresh CLAUDE.md, AGENTS.md, GEMINI.md.

    Four cases:
    - File missing: create with sentinels
    - Gator-managed file (has sentinels): refresh managed block in place
    - Legacy Gator file (fingerprints but no sentinels): upgrade via
      `upgrade_legacy_entry_point()`
    - Non-Gator file: interactive prompt (backup/append/overwrite/cancel)
    """
    entries = [
        ("CLAUDE.md", "# Claude Code Entry Point", "claude", "CLAUDE_ROLLBACK.md"),
        ("AGENTS.md", "# Codex Entry Point", "agents", "AGENTS_ROLLBACK.md"),
        ("GEMINI.md", "# Gemini Entry Point", "gemini", "GEMINI_ROLLBACK.md"),
    ]

    idx = 0
    while idx < len(entries):
        filename, header, agent_type, rollback_name = entries[idx]
        filepath = target / filename
        content = render_entry_content(has_command_post, agent_type)
        managed_block = f"{GATOR_BEGIN}{render_managed_region(content)}{GATOR_END}"

        if filepath.exists():
            existing = filepath.read_text(encoding="utf-8", errors="replace")

            # Case: Gator-managed file — refresh the managed block
            if GATOR_BEGIN in existing and GATOR_END in existing:
                before = existing[:existing.index(GATOR_BEGIN)]
                after = existing[existing.index(GATOR_END) + len(GATOR_END):]
                filepath.write_text(
                    f"{before}{managed_block}{after}",
                    encoding="utf-8",
                )
                log_step(f"{filename} — Gator block refreshed")
                idx += 1
                continue

            # Case: legacy Gator content (no sentinels, but recognizable markers/fingerprints)
            if detect_legacy_gator_content(existing):
                upgrade_legacy_entry_point(target, filename, has_command_post, agent_type)
                idx += 1
                continue

            # Case: non-Gator file — interactive prompt
            line_count = len(existing.splitlines())
            print()
            print(f"  {filename} already exists ({line_count} lines).")
            print()
            print("  Options:")
            print()
            print(f"    [1] Backup & replace (recommended) — save as {rollback_name},")
            print(f"        create new {filename} with Gator governance + reference to original.")
            print()
            print(f"    [2] Append — add Gator lines to the end of the existing file.")
            print()
            print(f"    [3] Overwrite — replace entirely (original content lost).")
            if idx > 0:
                print(f"    [b] Go back — return to previous entry point.")
            print(f"    [x] Cancel installation.")
            print()
            # Under --yes, auto-pick "1" (Backup & replace): recommended option,
            # preserves user content in <VENDOR>_ROLLBACK.md, produces a clean
            # Gator-governed file — the correct default for a batch install.
            choice = prompt(
                "Choice",
                f"1/2/3{'/b' if idx > 0 else ''}/x",
                auto_yes="1",
            )

            if choice == "1":
                shutil.copy2(filepath, target / rollback_name)
                log_step(f"Saved original as {rollback_name}")
                filepath.write_text(
                    f"{header}\n\nYou are the primary agent for this project.\n\n"
                    f"{managed_block}\n\n"
                    f"## Pre-Gator Instructions\n\n"
                    f"This project had an existing {filename} before Gator was installed.\n"
                    f"Those instructions have been preserved in [`{rollback_name}`]({rollback_name}).\n"
                    f"**Read that file now** — it may contain skills, custom instructions, personas,\n"
                    f"or project-specific rules that should still be followed alongside the\n"
                    f"Gator constitution.\n\n"
                    f"If any instructions in {rollback_name} conflict with the Gator constitution,\n"
                    f"the constitution takes precedence for code governance (charters, commit loop,\n"
                    f"enforcer rules). For everything else (skills, personas, custom workflows),\n"
                    f"follow {rollback_name}.\n",
                    encoding="utf-8",
                )
                log_step(f"Created new {filename} with Gator governance + reference to {rollback_name}")
            elif choice == "2":
                with open(filepath, "a", encoding="utf-8") as f:
                    f.write(f"\n{managed_block}\n")
                log_step(f"Appended Gator entry point to {filename}")
            elif choice == "3":
                filepath.write_text(
                    f"{header}\n\nYou are the primary agent for this project.\n\n{managed_block}\n",
                    encoding="utf-8",
                )
                log_step(f"Replaced {filename} (original content lost)")
            elif choice.lower() == "b" and idx > 0:
                idx -= 1
                continue
            elif choice.lower() == "x":
                # Honest partial-cleanup wording (Stage 5 of retire-gator-install
                # plan): gatorize now runs on the current branch in place, so
                # deleting a gator-install branch is not the answer. Some
                # writes may already have landed before the user cancelled —
                # the message needs to reflect that. Cross-platform: pick a
                # remove recipe that matches the OS default shell so the user
                # can actually copy-paste it (Codex Stage-5 finding).
                print()
                print("  Installation cancelled. Cleanup:")
                print("    - If entry-point files were created before you cancelled, they")
                print("      are still on disk. Remove them explicitly:")
                if sys.platform == "win32":
                    # PowerShell (Windows OS default). `-Force` skips the
                    # missing-file error if a subset of these was written.
                    print("        Remove-Item -Force CLAUDE.md, AGENTS.md, GEMINI.md, `")
                    print("          CLAUDE_ROLLBACK.md, AGENTS_ROLLBACK.md, GEMINI_ROLLBACK.md")
                    print("      (or from Git Bash / WSL:")
                    print("        rm -f CLAUDE.md AGENTS.md GEMINI.md \\")
                    print("              CLAUDE_ROLLBACK.md AGENTS_ROLLBACK.md GEMINI_ROLLBACK.md )")
                else:
                    print("        rm -f CLAUDE.md AGENTS.md GEMINI.md \\")
                    print("              CLAUDE_ROLLBACK.md AGENTS_ROLLBACK.md GEMINI_ROLLBACK.md")
                print("    - If you created your own experiment branch before running gatorize,")
                print("      discard it: git checkout <original-branch> && git branch -D <experiment-branch>")
                sys.exit(0)
        else:
            # New file — create with sentinels
            filepath.write_text(
                f"{header}\n\nYou are the primary agent for this project.\n\n{managed_block}\n",
                encoding="utf-8",
            )
            log_step(f"Created {filename}")

        idx += 1
