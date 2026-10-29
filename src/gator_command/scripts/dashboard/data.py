"""Data collection and transformation for the dashboard.

Handles registry loading, standalone data collection, repo path
resolution, search, history, and repo key injection.
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from dashboard.helpers import run_json, run_text, git_run, run_override_cli

from gator_core import (
    import_sibling,
    normalize_path, git,
)


# ── discovery roots ───────────────────────────────────────────────────────────

# Default home-relative directories to scan for local Git repositories when
# the "Add Repository" modal fetches auto-discovery candidates.
DEFAULT_DISCOVERY_ROOTS = ("code", "code2", "projects", "repos", "src", "dev")


def resolve_discovery_roots():
    """Return the list of directory paths to scan for local Git repositories.

    Resolution order:
    1. `GATOR_DASHBOARD_DISCOVERY_ROOTS` environment variable, if set and
       non-empty — a list of paths separated by the OS path separator
       (`:` on Unix, `;` on Windows). Tilde is expanded per entry.
    2. Default home-relative set: `~/code`, `~/code2`, `~/projects`,
       `~/repos`, `~/src`, `~/dev`.

    Only returns paths that exist as directories — non-existent entries
    are filtered out silently. Env-var override is exclusive: when set,
    the defaults are NOT unioned in.

    The env-var override exists so the Dashboard can be pointed at an
    isolated fleet for screenshot capture, demo sessions, or repos
    organized outside the default home-relative layout (e.g. `~/work`,
    `/mnt/repos`).
    """
    env_roots = os.environ.get("GATOR_DASHBOARD_DISCOVERY_ROOTS", "").strip()
    if env_roots:
        candidates = [
            Path(p.strip()).expanduser()
            for p in env_roots.split(os.pathsep)
            if p.strip()
        ]
    else:
        home = Path.home()
        candidates = [home / name for name in DEFAULT_DISCOVERY_ROOTS]
    return [c for c in candidates if c.is_dir()]


# ── registry ──────────────────────────────────────────────────────────────────

def load_registry_repos(command_post_root):
    """Load repo list from machine-local dashboard registry.

    Args:
        command_post_root: Unused (kept for call-site compatibility).
    """
    try:
        from gator_core import read_dashboard_registry
        repos = read_dashboard_registry()
    except ImportError:
        repos = []
    # Normalize MSYS-style paths (/c/Users/...) to Windows-native
    for r in repos:
        raw = r.get("path", "")
        if raw:
            r["path"] = normalize_path(raw)
    return repos


# ── repo path resolution ─────────────────────────────────────────────────────

def resolve_repo_path(repo_name, registry_repos):
    """Resolve a repo name to its absolute path from the registry.

    Returns a normalized path (Windows-native on Windows) so Path.is_dir()
    works correctly. Registry may contain MSYS-style /c/ paths.
    """
    for r in registry_repos:
        if r.get("name") == repo_name:
            raw = r.get("path", "")
            return normalize_path(raw) if raw else ""
    return ""


# ── git history ───────────────────────────────────────────────────────────────

HISTORY_LIMIT_MAX = 200


def _parse_trailer_lines(text):
    """Parse git's `%(trailers:only,unfold)` output into [(key, value)]."""
    pairs = []
    for line in (text or "").splitlines():
        key, sep, value = line.partition(":")
        if sep and key and key == key.strip() and " " not in key:
            pairs.append((key, value.strip()))
    return pairs


def _split_description(body, trailer_pairs):
    """Return the body without its trailing trailer block.

    Only the final paragraph is removed, and only when every line in it
    (after unfolding continuation lines) is one of the trailers Git itself
    parsed. A prose `Key: value` line is therefore never dropped.
    """
    body = (body or "").strip()
    if not body or not trailer_pairs:
        return body
    paragraphs = [p for p in body.split("\n\n")]
    last = paragraphs[-1]
    unfolded = []
    for line in last.splitlines():
        if line[:1] in (" ", "\t") and unfolded:
            unfolded[-1] += " " + line.strip()
        else:
            unfolded.append(line)
    known = {" ".join(f"{k}: {v}".split()) for k, v in trailer_pairs}
    if unfolded and all(" ".join(l.split()) in known for l in unfolded):
        return "\n\n".join(paragraphs[:-1]).strip()
    return body


def get_repo_history(repo_path, limit=20):
    """Get recent commit history from a repo via git log.

    Returns list of commit dicts with hash, short_hash, date, author,
    subject, body, description (body without its trailer block), trailers
    (every Gator-* pair, in order), agent and architect.
    Pure git — no session dependency.
    """
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, HISTORY_LIMIT_MAX))
    fmt = ("%H%x00%h%x00%aI%x00%an%x00%s%x00%b%x00%(trailers:key=Gator-Agent)"
           "%x00%(trailers:key=Gator-Architect)%x00%(trailers:only,unfold)%x01")
    out, ok = git(
        "log", f"--max-count={limit}", f"--format={fmt}",
        cwd=repo_path,
    )
    if not ok or not out:
        return []

    commits = []
    for record in out.split("\x01"):
        record = record.strip()
        if not record:
            continue
        parts = record.split("\x00")
        if len(parts) < 6:
            continue
        pairs = _parse_trailer_lines(parts[8]) if len(parts) > 8 else []
        trailers = [{"key": k, "value": v} for k, v in pairs if k.startswith("Gator-")]
        architect = parts[7].strip().replace("Gator-Architect: ", "") if len(parts) > 7 else ""
        if not architect:
            # Legacy commits name the Architect as Gator-PI.
            architect = next((v for k, v in pairs if k == "Gator-PI"), "")
        commits.append({
            "hash": parts[0],
            "short_hash": parts[1],
            "date": parts[2],
            "author": parts[3],
            "subject": parts[4],
            "body": parts[5].strip(),
            "description": _split_description(parts[5], pairs),
            "trailers": trailers,
            "agent": parts[6].strip().replace("Gator-Agent: ", "") if len(parts) > 6 else "",
            "architect": architect,
        })
    return commits


# ── audit sessions ────────────────────────────────────────────────────────────

def resolve_audit_sessions(repo_hash=None, fleet=False, refresh=False,
                           registry_repos=None):
    """Resolve and return session summaries for the audit endpoint.

    Returns {"data": ..., "status": ...} dict. Testable without HTTP.
    """
    try:
        aggregator = import_sibling("gator-session-aggregator")
    except Exception as exc:
        return {"data": {"error": f"aggregator not available: {exc}"}, "status": 500}

    if fleet:
        summaries = aggregator.get_fleet_summaries(force_refresh=refresh)
        return {"data": summaries, "status": 200}

    if repo_hash:
        repo_path = None
        for r in (registry_repos or []):
            raw = r.get("path", "")
            resolved = normalize_path(raw) if raw else ""
            if resolved and aggregator.session_cache_key(resolved) == repo_hash:
                repo_path = resolved
                break
        if not repo_path:
            return {"data": {"error": f"repo not found for key: {repo_hash}"}, "status": 404}
        summaries = aggregator.get_session_summaries(repo_path, force_refresh=refresh)
        return {"data": summaries, "status": 200}

    summaries = aggregator.get_fleet_summaries(force_refresh=refresh)
    return {"data": summaries, "status": 200}


# ── repo update ───────────────────────────────────────────────────────────────

def resolve_repo_update(repo_name, registry_repos=None, fleet_data=None,
                        run_text_fn=None):
    """Resolve a repo update request and run gator-update against it.

    Returns {"data": ..., "status": ...} dict. Testable without HTTP.
    Pre-checks that the repo path exists and contains a .gator/ dir —
    ungatorized repos get HTTP 400 pointing at the Gatorize button.
    """
    if not repo_name:
        return {"data": {"error": "repo name required"}, "status": 400}

    repo_path = resolve_repo_path(repo_name, registry_repos or [])
    if not repo_path:
        repos = (fleet_data or {}).get("repos", [])
        repo = next((r for r in repos if r.get("name") == repo_name), None)
        if not repo:
            return {"data": {"error": f"repo '{repo_name}' not found"}, "status": 404}
        if not repo.get("accessible"):
            return {"data": {"error": "repo not accessible locally"}, "status": 400}
        repo_path = normalize_path(repo.get("path", ""))

    if not repo_path or not Path(repo_path).is_dir():
        return {"data": {"error": "repo path not accessible"}, "status": 400}

    if not (Path(repo_path) / ".gator").is_dir():
        return {
            "data": {"error": "not gatorized — use Gatorize button (Fleet row) instead of Update"},
            "status": 400,
        }

    runner = run_text_fn or run_text
    stdout, stderr, exit_code = runner(
        "gator-update", "--path", repo_path, timeout=60,
    )
    return {
        "data": {
            "status": "ok" if exit_code == 0 else "error",
            "output": stdout or stderr,
            "exit_code": exit_code,
        },
        "status": 200,
    }


# ── repo gatorize (Stage 3 fold-in of retire-gator-install plan) ──────────────

def resolve_repo_gatorize(repo_name, registry_repos=None, fleet_data=None,
                          run_text_fn=None):
    """Resolve a repo gatorize request and run `gator gatorize --yes` against it.

    Returns {"status": ..., "data": ...} dict. Testable without HTTP.
    Called when the Fleet-row 'Gatorize' button POSTs to
    /api/repo/<name>/gatorize on an ungoverned repo. Unlike resolve_repo_update,
    this endpoint EXPECTS the target repo to have no .gator/ dir yet — it's
    the install path, not the refresh path. Runs non-interactively via --yes
    because the Dashboard cannot answer prompts.
    """
    if not repo_name:
        return {"data": {"error": "repo name required"}, "status": 400}

    repo_path = resolve_repo_path(repo_name, registry_repos or [])
    if not repo_path:
        repos = (fleet_data or {}).get("repos", [])
        repo = next((r for r in repos if r.get("name") == repo_name), None)
        if not repo:
            return {"data": {"error": f"repo '{repo_name}' not found"}, "status": 404}
        if not repo.get("accessible"):
            return {"data": {"error": "repo not accessible locally"}, "status": 400}
        repo_path = normalize_path(repo.get("path", ""))

    if not repo_path or not Path(repo_path).is_dir():
        return {"data": {"error": "repo path not accessible"}, "status": 400}

    # If already gatorized, deflect to the update endpoint — no need to re-run
    # the installer against an already-governed repo.
    if (Path(repo_path) / ".gator").is_dir():
        return {
            "data": {"error": "already gatorized — use Update button instead"},
            "status": 400,
        }

    runner = run_text_fn or run_text
    stdout, stderr, exit_code = runner(
        "gatorize", "--yes", repo_path, timeout=120,
    )
    return {
        "data": {
            "status": "ok" if exit_code == 0 else "error",
            "output": stdout or stderr,
            "exit_code": exit_code,
        },
        "status": 200,
    }


# ── blocked-commit override relay (#76) ───────────────────────────────────────
#
# The Dashboard relays the repository's own override CLI
# (`gator hook override ... --json`, via helpers.run_override_cli) and
# serves only an allowlisted projection of its answer. It never reads the
# Git-private override state, never imports repository modules, and never
# decides approvability: the CLI's refusal sequence does.

OVERRIDE_STATUS_SCHEMA = "gator-override-status-v1"
OVERRIDE_APPROVE_SCHEMA = "gator-override-approve-v1"
OVERRIDE_CANCEL_SCHEMA = "gator-override-cancel-v1"
_OVERRIDE_STATES = frozenset({
    "none", "blocked", "approved", "stale", "expired", "malformed", "legacy",
    "unavailable",
})
_OVERRIDE_RESOLUTIONS = frozenset({"external-approval", "pause", "fix-required"})
_OVERRIDE_REFUSALS = frozenset({
    "no-block", "malformed", "block-changed", "findings-changed", "unavailable",
    "tree-changed", "expired", "legacy", "nothing-approvable", "too-recent",
    "invalid-input", "write-failed", "too-many-findings",
})
_OVERRIDE_TEXT_MAX = 2000
_OVERRIDE_FILES_MAX = 500
_OVERRIDE_FINDINGS_MAX = 200
_OVERRIDE_NAME_MAX = 80
_OVERRIDE_REASON_MAX = 200
_BLOCK_ID_RE = re.compile(r"^[0-9a-f]{8}$")
_REVISION_RE = re.compile(r"^[0-9a-f]{16}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_OVERRIDE_TRUNCATED = " … (truncated; see `gator hook override status`)"
OVERRIDE_INCOMPLETE_MESSAGE = (
    "This blocked commit has {total} findings, more than the Dashboard can "
    "show in full, so it cannot be approved here. Review and approve it with "
    "`gator hook override status` and `gator hook override approve` in a "
    "terminal, or discard it.")
OVERRIDE_UNSUPPORTED_MESSAGE = (
    "This repository's Gator runtime cannot report blocked commits to the "
    "Dashboard. Run `gator update` in the repository, or use "
    "`gator hook override status` in a terminal.")


def _ov_text(value, cap=_OVERRIDE_TEXT_MAX):
    return value[:cap] if isinstance(value, str) else None


def _ov_num(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _ov_list(value, cap):
    if not isinstance(value, list):
        return []
    return [v[:_OVERRIDE_TEXT_MAX] for v in value[:cap] if isinstance(v, str)]


def _ov_parse(stdout, schema):
    try:
        obj = json.loads((stdout or "").strip())
    except ValueError:
        return None
    if not isinstance(obj, dict) or obj.get("schema") != schema:
        return None
    return obj


def shape_override_status(stdout, stderr, exit_code):
    """Allowlisted gator-override-status-v1 projection of the CLI's output.

    Exit 0 with no stdout is a dispatcher skip (ungoverned branch, no
    runtime): ``state: ungoverned``. Output that is not one status object
    (an older runtime's argparse exit 2, text, another schema) is
    ``state: unsupported``. Human CLI text is never parsed.
    """
    if exit_code == 0 and not (stdout or "").strip():
        return {"schema": OVERRIDE_STATUS_SCHEMA, "state": "ungoverned"}
    obj = _ov_parse(stdout, OVERRIDE_STATUS_SCHEMA)
    if obj is None or obj.get("state") not in _OVERRIDE_STATES:
        return {"schema": OVERRIDE_STATUS_SCHEMA, "state": "unsupported",
                "message": OVERRIDE_UNSUPPORTED_MESSAGE,
                "command": "gator hook override status"}
    block = obj.get("block")
    block_view = None
    if isinstance(block, dict) and _ov_text(block.get("block_id")):
        block_view = {
            "block_id": _ov_text(block.get("block_id"), 64),
            "created_at": _ov_text(block.get("created_at"), 64),
            "created_epoch": _ov_num(block.get("created_epoch")),
            "expires_at": _ov_text(block.get("expires_at"), 64),
            "expires_epoch": _ov_num(block.get("expires_epoch")),
            "age_seconds": _ov_num(block.get("age_seconds")),
            "tree_matches": block.get("tree_matches") is True,
            "files": _ov_list(block.get("files"), _OVERRIDE_FILES_MAX),
            "files_total": (len(block["files"]) if isinstance(block.get("files"), list)
                            else 0),
        }
    findings = []
    raw_findings = obj.get("findings") if isinstance(obj.get("findings"), list) else []
    # Every finding must reach the Architect before anything is approvable:
    # if any finding is over the cap or cannot be represented, the status
    # becomes the read-only `incomplete` state below (never silently cut).
    complete = len(raw_findings) <= _OVERRIDE_FINDINGS_MAX
    for f in raw_findings[:_OVERRIDE_FINDINGS_MAX]:
        if (not isinstance(f, dict) or not _ov_text(f.get("rule"))
                or f.get("resolution") not in _OVERRIDE_RESOLUTIONS):
            complete = False
            continue
        message = f.get("message") if isinstance(f.get("message"), str) else ""
        if len(message) > _OVERRIDE_TEXT_MAX:
            message = message[:_OVERRIDE_TEXT_MAX] + _OVERRIDE_TRUNCATED
        findings.append({
            "rule": _ov_text(f.get("rule"), 120),
            "resolution": f["resolution"],
            "message": message,
            "covered": f.get("covered") is True,
            "legacy": f.get("legacy") is True,
        })
    approval = obj.get("approval") if isinstance(obj.get("approval"), dict) else {}
    approval_view = {
        "state": _ov_text(approval.get("state"), 32),
        "detail": _ov_text(approval.get("detail")),
        "approval_id": _ov_text(approval.get("approval_id"), 64),
        "approved_by": _ov_text(approval.get("approved_by"), _OVERRIDE_NAME_MAX),
        "approved_at": _ov_text(approval.get("approved_at"), 64),
        "approved_rules": _ov_list(approval.get("approved_rules"), _OVERRIDE_FINDINGS_MAX),
    }
    revision = obj.get("revision")
    refusal = obj.get("approve_refusal")
    wait = _ov_num(obj.get("approve_wait_seconds"))
    delay = _ov_num(obj.get("min_approval_delay_seconds"))
    shaped = {
        "schema": OVERRIDE_STATUS_SCHEMA,
        "state": obj["state"],
        "revision": revision if isinstance(revision, str) and _REVISION_RE.match(revision) else None,
        "malformed": [m for m in _ov_list(obj.get("malformed"), 2) if m in ("block", "approval")],
        "block": block_view,
        "findings": findings,
        "approval": approval_view,
        "approvable_rules": _ov_list(obj.get("approvable_rules"), _OVERRIDE_FINDINGS_MAX),
        "covered_rules": _ov_list(obj.get("covered_rules"), _OVERRIDE_FINDINGS_MAX),
        "uncovered_external_rules": _ov_list(obj.get("uncovered_external_rules"),
                                             _OVERRIDE_FINDINGS_MAX),
        "can_approve": obj.get("can_approve") is True,
        "approve_refusal": refusal if refusal in _OVERRIDE_REFUSALS else None,
        "approve_wait_seconds": max(0, min(int(wait), 3600)) if wait is not None else 0,
        "min_approval_delay_seconds": int(delay) if delay is not None else None,
        "architect_default": _ov_text(obj.get("architect_default"), _OVERRIDE_NAME_MAX),
    }
    if obj["state"] == "unavailable":
        shaped["message"] = _ov_text(obj.get("message")) or ""
    if not complete and obj["state"] in ("blocked", "approved"):
        # A transport limit, not a policy decision: nothing is approvable
        # from the Dashboard, and the terminal shows every finding.
        shaped.update({
            "state": "incomplete",
            "findings_total": len(raw_findings),
            "can_approve": False,
            "approve_refusal": "too-many-findings",
            "uncovered_external_rules": [],
            "message": OVERRIDE_INCOMPLETE_MESSAGE.format(total=len(raw_findings)),
            "command": "gator hook override status",
        })
    return shaped


def shape_override_result(stdout, stderr, exit_code, action):
    """(data, http_status) for an approve/cancel CLI answer.

    200 on success; 409 on a CLI refusal, an unsupported runtime or a
    dispatcher skip (each with a ``refusal`` code and ``message``).
    """
    schema = OVERRIDE_APPROVE_SCHEMA if action == "approve" else OVERRIDE_CANCEL_SCHEMA
    command = f"gator hook override {action}"
    if exit_code == 0 and not (stdout or "").strip():
        return ({"ok": False, "refusal": "unavailable", "command": command,
                 "message": "Gator did not run for this repository; the current "
                            "branch may not be governed."}, 409)
    obj = _ov_parse(stdout, schema)
    if obj is None:
        return ({"ok": False, "refusal": "unsupported-runtime", "command": command,
                 "message": OVERRIDE_UNSUPPORTED_MESSAGE}, 409)
    remaining = obj.get("remaining") if isinstance(obj.get("remaining"), dict) else {}
    data = {
        "ok": obj.get("ok") is True,
        "message": _ov_text(obj.get("message")) or "",
        "remaining": {
            "fix_required": _ov_list(remaining.get("fix_required"), _OVERRIDE_FINDINGS_MAX),
            "paused": _ov_list(remaining.get("paused"), _OVERRIDE_FINDINGS_MAX),
        },
    }
    if data["ok"]:
        if action == "approve" and isinstance(obj.get("approval"), dict):
            a = obj["approval"]
            data["approval"] = {
                "approval_id": _ov_text(a.get("approval_id"), 64),
                "block_id": _ov_text(a.get("block_id"), 64),
                "approved_rules": _ov_list(a.get("approved_rules"), _OVERRIDE_FINDINGS_MAX),
                "approved_by": _ov_text(a.get("approved_by"), _OVERRIDE_NAME_MAX),
                "expires_at": _ov_text(a.get("expires_at"), 64),
            }
        if action == "cancel":
            data["removed"] = _ov_list(obj.get("removed"), 10)
        return data, 200
    refusal = obj.get("refusal")
    data["refusal"] = refusal if refusal in _OVERRIDE_REFUSALS else "refused"
    retry = _ov_num(obj.get("retry_after_seconds"))
    data["retry_after_seconds"] = int(retry) if retry is not None else None
    return data, 409


def override_cli_args(action, body):
    """(argv, error) for an approve/cancel POST body. Validates before any
    subprocess; request text only ever becomes separate argv values."""
    if not isinstance(body, dict):
        return None, "request body must be a JSON object"
    revision = body.get("revision")
    if not isinstance(revision, str) or not _REVISION_RE.match(revision):
        return None, "revision must be 16 lowercase hex characters"
    block_id = body.get("block_id")
    if block_id is None and action == "cancel":
        args = ["cancel", "--json", "--expect-revision", revision]
        return args, None
    if not isinstance(block_id, str) or not _BLOCK_ID_RE.match(block_id):
        return None, "block_id must be 8 lowercase hex characters"
    args = [action, "--json", "--expect-block", block_id, "--expect-revision", revision]
    if action == "cancel":
        return args, None
    fields = {}
    for key, cap in (("name", _OVERRIDE_NAME_MAX), ("reason", _OVERRIDE_REASON_MAX)):
        value = body.get(key)
        if not isinstance(value, str) or not value.strip():
            return None, f"{key} is required"
        value = value.strip()
        if len(value) > cap:
            return None, f"{key} is limited to {cap} characters"
        if _CONTROL_RE.search(value):
            return None, f"{key} must not contain control characters"
        fields[key] = value
    return args + ["--name", fields["name"], "--reason", fields["reason"]], None


def resolve_repo_override(action, repo_path, body=None, run_fn=None):
    """Run one override action for a resolved repository path.

    ``action`` is "status", "approve" or "cancel". Returns
    {"data": ..., "status": ...}. Testable without HTTP (inject run_fn).
    """
    runner = run_fn or run_override_cli
    if action == "status":
        return {"data": shape_override_status(*runner(repo_path, "status", "--json")),
                "status": 200}
    args, error = override_cli_args(action, body)
    if error:
        return {"data": {"error": error}, "status": 400}
    if action == "approve":
        # Enforce the incomplete-findings rule on the server too, so a
        # direct POST cannot approve findings the Dashboard never showed.
        current = shape_override_status(*runner(repo_path, "status", "--json"))
        if current.get("state") == "incomplete":
            return {"data": {"ok": False, "refusal": "too-many-findings",
                             "message": current["message"],
                             "command": "gator hook override approve",
                             "retry_after_seconds": None,
                             "remaining": {"fix_required": [], "paused": []}},
                    "status": 409}
    data, status = shape_override_result(*runner(repo_path, *args), action)
    return {"data": data, "status": status}


# ── data injection ────────────────────────────────────────────────────────────

def inject_repo_keys(fast_data):
    """Add repo_key (path-hash) to each fleet repo entry for session identity."""
    try:
        agg = import_sibling("gator-session-aggregator")
    except Exception:
        return fast_data
    fleet = fast_data.get("fleet") or {}
    repos = fleet.get("repos") or fast_data.get("repos") or []
    for r in repos:
        if r.get("repo_key"):
            continue
        raw = r.get("path", "")
        resolved = normalize_path(raw) if raw else ""
        r["repo_key"] = agg.session_cache_key(resolved) if resolved else ""
    return fast_data


# ── search ────────────────────────────────────────────────────────────────────

def parse_search_query(query):
    """Parse a search query with AND/OR boolean operators.

    Returns (mode, terms) where mode is "and", "or", or "phrase".
    """
    and_parts = re.split(r'\s+AND\s+', query, flags=re.IGNORECASE)
    if len(and_parts) > 1:
        terms = [t.strip().lower() for t in and_parts if t.strip()]
        return ("and", terms)
    or_parts = re.split(r'\s+OR\s+', query, flags=re.IGNORECASE)
    if len(or_parts) > 1:
        terms = [t.strip().lower() for t in or_parts if t.strip()]
        return ("or", terms)
    return ("phrase", [query.lower()])


# Search scope: governance documents only, narrower than listing.
SEARCH_NAMESPACES = (".gator", "gator-command")
SEARCH_EXTS = (".md", ".json")


def search_documents(candidates, query, max_results=50):
    """Search authorized governance documents for a query string.

    `candidates` are objects with `namespace_root`, `disk_rel`,
    `logical` and `target` (the server's live-candidate seam provides
    them); this function never discovers paths itself. It keeps the
    ones in SEARCH_NAMESPACES with a SEARCH_EXTS suffix (case-folded),
    reads them in namespace -> extension -> path order, and stops after
    `max_results` matches. An unreadable candidate is skipped silently.

    Supports boolean operators: AND (all terms), OR (any term), or plain phrase.
    Returns list of {path, snippet, match_count} dicts.
    """
    mode, terms = parse_search_query(query)
    results = []

    ordered = []
    for c in candidates:
        if c.namespace_root not in SEARCH_NAMESPACES:
            continue
        ext = os.path.splitext(c.disk_rel)[1].casefold()
        if ext not in SEARCH_EXTS:
            continue
        key = (SEARCH_NAMESPACES.index(c.namespace_root),
               SEARCH_EXTS.index(ext),
               tuple(os.path.normcase(s) for s in c.disk_rel.split("/")))
        ordered.append((key, c))
    ordered.sort(key=lambda kc: kc[0])

    for _, c in ordered:
        if len(results) >= max_results:
            break
        try:
            content = c.target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lower_content = content.lower()

        if mode == "and":
            if not all(t in lower_content for t in terms):
                continue
        elif mode == "or":
            if not any(t in lower_content for t in terms):
                continue
        else:
            if terms[0] not in lower_content:
                continue

        match_count = 0
        first_idx = len(content)
        for t in terms:
            match_count += lower_content.count(t)
            idx = lower_content.find(t)
            if 0 <= idx < first_idx:
                first_idx = idx

        start = max(0, first_idx - 60)
        end = min(len(content), first_idx + 80)
        snippet = content[start:end].replace("\n", " ")
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."

        results.append({
            "path": c.logical,
            "snippet": snippet,
            "match_count": match_count,
        })

    results.sort(key=lambda r: r["match_count"], reverse=True)
    return results[:max_results]


# ── data collection ───────────────────────────────────────────────────────────

def collect_standalone_data(registry_repos):
    """Standalone startup: per-repo governance data from gator-repo-status."""
    repos = []
    for r in registry_repos:
        repo_path = r.get("path", "")
        accessible = bool(repo_path and Path(repo_path).is_dir())
        repo_key = ""
        if accessible:
            try:
                agg = import_sibling("gator-session-aggregator")
                repo_key = agg.session_cache_key(repo_path)
            except Exception:
                pass
        repo_data = {
            "name": r.get("name", ""),
            "path": repo_path,
            "repo_key": repo_key,
            "remote": r.get("remote", ""),
            "registered": r.get("registered", r.get("added_at", "")),
            "status": r.get("status", "current"),
            "accessible": accessible,
            "gatorized": (Path(repo_path) / ".gator").is_dir() if repo_path else False,
        }
        if accessible:
            status = run_json("gator-repo-status", "--path", repo_path, timeout=15)
            if status and not status.get("error"):
                repo_data.update({
                    "branch": status.get("branch", ""),
                    "charters": status.get("charter_count", 0),
                    "charter_coverage_pct": status.get("charter_coverage_pct", 0),
                    "hook_status": status.get("hook_status", "unknown"),
                    "config": status.get("config", {}),
                    "enterprise_managed": bool(status.get("enterprise_managed", False)),
                    # Machine-local level for this clone; strict when absent.
                    "commit_policy": status.get("commit_policy") or "strict",
                    "topology": status.get("topology", "standalone"),
                    "last_governed_commit": status.get("last_governed_commit"),
                    "session_summary_count": status.get("session_summary_count", 0),
                    "override_events": status.get("override_events", []),
                    "cli_version": status.get("cli_version", ""),
                })
            elif status and status.get("error"):
                repo_data["status_error"] = status["error"]
        repos.append(repo_data)
    # Resolve current CLI version for frontend version comparison
    cli_ver = ""
    try:
        from gator_core import get_version
        cli_ver = get_version()
    except ImportError:
        pass

    return {
        "standalone": True,
        "generated_at": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gator_cli_version": cli_ver,
        "repos": repos,
    }
