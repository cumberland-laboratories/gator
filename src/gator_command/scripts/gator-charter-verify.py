#!/usr/bin/env python3
"""
gator charter-verify — Structural charter quality checker.

Compares existing charters against actual code structure and emits
findings. Machine checks plausibility; enforcer judges materiality.

Finding classes:
  coverage-gap       — tracked source file not covered by any charter
  function-gap       — public seam (entry point or cross-charter import) not
                       represented in its charter; `reason` says which
  function-candidate — strict mode only (--functions strict): a public function
                       the broad name/docstring heuristic flags but the
                       default policy (charter_significance) does not
  complexity-mismatch — complex file with unusually thin charter
  stale-structure    — charter references functions that no longer exist
  stale-exclusion    — a name on a charter's **Internal**: line is defined in
                       none of the files that charter covers
  cross-cutting-suspect — high import fan-out without cross-cutting treatment

Usage:
    python gator-command/scripts/gator-charter-verify.py --path <repo>
    python gator-command/scripts/gator-charter-verify.py --path <repo> --json
    python gator-command/scripts/gator-charter-verify.py --path <repo> --changed-only
    python gator-command/scripts/gator-charter-verify.py --path <repo> --functions strict

@reads: charter files, source files (via ast), .gator/.charterignore, git
@writes: stdout (text or json; JSON adds `charters: [{name, path, covers}]`
         and `function_policy: "default" | "strict"`)
"""

import argparse
import json
import re
import sys
from pathlib import Path

from gator_core import (
    get_version, find_gator_root, ensure_utf8_stdout, git, import_sibling,
)
from charter_covers import coverage_index
import charter_significance as significance

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
                # **Internal**: names (#105); shape problems are lint findings.
                "internal": significance.parse_internal(text)[0],
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

    Recognizes patterns like (see `charter_significance.heading_names()`):
    - ### function_name(args)
    - ### first(args) / second() / ClassName.method_name(args)
    - ### class ClassName

    `File:` lines are read with or without backticks.

    Returns a set of function names (for coverage checks) and a dict
    mapping function names to their associated File: path (for stale checks).
    """
    functions = set()
    function_files = {}  # name -> file path from File: line
    last_file_ref = None  # Track File: context for #### method entries

    def _record(name, file_ref):
        # For ClassName.method, record both the dotted name and the method
        for key in ([name, name.split(".")[-1]] if "." in name else [name]):
            functions.add(key)
            if file_ref:
                function_files[key] = file_ref

    lines = text.splitlines()
    for i, line in enumerate(lines):
        # ### and #### entries (methods use ####); a grouped heading
        # (`### a() / b()`) documents every name it lists.
        names = significance.heading_names(line)
        if names:
            # Look for File: line in the next few lines
            file_ref = None
            for j in range(i + 1, min(i + 4, len(lines))):
                file_ref = significance.parse_file_line(lines[j])
                if file_ref:
                    last_file_ref = file_ref
                    break

            # #### entries (methods) inherit the File: from their parent ### entry
            if not file_ref and line.startswith("####"):
                file_ref = last_file_ref

            for name in names:
                _record(name, file_ref)

        # Track File: lines for context inheritance
        elif line.startswith("File:"):
            file_ref = significance.parse_file_line(line)
            if file_ref:
                last_file_ref = file_ref

        # Reset context at section boundaries
        elif line.startswith("---") or line.startswith("## "):
            last_file_ref = None

    return functions, function_files


# ---------------------------------------------------------------------------
# Finding generation
# ---------------------------------------------------------------------------

def verify(repo_root, gator_dir, dirs=None, changed_only=False, function_policy="default"):
    """Run all verification checks. Returns a list of findings.

    `function_policy="strict"` adds `function-candidate` findings; every
    default finding is identical in both modes.

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
    _, charter_functions, charter_function_files, charters = parse_charters(charter_dirs)
    # Resolve Covers entries (exact, directory prefix, or glob) against the
    # discovered files through the shared grammar (#88): file -> charter names.
    coverage_map = coverage_index(all_files, charters)

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

    signals, importers = _collect_signals(repo_root, analyses)

    # --- Check: coverage-gap ---
    findings.extend(_check_coverage_gaps(all_files, coverage_map))

    # --- Check: function-gap ---
    charter_internal = {c["name"]: set(c["internal"]) for c in charters}
    findings.extend(_check_function_gaps(
        analyses, coverage_map, charter_functions, signals, importers, function_policy,
        charter_internal))

    # --- Check: stale-exclusion ---
    findings.extend(_check_stale_exclusions(repo_root, analyses, coverage_map, charters, signals))

    # --- Check: complexity-mismatch ---
    findings.extend(_check_complexity_mismatch(analyses, coverage_map, charters))

    # --- Check: stale-structure ---
    findings.extend(_check_stale_structure(
        analyses, coverage_map, charter_functions, charter_function_files, signals))

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


_PY_EXTENSIONS = (".py",)
_JS_EXTENSIONS = (".js", ".jsx", ".ts", ".tsx")


def _collect_signals(repo_root, analyses):
    """Per-file significance signals and the cross-module import map.

    Returns `(signals, importers)`: `signals[rel_path]` is the
    `charter_significance` signal dict; `importers[(stem, name)]` is the
    set of analyzed files that import `name` from a module named `stem`.
    Only analyzed (discovered) files count as importers.
    """
    signals = {}
    importers = {}
    for rel_path in analyses:
        ext = Path(rel_path).suffix.lower()
        if ext not in _PY_EXTENSIONS + _JS_EXTENSIONS:
            continue
        try:
            source = (repo_root / rel_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        sig = (significance.python_signals(source) if ext in _PY_EXTENSIONS
               else significance.javascript_signals(source))
        signals[rel_path] = sig
        for key in sig["imports"]:
            importers.setdefault(key, set()).add(rel_path)
    return signals, importers


def _is_charter_worthy(fn, analysis):
    """Broad heuristic, used only by strict mode (`function-candidate`).

    The default `function-gap` decision is `charter_significance.decide()`.
    This keeps the pre-#105 name/docstring/argument-count signal as an
    opt-in investigation tool.
    """
    name = fn["name"]

    # Skip conventional names
    if name in significance.CONVENTIONAL_NAMES:
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


def _check_function_gaps(analyses, coverage_map, charter_functions,
                         signals=None, importers=None, function_policy="default",
                         charter_internal=None):
    """Find public seams not documented in their covering charter.

    The default decision is `charter_significance.decide()`: entry points,
    and functions imported by a file that a different charter owns. Strict
    mode also reports `function-candidate` for undocumented functions that
    the broad `_is_charter_worthy()` heuristic flags but the policy calls
    internal. A name on the `**Internal**:` line of a charter that covers
    the file (`charter_internal`) is neither. `coverage_map` is the
    resolved `{file: [charter names]}` index, so a charter that does not
    cover the file can never suppress its gaps.
    """
    signals = signals or {}
    importers = importers or {}
    charter_internal = charter_internal or {}
    findings = []
    for rel_path, analysis in analyses.items():
        # Only check files that have a charter
        if rel_path not in coverage_map:
            continue

        charter_names = coverage_map[rel_path]
        # Collect all documented functions across covering charters
        all_documented = set()
        excluded = set()
        for cn in charter_names:
            all_documented.update(charter_functions.get(cn, set()))
            excluded.update(charter_internal.get(cn, set()))

        stem = Path(rel_path).stem
        entries = signals.get(rel_path, {}).get("entries", set())
        for fn in analysis["functions"]:
            name = fn["name"]
            if name in all_documented or name in excluded:
                continue
            importer_owners = [coverage_map.get(q, [])
                               for q in importers.get((stem, name), ()) if q != rel_path]
            decision, reason = significance.decide(
                name, fn["is_private"], entries, importer_owners, charter_names)
            if decision == "document":
                kind = "entry point" if reason == "entry" else "imported by another charter's code"
                findings.append({
                    "class": "function-gap",
                    "severity": "info",
                    "file": rel_path,
                    "function": name,
                    "reason": reason,
                    "message": f"Public seam `{name}()` ({kind}) not documented in charter",
                    "charter": charter_names[0],
                })
            elif (function_policy == "strict" and decision == "internal"
                    and _is_charter_worthy(fn, analysis)):
                findings.append({
                    "class": "function-candidate",
                    "severity": "info",
                    "file": rel_path,
                    "function": name,
                    "message": f"Public function `{name}()` may deserve a charter entry (strict heuristic)",
                    "charter": charter_names[0],
                })
    return findings


def _check_stale_exclusions(repo_root, analyses, coverage_map, charters, signals=None):
    """Find `**Internal**:` names defined in none of the charter's covered files.

    "Out of scope" and "stale" are one condition for a name list scoped to
    the files `coverage_index()` assigns the charter: a name that exists
    only in a file another charter covers is reported too.
    """
    signals = signals or {}
    root = Path(repo_root).resolve()
    findings = []
    for charter in charters:
        if not charter["internal"]:
            continue
        defined = set()
        for rel_path, names in coverage_map.items():
            if charter["name"] not in names or rel_path not in analyses:
                continue
            analysis = analyses[rel_path]
            defined.update(fn["name"] for fn in analysis["functions"])
            for cls in analysis["classes"]:
                defined.add(cls["name"])
                defined.update(m["name"] for m in cls["methods"])
            defined.update(signals.get(rel_path, {}).get("registered", ()))
        try:
            charter_path = Path(charter["file"]).resolve().relative_to(root).as_posix()
        except ValueError:
            charter_path = Path(charter["file"]).as_posix()
        for name in charter["internal"]:
            if name not in defined:
                findings.append({
                    "class": "stale-exclusion",
                    "severity": "info",
                    "file": charter_path,
                    "function": name,
                    "message": (f"Charter `{charter['name']}` lists `{name}` on **Internal**: "
                                "but it is not defined in any file this charter covers"),
                    "charter": charter["name"],
                })
    return findings


def _check_complexity_mismatch(analyses, coverage_map, charters):
    """Find complex files with unusually thin charters.

    `coverage_map` is the resolved `{file: [charter names]}` index.
    """
    findings = []

    line_counts = {c["name"]: c["line_count"] for c in charters}

    for rel_path, analysis in analyses.items():
        if rel_path not in coverage_map:
            continue

        c = analysis["complexity"]
        # Heuristic: file has significant complexity
        is_complex = (c["functions"] >= 8 or c["classes"] >= 2 or c["lines"] >= 300)
        # Charter is thin (less than 30 lines suggests minimal documentation).
        # Use the longest of the charters that cover this file.
        charter_lc = max(line_counts.get(n, 0) for n in coverage_map[rel_path])
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


def _check_stale_structure(analyses, coverage_map, charter_functions, charter_function_files,
                           signals=None):
    """Find charter function entries that no longer exist in code.

    Only flags functions whose File: line in the charter matches the
    specific source file being checked. This avoids false positives when
    a charter covers multiple files. JavaScript `window.<path>`
    registrations (`signals[...]["registered"]`) count as existing code.
    """
    signals = signals or {}
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
        actual_names.update(signals.get(rel_path, {}).get("registered", ()))

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


def charter_summaries(repo_root):
    """Return `[{name, path, covers}]` for every parsed charter.

    `path` is repo-relative POSIX when the charter lives under the repo.
    Additive JSON for consumers that attribute findings to charters or
    evaluate `Covers` themselves (the Dashboard charter sync check).

    @reads: charter .md files
    """
    _, _, _, charters = parse_charters(find_charter_dirs(repo_root))
    root = Path(repo_root).resolve()
    out = []
    for c in charters:
        path = Path(c["file"])
        try:
            rel = path.resolve().relative_to(root).as_posix()
        except ValueError:
            rel = path.as_posix()
        out.append({"name": c["name"], "path": rel, "covers": list(c["covers"])})
    return out


def print_json_findings(findings, charters=None, function_policy=None):
    """Output findings as JSON. `charters` and `function_policy` (additive)
    are included when given."""
    output = {
        "version": VERSION,
        "finding_count": len(findings),
        "summary": {},
        "findings": findings,
    }
    if charters is not None:
        output["charters"] = charters
    if function_policy is not None:
        output["function_policy"] = function_policy
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
    parser.add_argument(
        "--functions", choices=("default", "strict"), default="default",
        help="Function-gap policy: default (public seams only) or strict "
             "(also report broad-heuristic candidates as function-candidate)",
    )
    args = parser.parse_args()

    # Find repo root
    repo_root = find_gator_root(args.path)
    if not repo_root:
        print("  Error: no .gator/ found. Run from a gatorized repo.", file=sys.stderr)
        sys.exit(1)

    gator_dir = repo_root / ".gator"

    # Run verification
    findings = verify(repo_root, gator_dir, args.dirs, args.changed_only, args.functions)

    # Output
    if args.json:
        print_json_findings(findings, charter_summaries(repo_root), args.functions)
    else:
        print_findings(findings)


if __name__ == "__main__":
    main()
