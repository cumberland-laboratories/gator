"""Charter discovery and validation for the gator pre-commit hook.

Resolves charter surfaces, iterates charter files, parses INDEX.md,
checks function references, and detects undocumented functions.
Self-contained — no gator_core imports required.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# Internal scaffold files that are not real charters
CHARTER_SCAFFOLD_FILES = {"_template.md", "README.md", "INDEX.md", ".gitkeep"}


# ---------------------------------------------------------------------------
# Charter discovery
# ---------------------------------------------------------------------------

def _resolve_charter_surface(repo_root):
    """Resolve the charter surface for this repo.

    Tries gator_core.resolve_charter_surface() first (canonical resolver),
    falls back to inline heuristic for self-contained operation.

    Returns (charter_dir: Path, cross_cutting_name: str|None).
    """
    try:
        scripts_dir = repo_root / "src" / "gator_command" / "scripts"
        if not scripts_dir.is_dir():
            scripts_dir = repo_root / "gator-command" / "scripts"
        if not scripts_dir.is_dir():
            scripts_dir = repo_root / ".gator" / "scripts"
        if scripts_dir.is_dir() and str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        from gator_core import resolve_charter_surface
        surface = resolve_charter_surface(repo_root)
        return Path(surface["charter_dir"]), surface.get("cross_cutting")
    except (ImportError, Exception):
        pass

    # Fallback: inline resolution (self-contained for fleet repos)
    command_post_charters = repo_root / "gator-command" / "charters"
    command_post_scripts = repo_root / "gator-command" / "scripts"
    if command_post_charters.is_dir() and command_post_scripts.is_dir():
        charter_dir = command_post_charters
    else:
        charter_dir = repo_root / ".gator" / "charters"

    cross_cutting = None
    if charter_dir.is_dir():
        for f in charter_dir.iterdir():
            if "cross-cutting" in f.name and f.suffix == ".md":
                cross_cutting = f.name
                break
    return charter_dir, cross_cutting


def _resolve_charter_dir(repo_root):
    """Convenience: return just the charter directory Path."""
    charter_dir, _ = _resolve_charter_surface(repo_root)
    return charter_dir


def _iter_charter_files(repo_root):
    """Yield real charter files from the governed repo's charter surface."""
    charter_dir = _resolve_charter_dir(repo_root)
    if not charter_dir.is_dir():
        return
    for charter_file in charter_dir.iterdir():
        if charter_file.suffix != ".md":
            continue
        if charter_file.name in CHARTER_SCAFFOLD_FILES:
            continue
        yield charter_file


# ---------------------------------------------------------------------------
# Charter state readers
# ---------------------------------------------------------------------------

def count_charters(gator_dir):
    """Count charter files and documented functions."""
    repo_root = gator_dir.parent
    charter_files = list(_iter_charter_files(repo_root))

    function_count = 0
    for cf in charter_files:
        try:
            text = cf.read_text(encoding="utf-8", errors="replace")
            for line in text.splitlines():
                if line.strip().startswith("### ") and "(" in line:
                    function_count += 1
        except OSError:
            continue

    return len(charter_files), function_count


def read_tripwire_patterns(gator_dir):
    """Extract @tripwire file patterns from charters."""
    patterns = set()
    repo_root = gator_dir.parent
    for cf in _iter_charter_files(repo_root):
        try:
            text = cf.read_text(encoding="utf-8", errors="replace")
            for line in text.splitlines():
                if "@tripwire" in line.lower():
                    # Extract file paths mentioned on tripwire lines
                    # Look for backtick-quoted paths or bare paths
                    for match in re.finditer(r'`([^`]+\.\w+)`', line):
                        patterns.add(match.group(1))
        except OSError:
            continue
    return patterns


# ---------------------------------------------------------------------------
# Charter validation (called by validate_hard_rules / validate_soft_rules)
# ---------------------------------------------------------------------------

def _check_charter_function_refs(charter_files, repo_root):
    """Check that ### func() entries in staged charters reference real functions.

    Parses charter for '### name(' entries and the 'Covers:' line, then greps
    the covered files for those function names. Returns list of names not found.
    Self-contained — no gator_core imports.
    """
    stale = []
    for cf in charter_files:
        cf_path = Path(cf) if Path(cf).is_absolute() else repo_root / cf
        if not cf_path.is_file():
            continue
        try:
            text = cf_path.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            continue

        # Extract function names from ### entries
        func_names = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("### ") and "(" in stripped:
                # "### foo_bar(args)" -> "foo_bar"
                name = stripped[4:].split("(")[0].strip()
                if name:
                    func_names.append(name)

        if not func_names:
            continue

        # Extract covered files from Covers: line
        covered_files = []
        for line in text.splitlines():
            if line.startswith("**Covers**:") or line.startswith("**Covers:**"):
                covered_files = re.findall(r'`([^`]+)`', line)
                break

        if not covered_files:
            continue

        # Read covered file contents
        covered_content = ""
        for rel_path in covered_files:
            full = repo_root / rel_path
            if full.is_file():
                try:
                    covered_content += full.read_text(encoding="utf-8", errors="replace")
                except (OSError, UnicodeDecodeError):
                    pass

        if not covered_content:
            continue

        # Check each function name exists somewhere in covered files
        for name in func_names:
            if name not in covered_content:
                stale.append(name)

    return stale


def _detect_new_functions(staged_files, repo_root):
    """Detect new function definitions in staged code and new ### entries in charters.

    Uses git diff --cached to find added lines. Returns (new_code_funcs, new_charter_entries).
    Self-contained — no gator_core imports.
    """
    new_code_funcs = []
    new_charter_entries = []

    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "-U0", "--no-color"],
            capture_output=True, text=True, cwd=str(repo_root),
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            return [], []
    except (OSError, subprocess.TimeoutExpired):
        return [], []

    for line in result.stdout.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        added = line[1:].strip()

        # New function definitions in code
        if (added.startswith("def ") or
                added.startswith("function ") or
                added.startswith("func ")):
            # Extract name: "def foo(..." -> "foo"
            for prefix in ("def ", "function ", "func "):
                if added.startswith(prefix):
                    rest = added[len(prefix):]
                    name = rest.split("(")[0].strip()
                    if name and not name.startswith("_"):
                        new_code_funcs.append(name)
                    break

        # New charter entries
        if added.startswith("### ") and "(" in added:
            name = added[4:].split("(")[0].strip()
            if name:
                new_charter_entries.append(name)

    return new_code_funcs, new_charter_entries


def _parse_charter_index(repo_root):
    """Parse INDEX.md to build a map of file patterns -> required charter names.

    Returns list of (pattern_str, set_of_charter_filenames) or empty list
    if INDEX is missing or unparseable.
    Self-contained — no gator_core imports.
    """
    charter_dir = _resolve_charter_dir(repo_root)
    index_path = charter_dir / "INDEX.md"
    if not index_path.is_file():
        return []

    try:
        text = index_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    mappings = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|") or line.startswith("| If") or line.startswith("|---"):
            continue
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) < 2:
            continue

        # Parse file patterns from first column
        # Format: `file.py`, `file2.py`, ... or prose like "Any pattern..."
        patterns = re.findall(r'`([^`]+)`', parts[0])
        if not patterns:
            continue

        # Parse charter refs from second column
        # Format: [Name](filename.md) · [Name2](filename2.md)
        charter_refs = set(re.findall(r'\(([^)]+\.md)\)', parts[1]))
        if not charter_refs:
            continue

        for pattern in patterns:
            mappings.append((pattern, charter_refs))

    return mappings


def _required_charters_for_files(code_files, repo_root):
    """Given a list of changed code files, return the set of charter filenames
    that INDEX.md says should be consulted.

    Returns set of charter filenames (e.g. {"scripts-fleet-intelligence.md",
    "scripts-cross-cutting.md"}).
    """
    mappings = _parse_charter_index(repo_root)
    if not mappings:
        return set()

    import fnmatch as _fnmatch
    required = set()
    for code_file in code_files:
        f_normalized = code_file.replace("\\", "/")
        f_basename = f_normalized.rsplit("/", 1)[-1]
        for pattern, charter_refs in mappings:
            if "*" in pattern or "?" in pattern:
                if _fnmatch.fnmatch(f_basename, pattern) or _fnmatch.fnmatch(f_normalized, pattern):
                    required.update(charter_refs)
            elif f_basename == pattern or pattern in f_normalized:
                required.update(charter_refs)

    return required
