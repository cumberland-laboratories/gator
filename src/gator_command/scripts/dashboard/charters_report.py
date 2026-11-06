"""Dashboard relay for the charter health report (`gator-charters-report-v1`).

`refresh_report()` runs `gator charters report --json`, keeps only the
allowlisted, bounded fields, and records the result for this checkout in
Git's private area. `read_report()` serves that record together with its
freshness: `current` when the record's input fingerprint equals the working
tree's, `stale` when it differs, `unknown` when it cannot be computed.

The record is a display cache, never tracked and never served as content.
It is untrusted input: every read re-validates it through `sanitize()`.

Imports only `dashboard.helpers`, `dashboard.charter_sync` (its record
patterns), `charter_report` (the fingerprint), and the standard library. It
never imports `gator-dashboard.py`.
"""

import json
import os
import re
from pathlib import Path

from dashboard.helpers import git_run, run_json
from dashboard.charter_sync import ARTIFACT_PATH_RE, _CHECKED_AT_RE, _REVISION_RE

SCHEMA = "gator-charters-report-v1"
RECORD_NAME = "gator-charters-report.json"
RECORD_MAX_BYTES = 512 * 1024
REPORT_TIMEOUT = 60
TEXT_MAX = 300
COUNT_MAX = 10 ** 9
PCT_MAX = 10 ** 6
ITEMS_MAX = 200
UNCOVERED_MAX = 50
LARGEST_MAX = 10
MODULE_PATHS_MAX = 50
PROBLEMS_MAX = 20

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEAD = re.compile(r"^[0-9a-f]{40,64}$")
_REV12 = re.compile(r"^[0-9a-f]{12}$")
_DRIVE = re.compile(r"^[A-Za-z]:")
_SECTIONS = ("charters", "coverage", "code", "sync")
_BANDS = ("below", "within", "above")
_SYNC_STATES = ("current", "needs-review", "none", "unavailable")
_MEASUREMENT_KEYS = ("source_files", "lines", "coverage", "modules", "sync")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def read_report(repo_path):
    """`(body, status)` for GET: the record and its freshness, or a state."""
    repo = Path(repo_path)
    if not repo.is_dir() or not (repo / ".gator").is_dir():
        return _unavailable("This repository is not accessible or not gatorized."), 200
    report = _read_record(repo)
    if report is None:
        return {"state": "none"}, 200
    return {"state": "report", "freshness": _freshness(repo, report), "report": report}, 200


def refresh_report(repo_path, run_fn=None):
    """`(body, status)` for POST: run the producer once and record the result.

    A failure of any kind returns 500 `{state: "failed", error}` and leaves
    the previous record untouched.
    """
    repo = Path(repo_path)
    if not repo.is_dir() or not (repo / ".gator").is_dir():
        return _unavailable("This repository is not accessible or not gatorized."), 200
    run_fn = run_fn or (lambda r: run_json(
        "gator-charters", "report", "--path", str(r), timeout=REPORT_TIMEOUT))
    data = run_fn(repo)
    if not isinstance(data, dict):
        return _failed("the charter report returned no result")
    if data.get("schema") == SCHEMA and data.get("status") == "unavailable":
        return _unavailable(data.get("reason") or "The charter report is unavailable."), 200
    if data.get("schema") == SCHEMA and data.get("status") == "failed":
        return _failed(f"charter report failed: {data.get('error') or 'unknown error'}")
    if data.get("error") and "schema" not in data:
        return _failed(f"charter report failed: {data['error']}")
    report = sanitize(data)
    if report is None:
        return _failed("the charter report did not validate")
    persisted = _write_record(repo, report)
    return {"state": "report", "freshness": _freshness(repo, report),
            "report": report, "persisted": persisted}, 200


# ---------------------------------------------------------------------------
# Freshness and the Git-private record
# ---------------------------------------------------------------------------

def _freshness(repo, report):
    try:
        from charter_report import input_fingerprint
        now = input_fingerprint(repo)
    except Exception:
        now = None
    if now is None:
        return "unknown"
    return "current" if now == report["inputs"]["fingerprint"] else "stale"


def _record_path(repo):
    out, ok = git_run("rev-parse", "--git-path", RECORD_NAME, cwd=str(repo))
    if not ok or not out.strip():
        return None
    path = Path(out.strip())
    return path if path.is_absolute() else repo / path


def _read_record(repo):
    path = _record_path(repo)
    if path is None:
        return None
    try:
        if not path.is_file() or path.stat().st_size > RECORD_MAX_BYTES:
            return None
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return sanitize(obj)


def _write_record(repo, report):
    path = _record_path(repo)
    if path is None:
        return False
    tmp = path.with_name(f".{RECORD_NAME}.tmp-{os.getpid()}")
    try:
        tmp.write_text(json.dumps(report, indent=2), encoding="utf-8")
        os.replace(tmp, path)
        return True
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        return False


def _unavailable(message):
    return {"state": "unavailable", "message": _clip(message)}


def _failed(message):
    return {"state": "failed", "error": _clip(message) or "charter report failed"}, 500


def _clip(value):
    return str(value)[:TEXT_MAX]


# ---------------------------------------------------------------------------
# Sanitizer: an explicit allowlist; unknown keys are dropped
# ---------------------------------------------------------------------------

class _Bad(Exception):
    pass


def _obj(value):
    if not isinstance(value, dict):
        raise _Bad
    return value


def _count(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= COUNT_MAX:
        raise _Bad
    return value


def _pct(value, nullable=True):
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= PCT_MAX:
        raise _Bad
    return value


def _flag(value):
    if not isinstance(value, bool):
        raise _Bad
    return value


def _str(value, limit=TEXT_MAX):
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value):
        raise _Bad
    return value


def _match(value, pattern, nullable=False):
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not pattern.match(value):
        raise _Bad
    return value


def _path(value):
    """A repo-relative POSIX path: no leading `/`, drive, `\\` or `..` segment."""
    value = _str(value)
    if (not value or value.startswith("/") or "\\" in value or _DRIVE.match(value)
            or ".." in value.split("/")):
        raise _Bad
    return value


def _choice(value, options, nullable=False):
    if value is None and nullable:
        return None
    if value not in options:
        raise _Bad
    return value


def _list(value, limit, item):
    if not isinstance(value, list) or len(value) > limit:
        raise _Bad
    return [item(v) for v in value]


def _charters(c):
    c = _obj(c)
    return {
        "count": _count(c["count"]), "lines": _count(c["lines"]),
        "documented_functions": _count(c["documented_functions"]),
        "charter_dir": _path(c["charter_dir"]),
        "items": _list(c["items"], ITEMS_MAX, lambda i: {
            "name": _str(_obj(i)["name"]), "path": _path(i["path"]),
            "lines": _count(i["lines"]), "documented_functions": _count(i["documented_functions"]),
            "covers_entries": _count(i["covers_entries"]),
            "covered_files": _count(i["covered_files"]), "covered_lines": _count(i["covered_lines"]),
        }),
        "items_truncated": _flag(c["items_truncated"]),
    }


def _coverage(c):
    c = _obj(c)
    return {
        "grammar": _str(c["grammar"]), "source_files": _count(c["source_files"]),
        "covered_files": _count(c["covered_files"]), "uncovered_files": _count(c["uncovered_files"]),
        "percent": _pct(c["percent"]),
        "uncovered": _list(c["uncovered"], UNCOVERED_MAX, _path),
        "uncovered_truncated": _flag(c["uncovered_truncated"]),
    }


def _module(m):
    m = _obj(m)
    # `paths` / `paths_truncated` are additive in v1: a record from before they
    # existed still sanitizes, with no paths.
    return {
        "charter": _str(m["charter"]), "files": _count(m["files"]), "lines": _count(m["lines"]),
        "paths": _list(m.get("paths", []), MODULE_PATHS_MAX, _path),
        "paths_truncated": _flag(m.get("paths_truncated", False)),
    }


def _code(c):
    c = _obj(c)
    target = _obj(c["target"])
    return {
        "product_files": _count(c["product_files"]), "product_lines": _count(c["product_lines"]),
        "charter_to_code_pct": _pct(c["charter_to_code_pct"]),
        "target": {"min": _pct(target["min"], False), "max": _pct(target["max"], False),
                   "source": _str(target["source"])},
        "band": _choice(c["band"], _BANDS, nullable=True),
        "modules": _list(c["modules"], ITEMS_MAX, _module),
        "modules_truncated": _flag(c["modules_truncated"]),
        "uncovered_module": {"files": _count(_obj(c["uncovered_module"])["files"]),
                             "lines": _count(c["uncovered_module"]["lines"])},
        "largest_files": _list(c["largest_files"], LARGEST_MAX, lambda f: {
            "path": _path(_obj(f)["path"]), "lines": _count(f["lines"]),
            "charters": _list(f["charters"], ITEMS_MAX, _str)}),
    }


def _sync(s):
    s = _obj(s)
    state = _choice(s["state"], _SYNC_STATES)
    if state not in ("current", "needs-review"):
        return {"state": state}
    counts = _obj(s["counts"])
    return {
        "state": state,
        "checked_at": _match(s["checked_at"], _CHECKED_AT_RE),
        "revision": _match(s["revision"], _REVISION_RE, nullable=True),
        "at_head": _flag(s["at_head"]),
        "counts": {k: _count(counts[k]) for k in ("current", "needs_review", "missing")},
        "findings_total": _count(s["findings_total"]),
        "artifact_path": _match(s["artifact_path"], ARTIFACT_PATH_RE),
    }


def sanitize(obj):
    """The allowlisted projection of a v1 report, or None when any check fails.

    Only `complete` and `partial` reports are records. Required fields are
    type-checked and bounded; unknown keys at any level are dropped, because a
    newer producer may add fields within v1.
    """
    try:
        obj = _obj(obj)
        if obj.get("schema") != SCHEMA:
            return None
        inputs = _obj(obj["inputs"])
        measurement = _obj(obj["measurement"])
        return {
            "schema": SCHEMA,
            "status": _choice(obj["status"], ("complete", "partial")),
            "generated_at": _match(obj["generated_at"], _CHECKED_AT_RE),
            "gator_version": _str(obj["gator_version"], 80),
            "inputs": {"fingerprint": _match(inputs["fingerprint"], _HEX64),
                       "head": _match(inputs["head"], _HEAD, nullable=True),
                       "revision": _match(inputs["revision"], _REV12, nullable=True)},
            "charters": _charters(obj["charters"]),
            "coverage": _coverage(obj["coverage"]),
            "code": _code(obj["code"]),
            "sync": _sync(obj["sync"]),
            "measurement": {k: _str(measurement[k]) for k in _MEASUREMENT_KEYS if k in measurement},
            "problems": _list(obj["problems"], PROBLEMS_MAX, lambda p: {
                "section": _choice(_obj(p)["section"], _SECTIONS), "message": _str(p["message"])}),
        }
    except (_Bad, KeyError, TypeError):
        return None
