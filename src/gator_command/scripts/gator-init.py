#!/usr/bin/env python3
"""
gator init — Branded boot sequence for Gator-governed repos.

Detects .gator/ in the current directory (or a specified path), reads
the knowledge layer, and prints a formatted status display. Designed
to run at session open in any AI CLI (Claude Code, Codex, Gemini).

Usage:
    python .gator/scripts/gator-init.py
    python .gator/scripts/gator-init.py --path /some/repo
    python .gator/scripts/gator-init.py --json

@reads: .gator/ directory structure, constitution.md, charters/, threads/
@writes: .git/hooks/ (self-heal only when hooks are missing or stale)
"""

import argparse
import json
import re
import sys
from pathlib import Path

from gator_core import (
    get_version, find_gator_root, ensure_utf8_stdout, GATOR_MARK_LINES,
    import_sibling, ensure_dashboard_registry_entry,
)
from gator_layout import get_gator_paths

VERSION = get_version()

TAGLINE = "oriented. the terrain is mapped."


# --- Detection and counting ---

def count_constitution_rules(paths):
    """Count enforceable rules in the constitution.

    Counts numbered list items, table rows with content, and bold-prefixed
    rules. This is a heuristic — not a parser.

    @reads: constitution.md (resolved by layout)
    """
    constitution = paths.constitution
    if not constitution.exists():
        return 0

    text = constitution.read_text(encoding="utf-8", errors="replace")
    count = 0

    for line in text.splitlines():
        stripped = line.strip()
        # Numbered steps (1. **Before changing code**: ...)
        if re.match(r'^\d+\.?\s+\*\*', stripped):
            count += 1
        # Bold-prefixed rules (- **BRANCHING**: ...)
        elif re.match(r'^-\s+\*\*[A-Z]', stripped):
            count += 1
        # Standalone bold imperatives (**The agent always asks before committing**)
        elif re.match(r'^\*\*The (agent|Architect|PI|enforcer)', stripped):
            count += 1

    return count


def count_charters(paths):
    """Count charter files and estimate mapping coverage.

    @reads: charters/ (resolved by layout)
    """
    charters_dir = paths.charters_dir
    if not charters_dir.is_dir():
        return 0, 0, 0.0

    skip = {"_template.md", "README.md", "INDEX.md"}
    charter_files = [
        f for f in charters_dir.iterdir()
        if f.suffix == ".md" and f.name not in skip
    ]

    # Count function entries across all charters (lines starting with ### )
    function_count = 0
    for cf in charter_files:
        text = cf.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if line.strip().startswith("### ") and "(" in line:
                function_count += 1

    # Estimate total functions in the repo (count def/func/function declarations)
    repo_root = paths.gator_root.parent
    total_functions = 0
    for ext in ("*.py", "*.gd", "*.js", "*.ts", "*.go", "*.rs", "*.java"):
        for code_file in repo_root.rglob(ext):
            # Skip .gator/ itself
            if ".gator" in str(code_file):
                continue
            try:
                text = code_file.read_text(encoding="utf-8", errors="replace")
                for line in text.splitlines():
                    stripped = line.strip()
                    if (stripped.startswith("def ") or
                        stripped.startswith("func ") or
                        stripped.startswith("function ") or
                        re.match(r'^(pub\s+)?(fn|func)\s+', stripped) or
                        re.match(r'^(export\s+)?(async\s+)?function\s+', stripped)):
                        total_functions += 1
            except (OSError, UnicodeDecodeError):
                continue

    coverage = (function_count / total_functions * 100) if total_functions > 0 else 0.0

    return len(charter_files), function_count, coverage


def count_working_set(paths):
    """Count threads and their total line count.

    @reads: threads/, active-threads/ (resolved by layout)
    """
    total_threads = 0
    total_lines = 0

    for subdir in (paths.active_threads_dir, paths.threads_dir):
        if not subdir.is_dir():
            continue
        for f in subdir.iterdir():
            if f.suffix == ".md" and f.name != ".gitkeep":
                total_threads += 1
                try:
                    total_lines += len(f.read_text(encoding="utf-8", errors="replace").splitlines())
                except (OSError, UnicodeDecodeError):
                    pass

    return total_threads, total_lines


def detect_enforcer(paths):
    """Detect enforcer configuration.

    @reads: scripts/enforcer-prompt.md, scripts/enforcer-review.py (resolved by layout)
    """
    has_prompt = (paths.scripts_dir / "enforcer-prompt.md").exists()
    has_script = (paths.scripts_dir / "enforcer-review.py").exists()

    if has_prompt and has_script:
        return "ready"
    elif has_prompt or has_script:
        return "partial"
    else:
        return "not configured"


def count_field_guides(paths):
    """Count field guide languages from pattern files.

    Field guides use two files per language: {lang}-patterns.md and
    {lang}-tutorial.md. Count languages from pattern files.

    @reads: field-guides/ (resolved by layout)
    """
    guides_dir = paths.field_guides_dir
    if not guides_dir.is_dir():
        return 0, []

    guides = [
        f.name.removesuffix("-patterns.md")
        for f in guides_dir.iterdir()
        if f.name.endswith("-patterns.md")
    ]
    return len(guides), sorted(guides)



def read_version(paths):
    """Read generation from .gator-version.

    @reads: .gator/.gator-version (always at root)
    """
    version_file = paths.gator_root / ".gator-version"
    if not version_file.exists():
        return None

    text = version_file.read_text(encoding="utf-8", errors="replace")
    info = {}
    for line in text.splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            info[key.strip()] = val.strip()
    return info


def ensure_git_hooks(repo_root, paths):
    """Self-heal git hooks at session start.

    Uses gator-update's hook planning and installation logic so there is
    exactly one definition of what "correctly installed hooks" means.
    """
    try:
        gator_update = import_sibling("gator-update")
    except ImportError as e:
        return {
            "status": "error",
            "detail": f"hook repair unavailable: {e}",
            "adds": 0,
            "updates": 0,
        }
    if gator_update is None:
        return {
            "status": "error",
            "detail": "gator-update.py not found",
            "adds": 0,
            "updates": 0,
        }

    if not (repo_root / ".git").exists():
        return {
            "status": "unavailable",
            "detail": "no .git directory",
            "adds": 0,
            "updates": 0,
        }

    # Check that the hook target script exists — without it, hooks can't work
    # even if they're installed, and plan_hook_updates returns [] (masking the problem).
    gator_script = paths.scripts_dir / "gator-pre-commit.py"
    # Runtime-split Phase 3 (S5): a PINNED repo needs no repo-resident
    # script — its stubs route through the installed CLI's dispatcher.
    # Only script-missing AND pin-missing is a genuinely degraded state.
    _pin_present = (repo_root / ".gator" / "runtime-pin.json").is_file()
    if not gator_script.exists() and not _pin_present:
        return {
            "status": "degraded",
            "detail": "gator-pre-commit.py missing",
            "adds": 0,
            "updates": 0,
        }

    # 2026-08-28: probe the shebang resolver directly. plan_hook_updates()
    # swallows HookShebangUnresolvable and returns [] to keep the main
    # `gator update` path clean, but for session-open we must distinguish
    # "hook install refused" from "no changes needed" — otherwise the
    # loud install-time refusal collapses into a false-green `ok` here
    # on exactly the machines the shebang fix is meant to protect.
    _hookshebang_exc = getattr(gator_update, "HookShebangUnresolvable", None)
    if _hookshebang_exc is not None:
        try:
            gator_update._hook_shebang()
        except _hookshebang_exc as exc:
            return {
                "status": "degraded",
                "detail": f"hook shebang unresolvable: {exc}",
                "adds": 0,
                "updates": 0,
            }

    plan = gator_update.plan_hook_updates(paths.gator_root, repo_root)
    adds = sum(1 for _, action in plan if action == "add")
    updates = sum(1 for _, action in plan if action == "update")

    if adds or updates:
        installed = gator_update.install_git_hooks(paths.gator_root, repo_root)
        if updates:
            detail = f"refreshed ({installed} hooks)"
            status = "refreshed"
        else:
            detail = f"installed ({installed} hooks)"
            status = "installed"
    else:
        detail = "ok"
        status = "ok"

    return {
        "status": status,
        "detail": detail,
        "adds": adds,
        "updates": updates,
    }


# --- Output formatting ---

def _constitution_drift_suffix(repo_root):
    """Return " · modified from baseline" when constitution drifts, else "".

    Stage 5. Best-effort: any failure — missing sibling script, unresolvable
    template source, unreadable files — degrades silently to no suffix.
    `gator init` must remain fast and non-fatal. Source-repo exemption is
    handled inside `check_constitution_drift()` (returns "source-repo-exempt",
    which we render as no suffix).
    """
    try:
        state_mod = import_sibling("gator-state")
        if not state_mod:
            return ""
        result = state_mod.check_constitution_drift(repo_root)
        if result.get("status") == "modified":
            return " · modified from baseline"
    except Exception:
        pass
    return ""


def format_check(label, value, width=16):
    """Format a single status line."""
    return f"  \u2713 {label:<{width}}{value}"


def print_boot_sequence(repo_root, paths, hook_status, registry_status):
    """Print the branded boot sequence.

    @reads: all detection functions above
    @writes: stdout
    """
    repo_name = repo_root.name

    # Header
    print()
    for line in GATOR_MARK_LINES:
        print(f"  {line}")
    print()
    print(f"  {VERSION}  ·  navigation coding, governed")
    print()
    print(f"  $ gator init")
    print()

    # Detection
    print(f"    found .gator/")
    print()

    # Constitution
    rule_count = count_constitution_rules(paths)
    drift_suffix = _constitution_drift_suffix(repo_root)
    print(format_check("constitution", f"{rule_count} rules in force{drift_suffix}"))

    # Charters
    charter_count, func_count, coverage = count_charters(paths)
    if charter_count > 0:
        detail = f"{charter_count} modules \u00b7 {func_count} functions documented"
        print(format_check("charters", detail))
    else:
        print(format_check("charters", "empty \u00b7 ready for bootstrap"))

    # Working set
    thread_count, line_count = count_working_set(paths)
    if thread_count > 0:
        print(format_check("working set", f"{thread_count} threads \u00b7 {line_count:,} lines"))
    else:
        print(format_check("working set", "empty \u00b7 threads emerge from work"))

    # Field guides (only show when present)
    guide_count, guide_langs = count_field_guides(paths)
    if guide_count > 0:
        lang_list = ", ".join(guide_langs)
        print(format_check("field guides", f"{guide_count} languages ({lang_list})"))

    # Enforcer
    enforcer_status = detect_enforcer(paths)
    print(format_check("enforcer", enforcer_status))

    # Git hooks
    print(format_check("hooks", hook_status["detail"]))

    # Dashboard registry
    reg_label = registry_status.get("detail", registry_status.get("status", ""))
    print(format_check("dashboard", reg_label))

    # Org-policy staleness nudge (runtime-split D6 decision (c),
    # 2026-08-22): purely local mtime check, Enterprise-active repos
    # only. The agent reading this banner at session opening runs the
    # pull — session-speed freshness with a visible audit trail, no
    # network in the boot path.
    try:
        from gator_core import policy_staleness_nudge
        # paths.gator_root, NOT a bare `gator_dir` — whiteboard 2026-08-22
        # r3: the original wiring referenced an undefined name and the
        # blanket except swallowed the NameError, making this surface
        # dead code (the exact silent failure D6 exists to prevent).
        # Wiring pinned by test_banner_shows_policy_nudge.
        _nudge = policy_staleness_nudge(paths.gator_root)
        if _nudge:
            print(f"  ! policy          {_nudge}")
    except Exception:
        pass

    # Tagline + session-opening directive (inbox 2026-08-23): the banner
    # used to END on the tagline, which reads as "session opening done" --
    # models (observed: Opus 4.7) took the constitution existence-check
    # tick as "constitution loaded" and skipped the read chain entirely.
    # The tail makes the next action explicit with a blunt resolved path,
    # no conditional two-path lookup for the model to skip. Machine-side
    # surface: this fix reaches the whole fleet in one CLI release.
    print()
    print(f"  {TAGLINE}")
    for line in session_opening_directive(repo_root, paths):
        print(line)
    print(f"  \u25b8")
    print()


def session_opening_directive(repo_root, paths):
    """Return the banner's next-action lines (session-opening reads).

    The check ticks above only verify files EXIST -- they do not mean
    the agent has read them. These lines convert the banner from a
    completion signal into a handoff: name the constitution by its one
    resolved path, then the three context reads the constitution's
    Session Opening block would otherwise have to relay.
    """
    try:
        const_rel = paths.constitution.relative_to(repo_root).as_posix()
    except Exception:
        const_rel = ".gator/.includes/constitution.md"
    try:
        root_rel = paths.gator_root.relative_to(repo_root).as_posix()
    except Exception:
        root_rel = ".gator"
    return [
        "",
        "  session opening is not finished. Read, in order:",
        f"    1. {const_rel}  \u2014 the rules; read before your first response",
        f"    2. {root_rel}/mission.md \u00b7 roadmap.md \u00b7 inbox.md  \u2014 what \u00b7 where \u00b7 open work",
    ]


def print_json(repo_root, paths, hook_status, registry_status):
    """Print status as JSON for programmatic consumption."""
    rule_count = count_constitution_rules(paths)
    charter_count, func_count, coverage = count_charters(paths)
    thread_count, line_count = count_working_set(paths)
    guide_count, guide_langs = count_field_guides(paths)
    enforcer_status = detect_enforcer(paths)
    version_info = read_version(paths)

    data = {
        "version": VERSION,
        "repo": repo_root.name,
        "repo_path": str(repo_root),
        "constitution_rules": rule_count,
        "charters": {
            "modules": charter_count,
            "functions_mapped": func_count,
            "coverage_pct": round(coverage, 1),
        },
        "working_set": {
            "threads": thread_count,
            "lines": line_count,
        },
        "field_guides": {
            "count": guide_count,
            "languages": guide_langs,
        },
        "enforcer": enforcer_status,
        "hooks": hook_status,
        "dashboard_registry": registry_status,
        "gator_version": version_info,
    }

    print(json.dumps(data, indent=2))


def print_not_found():
    """Print message when .gator/ is not found."""
    print()
    for line in GATOR_MARK_LINES:
        print(f"  {line}")
    print()
    print(f"  {VERSION}  ·  navigation coding, governed")
    print()
    print("  no .gator/ found.")
    print()
    print("  to gatorize this repo:")
    print("    gator gatorize .")
    print()


# --- Entry point ---

def main():
    ensure_utf8_stdout()

    parser = argparse.ArgumentParser(
        description="Gator init — branded boot sequence for governed repos."
    )
    parser.add_argument(
        "--path", "-p",
        help="Path to search for .gator/ (default: current directory)",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON instead of formatted display",
    )
    args = parser.parse_args()

    repo_root = find_gator_root(args.path)

    if not repo_root:
        print_not_found()
        sys.exit(1)

    paths = get_gator_paths(repo_root)
    hook_status = ensure_git_hooks(repo_root, paths)
    registry_status = ensure_dashboard_registry_entry(repo_root, source="gator-init")

    if args.json:
        print_json(repo_root, paths, hook_status, registry_status)
    else:
        print_boot_sequence(repo_root, paths, hook_status, registry_status)


if __name__ == "__main__":
    main()
