"""Security lint engine for the gator pre-commit hook.

Self-contained Layer 1 lint: parses git diff for added lines, matches
against embedded security/SQL/code patterns, applies context-aware
severity adjustments.  No external imports beyond stdlib.
"""

from __future__ import annotations

import json
import os
import re
import subprocess


def _git(*args, cwd=None):
    """Run a git command, return stdout. Returns empty string on failure."""
    try:
        result = subprocess.run(
            ["git"] + list(args),
            capture_output=True, text=True, cwd=cwd,
            encoding="utf-8", errors="replace",
        )
        return (result.stdout or "").strip()
    except OSError:
        return ""

# ---------------------------------------------------------------------------
# Lint rules — dangerous code patterns (from enforcer-review.py)
# Embedded here so the hook is self-contained with no import path fragility.
# ---------------------------------------------------------------------------

LINT_RULES = [
    # Secrets & credentials
    {
        "id": "SEC-001", "name": "Hardcoded password",
        "pattern": r"""(?i)(password|passwd|pwd)\s*=\s*['\"][^'\"]+['\"]""",
        "severity": "HIGH",
        "message": "Possible hardcoded password. Use environment variables or a secrets manager.",
        "exclude_extensions": {".md", ".txt", ".rst"},
    },
    {
        "id": "SEC-002", "name": "API key in source",
        "pattern": r"""(?i)(api[_-]?key|secret[_-]?key|access[_-]?token)\s*=\s*['\"][A-Za-z0-9+/=_-]{16,}['\"]""",
        "severity": "HIGH",
        "message": "Possible API key or secret in source code.",
        "exclude_extensions": {".md", ".txt", ".rst"},
    },
    {
        "id": "SEC-003", "name": "Private key material",
        "pattern": r"""-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----""",
        "severity": "CRITICAL",
        "message": "Private key material in source file.",
        "exclude_extensions": set(),
        # Downgrade to warning in documentation directories — these contain example text
        "doc_paths": ["reference-notes/", "procedures/", "docs/"],
        # Outside doc paths: require base64-looking key body within context_window lines
        # A lone PEM header without key body is almost always documentation or a stub
        "context_required": r"""[A-Za-z0-9+/]{40,}={0,2}\s*$""",
        "context_window": 10,
    },
    # SQL dangers
    {
        "id": "SQL-001", "name": "DROP TABLE",
        "pattern": r"""(?i)\bDROP\s+TABLE\b""",
        "severity": "HIGH",
        "message": "DROP TABLE detected. Verify this is intentional and scoped correctly.",
        "exclude_extensions": {".md"},
    },
    {
        "id": "SQL-002", "name": "DELETE without WHERE",
        "pattern": r"""(?i)\bDELETE\s+FROM\s+\w+\s*(?:;|\n|$)""",
        "severity": "HIGH",
        "message": "DELETE FROM without WHERE clause — this deletes all rows.",
        "exclude_extensions": {".md"},
    },
    {
        "id": "SQL-003", "name": "TRUNCATE",
        "pattern": r"""(?i)\bTRUNCATE\s+(?:TABLE\s+)?\w+""",
        "severity": "HIGH",
        "message": "TRUNCATE detected. Irreversible bulk deletion.",
        "exclude_extensions": {".md"},
    },
    {
        "id": "SQL-004", "name": "SQL string concatenation",
        "pattern": r"""(?:execute|cursor\.execute|query)\s*\(.*(?:\+|%\s|\.format|f['\"])""",
        "severity": "MEDIUM",
        "message": "Possible SQL injection — string concatenation in query. Use parameterized queries.",
        "exclude_extensions": {".md"},
    },
    # Code safety
    {
        "id": "CODE-001", "name": "eval() usage",
        "pattern": r"""\beval\s*\(""",
        "severity": "MEDIUM",
        "message": "eval() executes arbitrary code. Verify input is trusted.",
        "exclude_extensions": {".md", ".txt"},
    },
    {
        "id": "CODE-002", "name": "shell=True in subprocess",
        "pattern": r"""subprocess\.\w+\(.*shell\s*=\s*True""",
        "severity": "MEDIUM",
        "message": "subprocess with shell=True — command injection risk.",
        "exclude_extensions": {".md"},
    },
    {
        "id": "CODE-003", "name": "os.system usage",
        "pattern": r"""\bos\.system\s*\(""",
        "severity": "MEDIUM",
        "message": "os.system() is a command injection risk. Use subprocess with shell=False.",
        "exclude_extensions": {".md"},
    },
]

# Files that should never be committed
DANGEROUS_FILENAMES = {".env"}
DANGEROUS_PREFIXES = {".env."}
DANGEROUS_SAFE = {".env.example"}


def parse_diff_added_lines(repo_root):
    """Parse git diff --cached to extract only added lines per file.

    Returns dict: {filepath: [(lineno, line_text), ...]}
    Only includes lines starting with '+' (additions), excluding
    diff headers. Line numbers are mapped to the target file.
    """
    raw_diff = _git("diff", "--cached", "-U0", "--no-color", cwd=repo_root)
    if not raw_diff:
        return {}

    added = {}
    current_file = None
    target_lineno = 0

    for line in raw_diff.splitlines():
        # New file header: +++ b/path/to/file
        if line.startswith("+++ b/"):
            current_file = line[6:]
            added.setdefault(current_file, [])
            continue

        # Hunk header: @@ -old,count +new,count @@
        if line.startswith("@@") and current_file:
            match = re.search(r'\+(\d+)', line)
            if match:
                target_lineno = int(match.group(1))
            continue

        # Added line
        if line.startswith("+") and not line.startswith("+++") and current_file:
            added[current_file].append((target_lineno, line[1:]))
            target_lineno += 1
            continue

        # Context or removed line — just advance target lineno for context
        if not line.startswith("-") and current_file:
            target_lineno += 1

    return added


def load_lint_allowlist(gator_dir):
    """Load the PI-approved lint allowlist from .gator/lint-allow.json.

    Each entry is: {"rule": "SQL-001", "file": "path", ...}
    Returns a set of (rule, file) tuples for fast lookup.
    """
    allowlist_file = gator_dir / "lint-allow.json"
    if not allowlist_file.exists():
        return set()
    try:
        entries = json.loads(allowlist_file.read_text(encoding="utf-8"))
        return {(e["rule"], e["file"]) for e in entries if "rule" in e and "file" in e}
    except (json.JSONDecodeError, OSError, KeyError):
        return set()


def _effective_severity(rule, filepath, surrounding_lines):
    """Compute context-aware effective severity for a lint match.

    context_required takes priority over doc_paths: if corroborating evidence
    (e.g. a base64 key body) is present in surrounding lines, the match is
    treated as real secret material at original severity regardless of file
    location. doc_paths only downgrades when evidence is absent — distinguishing
    a lone example header in a reference doc from an actual committed key.
    """
    severity = rule["severity"]

    # Context-required check first — real evidence overrides location heuristics.
    if severity in ("CRITICAL", "HIGH") and rule.get("context_required"):
        context_found = any(
            re.search(rule["context_required"], line) for line in surrounding_lines
        )
        if context_found:
            # Corroborating evidence present — real key material, keep severity.
            return severity
        # No body found — likely documentation or stub. Fall through to
        # location-based downgrade or unconditional downgrade below.
        if rule.get("doc_paths"):
            f_norm = filepath.replace("\\", "/")
            if any(dp in f_norm for dp in rule["doc_paths"]):
                return "MEDIUM"
        return "MEDIUM"

    # Rules without context_required: apply doc_paths location-based downgrade.
    if rule.get("doc_paths"):
        f_norm = filepath.replace("\\", "/")
        if any(dp in f_norm for dp in rule["doc_paths"]):
            return "MEDIUM"

    return severity


def run_layer1_lint(staged_files, repo_root):
    """Run mechanical lint rules against ADDED lines only (from git diff).

    Only lines being introduced in this commit are checked. Existing
    code is implicitly approved by virtue of being in the codebase.
    This eliminates false alarm fatigue and means the PI only reviews
    what they're actually introducing.

    The allowlist (.gator/lint-allow.json) handles the rare case where
    new dangerous code is intentional.
    """
    findings = []
    gator_dir = repo_root / ".gator"
    allowed = load_lint_allowlist(gator_dir)

    # Self-exclude patterns (these files contain or quote the patterns they detect)
    self_excludes = {"gator-pre-commit.py", "enforcer-review.py", "enforcer-prompt.md", "lint-allow.json", "commit_issues.md", "whiteboard.md",
                     "precommit_lint.py"}

    # Path-scoped excludes for Gator-provided documentation that quotes dangerous
    # patterns as examples. Unlike self_excludes (basename-only), these check the
    # normalized path so a user file with the same name is still scanned.
    gator_doc_excludes = {"reference-notes/dangerous-patterns.md"}

    # Check for dangerous filenames in staged files (these are always checked
    # regardless of diff — staging a .env file is the danger)
    for filepath in staged_files:
        basename = os.path.basename(filepath)
        if basename in self_excludes:
            continue
        if basename in DANGEROUS_FILENAMES or (
            any(basename.startswith(p) for p in DANGEROUS_PREFIXES)
            and basename not in DANGEROUS_SAFE
        ):
            if ("HYG-002", filepath) not in allowed:
                findings.append({
                    "rule": "HYG-002",
                    "severity": "HIGH",
                    "file": filepath,
                    "line": 0,
                    "message": f"{basename} should not be committed. Add to .gitignore.",
                })

    # Parse diff for added lines only
    added_lines = parse_diff_added_lines(repo_root)

    for filepath, lines in added_lines.items():
        basename = os.path.basename(filepath)
        if basename in self_excludes:
            continue
        f_norm = filepath.replace("\\", "/")
        if any(f_norm.endswith(dp) for dp in gator_doc_excludes):
            continue

        _, ext = os.path.splitext(filepath)

        for rule in LINT_RULES:
            if ext in rule.get("exclude_extensions", set()):
                continue
            if (rule["id"], filepath) in allowed:
                continue
            pattern = rule["pattern"]
            for i, (lineno, line_text) in enumerate(lines):
                if re.search(pattern, line_text):
                    window = rule.get("context_window", 10)
                    if rule.get("context_required"):
                        # Read full file content so a key body already in the
                        # file (not newly added in this diff) is still detected.
                        try:
                            file_lines = (repo_root / filepath).read_text(
                                encoding="utf-8", errors="replace"
                            ).splitlines()
                            line_idx = lineno - 1
                            ctx = file_lines[
                                max(0, line_idx - window):line_idx + window + 1
                            ]
                        except OSError:
                            ctx = [lt for _, lt in lines[max(0, i - window):i + window + 1]]
                    else:
                        ctx = [lt for _, lt in lines[max(0, i - window):i + window + 1]]
                    effective_sev = _effective_severity(rule, filepath, ctx)
                    findings.append({
                        "rule": rule["id"],
                        "severity": effective_sev,
                        "file": filepath,
                        "line": lineno,
                        "message": rule["message"],
                        "match": line_text.strip()[:120],
                    })

    return findings
