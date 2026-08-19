"""Enterprise vendor SessionStart hook install — MACHINE-scoped, merge-safe.

Installs Gator SessionStart hooks into vendor-tool settings files at the
USER HOME level (not per-repo):
  ~/.claude/settings.json
  ~/.codex/hooks.json
  ~/.gemini/settings.json

Applies to every vendor session on this machine, regardless of which
repo the user opens. Distinct from base Gator's REPO-scoped variant
(`gator-update.py::install_vendor_hooks(templates_dir, repo_root)`,
which writes to `<repo>/.claude/settings.json` and applies only when
that specific repo is opened). Both merge-safe, both similar merge
logic, different installation scope — that's why the module and
function names carry the `enterprise_` prefix. Grep for
`install_enterprise_vendor_hooks` to find call sites; grep for
`install_vendor_hooks` for the base repo-scoped variant.

Merge-safe by construction: preserves user hooks, identifies
Gator-managed entries by `.gator/` in the command string, updates
Gator hooks in place on re-invocation or `--force`. Creates parent
directories if missing — never silently skips. Fail-closed on
malformed/wrong-shape settings files (returns "unchanged", never
clobbers).

Called from `gator enterprise setup --install-hooks` (Phase 4c-B,
2026-08-01). Not called from base-Gator paths — this is
Enterprise-adjacent behavior gated by the Enterprise CLI's opt-in flag.

Every function accepts an optional `home` parameter (defaults to
`Path.home()`) so tests can supply `tmp_path` as a fake home directory
without monkeypatching. Structural testability, not runtime mocking.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


# SessionStart hook templates — the commands that run when a vendor
# session starts. Runtime-split Phase 3b (2026-08-19): route through the
# installed CLI's `gator hook` dispatcher (resolves pinned vs repo
# runtime per repo; warning-mode no-op on ungoverned CWDs). This also
# fixes Phase-0 finding F1: the previous commands used v1 paths
# (.gator/scripts/) that have been dead on v2 repos since the .includes
# split — machine-hook session registration was silently no-op there.
# Degradation: a machine without `gator` on PATH loses session
# registration (visible hook error, session proceeds) — the CLI is a
# prerequisite of Enterprise activation anyway.
HOOK_TEMPLATES = {
    "claude": {
        "hooks": {
            "SessionStart": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "gator hook session-open",
                            "timeout": 5,
                        },
                        {
                            "type": "command",
                            "command": "gator hook session-start",
                            "timeout": 5,
                        },
                    ]
                }
            ]
        }
    },
    "codex": {
        "hooks": {
            "SessionStart": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "gator hook session-open",
                            "timeout": 10,
                        },
                        {
                            "type": "command",
                            "command": "gator hook session-start",
                            "timeout": 10,
                        },
                    ]
                }
            ]
        }
    },
    "gemini": {
        "hooks": {
            "SessionStart": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "gator hook session-open",
                            "timeout": 5,
                        },
                        {
                            "type": "command",
                            "command": "gator hook session-start",
                            "timeout": 5,
                        },
                    ]
                }
            ]
        }
    },
}

# Vendor config: (display_name, settings_dir_name, settings_filename).
# The dir_name maps to a template key via _DIR_TO_TEMPLATE below.
VENDOR_CONFIGS = [
    ("Claude Code", ".claude", "settings.json"),
    ("Codex CLI", ".codex", "hooks.json"),
    ("Gemini CLI", ".gemini", "settings.json"),
]

_DIR_TO_TEMPLATE = {
    ".claude": "claude",
    ".codex": "codex",
    ".gemini": "gemini",
}


def install_enterprise_vendor_hooks(force: bool = False, home: Optional[Path] = None) -> dict:
    """Install vendor SessionStart hooks at MACHINE level (~/.claude, etc.).

    Merge-safe: preserves user hooks, updates only Gator-managed entries.
    Creates parent directories if missing — never skips.

    Args:
        force: If True, re-apply the template even when existing Gator
            commands match — useful for template drift recovery.
        home: If provided, treat as the user's home directory (tests
            supply a tmp_path here). Defaults to `Path.home()`.

    Returns:
        Dict mapping vendor display name to one of "installed",
        "updated", or "unchanged". Never raises for expected error
        modes (missing dirs, malformed JSON) — callers can trust the
        return value to describe what happened.
    """
    home_dir = Path(home) if home is not None else Path.home()
    results: dict = {}

    for vendor_name, settings_dir, settings_file in VENDOR_CONFIGS:
        template_key = _DIR_TO_TEMPLATE[settings_dir]
        template = HOOK_TEMPLATES[template_key]
        settings_path = home_dir / settings_dir / settings_file

        result = _merge_hooks(settings_path, template, force=force)
        results[vendor_name] = result

    return results


def _is_gator_hook_command(cmd):
    """True when a vendor-hook command string is Gator-managed.

    Recognizes both generations: the pre-Phase-3 repo-script invocations
    (".gator/" path substring) and the Phase 3b machine-side CLI route
    ("gator hook <name>"). Both must match or updates would duplicate
    the Gator group when migrating between generations.
    """
    return ".gator/" in cmd or cmd.strip().startswith("gator hook ")


def _merge_hooks(settings_path: Path, template: dict, force: bool = False) -> str:
    """Merge Gator SessionStart hooks into a vendor settings file.

    Returns: "installed", "updated", or "unchanged".
    """
    template_hooks = template.get("hooks", {})

    # File doesn't exist — create it with just the template.
    if not settings_path.exists():
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(
            json.dumps(template, indent=2) + "\n", encoding="utf-8"
        )
        return "installed"

    # Read existing — refuse to clobber on parse errors.
    try:
        existing = json.loads(settings_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        return "unchanged"

    if not isinstance(existing, dict):
        return "unchanged"

    existing_hooks = existing.get("hooks", {})
    if not isinstance(existing_hooks, dict):
        # `hooks` is present but wrong type (e.g., a string or a list).
        # Never clobber — fail closed. Codex Phase 4c-B review caught
        # this on the ported enterprise variant; base Gator's
        # gator-update.py version already had the correct check.
        return "unchanged"

    needs_update = False

    for event_name, groups in template_hooks.items():
        if event_name not in existing_hooks:
            # No hooks for this event yet — add ours.
            existing_hooks[event_name] = groups
            needs_update = True
        else:
            event_value = existing_hooks[event_name]
            if not isinstance(event_value, list):
                continue

            # Extract template hook commands.
            template_hooks_list = []
            for group in groups:
                if isinstance(group, dict):
                    template_hooks_list = group.get("hooks", [])
                    break
            if not template_hooks_list:
                continue

            # Find existing Gator group (identified by `.gator/` in
            # command strings). Any other groups are user hooks and
            # MUST be preserved unchanged.
            gator_group = None
            for existing_group in event_value:
                if not isinstance(existing_group, dict):
                    continue
                group_hooks = existing_group.get("hooks", [])
                group_cmds = [
                    h.get("command", "") for h in group_hooks if isinstance(h, dict)
                ]
                if any(_is_gator_hook_command(cmd) for cmd in group_cmds):
                    gator_group = existing_group
                    break

            if gator_group is None:
                # No Gator hooks yet — append a new group.
                event_value.append({"hooks": list(template_hooks_list)})
                needs_update = True
            else:
                # Gator hooks exist — check whether they still match
                # the template. On drift or --force, re-apply.
                existing_hooks_list = gator_group.get("hooks", [])
                existing_gator = [
                    h for h in existing_hooks_list
                    if isinstance(h, dict) and _is_gator_hook_command(h.get("command", ""))
                ]
                user_hooks_in_group = [
                    h for h in existing_hooks_list
                    if not (
                        isinstance(h, dict)
                        and _is_gator_hook_command(h.get("command", ""))
                    )
                ]
                existing_gator_cmds = [h.get("command", "") for h in existing_gator]
                template_cmds = [
                    h.get("command", "")
                    for h in template_hooks_list
                    if isinstance(h, dict)
                ]

                if force or existing_gator_cmds != template_cmds:
                    # Re-apply template, preserving any user hooks
                    # that happened to share the group.
                    gator_group["hooks"] = list(template_hooks_list) + user_hooks_in_group
                    needs_update = True

    if not needs_update:
        return "unchanged"

    existing["hooks"] = existing_hooks
    settings_path.write_text(
        json.dumps(existing, indent=2) + "\n", encoding="utf-8"
    )
    return "updated"
