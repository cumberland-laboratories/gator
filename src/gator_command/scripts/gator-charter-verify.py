#!/usr/bin/env python3
"""
gator charter-verify — Structural charter quality checker.

Compares existing charters against actual code structure and emits
findings. Machine checks plausibility; enforcer judges materiality.

Finding classes:
  coverage-gap       — tracked source file not covered by any charter
  function-gap       — public function not represented in any charter
  complexity-mismatch — complex file with unusually thin charter
  stale-structure    — charter references functions that no longer exist
  cross-cutting-suspect — high import fan-out without cross-cutting treatment

Usage:
    python gator-command/scripts/gator-charter-verify.py --path <repo>
    python gator-command/scripts/gator-charter-verify.py --path <repo> --json
    python gator-command/scripts/gator-charter-verify.py --path <repo> --changed-only

@reads: charter files, source files (via ast), .gator/.charterignore, git
@writes: stdout (text or json)
"""

import argparse
import json
import re
import sys
from pathlib import Path

from gator_core import (
    get_version, find_gator_root, ensure_utf8_stdout, git, import_sibling,
)

VERSION = get_version()

# Import shared analysis functions from charter-draft
_draft = import_sibling("gator-charter-draft")
if not _draft:
    print("  Error: gator-charter-draft.py not found.", file=sys.stderr)
    sys.exit(1)

discover_files = _draft.discover_files
analyze_python = _draft.analyze_python
load_charterignore = _draft.load_charterignore
SUPPORTED_EXTENSIONS = _draft.SUPPORTED_EXTENSIONS


# ---------------------------------------------------------------------------
# Charter parsing
# ---------------------------------------------------------------------------

def find_charter_dirs(repo_root):
    """Find charter directories in the repo.

    Returns a list of (dir_path, label) tuples. Checks both:
    - .gator/charters/ (per-repo governance)
    - gator-command/charters/ (command-post source charters)

    @reads: repo directory structure
    """
    from gator_layout import get_gator_paths

    dirs = []
    if (repo_root / ".gator").is_dir():
        paths = get_gator_paths(repo_root)
        if paths.charters_dir.is_dir():
            dirs.append((paths.charters_dir, ".gator/charters"))

    gc_charters = repo_root / "gator-command" / "charters"
    if gc_charters.is_dir():
        dirs.append((gc_charters, "gator-command/charters"))

    return dirs


def parse_charters(charter_dirs):
    """Parse all charter files and extract structural information.

    Returns a dict mapping source file paths (from Covers: lines) to
    charter info, and a list of all charter entries with their functions.

    @reads: charter .md files
    """
    # Maps: source_file_path -> list of charter names that cover it
    coverage_map = {}
    # Maps: charter_name -> set of documented function names
    charter_functions = {}
    # Maps: charter_name -> dict of function_name -> file_path
    charter_function_files = {}
    # All charter entries
    charters = []

    skip_files = {"_template.md", "README.md", "INDEX.md"}

    for charter_dir, label in charter_dirs:
        for md_file in sorted(charter_dir.glob("*.md")):
            if md_file.name in skip_files:
                continue

            try:
                text = md_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            charter_name = md_file.stem
            covers = _parse_covers(text)
            functions, function_files = _parse_function_entries(text)

            charter_functions[charter_name] = functions
            charter_function_files[charter_name] = function_files

            for src_path in covers:
                if src_path not in coverage_map:
                    coverage_map[src_path] = []
                coverage_map[src_path].append(charter_name)

            charters.append({
                "name": charter_name,
                "file": str(md_file),
                "label": label,
                "covers": covers,
                "functions": functions,
                "line_count": len(text.splitlines()),
            })

    return coverage_map, charter_functions, charter_function_files, charters


def _parse_covers(text):
    """Extract file paths from the **Covers**: line."""
    paths = []
    for line in text.splitlines():
        if line.startswith("**Covers**:"):
            # Extract backtick-quoted paths
            paths.extend(re.findall(r'`([^`]+)`', line))
            break
    return paths


def _parse_function_entries(text):
    """Extract function names from ### entries in a charter.

    Recognizes patterns like:
    - ### function_name(args)
    - ### ClassName.method_name(args)
    - ### class ClassName

    Returns a set of function names (for coverage checks) and a dict
    mapping function names to their associated File: path (for stale checks).
    """
    functions = set()
    function_files = {}  # name -> file path from File: line
    last_file_ref = None  # Track File: context for #### method entries

    lines = text.splitlines()
    for i, line in enumerate(lines):
        # Match both ### and #### entries (methods use ####)
        m = re.match(r'^#{3,4}\s+(?:class\s+)?(\w[\w.]*?)(?:\(|$)', line)
        if m:
            name = m.group(1)
            # For ClassName.method, extract both class and method
            if "." in name:
                parts = name.split(".")
                functions.add(parts[-1])
                functions.add(name)
            else:
                functions.add(name)

            # Look for File: line in the next few lines
            found_file = False
            for j in range(i + 1, min(i + 4, len(lines))):
                fm = re.match(r'^File:\s*`([^`]+)`', lines[j])
                if fm:
                    file_ref = fm.group(1)
                    function_files[name] = file_ref
                    if "." in name:
                        function_files[name.split(".")[-1]] = file_ref
                    last_file_ref = file_ref
                    found_file = True
                    break

            # #### entries (methods) inherit the File: from their parent ### entry
            if not found_file and line.startswith("####") and last_file_ref:
                function_files[name] = last_file_ref
                if "." in name:
                    function_files[name.split(".")[-1]] = last_file_ref

        # Track File: lines for context inheritance
        elif line.startswith("File:"):
            fm = re.match(r'^File:\s*`([^`]+)`', line)
            if fm:
                last_file_ref = fm.group(1)

        # Reset context at section boundaries
        elif line.startswith("---") or line.startswith("## "):
            last_file_ref = None

    return functions, function_files


# ---------------------------------------------------------------------------
# Finding generation
# ---------------------------------------------------------------------------

def verify(repo_root, gator_dir, dirs=None, changed_only=False):
    """Run all verification checks. Returns a list of findings.

    @reads: charters, source files, git
    """
    findings = []

    # Discover charterable files
    from gator_layout import get_gator_paths
    paths = get_gator_paths(repo_root)
    all_files = discover_files(repo_root, paths, dirs)

    # If --changed-only, filter to files changed since last commit
    if changed_only:
        diff_output, ok = git("diff", "--name-only", "HEAD~1", "HEAD", cwd=repo_root)
        if ok and diff_output:
            changed = set(diff_output.splitlines())
            all_files = [f for f in all_files if f in changed]

    # Parse existing charters
    charter_dirs = find_charter_dirs(repo_root)
    coverage_map, charter_functions, charter_function_files, charters = parse_charters(charter_dirs)

    # Analyze source files (all supported languages)
    analyses = {}
    for rel_path in all_files:
        abs_path = repo_root / rel_path
        ext = Path(rel_path).suffix.lower()

        result = None
        if ext == ".py":
            result = analyze_python(abs_path, rel_path)
        elif ext in (".js", ".jsx", ".ts", ".tsx"):
            result = _draft.analyze_javascript(abs_path, rel_path)
        elif ext in (".sh", ".bash"):
            result = _draft.analyze_shell(abs_path, rel_path)
        else:
            result = _draft.analyze_minimal(abs_path, rel_path)

        if result:
            analyses[rel_path] = result

    # --- Check: coverage-gap ---
    findings.extend(_check_coverage_gaps(all_files, coverage_map))

    # --- Check: function-gap ---
    findings.extend(_check_function_gaps(analyses, coverage_map, charter_functions))

    # --- Check: complexity-mismatch ---
    findings.extend(_check_complexity_mismatch(analyses, coverage_map, charters))

    # --- Check: stale-structure ---
    findings.extend(_check_stale_structure(analyses, coverage_map, charter_functions, charter_function_files))

    # --- Check: cross-cutting-suspect ---
    findings.extend(_check_cross_cutting(analyses, coverage_map))

    return findings


def _check_coverage_gaps(all_files, coverage_map):
    """Find tracked source files not covered by any charter."""
    findings = []
    for rel_path in all_files:
        if rel_path not in coverage_map:
            findings.append({
                "class": "coverage-gap",
                "severity": "warn",
                "file": rel_path,
                "message": f"Not covered by any charter",
            })
    return findings


# Functions that are conventionally not charter-worthy
_SKIP_FUNCTION_NAMES = {
    "main", "setup", "teardown",
    # Common output helpers — rarely need charter entries
    "print_report", "print_json", "print_json_report", "print_result",
    "print_plan", "print_json_plan", "print_findings", "print_json_findings",
    "print_scaffolds", "print_index_suggestions",
    # Common rendering helpers
    "escHtml", "fmtTs", "fmtDate",
}


def _is_charter_worthy(fn, analysis):
    """Heuristic: is this function significant enough to warrant a charter entry?

    Filters out conventional helpers and small utility functions to reduce noise.
    Only flags functions that look like public API, complex logic, or entrypoints.
    """
    name = fn["name"]

    # Skip conventional names
    if name in _SKIP_FUNCTION_NAMES:
        return False

    # Skip private functions
    if fn["is_private"]:
        return False

    # Skip very short names (likely helpers: e.g., "go", "run", "ok")
    if len(name) <= 2:
        return False

    # Always flag if the function has a docstring (author intended it to be public API)
    if fn.get("docstring_summary"):
        return True

    # Flag functions with many arguments (likely significant interface)
    if len(fn.get("args", [])) >= 4:
        return True

    # In files with few functions, each one is more likely significant
    total_public = sum(1 for f in analysis["functions"] if not f["is_private"])
    if total_public <= 3:
        return True

    # Flag functions whose name suggests significance (verbs that imply action)
    significant_prefixes = (
        "scan_", "collect_", "build_", "generate_", "execute_",
        "install_", "deploy_", "validate_", "verify_", "resolve_",
        "discover_", "analyze_", "parse_", "load_", "save_",
        "check_", "create_", "update_", "delete_", "run_",
        "render_", "handle_", "process_", "fetch_", "pull_",
    )
    if any(name.startswith(p) for p in significant_prefixes):
        return True

    return False


def _check_function_gaps(analyses, coverage_map, charter_functions):
    """Find significant public functions not documented in their covering charter.

    Uses heuristics to filter out conventional helpers and small utility
    functions. Only flags functions that look charter-worthy.
    """
    findings = []
    for rel_path, analysis in analyses.items():
        # Only check files that have a charter
        if rel_path not in coverage_map:
            continue

        charter_names = coverage_map[rel_path]
        # Collect all documented functions across covering charters
        all_documented = set()
        for cn in charter_names:
            all_documented.update(charter_functions.get(cn, set()))

        # Check charter-worthy functions only
        for fn in analysis["functions"]:
            if fn["name"] in all_documented:
                continue
            if not _is_charter_worthy(fn, analysis):
                continue
            findings.append({
                "class": "function-gap",
                "severity": "info",
                "file": rel_path,
                "function": fn["name"],
                "message": f"Public function `{fn['name']}()` not documented in charter",
                "charter": charter_names[0],
            })
    return findings


def _check_complexity_mismatch(analyses, coverage_map, charters):
    """Find complex files with unusually thin charters."""
    findings = []

    # Build charter line count map
    charter_lines = {}
    for c in charters:
        for src_path in c["covers"]:
            # Use the charter with the most lines if multiple cover this file
            if src_path not in charter_lines or c["line_count"] > charter_lines[src_path]:
                charter_lines[src_path] = c["line_count"]

    for rel_path, analysis in analyses.items():
        if rel_path not in coverage_map:
            continue

        c = analysis["complexity"]
        # Heuristic: file has significant complexity
        is_complex = (c["functions"] >= 8 or c["classes"] >= 2 or c["lines"] >= 300)
        # Charter is thin (less than 30 lines suggests minimal documentation)
        charter_lc = charter_lines.get(rel_path, 0)
        is_thin = charter_lc < 30

        if is_complex and is_thin:
            findings.append({
                "class": "complexity-mismatch",
                "severity": "warn",
                "file": rel_path,
                "message": (
                    f"Complex file ({c['functions']}f/{c['classes']}c/{c['lines']}L) "
                    f"but charter is only {charter_lc} lines"
                ),
            })
    return findings


def _check_stale_structure(analyses, coverage_map, charter_functions, charter_function_files):
    """Find charter function entries that no longer exist in code.

    Only flags functions whose File: line in the charter matches the
    specific source file being checked. This avoids false positives when
    a charter covers multiple files.
    """
    findings = []

    for rel_path, analysis in analyses.items():
        if rel_path not in coverage_map:
            continue

        charter_names = coverage_map[rel_path]
        # Get all actual function/class names in the file
        actual_names = set()
        for fn in analysis["functions"]:
            actual_names.add(fn["name"])
        for cls in analysis["classes"]:
            actual_names.add(cls["name"])
            for m in cls["methods"]:
                actual_names.add(m["name"])
                actual_names.add(f"{cls['name']}.{m['name']}")

        for cn in charter_names:
            documented = charter_functions.get(cn, set())
            fn_files = charter_function_files.get(cn, {})

            for doc_fn in documented:
                # Skip generic section headers
                if doc_fn in ("Internal_helpers", "Internal"):
                    continue

                # Only check if the File: line points to this specific file
                declared_file = fn_files.get(doc_fn, "")
                if declared_file and declared_file != rel_path:
                    continue  # This function belongs to a different file in the same charter

                # If no File: line, skip — can't determine which file it belongs to
                if not declared_file:
                    continue

                base_name = doc_fn.split(".")[-1] if "." in doc_fn else doc_fn
                if base_name not in actual_names and doc_fn not in actual_names:
                    findings.append({
                        "class": "stale-structure",
                        "severity": "info",
                        "file": rel_path,
                        "function": doc_fn,
                        "message": f"Charter `{cn}` documents `{doc_fn}()` but it was not found in `{rel_path}`",
                        "charter": cn,
                    })
    return findings


def _check_cross_cutting(analyses, coverage_map):
    """Find modules with high import fan-out that may need cross-cutting treatment."""
    findings = []

    for rel_path, analysis in analyses.items():
        imports = analysis["imports"]
        # Heuristic: importing from many sibling modules suggests orchestration
        sibling_imports = [i for i in imports if not i.startswith(("os", "sys", "json",
            "re", "pathlib", "datetime", "argparse", "subprocess", "shutil",
            "io", "ast", "fnmatch", "collections", "typing", "dataclasses",
            "threading", "socket", "http", "importlib", "filecmp", "webbrowser"))]

        if len(sibling_imports) >= 5:
            findings.append({
                "class": "cross-cutting-suspect",
                "severity": "info",
                "file": rel_path,
                "message": (
                    f"High sibling-import fan-out ({len(sibling_imports)} non-stdlib imports: "
                    f"{', '.join(sibling_imports[:5])}{'...' if len(sibling_imports) > 5 else ''})"
                ),
            })
    return findings


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_findings(findings):
    """Print findings to terminal."""
    if not findings:
        print()
        print("  gator charter-verify")
        print()
        print("  No findings. Charters look structurally sound.")
        print()
        return

    # Group by severity
    by_severity = {"warn": [], "info": []}
    for f in findings:
        by_severity.setdefault(f["severity"], []).append(f)

    # Group by class
    by_class = {}
    for f in findings:
        by_class.setdefault(f["class"], []).append(f)

    print()
    print(f"  gator charter-verify  ({len(findings)} findings)")
    print()

    # Summary counts
    for cls, items in sorted(by_class.items()):
        severity_counts = {}
        for item in items:
            severity_counts[item["severity"]] = severity_counts.get(item["severity"], 0) + 1
        counts = ", ".join(f"{v} {k}" for k, v in sorted(severity_counts.items()))
        print(f"  {cls}: {len(items)} ({counts})")
    print()

    # Warnings first
    warns = by_severity.get("warn", [])
    if warns:
        print("  ── Warnings ──")
        print()
        for f in warns:
            print(f"  [{f['class']}] {f['file']}")
            print(f"    {f['message']}")
            print()

    # Info
    infos = by_severity.get("info", [])
    if infos:
        print("  ── Info ──")
        print()
        for f in infos:
            print(f"  [{f['class']}] {f['file']}")
            print(f"    {f['message']}")
            print()


def print_json_findings(findings):
    """Output findings as JSON."""
    output = {
        "version": VERSION,
        "finding_count": len(findings),
        "summary": {},
        "findings": findings,
    }
    # Summary by class
    for f in findings:
        cls = f["class"]
        output["summary"][cls] = output["summary"].get(cls, 0) + 1

    print(json.dumps(output, indent=2))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ensure_utf8_stdout()

    parser = argparse.ArgumentParser(
        description="Gator charter-verify — structural charter quality checker.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--path", "-p",
        help="Path to repo (default: current directory, walks up to find .gator/)",
    )
    parser.add_argument(
        "--dirs", "-d", nargs="+",
        help="Directories to scope to (relative to repo root)",
    )
    parser.add_argument(
        "--json", "-j", action="store_true",
        help="Output findings as JSON",
    )
    parser.add_argument(
        "--changed-only", "-c", action="store_true",
        help="Only check files changed in the last commit",
    )
    args = parser.parse_args()

    # Find repo root
    repo_root = find_gator_root(args.path)
    if not repo_root:
        print("  Error: no .gator/ found. Run from a gatorized repo.", file=sys.stderr)
        sys.exit(1)

    gator_dir = repo_root / ".gator"

    # Run verification
    findings = verify(repo_root, gator_dir, args.dirs, args.changed_only)

    # Output
    if args.json:
        print_json_findings(findings)
    else:
        print_findings(findings)


if __name__ == "__main__":
    main()
