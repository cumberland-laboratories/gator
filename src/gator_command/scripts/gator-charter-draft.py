#!/usr/bin/env python3
"""
gator charter-draft — Mechanical charter scaffold generator.

Uses Python's ast module to extract code structure and generate charter
drafts. Machine extracts structure; agent writes meaning; enforcer checks both.

Usage:
    python gator-command/scripts/gator-charter-draft.py --path <repo>
    python gator-command/scripts/gator-charter-draft.py --path <repo> --dirs src lib
    python gator-command/scripts/gator-charter-draft.py --path <repo> --write
    python gator-command/scripts/gator-charter-draft.py --path <repo> --write --output-dir gator-command/charters
    python gator-command/scripts/gator-charter-draft.py --path <repo> --json

@reads: source files (via ast), .gator/.charterignore, git ls-files
@writes: charter directory (--write mode only, never overwrites existing).
         Default: .gator/charters/. Override with --output-dir for repos
         where the authoritative charter surface is elsewhere (e.g.
         gator-command/charters/ in the command post repo).
"""

import argparse
import ast
import fnmatch
import json
import re
import sys
from datetime import date
from pathlib import Path

from gator_core import get_version, find_gator_root, ensure_utf8_stdout, git

VERSION = get_version()

# All source file extensions eligible for charter coverage.
# Files with these extensions are discovered and included in coverage checks.
SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".sh", ".bash",
    ".go", ".rs",
    ".rb", ".java", ".cs", ".cpp", ".c", ".h",
}

# Extensions with structural analyzers (ast/regex extraction).
# Files not in this set still appear in coverage-gap checks but
# get a minimal scaffold without function/class inventory.
ANALYZABLE_EXTENSIONS = {".py", ".js", ".sh"}

# Built-in exclusions applied when no .charterignore exists
FALLBACK_EXCLUSIONS = [
    "tests/", "test/", "__tests__/", "__pycache__/",
    "node_modules/", "vendor/", "dist/", "build/",
    ".gator/", ".git/", ".venv/", "venv/",
]


# ---------------------------------------------------------------------------
# .charterignore
# ---------------------------------------------------------------------------

def load_charterignore(paths):
    """Load .charterignore patterns from the resolved charterignore path.

    Returns a list of gitignore-style patterns. Falls back to
    FALLBACK_EXCLUSIONS if the file doesn't exist.

    @reads: .charterignore (resolved by layout)
    """
    ignore_file = paths.charterignore
    if not ignore_file.exists():
        return FALLBACK_EXCLUSIONS

    patterns = []
    try:
        text = ignore_file.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                patterns.append(stripped)
    except OSError:
        return FALLBACK_EXCLUSIONS

    return patterns


def is_ignored(rel_path, patterns):
    """Check if a relative file path matches any charterignore pattern.

    Supports:
    - directory patterns ending in / (match any path component)
    - glob patterns with * and **
    - basename patterns (no / in pattern matches against filename)
    """
    parts = Path(rel_path).parts
    name = Path(rel_path).name

    for pattern in patterns:
        # Directory pattern: tests/ matches any path containing that dir
        if pattern.endswith("/"):
            dir_name = pattern.rstrip("/")
            # Multi-component: match as path prefix (e.g. gator-command/templates/)
            if "/" in dir_name:
                if rel_path.startswith(dir_name + "/") or rel_path == dir_name:
                    return True
            else:
                # Single component: match any path part
                if dir_name in parts:
                    return True
            continue

        # Pattern with path separator: match against full path
        if "/" in pattern:
            if fnmatch.fnmatch(rel_path, pattern):
                return True
            # Also try without leading **/ for convenience
            if pattern.startswith("**/"):
                if fnmatch.fnmatch(rel_path, pattern[3:]):
                    return True
                # Match against each suffix of the path
                for i in range(len(parts)):
                    suffix = "/".join(parts[i:])
                    if fnmatch.fnmatch(suffix, pattern[3:]):
                        return True
            continue

        # Basename pattern: match against filename only
        if fnmatch.fnmatch(name, pattern):
            return True

    return False


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def discover_files(repo_root, paths, dirs=None):
    """Discover charterable source files.

    Uses git ls-files for tracked files, then filters by:
    1. --dirs scope (if given)
    2. .charterignore patterns
    3. Supported file extensions

    @reads: git index, .charterignore (resolved by layout)
    """
    # Get tracked files
    ls_output, ok = git("ls-files", cwd=repo_root)
    if not ok or not ls_output:
        return []

    all_files = ls_output.splitlines()
    patterns = load_charterignore(paths)

    result = []
    for rel_path in all_files:
        # Scope to --dirs if specified
        if dirs:
            if not any(rel_path.startswith(d.rstrip("/") + "/") or rel_path == d for d in dirs):
                continue

        # Apply charterignore
        if is_ignored(rel_path, patterns):
            continue

        # Filter to supported extensions
        ext = Path(rel_path).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue

        result.append(rel_path)

    return sorted(result)


# ---------------------------------------------------------------------------
# Python analyzer (ast-based)
# ---------------------------------------------------------------------------

def analyze_python(file_path, rel_path):
    """Extract structural information from a Python file using ast.

    Returns a dict with: functions, classes, imports, complexity signals,
    entrypoint detection. Returns None if the file cannot be parsed.

    @reads: single Python source file
    """
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    try:
        tree = ast.parse(source, filename=str(rel_path))
    except SyntaxError:
        return None

    line_count = len(source.splitlines())

    # Module-level docstring
    module_docstring = ast.get_docstring(tree) or ""
    module_summary = module_docstring.split("\n")[0].strip() if module_docstring else ""

    functions = []
    classes = []
    imports = []
    has_main_guard = False
    has_argparse = False

    for node in ast.iter_child_nodes(tree):
        # Top-level functions
        if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            functions.append(_extract_function(node))

        # Classes
        elif isinstance(node, ast.ClassDef):
            cls_info = _extract_class(node)
            classes.append(cls_info)

        # Imports
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)

        # if __name__ == "__main__" guard
        elif isinstance(node, ast.If):
            if _is_main_guard(node):
                has_main_guard = True

    # Check for argparse usage
    has_argparse = "argparse" in imports

    return {
        "rel_path": rel_path,
        "line_count": line_count,
        "docstring_summary": module_summary,
        "functions": functions,
        "classes": classes,
        "imports": sorted(set(imports)),
        "has_main_guard": has_main_guard,
        "has_argparse": has_argparse,
        "is_entrypoint": has_main_guard or has_argparse,
        "complexity": {
            "functions": len(functions),
            "classes": len(classes),
            "methods": sum(len(c["methods"]) for c in classes),
            "imports": len(set(imports)),
            "lines": line_count,
        },
    }


def _extract_function(node):
    """Extract function signature and metadata."""
    args = []
    for arg in node.args.args:
        args.append(arg.arg)
    if node.args.vararg:
        args.append(f"*{node.args.vararg.arg}")
    if node.args.kwonlyargs:
        for kw in node.args.kwonlyargs:
            args.append(kw.arg)
    if node.args.kwarg:
        args.append(f"**{node.args.kwarg.arg}")

    decorators = []
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name):
            decorators.append(dec.id)
        elif isinstance(dec, ast.Attribute):
            decorators.append(ast.dump(dec))

    # Extract docstring
    docstring = ast.get_docstring(node) or ""
    first_line = docstring.split("\n")[0].strip() if docstring else ""

    return {
        "name": node.name,
        "args": args,
        "signature": f"{node.name}({', '.join(args)})",
        "decorators": decorators,
        "line": node.lineno,
        "docstring_summary": first_line,
        "is_private": node.name.startswith("_"),
    }


def _extract_class(node):
    """Extract class structure."""
    methods = []
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods.append(_extract_function(item))

    bases = []
    for base in node.bases:
        if isinstance(base, ast.Name):
            bases.append(base.id)
        elif isinstance(base, ast.Attribute):
            bases.append(f"{ast.dump(base)}")

    docstring = ast.get_docstring(node) or ""
    first_line = docstring.split("\n")[0].strip() if docstring else ""

    return {
        "name": node.name,
        "bases": bases,
        "methods": methods,
        "line": node.lineno,
        "docstring_summary": first_line,
    }


def _is_main_guard(node):
    """Check if an If node is `if __name__ == '__main__':`."""
    test = node.test
    if isinstance(test, ast.Compare):
        if (isinstance(test.left, ast.Name) and test.left.id == "__name__"
                and len(test.comparators) == 1):
            comp = test.comparators[0]
            if isinstance(comp, ast.Constant) and comp.value == "__main__":
                return True
    return False


# ---------------------------------------------------------------------------
# JavaScript / TypeScript analyzer (regex-based)
# ---------------------------------------------------------------------------

# Patterns for JS/TS function extraction
_JS_FUNCTION = re.compile(
    r'^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)',
    re.MULTILINE,
)
_JS_ARROW_NAMED = re.compile(
    r'^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[\w]+)\s*=>',
    re.MULTILINE,
)
_JS_CLASS = re.compile(
    r'^(?:export\s+)?class\s+(\w+)',
    re.MULTILINE,
)
_JS_METHOD = re.compile(
    r'^\s+(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{',
    re.MULTILINE,
)
_JS_IMPORT = re.compile(
    r'(?:import\s+.*?from\s+["\']([^"\']+)["\']|require\s*\(\s*["\']([^"\']+)["\']\s*\))',
)


def analyze_javascript(file_path, rel_path):
    """Extract structural information from a JS/TS file using regex.

    Less precise than ast-based Python analysis, but captures the main
    structural elements: named functions, arrow functions, classes, imports.

    @reads: single JS/TS source file
    """
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    lines = source.splitlines()
    line_count = len(lines)

    # Extract first comment block as module summary
    module_summary = ""
    if lines and lines[0].strip().startswith("/**"):
        for line in lines[1:]:
            stripped = line.strip().lstrip("* ").rstrip()
            if stripped.startswith("*/"):
                break
            if stripped and not module_summary:
                module_summary = stripped
                break

    functions = []
    classes = []
    imports = []

    # Named functions
    for m in _JS_FUNCTION.finditer(source):
        name = m.group(1)
        args_str = m.group(2).strip()
        args = [a.strip().split(":")[0].strip() for a in args_str.split(",") if a.strip()] if args_str else []
        functions.append({
            "name": name,
            "args": args,
            "signature": f"{name}({', '.join(args)})",
            "decorators": [],
            "line": source[:m.start()].count("\n") + 1,
            "docstring_summary": "",
            "is_private": name.startswith("_"),
        })

    # Arrow functions assigned to const/let/var
    for m in _JS_ARROW_NAMED.finditer(source):
        name = m.group(1)
        functions.append({
            "name": name,
            "args": [],
            "signature": f"{name}()",
            "decorators": [],
            "line": source[:m.start()].count("\n") + 1,
            "docstring_summary": "",
            "is_private": name.startswith("_"),
        })

    # Classes
    for m in _JS_CLASS.finditer(source):
        name = m.group(1)
        classes.append({
            "name": name,
            "bases": [],
            "methods": [],
            "line": source[:m.start()].count("\n") + 1,
            "docstring_summary": "",
        })

    # Imports
    for m in _JS_IMPORT.finditer(source):
        imp = m.group(1) or m.group(2)
        if imp:
            imports.append(imp)

    return {
        "rel_path": rel_path,
        "line_count": line_count,
        "docstring_summary": module_summary,
        "functions": functions,
        "classes": classes,
        "imports": sorted(set(imports)),
        "has_main_guard": False,
        "has_argparse": False,
        "is_entrypoint": False,
        "complexity": {
            "functions": len(functions),
            "classes": len(classes),
            "methods": 0,
            "imports": len(set(imports)),
            "lines": line_count,
        },
    }


# ---------------------------------------------------------------------------
# Shell analyzer (regex-based)
# ---------------------------------------------------------------------------

_SH_FUNCTION = re.compile(
    r'^(?:function\s+)?(\w+)\s*\(\s*\)\s*\{',
    re.MULTILINE,
)
_SH_SOURCE = re.compile(
    r'^\s*(?:source|\.)(?:\s+)([^\s;#]+)',
    re.MULTILINE,
)


def analyze_shell(file_path, rel_path):
    """Extract structural information from a shell script using regex.

    Captures function definitions and source/. includes.

    @reads: single shell source file
    """
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    lines = source.splitlines()
    line_count = len(lines)

    # Extract first comment block as module summary
    module_summary = ""
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#!"):
            continue
        if stripped.startswith("#"):
            text = stripped.lstrip("# ").strip()
            if text and not module_summary:
                module_summary = text
                break
        elif stripped:
            break

    functions = []
    imports = []

    for m in _SH_FUNCTION.finditer(source):
        name = m.group(1)
        functions.append({
            "name": name,
            "args": [],
            "signature": f"{name}()",
            "decorators": [],
            "line": source[:m.start()].count("\n") + 1,
            "docstring_summary": "",
            "is_private": name.startswith("_"),
        })

    for m in _SH_SOURCE.finditer(source):
        imports.append(m.group(1))

    return {
        "rel_path": rel_path,
        "line_count": line_count,
        "docstring_summary": module_summary,
        "functions": functions,
        "classes": [],
        "imports": sorted(set(imports)),
        "has_main_guard": False,
        "has_argparse": False,
        "is_entrypoint": True,  # Shell scripts are typically entrypoints
        "complexity": {
            "functions": len(functions),
            "classes": 0,
            "methods": 0,
            "imports": len(set(imports)),
            "lines": line_count,
        },
    }


# ---------------------------------------------------------------------------
# Minimal analyzer (coverage tracking only)
# ---------------------------------------------------------------------------

def analyze_minimal(file_path, rel_path):
    """Minimal analysis for file types without a structural analyzer.

    Only counts lines — enough for coverage-gap detection and basic
    scaffolding. No function/class extraction.

    @reads: single source file
    """
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    line_count = len(source.splitlines())

    return {
        "rel_path": rel_path,
        "line_count": line_count,
        "docstring_summary": "",
        "functions": [],
        "classes": [],
        "imports": [],
        "has_main_guard": False,
        "has_argparse": False,
        "is_entrypoint": False,
        "complexity": {
            "functions": 0,
            "classes": 0,
            "methods": 0,
            "imports": 0,
            "lines": line_count,
        },
    }


# ---------------------------------------------------------------------------
# Charter name generation
# ---------------------------------------------------------------------------

def charter_name_from_path(rel_path):
    """Generate a charter name from a file path.

    Examples:
        src/auth/login.py -> auth-login
        gator-command/scripts/gator-fleet-report.py -> gator-fleet-report
        lib/utils.py -> utils
    """
    p = Path(rel_path)
    stem = p.stem

    # For files in a meaningful directory, include the parent
    parent = p.parent
    if parent != Path(".") and parent.name not in (".", "src", "lib", "scripts"):
        return f"{parent.name}-{stem}"

    return stem


# ---------------------------------------------------------------------------
# Scaffold generation
# ---------------------------------------------------------------------------

def generate_scaffold(analysis):
    """Generate a markdown charter scaffold from analysis results.

    @reads: analysis dict from analyze_python()
    """
    rel_path = analysis["rel_path"]
    name = charter_name_from_path(rel_path)
    complexity = analysis["complexity"]
    today = date.today().isoformat()

    lines = []
    lines.append(f"# Charter: {name}")
    lines.append("")
    lines.append(f"**Covers**: `{rel_path}`")
    lines.append("")

    # Owns section
    lines.append("## Owns")
    lines.append("")
    if analysis.get("docstring_summary"):
        lines.append(f"<!-- Mechanical hint: module docstring says: {analysis['docstring_summary']} -->")
    lines.append("<!-- Agent enrichment needed: describe what this module owns and why -->")
    lines.append("")

    # Does Not Own section
    lines.append("## Does Not Own")
    lines.append("")
    lines.append("<!-- Agent enrichment needed: define boundaries -->")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Public functions
    public_fns = [f for f in analysis["functions"] if not f["is_private"]]
    private_fns = [f for f in analysis["functions"] if f["is_private"]]

    for fn in public_fns:
        lines.append(f"### {fn['signature']}")
        lines.append(f"File: `{rel_path}`")
        if fn["docstring_summary"]:
            lines.append(f"<!-- Mechanical hint: {fn['docstring_summary']} -->")
        lines.append("<!-- Agent enrichment needed: purpose, filesystem access, callers, tripwires -->")
        lines.append("")

    # Classes
    for cls in analysis["classes"]:
        lines.append(f"### class {cls['name']}")
        lines.append(f"File: `{rel_path}`")
        if cls["docstring_summary"]:
            lines.append(f"<!-- Mechanical hint: {cls['docstring_summary']} -->")
        lines.append("<!-- Agent enrichment needed: purpose, responsibilities -->")
        lines.append("")

        pub_methods = [m for m in cls["methods"]
                       if not m["name"].startswith("_") or m["name"] in ("__init__",)]
        for m in pub_methods:
            lines.append(f"#### {cls['name']}.{m['signature']}")
            if m["docstring_summary"]:
                lines.append(f"<!-- Mechanical hint: {m['docstring_summary']} -->")
            lines.append("<!-- Agent enrichment needed -->")
            lines.append("")

    # Internal helpers (collapsed)
    if private_fns:
        lines.append("### Internal helpers")
        lines.append("")
        for fn in private_fns:
            summary = f" — {fn['docstring_summary']}" if fn["docstring_summary"] else ""
            lines.append(f"- `{fn['signature']}`{summary}")
        lines.append("")

    lines.append("---")
    lines.append("")

    # Mechanical scaffold notes
    lines.append("## Scaffold Notes")
    lines.append("")
    if analysis["imports"]:
        lines.append(f"- **Imports**: {', '.join(analysis['imports'])}")
    lines.append(f"- **Complexity**: {complexity['functions']} functions, "
                 f"{complexity['classes']} classes, "
                 f"{complexity['methods']} methods, "
                 f"{complexity['lines']} lines")
    lines.append(f"- **Entrypoint**: {'yes' if analysis['is_entrypoint'] else 'no'}")
    lines.append(f"- Generated: {today} by gator-charter-draft {VERSION}")
    lines.append("")

    # Connections placeholder
    lines.append("## Connections")
    lines.append("")
    lines.append("<!-- Agent enrichment needed: cross-references to other charters -->")
    lines.append("-> [Index](INDEX.md)")
    lines.append("")

    return "\n".join(lines), name


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_scaffolds(scaffolds):
    """Print all scaffolds to stdout, separated by dividers."""
    for i, (text, name) in enumerate(scaffolds):
        if i > 0:
            print("\n" + "=" * 72 + "\n")
        print(text)


def print_json(analyses, scaffolds):
    """Output structured JSON."""
    items = []
    for analysis, (text, name) in zip(analyses, scaffolds):
        items.append({
            "charter_name": name,
            "source_file": analysis["rel_path"],
            "complexity": analysis["complexity"],
            "is_entrypoint": analysis["is_entrypoint"],
            "function_count": len(analysis["functions"]),
            "class_count": len(analysis["classes"]),
            "scaffold_lines": len(text.splitlines()),
        })

    output = {
        "version": VERSION,
        "generated": date.today().isoformat(),
        "file_count": len(items),
        "charters": items,
    }
    print(json.dumps(output, indent=2))


def write_scaffolds(scaffolds, output_dir, dry_run=False):
    """Write scaffold files to the specified charter directory.

    Never overwrites existing charter files.

    @writes: <output_dir>/<name>.md (new files only)
    """
    charters_dir = Path(output_dir)
    charters_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    skipped = 0

    for text, name in scaffolds:
        filename = f"{name}.md"
        dest = charters_dir / filename

        if dest.exists():
            if dry_run:
                print(f"  skip (exists): {filename}")
            skipped += 1
            continue

        if dry_run:
            print(f"  would write: {filename}")
        else:
            dest.write_text(text, encoding="utf-8")
            print(f"  + {filename}")
        written += 1

    return written, skipped


def print_index_suggestions(scaffolds, analyses):
    """Print INDEX.md routing suggestions."""
    print()
    print("  INDEX.md suggestions:")
    print()
    print("  | Charter | Covers | Complexity |")
    print("  |---------|--------|------------|")
    for analysis, (_, name) in zip(analyses, scaffolds):
        c = analysis["complexity"]
        score = f"{c['functions']}f/{c['classes']}c/{c['lines']}L"
        print(f"  | [{name}]({name}.md) | `{analysis['rel_path']}` | {score} |")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ensure_utf8_stdout()

    parser = argparse.ArgumentParser(
        description="Gator charter-draft — mechanical charter scaffold generator.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--path", "-p",
        help="Path to repo (default: current directory, walks up to find .gator/)",
    )
    parser.add_argument(
        "--dirs", "-d", nargs="+",
        help="Directories to scope to (relative to repo root). "
             "If omitted, scans all tracked files minus .charterignore exclusions.",
    )
    parser.add_argument(
        "--output-dir", "-o",
        help="Directory to write charters to (default: .gator/charters/). "
             "Use this to target a different charter surface, e.g. gator-command/charters/.",
    )
    parser.add_argument(
        "--write", "-w", action="store_true",
        help="Write draft charters (never overwrites existing). "
             "Default target: .gator/charters/ (override with --output-dir).",
    )
    parser.add_argument(
        "--dry-run", "-n", action="store_true",
        help="Show what would be written without writing",
    )
    parser.add_argument(
        "--json", "-j", action="store_true",
        help="Output structured JSON",
    )
    parser.add_argument(
        "--index", "-i", action="store_true",
        help="Include INDEX.md routing suggestions",
    )
    args = parser.parse_args()

    # Find repo root
    repo_root = find_gator_root(args.path)
    if not repo_root:
        print("  Error: no .gator/ found. Run from a gatorized repo.", file=sys.stderr)
        sys.exit(1)

    from gator_layout import get_gator_paths
    paths = get_gator_paths(repo_root)

    # Discover files
    files = discover_files(repo_root, paths, args.dirs)

    if not files:
        if args.json:
            print(json.dumps({"version": VERSION, "file_count": 0, "charters": []}))
        else:
            print()
            print("  gator charter-draft")
            print()
            print("  No charterable source files found.")
            if args.dirs:
                print(f"  Scoped to: {', '.join(args.dirs)}")
            print("  Check .gator/.charterignore and --dirs scope.")
            print()
        return

    # Analyze
    analyses = []
    for rel_path in files:
        abs_path = repo_root / rel_path
        ext = Path(rel_path).suffix.lower()

        result = None
        if ext == ".py":
            result = analyze_python(abs_path, rel_path)
        elif ext in (".js", ".jsx", ".ts", ".tsx"):
            result = analyze_javascript(abs_path, rel_path)
        elif ext in (".sh", ".bash"):
            result = analyze_shell(abs_path, rel_path)
        else:
            # Minimal analysis for coverage tracking only
            result = analyze_minimal(abs_path, rel_path)

        if result:
            analyses.append(result)

    if not analyses:
        if args.json:
            print(json.dumps({"version": VERSION, "file_count": 0, "charters": []}))
        else:
            print()
            print("  gator charter-draft")
            print()
            print(f"  Found {len(files)} source files but none could be parsed.")
            print()
        return

    # Generate scaffolds
    scaffolds = [generate_scaffold(a) for a in analyses]

    # Output
    if args.json:
        print_json(analyses, scaffolds)
        return

    if not args.write and not args.dry_run:
        print()
        print(f"  gator charter-draft  ({len(scaffolds)} files → {len(scaffolds)} charter drafts)")
        print()
        print_scaffolds(scaffolds)

        if args.index:
            print_index_suggestions(scaffolds, analyses)
        return

    # Resolve output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
        if not output_dir.is_absolute():
            output_dir = repo_root / output_dir
    else:
        output_dir = paths.charters_dir

    # Write or dry-run
    mode = "dry run" if args.dry_run else "write"
    print()
    print(f"  gator charter-draft ({mode})")
    print(f"  target: {output_dir}")
    print()
    written, skipped = write_scaffolds(scaffolds, output_dir, dry_run=args.dry_run)

    if args.index:
        print_index_suggestions(scaffolds, analyses)

    print(f"  {written} {'would be written' if args.dry_run else 'written'}, {skipped} skipped (already exist)")
    print()


if __name__ == "__main__":
    main()
