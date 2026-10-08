#!/usr/bin/env python3
"""
gator state — report the state of a governed repo.

Reports constitution drift (fleet repos only), a host/repo version
diagnostic, and an informational view of native agent files
(CLAUDE.md / AGENTS.md / GEMINI.md). Since the gator-native entry point
(2026-10-08) Gator does not manage those files: they are repository-owned,
so status never calls them drifted, missing, or in need of repair, and
`repair` is a no-write compatibility stub.

Subcommands:
  gator state status    Report state (text or JSON)
  gator state repair    Compatibility stub: explains the change, writes nothing
"""

import argparse
import json
import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from gator_core import (
    get_version, find_gator_root, ensure_utf8_stdout,
    resolve_template_source,
)
from gator_layout import get_gator_paths
from gatorize.managed_block import (
    GATOR_BEGIN, GATOR_END,
    detect_legacy_gator_content,
)


# v2 (2026-10-08): `entry_points` / `entry_point_baseline_kind` were removed
# and `native_files` added — a meaning change, hence the bump.
SCHEMA = "gator-state-v2"

# Native agent files reported for information only. Gator never writes them.
NATIVE_FILES = ("CLAUDE.md", "AGENTS.md", "GEMINI.md")


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


def describe_native_file(repo_root, filename):
    """Informational record for one native agent file. Read-only.

    `historical_gator_block` is True when the file still carries content an
    older Gator wrote: sentinel bytes (well-formed or not) or a legacy
    fingerprint. It is history, not drift; nothing here proposes a change.
    """
    filepath = repo_root / filename
    present = filepath.is_file()
    historical = False
    if present:
        try:
            text = filepath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            text = ""
        historical = (
            GATOR_BEGIN in text or GATOR_END in text
            or detect_legacy_gator_content(text)
        )
    return {
        "filename": filename,
        "present": present,
        "managed": False,
        "historical_gator_block": historical,
        "local_companion": "present" if local_companion_present(repo_root, filename) else "absent",
    }


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

    The only baseline is the constitution, resolved through
    `resolve_template_source()`. Native agent files have no baseline: they
    are repository-owned and reported for information only.
    """
    gator_dir = repo_root / ".gator"
    templates_dir, _gator_root = resolve_template_source(gator_dir)

    return {
        "schema": SCHEMA,
        "repo_root": str(repo_root),
        "host_cli_version": get_version(),
        "repo_gator_version": read_repo_gator_version(repo_root),
        "constitution_baseline_source": str(templates_dir) if templates_dir else None,
        "native_files": [describe_native_file(repo_root, name) for name in NATIVE_FILES],
        "constitution": check_constitution(repo_root, templates_dir),
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


def _native_file_label(record):
    if not record["present"]:
        return "absent"
    if record["historical_gator_block"]:
        return "present · historical Gator block (not refreshed)"
    return "present"


def render_status_text(report):
    """Render the status report as concise text output."""
    lines = []
    diag = _format_version_diagnostic(report["host_cli_version"], report["repo_gator_version"])
    if diag:
        lines.append(diag)
    lines.append("")
    lines.append("  native agent files (not managed by Gator):")
    for rec in report["native_files"]:
        lines.append(f"    {rec['filename']:<12} {_native_file_label(rec)}")
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
# Repair (compatibility stub)
# ---------------------------------------------------------------------------

REPAIR_NOTICE = (
    "  Nothing to repair: Gator no longer manages CLAUDE.md / AGENTS.md / GEMINI.md.\n"
    "  Historical Gator blocks are left as-is; edit or remove them yourself.\n"
)


def render_repair_text(dry_run):
    lines = [REPAIR_NOTICE.rstrip("\n")]
    if dry_run:
        lines.append("  (dry run: nothing would change either way)")
    lines.append("")
    lines.append("  constitution: repair deferred (v1 detection-only — copy manually if needed)")
    lines.append("  local companions: preserved (never touched by gator state)")
    return "\n".join(lines) + "\n"


def render_repair_json(dry_run):
    return json.dumps({
        "schema": SCHEMA,
        "dry_run": dry_run,
        "actions": [],
        "native_files": "not-managed",
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
    """No-write compatibility stub. Accepts the old arguments; never touches files."""
    repo_root = find_gator_root(args.path)
    if not repo_root:
        print("  Error: no .gator/ found. Run from a gatorized repo.", file=sys.stderr)
        return 1
    if args.json:
        sys.stdout.write(render_repair_json(args.dry_run))
    else:
        sys.stdout.write(render_repair_text(args.dry_run))
    return 0


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def _build_parser():
    parser = argparse.ArgumentParser(
        prog="gator state",
        description="Report the state of a governed repo.",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_status = sub.add_parser("status", help="Report state (text or JSON)")
    p_status.add_argument("--path", default=None, help="Repo root (default: cwd)")
    p_status.add_argument("--json", action="store_true", help="Emit JSON output")

    p_repair = sub.add_parser(
        "repair",
        help="Compatibility stub: Gator no longer manages native agent files; writes nothing",
    )
    p_repair.add_argument("filename", nargs="?", default=None,
                          help="Accepted for compatibility; ignored")
    p_repair.add_argument("--path", default=None, help="Repo root (default: cwd)")
    p_repair.add_argument("--dry-run", action="store_true", help="Accepted for compatibility; nothing is written either way")
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
