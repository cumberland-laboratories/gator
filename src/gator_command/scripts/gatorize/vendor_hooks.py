"""Vendor hook merge logic for SessionStart hook configs.

Handles merge-safe installation of Gator hooks into vendor settings
files (.claude/settings.json, .codex/hooks.json, .gemini/settings.json).

This is the single source of truth for vendor hook merge behavior.
The template-deployed gator-update.py has its own copy (fleet repos
cannot import from the gatorize package).
"""

import json
from pathlib import Path


# Vendor hook config: (template_file, target_dir, target_filename)
VENDOR_HOOK_CONFIGS = [
    ("vendor-hooks/claude-settings.json", ".claude", "settings.json"),
    ("vendor-hooks/codex-hooks.json", ".codex", "hooks.json"),
    ("vendor-hooks/gemini-settings.json", ".gemini", "settings.json"),
]


def _extract_hook_commands(groups):
    """Extract all command strings from a list of hook groups."""
    commands = set()
    for group in groups:
        if not isinstance(group, dict):
            continue
        for hook in group.get("hooks", []):
            if isinstance(hook, dict) and "command" in hook:
                commands.add(hook["command"])
    return commands


def _is_gator_hook_command(cmd):
    """True when a vendor-hook command string is Gator-managed.

    Recognizes all three shapes: the pre-Phase-3 repo-script invocations
    (".gator/" path substring — also matches the Phase 3b shell-chain
    fallback), the bare CLI route ("gator hook <name>"), and the
    absolute-launcher route ('"/path/to/gator[.exe]" hook <name>' —
    emitted machine-side by Enterprise). All must match or updates would
    duplicate the Gator group when migrating between generations.
    """
    if ".gator/" in cmd:
        return True
    s = cmd.strip()
    if s.startswith('"'):
        end = s.find('"', 1)
        if end == -1:
            return False
        head, rest = s[1:end], s[end + 1:].lstrip()
    else:
        parts = s.split(None, 1)
        head, rest = parts[0], (parts[1] if len(parts) > 1 else "")
    exe = head.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return exe in ("gator", "gator.exe") and rest.startswith("hook ")


def merge_hooks_into_settings(settings_path, hooks_template_path):
    """Merge Gator hooks into a vendor settings JSON file without clobbering.

    Finds the existing Gator group (identified by .gator/ in command strings),
    separates Gator hooks from user hooks, and rebuilds with template Gator
    hooks followed by preserved user hooks when commands or ordering differ.
    Falls back to appending a new group if no Gator group exists.

    Never clobbers existing permissions, env vars, or user hooks.

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

    try:
        existing = json.loads(settings_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        return "unchanged"

    if not isinstance(existing, dict):
        return "unchanged"

    existing_hooks = existing.get("hooks", {})
    if not isinstance(existing_hooks, dict):
        return "unchanged"

    needs_update = False

    for event_name, groups in template_hooks.items():
        if event_name not in existing_hooks:
            existing_hooks[event_name] = groups
            needs_update = True
        else:
            event_value = existing_hooks[event_name]
            if not isinstance(event_value, list):
                continue
            template_hooks_list = []
            for group in groups:
                if isinstance(group, dict):
                    template_hooks_list = group.get("hooks", [])
                    break
            if not template_hooks_list:
                continue

            gator_group = None
            for existing_group in event_value:
                if not isinstance(existing_group, dict):
                    continue
                group_hooks = existing_group.get("hooks", [])
                group_cmds = [h.get("command", "") for h in group_hooks if isinstance(h, dict)]
                if any(_is_gator_hook_command(cmd) for cmd in group_cmds):
                    gator_group = existing_group
                    break

            if gator_group is None:
                event_value.append({"hooks": list(template_hooks_list)})
                needs_update = True
            else:
                existing_hooks_list = gator_group.get("hooks", [])
                existing_gator = [h for h in existing_hooks_list if isinstance(h, dict) and _is_gator_hook_command(h.get("command", ""))]
                user_hooks = [h for h in existing_hooks_list if not (isinstance(h, dict) and _is_gator_hook_command(h.get("command", "")))]
                existing_gator_cmds = [h.get("command", "") for h in existing_gator]
                template_cmds = [h.get("command", "") for h in template_hooks_list if isinstance(h, dict)]
                if existing_gator_cmds != template_cmds:
                    gator_group["hooks"] = list(template_hooks_list) + user_hooks
                    needs_update = True

    if not needs_update:
        return "unchanged"

    existing["hooks"] = existing_hooks
    settings_path.write_text(
        json.dumps(existing, indent=2) + "\n", encoding="utf-8"
    )
    return "update"


def install_vendor_hooks(templates_dir, repo_root):
    """Install vendor SessionStart hook configs into the repo (merge-safe).

    Returns count of files changed.
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
