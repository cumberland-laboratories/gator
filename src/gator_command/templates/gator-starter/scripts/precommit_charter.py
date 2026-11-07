"""Charter discovery and validation for the gator pre-commit hook.

Resolves charter surfaces, iterates charter files, parses INDEX.md,
checks function references, and detects new undocumented seams.
Self-contained — no gator_core imports required. `new_seam_functions()`
imports the sibling `charter_significance` (shipped beside this file in
every hook runtime) and degrades to no warning without it.
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


_PY_EXTENSIONS = (".py",)
_JS_EXTENSIONS = (".js", ".jsx", ".ts", ".tsx")
_PY_NEW_DEF = re.compile(r"^(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(")
_JS_NEW_DEF = re.compile(
    r"^\s*(?:export\s+)?(?:(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*\("
    r"|(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=)")


def _git_bytes(repo_root, args, stdin=None):
    """Run git and return stdout bytes, or None on any failure."""
    try:
        result = subprocess.run(["git", *args], cwd=str(repo_root), input=stdin,
                                capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def _new_definitions(repo_root):
    """`[(path, name)]` for top-level definitions added in the staged diff."""
    out = _git_bytes(repo_root, ["diff", "--cached", "-U0", "--no-color", "--no-ext-diff"])
    if out is None:
        return []
    found = []
    path = None
    for line in out.decode("utf-8", errors="replace").splitlines():
        if line.startswith("+++ "):
            target = line[4:].rstrip("\t")
            path = target[2:] if target.startswith("b/") else None
            continue
        if not path or not line.startswith("+"):
            continue
        added = line[1:]
        ext = Path(path).suffix.lower()
        if ext in _PY_EXTENSIONS:
            m = _PY_NEW_DEF.match(added)          # top level only, like the verifier
            name = m.group(1) if m else None
        elif ext in _JS_EXTENSIONS:
            m = _JS_NEW_DEF.match(added)
            name = (m.group(1) or m.group(2)) if m else None
        else:
            name = None
        if name and (path, name) not in found:
            found.append((path, name))
    return found


def _index_entries(repo_root):
    """`{path: oid}` for every stage-0 entry in the index, or None."""
    out = _git_bytes(repo_root, ["ls-files", "-s", "-z"])
    if out is None:
        return None
    entries = {}
    for record in out.split(b"\0"):
        if not record:
            continue
        meta, _, path = record.partition(b"\t")
        fields = meta.split()
        if len(fields) == 3 and fields[2] == b"0":
            entries[path.decode("utf-8", errors="replace")] = fields[1].decode()
    return entries


def _read_blobs(repo_root, oids):
    """`{oid: text}` read through one `git cat-file --batch`, or None."""
    oids = list(dict.fromkeys(oids))
    if not oids:
        return {}
    out = _git_bytes(repo_root, ["cat-file", "--batch"],
                     stdin=("\n".join(oids) + "\n").encode())
    if out is None:
        return None
    blobs, pos = {}, 0
    for oid in oids:
        end = out.find(b"\n", pos)
        if end < 0:
            return None
        header = out[pos:end].split()
        pos = end + 1
        if len(header) != 3 or header[1] != b"blob":
            continue                              # missing or not a blob
        size = int(header[2])
        blobs[oid] = out[pos:pos + size].decode("utf-8", errors="replace")
        pos += size + 1                           # content, then a newline
    return blobs


def new_seam_functions(repo_root, charter_dir=None):
    """New public seams in the staged change that no charter documents.

    Reads the index only — never the working tree (#105):
    - new top-level definitions come from the added lines of the staged diff;
    - every tracked `.py` / `.js`-family path is a candidate importer, read
      by object ID through one `git cat-file --batch`; a blob that does not
      mention a new name is skipped before parsing;
    - ownership is the staged INDEX.md routing. The cross-cutting charter
      is "read first" routing, not ownership, so it counts only for a file
      routed to nothing else;
    - documented and `**Internal**:` names come from every staged charter.
    The decision is `charter_significance.decide()`, shared with the
    verifier. Any Git or import failure returns [] (advisory, never a block).
    """
    try:
        scripts_dir = str(Path(__file__).resolve().parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import charter_significance as significance

        new_defs = _new_definitions(repo_root)
        if not new_defs:
            return []
        entries = _index_entries(repo_root)
        if entries is None:
            return []
        cross_cutting = None
        if charter_dir is None:
            charter_dir, cross_cutting = _resolve_charter_surface(repo_root)
        try:
            charter_rel = Path(charter_dir).resolve().relative_to(
                Path(repo_root).resolve()).as_posix()
        except ValueError:
            return []

        charter_paths = [p for p in entries
                         if p.startswith(charter_rel + "/") and p.endswith(".md")
                         and "/" not in p[len(charter_rel) + 1:]]
        if cross_cutting is None:
            cross_cutting = next((p.rsplit("/", 1)[-1] for p in charter_paths
                                  if "cross-cutting" in p.rsplit("/", 1)[-1]), None)
        code_paths = [p for p in entries
                      if Path(p).suffix.lower() in _PY_EXTENSIONS + _JS_EXTENSIONS]
        blobs = _read_blobs(repo_root, [entries[p] for p in charter_paths + code_paths])
        if blobs is None:
            return []

        def text(path):
            return blobs.get(entries.get(path), "")

        mappings = _parse_index_text(text(charter_rel + "/INDEX.md"))

        def owners(path):
            routed = _required_charters_for_files([path], repo_root, mappings)
            narrowed = routed - {cross_cutting}
            return narrowed or routed

        documented, excluded = set(), set()
        for path in charter_paths:
            if path.rsplit("/", 1)[-1] in CHARTER_SCAFFOLD_FILES:
                continue
            body = text(path)
            for line in body.splitlines():
                for name in significance.heading_names(line):
                    documented.update({name, name.split(".")[-1]})
            excluded.update(significance.parse_internal(body)[0])

        def signals(path):
            if Path(path).suffix.lower() in _PY_EXTENSIONS:
                return significance.python_signals(text(path))
            return significance.javascript_signals(text(path))

        new_names = {name for _, name in new_defs}
        importer_signals = {}
        for path in code_paths:
            body = text(path)
            if any(name in body for name in new_names):
                importer_signals[path] = signals(path)

        seams = []
        for path, name in new_defs:
            if name in documented or name in excluded or name in seams:
                continue
            if path not in entries:
                continue                          # deleted or not a tracked file
            stem = Path(path).stem
            importer_owners = [owners(q) for q, sig in importer_signals.items()
                               if q != path and (stem, name) in sig["imports"]]
            own_signals = importer_signals.get(path) or signals(path)
            decision, _ = significance.decide(
                name, name.startswith("_"), own_signals["entries"],
                importer_owners, owners(path))
            if decision == "document":
                seams.append(name)
        return seams
    except Exception:
        return []


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

    return _parse_index_text(text)


def _parse_index_text(text):
    """INDEX.md text -> list of (pattern_str, set_of_charter_filenames)."""
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


def _required_charters_for_files(code_files, repo_root, mappings=None):
    """Given a list of changed code files, return the set of charter filenames
    that INDEX.md says should be consulted.

    `mappings` (from `_parse_index_text()`) replaces the working-tree
    INDEX.md, so a caller can route against the staged INDEX blob.

    Returns set of charter filenames (e.g. {"scripts-fleet-intelligence.md",
    "scripts-cross-cutting.md"}).
    """
    if mappings is None:
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
