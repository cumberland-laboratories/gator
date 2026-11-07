"""Dashboard charter sync check: one mechanical charter-to-code report.

`run_sync()` runs the existing charter verifier, adds a bounded
recent-commit coverage signal, rolls both up into the page summary, writes
one Markdown report with a repair sketch to `.gator/artifacts/`, and records
the sanitized summary for this checkout in Git's private area. It never
edits a charter, source file, Git history or commit message.

`read_last()` returns the recorded summary, re-validated field by field, or
None. The report is the evidence; the record is only a display cache.

Imports only `dashboard.helpers`, `charter_covers`, `gator_core`,
`gator_layout` and the standard library. It never imports `gator-dashboard.py`.
"""

import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path

from dashboard.helpers import git_run, run_json
# The shared Covers grammar (#88); `covers_match` stays a module-level name.
from charter_covers import covers_match

VERIFY_TIMEOUT = 60
COMMIT_LIMIT = 20
RECORD_NAME = "gator-charter-sync.json"
RECORD_SCHEMA = "gator-charter-sync-v1"
RECORD_MAX_BYTES = 64 * 1024
GROUPS_MAX = 50
TEXT_MAX = 300
COUNT_MAX = 10 ** 6

ARTIFACT_PATH_RE = re.compile(
    r"^\.gator/artifacts/\d{4}-\d{2}-\d{2}-charter-sync-report[-0-9A-Z]*\.md$")
_CHECKED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_REVISION_RE = re.compile(r"^[0-9a-f]{4,40}$")

# Display order: highest signal first.
KINDS = ("stale-structure", "stale-exclusion", "complexity-mismatch", "coverage-gap",
         "function-gap", "cross-cutting-suspect")
_PRIORITY = {k: i for i, k in enumerate(KINDS)}

# Shown and counted, but never alone a reason for "needs-review" (#105):
# a default function gap or an import fan-out heuristic is a review
# prompt, not drift.
ADVISORY = frozenset({"function-gap", "cross-cutting-suspect"})

# The sketch's finding-to-action table: page wording, repair guidance.
WORDING = {
    "coverage-gap": "Source file has no charter coverage.",
    "function-gap": "Public seam is not represented in its charter (advisory).",
    "complexity-mismatch": "Charter may be too thin for this module.",
    "stale-structure": "Charter names code that no longer exists.",
    "stale-exclusion": "Charter lists an internal name that no longer exists.",
    "cross-cutting-suspect": "High fan-out may need cross-cutting treatment (advisory).",
}
REPAIR = {
    "coverage-gap": "Identify the owning charter or create a new charter boundary.",
    "function-gap": ("Document the public seam or high-blast-radius helper, group related "
                     "helpers that share one boundary and invariant, or list the name on the "
                     "charter's **Internal**: line; do not add bare function lists."),
    "complexity-mismatch": ("Review public responsibilities and module boundary; "
                            "do not pad prose mechanically."),
    "stale-structure": "Update the named responsibility or restore the intended implementation.",
    "stale-exclusion": "Remove the name from the Internal line, or restore the function.",
    "cross-cutting-suspect": "Decide whether the concern belongs in a cross-cutting charter.",
}
COMMIT_WORDING = "Commit changed governed code without a charter update."
COMMIT_REPAIR = "Confirm that no charter change was needed, or revise the affected charter."

_FILE_LEVEL = ("complexity-mismatch", "cross-cutting-suspect")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_sync(repo_path, now=None, verify_fn=None):
    """Run one check. Returns `(result, http_status)`.

    A run either writes a complete report and returns the summary (200,
    `persisted` says whether the record was saved), or writes nothing and
    returns `{"state": "failed", "error": ...}` (500). An inaccessible or
    ungatorized repository returns `{"state": "unavailable", ...}` (200).
    """
    repo = Path(repo_path)
    if not repo.is_dir() or not (repo / ".gator").is_dir():
        return {"state": "unavailable",
                "message": "This repository is not accessible or not gatorized."}, 200
    now = now or datetime.now(timezone.utc)
    verify_fn = verify_fn or (lambda r: run_json(
        "gator-charter-verify", "--path", str(r), timeout=VERIFY_TIMEOUT))

    data = verify_fn(repo)
    problem = _verifier_problem(data)
    if problem:
        return _failed(problem)

    findings = data["findings"]
    charters = data.get("charters")
    if not _valid_charters(charters):
        charters = None

    # Every Git read completes (or the run fails) before anything is written.
    try:
        revision, dirty = _revision(repo)
        coverage = _commit_coverage(repo, charters, has_commits=revision is not None)
    except GitReadError as exc:
        return _failed(f"Git could not be read: {exc}")
    summary = _roll_up(findings, charters, coverage)
    summary.update({
        "schema": RECORD_SCHEMA,
        "checked_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "revision": revision,
        "dirty": dirty,
    })

    # Validate and render before publishing: a failure here writes nothing.
    names = _report_names(now)
    summary["artifact_path"] = _ARTIFACTS_REL + names[0]
    if _sanitize(summary) is None:
        return _failed("internal error: summary did not validate")
    text = _render_report(summary, findings, charters, coverage)

    try:
        artifact = _write_artifact(repo, names, text)
    except OSError as exc:
        return _failed(f"report not written: {exc}")
    summary["artifact_path"] = artifact
    clean = _sanitize(summary)
    if clean is None:  # names differ only in the suffix ARTIFACT_PATH_RE allows
        return _failed("internal error: summary did not validate")
    persisted = _write_record(repo, clean)
    result = dict(clean)
    result["persisted"] = persisted
    return result, 200


def read_last(repo_path):
    """The recorded summary for this checkout, re-validated, or None."""
    path = _record_path(Path(repo_path))
    if path is None:
        return None
    try:
        if not path.is_file() or path.stat().st_size > RECORD_MAX_BYTES:
            return None
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return _sanitize(obj)


# ---------------------------------------------------------------------------
# Verifier input
# ---------------------------------------------------------------------------

def _failed(message):
    return {"state": "failed", "error": _text(message) or "check failed"}, 500


def _verifier_problem(data):
    if not isinstance(data, dict):
        return "charter verifier returned no result"
    if data.get("error"):
        return f"charter verifier failed: {data['error']}"
    findings = data.get("findings")
    if not isinstance(findings, list):
        return "charter verifier output has no findings list"
    for f in findings:
        if not (isinstance(f, dict) and isinstance(f.get("class"), str)
                and isinstance(f.get("file"), str)):
            return "charter verifier output has a malformed finding"
    return None


def _valid_charters(charters):
    if not isinstance(charters, list):
        return False
    for c in charters:
        if not (isinstance(c, dict) and isinstance(c.get("name"), str)
                and isinstance(c.get("path"), str) and isinstance(c.get("covers"), list)
                and all(isinstance(e, str) for e in c["covers"])):
            return False
    return True


class GitReadError(Exception):
    """A Git read the check depends on failed; the run must report `failed`."""


def _revision(repo):
    """`(short revision or None, dirty)`. None means a repository with no commits.

    Only an unborn HEAD (`rev-parse --verify -q` fails with no output) is
    None. Any other Git failure raises `GitReadError`.
    """
    out, ok = git_run("rev-parse", "--is-inside-work-tree", cwd=str(repo))
    if not ok or out.strip() != "true":
        raise GitReadError(out.strip() or "not a Git work tree")
    out, ok = git_run("rev-parse", "--verify", "-q", "HEAD", cwd=str(repo))
    if ok and _REVISION_RE.match(out.strip()):
        revision = out.strip()[:12]
    elif not ok and not out.strip():
        revision = None
    else:
        raise GitReadError(out.strip() or "HEAD could not be read")
    status, ok = git_run("status", "--porcelain", "--untracked-files=no", cwd=str(repo))
    if not ok:
        raise GitReadError(status.strip() or "status could not be read")
    return revision, bool(status.strip())


# ---------------------------------------------------------------------------
# Commit coverage
# ---------------------------------------------------------------------------



def _charter_dir_rel(repo):
    try:
        from gator_core import resolve_charter_surface
        charter_dir = Path(resolve_charter_surface(repo)["charter_dir"])
        return charter_dir.resolve().relative_to(repo.resolve()).as_posix()
    except Exception:
        return None


def _commit_coverage(repo, charters, has_commits=True):
    """Examine the latest non-merge commits. A review signal, never a verdict.

    Raises `GitReadError` when the history of a repository with commits
    cannot be read. The supported partial cases carry a `reason`.
    """
    result = {"examined": 0, "without_charter_update": 0, "reason": None, "commits": []}
    if charters is None:
        result["reason"] = "This Gator version does not report charter coverage."
        return result
    if not has_commits:
        result["reason"] = "This repository has no commits yet."
        return result
    charter_rel = _charter_dir_rel(repo)
    if charter_rel is None:
        result["reason"] = "The charter directory could not be resolved."
        return result
    out, ok = git_run("-c", "core.quotepath=off", "log", "--no-merges",
                      f"-n{COMMIT_LIMIT}", "--name-only",
                      "--format=\x1e%H %h %s", cwd=str(repo))
    if not ok:
        raise GitReadError(out.strip() or "commit history could not be read")
    entries = [e for c in charters for e in c["covers"]]
    for record in out.split("\x1e"):
        lines = [ln for ln in record.splitlines() if ln.strip()]
        if not lines:
            continue
        parts = lines[0].split(" ", 2)
        short = parts[1] if len(parts) > 1 else ""
        subject = parts[2] if len(parts) > 2 else ""
        files = [ln.strip() for ln in lines[1:]]
        governed = [f for f in files if any(covers_match(f, e) for e in entries)]
        charter_updated = any(f.startswith(charter_rel + "/") for f in files)
        result["examined"] += 1
        flagged = bool(governed) and not charter_updated
        if flagged:
            result["without_charter_update"] += 1
        result["commits"].append({
            "short": short, "subject": subject, "governed": governed,
            "charter_updated": charter_updated, "flagged": flagged,
        })
    return result


# ---------------------------------------------------------------------------
# Roll-up
# ---------------------------------------------------------------------------

def _attributed_charters(finding, charters):
    if isinstance(finding.get("charter"), str):
        return [finding["charter"]]
    if finding["class"] in _FILE_LEVEL and charters:
        return [c["name"] for c in charters
                if any(covers_match(finding["file"], e) for e in c["covers"])]
    return []


def _group_findings(findings, charters):
    """Group by charter, or by source file when no charter is attributed."""
    groups = {}
    for f in findings:
        names = _attributed_charters(f, charters)
        keys = [("charter", n) for n in names] or [("file", f["file"])]
        for key in keys:
            groups.setdefault(key, []).append(f)
    return groups


def _plural(n, word):
    return f"{n} {word}{'s' if n != 1 else ''}"


def _roll_up(findings, charters, coverage):
    charter_paths = {c["name"]: c["path"] for c in (charters or [])}
    groups = _group_findings(findings, charters)
    names = set(charter_paths) | {n for (k, n) in groups if k == "charter"}
    # Only decisive findings put a charter (or the result) in needs-review.
    decisive = [f for f in findings if f["class"] not in ADVISORY]
    advisory = [f for f in findings if f["class"] in ADVISORY]
    needs_review = {n for (k, n) in _group_findings(decisive, charters) if k == "charter"}
    missing = {f["file"] for f in findings if f["class"] == "coverage-gap"}

    shown = []
    for (kind, label), items in groups.items():
        top = min((f["class"] for f in items), key=lambda c: _PRIORITY.get(c, len(KINDS)))
        shown.append({
            "kind": top if top in WORDING else "cross-cutting-suspect",
            "label": label,
            "charter_path": charter_paths.get(label) if kind == "charter" else None,
            "message": WORDING.get(top, "Charter finding."),
            "count": len(items),
        })
    shown.sort(key=lambda g: (_PRIORITY.get(g["kind"], len(KINDS)), -g["count"], g["label"]))

    flagged = coverage["without_charter_update"]
    state = "current" if not decisive and not flagged else "needs-review"
    if state == "current" and not advisory:
        headline = "Current — no structural charter-to-code findings."
    elif state == "current":
        advised = {n for (k, n) in _group_findings(advisory, charters) if k == "charter"}
        headline = (f"Current — {_plural(len(advisory), 'advisory finding')} "
                    f"in {_plural(len(advised), 'charter')}.")
    else:
        headline = (f"{_plural(len(decisive), 'finding')} "
                    f"in {_plural(len(needs_review), 'charter')}")
        if missing:
            headline += f"; {_plural(len(missing), 'source file')} without a charter"
        if advisory:
            headline += f"; {len(advisory)} advisory"
        headline += "."
    return {
        "state": state,
        "headline": headline,
        "counts": {"current": len(names) - len(needs_review),
                   "needs_review": len(needs_review), "missing": len(missing)},
        "recent_commits": {"examined": coverage["examined"],
                           "without_charter_update": flagged,
                           "reason": coverage["reason"]},
        "findings_total": len(findings),
        "groups_total": len(shown),
        "findings": shown[:GROUPS_MAX],
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _code(value):
    return "`" + str(value).replace("`", "'").replace("\n", " ") + "`"


def _render_report(summary, findings, charters, coverage):
    revision = summary["revision"] or "no commits"
    lines = [
        "---",
        f"date: {summary['checked_at'][:10]}",
        "type: charter-sync-report",
        f"revision: {revision}",
        f"state: {summary['state']}",
        "---",
        "",
        "# Charter sync report",
        "",
        "## Executive summary",
        "",
        f"- Checked revision: {_code(revision)}"
        + (" (the working tree had uncommitted changes)" if summary["dirty"] else ""),
        f"- Checked at: {summary['checked_at']}",
        f"- State: {'Current' if summary['state'] == 'current' else 'Needs review'}",
        f"- Result: {summary['headline']}",
        f"- Charters: {summary['counts']['current']} current, "
        f"{summary['counts']['needs_review']} need review; "
        f"{summary['counts']['missing']} source files without a charter.",
        "",
        "This report was generated by the Dashboard charter sync check. The check "
        "reads charters, source structure and Git history. It does not edit code, "
        "charters, Git history or commit messages. Its findings are heuristics for "
        "review, not violations.",
        "",
        "## Structural findings",
        "",
    ]
    if not findings:
        lines.append("No structural charter-to-code findings.")
    groups = _group_findings(findings, charters)
    for (kind, label), items in sorted(
            groups.items(), key=lambda kv: (kv[0][0] != "charter", kv[0][1])):
        lines.append(f"### {'Charter' if kind == 'charter' else 'Uncovered file'} {_code(label)}")
        lines.append("")
        for f in sorted(items, key=lambda f: (_PRIORITY.get(f["class"], len(KINDS)), f["file"])):
            msg = str(f.get("message", "")).replace("\n", " ")
            note = " (advisory)" if f["class"] in ADVISORY else ""
            lines.append(f"- [{f['class']}]{note} {_code(f['file'])}: {msg}")
        lines.append("")

    lines += ["## Recent commit coverage", ""]
    if coverage["reason"]:
        lines.append(coverage["reason"])
    else:
        lines.append(f"{coverage['examined']} recent non-merge commits examined; "
                     f"{coverage['without_charter_update']} changed governed code "
                     "without a charter update (charter update not observed).")
        lines.append("")
        for c in coverage["commits"]:
            note = ("charter update not observed" if c["flagged"]
                    else "charter updated" if c["charter_updated"]
                    else "no governed code changed")
            subject = c["subject"].replace("\n", " ")
            lines.append(f"- {_code(c['short'])} {subject} — {note}")
            for g in c["governed"][:20]:
                lines.append(f"  - {_code(g)}")
    lines.append("")

    lines += ["## Repair sketch", "",
              "Each step is guidance from the evidence above. Nothing has been changed.", ""]
    step = 0
    # Decisive steps first, then the advisory ones.
    for advisory_pass in (False, True):
        for (kind, label), items in sorted(
                groups.items(), key=lambda kv: (kv[0][0] != "charter", kv[0][1])):
            for cls in sorted({f["class"] for f in items},
                              key=lambda c: _PRIORITY.get(c, len(KINDS))):
                if (cls in ADVISORY) != advisory_pass:
                    continue
                step += 1
                n = sum(1 for f in items if f["class"] == cls)
                note = ", advisory" if advisory_pass else ""
                lines.append(f"{step}. {_code(label)} — {cls} ({n}{note}): "
                             f"{REPAIR.get(cls, 'Review the finding.')}")
    for c in coverage["commits"]:
        if c["flagged"]:
            step += 1
            lines.append(f"{step}. Commit {_code(c['short'])}: {COMMIT_REPAIR}")
    if step == 0:
        lines.append("No repair steps.")
    lines.append("")
    return "\n".join(lines)


def _is_link_or_reparse(path):
    try:
        st = os.stat(os.fspath(path), follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    if stat.S_ISLNK(st.st_mode):
        return True
    return bool(getattr(st, "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


_ARTIFACTS_REL = ".gator/artifacts/"


def _report_names(now):
    day = now.strftime("%Y-%m-%d")
    stamp = now.strftime("%H%M%SZ")
    names = [f"{day}-charter-sync-report.md", f"{day}-charter-sync-report-{stamp}.md"]
    return names + [f"{day}-charter-sync-report-{stamp}-{i}.md" for i in range(2, 10)]


def _write_artifact(repo, names, text):
    """Publish the rendered report under the first free name. Returns its rel path.

    Exclusive create never overwrites. A file this call created is removed
    again if writing or closing it fails, so a failed run leaves no partial
    report; a pre-existing file is never touched.
    """
    from gator_layout import get_gator_paths
    artifacts = Path(get_gator_paths(repo).artifacts_dir)
    if _is_link_or_reparse(repo / ".gator") or _is_link_or_reparse(artifacts):
        raise OSError("the artifacts directory is a link; refusing to write")
    artifacts.mkdir(exist_ok=True)
    for name in names:
        target = artifacts / name
        try:
            fh = open(target, "x", encoding="utf-8", newline="\n")
        except FileExistsError:
            continue
        try:
            with fh:
                fh.write(text)
        except BaseException:
            try:
                target.unlink()
            except OSError:
                pass
            raise
        return target.relative_to(repo).as_posix()
    raise OSError("no free report name for today")


# ---------------------------------------------------------------------------
# Git-private record
# ---------------------------------------------------------------------------

def _record_path(repo):
    out, ok = git_run("rev-parse", "--git-path", RECORD_NAME, cwd=str(repo))
    if not ok or not out.strip():
        return None
    path = Path(out.strip())
    return path if path.is_absolute() else repo / path


def _write_record(repo, summary):
    path = _record_path(repo)
    if path is None:
        return False
    tmp = path.with_name(f".{RECORD_NAME}.tmp-{os.getpid()}")
    try:
        tmp.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        os.replace(tmp, path)
        return True
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        return False


def _text(value, limit=TEXT_MAX):
    return value[:limit] if isinstance(value, str) else None


def _count(value):
    return (isinstance(value, int) and not isinstance(value, bool)
            and 0 <= value <= COUNT_MAX)


_RECORD_KEYS = {"schema", "state", "checked_at", "revision", "dirty", "headline",
                "counts", "recent_commits", "findings_total", "groups_total",
                "findings", "artifact_path"}


def _sanitize(obj):
    """Strict, field-by-field projection of a summary record, or None."""
    if not isinstance(obj, dict) or set(obj) != _RECORD_KEYS:
        return None
    if obj["schema"] != RECORD_SCHEMA or obj["state"] not in ("current", "needs-review"):
        return None
    if not (isinstance(obj["checked_at"], str) and _CHECKED_AT_RE.match(obj["checked_at"])):
        return None
    rev = obj["revision"]
    if rev is not None and not (isinstance(rev, str) and _REVISION_RE.match(rev)):
        return None
    if not isinstance(obj["dirty"], bool) or not isinstance(obj["headline"], str):
        return None
    if not (_count(obj["findings_total"]) and _count(obj["groups_total"])):
        return None
    counts = obj["counts"]
    if not (isinstance(counts, dict) and set(counts) == {"current", "needs_review", "missing"}
            and all(_count(v) for v in counts.values())):
        return None
    rc = obj["recent_commits"]
    if not (isinstance(rc, dict) and set(rc) == {"examined", "without_charter_update", "reason"}
            and _count(rc["examined"]) and _count(rc["without_charter_update"])
            and (rc["reason"] is None or isinstance(rc["reason"], str))):
        return None
    if not (isinstance(obj["artifact_path"], str)
            and ARTIFACT_PATH_RE.match(obj["artifact_path"])):
        return None
    groups = obj["findings"]
    if not (isinstance(groups, list) and len(groups) <= GROUPS_MAX):
        return None
    clean_groups = []
    for g in groups:
        if not (isinstance(g, dict)
                and set(g) == {"kind", "label", "charter_path", "message", "count"}
                and g["kind"] in KINDS and isinstance(g["label"], str)
                and isinstance(g["message"], str) and _count(g["count"])
                and (g["charter_path"] is None or isinstance(g["charter_path"], str))):
            return None
        clean_groups.append({
            "kind": g["kind"], "label": _text(g["label"]),
            "charter_path": _text(g["charter_path"]) if g["charter_path"] else None,
            "message": _text(g["message"]), "count": g["count"],
        })
    return {
        "schema": RECORD_SCHEMA,
        "state": obj["state"],
        "checked_at": obj["checked_at"],
        "revision": rev,
        "dirty": obj["dirty"],
        "headline": _text(obj["headline"]),
        "counts": dict(counts),
        "recent_commits": {"examined": rc["examined"],
                           "without_charter_update": rc["without_charter_update"],
                           "reason": _text(rc["reason"]) if rc["reason"] else None},
        "findings_total": obj["findings_total"],
        "groups_total": obj["groups_total"],
        "findings": clean_groups,
        "artifact_path": obj["artifact_path"],
    }
