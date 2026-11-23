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

def _legacy_heading_names(line):
    """Pre-#16 reader: the text before the first `(` of a `### ` heading."""
    stripped = line.strip()
    if stripped.startswith("### ") and "(" in stripped:
        name = stripped[4:].split("(")[0].strip()
        return [name] if name else []
    return []


def _check_charter_function_refs(charter_files, repo_root):
    """Names in staged charters' `### ` headings that no covered file contains.

    Headings are read with `charter_significance.heading_names()` (#16), the
    reader the verifier and the new-seam warning use, so a compound heading
    such as `### Vendor cleanup in _run() / print_plan()` yields `_run` and
    `print_plan`, and prose or constants yield nothing. The files searched
    are the tracked files the charter's `**Covers**:` line names
    (`charter_covers` grammar, so globs and directory prefixes count) plus
    every `File:` line. A dotted name (`window.gatorNavToRepo`) is found by
    its last part. Returns the names not found; any failure finds nothing.
    """
    try:
        import charter_significance as significance
        heading_names = significance.heading_names
        parse_file_line = significance.parse_file_line
    except ImportError:  # older runtime without the shared reader
        heading_names = _legacy_heading_names
        parse_file_line = lambda line: None  # noqa: E731
    try:
        from charter_covers import covers_match
    except ImportError:
        def covers_match(path, entry):
            return path.replace("\\", "/") == entry.replace("\\", "/")

    repo_root = Path(repo_root)
    tracked = None

    stale = []
    for cf in charter_files:
        cf_path = Path(cf) if Path(cf).is_absolute() else repo_root / cf
        if not cf_path.is_file():
            continue
        try:
            text = cf_path.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            continue

        lines = text.splitlines()
        func_names = []
        for line in lines:
            if line.strip().startswith("### "):
                for name in heading_names(line.strip()):
                    if name not in func_names:
                        func_names.append(name)
        if not func_names:
            continue

        entries = _covers_entries(text)
        file_lines = [f for f in (parse_file_line(line) for line in lines) if f]
        if not entries and not file_lines:
            continue

        if tracked is None:
            out = _git_bytes(repo_root, ["ls-files", "-z"])
            tracked = ([] if out is None else
                       [t for t in out.decode("utf-8", errors="replace").split("\0") if t])
        paths = [t for t in tracked if any(covers_match(t, e) for e in entries)]
        for rel in entries + file_lines:
            if rel not in paths and not any(c in rel for c in "*?["):
                paths.append(rel)

        covered_content = ""
        for rel_path in paths:
            full = repo_root / rel_path
            if full.is_file():
                try:
                    covered_content += full.read_text(encoding="utf-8", errors="replace")
                except (OSError, UnicodeDecodeError):
                    pass
        if not covered_content:
            continue

        for name in func_names:
            if name.split(".")[-1] not in covered_content:
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
            elif _token_matches(f_normalized, pattern):
                required.update(charter_refs)

    return required


def _token_matches(path, token):
    """A plain INDEX token names `path` on whole path segments (#112).

    The path equals the token, ends with `/<token>` (a bare file name or a
    partial path matches that file wherever it lives), or starts with
    `<token>/` (a directory token). A substring inside another file name
    never matches: `gator_core.py` does not claim `tests/test_gator_core.py`.
    """
    token = token.replace("\\", "/").rstrip("/")
    if not token:
        return False
    return path == token or path.endswith("/" + token) or path.startswith(token + "/")


def _covers_entries(charter_text):
    """The backticked entries of a charter's `**Covers**:` line."""
    for line in charter_text.splitlines():
        if line.startswith("**Covers**:") or line.startswith("**Covers:**"):
            return re.findall(r'`([^`]+)`', line)
    return []


def charter_index_gaps(code_files, staged_charters, repo_root, mappings=None):
    """Return the charter updates that INDEX.md routing still needs (#18).

    INDEX.md is a reading list: Cross-Cutting first, then the matching
    domain rows. For each changed code file and each row that matches it,
    at least one of the row's domain charters must be staged. The
    cross-cutting charter counts as a domain charter only on a row that
    lists nothing else. It is required separately only for a file that
    its own `Covers` line names (`charter_covers` grammar).

    Returns a list of `{"kind": "domain" | "cross-cutting", "files": [...],
    "charters": [...]}`; for `domain`, staging any one of `charters` is
    enough. Empty when routing is satisfied or INDEX.md is absent.
    """
    if mappings is None:
        mappings = _parse_charter_index(repo_root)
    if not mappings:
        return []
    staged = {s.replace("\\", "/").rsplit("/", 1)[-1] for s in staged_charters}
    charter_dir, cross_cutting = _resolve_charter_surface(Path(repo_root))

    gaps = {}
    for code_file in code_files:
        for pattern, charter_refs in mappings:
            if not _required_charters_for_files([code_file], repo_root,
                                                [(pattern, charter_refs)]):
                continue
            domain = set(charter_refs) - {cross_cutting}
            options = frozenset(domain or charter_refs)
            if options & staged:
                continue
            gaps.setdefault(("domain", options), []).append(code_file)

    if cross_cutting and cross_cutting not in staged:
        try:
            cc_text = (Path(charter_dir) / cross_cutting).read_text(
                encoding="utf-8", errors="replace")
        except OSError:
            cc_text = ""
        entries = _covers_entries(cc_text)
        try:
            from charter_covers import covers_match
        except ImportError:  # older runtime without the shared matcher
            def covers_match(path, entry):
                return path.replace("\\", "/") == entry.replace("\\", "/")
        for code_file in code_files:
            if any(covers_match(code_file, e) for e in entries):
                gaps.setdefault(("cross-cutting", frozenset({cross_cutting})),
                                []).append(code_file)

    result = []
    for (kind, options), files in gaps.items():
        unique = list(dict.fromkeys(files))
        result.append({"kind": kind, "files": unique,
                       "charters": sorted(options)})
    result.sort(key=lambda g: (g["kind"] != "domain", g["charters"]))
    return result
