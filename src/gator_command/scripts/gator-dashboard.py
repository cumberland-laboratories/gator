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
import json
import os
import socket
import subprocess
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

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
    from pathlib import PurePosixPath
    name = PurePosixPath(file_path).name
    return name in _DENIED_FILENAMES


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

    def _send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass  # Client disconnected (e.g., during restart)

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

        # Root — serve dashboard shell
        if path == "/" or path == "/index.html":
            self._send_file(DASHBOARD_DIR / "dashboard.html")
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

        if path.startswith("/api/repo/") and "/files" in path and path.endswith("/files"):
            repo_name = path[len("/api/repo/"):-len("/files")]
            if not repo_name:
                self._send_json({"error": "repo name required"}, 400)
                return
            repo_path = _resolve_repo_path(repo_name, _REGISTRY_REPOS)
            if not repo_path or not Path(repo_path).is_dir():
                self._send_json({"error": "repo not accessible"}, 400)
                return

            # Check for ?version=<hash> — use git ls-tree instead of filesystem
            from urllib.parse import urlparse, parse_qs as _parse_qs
            qs = _parse_qs(urlparse(self.path).query)
            version = qs.get("version", [None])[0]

            if version:
                import re as _re
                if not _re.match(r'^[0-9a-fA-F]+$', version):
                    self._send_json({"error": "invalid version hash"}, 400)
                    return
                tree_output, ok = _git_run(
                    "ls-tree", "-r", "--name-only", version,
                    cwd=repo_path,
                )
                if not ok:
                    self._send_json({"error": f"version not found: {version}"}, 404)
                    return
                files = []
                _SRC_EXT = {".py", ".js", ".ts", ".jsx", ".tsx", ".md", ".txt",
                            ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini",
                            ".sh", ".bash", ".css", ".html", ".sql", ".rs",
                            ".go", ".java", ".rb", ".c", ".h", ".cpp", ".hpp"}
                _SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv",
                              "venv", ".env", "dist", "build"}
                for line in tree_output.splitlines():
                    fpath = line.strip()
                    if not fpath:
                        continue
                    parts = fpath.split("/")
                    if any(p in _SKIP_DIRS or (p.startswith(".") and p not in (".gator",)) for p in parts[:-1]):
                        continue
                    fname = parts[-1]
                    ext = ("." + fname.rsplit(".", 1)[1]) if "." in fname else ""
                    # Route to the same three sources as the filesystem walker
                    if fpath.startswith(".gator/"):
                        if "sessions/_active/" in fpath:
                            continue
                        if ext.lower() not in (".md", ".json", ".jsonl", ".html", ".htm"):
                            continue
                        if _is_denied_path(fpath):
                            continue
                        rel = fpath[len(".gator/"):]
                        dir_part = "/".join(rel.split("/")[:-1])
                        files.append({
                            "path": rel,
                            "name": fname,
                            "dir": dir_part,
                            "size": 0,
                            "source": ".gator",
                        })
                    elif fpath.startswith("gator-command/"):
                        if "sessions/_active/" in fpath:
                            continue
                        if ext.lower() not in (".md", ".json"):
                            continue
                        dir_part = "/".join(fpath.split("/")[:-1])
                        files.append({
                            "path": fpath,
                            "name": fname,
                            "dir": dir_part,
                            "size": 0,
                            "source": "gator-command",
                        })
                    else:
                        if ext.lower() not in _SRC_EXT:
                            continue
                        dir_part = "/".join(parts[:-1])
                        files.append({
                            "path": "source/" + fpath,
                            "name": fname,
                            "dir": ("source/" + dir_part) if dir_part else "source",
                            "size": 0,
                            "source": "repo",
                        })
                self._send_json({"files": files, "version": version})
                return

            repo_root = Path(repo_path)
            gator_dir = repo_root / ".gator"
            gc_dir = repo_root / "gator-command"
            if not gator_dir.is_dir() and not gc_dir.is_dir():
                self._send_json({"files": []})
                return
            files = []
            # Scan .gator/ (all repos)
            if gator_dir.is_dir():
                for f in sorted(
                    list(gator_dir.rglob("*.md"))
                    + list(gator_dir.rglob("*.json"))
                    + list(gator_dir.rglob("*.jsonl"))
                    + list(gator_dir.rglob("*.html"))
                    + list(gator_dir.rglob("*.htm"))
                ):
                    rel = f.relative_to(gator_dir)
                    rel_str = str(rel).replace("\\", "/")
                    if rel_str.startswith("sessions/_active/"):
                        continue
                    if _is_denied_path(rel_str):
                        continue
                    st = f.stat()
                    files.append({
                        "path": rel_str,
                        "name": f.name,
                        "dir": str(rel.parent).replace("\\", "/") if str(rel.parent) != "." else "",
                        "size": st.st_size,
                        "mtime": st.st_mtime,
                        "source": ".gator",
                    })
            # Scan gator-command/ (repos with command-post knowledge layer)
            if gc_dir.is_dir():
                for f in sorted(list(gc_dir.rglob("*.md")) + list(gc_dir.rglob("*.json"))):
                    rel = f.relative_to(gc_dir)
                    rel_str = str(rel).replace("\\", "/")
                    if rel_str.startswith("sessions/_active/"):
                        continue
                    st = f.stat()
                    files.append({
                        "path": "gator-command/" + rel_str,
                        "name": f.name,
                        "dir": ("gator-command/" + str(rel.parent).replace("\\", "/")).rstrip("/") if str(rel.parent) != "." else "gator-command",
                        "size": st.st_size,
                        "mtime": st.st_mtime,
                        "source": "gator-command",
                    })
            # Also list source files (project code, read-only browsing)
            repo_root_path = Path(repo_path)
            source_files = []
            # Common source extensions to include
            _SRC_EXT = {".py", ".js", ".ts", ".jsx", ".tsx", ".md", ".txt",
                        ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini",
                        ".sh", ".bash", ".css", ".html", ".sql", ".rs",
                        ".go", ".java", ".rb", ".c", ".h", ".cpp", ".hpp"}
            _SKIP_DIRS = {".gator", "gator-command", ".git", "node_modules",
                          "__pycache__", ".venv", "venv", ".env", "dist", "build"}
            for item in sorted(repo_root_path.rglob("*")):
                if not item.is_file():
                    continue
                if item.suffix.lower() not in _SRC_EXT:
                    continue
                # Skip governance and hidden dirs
                parts = item.relative_to(repo_root_path).parts
                if any(p in _SKIP_DIRS or p.startswith(".") for p in parts[:-1]):
                    continue
                rel = item.relative_to(repo_root_path)
                rel_str = str(rel).replace("\\", "/")
                dir_str = str(rel.parent).replace("\\", "/") if str(rel.parent) != "." else ""
                st = item.stat()
                source_files.append({
                    "path": "source/" + rel_str,
                    "name": item.name,
                    "dir": "source/" + dir_str if dir_str else "source",
                    "size": st.st_size,
                    "mtime": st.st_mtime,
                    "source": "repo",
                })
            files.extend(source_files)
            self._send_json({"files": files})
            return

        # Serve a binary file (images) from a repo — GET /api/repo/<name>/raw/<path>
        if path.startswith("/api/repo/") and "/raw/" in path:
            after_repo = path[len("/api/repo/"):]
            raw_marker = "/raw/"
            idx = after_repo.find(raw_marker)
            if idx < 0:
                self.send_error(400, "invalid path")
                return
            from urllib.parse import unquote
            repo_name = unquote(after_repo[:idx])
            file_path = unquote(after_repo[idx + len(raw_marker):])
            if not repo_name or not file_path or ".." in file_path:
                self.send_error(400, "invalid path")
                return
            repo_path = _resolve_repo_path(repo_name, _REGISTRY_REPOS)
            if not repo_path:
                self.send_error(404, "repo not found")
                return
            # Resolve: source/ → repo root, gator-command/ → gator-command, else .gator/
            if file_path.startswith("source/"):
                full_path = Path(repo_path) / file_path[len("source/"):]
            elif file_path.startswith("gator-command/"):
                full_path = Path(repo_path) / file_path
            else:
                full_path = Path(repo_path) / ".gator" / file_path
            # Deny loop secret files
            if _is_denied_path(file_path):
                self.send_error(403, "access denied")
                return
            if not full_path.is_file():
                self.send_error(404, f"not found: {file_path}")
                return
            ext = full_path.suffix.lower()
            mime = {
                ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp",
                ".html": "text/html; charset=utf-8", ".htm": "text/html; charset=utf-8",
            }.get(ext, "application/octet-stream")
            content = full_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        # Read a specific .gator/ file from a repo
        # GET /api/repo/<name>/history/<filepath> — git log for a file
        if path.startswith("/api/repo/") and "/history/" in path:
            after_repo = path[len("/api/repo/"):]
            hist_marker = "/history/"
            idx = after_repo.find(hist_marker)
            if idx < 0:
                self._send_json({"error": "invalid path"}, 400)
                return
            from urllib.parse import unquote
            repo_name = unquote(after_repo[:idx])
            file_path = unquote(after_repo[idx + len(hist_marker):])
            if not repo_name or not file_path:
                self._send_json({"error": "repo name and file path required"}, 400)
                return
            if ".." in file_path:
                self._send_json({"error": "invalid file path"}, 400)
                return
            repo_path = _resolve_repo_path(repo_name, _REGISTRY_REPOS)
            if not repo_path:
                self._send_json({"error": "repo not found"}, 404)
                return
            # Resolve to absolute path (same logic as /file/)
            if file_path.startswith("source/"):
                full_path = Path(repo_path) / file_path[len("source/"):]
            elif file_path.startswith("gator-command/"):
                full_path = Path(repo_path) / file_path
            else:
                full_path = Path(repo_path) / ".gator" / file_path
            # Get git log for this file
            log_output, ok = _git_run(
                "log", "--format=%H%n%h%n%ai%n%s", "-50", "--", str(full_path),
                cwd=repo_path,
            )
            commits = []
            if ok and log_output:
                lines = log_output.splitlines()
                # Each commit is 4 lines: full_hash, short_hash, date, subject
                for i in range(0, len(lines) - 3, 4):
                    commits.append({
                        "hash": lines[i],
                        "short_hash": lines[i + 1],
                        "date": lines[i + 2],
                        "message": lines[i + 3],
                    })
            self._send_json({"path": file_path, "commits": commits})
            return

        # GET /api/repo/<name>/file/<filepath>[?version=<hash>]
        if path.startswith("/api/repo/") and "/file/" in path:
            # Parse: /api/repo/<name>/file/<filepath>
            after_repo = path[len("/api/repo/"):]
            file_marker = "/file/"
            idx = after_repo.find(file_marker)
            if idx < 0:
                self._send_json({"error": "invalid path"}, 400)
                return
            from urllib.parse import unquote
            repo_name = unquote(after_repo[:idx])
            file_path = unquote(after_repo[idx + len(file_marker):])
            if not repo_name or not file_path:
                self._send_json({"error": "repo name and file path required"}, 400)
                return
            # Security: no path traversal
            if ".." in file_path:
                self._send_json({"error": "invalid file path"}, 400)
                return
            # Deny loop secret files
            if _is_denied_path(file_path):
                self._send_json({"error": "access denied"}, 403)
                return
            repo_path = _resolve_repo_path(repo_name, _REGISTRY_REPOS)
            if not repo_path:
                self._send_json({"error": "repo not found"}, 404)
                return
            # Resolve file: source/ → repo root, gator-command/ → gator-command dir, else .gator/
            if file_path.startswith("source/"):
                full_path = Path(repo_path) / file_path[len("source/"):]
            elif file_path.startswith("gator-command/"):
                full_path = Path(repo_path) / file_path
            else:
                full_path = Path(repo_path) / ".gator" / file_path
            # Check for ?version=<hash> query param
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            version = qs.get("version", [None])[0]

            if version:
                # Validate: version must be hex only (git hash)
                import re as _re
                if not _re.match(r'^[0-9a-fA-F]+$', version):
                    self._send_json({"error": "invalid version hash"}, 400)
                    return
                # Compute git-relative path directly from file_path
                # (avoid Path.resolve().relative_to() which breaks on Windows)
                if file_path.startswith("source/"):
                    git_rel = file_path[len("source/"):]
                elif file_path.startswith("gator-command/"):
                    git_rel = file_path
                else:
                    git_rel = ".gator/" + file_path
                content, ok = _git_run("show", f"{version}:{git_rel}", cwd=repo_path)
                if not ok:
                    self._send_json({"error": f"version not found: {version}"}, 404)
                    return
                # Get the commit date for this version
                git_date, _ = _git_run("log", "-1", "--format=%ai", version, cwd=repo_path)
                self._send_json({
                    "path": file_path,
                    "content": content,
                    "last_modified": git_date or None,
                    "version": version,
                })
                return

            if not full_path.is_file():
                self._send_json({"error": f"file not found: {file_path}"}, 404)
                return
            content = full_path.read_text(encoding="utf-8", errors="replace")
            # Get git last-modified date for this file
            git_date, _ = _git_run(
                "log", "-1", "--format=%ai", "--", str(full_path),
                cwd=repo_path,
            )
            self._send_json({
                "path": file_path,
                "content": content,
                "last_modified": git_date or None,
            })
            return

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

    port = find_free_port(args.port)
    base_url = f"http://localhost:{port}"
    open_url = f"{base_url}/?repo={args.repo}" if args.repo else base_url

    server = HTTPServer(("127.0.0.1", port), DashboardHandler)

    print(f"  Ready: {open_url}")
    print(f"  Ctrl+C to stop\n", flush=True)

    if not args.no_open:
        open_browser(open_url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Dashboard stopped.")


if __name__ == "__main__":
    main()
