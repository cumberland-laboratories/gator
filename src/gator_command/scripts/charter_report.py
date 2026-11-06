"""Charter health report (`gator-charters-report-v1`): files and Git only.

`build_report()` describes a governed repository's charters mechanically:
the charter inventory, `Covers` coverage of the source files, code size per
charter, and the last charter sync check's summary. `input_fingerprint()`
names everything the report reads, so a consumer can tell whether a saved
report still describes the working tree. `render_text()` is the human view.

The report reuses existing calculations instead of copying them: the source
file set is `gator-charter-draft.discover_files()`, the charter set is
`gator-charter-verify.parse_charters()`, coverage is the shared
`charter_covers` grammar, and the sync summary is
`dashboard.charter_sync.read_last()`. It never runs the verifier's checks or
the sync check, and it never writes a file.
"""

import functools
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from charter_covers import GRAMMAR, coverage_index
from gator_core import get_version, import_sibling, resolve_charter_surface

SCHEMA = "gator-charters-report-v1"
ITEMS_MAX = 200
UNCOVERED_MAX = 50
MODULE_PATHS_MAX = 50
LARGEST_MAX = 10
PROBLEMS_MAX = 20
TEXT_MAX = 300
GIT_TIMEOUT = 30
SYNC_RECORD_NAME = "gator-charter-sync.json"
SYNC_RECORD_MAX = 64 * 1024
TARGET = {"min": 3, "max": 6, "source": "constitution"}

MEASUREMENT = {
    "source_files": ("Tracked files with a supported source extension, after "
                     ".charterignore (or its default exclusions), as the charter "
                     "verifier discovers them."),
    "lines": "Physical lines (newline count) of each source file in the working tree.",
    "coverage": (f"A source file is covered when a charter's Covers entry names it "
                 f"({GRAMMAR}: exact path, directory prefix or full-path glob). "
                 "Charters come from the resolved charter directory."),
    "modules": ("Lines per charter count every file that charter covers; a file "
                "covered by two charters counts in both. Product lines count it once."),
    "sync": "The last charter sync check saved for this checkout; the report never runs it.",
}


# ---------------------------------------------------------------------------
# Input fingerprint
# ---------------------------------------------------------------------------

def _git_bytes(repo, *args):
    """`(stdout bytes, returncode)`; returncode is None when Git cannot run."""
    try:
        r = subprocess.run(["git", *args], cwd=str(repo), capture_output=True,
                           timeout=GIT_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return b"", None
    return r.stdout, r.returncode


def is_work_tree(repo):
    out, rc = _git_bytes(repo, "rev-parse", "--is-inside-work-tree")
    return rc == 0 and out.strip() == b"true"


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _stat(path):
    try:
        st = os.stat(path)
    except OSError:
        return "missing"
    return [st.st_size, st.st_mtime_ns]


def _status_paths(raw):
    """`[(XY, path)]` from `git status --porcelain=v1 -z` (renames give the new path)."""
    out = []
    tokens = raw.split(b"\0")
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        i += 1
        if len(tok) < 4:
            continue
        xy = tok[:2].decode("ascii", "replace")
        out.append((xy, tok[3:].decode("utf-8", "replace")))
        if xy[0] in "RC":
            i += 1  # the original path follows a rename or copy
    return out


def _git_private(repo, name):
    out, rc = _git_bytes(repo, "rev-parse", "--git-path", name)
    if rc != 0 or not out.strip():
        return None
    path = Path(out.strip().decode("utf-8", "replace"))
    return path if path.is_absolute() else Path(repo) / path


@functools.lru_cache(maxsize=1)
def gator_version():
    # Resolved from this file's location, never the caller's working directory,
    # so the CLI and the Dashboard of one install always agree.
    try:
        return get_version(cwd=Path(__file__).resolve().parent)
    except Exception:  # failed_report() must always be buildable
        return "unknown"


def _inputs(repo):
    """`(fingerprint, head)`; `(None, None)` when any Git read fails."""
    repo = Path(repo)
    if not is_work_tree(repo):
        return None, None
    out, rc = _git_bytes(repo, "rev-parse", "--verify", "-q", "HEAD")
    if rc == 0 and out.strip():
        head = out.strip().decode("ascii", "replace")
    elif rc == 1 and not out.strip():
        head = None  # a repository with no commits
    else:
        return None, None
    status, rc = _git_bytes(repo, "--no-optional-locks", "status",
                            "--porcelain=v1", "-z", "--untracked-files=no")
    if rc != 0:
        return None, None
    index, rc = _git_bytes(repo, "ls-files", "-s", "-z")
    if rc != 0:
        return None, None
    worktree = sorted([p, xy, _stat(repo / p)] for xy, p in _status_paths(status))

    charter_dir = Path(resolve_charter_surface(repo)["charter_dir"])
    charters = []
    if charter_dir.is_dir():
        charters = sorted([f.name, _stat(f)] for f in charter_dir.glob("*.md") if f.is_file())
    from gator_layout import get_gator_paths
    ignore = Path(get_gator_paths(repo).charterignore)
    sync = None
    record = _git_private(repo, SYNC_RECORD_NAME)
    if record is not None and record.is_file():
        with open(record, "rb") as fh:
            sync = _sha(fh.read(SYNC_RECORD_MAX + 1))
    payload = {
        "schema": SCHEMA, "gator_version": gator_version(), "head": head,
        "index": _sha(index), "worktree": worktree, "charters": charters,
        "charterignore": _stat(ignore) if ignore.exists() else None, "sync": sync,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return _sha(canonical.encode("utf-8")), head


def input_fingerprint(repo_root):
    """A 64-hex digest of every input the report reads, or None on a Git failure.

    Inputs: the schema and Gator version, HEAD, the index (`ls-files -s`),
    each `status` entry's path, state, size and mtime, the charter files'
    names, sizes and mtimes, `.charterignore`, and the charter sync record's
    bytes. `--no-optional-locks` keeps a reader from taking `index.lock`.
    """
    try:
        return _inputs(repo_root)[0]
    except Exception:  # a reader never fails the caller; None means "unknown"
        return None


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _text(value):
    return str(value)[:TEXT_MAX]


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _base(status):
    return {"schema": SCHEMA, "status": status, "generated_at": _now(),
            "gator_version": gator_version()}


def unavailable_report(reason):
    out = _base("unavailable")
    out["reason"] = _text(reason)
    return out


def failed_report(error):
    out = _base("failed")
    out["error"] = _text(error) or "report failed"
    return out


def _count_lines(path):
    with open(path, "rb") as fh:
        data = fh.read()
    return data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)


def _pct(part, whole):
    return round(part * 100.0 / whole, 1) if whole else None


def _band(pct):
    if pct is None:
        return None
    if pct < TARGET["min"]:
        return "below"
    return "above" if pct > TARGET["max"] else "within"


def _rel(path, repo):
    try:
        return Path(path).resolve().relative_to(repo).as_posix()
    except ValueError:
        return Path(path).as_posix()


def _sync_section(repo, head, problems):
    try:
        from dashboard.charter_sync import read_last
    except Exception as exc:  # optional enrichment: degrade this section only
        problems.append({"section": "sync",
                         "message": _text(f"The charter sync reader is unavailable: {exc}")})
        return {"state": "unavailable"}
    record = read_last(repo)
    if record is None:
        return {"state": "none"}
    revision = record.get("revision")
    return {
        "state": record["state"],
        "checked_at": record["checked_at"],
        "revision": revision,
        "at_head": bool(head and revision and head.startswith(revision)),
        "counts": dict(record["counts"]),
        "findings_total": record["findings_total"],
        "artifact_path": record["artifact_path"],
    }


def build_report(repo_root):
    """The `gator-charters-report-v1` report for `repo_root` (a dict)."""
    repo = Path(repo_root).resolve()
    if not (repo / ".gator").is_dir():
        return unavailable_report("This repository is not gatorized.")
    if not is_work_tree(repo):
        return unavailable_report("This repository is not a Git work tree.")
    # The fingerprint is taken before any input is read: an edit during the
    # run makes the saved report stale; it never makes a stale one current.
    try:
        fingerprint, head = _inputs(repo)
    except Exception:
        fingerprint, head = None, None
    if fingerprint is None:
        return failed_report("Git could not be read.")

    _verify = import_sibling("gator-charter-verify")
    _draft = import_sibling("gator-charter-draft")
    if _verify is None or _draft is None:
        return failed_report("The charter verifier is not installed beside this script.")
    from gator_layout import get_gator_paths

    problems = []
    charter_dir = Path(resolve_charter_surface(repo)["charter_dir"])
    parsed = []
    if charter_dir.is_dir():
        _, _, _, parsed = _verify.parse_charters([(charter_dir, _rel(charter_dir, repo))])
    files = _draft.discover_files(repo, get_gator_paths(repo))

    lines = {}
    for f in files:
        try:
            lines[f] = _count_lines(repo / f)
        except OSError as exc:
            lines[f] = 0
            problems.append({"section": "code",
                             "message": _text(f"{f} could not be read: {exc.strerror or exc}")})
    index = coverage_index(files, parsed)

    items, covered_by = [], {}
    for c in parsed:
        covered = [f for f in files if c["name"] in index.get(f, ())]
        covered_by[c["name"]] = covered
        items.append({
            "name": c["name"], "path": _rel(c["file"], repo), "lines": c["line_count"],
            "documented_functions": len(c["functions"]), "covers_entries": len(c["covers"]),
            "covered_files": len(covered), "covered_lines": sum(lines[f] for f in covered),
        })
    charter_lines = sum(c["line_count"] for c in parsed)
    product_lines = sum(lines.values())
    uncovered = [f for f in files if f not in index]
    ratio = _pct(charter_lines, product_lines)

    modules = sorted(({"charter": i["name"], "files": i["covered_files"],
                       "lines": i["covered_lines"],
                       "paths": covered_by[i["name"]][:MODULE_PATHS_MAX],
                       "paths_truncated": len(covered_by[i["name"]]) > MODULE_PATHS_MAX}
                      for i in items),
                     key=lambda m: (-m["lines"], m["charter"]))
    largest = sorted(files, key=lambda f: (-lines[f], f))[:LARGEST_MAX]

    report = _base("complete")
    report.update({
        "inputs": {"fingerprint": fingerprint, "head": head,
                   "revision": head[:12] if head else None},
        "charters": {
            "count": len(parsed), "lines": charter_lines,
            "documented_functions": sum(len(c["functions"]) for c in parsed),
            "charter_dir": _rel(charter_dir, repo),
            "items": items[:ITEMS_MAX], "items_truncated": len(items) > ITEMS_MAX,
        },
        "coverage": {
            "grammar": GRAMMAR, "source_files": len(files), "covered_files": len(index),
            "uncovered_files": len(uncovered), "percent": _pct(len(index), len(files)),
            "uncovered": uncovered[:UNCOVERED_MAX],
            "uncovered_truncated": len(uncovered) > UNCOVERED_MAX,
        },
        "code": {
            "product_files": len(files), "product_lines": product_lines,
            "charter_to_code_pct": ratio, "target": dict(TARGET), "band": _band(ratio),
            "modules": modules[:ITEMS_MAX], "modules_truncated": len(modules) > ITEMS_MAX,
            "uncovered_module": {"files": len(uncovered),
                                 "lines": sum(lines[f] for f in uncovered)},
            "largest_files": [{"path": f, "lines": lines[f], "charters": list(index.get(f, []))}
                              for f in largest],
        },
        "sync": _sync_section(repo, head, problems),
        "measurement": dict(MEASUREMENT),
    })
    report["problems"] = problems[:PROBLEMS_MAX]
    if problems:
        report["status"] = "partial"
    return report


# ---------------------------------------------------------------------------
# Text output
# ---------------------------------------------------------------------------

def _n(value):
    return f"{value:,}"


def render_text(report):
    """A short human summary of a report of any status."""
    status = report.get("status")
    if status == "unavailable":
        return f"  Charter report unavailable: {report.get('reason', '')}"
    if status == "failed":
        return f"  Charter report failed: {report.get('error', '')}"
    ch, cov, code, sync = report["charters"], report["coverage"], report["code"], report["sync"]
    out = ["", "  gator charters report", ""]
    out.append(f"  Charters:   {_n(ch['count'])} ({_n(ch['lines'])} lines, "
               f"{_n(ch['documented_functions'])} documented functions)")
    pct = "n/a" if cov["percent"] is None else f"{cov['percent']}%"
    out.append(f"  Coverage:   {_n(cov['covered_files'])} of {_n(cov['source_files'])} "
               f"source files ({pct}); {_n(cov['uncovered_files'])} without a charter")
    ratio = code["charter_to_code_pct"]
    if ratio is None:
        out.append("  Size:       no source lines")
    else:
        word = {"below": "below", "within": "within", "above": "above"}[code["band"]]
        out.append(f"  Size:       charters are {ratio}% of {_n(code['product_lines'])} "
                   f"product lines ({word} the {TARGET['min']}-{TARGET['max']}% target)")
    if sync["state"] in ("current", "needs-review"):
        where = "at HEAD" if sync["at_head"] else f"at {sync['revision'] or 'no commit'}"
        out.append(f"  Last sync:  {sync['state']}, {sync['checked_at']} ({where})")
    else:
        out.append("  Last sync:  " + ("never run" if sync["state"] == "none" else "unavailable"))
    if code["largest_files"]:
        top = code["largest_files"][0]
        out.append(f"  Largest:    {top['path']} ({_n(top['lines'])} lines)")
    for p in report.get("problems", []):
        out.append(f"  ! {p['section']}: {p['message']}")
    out.append("")
    return "\n".join(out)
