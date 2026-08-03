#!/usr/bin/env python3
"""
gator update — Refresh templates from the installed package.

Overlays template-derived files (constitution, procedures, scripts,
reference-notes, docs, charter templates) from the gator-starter template
into the current repo's .gator/. User content (charters, threads,
artifacts, mission, roadmap, inbox, etc.) is never touched.

Overlay-not-replace: template files overwrite same-named files; files
that exist only in the target are left untouched.

Usage:
    python .gator/scripts/gator-update.py              # interactive
    python .gator/scripts/gator-update.py --dry-run     # show what would change
    python .gator/scripts/gator-update.py --json         # output plan as JSON

@reads: product-source.json, templates/gator-starter/
@writes: .gator/ template-derived files (overlay, never deletes)
@does-not-own: user content (charters, threads, artifacts, mission, roadmap, etc.)
"""

import argparse
import filecmp
import json
import os
import shutil
import sys
from pathlib import Path

from gator_core import (
    get_version, find_gator_root, normalize_path,
    ensure_utf8_stdout, git, import_sibling,
    resolve_template_source, read_product_source,
)

VERSION = get_version()

# Gitignore convergence — import from gatorize (graceful degradation)
try:
    _gatorize = import_sibling("gatorize")
    if _gatorize:
        ensure_repo_gitignore = _gatorize.ensure_repo_gitignore
    else:
        ensure_repo_gitignore = lambda repo_root: None
except Exception:
    ensure_repo_gitignore = lambda repo_root: None

# Entry-point block refresh — Stage 4b. Template copy inlines the
# managed_block parsing helpers (plan Stage 4b option 2) so this file
# runs standalone on fleet repos without a gatorize/ sub-package. The
# helpers' bodies must byte-match src/gator_command/scripts/gatorize/managed_block.py
# — enforced by TestTemplateSync's AST-equivalence assertion.

from dataclasses import dataclass as _dataclass
from enum import Enum as _Enum

# Marker/fingerprint constants inlined from gatorize/helpers.py
GATOR_MARKER = "# --- Gator Navigation Coding ---"
COMMAND_POST_MARKER = "# --- Gator Command Post ---"

# Sentinel bytes are the ownership contract with every gatorized repo.
# Do NOT mutate — whitespace, casing, or attributes. See Invariant #1 of
# the Stage plan.
GATOR_BEGIN = "<!-- GATOR:BEGIN -->"
GATOR_END = "<!-- GATOR:END -->"

# Legacy fingerprints — recognizable Gator content in files that predate
# the sentinel format. Keep in sync with `action_install_entry_points()`
# case-2 detection.
_LEGACY_FINGERPRINTS = (
    GATOR_MARKER,
    COMMAND_POST_MARKER,
    "gator-init.py",
    ".gator/constitution.md",
)


class BlockState(_Enum):
    """Canonical six-state vocabulary for entry-point files.

    Defined once here; all API constants, JSON schema values, human output,
    and test fixtures must use these exact lowercase spellings (via `.value`).
    See "Canonical State Vocabulary" in the Stage plan.
    """
    CLEAN = "clean"
    MODIFIED = "modified"
    LEGACY = "legacy"
    CORRUPTED = "corrupted"
    ABSENT = "absent"
    FOREIGN = "foreign"


@_dataclass(frozen=True)
class ManagedBlockLocation:
    """Slices and byte offsets of a well-formed managed block in a file's text."""
    before: str
    block_content: str
    after: str
    begin_index: int
    end_index: int


def render_managed_region(baseline_content: str) -> str:
    """Exact bytes that should appear between GATOR_BEGIN and GATOR_END.

    Centralizes the newline wrapping so installer, `gator update` block-refresh
    (Stage 4b), and `gator state repair` (Stage 4) all produce byte-identical
    managed regions given the same baseline content.
    """
    return f"\n{baseline_content}\n"


def find_managed_block(text):
    """Return a ManagedBlockLocation for a well-formed sentinel pair, else None.

    "Well-formed" means exactly one GATOR_BEGIN and one GATOR_END, in that order.
    Returns None for any deviation (no sentinels, dangling, reversed, duplicated).
    Callers that need to distinguish "corrupted" from "no sentinels" should use
    `classify_managed_block()` instead.
    """
    if text.count(GATOR_BEGIN) != 1 or text.count(GATOR_END) != 1:
        return None
    begin = text.index(GATOR_BEGIN)
    end = text.index(GATOR_END)
    if end < begin:
        return None
    block_content = text[begin + len(GATOR_BEGIN):end]
    return ManagedBlockLocation(
        before=text[:begin],
        block_content=block_content,
        after=text[end + len(GATOR_END):],
        begin_index=begin,
        end_index=end,
    )


def _has_sentinel_bytes(text):
    """True if either sentinel appears at all in the text."""
    return GATOR_BEGIN in text or GATOR_END in text


def _sentinels_are_malformed(text):
    """True if sentinel bytes appear but do not form exactly one valid pair.

    Malformed = dangling BEGIN, dangling END, reversed order, duplicated BEGIN,
    or duplicated END. Returns False when there are no sentinels at all (that
    is LEGACY or FOREIGN, not CORRUPTED) and False when there is a valid pair.
    """
    if not _has_sentinel_bytes(text):
        return False
    n_begin = text.count(GATOR_BEGIN)
    n_end = text.count(GATOR_END)
    if n_begin != 1 or n_end != 1:
        return True
    return text.index(GATOR_END) < text.index(GATOR_BEGIN)


def detect_legacy_gator_content(text):
    """True if the file has no sentinel pair but matches recognizable Gator content.

    Mirrors the fingerprint checks previously inline in `action_install_entry_points()`
    (pre-Stage-3 entry_points.py:114-120). Sentinels alone do not count as legacy —
    only the fingerprint strings do.
    """
    return any(fp in text for fp in _LEGACY_FINGERPRINTS)


def classify_managed_block(text, baseline_content, *, file_exists):
    """Classify the state of an entry-point file relative to a baseline.

    Dispatch order:
      1. `file_exists=False` → ABSENT
      2. valid sentinel pair → CLEAN or MODIFIED (byte-compare against baseline)
      3. malformed sentinel bytes → CORRUPTED
      4. no sentinels + legacy fingerprint → LEGACY
      5. no sentinels + no fingerprint → FOREIGN

    `baseline_content` is the raw content that should appear between the
    sentinels (i.e., the return value of `render_entry_content()`). The
    function internally wraps it via `render_managed_region()` for the
    byte-compare so callers do not need to know the newline contract.
    """
    if not file_exists:
        return BlockState.ABSENT
    location = find_managed_block(text)
    if location is not None:
        expected = render_managed_region(baseline_content)
        return BlockState.CLEAN if location.block_content == expected else BlockState.MODIFIED
    if _sentinels_are_malformed(text):
        return BlockState.CORRUPTED
    if detect_legacy_gator_content(text):
        return BlockState.LEGACY
    return BlockState.FOREIGN


# Baseline content generators — only available when the gatorize sub-package
# is reachable (package copy always; template copy on fleet repos only if
# the sub-package has been shipped, which is a Stage 6+ decision).
try:
    from gatorize.entry_points import render_entry_content, upgrade_legacy_entry_point
    _ENTRY_POINT_REFRESH_AVAILABLE = True
except Exception:
    _ENTRY_POINT_REFRESH_AVAILABLE = False




# Files that are template-derived (safe to overwrite)
# These are shipped files — on v2 they go to .includes/
TEMPLATE_FILES = [
    "constitution.md",
    "gator-start-up.md",
]

# Dotfiles that need renaming from template (stored without dot to avoid git issues)
# Shipped — on v2 they go to .includes/
TEMPLATE_DOTFILES = {
    "charterignore": ".charterignore",
}

# Shipped directories — on v2 they go to .includes/<dir>
SHIPPED_TEMPLATE_DIRS = {
    "procedures": "procedures",
    "reference-notes": "reference-notes",
    "scripts": "scripts",
    "blueprints": "blueprints",
}

# User-content directories — always at .gator/ root regardless of layout
USER_TEMPLATE_DIRS = {
    "docs": "docs",
    "sessions": "sessions",
    "artifacts": "artifacts",
    "threads": "threads",
    "policies": "policies",
    "field-guides": "field-guides",
    "vault": "vault",
}

# Combined for backward compat (used by plan_hook_updates etc.)
TEMPLATE_DIRS = {**SHIPPED_TEMPLATE_DIRS, **USER_TEMPLATE_DIRS}

# Charter scaffolding files (shipped — on v2 they go to .includes/charters/)
CHARTER_TEMPLATE_FILES = ["README.md", "_template.md"]

# Slash commands
CLAUDE_COMMANDS_DIR = "commands"


# --- Path resolution ---



# --- Diff and overlay ---

def plan_file_update(src, dest):
    """Compare a template file to the installed version.

    Returns: (action, src, dest) where action is 'add', 'update', 'unchanged', or 'skip'
    """
    if not dest.exists():
        return "add", src, dest
    if filecmp.cmp(src, dest, shallow=False):
        return "unchanged", src, dest
    return "update", src, dest


def plan_updates(templates_dir, gator_dir, repo_root):
    """Build the full update plan.

    Layout-aware: on v2 repos, shipped content targets .gator/.includes/.
    On v1 repos, all content targets .gator/ root (current behavior).

    @reads: templates_dir, gator_dir
    @does-not-own: executing the updates
    """
    plan = []

    # Detect layout to route shipped content
    try:
        from gator_layout import resolve_gator_layout
        layout = resolve_gator_layout(repo_root)
    except Exception:
        layout = "v1"

    # Refuse to write on mixed or invalid layouts — force migration first
    if layout == "mixed":
        raise RuntimeError(
            "Layout is mixed — run 'gator update --migrate-layout' to repair "
            "before updating."
        )
    if layout == "invalid":
        raise RuntimeError(
            "Layout is invalid — .gator/ structure cannot be resolved. "
            "Re-run gatorize or check .gator/ integrity."
        )

    # Shipped base: .includes/ for v2, root for v1
    shipped_base = gator_dir / ".includes" if layout == "v2" else gator_dir

    # Top-level template files (shipped)
    for filename in TEMPLATE_FILES:
        src = templates_dir / filename
        dest = shipped_base / filename
        if src.exists():
            plan.append(plan_file_update(src, dest))

    # Dotfiles (shipped)
    for src_name, dest_name in TEMPLATE_DOTFILES.items():
        src = templates_dir / src_name
        dest = shipped_base / dest_name
        if src.exists():
            plan.append(plan_file_update(src, dest))

    # Charter scaffolding (shipped)
    for filename in CHARTER_TEMPLATE_FILES:
        src = templates_dir / "charters" / filename
        dest = shipped_base / "charters" / filename
        if src.exists():
            plan.append(plan_file_update(src, dest))

    # Shipped directories → shipped_base (but scaffolding stays at root)
    _SCAFFOLDING = {"README.md", "_template.md"}
    for src_subdir, dest_subdir in SHIPPED_TEMPLATE_DIRS.items():
        src_dir = templates_dir / src_subdir
        if not src_dir.is_dir():
            continue
        for src_file in sorted(src_dir.iterdir()):
            if src_file.is_file():
                if layout == "v2" and src_file.name in _SCAFFOLDING:
                    # Scaffolding stays at user-visible root
                    dest_file = gator_dir / dest_subdir / src_file.name
                else:
                    dest_file = shipped_base / dest_subdir / src_file.name
                plan.append(plan_file_update(src_file, dest_file))
        # Nested subdirs (e.g., scripts/hooks/)
        for sub in sorted(src_dir.iterdir()):
            if sub.is_dir():
                dest_sub = shipped_base / dest_subdir / sub.name
                for src_file in sorted(sub.iterdir()):
                    if src_file.is_file():
                        dest_file = dest_sub / src_file.name
                        plan.append(plan_file_update(src_file, dest_file))

    # User-content directories → always gator_dir root
    _plan_dir_overlay(plan, templates_dir, gator_dir, USER_TEMPLATE_DIRS)

    # Claude Code slash commands (not in .gator/)
    src_commands = templates_dir / CLAUDE_COMMANDS_DIR
    if src_commands.is_dir():
        dest_commands = repo_root / ".claude" / "commands"
        for src_file in sorted(src_commands.iterdir()):
            if src_file.is_file():
                dest_file = dest_commands / src_file.name
                plan.append(plan_file_update(src_file, dest_file))

    return plan


def _plan_dir_overlay(plan, templates_dir, dest_base, dirs_map):
    """Plan file overlays for a set of template directories."""
    for src_subdir, dest_subdir in dirs_map.items():
        src_dir = templates_dir / src_subdir
        dest_dir = dest_base / dest_subdir
        if not src_dir.is_dir():
            continue
        # Top-level files
        for src_file in sorted(src_dir.iterdir()):
            if src_file.is_file():
                dest_file = dest_dir / src_file.name
                plan.append(plan_file_update(src_file, dest_file))
        # Nested subdirectories (e.g., scripts/hooks/)
        for sub in sorted(src_dir.iterdir()):
            if sub.is_dir():
                dest_sub = dest_dir / sub.name
                for src_file in sorted(sub.iterdir()):
                    if src_file.is_file():
                        dest_file = dest_sub / src_file.name
                        plan.append(plan_file_update(src_file, dest_file))



def _extract_hook_commands(groups):
    """Extract all command strings from a list of hook groups.

    Each group is a dict with a "hooks" key containing a list of hook entries.
    Each hook entry has a "command" key.
    """
    commands = set()
    for group in groups:
        if not isinstance(group, dict):
            continue
        for hook in group.get("hooks", []):
            if isinstance(hook, dict) and "command" in hook:
                commands.add(hook["command"])
    return commands


def merge_hooks_into_settings(settings_path, hooks_template_path):
    """Merge Gator hooks into a vendor settings JSON file without clobbering.

    If the settings file doesn't exist, writes the hooks template as-is.
    If it exists, deep-merges the hooks block: for each hook event,
    compares individual hook commands and adds any that are missing.
    This ensures that adding a new Gator hook (e.g., gator-session-open.py)
    to the template will propagate to repos that already have older Gator
    hooks installed.

    Returns: 'add', 'update', or 'unchanged'.
    """
    hooks_template = json.loads(hooks_template_path.read_text(encoding="utf-8"))
    template_hooks = hooks_template.get("hooks", {})

    if not settings_path.exists():
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(
            json.dumps(hooks_template, indent=2) + "\n", encoding="utf-8"
        )
        return "add"

    # Read existing settings
    try:
        existing = json.loads(settings_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        # Corrupt file — don't clobber, skip
        return "unchanged"

    if not isinstance(existing, dict):
        return "unchanged"

    # Validate hooks shape — bail if it's not what we expect
    existing_hooks = existing.get("hooks", {})
    if not isinstance(existing_hooks, dict):
        # hooks is present but wrong type (e.g., a list) — don't clobber
        return "unchanged"

    needs_update = False

    for event_name, groups in template_hooks.items():
        if event_name not in existing_hooks:
            existing_hooks[event_name] = groups
            needs_update = True
        else:
            event_value = existing_hooks[event_name]
            if not isinstance(event_value, list):
                # Event value is wrong shape — skip this event, don't corrupt
                continue
            # Get the template hooks list for this event
            template_hooks_list = []
            for group in groups:
                if isinstance(group, dict):
                    template_hooks_list = group.get("hooks", [])
                    break
            if not template_hooks_list:
                continue

            # Find the existing Gator group (contains any .gator/ command)
            gator_group = None
            for existing_group in event_value:
                if not isinstance(existing_group, dict):
                    continue
                group_hooks = existing_group.get("hooks", [])
                group_cmds = [h.get("command", "") for h in group_hooks if isinstance(h, dict)]
                if any(".gator/" in cmd for cmd in group_cmds):
                    gator_group = existing_group
                    break

            if gator_group is None:
                # No existing Gator group — append the template group
                event_value.append({"hooks": list(template_hooks_list)})
                needs_update = True
            else:
                # Separate user hooks from Gator hooks in the existing group,
                # then rebuild: template Gator hooks + preserved user hooks.
                existing_hooks_list = gator_group.get("hooks", [])
                existing_gator = [h for h in existing_hooks_list if isinstance(h, dict) and ".gator/" in h.get("command", "")]
                user_hooks = [h for h in existing_hooks_list if not (isinstance(h, dict) and ".gator/" in h.get("command", ""))]
                existing_gator_cmds = [h.get("command", "") for h in existing_gator]
                template_cmds = [h.get("command", "") for h in template_hooks_list if isinstance(h, dict)]
                if existing_gator_cmds != template_cmds:
                    # Rebuild: template Gator hooks first, then user hooks
                    gator_group["hooks"] = list(template_hooks_list) + user_hooks
                    needs_update = True

    if not needs_update:
        return "unchanged"

    existing["hooks"] = existing_hooks
    settings_path.write_text(
        json.dumps(existing, indent=2) + "\n", encoding="utf-8"
    )
    return "update"


# Vendor hook config: (template_file, target_dir, target_filename)
VENDOR_HOOK_CONFIGS = [
    ("vendor-hooks/claude-settings.json", ".claude", "settings.json"),
    ("vendor-hooks/codex-hooks.json", ".codex", "hooks.json"),
    ("vendor-hooks/gemini-settings.json", ".gemini", "settings.json"),
]


def install_vendor_hooks(templates_dir, repo_root):
    """Install vendor SessionStart hook configs into the repo.

    Merge-safe: injects Gator hooks into existing settings files
    without clobbering user content (permissions, env vars, other hooks).

    Returns count of files added or updated.
    """
    changed = 0
    for template_file, target_dir, target_name in VENDOR_HOOK_CONFIGS:
        src = templates_dir / template_file
        if not src.exists():
            continue
        dest = repo_root / target_dir / target_name
        result = merge_hooks_into_settings(dest, src)
        if result in ("add", "update"):
            changed += 1
    return changed


def execute_updates(plan):
    """Execute the update plan — copy files that need adding or updating.

    @writes: .gator/ template-derived files
    @does-not-own: user content
    """
    added = 0
    updated = 0
    unchanged = 0

    for action, src, dest in plan:
        if action == "add":
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            added += 1
        elif action == "update":
            shutil.copy2(src, dest)
            updated += 1
        else:
            unchanged += 1

    return added, updated, unchanged


# --- Entry-point managed-block refresh (Stage 4b) ---

_ENTRY_POINT_META = [
    {"filename": "CLAUDE.md", "agent_type": "claude", "header": "# Claude Code Entry Point"},
    {"filename": "AGENTS.md", "agent_type": "agents", "header": "# Codex Entry Point"},
    {"filename": "GEMINI.md", "agent_type": "gemini", "header": "# Gemini Entry Point"},
]


def plan_entry_point_updates(repo_root):
    """Plan managed-block refresh actions for entry-point files.

    Returns a list of dicts: {filename, agent_type, state, action}. Empty
    list when the entry-point refresh API is unavailable (template copy on
    fleet repos without the gatorize sub-package) — graceful degradation.

    Read-only: consistent with the plan/execute separation TRIPWIRE.

    Dispatch per plan Stage 4b:
      clean → skip (no plan entry)
      modified → refresh-block (executor writes .pre-gator-update backup first)
      legacy → upgrade-legacy (delegates to upgrade_legacy_entry_point)
      absent → create-fresh (deterministic, non-destructive)
      corrupted → skip (ambiguous; belongs to gator state repair)
      foreign → skip (belongs to gatorize interactive prompt)
    """
    if not _ENTRY_POINT_REFRESH_AVAILABLE:
        return []

    actions = []
    for meta in _ENTRY_POINT_META:
        filepath = repo_root / meta["filename"]
        baseline = render_entry_content(has_command_post=False, agent_type=meta["agent_type"])
        if filepath.exists():
            text = filepath.read_text(encoding="utf-8", errors="replace")
            state = classify_managed_block(text, baseline, file_exists=True)
        else:
            state = classify_managed_block("", baseline, file_exists=False)

        if state is BlockState.CLEAN:
            continue  # no plan entry
        if state is BlockState.MODIFIED:
            action = "refresh-block"
        elif state is BlockState.LEGACY:
            action = "upgrade-legacy"
        elif state is BlockState.ABSENT:
            action = "create-fresh"
        else:
            # CORRUPTED and FOREIGN carry ambiguity — skip in gator update
            continue

        actions.append({
            "filename": meta["filename"],
            "agent_type": meta["agent_type"],
            "state": state.value,
            "action": action,
        })
    return actions


def execute_entry_point_updates(repo_root, actions):
    """Execute planned entry-point refresh actions.

    Annotates each action with an 'outcome' field. Returns
    `(refreshed, upgraded, created, skipped)` — the counts feed into
    `print_result()` completion accounting and the `.gator-version` stamp
    gate in `main()`. Any non-zero count means repo state changed.

    - refresh-block on modified → write <VENDOR>.md.pre-gator-update backup
      next to the file, then replace the sentinel region with the baseline.
      Content outside sentinels preserved byte-for-byte.
    - upgrade-legacy → delegate to upgrade_legacy_entry_point.
    - create-fresh → write a new file with sentinel-wrapped baseline block.
      No backup written (nothing existed).
    """
    refreshed = 0
    upgraded = 0
    created = 0
    skipped = 0

    if not _ENTRY_POINT_REFRESH_AVAILABLE:
        for entry in actions:
            entry["outcome"] = "skipped-unavailable"
            skipped += 1
        return refreshed, upgraded, created, skipped

    for entry in actions:
        filename = entry["filename"]
        agent_type = entry["agent_type"]
        action = entry["action"]
        filepath = repo_root / filename
        meta = next(m for m in _ENTRY_POINT_META if m["filename"] == filename)

        if action == "refresh-block":
            existing = filepath.read_text(encoding="utf-8", errors="replace")
            location = find_managed_block(existing)
            if location is None:
                entry["outcome"] = "skipped-race"
                skipped += 1
                continue
            # Backup before overwrite — .pre-gator-update sibling
            backup_path = filepath.with_name(f"{filename}.pre-gator-update")
            backup_path.write_text(existing, encoding="utf-8")
            baseline = render_entry_content(has_command_post=False, agent_type=agent_type)
            expected_region = render_managed_region(baseline)
            new_text = f"{location.before}{GATOR_BEGIN}{expected_region}{GATOR_END}{location.after}"
            filepath.write_text(new_text, encoding="utf-8")
            entry["outcome"] = "refreshed-with-backup"
            refreshed += 1
            continue

        if action == "upgrade-legacy":
            upgrade_legacy_entry_point(repo_root, filename, has_command_post=False, agent_type=agent_type)
            entry["outcome"] = "upgraded"
            upgraded += 1
            continue

        if action == "create-fresh":
            baseline = render_entry_content(has_command_post=False, agent_type=agent_type)
            managed_block = f"{GATOR_BEGIN}{render_managed_region(baseline)}{GATOR_END}"
            filepath.write_text(
                f"{meta['header']}\n\nYou are the primary agent for this project.\n\n{managed_block}\n",
                encoding="utf-8",
            )
            entry["outcome"] = "created"
            created += 1
            continue

        entry["outcome"] = "skipped-unknown"
        skipped += 1
    return refreshed, upgraded, created, skipped


def plan_hook_updates(gator_dir, repo_root):
    """Plan git hook installations. Returns list of (hook_name, action).

    Compares the generated cross-platform Python wrappers to the current
    managed hook dir contents. This matches what install_git_hooks()
    actually writes, so the plan is accurate on both Unix and Windows.

    Layout-aware: resolves the pre-commit script path via the resolver.
    """
    git_hooks = get_managed_hook_dir(repo_root)

    # Resolve pre-commit script path (layout-aware)
    script_path = None
    try:
        from gator_layout import get_gator_paths
        paths = get_gator_paths(repo_root)
        gator_script = paths.scripts_dir / "gator-pre-commit.py"
    except Exception:
        gator_script = gator_dir / "scripts" / "gator-pre-commit.py"

    if not git_hooks.parent.is_dir() or not gator_script.exists():
        return []

    # Resolve script_path for wrappers (same logic as install_git_hooks)
    try:
        script_rel = str(gator_script).replace("\\", "/")
        repo_str = str(repo_root).replace("\\", "/")
        if script_rel.startswith(repo_str):
            script_path = script_rel[len(repo_str):].lstrip("/")
    except Exception:
        pass

    expected_hooks = build_git_hook_wrappers(gator_script=script_path)
    config_needs_update = hooks_config_needs_update(repo_root)
    results = []
    for hook_name, expected_content in sorted(expected_hooks.items()):
        dest = git_hooks / hook_name
        if not dest.exists():
            results.append((hook_name, "add"))
            continue
        actual = dest.read_text(encoding="utf-8", errors="replace")
        if actual != expected_content or config_needs_update:
            results.append((hook_name, "update"))
        else:
            results.append((hook_name, "unchanged"))

    return results


def _hook_shebang():
    """Return the platform-correct shebang for hook wrappers."""
    return "#!C:/Windows/py.exe -3" if os.name == "nt" else "#!/usr/bin/env python3"


def get_managed_hooks_path_value():
    """Return the core.hooksPath value Gator manages on this platform."""
    return ".git/gator-hooks" if os.name == "nt" else None


def get_managed_hook_dir(repo_root):
    """Return the hook directory Gator actively manages."""
    hooks_path = get_managed_hooks_path_value()
    if hooks_path:
        return repo_root / Path(hooks_path)
    return repo_root / ".git" / "hooks"


def get_hook_probe_dirs(repo_root):
    """Return installed-hook directories to probe, managed dir first."""
    probe_dirs = [get_managed_hook_dir(repo_root)]
    legacy = repo_root / ".git" / "hooks"
    if legacy not in probe_dirs:
        probe_dirs.append(legacy)
    return probe_dirs


def hooks_config_needs_update(repo_root):
    """Return True when core.hooksPath is missing or wrong."""
    expected = get_managed_hooks_path_value()
    if not expected:
        return False
    actual, ok = git("config", "--local", "--get", "core.hooksPath", cwd=repo_root)
    return not ok or actual.strip() != expected


def _configure_managed_hooks_path(repo_root):
    """Set core.hooksPath when this platform uses a non-default dir."""
    expected = get_managed_hooks_path_value()
    if not expected:
        return True
    _, ok = git("config", "--local", "core.hooksPath", expected, cwd=repo_root)
    return ok


def get_managed_hook_display_path():
    """Return the human-readable relative hook path for output."""
    return get_managed_hooks_path_value() or ".git/hooks"


def build_git_hook_wrappers(gator_script=None):
    """Return the exact hook wrapper contents gator installs.

    The subprocess.call inside uses the exact interpreter path — spaces are
    safe there because it's a Python string argument, not a shebang.

    gator_script: path to the pre-commit script relative to repo root.
    Defaults to ".gator/scripts/gator-pre-commit.py" for v1 layout.
    v2 layout passes ".gator/.includes/scripts/gator-pre-commit.py".
    """
    python_path = sys.executable.replace("\\", "/")
    if gator_script is None:
        gator_script = ".gator/scripts/gator-pre-commit.py"
    shebang = _hook_shebang()

    # Each wrapper checks if the governance script exists before calling it.
    # On branches where .gator/ hasn't been merged yet, the script is absent
    # but hooks are still installed. In that case, warn and allow the commit.
    warn_msg = (
        '\\n  Gator: governance hooks are installed, but the current branch'
        '\\n  does not contain .gator/. Proceeding in warning mode.'
        '\\n  If this branch should be governed, merge or restore the Gator layer.\\n'
    )
    guard = (
        'import os, subprocess, sys\n'
        f'script = "{gator_script}"\n'
        'if not os.path.isfile(script):\n'
        f'    print("{warn_msg}")\n'
        '    sys.exit(0)\n'
    )

    return {
        "pre-commit": (
            f'{shebang}\n'
            f'{guard}'
            f'sys.exit(subprocess.call([r"{python_path}", script, "--phase", "validate"]))\n'
        ),
        "commit-msg": (
            f'{shebang}\n'
            f'{guard}'
            f'sys.exit(subprocess.call([r"{python_path}", script, "--phase", "trailers", sys.argv[1]]))\n'
        ),
        "post-commit": (
            f'{shebang}\n'
            f'{guard}'
            f'sys.exit(subprocess.call([r"{python_path}", script, "--phase", "cleanup"]))\n'
        ),
    }


def install_git_hooks(gator_dir, repo_root):
    """Install/refresh git hooks as cross-platform Python wrappers.

    Writes Python-shebang hooks that call gator-pre-commit.py directly.
    Windows installs into `.git/gator-hooks/` and sets `core.hooksPath`
    to bypass the Git-for-Windows/MSYS launcher path. Unix installs into
    the normal `.git/hooks/` directory.

    Layout-aware: resolves the script path via gator_layout for v2 repos.

    @writes: managed git hook dir, git config core.hooksPath (Windows only)
    """
    git_hooks = get_managed_hook_dir(repo_root)
    if not git_hooks.parent.is_dir():
        return 0

    git_hooks.mkdir(parents=True, exist_ok=True)
    installed = 0

    # Resolve the script path based on layout
    script_path = None
    try:
        from gator_layout import get_gator_paths
        paths = get_gator_paths(repo_root)
        script_rel = str(paths.scripts_dir / "gator-pre-commit.py").replace("\\", "/")
        # Make relative to repo root
        repo_str = str(repo_root).replace("\\", "/")
        if script_rel.startswith(repo_str):
            script_path = script_rel[len(repo_str):].lstrip("/")
    except Exception:
        pass  # fallback to default

    for name, content in build_git_hook_wrappers(gator_script=script_path).items():
        dest = git_hooks / name
        dest.write_text(content, encoding="utf-8")
        try:
            import stat
            dest.chmod(dest.stat().st_mode | stat.S_IEXEC)
        except (OSError, AttributeError):
            pass
        installed += 1

    _configure_managed_hooks_path(repo_root)
    return installed


# --- Output ---

def print_plan(plan, dry_run=False, hooks=None, entry_point_actions=None):
    """Print the update plan."""
    adds = [(a, s, d) for a, s, d in plan if a == "add"]
    updates = [(a, s, d) for a, s, d in plan if a == "update"]
    unchanged = [(a, s, d) for a, s, d in plan if a == "unchanged"]

    hook_adds = [h for h in (hooks or []) if h[1] == "add"]
    hook_updates = [h for h in (hooks or []) if h[1] == "update"]

    entry_actions = entry_point_actions or []

    mode = " (dry run)" if dry_run else ""
    print()
    print(f"  gator update{mode}")
    print()

    if adds:
        print(f"  New files ({len(adds)}):")
        for _, _, dest in adds:
            print(f"    + {dest.name}")
        print()

    if updates:
        print(f"  Updated files ({len(updates)}):")
        for _, _, dest in updates:
            print(f"    ~ {dest.name}")
        print()

    if hook_adds or hook_updates:
        print(f"  Git hooks ({len(hook_adds)} new, {len(hook_updates)} updated):")
        hook_dir = get_managed_hook_display_path()
        for name, action in (hooks or []):
            if action == "add":
                print(f"    + {hook_dir}/{name}")
            elif action == "update":
                print(f"    ~ {hook_dir}/{name}")
        print()

    if entry_actions:
        print(f"  Entry-point blocks ({len(entry_actions)}):")
        for entry in entry_actions:
            print(f"    ~ {entry['filename']:<12} {entry['state']:<11} → {entry['action']}")
        print()

    if not adds and not updates and not hook_adds and not hook_updates and not entry_actions:
        print(f"  Everything is current. No updates needed.")
        print()
        return

    print(f"  Unchanged: {len(unchanged)} files")
    print(f"  Total: {len(adds)} new, {len(updates)} updated, {len(unchanged)} unchanged, {len(entry_actions)} entry-point actions")
    print()


def print_result(added, updated, unchanged, entry_point_counts=None):
    """Print the result after executing updates.

    Stage 4b: `entry_point_counts` is `(refreshed, upgraded, created, skipped)`
    from `execute_entry_point_updates()`. When any of refreshed/upgraded/created
    is non-zero, an additional "Entry-point blocks:" line prints so users see
    that repo state changed even on updates where file-overlay counts are all zero.
    """
    print(f"  Done: {added} added, {updated} updated, {unchanged} unchanged")
    if entry_point_counts:
        refreshed, upgraded, created, _ = entry_point_counts
        if refreshed or upgraded or created:
            parts = []
            if refreshed:
                parts.append(f"{refreshed} refreshed")
            if upgraded:
                parts.append(f"{upgraded} upgraded")
            if created:
                parts.append(f"{created} created")
            print(f"  Entry-point blocks: {', '.join(parts)}")
    print()


def print_json_plan(plan, templates_dir, hooks=None, entry_point_actions=None):
    """Output the plan as JSON.

    Top-level schema field is "gator-update-v1" — declared here so downstream
    consumers can detect the shape. New fields inside v1 are additive
    (entry_point_actions was added in Stage 4b).
    """
    items = []
    for action, src, dest in plan:
        items.append({
            "action": action,
            "source": str(src),
            "destination": str(dest),
            "filename": dest.name,
        })

    hook_items = []
    hook_dir = get_managed_hook_display_path()
    for name, action in (hooks or []):
        hook_items.append({
            "hook": name,
            "action": action,
            "destination": f"{hook_dir}/{name}",
        })

    entry_items = list(entry_point_actions or [])

    output = {
        "schema": "gator-update-v1",
        "version": VERSION,
        "templates": str(templates_dir),
        "plan": items,
        "hooks": hook_items,
        "entry_point_actions": entry_items,
        "summary": {
            "add": sum(1 for i in items if i["action"] == "add"),
            "update": sum(1 for i in items if i["action"] == "update"),
            "unchanged": sum(1 for i in items if i["action"] == "unchanged"),
            "hooks_add": sum(1 for h in hook_items if h["action"] == "add"),
            "hooks_update": sum(1 for h in hook_items if h["action"] == "update"),
            "entry_point_actions": len(entry_items),
        }
    }
    print(json.dumps(output, indent=2))


# --- Layout migration ---

def _merge_dir_files_only(src, dest, report, prefix):
    """Recursively merge files from src into dest, dest-wins on file collision.

    Used only by migrate_layout()'s Step 5 to handle both-directories-exist
    cases whose names aren't in the known-safe legacy allowlist. Files present
    at both sides are removed from src (dest is canonical, same rule as
    SHIPPED_ROOT_FILES in Step 4). Empty subdirs are rmdir'd bottom-up. Any
    leftover content (non-file/non-dir entries; subdirs that still hold
    content after merge) is logged into report["conflicts"] and left in place
    so the operator sees a concrete path in the final migration report.
    """
    dest.mkdir(exist_ok=True)
    for entry in sorted(src.iterdir()):
        dest_entry = dest / entry.name
        if entry.is_file():
            if not dest_entry.exists():
                shutil.move(str(entry), str(dest_entry))
                report["moved"].append(f"{prefix}/{entry.name}")
            else:
                entry.unlink()
                report["moved"].append(
                    f"{prefix}/{entry.name} (root copy removed)"
                )
        elif entry.is_dir():
            _merge_dir_files_only(
                entry, dest_entry, report,
                prefix=f"{prefix}/{entry.name}",
            )
        else:
            report["conflicts"].append(
                f"{prefix}/{entry.name} (non-file, non-dir; left in place)"
            )
    try:
        src.rmdir()
    except OSError:
        report["conflicts"].append(
            f"{prefix}/ (still contains unresolvable content)"
        )


def migrate_layout(repo_root, gator_dir, templates_dir):
    """Migrate a v1 repo to v2 layout.

    The ONLY code path that moves files from flat .gator/ to .gator/.includes/.
    Never called by normal update or install — only by --migrate-layout.

    Algorithm (from the approved plan):
    1. Resolve current layout — refuse unless v1 or repairable mixed
    2. Resolve template source for shipped file classification
    3. Create .gator/.includes/
    4. Move shipped root files into .includes/
    5. Move shipped directories into .includes/
    5a. Regenerate Git hook wrappers for new script path
    6. For mixed directories: move only shipped files, leave user files
    7-8. Leave user and runtime files in place
    9. Write layout-version.json
    10. Emit migration report
    11. Re-validate
    """
    from gator_layout import (
        resolve_gator_layout, get_gator_paths,
        SHIPPED_ROOT_FILES, SHIPPED_DIRECTORIES,
        get_shipped_files_for_directory,
        resolve_template_source_for_layout,
    )

    layout = resolve_gator_layout(repo_root)
    report = {
        "source_layout": layout,
        "moved": [],
        "preserved": [],
        "conflicts": [],
        "final_layout": None,
    }

    # Step 1: refuse unless v1 or repairable mixed
    if layout == "v2":
        print("  Already v2 layout. Nothing to migrate.")
        report["final_layout"] = "v2"
        return report
    if layout == "invalid":
        print("  Error: invalid .gator/ layout — cannot migrate.", file=sys.stderr)
        report["final_layout"] = "invalid"
        return report
    if layout not in ("v1", "mixed"):
        print(f"  Error: unexpected layout '{layout}'.", file=sys.stderr)
        report["final_layout"] = layout
        return report

    # Step 2: resolve template source for shipped file classification
    template_source = resolve_template_source_for_layout(gator_dir)
    if not template_source and templates_dir:
        template_source = templates_dir

    includes = gator_dir / ".includes"
    includes.mkdir(exist_ok=True)

    # Step 4: move shipped root files
    for fname in SHIPPED_ROOT_FILES:
        src = gator_dir / fname
        dest = includes / fname
        if src.is_file() and not dest.exists():
            shutil.move(str(src), str(dest))
            report["moved"].append(fname)
        elif src.is_file() and dest.exists():
            # Both exist — remove the root copy (includes/ is canonical)
            src.unlink()
            report["moved"].append(f"{fname} (root copy removed)")

    # Also handle charterignore stored without dot
    charterignore = gator_dir / ".charterignore"
    dest_ci = includes / ".charterignore"
    if charterignore.is_file() and not dest_ci.exists():
        shutil.move(str(charterignore), str(dest_ci))
        report["moved"].append(".charterignore")

    # Step 5: move fully shipped directories
    for dname in SHIPPED_DIRECTORIES:
        src_dir = gator_dir / dname
        dest_dir = includes / dname
        if src_dir.is_dir():
            if not dest_dir.exists():
                shutil.move(str(src_dir), str(dest_dir))
                report["moved"].append(f"{dname}/")
            else:
                # Both exist — merge: move files not yet in dest.
                # Duplicate handling MUST mirror Step 4 (SHIPPED_ROOT_FILES):
                # when a file exists at BOTH src and dest, the dest copy
                # (`.includes/`) is canonical and the src copy is removed.
                # Without this, files that were both bootstrapped to root
                # AND populated in .includes/ (e.g. a repo that was
                # re-gatorized on top of a v1-shape port) leave the root
                # duplicates in place, migrate_layout reports "Result:
                # mixed (migration incomplete)" and never converges.
                # Fix committed 2026-08-02 after the monorepo cutover hit
                # exactly that state in .gator/reference-notes/ and had
                # to be resolved by hand.
                for f in sorted(src_dir.iterdir()):
                    dest_f = dest_dir / f.name
                    if f.is_file():
                        if not dest_f.exists():
                            shutil.move(str(f), str(dest_f))
                            report["moved"].append(f"{dname}/{f.name}")
                        else:
                            # Both exist — remove src (dest is canonical)
                            f.unlink()
                            report["moved"].append(
                                f"{dname}/{f.name} (root copy removed)"
                            )
                    elif f.is_dir() and not dest_f.exists():
                        shutil.move(str(f), str(dest_f))
                        report["moved"].append(f"{dname}/{f.name}/")
                    elif f.is_dir():
                        # Both directories exist. Known-safe legacy residue:
                        # __pycache__/ (Python bytecode, regenerated) and
                        # hooks/ (pre-monorepo git-hook install location —
                        # install_git_hooks now writes to .git/hooks/ or
                        # .git/gator-hooks/, so these copies are dead weight
                        # after migration). Remove src unconditionally for
                        # both. Everything else: recursive files-only merge
                        # (dest wins on collision) via _merge_dir_files_only.
                        # See Issue #6 for the field case that motivated this.
                        if f.name in ("__pycache__", "hooks"):
                            shutil.rmtree(str(f))
                            report["moved"].append(
                                f"{dname}/{f.name}/ (legacy residue removed)"
                            )
                        else:
                            _merge_dir_files_only(
                                f, dest_f, report,
                                prefix=f"{dname}/{f.name}",
                            )
                # Remove src if empty
                try:
                    src_dir.rmdir()
                except OSError:
                    pass
                report["moved"].append(f"{dname}/ (merged)")

    # Step 5a: regenerate Git hook wrappers for new .includes/scripts/ path
    hooks_installed = install_git_hooks(gator_dir, repo_root)
    if hooks_installed > 0:
        report["moved"].append(f"git hooks regenerated ({hooks_installed})")

    # Step 6: mixed directories — move only shipped files
    for dname in ("procedures", "charters", "blueprints"):
        src_dir = gator_dir / dname
        if not src_dir.is_dir():
            continue

        shipped_files = get_shipped_files_for_directory(
            dname, template_source=template_source
        )

        dest_dir = includes / dname
        dest_dir.mkdir(exist_ok=True)

        for f in sorted(src_dir.iterdir()):
            if not f.is_file():
                continue
            # Scaffolding stays at user-visible root
            if f.name in ("README.md", "_template.md"):
                report["preserved"].append(f"{dname}/{f.name} (scaffolding)")
                continue
            if f.name in shipped_files:
                dest_f = dest_dir / f.name
                if not dest_f.exists():
                    shutil.move(str(f), str(dest_f))
                    report["moved"].append(f"{dname}/{f.name}")
                else:
                    f.unlink()
                    report["moved"].append(f"{dname}/{f.name} (root copy removed)")
            else:
                report["preserved"].append(f"{dname}/{f.name}")

    # Steps 7-8: user and runtime files stay in place (no action needed)

    # Step 9: write layout-version.json
    import json as _json
    (gator_dir / "layout-version.json").write_text(
        _json.dumps({"layout": "v2"}) + "\n", encoding="utf-8"
    )

    # Step 10: emit report
    print()
    print("  gator migrate-layout")
    print()
    print(f"  Source layout: {layout}")
    print(f"  Moved to .includes/: {len(report['moved'])} items")
    for item in report["moved"]:
        print(f"    + {item}")
    if report["preserved"]:
        print(f"  Preserved at root: {len(report['preserved'])} user files")
        for item in report["preserved"]:
            print(f"    = {item}")
    if report["conflicts"]:
        print(f"  Conflicts: {len(report['conflicts'])}")
        for item in report["conflicts"]:
            print(f"    ! {item}")

    # Step 11: re-validate
    final_layout = resolve_gator_layout(repo_root)
    report["final_layout"] = final_layout
    print()
    if final_layout == "v2":
        print(f"  Result: v2 (clean)")
        print()
        print("  Next step: run 'gator update' to refresh scripts in .includes/")
        print("  with the latest resolver-aware versions.")
    elif final_layout == "mixed":
        print(f"  Result: mixed (migration incomplete — check conflicts)")
    else:
        print(f"  Result: {final_layout} (unexpected)")
    print()

    return report


# --- Entry point ---

def main():
    ensure_utf8_stdout()

    parser = argparse.ArgumentParser(
        description="Gator update — refresh templates and optionally sync org policy."
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be updated without changing anything"
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output update plan as JSON"
    )
    parser.add_argument(
        "--path", "-p",
        help="Path to search for .gator/ (default: current directory)"
    )
    parser.add_argument(
        "--source", "-s",
        help="Path to the Gator clone (rebinds product-source.json)"
    )
    parser.add_argument(
        "--migrate-layout",
        action="store_true",
        help="Migrate v1 flat layout to v2 .includes/ layout"
    )
    args = parser.parse_args()

    # Find the repo
    repo_root = find_gator_root(args.path)
    if not repo_root:
        print("  Error: no .gator/ found. Run from a gatorized repo.", file=sys.stderr)
        sys.exit(1)

    gator_dir = repo_root / ".gator"

    # Channel 1: resolve template source (product-source.json, --source, or thin link fallback)
    templates_dir, gator_root = resolve_template_source(gator_dir, args.source)
    if not templates_dir:
        # Self-heal: fall back to the running install's own location. gator-update.py
        # lives at <gator_root>/scripts/gator-update.py, so its parent.parent is a
        # valid gator_root with templates alongside — for the package install
        # (pipx site-packages) and for the dev source checkout alike. The
        # fleet-repo template mirror (`.gator/scripts/gator-update.py`) has no
        # templates alongside, so its parent.parent lookup fails and we fall
        # through to the original error — the fleet-repo mirror's caller should
        # use --source anyway.
        fallback_root = Path(__file__).resolve().parent.parent
        fallback_tpl = fallback_root / "templates" / "gator-starter"
        if fallback_tpl.is_dir():
            ps = read_product_source(gator_dir)
            stale_path = ps.get("gator_root", "?") if ps else "not configured"
            print(f"  Warning: recorded product template source not found — self-healing.")
            print(f"    Recorded: {stale_path}")
            print(f"    Rebinding to running install: {fallback_root}")
            templates_dir = fallback_tpl
            gator_root = fallback_root
            # Rewrite product-source.json so future runs don't need self-heal.
            import json as _json
            from datetime import date
            ps_file = gator_dir / "product-source.json"
            old_ps = read_product_source(gator_dir) or {}
            ps_data = {
                "gator_root": str(gator_root),
                "template_dir": "templates/gator-starter",
                "installed": old_ps.get("installed", ""),
                "updated": date.today().isoformat(),
            }
            try:
                ps_file.write_text(
                    _json.dumps(ps_data, indent=2) + "\n", encoding="utf-8",
                )
            except OSError as exc:
                print(f"    (Warning: could not rewrite product-source.json: {exc})")
        else:
            ps = read_product_source(gator_dir)
            stale_path = ps.get("gator_root", "?") if ps else "not configured"
            print(f"  Error: product template source not found.", file=sys.stderr)
            print(f"  Last known source: {stale_path}", file=sys.stderr)
            print(f"  Running install has no usable templates either — try:", file=sys.stderr)
            print(f"    gator update --source /path/to/gator", file=sys.stderr)
            sys.exit(1)

    # Update product-source.json if --source was given (rebind)
    if args.source:
        import json as _json
        ps_file = gator_dir / "product-source.json"
        tpl_rel = str(templates_dir.relative_to(gator_root))
        ps_data = {
            "gator_root": str(gator_root),
            "template_dir": tpl_rel,
            "installed": "",
            "updated": "",
        }
        # Preserve installed date if existing
        old_ps = read_product_source(gator_dir)
        if old_ps:
            ps_data["installed"] = old_ps.get("installed", "")
        from datetime import date
        ps_data["updated"] = str(date.today())
        if not ps_data["installed"]:
            ps_data["installed"] = ps_data["updated"]
        ps_file.write_text(_json.dumps(ps_data, indent=2) + "\n", encoding="utf-8")
        print(f"  Product source rebound to: {gator_root}")

    # Migration mode — separate code path
    if args.migrate_layout:
        report = migrate_layout(repo_root, gator_dir, templates_dir)
        # After a v1→v2 convergence the shipped script paths just moved from
        # `.gator/scripts/` to `.gator/.includes/scripts/`. Vendor SessionStart
        # hooks (Claude / Codex / Gemini) still point at the old paths until
        # `install_vendor_hooks` re-merges the current templates. Do that
        # inline so a caller who only runs `--migrate-layout` (and never a
        # follow-up `gator update`) doesn't end up with dead hook targets.
        # Wrap in try/except: a vendor-hook refresh failure must never mask
        # or override the migration's own exit code.
        if report.get("final_layout") == "v2":
            try:
                install_vendor_hooks(templates_dir, repo_root)
            except Exception as e:
                print(
                    f"  Warning: vendor hook refresh failed: {e}",
                    file=sys.stderr,
                )
        sys.exit(0 if report.get("final_layout") == "v2" else 1)

    # Build plan (refuses mixed/invalid layouts with a clean message)
    try:
        plan = plan_updates(templates_dir, gator_dir, repo_root)
    except RuntimeError as e:
        print(f"  Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Plan git hook installation
    hooks_to_install = plan_hook_updates(gator_dir, repo_root)

    # Plan entry-point block refresh (Stage 4b) — empty list when the
    # gatorize sub-package is not reachable (template copy on fleet repos).
    entry_point_actions = plan_entry_point_updates(repo_root)

    # JSON mode
    if args.json:
        print_json_plan(plan, templates_dir, hooks_to_install, entry_point_actions)
        return

    # Dry run
    if args.dry_run:
        print_plan(plan, dry_run=True, hooks=hooks_to_install, entry_point_actions=entry_point_actions)
        return

    # Converge gitignore rules (same as gatorize.py install/upgrade path)
    ensure_repo_gitignore(repo_root)

    # Execute
    print_plan(plan, hooks=hooks_to_install, entry_point_actions=entry_point_actions)
    added, updated, unchanged = execute_updates(plan)

    # Execute entry-point block refresh — Stage 4b. Counts feed into
    # print_result() and the .gator-version stamp gate below.
    entry_point_counts = (0, 0, 0, 0)
    if entry_point_actions:
        entry_point_counts = execute_entry_point_updates(repo_root, entry_point_actions)

    # Install/refresh git hooks
    hooks_installed = install_git_hooks(gator_dir, repo_root)
    if hooks_installed > 0:
        print(f"  Git hooks: {hooks_installed} installed/refreshed")

    # Install/merge vendor SessionStart hook configs
    vendor_hooks_changed = install_vendor_hooks(templates_dir, repo_root)
    if vendor_hooks_changed > 0:
        print(f"  Vendor hooks: {vendor_hooks_changed} config(s) installed/updated")

    # Update product-source.json timestamp
    ps = read_product_source(gator_dir)
    if ps:
        import json as _json
        from datetime import date
        ps["updated"] = str(date.today())
        ps_file = gator_dir / "product-source.json"
        ps_file.write_text(_json.dumps(ps, indent=2) + "\n", encoding="utf-8")

    # Stamp .gator-version. As of v2.4.2 (fleet-wide Dashboard fix):
    # - `cli-version` always stamps — records the CLI that last verified this
    #   repo. Without this, an already-current repo never re-stamps and the
    #   Dashboard Fleet Version column shows stale CLI forever, keeping its
    #   Update button falsely enabled.
    # - `updated:` still gates on file changes — preserves "last modification"
    #   timestamp semantics (Stage 4b: fires when file-overlay OR entry-point
    #   actions changed state).
    ep_refreshed, ep_upgraded, ep_created, _ = entry_point_counts
    ep_changed = ep_refreshed + ep_upgraded + ep_created > 0
    made_changes = added > 0 or updated > 0 or ep_changed
    version_file = gator_dir / ".gator-version"
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    cli_ver = get_version()
    if version_file.exists():
        lines = version_file.read_text(encoding="utf-8").splitlines()
        new_lines = []
        has_cli_version = False
        for line in lines:
            if line.startswith("updated:") and made_changes:
                new_lines.append(f"updated: {now}")
            elif line.startswith("cli-version:"):
                new_lines.append(f"cli-version: {cli_ver}")
                has_cli_version = True
            else:
                new_lines.append(line)
        if not has_cli_version:
            new_lines.append(f"cli-version: {cli_ver}")
        version_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    else:
        # No .gator-version at all — write a fresh stub. Handles both the
        # first-upgrade-of-a-gen-0-install case and the pathological
        # no-changes-and-no-file case (still records that gator-update ran).
        version_file.write_text(
            f"generation: 2\n"
            f"installed: {now}\n"
            f"updated: {now}\n"
            f"action: update\n"
            f"installer: gator-update.py\n"
            f"cli-version: {cli_ver}\n",
            encoding="utf-8",
        )

    print_result(added, updated, unchanged, entry_point_counts=entry_point_counts)


if __name__ == "__main__":
    main()
