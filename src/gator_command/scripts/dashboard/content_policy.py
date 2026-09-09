"""Shared content-transport policy for the Dashboard file endpoints.

B1 §5.3 (r6) + errata E1. Single source of truth for the allowlist,
denylist, MIME map, and `/files` wire-schema serializer consumed by both
`gator-dashboard.py` (live and historical listing handlers, `/file`,
`/raw`, `/history/<file>`) and any future scanner refactor.

All string constants are stored pre-`str.casefold()`-normalized so the
runtime check is a fold-once comparison (r3 F1, r5 T1). Callers case-fold
the runtime input once and compare against these constants directly.

Nothing in this module performs I/O or subprocess calls; it is a pure
policy layer.
"""


# ── Allowlists ────────────────────────────────────────────────────

# Source-namespace text extensions (repo code + prose).
_ALLOWED_TEXT_EXTS_SOURCE = frozenset({
    ".py", ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs",
    ".md", ".rst", ".txt", ".json", ".jsonl",
    ".yaml", ".yml", ".toml", ".cfg", ".ini", ".xml",
    ".sh", ".bash", ".sql",
    ".css", ".html", ".htm", ".svg",
    ".rs", ".go", ".java", ".rb", ".c", ".h", ".cpp", ".hpp",
})

# Governance-namespace text extensions (`.gator/` + `gator-command/`).
# Narrower on purpose: governance is prose + config + generated HTML
# artifacts; code files under `.gator/` are not user-browsable.
_ALLOWED_TEXT_EXTS_GOVERNANCE = frozenset({
    ".md", ".rst", ".txt", ".json", ".jsonl",
    ".yaml", ".yml", ".toml",
    ".html", ".htm", ".svg",
})

# Raw asset extensions — served as bytes by `/raw` only. `/file` refuses
# these (JSON envelope with 404 because is_browsable filters by
# extension per endpoint).
_ALLOWED_RAW_ASSET_EXTS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico",
    ".pdf", ".woff2",
})


# ── Denylists (all values pre-casefolded) ────────────────────────

# Directory segments never traversed by the live scanner and never
# emitted by the historical `git ls-tree` mapping. Applied to
# case-folded intermediate segments; leaf files with these names are
# still legitimate (e.g. `dist` may be a filename).
_DENIED_DIR_SEGMENTS = frozenset({
    ".git", ".hg", ".svn",
    "node_modules", "__pycache__",
    ".venv", "venv", "env",
    "dist", "build",
    ".pytest_cache", ".tox", ".mypy_cache", ".ruff_cache",
    ".idea", ".vscode",
})

# Hidden-basename prefixes. Applied to case-folded leaf and
# intermediate components. `.env` prefix catches `.env`, `.env.local`,
# `.env.production` (r2 F1).
_DENIED_HIDDEN_PREFIXES = frozenset({
    ".env",
    ".git",
    ".ssh",
    ".aws",
    ".npmrc",
    ".pypirc",
    ".netrc",
    ".htpasswd",
})

# Basename SUFFIX denies (r2 F1): catches secret material regardless of
# the basename that precedes the suffix — `private.pem`, `server.key`,
# `cert.pfx` all match.
_DENIED_BASENAME_SUFFIXES = frozenset({
    ".pem", ".key", ".pfx", ".p12", ".pkcs12", ".pgp",
    ".asc",
})

# Exact basenames still denied (independent of extension rules).
_DENIED_EXACT_BASENAMES = frozenset({
    ".tokens.json",
    "session.lock",
    ".override-request.json",
    ".override-approved.json",
    ".override-meta.json",
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
})


# ── MIME map (derived from allowlists) ────────────────────────────

# Import-time assertion below guarantees every allowed extension has a
# MIME entry; no `application/octet-stream` fallback exists at runtime.
_MIME_MAP = {
    ".py":    "text/x-python; charset=utf-8",
    ".js":    "text/javascript; charset=utf-8",
    ".ts":    "text/x-typescript; charset=utf-8",
    ".jsx":   "text/javascript; charset=utf-8",
    ".tsx":   "text/x-typescript; charset=utf-8",
    ".mjs":   "text/javascript; charset=utf-8",
    ".cjs":   "text/javascript; charset=utf-8",
    ".md":    "text/markdown; charset=utf-8",
    ".rst":   "text/x-rst; charset=utf-8",
    ".txt":   "text/plain; charset=utf-8",
    ".json":  "application/json; charset=utf-8",
    ".jsonl": "application/x-ndjson; charset=utf-8",
    ".yaml":  "application/yaml; charset=utf-8",
    ".yml":   "application/yaml; charset=utf-8",
    ".toml":  "application/toml; charset=utf-8",
    ".cfg":   "text/plain; charset=utf-8",
    ".ini":   "text/plain; charset=utf-8",
    ".xml":   "application/xml; charset=utf-8",
    ".sh":    "text/x-shellscript; charset=utf-8",
    ".bash":  "text/x-shellscript; charset=utf-8",
    ".sql":   "application/sql; charset=utf-8",
    ".css":   "text/css; charset=utf-8",
    ".html":  "text/html; charset=utf-8",
    ".htm":   "text/html; charset=utf-8",
    ".svg":   "image/svg+xml",
    ".rs":    "text/x-rust; charset=utf-8",
    ".go":    "text/x-go; charset=utf-8",
    ".java":  "text/x-java; charset=utf-8",
    ".rb":    "text/x-ruby; charset=utf-8",
    ".c":     "text/x-c; charset=utf-8",
    ".h":     "text/x-c; charset=utf-8",
    ".cpp":   "text/x-c++; charset=utf-8",
    ".hpp":   "text/x-c++; charset=utf-8",
    ".png":   "image/png",
    ".jpg":   "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif":   "image/gif",
    ".webp":  "image/webp",
    ".ico":   "image/x-icon",
    ".pdf":   "application/pdf",
    ".woff2": "font/woff2",
}

# Every allowlist entry MUST have a MIME map entry — no octet-stream
# fallback for allowed extensions at runtime.
_missing_mime = (
    (_ALLOWED_TEXT_EXTS_SOURCE
     | _ALLOWED_TEXT_EXTS_GOVERNANCE
     | _ALLOWED_RAW_ASSET_EXTS)
    - _MIME_MAP.keys()
)
assert not _missing_mime, (
    f"content_policy: allowlist extensions missing from _MIME_MAP: "
    f"{sorted(_missing_mime)}"
)


def _text_exts_for(namespace_root):
    """Return the text allowlist for the given namespace root.

    `.gator` and `gator-command` share the narrower governance set;
    the source namespace uses the broader code+prose set.
    """
    if namespace_root == ".gator":
        return _ALLOWED_TEXT_EXTS_GOVERNANCE
    if namespace_root == "gator-command":
        return _ALLOWED_TEXT_EXTS_GOVERNANCE
    return _ALLOWED_TEXT_EXTS_SOURCE


# ── E1 canonical `/files` wire-schema serializer ─────────────────

def _serialize_listing_entry(namespace_root, disk_rel, name, size,
                             mtime=None):
    """One serializer, both branches (live + historical).

    Preserves the shipped wire schema at `gator-dashboard.py:389-419`
    (live) and `:446-499` (historical):

    - `""`             → `path="source/<disk_rel>"`,  `source="repo"`
    - `".gator"`       → `path="<disk_rel>"`,         `source=".gator"`
    - `"gator-command"`→ `path="gator-command/<disk_rel>"`,
                          `source="gator-command"`

    Any other `namespace_root` value raises `ValueError` — the namespace
    enum is closed and a security-boundary serializer must not silently
    mislabel an unknown value.

    `dir` is derived from the canonical wire `path`. `mtime` is optional
    (live entries carry it; historical entries do not).
    """
    if namespace_root == "":
        wire_path = "source/" + disk_rel
        source = "repo"
    elif namespace_root == ".gator":
        wire_path = disk_rel                    # implicit ns in URL
        source = ".gator"
    elif namespace_root == "gator-command":
        wire_path = "gator-command/" + disk_rel
        source = "gator-command"
    else:
        raise ValueError(
            f"unknown namespace root: {namespace_root!r}")
    dir_part = "/".join(wire_path.split("/")[:-1])
    entry = {
        "path": wire_path,
        "name": name,
        "dir": dir_part,
        "size": size,
        "source": source,
    }
    if mtime is not None:
        entry["mtime"] = mtime
    return entry
