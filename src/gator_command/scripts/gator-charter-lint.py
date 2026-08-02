#!/usr/bin/env python3
"""
gator-charter-lint — validate charter files against Charter Schema v1.

Usage:
    python gator-charter-lint.py [--json] [--charter PATH] [--charters-dir DIR]

Structural validation only — checks that required sections exist and function
entries are well-formed. Does not check content quality, file path resolution,
or function name existence.

@reads: .gator/charters/*.md, gator-command/charters/*.md
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from gator_core import ensure_utf8_stdout
except ImportError:
    def ensure_utf8_stdout():
        pass

SKIP_FILES = {"_template.md", "README.md"}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    check: str
    severity: str  # error, warn, info
    line: int
    message: str


@dataclass
class FunctionEntry:
    name: str
    line: int
    has_file_line: bool = False
    has_description: bool = False
    has_annotations: bool = False


@dataclass
class CharterDoc:
    path: str = ""
    lines: list = field(default_factory=list)
    title: str = ""
    title_line: int = 0
    has_covers: bool = False
    covers_line: int = 0
    sections: dict = field(default_factory=dict)  # heading -> line number
    separators: list = field(default_factory=list)  # line numbers of ---
    functions: list = field(default_factory=list)  # list of FunctionEntry
    is_index: bool = False
    is_cross_cutting: bool = False
    has_dispatch_table: bool = False


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def parse_charter(path):
    """Parse a charter markdown file into a CharterDoc structure."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    doc = CharterDoc(path=str(path), lines=lines)

    # Detect file type from first heading
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# Charter Index"):
            doc.is_index = True
            doc.title = stripped
            doc.title_line = i + 1
            break
        if stripped.startswith("# Charter:"):
            doc.title = stripped
            doc.title_line = i + 1
            break
        if stripped.startswith("# "):
            doc.title = stripped
            doc.title_line = i + 1
            break

    # Scan for structural elements
    non_blank_count = 0
    current_section = None
    current_func = None
    in_table = False

    ANNOTATION_PREFIXES = (
        "@reads:", "@writes:", "Models:", "Filesystem:",
        "Session R:", "Session W:",
        "←", "<-", "→", "->", "!",
    )

    for i, line in enumerate(lines):
        stripped = line.strip()
        lineno = i + 1

        # Track non-blank lines for covers detection
        if stripped:
            non_blank_count += 1

        # Covers line
        if "**Covers**:" in stripped or "**Covers**" in stripped:
            doc.has_covers = True
            doc.covers_line = lineno

        # Separators
        if stripped == "---":
            doc.separators.append(lineno)

        # Tables (for dispatch table detection)
        if stripped.startswith("|") and "|" in stripped[1:]:
            in_table = True
            if "changing" in stripped.lower() or "charter" in stripped.lower():
                doc.has_dispatch_table = True
        elif in_table and not stripped.startswith("|"):
            in_table = False

        # Section headings (## level)
        if stripped.startswith("## ") and not stripped.startswith("### "):
            section_name = stripped[3:].strip()
            doc.sections[section_name] = lineno
            current_section = section_name
            current_func = None

            # Detect cross-cutting patterns
            if "TRIPWIRE" in section_name or "Pattern" in section_name:
                doc.is_cross_cutting = True
            continue

        # Function entries (### level)
        if stripped.startswith("### "):
            func_name = stripped[4:].strip()
            current_func = FunctionEntry(name=func_name, line=lineno)
            doc.functions.append(current_func)
            continue

        # Parse function entry content
        if current_func and stripped:
            if stripped.startswith("File:") or stripped.startswith("File :"):
                current_func.has_file_line = True
            elif any(stripped.startswith(p) for p in ANNOTATION_PREFIXES):
                current_func.has_annotations = True
            elif not current_func.has_description:
                # First non-annotation, non-File line is description
                # (File: line may be absent for bash/single-file charters)
                current_func.has_description = True

    return doc


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _get_covers_text(doc):
    """Extract the covers line text from the doc."""
    if not doc.has_covers:
        return ""
    idx = doc.covers_line - 1
    if 0 <= idx < len(doc.lines):
        return doc.lines[idx]
    return ""


def validate_charter(doc):
    """Validate a parsed CharterDoc. Returns list of Finding."""
    findings = []

    if doc.is_index:
        return _validate_index(doc)

    # Title
    if not doc.title.startswith("# Charter:"):
        findings.append(Finding(
            "title-format", "error", doc.title_line or 1,
            f"First heading should be '# Charter: [Name]', got: '{doc.title}'"
        ))

    # Covers — not required for cross-cutting charters (they cover patterns, not files)
    if not doc.has_covers and not doc.is_cross_cutting:
        findings.append(Finding(
            "covers-present", "error", 1,
            "**Covers**: line missing (should appear within first 5 non-blank lines)"
        ))

    # Required sections
    owns_found = False
    does_not_own_found = False

    for section, lineno in doc.sections.items():
        if section == "Owns":
            owns_found = True
        if section == "Does Not Own":
            does_not_own_found = True

    if not owns_found:
        findings.append(Finding(
            "owns-section", "error", 1,
            "Missing required section: ## Owns"
        ))

    if not does_not_own_found:
        findings.append(Finding(
            "does-not-own-section", "error", 1,
            "Missing required section: ## Does Not Own"
        ))

    # Separator before functions
    if doc.functions and not doc.separators:
        findings.append(Finding(
            "separator-before-functions", "error", doc.functions[0].line,
            "Function entries found but no --- separator before them"
        ))

    # Conditional sections (required if functions exist)
    if doc.functions:
        has_before_changing = any(
            s.startswith("Before Changing") for s in doc.sections
        )
        has_connections = "Connections" in doc.sections

        if not has_before_changing:
            findings.append(Finding(
                "before-changing-section", "warn", 1,
                "Missing '## Before Changing This Module' — recommended when function entries exist"
            ))

        if not has_connections:
            findings.append(Finding(
                "connections-section", "warn", 1,
                "Missing '## Connections' — recommended when function entries exist"
            ))

    # Function entry validation
    # Count how many covered files there are (multi-file charters need File: lines more)
    multi_file = doc.has_covers and ("," in _get_covers_text(doc) or "`.gator" not in _get_covers_text(doc) and "`gator" not in _get_covers_text(doc))

    for func in doc.functions:
        if not func.has_file_line:
            # Error for multi-file charters (ambiguous which file), warn for single-file
            severity = "warn"
            findings.append(Finding(
                "file-line", severity, func.line,
                f"Function entry '{func.name}' missing 'File:' line"
            ))

        if func.has_file_line and not func.has_description:
            findings.append(Finding(
                "description-line", "warn", func.line,
                f"Function entry '{func.name}' has no description after File: line"
            ))

        if not func.has_annotations:
            findings.append(Finding(
                "no-annotations", "info", func.line,
                f"Function entry '{func.name}' has no caller/callee/tripwire annotations"
            ))

    return findings


def _validate_index(doc):
    """Validate an INDEX.md file."""
    findings = []

    if not doc.title.startswith("# Charter Index"):
        findings.append(Finding(
            "index-title", "error", doc.title_line or 1,
            f"INDEX.md should start with '# Charter Index', got: '{doc.title}'"
        ))

    if not doc.has_dispatch_table:
        findings.append(Finding(
            "dispatch-table", "warn", 1,
            "INDEX.md should contain a dispatch table mapping code paths to charters"
        ))

    return findings


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report(results):
    """Print human-readable report."""
    total_errors = 0
    total_warnings = 0
    total_info = 0

    for path, findings in results.items():
        errors = [f for f in findings if f.severity == "error"]
        warnings = [f for f in findings if f.severity == "warn"]
        infos = [f for f in findings if f.severity == "info"]

        total_errors += len(errors)
        total_warnings += len(warnings)
        total_info += len(infos)

        if not findings:
            print(f"  ✓ {Path(path).name}")
            continue

        status = "✗" if errors else "⚠" if warnings else "·"
        print(f"  {status} {Path(path).name}")

        for f in findings:
            icon = {"error": "✗", "warn": "⚠", "info": "·"}.get(f.severity, " ")
            print(f"    {icon} L{f.line}: [{f.check}] {f.message}")

    print()
    print(f"  {len(results)} files checked: "
          f"{total_errors} errors, {total_warnings} warnings, {total_info} info")


def print_json_report(results):
    """Print JSON report."""
    output = {}
    for path, findings in results.items():
        output[path] = [asdict(f) for f in findings]
    print(json.dumps(output, indent=2))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def find_charter_dirs():
    """Find charter directories from the current working directory."""
    from gator_layout import get_gator_paths

    dirs = []
    cwd = Path.cwd()

    # Check .gator/charters/ via layout resolver (per-repo governance)
    if (cwd / ".gator").is_dir():
        paths = get_gator_paths(cwd)
        if paths.charters_dir.is_dir():
            dirs.append(paths.charters_dir)

    # Check gator-command/charters/ (command-post product charters)
    gc_charters = cwd / "gator-command" / "charters"
    if gc_charters.is_dir():
        dirs.append(gc_charters)

    return dirs


def collect_files(charter_path=None, charters_dir=None):
    """Collect charter files to validate."""
    files = []

    if charter_path:
        files.append(Path(charter_path))
    elif charters_dir:
        d = Path(charters_dir)
        if d.is_dir():
            files.extend(sorted(f for f in d.glob("*.md") if f.name not in SKIP_FILES))
    else:
        for d in find_charter_dirs():
            files.extend(sorted(f for f in d.glob("*.md") if f.name not in SKIP_FILES))

    return files


def main():
    ensure_utf8_stdout()

    parser = argparse.ArgumentParser(
        description="Validate charter files against Charter Schema v1."
    )
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    parser.add_argument("--charter", metavar="PATH", help="Validate a single charter file")
    parser.add_argument("--charters-dir", metavar="DIR", help="Validate all charters in directory")

    args = parser.parse_args()

    files = collect_files(charter_path=args.charter, charters_dir=args.charters_dir)

    if not files:
        print("  No charter files found.")
        return

    print()
    print(f"  charter-lint: checking {len(files)} files")
    print()

    results = {}
    has_errors = False

    for f in files:
        try:
            doc = parse_charter(f)
            findings = validate_charter(doc)
            results[str(f)] = findings
            if any(fd.severity == "error" for fd in findings):
                has_errors = True
        except Exception as e:
            results[str(f)] = [Finding("parse-error", "error", 0, str(e))]
            has_errors = True

    if args.json:
        print_json_report(results)
    else:
        print_report(results)

    sys.exit(1 if has_errors else 0)


if __name__ == "__main__":
    main()
