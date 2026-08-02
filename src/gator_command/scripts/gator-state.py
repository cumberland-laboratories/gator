#!/usr/bin/env python3
"""
gator state — report and repair the managed state of a governed repo.

Stage 4 of `2026-07-28-local-agent-overrides-and-managed-state-plan.md`.
Narrow first cut: entry-point files (CLAUDE.md / AGENTS.md / GEMINI.md)
and constitution drift (fleet repos only). Constitution repair is deferred
to a future release; foreign entry-point files are referred to `gatorize`.

Subcommands:
  gator state status    Report managed state (text or JSON)
  gator state repair    Restore managed regions (six-state dispatch)
"""

import argparse
import json
import shutil
import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from gator_core import (
    get_version, find_gator_root, ensure_utf8_stdout,
    resolve_template_source, read_product_source,
)
from gator_layout import get_gator_paths
from gatorize.entry_points import render_entry_content, upgrade_legacy_entry_point
from gatorize.managed_block import (
    GATOR_BEGIN, GATOR_END,
    BlockState,
    find_managed_block,
    classify_managed_block,
    render_managed_region,
)


SCHEMA = "gator-state-v1"

# Vendor entry-point metadata. Single source of truth for filename,
# agent_type, and rollback-name mappings used across status and repair.
_ENTRY_POINTS = [
    {"filename": "CLAUDE.md", "agent_type": "claude", "rollback": "CLAUDE_ROLLBACK.md", "header": "# Claude Code Entry Point"},
    {"filename": "AGENTS.md", "agent_type": "agents", "rollback": "AGENTS_ROLLBACK.md", "header": "# Codex Entry Point"},
    {"filename": "GEMINI.md", "agent_type": "gemini", "rollback": "GEMINI_ROLLBACK.md", "header": "# Gemini Entry Point"},
]


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

def is_source_repo(repo_root):
    """True if the repo is the source `gator-command` repo.

    Detection: presence of `gator-command/mission.md` alongside root
    `constitution.md`. See "Source-repo exception" in the Stage plan.
    """
    return (
        (repo_root / "gator-command" / "mission.md").exists()
        and (repo_root / "constitution.md").exists()
    )


def read_repo_gator_version(repo_root):
    """Return the `cli-version` recorded in `.gator/.gator-version`, or None.

    Never raises — returns None on missing file, unreadable content, or
    absent key. Used for the version-diagnostic line only.
    """
    version_file = repo_root / ".gator" / ".gator-version"
    if not version_file.exists():
        return None
    try:
        text = version_file.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    for line in text.splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            if key.strip() == "cli-version":
                v = val.strip()
                return v or None
    return None


def local_companion_present(repo_root, filename):
    """True if the corresponding `*.local.md` companion file exists at repo root.

    NEVER reads the file — only `.exists()`. Local ownership boundary
    (Invariant #7) forbids reading these files from any Gator code path.
    """
    stem = Path(filename).stem  # "CLAUDE.md" → "CLAUDE"
    return (repo_root / f"{stem}.local.md").exists()


# ---------------------------------------------------------------------------
# Status collection
# ---------------------------------------------------------------------------

def classify_entry_point(repo_root, filename, agent_type):
    """Classify a single entry-point file. Returns (BlockState, text_or_None)."""
    filepath = repo_root / filename
    baseline = render_entry_content(has_command_post=False, agent_type=agent_type)
    if not filepath.exists():
        return classify_managed_block("", baseline, file_exists=False), None
    text = filepath.read_text(encoding="utf-8", errors="replace")
    return classify_managed_block(text, baseline, file_exists=True), text


def check_constitution(repo_root, templates_dir):
    """Return a dict describing constitution drift, or the source-repo exemption.

    Returns one of:
      {"status": "source-repo-exempt"}
      {"status": "no-baseline"}
      {"status": "no-repo-constitution"}
      {"status": "clean"}
      {"status": "modified"}
    """
    if is_source_repo(repo_root):
        return {"status": "source-repo-exempt"}
    if templates_dir is None:
        return {"status": "no-baseline"}

    template_constitution = templates_dir / "constitution.md"
    if not template_constitution.exists():
        return {"status": "no-baseline"}

    paths = get_gator_paths(repo_root)
    repo_constitution = paths.constitution
    if not repo_constitution.exists():
        return {"status": "no-repo-constitution"}

    template_bytes = template_constitution.read_bytes()
    repo_bytes = repo_constitution.read_bytes()
    if template_bytes == repo_bytes:
        return {"status": "clean"}
    return {"status": "modified"}


def check_constitution_drift(repo_root):
    """Convenience wrapper — resolves the template source internally.

    Returns the same status dict as `check_constitution()`. Never raises;
    any failure inside `resolve_template_source()` degrades to
    `{"status": "no-baseline"}`. Used by `gator-init.py` (via
    `import_sibling`) to append a drift suffix to the boot output without
    forcing the caller to know about template resolution.

    Stage 5 of the local-agent-overrides + managed-state plan.
    """
    try:
        gator_dir = repo_root / ".gator"
        templates_dir, _gator_root = resolve_template_source(gator_dir)
    except Exception:
        templates_dir = None
    return check_constitution(repo_root, templates_dir)


def collect_status(repo_root):
    """Assemble the full status report as a dict.

    Two independent baselines with different lifecycles:
    - **Entry-point baseline** is `render_entry_content()` from the currently-imported
      `gator_command` package (moves on `pipx upgrade`). Not a file, not overridable.
    - **Constitution baseline** is the file at `resolve_template_source()`
      (moves on `product-source.json` rebind or upstream template update).
    """
    gator_dir = repo_root / ".gator"
    templates_dir, _gator_root = resolve_template_source(gator_dir)

    entry_reports = []
    for meta in _ENTRY_POINTS:
        state, _text = classify_entry_point(repo_root, meta["filename"], meta["agent_type"])
        entry_reports.append({
            "filename": meta["filename"],
            "agent_type": meta["agent_type"],
            "state": state.value,
            "local_companion": "present" if local_companion_present(repo_root, meta["filename"]) else "absent",
        })

    constitution_report = check_constitution(repo_root, templates_dir)

    return {
        "schema": SCHEMA,
        "repo_root": str(repo_root),
        "host_cli_version": get_version(),
        "repo_gator_version": read_repo_gator_version(repo_root),
        "entry_point_baseline_kind": "installed-package-code",
        "constitution_baseline_source": str(templates_dir) if templates_dir else None,
        "entry_points": entry_reports,
        "constitution": constitution_report,
    }


# ---------------------------------------------------------------------------
# Status output
# ---------------------------------------------------------------------------

def _format_version_diagnostic(host_v, repo_v):
    if not host_v:
        return None
    if repo_v and repo_v != host_v:
        return f"host: gator {host_v} · repo: gatorized with gator {repo_v}"
    return f"host: gator {host_v}"


def render_status_text(report):
    """Render the status report as concise text output."""
    lines = []
    diag = _format_version_diagnostic(report["host_cli_version"], report["repo_gator_version"])
    if diag:
        lines.append(diag)
    lines.append("")
    lines.append("  entry points:")
    for ep in report["entry_points"]:
        companion = f"· {ep['agent_type'].upper()}.local.md {ep['local_companion']}"
        lines.append(f"    {ep['filename']:<12} {ep['state']:<11} {companion}")
    lines.append("")
    c = report["constitution"]
    status = c["status"]
    if status == "source-repo-exempt":
        con_line = "source-repo — baseline is authoritative"
    elif status == "no-baseline":
        con_line = "no template source available"
    elif status == "no-repo-constitution":
        con_line = "constitution absent in repo"
    elif status == "clean":
        con_line = "matches baseline"
    elif status == "modified":
        con_line = "modified from baseline"
    else:
        con_line = status
    lines.append(f"  constitution: {con_line}")
    return "\n".join(lines) + "\n"


def render_status_json(report):
    return json.dumps(report, indent=2) + "\n"


# ---------------------------------------------------------------------------
# Repair
# ---------------------------------------------------------------------------

def _fresh_file_content(header, managed_block):
    """The byte-format an installer would write for a missing entry-point file."""
    return f"{header}\n\nYou are the primary agent for this project.\n\n{managed_block}\n"


def plan_repair(repo_root, only_filename=None):
    """Return a list of planned repair actions. Read-only."""
    actions = []
    for meta in _ENTRY_POINTS:
        if only_filename and meta["filename"] != only_filename:
            continue
        state, _text = classify_entry_point(repo_root, meta["filename"], meta["agent_type"])
        action = _plan_action_for_state(state, meta)
        actions.append({
            "filename": meta["filename"],
            "agent_type": meta["agent_type"],
            "state": state.value,
            "action": action,
        })
    return actions


def _plan_action_for_state(state, meta):
    if state is BlockState.CLEAN:
        return "noop"
    if state is BlockState.MODIFIED:
        return "restore-block"
    if state is BlockState.LEGACY:
        return "upgrade-legacy"
    if state is BlockState.CORRUPTED:
        return f"backup-to-{meta['rollback']}-then-recreate"
    if state is BlockState.ABSENT:
        return "create-fresh"
    if state is BlockState.FOREIGN:
        return "skip-refer-to-gatorize"
    return "unknown"


def execute_repair(repo_root, plan):
    """Apply the planned repair actions. Returns the same plan with 'outcome' fields."""
    for entry in plan:
        outcome = _execute_one(repo_root, entry)
        entry["outcome"] = outcome
    return plan


def _execute_one(repo_root, entry):
    filename = entry["filename"]
    agent_type = entry["agent_type"]
    action = entry["action"]
    filepath = repo_root / filename
    meta = next(m for m in _ENTRY_POINTS if m["filename"] == filename)

    if action == "noop":
        return "unchanged"

    if action == "restore-block":
        text = filepath.read_text(encoding="utf-8", errors="replace")
        location = find_managed_block(text)
        if location is None:
            # State said MODIFIED, so find_managed_block should succeed;
            # defensively skip if the file changed between plan and execute.
            return "skipped-race"
        baseline = render_entry_content(has_command_post=False, agent_type=agent_type)
        expected_region = render_managed_region(baseline)
        new_text = f"{location.before}{GATOR_BEGIN}{expected_region}{GATOR_END}{location.after}"
        filepath.write_text(new_text, encoding="utf-8")
        return "restored"

    if action == "upgrade-legacy":
        upgrade_legacy_entry_point(repo_root, filename, has_command_post=False, agent_type=agent_type)
        return "upgraded"

    if action.startswith("backup-to-"):
        # Backup existing to <VENDOR>_ROLLBACK.md then write fresh
        rollback = meta["rollback"]
        shutil.copy2(filepath, repo_root / rollback)
        baseline = render_entry_content(has_command_post=False, agent_type=agent_type)
        managed_block = f"{GATOR_BEGIN}{render_managed_region(baseline)}{GATOR_END}"
        filepath.write_text(_fresh_file_content(meta["header"], managed_block), encoding="utf-8")
        return f"backed-up-to-{rollback}-and-recreated"

    if action == "create-fresh":
        baseline = render_entry_content(has_command_post=False, agent_type=agent_type)
        managed_block = f"{GATOR_BEGIN}{render_managed_region(baseline)}{GATOR_END}"
        filepath.write_text(_fresh_file_content(meta["header"], managed_block), encoding="utf-8")
        return "created"

    if action == "skip-refer-to-gatorize":
        return "skipped-foreign"

    return "skipped-unknown"


# ---------------------------------------------------------------------------
# Repair output
# ---------------------------------------------------------------------------

def render_repair_text(plan, dry_run):
    lines = []
    header = "  gator state repair (dry-run) — planned actions:" if dry_run else "  gator state repair — outcomes:"
    lines.append(header)
    for entry in plan:
        state = entry["state"]
        action = entry["action"]
        if dry_run:
            lines.append(f"    {entry['filename']:<12} {state:<11} → would: {action}")
        else:
            outcome = entry.get("outcome", "?")
            lines.append(f"    {entry['filename']:<12} {state:<11} → {outcome}")
    lines.append("")
    lines.append("  constitution: repair deferred (v1 detection-only — copy manually if needed)")
    lines.append("  local companions: preserved (never touched by gator state)")
    return "\n".join(lines) + "\n"


def render_repair_json(plan, dry_run):
    return json.dumps({
        "schema": SCHEMA,
        "dry_run": dry_run,
        "actions": plan,
        "constitution": "repair-deferred-v1",
        "local_companions": "preserved",
    }, indent=2) + "\n"


# ---------------------------------------------------------------------------
# Subcommand entry points
# ---------------------------------------------------------------------------

def main_status(args):
    repo_root = find_gator_root(args.path)
    if not repo_root:
        print("  Error: no .gator/ found. Run from a gatorized repo.", file=sys.stderr)
        return 1
    report = collect_status(repo_root)
    if args.json:
        sys.stdout.write(render_status_json(report))
    else:
        sys.stdout.write(render_status_text(report))
    return 0


def main_repair(args):
    repo_root = find_gator_root(args.path)
    if not repo_root:
        print("  Error: no .gator/ found. Run from a gatorized repo.", file=sys.stderr)
        return 1
    only = args.filename if args.filename else None
    plan = plan_repair(repo_root, only_filename=only)
    if args.dry_run:
        if args.json:
            sys.stdout.write(render_repair_json(plan, dry_run=True))
        else:
            sys.stdout.write(render_repair_text(plan, dry_run=True))
        return 0
    plan = execute_repair(repo_root, plan)
    if args.json:
        sys.stdout.write(render_repair_json(plan, dry_run=False))
    else:
        sys.stdout.write(render_repair_text(plan, dry_run=False))
    return 0


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def _build_parser():
    parser = argparse.ArgumentParser(
        prog="gator state",
        description="Report or repair the managed state of a governed repo.",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_status = sub.add_parser("status", help="Report managed state (text or JSON)")
    p_status.add_argument("--path", default=None, help="Repo root (default: cwd)")
    p_status.add_argument("--json", action="store_true", help="Emit JSON output")

    p_repair = sub.add_parser("repair", help="Restore managed regions (six-state dispatch)")
    p_repair.add_argument("filename", nargs="?", default=None,
                          help="Restrict repair to a single entry-point file (default: all three)")
    p_repair.add_argument("--path", default=None, help="Repo root (default: cwd)")
    p_repair.add_argument("--dry-run", action="store_true", help="Preview planned actions without touching the filesystem")
    p_repair.add_argument("--json", action="store_true", help="Emit JSON output")

    return parser


def main():
    ensure_utf8_stdout()
    parser = _build_parser()
    args = parser.parse_args()
    if args.subcommand == "status":
        sys.exit(main_status(args))
    if args.subcommand == "repair":
        sys.exit(main_repair(args))
    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
