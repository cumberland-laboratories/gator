#!/usr/bin/env python3
"""
gator-dashboard.py — Gator governance dashboard server.

Two-tier startup:
  Tier 1 (fast): runs gator-fleet-report, gator-drift, gator-audit at startup.
                 Feeds Fleet view and Audit view immediately.
  Tier 2 (lazy): runs gator-repo-status on demand via GET /api/repo/<name>.
                 Feeds Repo view when user clicks a repo.

Usage:
  python gator-dashboard.py [--port 8420] [--no-open] [--snapshot] [--repo <name>]

Flags:
  --port N      HTTP port (default 8420; tries 8421-8429 on conflict)
  --no-open     Skip browser open
  --snapshot    Write self-contained HTML to stdout and exit (no server)
  --repo NAME   Pre-load Repo view on open (skips Fleet, opens Repo directly)

@reads: output of sibling CLI scripts (gator-fleet-report, gator-drift, gator-audit, gator-repo-status)
@writes: nothing (--snapshot writes to stdout)
"""

import argparse
import collections
import http as _http
import json
import logging
import os
import re
import socket
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape as _html_escape
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import parse_qs, unquote

# ── paths ─────────────────────────────────────────────────────────────────────

SCRIPTS_DIR = Path(__file__).resolve().parent
DASHBOARD_DIR = SCRIPTS_DIR / "dashboard"
COMMAND_POST_ROOT = SCRIPTS_DIR.parent.parent.parent  # repo root (src/gator_command/scripts/ → repo root)

sys.path.insert(0, str(SCRIPTS_DIR))
from gator_core import get_version, import_sibling, git  # noqa: E402

# ── extracted modules ─────────────────────────────────────────────────────────
from dashboard.helpers import (  # noqa: E402
    run_json, run_text, git_run as _git_run,
)
from dashboard.updates import (  # noqa: E402
    check_for_updates, upgrade_and_restart,
    restart_server as _restart_server,
)
from dashboard.snapshot import build_snapshot  # noqa: E402
from dashboard.data import (  # noqa: E402
    load_registry_repos as _load_registry_repos,
    resolve_repo_path as _resolve_repo_path,
    get_repo_history as _get_repo_history,
    resolve_audit_sessions as _resolve_audit_sessions,
    resolve_repo_update as _resolve_repo_update,
    resolve_repo_gatorize as _resolve_repo_gatorize,
    resolve_discovery_roots as _resolve_discovery_roots,
    inject_repo_keys as _inject_repo_keys,
    parse_search_query as _parse_search_query,
    search_repo_files as _search_repo_files,
    collect_standalone_data,
)

# ── data collection: see dashboard/data.py

# Registry-based repo list (for path resolution)
_REGISTRY_REPOS = []

# ── security: denied file paths (loop secrets, override internals)
_DENIED_FILENAMES = frozenset({
    ".tokens.json",
    "session.lock",
    ".override-request.json",
    ".override-approved.json",
    ".override-meta.json",
})


def _is_denied_path(file_path):
    """Check if a file path should be blocked from serving.

    Denies access to loop secret files and override internals.
    Checks the final filename component against the deny set.
    """
    name = PurePosixPath(file_path).name
    return name in _DENIED_FILENAMES


# ── B1 Slice 1 (v2.13.0): safe content transport helpers ──────────
#
# Pure-Python helpers introduced in Slice 1: URL parsing, logical-path
# parsing, Windows-reserved-name check, response helpers. Not yet wired
# into `do_GET` (Slice 2 owns that migration). Consumed by the future
# `_handle_files` / `_handle_file` / `_handle_raw` / `_handle_history`
# methods and by unit tests via the `dashboard_module` fixture.
#
# See:
#   - vault/artifacts/2026-09-07-dashboard-safe-content-transport-b1-plan.md
#     (r6, frozen design record)
#   - vault/artifacts/2026-09-08-dashboard-b1-execution-errata.md
#     (E1-E5, authoritative for corrections)

from dashboard import content_policy as _content_policy  # noqa: E402
from dashboard.content_policy import (  # noqa: E402
    _ALLOWED_TEXT_EXTS_SOURCE,
    _ALLOWED_TEXT_EXTS_GOVERNANCE,
    _ALLOWED_RAW_ASSET_EXTS,
    _DENIED_DIR_SEGMENTS,
    _DENIED_HIDDEN_PREFIXES,
    _DENIED_BASENAME_SUFFIXES,
    _DENIED_EXACT_BASENAMES,
    _MIME_MAP,
    _text_exts_for,
    _serialize_listing_entry,
)

import functools as _functools  # noqa: E402
import stat as _stat  # noqa: E402


# ── Logical-path parse (r6 §4 + errata E5) ────────────────────────

LogicalPath = collections.namedtuple(
    "LogicalPath", "namespace_root disk_rel git_rel")

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f]")

# r4 F1 — Win32 trailing-dot/space aliases.
_WIN_TRAILING_STRIP = " \t\n\r\v\f."


def _strip_trailing_dots_spaces(segment):
    """Strip trailing ASCII whitespace and dots. r4 F1 helper."""
    return segment.rstrip(_WIN_TRAILING_STRIP)


# r5 F4 → r6 durability → errata E5. Explicit set is the PRIMARY
# reserved-name check; `PureWindowsPath.is_reserved()` is a
# secondary belt-and-suspenders check that may disappear in a
# future Python. The set covers ASCII digits, superscript-digit
# forms (U+00B9 / U+00B2 / U+00B3), and console-device names.
_WIN_RESERVED_STEMS_EXPLICIT = frozenset({
    "con", "prn", "aux", "nul",
    "com1", "com2", "com3", "com4", "com5",
    "com6", "com7", "com8", "com9",
    "lpt1", "lpt2", "lpt3", "lpt4", "lpt5",
    "lpt6", "lpt7", "lpt8", "lpt9",
    "com¹", "com²", "com³",
    "lpt¹", "lpt²", "lpt³",
    "conin$", "conout$",
})


def _casefold_segment(s):
    """Case-fold a single path segment for policy comparison.
    Do NOT substitute the folded form back into disk_rel / git_rel.
    """
    return s.casefold()


def _is_reserved_windows_component(candidate):
    """Authoritative Windows-reserved check with two-layer rule
    (r6 durability + errata E5).

    Layer 1 (PRIMARY): consult `_WIN_RESERVED_STEMS_EXPLICIT`
    against the case-folded stem (basename minus first extension).
    Errata E5: strip trailing ASCII spaces before splitting — Win32
    ignores them, so `NUL .txt`, `COM1 .md`, `CONIN$ .txt` must be
    caught by layer 1 alone.

    Layer 2 (SECONDARY): consult `PureWindowsPath.is_reserved()`
    while available. Deprecated in Python 3.13. Divergence between
    layers logs `dashboard.security` for operator visibility so the
    explicit set gets updated in a follow-on release.

    Runs unconditionally (not gated on `sys.platform == "win32"`)
    so a Windows-reserved name cannot enter through a cross-platform
    development fixture.
    """
    if not candidate:
        return False

    # Layer 1 — trailing-space normalized stem lookup.
    raw_stem = candidate.split(".", 1)[0]
    stem = raw_stem.rstrip(" \t").casefold()
    if stem in _WIN_RESERVED_STEMS_EXPLICIT:
        return True
    # Console-device names have no extension; also check the full
    # trailing-space-stripped candidate.
    if candidate.rstrip(" \t").casefold() in _WIN_RESERVED_STEMS_EXPLICIT:
        return True

    # Layer 2 — stdlib probe (advisory, may vanish on future Python).
    # r6 durability: PureWindowsPath.is_reserved() emits a
    # DeprecationWarning on Python 3.13+ and is scheduled for removal
    # in 3.15. Suppress the warning here — layer 1 is the primary
    # check and the warning would fire once per parsed segment (very
    # noisy). Errata E5 pins prove layer 1 alone covers every
    # documented family without the stdlib.
    import warnings as _warnings
    try:
        with _warnings.catch_warnings():
            _warnings.simplefilter("ignore", DeprecationWarning)
            stdlib_reserved = PureWindowsPath(
                candidate).is_reserved()
    except (TypeError, ValueError):
        return True  # Defensive: unparseable → refuse.
    except AttributeError:
        return False  # Method removed in a future Python.

    if stdlib_reserved:
        logging.getLogger("dashboard.security").warning(
            "reserved_name_only_in_stdlib candidate=%s — "
            "extend _WIN_RESERVED_STEMS_EXPLICIT",
            candidate)
        return True
    return False


def parse_logical_path(logical):
    """Parse a decoded URL path into a
    (namespace_root, disk_rel, git_rel) triple. Returns None on
    any reject condition (caller responds 400).

    Ordering matters — each check runs on the value produced by
    the previous one.
    """
    if not isinstance(logical, str) or not logical:
        return None

    # 1. Namespace parse — three canonical shapes (exact-case;
    # r3 F1 rejects case aliases so URL contract stays honest).
    if logical.startswith("source/"):
        namespace_root = ""
        tail = logical[len("source/"):]
        git_prefix = ""
    elif logical.startswith("gator-command/"):
        namespace_root = "gator-command"
        tail = logical[len("gator-command/"):]
        git_prefix = "gator-command/"
    else:
        cf = logical.casefold()
        if (logical.startswith(".gator/") or logical == ".gator"
                or cf.startswith(".gator/") or cf == ".gator"
                or cf.startswith("source/")
                or cf.startswith("gator-command/")):
            return None
        namespace_root = ".gator"
        tail = logical
        git_prefix = ".gator/"

    if not tail:
        return None

    # Windows drive-relative (`C:x`) has drive `C:` even without a root.
    if PureWindowsPath(tail).drive:
        return None
    # Backslash reject on any platform.
    if "\\" in tail:
        return None
    # Control chars and tilde prefix.
    if _CONTROL_CHARS_RE.search(tail):
        return None
    if tail.startswith("~"):
        return None

    # Segment shape checks.
    parts = tail.split("/")
    if any(p in ("", "..", ".") for p in parts):
        return None

    # 6a. ADS colons.
    if any(":" in p for p in parts):
        return None

    # 6b. Win32 trailing-dot/space.
    for p in parts:
        stripped = _strip_trailing_dots_spaces(p)
        if stripped != p or stripped == "":
            return None

    # 6c. Windows-reserved device names on EVERY segment (delegated
    # to the E5 helper). Checked on both original and
    # trailing-stripped forms for defense-in-depth.
    for p in parts:
        for candidate in (p, _strip_trailing_dots_spaces(p)):
            if not candidate:
                continue
            if _is_reserved_windows_component(candidate):
                return None

    # Cross-platform rooted check.
    if (PurePosixPath(tail).is_absolute()
            or PureWindowsPath(tail).is_absolute()):
        return None

    disk_rel = tail
    git_rel = git_prefix + tail
    return LogicalPath(namespace_root, disk_rel, git_rel)


# ── URL parser (r6 §8b.1 + errata E2 + E3) ────────────────────────

# Every `%` in the raw path MUST be immediately followed by two hex
# digits. `%ZZ` and dangling `%` fail this fullmatch.
_WELL_FORMED_PCT_RE = re.compile(r"[^%]*(%[0-9a-fA-F]{2}[^%]*)*")
# Encoded slash / backslash reject on raw path (routing boundary).
_ENCODED_SEP_RE = re.compile(r"%2[fF]|%5[cC]")
# After decoding, any surviving `%` is a double-encoded input.
_ANY_PCT_IN_DECODED_RE = re.compile(r"%")


@dataclass(frozen=True)
class Request:
    endpoint: str          # "files"|"file"|"raw"|"history"|"other"
    repo_name: str
    logical_path: str      # None for endpoints without one
    version_present: bool
    version_value: str
    query: dict


@dataclass(frozen=True)
class ParseError:
    """Structured pre-dispatch parse failure (r6 F2). Carries only
    safely derivable info — no decoding of untrusted path
    components. Populates `response_kind` and `version_present` so
    `do_GET` can pick the correct error responder before the URL
    is fully classified.
    """
    status: int
    message: str
    response_kind: str    # "json" | "raw"
    version_present: bool


def _infer_response_kind_raw(raw_path):
    """Cheap safe classification of a raw path. Only inspects ASCII
    bytes; no unquote, no parse_qs.

    Returns "json" if the raw path's endpoint segment is `/files`,
    `/file`, or `/history` (all JSON endpoints in B1); returns
    "raw" otherwise or when the endpoint cannot be read cleanly.
    """
    parts = raw_path.split("/")
    if len(parts) < 5:
        return "raw"
    if parts[0] != "" or parts[1] != "api" or parts[2] != "repo":
        return "raw"
    ep = parts[4]
    if ep in ("files", "file", "history"):
        return "json"
    return "raw"


def _parse_request(handler):
    """Single URL-parser. Returns `(Request, None)` on success or
    `(None, ParseError)` on failure (r6 F2 — structured error;
    errata E2 all-slash normalization; errata E3 `parse_qs` at
    start).
    """
    raw = handler.path
    q_idx = raw.find("?")
    if q_idx >= 0:
        raw_path = raw[:q_idx]
        raw_query = raw[q_idx + 1:]
    else:
        raw_path = raw
        raw_query = ""

    # E2 — match shipped `do_GET` normalization at line 189-194
    # exactly. Strip ALL trailing slashes, collapse empty to "/".
    raw_path = raw_path.rstrip("/") or "/"

    # E3 — parse the query once at the start. `parse_qs` never
    # touches path components, so this is safe even when the path
    # is malformed. Reused for both `ParseError.version_present`
    # and the final `Request.query`.
    try:
        query_map = parse_qs(raw_query, keep_blank_values=True)
    except (ValueError, UnicodeDecodeError):
        query_map = {}
    version_present = "version" in query_map

    def _fail(status, message):
        return (None, ParseError(
            status=status,
            message=message,
            response_kind=_infer_response_kind_raw(raw_path),
            version_present=version_present,
        ))

    # Step 2 — validate `%XX` well-formedness on raw_path.
    if not _WELL_FORMED_PCT_RE.fullmatch(raw_path):
        return _fail(400, "malformed percent-escape in path")

    # Step 3 — reject encoded slashes / backslashes on raw_path.
    if _ENCODED_SEP_RE.search(raw_path):
        return _fail(400, "encoded slash or backslash in path")

    # Step 4 — structural split on unencoded `/`.
    raw_parts = raw_path.split("/")

    # Step 5 — EXACT endpoint shape enforcement.
    if (len(raw_parts) < 4 or raw_parts[0] != ""
            or raw_parts[1] != "api" or raw_parts[2] != "repo"):
        # Not our namespace — pass through as "other".
        version_value = (query_map.get("version", [""])[0]
                         if version_present else "")
        return (Request("other", "", None,
                        version_present, version_value, query_map),
                None)

    raw_repo_name = raw_parts[3]
    if not raw_repo_name:
        return _fail(400, "repo name required")

    if len(raw_parts) == 4:
        endpoint = "other"
        raw_logical_parts = None
    else:
        raw_endpoint = raw_parts[4]
        if raw_endpoint == "files":
            if len(raw_parts) != 5:
                return _fail(404, "unknown endpoint")
            endpoint = "files"
            raw_logical_parts = None
        elif raw_endpoint == "history" and len(raw_parts) == 5:
            # /api/repo/<name>/history (repo-scope) — legacy route,
            # not owned by B1.
            endpoint = "other"
            raw_logical_parts = None
        elif raw_endpoint in ("file", "raw", "history"):
            if len(raw_parts) < 6:
                return _fail(400, "logical path required")
            endpoint = raw_endpoint
            raw_logical_parts = raw_parts[5:]
        else:
            # Unknown endpoint name (search, check, commits, ...)
            # — pass through as "other"; legacy dispatcher owns it.
            endpoint = "other"
            raw_logical_parts = None

    # Step 6 — decode each surviving RAW component EXACTLY ONCE.
    try:
        repo_name = unquote(raw_repo_name,
                            encoding="utf-8", errors="strict")
        decoded_logical_parts = (
            [unquote(p, encoding="utf-8", errors="strict")
             for p in raw_logical_parts]
            if raw_logical_parts is not None else None
        )
    except UnicodeDecodeError:
        return _fail(400, "malformed UTF-8 in URL")

    # Step 7 — defense in depth. `%25xx` decodes to `%xx`; refuse.
    if _ANY_PCT_IN_DECODED_RE.search(repo_name):
        return _fail(400, "double-encoded input")
    if decoded_logical_parts is not None:
        for p in decoded_logical_parts:
            if _ANY_PCT_IN_DECODED_RE.search(p):
                return _fail(400, "double-encoded input")

    logical = ("/".join(decoded_logical_parts)
               if decoded_logical_parts is not None else None)

    version_value = (query_map.get("version", [""])[0]
                     if version_present else "")

    return (Request(endpoint, repo_name, logical,
                    version_present, version_value, query_map),
            None)


# ── Raw-error HTML template (r6 F3) ───────────────────────────────

_RAW_ERROR_HTML_TEMPLATE = (
    "<!DOCTYPE html>\n"
    "<html><head><title>{status} {short}</title></head>"
    "<body><h1>{status} {short}</h1>"
    "<p>{explain}</p></body></html>"
)


# ── B1 Slice 2 (v2.13.0): containment, authorization, discovery ──
#
# Live-disk containment (`_contained_repo_path`,
# `_contained_namespace_root`), the endpoint-dispatched
# authorization allowlist (`is_browsable`), the reparse-point-aware
# walker (`_iter_scanner_files`), the historical `git ls-tree`
# symmetry helpers (`_ns_prefix_for`, `_reparse_ls_tree_entry`),
# the live-branch canonical-logical composition
# (`_canonical_logical_for`), the immutable-object-id resolver
# (`resolve_version_ref`), byte-preserving reader
# (`git_show_at_ref`), and the transport-header helper
# (`apply_response_headers`).
#
# See:
#   - vault/artifacts/2026-09-07-dashboard-safe-content-transport-b1-plan.md
#     (r6 §5.1, §5.1a, §5.1a-historical, §5.2, §6, §7, §8, §8b)
#   - vault/artifacts/2026-09-08-dashboard-b1-execution-errata.md
#     (E1-E5)


# r4 F4 sentinel — distinguishable from a real Path and from
# None. Never leaks past `/history/<file>`; consumers that
# receive this MUST NOT do disk I/O against `namespace_root`.
_NAMESPACE_ABSENT_OK = object()

# r5 T2 — symmetric with `parse_logical_path`'s three namespace
# roots. Iterated by the historical `/files?version=` handler.
_HISTORICAL_NAMESPACES = (".gator", "gator-command", "")

# Win32 FILE_ATTRIBUTE_REPARSE_POINT flag per Win32 SDK.
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400

# Bounded git subprocess timeouts (seconds).
_GIT_META_TIMEOUT = 10
_GIT_SHOW_TIMEOUT = 30


def _contained_repo_path(repo_path, namespace_root, disk_rel):
    """Return the resolved absolute Path or None on any reject.

    Two resolves, two containment checks, PLUS a per-component
    reparse-point rejection walk (2026-09-09 Codex F1 finding).
    Live-disk gate — called for endpoints WITHOUT `?version=`.
    `disk_rel` is trusted to have already passed
    `parse_logical_path`'s syntactic gates.

    F1 fix: the two-resolve containment check catches external
    escape (a symlink pointing OUTSIDE the repo), but on its own
    it does NOT catch an IN-REPO alias — a symlink or junction
    like `source/public -> .gator/sessions/_active` whose target
    stays inside the repo but corresponds to a namespace whose
    real policy denies serving. Authorization ran on the LOGICAL
    path (`source/public/token.json`), so `is_browsable` said yes;
    the resolved target is `.gator/sessions/_active/token.json`
    which the handler would then serve. To close the alias, walk
    the unresolved path from repo root and reject if any component
    is a reparse point (Windows junction, mount point, POSIX
    symlink, or any other reparse tag).
    """
    try:
        repo_root_r = Path(repo_path).resolve(strict=True)
    except (OSError, RuntimeError):
        return None

    # (1) Namespace root: catches a symlinked `.gator/` or
    # `gator-command/` that points outside the repo. Also
    # rejects the namespace root itself being a reparse point
    # inside the repo (belt-and-suspenders — the namespace-root
    # resolve already fails on a broken symlink; this rejects
    # the pathological case of a valid in-repo target).
    ns_path = Path(repo_path) / namespace_root if namespace_root \
        else Path(repo_path)
    if namespace_root and _path_exists(ns_path) and (
            _is_reparse_point(ns_path)):
        return None
    try:
        base_r = ns_path.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if base_r != repo_root_r and repo_root_r not in base_r.parents:
        return None

    # (1b) F1 fix — reject ANY in-repo reparse point along the
    # unresolved path from the namespace base down to the target.
    # Walking unresolved components means a `source/public`
    # junction into `.gator/sessions/_active/` is caught here even
    # though its resolved target is technically inside the repo.
    current = ns_path
    for segment in disk_rel.split("/"):
        if not segment:
            continue
        current = current / segment
        if _path_exists(current) and _is_reparse_point(current):
            logging.getLogger("dashboard.security").warning(
                "reparse_point_in_live_request path=%s",
                str(current))
            return None

    # (2) Target: catches disk-relative symlinks that escape
    # OUTSIDE the repo (still needed even after 1b because a
    # dangling symlink pointing outside would be caught here
    # rather than the reparse walk).
    try:
        target_r = (base_r / disk_rel).resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if target_r != base_r and base_r not in target_r.parents:
        return None

    return target_r


def _path_exists(p):
    """`Path.exists()` follows symlinks; `lstat()` does not. Use
    lstat so a dangling or reparse-target-unreachable path still
    reports existence for the reparse-point check.
    """
    try:
        p.lstat()
        return True
    except (OSError, ValueError):
        return False


def _contained_namespace_root(repo_path, namespace_root,
                              *, for_history_only=False):
    """r3 F5 addition — namespace-root-only containment.

    r4 F4: when `for_history_only=True`, an absent namespace
    directory returns `_NAMESPACE_ABSENT_OK` (git log needs only
    repo root + git_rel, not the current disk state of the
    namespace root). When it exists, strict-resolve containment
    still applies — a real namespace root that resolves outside
    the repo is rejected.
    """
    try:
        repo_root_r = Path(repo_path).resolve(strict=True)
    except (OSError, RuntimeError):
        return None

    ns_path = Path(repo_path) / namespace_root
    if for_history_only and not ns_path.exists():
        return _NAMESPACE_ABSENT_OK

    try:
        base_r = ns_path.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if base_r != repo_root_r and repo_root_r not in base_r.parents:
        return None
    return base_r


def _is_denied_segment(cf_part, namespace_root, is_leaf):
    """Case-folded segment-level deny. `_DENIED_HIDDEN_PREFIXES`
    for explicit-name coverage; every other dot-prefixed segment
    is denied by default (r6 F4 — collapse to a single rule so the
    walker and serve time agree).
    """
    if not cf_part.startswith("."):
        return False
    if cf_part == ".gator" and namespace_root == ".gator":
        return False  # never appears here anyway; safety net
    for prefix in _DENIED_HIDDEN_PREFIXES:
        if cf_part.startswith(prefix):
            return True
    return True  # every other dot-file / dot-dir denied by default


def is_text_for_file_endpoint_ext(ext, namespace_root):
    """r3 F6 — text eligibility on /file/ is decided by the
    extension allowlist, NOT by MIME family. `.svg` is in the
    text allowlist so it IS servable via /file/."""
    return ext in _text_exts_for(namespace_root)


def is_browsable(namespace_root, disk_rel, endpoint):
    """Authorization policy for file-serving endpoints.

    endpoint in {"files", "file", "raw", "history"}. Returns True
    iff `(namespace, path, endpoint)` is allowed. False means the
    caller responds 404 (never 403 — the response cannot be used
    as an existence oracle). All comparisons are case-folded so a
    case-aliased `Sessions/_ACTIVE/x.json` cannot bypass a deny.
    """
    parts = disk_rel.split("/")
    cf_parts = [_casefold_segment(p) for p in parts]

    # Hidden-segment check applies to EVERY component (r6 F4 —
    # walker and serve time agree).
    for i, cf_part in enumerate(cf_parts):
        if _is_denied_segment(cf_part, namespace_root,
                              is_leaf=(i == len(cf_parts) - 1)):
            return False

    # Intermediate denied directory segments.
    for cf_part in cf_parts[:-1]:
        if cf_part in _DENIED_DIR_SEGMENTS:
            return False

    # `.gator` namespace never exposes _active session state.
    cf_disk_rel = "/".join(cf_parts)
    if namespace_root == ".gator" and cf_disk_rel.startswith(
            "sessions/_active/"):
        return False

    # Basename policy — suffix rules (`.pem`, `.key`, `.pfx`,
    # `.env.local`, ...).
    cf_leaf = cf_parts[-1]
    for suffix in _DENIED_BASENAME_SUFFIXES:
        if cf_leaf.endswith(suffix):
            return False
    if cf_leaf in _DENIED_EXACT_BASENAMES:
        return False

    # r5 F3 — governance-root guard for the source namespace.
    if namespace_root == "" and cf_parts:
        if cf_parts[0] in (".gator", "gator-command"):
            return False

    # Extension allowlist dispatched by endpoint.
    ext = PurePosixPath(cf_leaf).suffix  # already folded
    allowed_text = _text_exts_for(namespace_root)

    if endpoint in ("files", "history"):
        return ext in allowed_text
    if endpoint == "file":
        return is_text_for_file_endpoint_ext(ext, namespace_root)
    if endpoint == "raw":
        return ext in allowed_text or ext in _ALLOWED_RAW_ASSET_EXTS
    return False


# ── Live-scanner walker (r4 F2 + r5 T1 + r5 F3 + r6 F4) ─────────

def _is_reparse_point(entry_or_path):
    """True if the given DirEntry OR Path is a Windows reparse
    point (junction, mount point, symlink dir/file, other reparse
    tag) OR a POSIX symlink.

    `Path.is_symlink()` alone returns False on Windows directory
    junctions — `rglob` therefore silently traverses them. This
    helper answers the broader "should the walker refuse to cross
    this filesystem boundary?".

    Python 3.9 compatibility (2026-09-09 Codex re-review, HIGH):
    `Path.stat(follow_symlinks=False)` was added in Python 3.10;
    on 3.9 it raises `TypeError` (uncaught before this fix), which
    would crash normal live handlers on the declared runtime floor
    (`pyproject.toml: requires-python = ">=3.9"`). Route through
    `os.stat(os.fspath(x), follow_symlinks=False)` uniformly — the
    stdlib `os.stat` has `follow_symlinks=` since 3.3 and works
    for BOTH `os.DirEntry` and `pathlib.Path` via `__fspath__`.
    `DirEntry.stat(follow_symlinks=False)` cache-hits when
    available, so preserve it via `isinstance(...)` check.
    """
    try:
        if hasattr(entry_or_path, "is_symlink") \
                and entry_or_path.is_symlink():
            return True
    except OSError:
        return True  # unreadable → refuse to cross.

    try:
        if isinstance(entry_or_path, os.DirEntry):
            # DirEntry.stat(follow_symlinks=False) has existed
            # since Python 3.6 and cache-hits the scandir stat.
            st = entry_or_path.stat(follow_symlinks=False)
        else:
            # Path or bare string — os.stat works on both via
            # __fspath__ and has follow_symlinks= since 3.3.
            st = os.stat(os.fspath(entry_or_path),
                         follow_symlinks=False)
    except OSError:
        return True

    reparse_tag = getattr(st, "st_reparse_tag", 0)
    if reparse_tag:
        return True

    file_attrs = getattr(st, "st_file_attributes", 0)
    if file_attrs & _FILE_ATTRIBUTE_REPARSE_POINT:
        return True

    return False


def _iter_scanner_files(namespace_root_path, namespace_root):
    """Top-down `os.scandir` walk that skips reparse-point
    directories BEFORE descent and reparse-point files at the
    file level. Prunes denied directories BEFORE descent so
    `.git`, `node_modules`, virtualenvs, and caches are never
    scanned. For `namespace_root == ""`, prunes top-level
    `.gator` and `gator-command` (r5 F3) so the source
    enumeration cannot alias governance content.

    r6 F4 collapses the dot-directory rule: EVERY dot-prefixed
    segment is pruned at descent (matching serve-time policy in
    `_is_denied_segment`), with a `namespace_root == ".gator"`
    safety-net exception for the walker's own root name.

    Yields file DirEntry objects. Callers MUST still run
    `_contained_repo_path` on the yielded entry as the F2
    belt-and-suspenders invariant.
    """
    stack = [namespace_root_path]
    reserved_top = frozenset(
        (".gator", "gator-command")
        if namespace_root == "" else ())
    is_top = True
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    if _is_reparse_point(entry):
                        logging.getLogger(
                            "dashboard.discovery").warning(
                            "reparse_point_rejected path=%s",
                            entry.path)
                        continue
                    try:
                        is_dir = entry.is_dir(follow_symlinks=False)
                    except OSError:
                        continue
                    if is_dir:
                        cf_name = entry.name.casefold()
                        if is_top and cf_name in reserved_top:
                            logging.getLogger(
                                "dashboard.discovery").warning(
                                "source_alias_denied path=%s "
                                "reason=governance_root",
                                entry.path)
                            continue
                        if cf_name in _DENIED_DIR_SEGMENTS:
                            continue
                        # r6 F4 — every dot-prefixed directory is
                        # denied at descent. Exception: the
                        # namespace-root case where the walker's
                        # own root is `.gator`.
                        if cf_name.startswith(".") and not (
                                cf_name == ".gator"
                                and namespace_root == ".gator"
                                and is_top):
                            continue
                        stack.append(entry.path)
                        continue
                    try:
                        is_file = entry.is_file(
                            follow_symlinks=False)
                    except OSError:
                        continue
                    if is_file:
                        yield entry
        except OSError:
            continue
        is_top = False


# ── Historical `git ls-tree` symmetry (r5 T2 + r6 F4 live-side) ─

def _ns_prefix_for(namespace_root):
    """r5 T2 — symmetric inverse of `parse_logical_path`'s
    namespace enum. Returns `(git_prefix, logical_prefix)`.
    """
    if namespace_root == ".gator":
        return (".gator/", "")
    if namespace_root == "gator-command":
        return ("gator-command/", "gator-command/")
    return ("", "source/")


def _canonical_logical_for(ns_root, disk_rel):
    """r6 F4 — build the canonical URL a client would submit for
    a file discovered under `ns_root`. Symmetric with
    `_ns_prefix_for` (r5 T2); live scanner + historical branch
    share the same predicate.
    """
    if ns_root == "":
        return "source/" + disk_rel
    if ns_root == ".gator":
        return disk_rel
    if ns_root == "gator-command":
        return "gator-command/" + disk_rel
    return None


def _reparse_ls_tree_entry(entry, namespace_root):
    """r5 T2 — turn a raw `git ls-tree -r --name-only` line into
    the logical path the client sees at `/files?version=`,
    re-parsed through the same rules the live URL parser applies.
    Returns None if the entry does NOT belong to this namespace
    or if it fails parse or authorization.
    """
    git_prefix, logical_prefix = _ns_prefix_for(namespace_root)
    if git_prefix and not entry.startswith(git_prefix):
        return None
    if namespace_root == "":
        # Source namespace excludes governance roots — those
        # entries map via their own namespaces instead.
        if entry.startswith(".gator/") or entry.startswith(
                "gator-command/"):
            return None
    trimmed = entry[len(git_prefix):] if git_prefix else entry
    logical = logical_prefix + trimmed
    lp = parse_logical_path(logical)
    if lp is None:
        return None
    if not is_browsable(lp.namespace_root, lp.disk_rel, "files"):
        return None
    return lp


# ── Immutable-ref resolver + byte-preserving reads (§6, §7) ─────

@_functools.lru_cache(maxsize=64)
def _object_format(repo_path):
    """Cached per-repo `git rev-parse --show-object-format`.
    Returns "sha1" or "sha256" on success; "sha1" as a defensive
    default when git errors (matches the pre-B1 assumption).
    """
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse",
             "--show-object-format"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=_GIT_META_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, OSError):
        return "sha1"
    if r.returncode != 0:
        return "sha1"
    fmt = r.stdout.strip()
    return fmt if fmt in ("sha1", "sha256") else "sha1"


def resolve_version_ref(repo_path, version_raw, object_format):
    """Validate `?version=` and return the canonical object ID.

    Returns `(sha_hex, error_message, http_status)`. `sha_hex`
    populated on success; error triple on failure. Uses object-ID
    lookup only (`cat-file -e <sha>^{commit}` for full-length;
    `rev-parse --disambiguate=` for prefixes). NEVER accepts a
    ref name — a branch named `<hex>` cannot mask the object.
    """
    if version_raw is None:
        return (None, "missing version parameter", 400)
    if version_raw == "":
        return (None, "version parameter must not be empty", 400)
    if not re.fullmatch(r"[0-9a-fA-F]+", version_raw):
        return (None, "version must be hex only", 400)
    sha_input = version_raw.lower()

    expected_len = 40 if object_format == "sha1" else (
        64 if object_format == "sha256" else 0)
    if expected_len == 0:
        return (None, "unknown object format", 500)

    if len(sha_input) == expected_len:
        try:
            r = subprocess.run(
                ["git", "-C", str(repo_path), "cat-file", "-e",
                 f"{sha_input}^{{commit}}"],
                capture_output=True,
                timeout=_GIT_META_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return (None, "git cat-file timed out after 10s", 500)
        except OSError as exc:
            return (None, f"git cat-file failed to launch: {exc}",
                    500)
        if r.returncode == 0:
            return (sha_input, None, None)
        return (None, f"version not found: {sha_input}", 404)

    if len(sha_input) < 7:
        return (None, "version prefix too short (min 7)", 400)
    if len(sha_input) >= expected_len:
        return (None, "version longer than object format", 400)

    try:
        r = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse",
             f"--disambiguate={sha_input}"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=_GIT_META_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return (None, "git rev-parse timed out after 10s", 500)
    except OSError as exc:
        return (None, f"git rev-parse failed to launch: {exc}",
                500)
    if r.returncode != 0:
        return (None, f"version not found: {sha_input}", 404)

    candidates = [line.strip() for line in r.stdout.splitlines()
                  if line.strip()]
    commit_candidates = []
    for cand in candidates:
        try:
            probe = subprocess.run(
                ["git", "-C", str(repo_path), "cat-file", "-t",
                 cand],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=_GIT_META_TIMEOUT,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            return (None, f"git cat-file failed: {exc}", 500)
        if probe.returncode == 0 and probe.stdout.strip() == (
                "commit"):
            commit_candidates.append(cand)

    if len(commit_candidates) == 0:
        return (None, f"version not found: {sha_input}", 404)
    if len(commit_candidates) > 1:
        return (None, "version prefix is ambiguous", 400)
    return (commit_candidates[0], None, None)


def git_show_at_ref(repo_path, sha, git_rel):
    """Byte-preserving `git show <sha>:<git_rel>`. Returns
    `(bytes, None)` on success or `(None, (status, message))` on
    failure. No `text=`, no `encoding=`, no `.strip()` on stdout
    — leading whitespace, trailing spaces, CRLF, and final
    newlines survive byte-for-byte.
    """
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_path), "show",
             f"{sha}:{git_rel}"],
            capture_output=True,
            timeout=_GIT_SHOW_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return (None, (504, "git show timed out after 30s"))
    except OSError as exc:
        return (None, (500, f"git show failed to launch: {exc}"))
    if r.returncode != 0:
        return (None, (404, f"file not present at version {sha}"))
    return (r.stdout, None)


def _git_commit_iso_date(repo_path, sha):
    """Return commit-date ISO string for `sha`, or None on any
    failure. Used to populate `last_modified` on historical
    `/file` responses.
    """
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_path), "log", "-1",
             "--format=%ai", sha],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=_GIT_META_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip() or None


def _mtime_iso(target):
    """UTC-ish ISO 8601 mtime string for a live Path. Uses the
    filesystem `st_mtime` epoch, formatted as
    `YYYY-MM-DD HH:MM:SS +ZZZZ` for consistency with git's
    `%ai` format on `/file` version responses.
    """
    try:
        st = target.stat()
    except OSError:
        return None
    dt = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S +0000")


def _mime_for(ext_lower):
    """MIME lookup from the shared `_MIME_MAP`. Returns None
    when the extension is not in the map — callers must have
    already checked `is_browsable`, so a miss here is a bug.
    """
    return _MIME_MAP.get(ext_lower)


def apply_response_headers(handler, mime, body_len, *,
                           cache_control=None):
    """Emit the transport headers B1 owns for RAW-body endpoints
    (`/raw`, `/file` binary paths — though `/file` is JSON now).
    B1 owns Content-Type, Content-Length,
    X-Content-Type-Options: nosniff, and Cache-Control on
    `?version=` responses. B1 does NOT emit
    Content-Security-Policy — B2 §4 owns it.
    """
    handler.send_header("Content-Type", mime)
    handler.send_header("Content-Length", str(body_len))
    handler.send_header("X-Content-Type-Options", "nosniff")
    if cache_control:
        handler.send_header("Cache-Control", cache_control)


# ── B2 Slice 1 (v2.13.0): sandboxed HTML preview CSP ──────────────
#
# `apply_html_csp_headers(handler, *, external)` is the ONLY seam
# B2 uses to add CSP to a `/raw` HTML response. It is called ONLY
# from `_handle_raw` when the resolved MIME is `text/html*`, AFTER
# `apply_response_headers` and BEFORE `end_headers`. It emits two
# additional headers on top of what `apply_response_headers`
# already wrote:
#
#   Content-Security-Policy:  (see _B2_CSP_EMBEDDED / _B2_CSP_EXTERNAL)
#   Vary: Sec-Fetch-Dest
#
# The Vary header is UNCONDITIONAL (even when the request did not
# carry Sec-Fetch-Dest): intermediaries cache based on the response
# Vary contract, not the request shape, so omitting it on the
# fallback response would let a cached fallback be served later to
# an iframe-context request and vice versa.
#
# Directives (r14 plan §4.1, audited across the 9 shipped
# blueprint HTML files 2026-09-09 — no `Function(...)` / `eval(...)`
# / string-arg timer usage found, so `'unsafe-eval'` is NOT
# permitted; only `'unsafe-inline'` for inline scripts and styles
# that shipped interactive blueprints require).

_B2_CSP_DIRECTIVES = (
    "default-src 'none'; "
    "script-src 'unsafe-inline'; "
    "style-src 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self' data:; "
    "media-src 'self' data:; "
    "form-action 'none'; "
    "base-uri 'none'; "
    "object-src 'none'; "
    "frame-ancestors 'self'"
)

# External-open (top-level navigation) additionally prepends
# `sandbox allow-scripts;` so the browser applies an opaque origin
# even at the top level, mirroring the iframe null-origin.
_B2_CSP_EMBEDDED = _B2_CSP_DIRECTIVES
_B2_CSP_EXTERNAL = "sandbox allow-scripts; " + _B2_CSP_DIRECTIVES


def apply_html_csp_headers(handler, *, external):
    """Emit CSP + Vary headers for a `/raw` `text/html` response.

    Called from `_handle_raw` AFTER `apply_response_headers` and
    BEFORE `end_headers`. Never emitted for non-HTML MIMEs. The
    `external` flag selects between the embedded (iframe) CSP and
    the external (top-level navigation) CSP — the latter prepends
    `sandbox allow-scripts;` so the top-level document runs as
    opaque-origin.
    """
    handler.send_header(
        "Content-Security-Policy",
        _B2_CSP_EXTERNAL if external else _B2_CSP_EMBEDDED)
    handler.send_header("Vary", "Sec-Fetch-Dest")


# ── HTTP handler ──────────────────────────────────────────────────────────────

class DashboardHandler(BaseHTTPRequestHandler):
    # Shared across all requests; set before server starts
    fast_data: dict = {}
    # Lock for refresh
    _refresh_lock = threading.Lock()

    def log_message(self, fmt, *args):
        pass  # Suppress default per-request log noise

    def handle_one_request(self):
        """Override to suppress ConnectionAbortedError during server restart."""
        try:
            super().handle_one_request()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass  # Expected during restart — old socket closing

    def _send_json(self, data, status=200, *, cache_control=None):
        """JSON response. Uniform Content-Type
        `application/json; charset=utf-8` (r4 F6 — the charset is
        required so browsers do not sniff), unconditional
        `X-Content-Type-Options: nosniff` (r3 F4), and
        `Cache-Control` set from the keyword arg (defaults to
        `no-cache` — the shipped sidebar-poll behavior; B1
        callers pass `no-store` for `?version=` responses to
        prevent caching of immutable historical content).
        """
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type",
                         "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control",
                         cache_control or "no-cache")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass  # Client disconnected (e.g., during restart)

    # ── B1 Slice 1 response helpers ──────────────────────────────

    def _send_json_error(self, status, message, *,
                         cache_control=None):
        """JSON-envelope error responder. `/files`, `/file`,
        `/history/<file>`, and every JSON `/api/repo/*` endpoint
        MUST call this on error — `send_error` returns HTML and
        would fail a client that expects the JSON envelope shape.
        `cache_control` propagates onto the response so
        `?version=` errors carry `no-store`.
        """
        self._send_json(
            {"error": message, "code": status},
            status=status, cache_control=cache_control)

    def _raw_error_direct(self, status, message, version_present):
        """Concrete self-contained raw-body error responder
        (r6 F3). Writes status + headers + body ONCE via
        `send_response` + explicit `send_header` + `end_headers`
        + `wfile.write`. NO delegation to `send_error`. NO
        dependency on undefined helper methods.

        Guarantees:
        - Status line sent EXACTLY ONCE.
        - Content-Type is `text/html;charset=utf-8`.
        - Content-Length matches encoded body bytes.
        - `X-Content-Type-Options: nosniff` is unconditional.
        - `Cache-Control: no-store` iff `version_present`.
        - Body write is guarded against
          `ConnectionAbortedError` / `BrokenPipeError`.
        """
        try:
            short = _http.HTTPStatus(status).phrase
        except ValueError:
            short = "Error"
        body_text = _RAW_ERROR_HTML_TEMPLATE.format(
            status=status,
            short=_html_escape(short),
            explain=_html_escape(str(message)),
        )
        body = body_text.encode("utf-8", errors="replace")
        self.send_response(status, message)
        self.send_header("Content-Type",
                         "text/html;charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        if version_present:
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError,
                BrokenPipeError):
            pass

    def _raw_error_from_req(self, status, message, req):
        """Thin adapter for handlers holding a `Request`. Reads
        `req.version_present` and delegates to
        `_raw_error_direct`.
        """
        version_present = (req is not None
                           and req.version_present)
        self._raw_error_direct(status, message, version_present)

    def _dispatch_parse_error(self, perr):
        """Route-aware pre-dispatch error responder (r6 F2).
        Reads `perr.response_kind` and picks `_send_json_error`
        (JSON endpoints) or `_raw_error_direct` (raw endpoints
        and everything the parser cannot classify safely).
        Cache-Control policy is uniform: `no-store` iff
        `perr.version_present`.
        """
        cache_ctl = ("no-store" if perr.version_present
                     else None)
        if perr.response_kind == "json":
            return self._send_json_error(
                perr.status, perr.message,
                cache_control=cache_ctl)
        return self._raw_error_direct(
            perr.status, perr.message, perr.version_present)

    # ── B1 Slice 2 handler methods (r6 F1 dispatch targets) ──────

    def _handle_files(self, req):
        """`/api/repo/<name>/files[?version=<sha>]` — JSON list of
        browsable files across the three namespaces. Live path uses
        the reparse-point-aware walker + `is_browsable`; historical
        path uses `git ls-tree -r --name-only` + the r5 T2 re-parse.
        Both branches mint response entries via
        `_serialize_listing_entry` so the wire schema is single-
        sourced (errata E1).
        """
        cache_ctl = "no-store" if req.version_present else None
        repo_path = _resolve_repo_path(req.repo_name,
                                        _REGISTRY_REPOS)
        if not repo_path or not Path(repo_path).is_dir():
            return self._send_json_error(
                400, "repo not accessible",
                cache_control=cache_ctl)

        if req.version_present:
            sha, msg, status = resolve_version_ref(
                repo_path, req.version_value,
                _object_format(repo_path))
            if msg:
                return self._send_json_error(
                    status, msg, cache_control=cache_ctl)
            try:
                r = subprocess.run(
                    ["git", "-C", str(repo_path),
                     "ls-tree", "-r", "--name-only", sha],
                    capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                    timeout=_GIT_META_TIMEOUT,
                )
            except (subprocess.TimeoutExpired, OSError) as exc:
                return self._send_json_error(
                    500, f"git ls-tree failed: {exc}",
                    cache_control=cache_ctl)
            if r.returncode != 0:
                return self._send_json_error(
                    404, f"version not found: {sha}",
                    cache_control=cache_ctl)

            files = []
            for line in r.stdout.splitlines():
                raw = line.strip()
                if not raw:
                    continue
                for ns in _HISTORICAL_NAMESPACES:
                    lp = _reparse_ls_tree_entry(raw, ns)
                    if lp is None:
                        continue
                    name = lp.disk_rel.rsplit("/", 1)[-1]
                    files.append(_serialize_listing_entry(
                        lp.namespace_root, lp.disk_rel,
                        name, 0))
                    break
            return self._send_json(
                {"files": files, "version": sha},
                cache_control=cache_ctl)

        # Live path — three namespaces enumerated symmetrically.
        files = []
        for ns in _HISTORICAL_NAMESPACES:
            base = _contained_namespace_root(repo_path, ns)
            if base is None or base is _NAMESPACE_ABSENT_OK:
                continue
            for entry in _iter_scanner_files(str(base), ns):
                try:
                    disk_rel = os.path.relpath(
                        entry.path, str(base)).replace(os.sep, "/")
                except ValueError:
                    continue
                logical = _canonical_logical_for(ns, disk_rel)
                if logical is None:
                    continue
                lp = parse_logical_path(logical)
                if lp is None:
                    continue
                if not is_browsable(lp.namespace_root, lp.disk_rel,
                                    "files"):
                    continue
                # F2 belt-and-suspenders — resolved-path
                # containment on every survivor.
                target = _contained_repo_path(
                    repo_path, lp.namespace_root, lp.disk_rel)
                if target is None:
                    logging.getLogger(
                        "dashboard.discovery").warning(
                        "symlink_or_junction_candidate_rejected "
                        "repo=%s path=%s reason=containment",
                        req.repo_name, disk_rel)
                    continue
                try:
                    st = entry.stat()
                except OSError:
                    continue
                files.append(_serialize_listing_entry(
                    lp.namespace_root, lp.disk_rel,
                    entry.name, st.st_size, mtime=st.st_mtime))
        return self._send_json({"files": files})

    def _handle_file(self, req):
        """`/api/repo/<name>/file/<logical>[?version=<sha>]` — JSON
        envelope with `content` (UTF-8-decoded with errors=replace,
        no `.strip()`), `content_type` advertisement (`text/plain`
        or `image/svg+xml`), `last_modified`, `version`. Errors are
        JSON envelopes via `_send_json_error`.
        """
        cache_ctl = "no-store" if req.version_present else None
        lp = parse_logical_path(req.logical_path)
        if lp is None:
            return self._send_json_error(
                400, "invalid path", cache_control=cache_ctl)
        if not is_browsable(lp.namespace_root, lp.disk_rel,
                            "file"):
            return self._send_json_error(
                404, "not found", cache_control=cache_ctl)
        repo_path = _resolve_repo_path(req.repo_name,
                                        _REGISTRY_REPOS)
        if not repo_path:
            return self._send_json_error(
                404, "repo not found", cache_control=cache_ctl)

        if req.version_present:
            sha, msg, status = resolve_version_ref(
                repo_path, req.version_value,
                _object_format(repo_path))
            if msg:
                return self._send_json_error(
                    status, msg, cache_control=cache_ctl)
            raw_bytes, ferr = git_show_at_ref(
                repo_path, sha, lp.git_rel)
            if ferr:
                return self._send_json_error(
                    ferr[0], ferr[1], cache_control=cache_ctl)
            mtime_iso = _git_commit_iso_date(repo_path, sha)
            version_out = sha
        else:
            target = _contained_repo_path(
                repo_path, lp.namespace_root, lp.disk_rel)
            if target is None or not target.is_file():
                return self._send_json_error(
                    404, "not found", cache_control=cache_ctl)
            try:
                raw_bytes = target.read_bytes()
            except (FileNotFoundError, PermissionError):
                # F3 (2026-09-09 Codex finding) — collapse to 404
                # per r6 §8b.3 error taxonomy so an unreadable or
                # concurrently removed target is indistinguishable
                # from the ordinary 404 path (no oracle).
                return self._send_json_error(
                    404, "not found", cache_control=cache_ctl)
            except OSError as exc:
                return self._send_json_error(
                    500, f"read failed: {exc}",
                    cache_control=cache_ctl)
            mtime_iso = _mtime_iso(target)
            version_out = None

        text = raw_bytes.decode("utf-8", errors="replace")
        ext = PurePosixPath(lp.disk_rel).suffix.casefold()
        content_type = ("image/svg+xml" if ext == ".svg"
                        else "text/plain")
        payload = {
            "path": req.logical_path,
            "content": text,
            "content_type": content_type,
            "last_modified": mtime_iso,
            "version": version_out,
        }
        self._send_json(payload, cache_control=cache_ctl)

    def _handle_raw(self, req):
        """`/api/repo/<name>/raw/<logical>[?version=<sha>]` — bytes.
        Success uses `apply_response_headers`; errors use
        `_raw_error_from_req` (thin adapter → `_raw_error_direct`).
        `Cache-Control: no-store` on `?version=` responses.
        """
        lp = parse_logical_path(req.logical_path)
        if lp is None:
            return self._raw_error_from_req(
                400, "invalid path", req)
        if not is_browsable(lp.namespace_root, lp.disk_rel,
                            "raw"):
            return self._raw_error_from_req(
                404, "not found", req)
        repo_path = _resolve_repo_path(req.repo_name,
                                        _REGISTRY_REPOS)
        if not repo_path:
            return self._raw_error_from_req(
                404, "repo not found", req)

        if req.version_present:
            sha, msg, status = resolve_version_ref(
                repo_path, req.version_value,
                _object_format(repo_path))
            if msg:
                return self._raw_error_from_req(
                    status, msg, req)
            body, ferr = git_show_at_ref(
                repo_path, sha, lp.git_rel)
            if ferr:
                return self._raw_error_from_req(
                    ferr[0], ferr[1], req)
        else:
            target = _contained_repo_path(
                repo_path, lp.namespace_root, lp.disk_rel)
            if target is None or not target.is_file():
                return self._raw_error_from_req(
                    404, "not found", req)
            try:
                body = target.read_bytes()
            except (FileNotFoundError, PermissionError):
                # F3 (2026-09-09 Codex finding) — 404 per r6
                # §8b.3 taxonomy (no existence/permission oracle).
                return self._raw_error_from_req(
                    404, "not found", req)
            except OSError as exc:
                return self._raw_error_from_req(
                    500, f"read failed: {exc}", req)

        ext = PurePosixPath(lp.disk_rel).suffix.casefold()
        mime = _mime_for(ext)
        if mime is None:
            # is_browsable said yes but no MIME — bug. Refuse the
            # response rather than emit octet-stream.
            return self._raw_error_from_req(
                500, "no MIME for browsable extension", req)
        cache = "no-store" if req.version_present else None
        # B2 Slice 1 (v2.13.0): HTML responses get an additional
        # CSP + Vary header set. The Sec-Fetch-Dest request header
        # selects between iframe-context (embedded) and top-level
        # navigation (external); missing → external (safer default
        # per r1 §3.2). `apply_response_headers` stays byte-exact
        # unchanged — B2's headers are additive-only via the
        # dedicated seam.
        is_html = mime.startswith("text/html")
        if is_html:
            sfd = self.headers.get("Sec-Fetch-Dest", "")
            external = sfd != "iframe"
        self.send_response(200)
        apply_response_headers(self, mime, len(body),
                               cache_control=cache)
        if is_html:
            apply_html_csp_headers(self, external=external)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError,
                BrokenPipeError):
            pass

    def _handle_history(self, req):
        """`/api/repo/<name>/history/<logical>` — commit list for a
        single file. `?version=` is REJECTED (400) — history has one
        contract (F5). Namespace containment via
        `_contained_namespace_root(..., for_history_only=True)` so
        pre-deletion commits for a file inside a deleted namespace
        directory still return.
        """
        if req.version_present:
            # F2 (2026-09-09 Codex finding) — every response that
            # consumed a `?version=` key carries no-store, even
            # this contract-shape rejection. Matches the uniform
            # transport-headers rule (§8.1, §12 TRIPWIRE).
            return self._send_json_error(
                400, "version not supported on /history",
                cache_control="no-store")
        lp = parse_logical_path(req.logical_path)
        if lp is None:
            return self._send_json_error(400, "invalid path")
        if not is_browsable(lp.namespace_root, lp.disk_rel,
                            "history"):
            return self._send_json_error(404, "not found")
        repo_path = _resolve_repo_path(req.repo_name,
                                        _REGISTRY_REPOS)
        if not repo_path:
            return self._send_json_error(404, "repo not found")

        base = _contained_namespace_root(
            repo_path, lp.namespace_root, for_history_only=True)
        if base is None:
            return self._send_json_error(404, "not found")

        try:
            r = subprocess.run(
                ["git", "-C", str(repo_path), "log",
                 "--format=%H%n%h%n%ai%n%s", "-50",
                 "--", lp.git_rel],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=_GIT_META_TIMEOUT,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            return self._send_json_error(
                500, f"git log failed: {exc}")
        commits = []
        if r.returncode == 0 and r.stdout:
            lines = r.stdout.splitlines()
            for i in range(0, len(lines) - 3, 4):
                commits.append({
                    "hash": lines[i],
                    "short_hash": lines[i + 1],
                    "date": lines[i + 2],
                    "message": lines[i + 3],
                })
        self._send_json(
            {"path": req.logical_path, "commits": commits})

    def _send_file(self, path):
        try:
            content = path.read_bytes()
        except FileNotFoundError:
            self.send_error(404, f"Not found: {path}")
            return
        ext = path.suffix.lower()
        mime = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css",
            ".js": "application/javascript",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".svg": "image/svg+xml",
        }.get(ext, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_dashboard_html(self):
        # Serve dashboard.html with an optional debug meta tag
        # injected into <head>. Injection is env-var checked per
        # request (not cached at startup) so the harness selects
        # the seam per-child at spawn time. See scripts-dashboard.md
        # TRIPWIRE (debug seam).
        path = DASHBOARD_DIR / "dashboard.html"
        try:
            html = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            self.send_error(404, f"Not found: {path}")
            return
        if os.environ.get("GATOR_DASHBOARD_DEBUG") == "1":
            html = html.replace(
                "</head>",
                '  <meta name="gator-debug" content="1">\n</head>',
                1,
            )
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError,
                BrokenPipeError):
            pass  # Client disconnected (matches _send_file).

    def _handle_audit_sessions(self):
        """Handle GET /api/audit/sessions — lazy session summary aggregation."""
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(self.path).query)

        repo_hash = qs.get("repo", [None])[0]
        fleet = qs.get("fleet", [""])[0].lower() == "true"
        refresh = qs.get("refresh", [""])[0].lower() == "true"

        result = _resolve_audit_sessions(
            repo_hash=repo_hash, fleet=fleet, refresh=refresh,
            registry_repos=_REGISTRY_REPOS,
        )
        self._send_json(result["data"], result.get("status", 200))

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/") or "/"

        # ── B1 Slice 2 (v2.13.0) — parse once + 4-way dispatch ──
        # Parser runs EXACTLY ONCE per request (§12 TRIPWIRE:
        # request parser). Result is consulted ONLY by the four
        # B1-owned endpoints; legacy branches below continue to
        # read `path` and `self.path` unchanged.
        req, perr = _parse_request(self)
        if perr is not None:
            return self._dispatch_parse_error(perr)
        if req.endpoint in ("files", "file", "raw", "history"):
            handler_by_endpoint = {
                "files":   self._handle_files,
                "file":    self._handle_file,
                "raw":     self._handle_raw,
                "history": self._handle_history,
            }
            return handler_by_endpoint[req.endpoint](req)

        # req.endpoint == "other" — control falls through to the
        # existing shipped legacy branches BELOW, unchanged.

        # Root — serve dashboard shell (with optional debug meta
        # injection when GATOR_DASHBOARD_DEBUG=1).
        if path == "/" or path == "/index.html":
            self._send_dashboard_html()
            return

        # Debug seam — exposes live _REGISTRY_REPOS so the test
        # harness can prove read-side isolation (the actual state
        # every handler operates on, not a recomputed Path.home()
        # shortcut). Gated per-request on GATOR_DASHBOARD_DEBUG=1
        # so the endpoint DOES NOT EXIST in production. See
        # scripts-dashboard.md TRIPWIRE (debug seam).
        if path == "/api/__gator_debug/registry_state":
            if os.environ.get("GATOR_DASHBOARD_DEBUG") != "1":
                self.send_error(404, "Not found")
                return
            self._send_json({
                "registry_repos": [
                    {"name": r.get("name"), "path": r.get("path")}
                    for r in _REGISTRY_REPOS
                ],
                "count": len(_REGISTRY_REPOS),
                "command_post_root": str(COMMAND_POST_ROOT),
            })
            return

        # Tier 1 data
        if path == "/api/data":
            self._send_json(self.__class__.fast_data)
            return

        # Refresh Tier 1 (async — starts background collection, returns immediately)
        if path == "/api/refresh":
            cls = self.__class__

            def _do_refresh():
                with cls._refresh_lock:
                    cls.fast_data = collect_standalone_data(_REGISTRY_REPOS)

            if not cls._refresh_lock.locked():
                threading.Thread(target=_do_refresh, daemon=True).start()
                self._send_json({"status": "refreshing"})
            else:
                self._send_json({"status": "already_refreshing"})
            return

        # Session summaries — lazy / on-demand aggregation (enterprise)
        if path == "/api/audit/sessions":
            self._handle_audit_sessions()
            return

        # Commit history — git log based, no session dependency
        if path.startswith("/api/repo/") and path.endswith("/history"):
            repo_name = path[len("/api/repo/"):-len("/history")]
            if not repo_name:
                self._send_json({"error": "repo name required"}, 400)
                return
            repo_path = _resolve_repo_path(repo_name, _REGISTRY_REPOS)
            if not repo_path or not Path(repo_path).is_dir():
                self._send_json({"error": "repo not accessible"}, 400)
                return
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            limit = int(qs.get("limit", ["20"])[0])
            commits = _get_repo_history(repo_path, limit)
            self._send_json({"commits": commits, "repo": repo_name})
            return

        # Cross-document search — server-side grep
        if path.startswith("/api/repo/") and path.endswith("/search"):
            repo_name = path[len("/api/repo/"):-len("/search")]
            if not repo_name:
                self._send_json({"error": "repo name required"}, 400)
                return
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            query = qs.get("q", [""])[0]
            if not query or len(query) < 2:
                self._send_json({"results": []})
                return
            repo_path = _resolve_repo_path(repo_name, _REGISTRY_REPOS)
            if not repo_path or not Path(repo_path).is_dir():
                self._send_json({"error": "repo not accessible"}, 400)
                return
            results = _search_repo_files(repo_path, query)
            self._send_json({"results": results, "query": query})
            return

        # Self-update check — read-only, no git fetch, no network
        if path == "/api/updates/check":
            self._send_json(check_for_updates())
            return

        # Check for available updates (dry-run, read-only)
        if path.startswith("/api/repo/") and path.endswith("/check"):
            repo_name = path[len("/api/repo/"):-len("/check")]
            if not repo_name:
                self._send_json({"error": "repo name required"}, 400)
                return
            repo_path = _resolve_repo_path(repo_name, _REGISTRY_REPOS)
            if not repo_path or not Path(repo_path).is_dir():
                self._send_json({"error": "repo not accessible"}, 400)
                return
            update_data = run_json("gator-update", "--dry-run", "--json",
                                   "--path", repo_path, timeout=30)
            # Also run charter-verify for charter health
            charter_data = run_json("gator-charter-verify",
                                    "--path", repo_path, timeout=15)
            result = dict(update_data)
            result["charter_health"] = {
                "finding_count": charter_data.get("finding_count", 0),
                "findings": charter_data.get("findings", []),
            } if not charter_data.get("error") else {"finding_count": -1, "findings": []}
            self._send_json(result)
            return

        # List .gator/ markdown files for a repo
        # GET /api/repo/<name>/commits — recent commit history for the repo
        if path.startswith("/api/repo/") and path.endswith("/commits"):
            repo_name = path[len("/api/repo/"):-len("/commits")]
            if not repo_name:
                self._send_json({"error": "repo name required"}, 400)
                return
            repo_path = _resolve_repo_path(repo_name, _REGISTRY_REPOS)
            if not repo_path:
                self._send_json({"error": "repo not found"}, 404)
                return
            log_output, ok = _git_run(
                "log", "--format=%H%n%h%n%ai%n%s", "-50",
                cwd=repo_path,
            )
            commits = []
            if ok and log_output:
                lines = log_output.splitlines()
                for i in range(0, len(lines) - 3, 4):
                    commits.append({
                        "hash": lines[i],
                        "short_hash": lines[i + 1],
                        "date": lines[i + 2],
                        "message": lines[i + 3],
                    })
            self._send_json({"commits": commits})
            return

        # B1 Slice 2 (v2.13.0): `/files`, `/raw/`, `/history/<file>`,
        # `/file/` are handled by the parse-once dispatch at the top
        # of do_GET. The four shipped route blocks that lived here
        # (~350 lines) were retired in favor of `_handle_files`,
        # `_handle_raw`, `_handle_history`, `_handle_file` as part
        # of the safe-content-transport migration.

        # Tier 2 — per-repo deep status (lazy, on demand)
        if path.startswith("/api/repo/") and "/file" not in path and not path.endswith(("/update", "/config", "/check", "/topology", "/files")):
            repo_name = path[len("/api/repo/"):]
            if not repo_name:
                self._send_json({"error": "repo name required"}, 400)
                return
            # Resolve name to path from registry for standalone compatibility
            repo_path = _resolve_repo_path(repo_name, _REGISTRY_REPOS)
            if repo_path:
                data = run_json("gator-repo-status", "--path", repo_path, timeout=30)
            else:
                data = run_json("gator-repo-status", "--repo", repo_name, timeout=30)
            self._send_json(data)
            return

        # GET /api/repos/discover — find local Git repos not yet registered
        if path == "/api/repos/discover":
            self._handle_repo_discover()
            return

        # Static files — serve from DASHBOARD_DIR
        rel = path.lstrip("/")
        candidate = DASHBOARD_DIR / rel
        if candidate.is_file():
            self._send_file(candidate)
            return

        self.send_error(404, f"Not found: {path}")

    def _handle_repo_discover(self):
        """Discover local Git repos not already in the dashboard registry.

        Discovery roots come from `resolve_discovery_roots()` — respects the
        `GATOR_DASHBOARD_DISCOVERY_ROOTS` env var override, falls back to
        the default home-relative set otherwise.
        """
        roots = [str(c) for c in _resolve_discovery_roots()]

        registered_paths = set()
        for r in _REGISTRY_REPOS:
            p = r.get("path", "")
            if p:
                try:
                    registered_paths.add(str(Path(p).resolve()))
                except OSError:
                    pass

        repos = []
        for scan_root in roots:
            try:
                for entry in os.scandir(scan_root):
                    if not entry.is_dir():
                        continue
                    git_dir = os.path.join(entry.path, ".git")
                    if not os.path.isdir(git_dir):
                        continue
                    abs_path = str(Path(entry.path).resolve())
                    if abs_path in registered_paths:
                        continue
                    gatorized = os.path.isdir(os.path.join(entry.path, ".gator"))
                    repos.append({
                        "name": entry.name,
                        "path": abs_path,
                        "gatorized": gatorized,
                    })
            except OSError:
                continue

        self._send_json({"roots": roots, "repos": repos})

    def _handle_repo_register(self):
        """Register a repo path in the local dashboard registry."""
        global _REGISTRY_REPOS
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        try:
            req = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._send_json({"error": "invalid JSON"}, 400)
            return

        repo_path = req.get("path", "").strip()
        if not repo_path or not os.path.isabs(repo_path):
            self._send_json({"error": "Absolute path required"}, 400)
            return
        if not os.path.isdir(os.path.join(repo_path, ".git")):
            self._send_json({"error": "Not a Git repository"}, 400)
            return

        from gator_core import ensure_dashboard_registry_entry
        result = ensure_dashboard_registry_entry(repo_path, source="dashboard")

        if result["status"] == "already_registered":
            self._send_json({"error": "Already registered"}, 409)
            return
        if result["status"] != "added":
            self._send_json({"error": result.get("detail", "Registration failed")}, 500)
            return

        # Update in-memory registry so refresh sees the new repo immediately
        abs_path = str(Path(repo_path).resolve())
        from datetime import datetime, timezone
        _REGISTRY_REPOS.append({
            "name": Path(repo_path).name,
            "path": abs_path,
            "remote": "",
            "registered": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": "dashboard",
        })

        self._send_json({"registered": True, "path": abs_path, "name": Path(repo_path).name})

    def _find_session_content(self, repo, source_kind, filename):
        """Resolve and read a session summary file from a local repo.

        Returns (content_string, error_string). Exactly one is non-None.
        """
        if source_kind != "local-repo":
            return None, f"unsupported source_kind: {source_kind}"

        # Resolve repo path from registry
        repo_path = _resolve_repo_path(repo, _REGISTRY_REPOS)
        if not repo_path:
            # Fallback: check standalone data repos list
            repos = self.__class__.fast_data.get("repos", [])
            match = next((r for r in repos if r.get("name") == repo), None)
            if not match:
                return None, f"repo '{repo}' not found"
            repo_path = match.get("path", "")
        if not repo_path:
            return None, "no local path for repo"
        filepath = Path(repo_path) / ".gator" / "sessions" / filename
        if not filepath.is_file():
            return None, "file not found in local repo"
        return filepath.read_text(encoding="utf-8", errors="replace"), None

    def _check_post_auth(self):
        """Reject unauthorized POSTs. Returns True if request is valid.

        Requires a custom header X-Gator-Dashboard: 1. Browsers never send
        custom headers on simple form POSTs, <img> embeds, or navigations.
        A cross-origin fetch() with custom headers triggers a CORS preflight
        OPTIONS request, which this server does not answer — so the browser
        blocks the actual POST. This closes the trust boundary for all
        browser-based attack vectors (forms, fetch, embeds).
        """
        if self.headers.get("X-Gator-Dashboard") != "1":
            self._send_json({"error": "missing required header"}, 403)
            return False
        return True

    def do_POST(self):
        path = self.path.split("?")[0]

        # ── auth check (anti-CSRF via custom header) ────────────────────────
        if not self._check_post_auth():
            return

        # POST /api/repos/register — add a repo to the dashboard registry
        if path == "/api/repos/register":
            self._handle_repo_register()
            return

        # POST /api/repo/<name>/config — write to repo's .gator/config.json
        if path.startswith("/api/repo/") and path.endswith("/config"):
            repo_name = path[len("/api/repo/"):-len("/config")]
            if not repo_name:
                self._send_json({"error": "repo name required"}, 400)
                return
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b""
            try:
                req = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self._send_json({"error": "invalid JSON"}, 400)
                return
            repo_path = _resolve_repo_path(repo_name, _REGISTRY_REPOS)
            if not repo_path:
                self._send_json({"error": f"repo '{repo_name}' not found in registry"}, 404)
                return
            config_path = Path(repo_path) / ".gator" / "config.json"
            # Read existing config
            config = {}
            if config_path.exists():
                try:
                    config = json.loads(config_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    config = {}
            # Apply changes
            if "enforcement_level" in req:
                level = req["enforcement_level"]
                if level not in ("strict", "warn", "off"):
                    self._send_json({"error": "enforcement_level must be strict, warn, or off"}, 400)
                    return
                config["enforcement_level"] = level
            config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
            # Update cached fast_data so page refresh reflects the change
            cached_repos = self.__class__.fast_data.get("repos", [])
            for r in cached_repos:
                if r.get("name") == repo_name:
                    if "config" not in r:
                        r["config"] = {}
                    r["config"].update(config)
                    break
            self._send_json({"status": "ok", "config": config})
            return

        # POST /api/repo/<name>/topology — switch repo between policy-synced and standalone
        if path.startswith("/api/repo/") and path.endswith("/topology"):
            repo_name = path[len("/api/repo/"):-len("/topology")]
            if not repo_name:
                self._send_json({"error": "repo name required"}, 400)
                return
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b""
            try:
                req = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self._send_json({"error": "invalid JSON"}, 400)
                return
            target_topology = req.get("topology", "")
            if target_topology not in ("standalone", "policy-synced"):
                self._send_json({"error": "topology must be 'standalone' or 'policy-synced'"}, 400)
                return
            repo_path = _resolve_repo_path(repo_name, _REGISTRY_REPOS)
            if not repo_path:
                self._send_json({"error": f"repo '{repo_name}' not found in registry"}, 404)
                return
            gator_dir = Path(repo_path) / ".gator"
            if not gator_dir.is_dir():
                self._send_json({"error": "repo has no .gator/ directory"}, 400)
                return

            from gator_core import get_repo_topology, clear_policy_artifacts

            if target_topology == "standalone":
                clear_policy_artifacts(gator_dir)
                new_topology = get_repo_topology(gator_dir)
                self._send_json({"status": "ok", "topology": new_topology})
            elif target_topology == "policy-synced":
                # Command-post architecture retired — policy-sync no longer supported
                self._send_json({"error": "policy-synced topology is no longer supported"}, 400)
            return

        # POST /api/updates/upgrade — pipx upgrade + restart
        if path == "/api/updates/upgrade":
            length = int(self.headers.get("Content-Length", 0))
            if length:
                self.rfile.read(length)
            self._send_json({"status": "upgrading"})
            # This function exits the process after responding
            threading.Thread(target=upgrade_and_restart, daemon=True).start()
            return

        # POST /api/restart — restart the dashboard server process
        if path == "/api/restart":
            length = int(self.headers.get("Content-Length", 0))
            if length:
                self.rfile.read(length)
            self._send_json({"status": "restarting"})
            # Schedule restart after response is sent
            threading.Thread(target=_restart_server, daemon=True).start()
            return

        # POST /api/session — serve raw markdown content of a session summary
        if path == "/api/session":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b""
            try:
                req = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self._send_json({"error": "invalid JSON"}, 400)
                return

            repo = req.get("repo", "")
            source_kind = req.get("source_kind", "")
            filename = req.get("filename", "")

            # Validate filename: no path traversal, must end with .md
            if not filename or ".." in filename or "/" in filename or "\\" in filename or not filename.endswith(".md"):
                self._send_json({"error": "invalid filename"}, 400)
                return
            if source_kind not in ("local-repo",):
                self._send_json({"error": "invalid source_kind"}, 400)
                return

            content, error = self._find_session_content(repo, source_kind, filename)
            if error:
                self._send_json({"error": error}, 404)
                return
            self._send_json({
                "filename": filename,
                "repo": repo,
                "source_kind": source_kind,
                "content": content,
            })
            return

        # POST /api/repo/<name>/update — run gator-update on a local repo
        if path.startswith("/api/repo/") and path.endswith("/update"):
            repo_name = path[len("/api/repo/"):-len("/update")]

            # Consume request body (may be empty, but must be read)
            length = int(self.headers.get("Content-Length", 0))
            if length:
                self.rfile.read(length)

            result = _resolve_repo_update(
                repo_name,
                registry_repos=_REGISTRY_REPOS,
                fleet_data=self.__class__.fast_data,
            )
            self._send_json(result["data"], result["status"])
            return

        # POST /api/repo/<name>/gatorize — install Gator into an ungoverned local repo
        if path.startswith("/api/repo/") and path.endswith("/gatorize"):
            repo_name = path[len("/api/repo/"):-len("/gatorize")]

            # Consume request body (may be empty, but must be read)
            length = int(self.headers.get("Content-Length", 0))
            if length:
                self.rfile.read(length)

            result = _resolve_repo_gatorize(
                repo_name,
                registry_repos=_REGISTRY_REPOS,
                fleet_data=self.__class__.fast_data,
            )
            self._send_json(result["data"], result["status"])
            return

        self.send_error(404, f"Not found: {path}")


# ── snapshot mode ─────────────────────────────────────────────────────────────

# ── snapshot: see dashboard/snapshot.py


# ── server startup ────────────────────────────────────────────────────────────

def find_free_port(start=8420):
    for port in range(start, start + 10):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(
        f"No free port found in range {start}–{start + 9}. "
        "Is another dashboard instance running?"
    )


def open_browser(url):
    try:
        if sys.platform == "win32":
            os.startfile(url)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", url])
        else:
            subprocess.Popen(["xdg-open", url])
    except Exception:
        pass  # Non-fatal — user can open manually


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Gator governance dashboard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--port", type=int, default=8420, help="HTTP port (default 8420)")
    parser.add_argument("--no-open", action="store_true", help="Skip browser open")
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="Write self-contained HTML to stdout and exit",
    )
    parser.add_argument("--repo", help="Pre-load Repo view for this repo name on open")
    parser.add_argument("--add-repo", metavar="PATH", help="Register a repo in the local dashboard")
    parser.add_argument("--remove-repo", metavar="NAME", help="Remove a repo from the local dashboard")
    args = parser.parse_args()

    if args.snapshot:
        # Write as UTF-8 bytes to avoid Windows cp1252 encoding issues
        registry = _load_registry_repos(COMMAND_POST_ROOT)
        sys.stdout.buffer.write(build_snapshot(collect_standalone_data(registry)).encode("utf-8"))
        return

    # Registry management (no server needed)
    if args.add_repo:
        from gator_core import add_dashboard_repo
        repo_path = Path(args.add_repo).resolve()
        if not repo_path.is_dir():
            print(f"  Error: directory not found: {args.add_repo}", file=sys.stderr)
            sys.exit(1)
        add_dashboard_repo(repo_path)
        print(f"  Added to dashboard: {repo_path.name} ({repo_path})")
        return

    if args.remove_repo:
        from gator_core import remove_dashboard_repo
        if remove_dashboard_repo(args.remove_repo):
            print(f"  Removed from dashboard: {args.remove_repo}")
        else:
            print(f"  Not found in dashboard: {args.remove_repo}")
        return

    global _REGISTRY_REPOS

    version = get_version() or "unknown"
    print(f"\n  gator dashboard  {version}")

    # Load registry
    _REGISTRY_REPOS = _load_registry_repos(COMMAND_POST_ROOT)

    print(f"  Repos registered: {len(_REGISTRY_REPOS)}", flush=True)
    fast_data = collect_standalone_data(_REGISTRY_REPOS)

    DashboardHandler.fast_data = fast_data

    if args.port == 0:
        # Kernel picks — bind directly and read the actual port back
        # from server_address. `find_free_port(0)` returns 0 (the
        # input value) not the assigned port, so skip it on the zero
        # path.
        server = HTTPServer(("127.0.0.1", 0), DashboardHandler)
    else:
        port = find_free_port(args.port)
        server = HTTPServer(("127.0.0.1", port), DashboardHandler)
    actual_port = server.server_address[1]
    base_url = f"http://127.0.0.1:{actual_port}"
    open_url = f"{base_url}/?repo={args.repo}" if args.repo else base_url

    # Ready protocol — column 0, `127.0.0.1` literal, printed
    # AFTER bind (URL is real) and BEFORE serve_forever (harness
    # gets it before request handling). flush=True so the reader
    # thread sees it under stdout buffering. This exact line is a
    # public interface between the dashboard and test harnesses /
    # tooling; see scripts-dashboard.md TRIPWIRE.
    print(f"Ready on {base_url}/", flush=True)
    # Human-oriented `Open:` line — when `--repo NAME` was passed,
    # show the repo-scoped URL so `--no-open --repo <name>` gives
    # the operator the URL they actually want to paste. Kept
    # indented + printed AFTER the Ready line so it doesn't
    # collide with the machine-readable protocol contract.
    if args.repo:
        print(f"  Open: {open_url}", flush=True)
    print(f"  Ctrl+C to stop\n", flush=True)

    if not args.no_open:
        open_browser(open_url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Dashboard stopped.")


if __name__ == "__main__":
    main()
