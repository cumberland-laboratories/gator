#!/usr/bin/env python3
"""
Enforcer Review — charter-grounded linter for Gator projects.

Runs in three layers:
  Layer 1: Mechanical lint (no model, instant, always works)
  Layer 2: Charter-grounded review (model reads charters + diff)
  Layer 3: Blast radius check (model reads cross-cutting + diff)

Configuration: .gator/scripts/enforcer-config.json
  - Set provider/model/api_key_env for Layer 2-3
  - Supports: anthropic, openai, google, ollama, none
  - Layer 1 always runs regardless of configuration

Usage:
  python .gator/scripts/enforcer-review.py                    # review all modified files
  python .gator/scripts/enforcer-review.py --files "a.py,b.py"  # review specific files
  python .gator/scripts/enforcer-review.py --staged           # review git staged changes
  python .gator/scripts/enforcer-review.py --layer 1          # mechanical lint only (no model)
  python .gator/scripts/enforcer-review.py --format json      # JSON output

Output goes to stdout and .gator/whiteboard.md (by default).
The whiteboard is the authoritative PI-visible record. Use --no-whiteboard
to suppress whiteboard writes (e.g., CI/CD pipelines that parse stdout).
"""

import argparse
import os
import re
import subprocess
import sys
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from gator_core import ensure_utf8_stdout, find_gator_root, resolve_thin_link
CONFIG_PATH = os.path.join(SCRIPT_DIR, "enforcer-config.json")
MODEL_TIMEOUT_SECONDS = 120

# Repo root: .gator/scripts/ → .gator/ → repo root
_REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))


def _deep_merge(defaults, override):
    """Recursively merge config dicts so partial nested overrides are safe."""
    merged = dict(defaults)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _normalize_path(path):
    """Normalize paths for reliable equality checks across cwd styles."""
    return os.path.normcase(os.path.abspath(path))


def load_config():
    """Load enforcer configuration. Returns defaults if file missing."""
    defaults = {
        "layer1": {"enabled": True},
        "layer2_3": {
            "enabled": True,
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "api_key_env": "ANTHROPIC_API_KEY",
        },
    }
    if not os.path.isfile(CONFIG_PATH):
        return defaults
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        return _deep_merge(defaults, cfg)
    except Exception:
        return defaults


# ─── Layer 1: Mechanical Lint (no model, instant) ───────────────────────

LAYER1_RULES = [
    # Secrets & credentials
    {
        "id": "SEC-001",
        "name": "Hardcoded password",
        "pattern": r"""(?i)(password|passwd|pwd)\s*=\s*['\"][^'\"]+['\"]""",
        "severity": "HIGH",
        "message": "Possible hardcoded password. Use environment variables or a secrets manager.",
        "exclude_extensions": [".md", ".txt", ".rst"],
    },
    {
        "id": "SEC-002",
        "name": "API key in source",
        "pattern": r"""(?i)(api[_-]?key|secret[_-]?key|access[_-]?token)\s*=\s*['\"][A-Za-z0-9+/=_-]{16,}['\"]""",
        "severity": "HIGH",
        "message": "Possible API key or secret in source code.",
        "exclude_extensions": [".md", ".txt", ".rst"],
    },
    {
        "id": "SEC-003",
        "name": "Private key material",
        "pattern": r"""-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----""",
        "severity": "CRITICAL",
        "message": "Private key material in source file.",
        "exclude_extensions": [],
        # Downgrade to warning in documentation directories — these contain example text
        "doc_paths": ["reference-notes/", "procedures/", "docs/"],
        # Outside doc paths: require base64-looking key body within context_window lines
        # A lone PEM header without key body is almost always documentation or a stub
        "context_required": r"""[A-Za-z0-9+/]{40,}={0,2}\s*$""",
        "context_window": 10,
    },
    # SQL dangers
    {
        "id": "SQL-001",
        "name": "DROP TABLE",
        "pattern": r"""(?i)\bDROP\s+TABLE\b""",
        "severity": "HIGH",
        "message": "DROP TABLE detected. Verify this is intentional and scoped correctly.",
        "exclude_extensions": [".md"],
    },
    {
        "id": "SQL-002",
        "name": "DELETE without WHERE",
        "pattern": r"""(?i)\bDELETE\s+FROM\s+\w+\s*(?:;|\n|$)""",
        "severity": "HIGH",
        "message": "DELETE FROM without WHERE clause — this deletes all rows.",
        "exclude_extensions": [".md"],
    },
    {
        "id": "SQL-003",
        "name": "TRUNCATE",
        "pattern": r"""(?i)\bTRUNCATE\s+(?:TABLE\s+)?\w+""",
        "severity": "HIGH",
        "message": "TRUNCATE detected. Irreversible bulk deletion.",
        "exclude_extensions": [".md"],
    },
    {
        "id": "SQL-004",
        "name": "SQL string concatenation",
        "pattern": r"""(?:execute|cursor\.execute|query)\s*\(.*(?:\+|%\s|\.format|f['\"])""",
        "severity": "MEDIUM",
        "message": "Possible SQL injection — string concatenation in query. Use parameterized queries.",
        "exclude_extensions": [".md"],
    },
    # Code safety
    {
        "id": "CODE-001",
        "name": "eval() usage",
        "pattern": r"""\beval\s*\(""",
        "severity": "MEDIUM",
        "message": "eval() executes arbitrary code. Verify input is trusted.",
        "exclude_extensions": [".md", ".txt"],
    },
    {
        "id": "CODE-002",
        "name": "shell=True in subprocess",
        "pattern": r"""subprocess\.\w+\(.*shell\s*=\s*True""",
        "severity": "MEDIUM",
        "message": "subprocess with shell=True — command injection risk.",
        "exclude_extensions": [".md"],
    },
    {
        "id": "CODE-003",
        "name": "os.system usage",
        "pattern": r"""\bos\.system\s*\(""",
        "severity": "MEDIUM",
        "message": "os.system() is a command injection risk. Use subprocess with shell=False.",
        "exclude_extensions": [".md"],
    },
    # Hygiene
    {
        "id": "HYG-001",
        "name": "TODO/FIXME/HACK introduced",
        "pattern": r"""(?i)\b(?:TODO|FIXME|HACK|XXX)\b""",
        "severity": "LOW",
        "message": "Marker comment found. Track it or resolve it.",
        "exclude_extensions": [".md"],
    },
    {
        "id": "HYG-002",
        "name": ".env file staged",
        "pattern": None,  # handled specially
        "severity": "HIGH",
        "message": ".env file should not be committed. Add to .gitignore.",
        "exclude_extensions": [],
    },
]


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


def run_layer1(files):
    """Run mechanical lint rules against file list. No model needed."""
    findings = []

    # Exclude enforcer files by basename — the rule catalog contains the
    # patterns it's searching for, causing false positives. Basename match
    # catches both .gator/scripts/ and template copies.
    SELF_EXCLUDE_NAMES = {"enforcer-review.py", "enforcer-prompt.md"}

    for filepath in files:
        if os.path.basename(filepath) in SELF_EXCLUDE_NAMES:
            continue

        _, ext = os.path.splitext(filepath)

        # Special case: .env file check
        basename = os.path.basename(filepath)
        if basename == ".env" or basename.startswith(".env."):
            if basename != ".env.example":
                findings.append({
                    "layer": 1,
                    "rule": "HYG-002",
                    "severity": "HIGH",
                    "file": filepath,
                    "line": 0,
                    "message": ".env file should not be committed. Add to .gitignore.",
                })
                continue

        if not os.path.isfile(filepath):
            continue

        try:
            with open(filepath, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception:
            continue

        for rule in LAYER1_RULES:
            if rule["pattern"] is None:
                continue
            if ext in rule.get("exclude_extensions", []):
                continue

            for i, line in enumerate(lines):
                if re.search(rule["pattern"], line):
                    window = rule.get("context_window", 10)
                    ctx = lines[max(0, i - window):i + window + 1]
                    effective_sev = _effective_severity(rule, filepath, ctx)
                    findings.append({
                        "layer": 1,
                        "rule": rule["id"],
                        "severity": effective_sev,
                        "file": filepath,
                        "line": i + 1,
                        "message": rule["message"],
                        "match": line.strip()[:120],
                    })

    return findings


# ─── Structural Priors (from gator-charter-verify) ─────────────────────

def _find_verify_script():
    """Locate gator-charter-verify.py.

    Search order:
    1. gator-command/scripts/ in this repo (command-post repo)
    2. Command post resolved via thin link (fleet repos)
    3. .gator/scripts/ local (fallback)

    Returns absolute path or None.
    """
    from pathlib import Path

    # 1. Command-post repo: gator-command/scripts/ is a sibling of .gator/
    candidate = os.path.join(_REPO_ROOT, "gator-command", "scripts", "gator-charter-verify.py")
    if os.path.isfile(candidate):
        return candidate

    # 2. Fleet repo: resolve command post via thin link, look in its scripts/
    gator_dir = Path(os.path.join(_REPO_ROOT, ".gator"))
    command_post = resolve_thin_link(gator_dir)
    if command_post:
        # Check both gator-command/ (dev) and gator-engine/ (public) layouts
        for parent in ("gator-command", "gator-engine"):
            candidate = str(command_post / parent / "scripts" / "gator-charter-verify.py")
            if os.path.isfile(candidate):
                return candidate

    # 3. Local .gator/scripts/ (manual placement)
    candidate = os.path.join(SCRIPT_DIR, "gator-charter-verify.py")
    if os.path.isfile(candidate):
        return candidate

    return None


def collect_structural_priors(files):
    """Run gator-charter-verify on the repo and filter to changed files.

    Runs a full-repo verify pass (typically <2s for ~50 files), then
    filters findings to only those affecting the changed file set.
    Returns a formatted string block for inclusion in the model prompt,
    or empty string if verify is unavailable or produces no findings.
    """
    verify_script = _find_verify_script()
    if not verify_script:
        return ""

    try:
        result = subprocess.run(
            [sys.executable, verify_script, "--path", _REPO_ROOT, "--json"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return ""

        data = json.loads(result.stdout)
        findings = data.get("findings", [])
        if not findings:
            return ""

        # Filter to findings relevant to the changed files
        changed_set = set(f.replace("\\", "/") for f in files)
        relevant = [f for f in findings if f.get("file", "").replace("\\", "/") in changed_set]
        if not relevant:
            return ""

        # Format as a compact block for the model
        lines = ["STRUCTURAL PRIORS (mechanical, from gator-charter-verify):"]
        for f in relevant:
            fn_note = f" ({f['function']})" if f.get("function") else ""
            lines.append(f"  [{f['class']}] {f['file']}{fn_note}: {f['message']}")

        return "\n".join(lines)

    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        return ""


# ─── Layer 2 & 3: Charter-Grounded Review (model required) ────────────

LAYER2_PROMPT = """You are an enforcer reviewing code changes against charters.

The CHARTERS are in the system prompt (the authoritative map of what each module owns, its functions, access patterns, and invariants). The DIFF is in the user message (the actual changes being committed).

If STRUCTURAL PRIORS are present before the diff, they are cheap mechanical findings from static analysis (gator-charter-verify). Use them to focus your review — they identify files with coverage gaps, undocumented functions, complexity mismatches, or stale charter entries. Structural priors are not verdicts; they are attention signals. You decide which are materially relevant to this diff.

Review for these specific failure modes, in priority order:

BOUNDARY VIOLATIONS (HIGH severity):
- Code added to a module that its charter says it "Does Not Own"
- A function reading/writing something not declared in its @reads/@writes

TRIPWIRE VIOLATIONS (HIGH severity):
- Changes that break a pattern labeled TRIPWIRE in any charter
- Modifications to cross-language constants, self-contained modules, or synchronized implementations without updating all affected sides

CHARTER DRIFT (MEDIUM severity):
- Functions added, removed, or renamed in code without corresponding charter updates
- Changed caller/callee relationships (← / →) not reflected in charter entries
- Charter still documents behavior the code no longer exhibits

MISSING CROSS-REFERENCES (MEDIUM severity):
- New cross-module dependencies not captured in ← / → annotations
- New files that should appear in a charter's Covers: line but don't

CHARTER UPDATE ACCURACY (LOW severity):
- Charter was updated but the update doesn't match what actually changed in the diff
- Overly broad or vague charter entries that don't describe the actual function behavior

Output ONLY a JSON array. Each object must have exactly these fields:
[{"severity": "HIGH", "file": "path/to/file", "finding": "one-sentence description"}]

If no issues found, output exactly: []
"""

FULL_AUDIT_PROMPT = """You are an enforcer performing a comprehensive charter-vs-code audit.

The CHARTERS are in the system prompt — they are the authoritative map of what each module owns, its functions, access patterns, invariants, and boundaries. The CODE SAMPLES are in the user message — the actual source files covered by those charters.

Audit for these specific failure modes, in priority order:

STALE ENTRIES (HIGH severity):
- Charter documents a function (### name()) that no longer exists in the code
- Charter describes behavior that the code no longer exhibits
- Charter's Covers: line references files that don't exist

MISSING ENTRIES (HIGH severity):
- Public functions in the code that have no charter entry
- Files that should be in a charter's Covers: line but aren't

BOUNDARY VIOLATIONS (HIGH severity):
- Code in a module doing something its charter says it "Does Not Own"
- Functions reading/writing things not declared in their @reads/@writes

STALE CROSS-REFERENCES (MEDIUM severity):
- ← (caller) or → (callee) annotations that no longer match actual call patterns
- Cross-cutting patterns that reference functions or behaviors that have changed

TRIPWIRE ACCURACY (MEDIUM severity):
- TRIPWIRE patterns described in cross-cutting charter that no longer match the code
- ! (tripwire) notes on individual functions that are outdated

INDEX ACCURACY (LOW severity):
- INDEX.md path mappings that point to wrong charters
- Files not covered by any INDEX entry

Output ONLY a JSON array. Each object must have exactly these fields:
[{"severity": "HIGH", "file": "path/to/file", "finding": "one-sentence description"}]

If no issues found, output exactly: []
"""


def get_diff_for_files(files):
    """Get combined diff for a list of files, including untracked files.

    For tracked files: uses git diff (staged + unstaged).
    For untracked files: synthesizes a diff from file contents so the
    model review covers the same scope as file discovery.
    """
    parts = []

    # Tracked files: combined staged + unstaged diff
    tracked = [f for f in files if _is_tracked(f)]
    if tracked:
        # Unstaged changes
        result = subprocess.run(
            ["git", "diff", "--no-color", "--"] + tracked,
            capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        if result.stdout.strip():
            parts.append(result.stdout)

        # Staged changes
        result = subprocess.run(
            ["git", "diff", "--cached", "--no-color", "--"] + tracked,
            capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        if result.stdout.strip():
            parts.append(result.stdout)

    # Untracked files: synthesize diff from contents
    untracked = [f for f in files if not _is_tracked(f)]
    for filepath in untracked:
        if not os.path.isfile(filepath):
            continue
        try:
            with open(filepath, encoding="utf-8", errors="replace") as f:
                content = f.read()
            lines = content.splitlines()
            # Format as a unified diff (new file)
            header = f"diff --git a/{filepath} b/{filepath}\nnew file\n--- /dev/null\n+++ b/{filepath}\n"
            hunk = f"@@ -0,0 +1,{len(lines)} @@\n"
            body = "\n".join(f"+{line}" for line in lines)
            parts.append(header + hunk + body + "\n")
        except Exception:
            continue

    return "\n".join(parts)


def _is_tracked(filepath):
    """Check if a file is tracked by git."""
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", filepath],
        capture_output=True, text=True
    )
    return result.returncode == 0


def _parse_index(charter_dir):
    """Parse INDEX.md to map file path patterns to charter filenames.

    Returns list of (pattern, [charter_filenames]) tuples.
    """
    index_path = os.path.join(charter_dir, "INDEX.md")
    if not os.path.isfile(index_path):
        return []

    mappings = []
    try:
        with open(index_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # Parse table rows: | path pattern | [Charter](file.md) ... |
                if not line.startswith("|") or line.startswith("| If ") or line.startswith("|---"):
                    continue
                parts = [p.strip() for p in line.split("|")[1:-1]]
                if len(parts) < 2:
                    continue
                raw_pattern = parts[0].strip()
                # Extract charter filenames from markdown links
                charter_refs = re.findall(r'\(([^)]+\.md)\)', parts[1])
                if not raw_pattern or not charter_refs:
                    continue
                # INDEX cells can be comma-separated file lists or path prefixes.
                # Split on commas and strip backticks from each sub-pattern.
                sub_patterns = [
                    p.strip().strip("`").strip()
                    for p in raw_pattern.split(",")
                    if p.strip()
                ]
                for sp in sub_patterns:
                    mappings.append((sp, charter_refs))
    except (OSError, UnicodeDecodeError):
        pass
    return mappings


def _resolve_primary_charter_dir(repo_root):
    """Return the authoritative charter directory for this repo.

    Special case: the source gator-command repo uses gator-command/charters
    as the primary script-charter surface. Ordinary governed repos use
    .gator/charters.
    """
    command_post_charters = os.path.join(repo_root, "gator-command", "charters")
    command_post_scripts = os.path.join(repo_root, "gator-command", "scripts")
    if os.path.isdir(command_post_charters) and os.path.isdir(command_post_scripts):
        return command_post_charters
    return os.path.join(repo_root, ".gator", "charters")


def find_relevant_charters(files, charter_dir=None):
    """Find charters relevant to the changed files using INDEX.md.

    Uses the INDEX to identify which charters cover the changed files,
    then loads only those charters plus cross-cutting.md (always included).
    Falls back to loading all charters if INDEX is missing or unparseable.
    """
    if charter_dir is None:
        repo_root = os.getcwd()
        charter_dir = _resolve_primary_charter_dir(repo_root)

    if not os.path.isdir(charter_dir):
        return {}

    # Always include cross-cutting if it exists
    relevant_names = set()
    cross_cutting = os.path.join(charter_dir, "cross-cutting.md")
    if os.path.isfile(cross_cutting):
        relevant_names.add("cross-cutting.md")

    # Try INDEX-based selection
    index_mappings = _parse_index(charter_dir)
    if index_mappings:
        for changed_file in files:
            f_normalized = changed_file.replace("\\", "/")
            f_basename = f_normalized.rsplit("/", 1)[-1]
            for pattern, charter_refs in index_mappings:
                # Glob-style: "extract-*-sessions.py" → match with fnmatch
                if "*" in pattern or "?" in pattern:
                    import fnmatch
                    if fnmatch.fnmatch(f_basename, pattern) or fnmatch.fnmatch(f_normalized, pattern):
                        relevant_names.update(charter_refs)
                # Exact filename or path prefix match
                elif f_basename == pattern or f_normalized.startswith(pattern) or pattern in f_normalized:
                    relevant_names.update(charter_refs)
        # If INDEX matched something, use only those charters
        if len(relevant_names) > 1:  # more than just cross-cutting
            charters = {}
            for name in relevant_names:
                fpath = os.path.join(charter_dir, name)
                if os.path.isfile(fpath):
                    try:
                        with open(fpath, encoding="utf-8") as f:
                            charters[name] = f.read()
                    except (OSError, UnicodeDecodeError):
                        pass
            if charters:
                return charters

    # Fallback: load all charters (INDEX missing, empty, or no matches)
    charters = {}
    for fname in os.listdir(charter_dir):
        if fname.endswith(".md") and not fname.startswith("_") and fname != "INDEX.md":
            fpath = os.path.join(charter_dir, fname)
            try:
                with open(fpath, encoding="utf-8") as f:
                    charters[fname] = f.read()
            except (OSError, UnicodeDecodeError):
                pass

    return charters


def call_model(provider, model, api_key, system_prompt, user_message,
               charter_text=None):
    """Call an LLM. Returns (response_text, usage_info) tuple.

    charter_text: when provided and provider is anthropic, charters are placed
    in the system prompt with cache_control so repeated runs within the TTL
    window (~5 min) pay ~90% less for the charter portion.
    """

    if provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        # Structure system prompt for caching: instructions (small) +
        # charters (large, stable across runs) with cache_control.
        if charter_text:
            system = [
                {"type": "text", "text": system_prompt},
                {"type": "text", "text": charter_text,
                 "cache_control": {"type": "ephemeral"}},
            ]
        else:
            system = system_prompt

        response = client.messages.create(
            model=model,
            max_tokens=2000,
            system=system,
            messages=[{"role": "user", "content": user_message}],
            timeout=MODEL_TIMEOUT_SECONDS,
        )
        usage = response.usage
        usage_info = {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
            "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
        }
        return response.content[0].text.strip(), usage_info

    elif provider == "openai":
        import openai
        client = openai.OpenAI(api_key=api_key)
        full_system = system_prompt
        if charter_text:
            full_system = f"{system_prompt}\n\nCHARTERS:\n{charter_text}"
        response = client.chat.completions.create(
            model=model,
            max_tokens=2000,
            messages=[
                {"role": "system", "content": full_system},
                {"role": "user", "content": user_message},
            ],
            timeout=MODEL_TIMEOUT_SECONDS,
        )
        usage_info = {}
        if response.usage:
            usage_info = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            }
        return response.choices[0].message.content.strip(), usage_info

    elif provider == "google":
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        gen_model = genai.GenerativeModel(model)
        full_prompt = system_prompt
        if charter_text:
            full_prompt = f"{system_prompt}\n\nCHARTERS:\n{charter_text}"
        response = gen_model.generate_content(
            f"{full_prompt}\n\n{user_message}",
            generation_config={"max_output_tokens": 2000},
            request_options={"timeout": MODEL_TIMEOUT_SECONDS},
        )
        return response.text.strip(), {}

    elif provider == "ollama":
        # Ollama runs locally — no API key, uses HTTP API
        import urllib.request
        full_system = system_prompt
        if charter_text:
            full_system = f"{system_prompt}\n\nCHARTERS:\n{charter_text}"
        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": full_system},
                {"role": "user", "content": user_message},
            ],
            "stream": False,
        }).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        return data["message"]["content"].strip(), {}

    else:
        raise ValueError(f"Unknown provider: {provider}")


def run_layer2_3(files, diff, config):
    """Run charter-grounded review using an LLM."""
    l23 = config.get("layer2_3", {})
    provider = l23.get("provider", "anthropic")
    model = l23.get("model", "claude-sonnet-4-6")
    api_key_env = l23.get("api_key_env", "ANTHROPIC_API_KEY")
    findings = []

    # Provider "none" = explicitly disabled
    if provider == "none":
        return [{
            "layer": 2,
            "rule": "SKIP",
            "severity": "INFO",
            "file": "",
            "line": 0,
            "message": "Layer 2-3 disabled (provider: none in enforcer-config.json). Layer 1 mechanical lint still ran.",
        }]

    # Get API key (ollama doesn't need one)
    api_key = None
    if provider != "ollama":
        api_key = os.environ.get(api_key_env)
        if not api_key:
            return [{
                "layer": 2,
                "rule": "SKIP",
                "severity": "INFO",
                "file": "",
                "line": 0,
                "message": (
                    f"{api_key_env} not set — skipping charter-grounded review (Layer 2-3).\n"
                    f"  To enable: set {api_key_env} in your environment.\n"
                    f"  To use a different provider: edit .gator/scripts/enforcer-config.json.\n"
                    f"  Supported: anthropic, openai, google, ollama (free/local), none (disable).\n"
                    f"  Layer 1 mechanical lint still ran."
                ),
            }]

    charters = find_relevant_charters(files)
    if not charters:
        return [{
            "layer": 2,
            "rule": "SKIP",
            "severity": "INFO",
            "file": "",
            "line": 0,
            "message": "No charters found — skipping charter-grounded review. Run bootstrap first (see .gator/gator-start-up.md).",
        }]

    # Build context — charters go to system prompt (cached), diff to user message
    charter_text = ""
    for name, content in charters.items():
        charter_text += f"\n\n--- CHARTER: {name} ---\n{content}"

    diff_limit = 100000
    charter_limit = 100000
    diff_truncated = len(diff) > diff_limit
    charters_truncated = len(charter_text) > charter_limit

    if diff_truncated or charters_truncated:
        truncated_parts = []
        if diff_truncated:
            truncated_parts.append(
                f"diff truncated to {diff_limit} chars from {len(diff)}"
            )
        if charters_truncated:
            truncated_parts.append(
                f"charters truncated to {charter_limit} chars from {len(charter_text)}"
            )
        findings.append({
            "layer": 2,
            "rule": "TRUNCATED",
            "severity": "INFO",
            "file": "",
            "line": 0,
            "message": (
                "Charter-grounded review used partial context: "
                + "; ".join(truncated_parts)
                + ". Review conclusions may miss tail context."
            ),
        })

    # Collect structural priors (cheap, no model, fast)
    priors_block = collect_structural_priors(files)

    # Charters passed separately for caching (Anthropic: system prompt with
    # cache_control; other providers: appended to system prompt as text).
    # User message: structural priors (if any) + diff.
    if priors_block:
        user_message = f"{priors_block}\n\nDIFF:\n```\n{diff[:diff_limit]}\n```"
        findings.append({
            "layer": 2,
            "rule": "STRUCTURAL",
            "severity": "INFO",
            "file": "",
            "line": 0,
            "message": f"Structural priors provided to model ({priors_block.count(chr(10))} lines from gator-charter-verify)",
        })
    else:
        user_message = f"DIFF:\n```\n{diff[:diff_limit]}\n```"
    truncated_charters = charter_text[:charter_limit]

    try:
        response_text, usage_info = call_model(
            provider, model, api_key, LAYER2_PROMPT, user_message,
            charter_text=truncated_charters,
        )

        # Report usage if available (cost transparency for the PI)
        if usage_info:
            cache_read = usage_info.get("cache_read_input_tokens", 0)
            cache_created = usage_info.get("cache_creation_input_tokens", 0)
            input_tok = usage_info.get("input_tokens", 0)
            output_tok = usage_info.get("output_tokens", 0)
            usage_parts = [f"{input_tok} input, {output_tok} output"]
            if cache_read:
                usage_parts.append(f"{cache_read} cached (90% savings)")
            elif cache_created:
                usage_parts.append(f"{cache_created} cached for next run")
            findings.append({
                "layer": 2,
                "rule": "USAGE",
                "severity": "INFO",
                "file": "",
                "line": 0,
                "message": f"Token usage ({provider}/{model}): {', '.join(usage_parts)}",
            })

        # Parse JSON findings from response
        json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if json_match:
            model_findings = json.loads(json_match.group())
            for f in model_findings:
                findings.append({
                    "layer": 2,
                    "rule": "CHARTER",
                    "severity": f.get("severity", "MEDIUM"),
                    "file": f.get("file", ""),
                    "line": 0,
                    "message": f.get("finding", ""),
                })
            return findings
        else:
            findings.append({
                "layer": 2,
                "rule": "CHARTER",
                "severity": "INFO",
                "file": "",
                "line": 0,
                "message": f"Charter review ({provider}/{model}): no issues found.",
            })
            return findings

    except ImportError as e:
        pkg = {"anthropic": "anthropic", "openai": "openai", "google": "google-generativeai"}.get(provider, provider)
        findings.append({
            "layer": 2,
            "rule": "SKIP",
            "severity": "INFO",
            "file": "",
            "line": 0,
            "message": f"Package not installed for {provider}: pip install {pkg}",
        })
        return findings
    except Exception as e:
        findings.append({
            "layer": 2,
            "rule": "ERROR",
            "severity": "INFO",
            "file": "",
            "line": 0,
            "message": f"Charter review failed ({provider}/{model}): {str(e)}",
        })
        return findings


# ─── Full Audit (--full mode) ─────────────────────────────────────────
#
# Two-phase approach:
#   Phase 1 (mechanical, free): Parse charters for ### func() entries and
#     Covers: files. Grep code for those function names. Scan code for
#     function declarations not in any charter. Check cross-references.
#   Phase 2 (model, targeted): Send only the discrepancies + relevant
#     function bodies to the model for semantic verification.

# Patterns for detecting function declarations across languages
_FUNC_PATTERNS = [
    # Python: def foo(
    (r'^\s*def\s+(\w+)\s*\(', None),
    # Bash: foo() { or function foo
    (r'^\s*(\w+)\s*\(\)\s*\{', {".sh"}),
    (r'^\s*function\s+(\w+)', {".sh"}),
    # JS/TS: function foo(, async function foo(, export function foo(
    (r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(', {".js", ".ts", ".jsx", ".tsx"}),
    # Go: func Foo(
    (r'^\s*func\s+(\w+)\s*\(', {".go"}),
    # Rust: fn foo(, pub fn foo(
    (r'^\s*(?:pub\s+)?fn\s+(\w+)\s*\(', {".rs"}),
]


def _parse_charter_entries(charter_text):
    """Extract function entries and covered files from a charter.

    Returns (func_entries, covered_files) where func_entries is a list of
    {name, lines} dicts and covered_files is a list of relative paths.
    """
    func_entries = []
    covered_files = []

    lines = charter_text.splitlines()
    for i, line in enumerate(lines):
        # Covers: line
        if line.startswith("**Covers**:") or line.startswith("**Covers:**"):
            covered_files = re.findall(r'`([^`]+)`', line)

        # Function entries: ### name(
        stripped = line.strip()
        if stripped.startswith("### ") and "(" in stripped:
            name = stripped[4:].split("(")[0].strip()
            if name:
                # Capture the entry text (up to next ### or ---)
                entry_lines = [line]
                for j in range(i + 1, min(i + 15, len(lines))):
                    if lines[j].strip().startswith("### ") or lines[j].strip() == "---":
                        break
                    entry_lines.append(lines[j])
                func_entries.append({
                    "name": name,
                    "entry_text": "\n".join(entry_lines),
                })

    return func_entries, covered_files


def _extract_function_body(content, func_name, ext):
    """Extract a function body from source code by name.

    Returns the function signature + body (up to 30 lines) or None.
    """
    lines = content.splitlines()
    for i, line in enumerate(lines):
        # Check if this line declares the function
        for pattern, exts in _FUNC_PATTERNS:
            if exts and ext not in exts:
                continue
            m = re.match(pattern, line)
            if m and m.group(1) == func_name:
                # Capture up to 30 lines of the function body
                end = min(i + 30, len(lines))
                return "\n".join(lines[i:end])
    return None


def _scan_code_functions(filepath, content):
    """Scan a source file for all function declarations.

    Returns list of function names.
    """
    _, ext = os.path.splitext(filepath)
    ext = ext.lower()
    functions = []

    for line in content.splitlines():
        for pattern, exts in _FUNC_PATTERNS:
            if exts and ext not in exts:
                continue
            m = re.match(pattern, line)
            if m:
                name = m.group(1)
                # Skip private/internal in some languages
                if not name.startswith("__"):
                    functions.append(name)
    return functions


def _run_phase1(charter_dir, repo_root):
    """Phase 1: Mechanical charter-vs-code comparison.

    Returns (findings, discrepancies) where discrepancies is a list of
    items that need model review.
    """
    findings = []
    discrepancies = []

    # Load all charters
    charters = {}
    for fname in os.listdir(charter_dir):
        if fname.endswith(".md") and not fname.startswith("_") and fname != "INDEX.md":
            fpath = os.path.join(charter_dir, fname)
            try:
                with open(fpath, encoding="utf-8") as f:
                    charters[fname] = f.read()
            except (OSError, UnicodeDecodeError):
                pass

    if not charters:
        return findings, discrepancies, {}

    # Per-charter analysis
    # Key by (func_name, filepath) to avoid name collisions across files
    all_chartered_funcs = set()   # {(func_name, charter_name)}
    all_code_funcs = []           # [(func_name, filepath)] — list to preserve all
    covered_file_contents = {}    # {filepath: content}
    all_covered_paths = set()     # All files covered by any charter

    for charter_name, charter_text in charters.items():
        func_entries, covered_files = _parse_charter_entries(charter_text)

        # Track chartered function names with charter context
        for entry in func_entries:
            all_chartered_funcs.add((entry["name"], charter_name))

        # Check Covers: files exist and read their contents
        charter_covered_content = ""  # Combined content of all covered files
        for rel_path in covered_files:
            all_covered_paths.add(rel_path)
            full = os.path.join(repo_root, rel_path)
            if not os.path.isfile(full):
                findings.append({
                    "layer": 2, "rule": "AUDIT-MECHANICAL",
                    "severity": "HIGH",
                    "file": charter_name, "line": 0,
                    "message": f"Covers: references '{rel_path}' but file does not exist.",
                })
                continue

            # Read the covered file (cache across charters)
            if rel_path not in covered_file_contents:
                try:
                    with open(full, encoding="utf-8", errors="replace") as f:
                        covered_file_contents[rel_path] = f.read()
                except OSError:
                    continue

            content = covered_file_contents[rel_path]
            charter_covered_content += "\n" + content

            # Scan code for functions — keyed by (name, filepath)
            code_funcs = _scan_code_functions(rel_path, content)
            for func in code_funcs:
                all_code_funcs.append((func, rel_path))

        # Check each chartered function exists in ANY of the covered files
        for entry in func_entries:
            if entry["name"] not in charter_covered_content:
                findings.append({
                    "layer": 2, "rule": "AUDIT-MECHANICAL",
                    "severity": "HIGH",
                    "file": charter_name, "line": 0,
                    "message": (
                        f"Charter documents '{entry['name']}()' but name not found "
                        f"in any Covers: file. Possibly renamed or removed."
                    ),
                })
                discrepancies.append({
                    "type": "stale_entry",
                    "charter": charter_name,
                    "function": entry["name"],
                    "entry_text": entry["entry_text"],
                })

    # Find undocumented functions — check each (name, file) pair individually
    chartered_names = {name for name, _ in all_chartered_funcs}
    for func_name, filepath in all_code_funcs:
        if func_name not in chartered_names:
            if func_name.startswith("_"):
                continue
            findings.append({
                "layer": 2, "rule": "AUDIT-MECHANICAL",
                "severity": "MEDIUM",
                "file": filepath, "line": 0,
                "message": f"Public function '{func_name}()' has no charter entry.",
            })
            content = covered_file_contents.get(filepath, "")
            _, ext = os.path.splitext(filepath)
            body = _extract_function_body(content, func_name, ext.lower())
            if body:
                discrepancies.append({
                    "type": "missing_entry",
                    "function": func_name,
                    "file": filepath,
                    "body": body,
                })

    # Scan for completely unchartered source files in the repo
    # Walk common script/source directories for files not in any Covers: line
    SOURCE_EXTENSIONS = {".py", ".sh", ".js", ".ts", ".go", ".rs", ".java", ".gd"}
    SCAN_DIRS = ["gator-command/scripts", "scripts", "src", "lib", "app"]
    for scan_dir in SCAN_DIRS:
        scan_path = os.path.join(repo_root, scan_dir)
        if not os.path.isdir(scan_path):
            continue
        for fname in os.listdir(scan_path):
            _, ext = os.path.splitext(fname)
            if ext.lower() not in SOURCE_EXTENSIONS:
                continue
            rel_path = os.path.join(scan_dir, fname).replace("\\", "/")
            if rel_path not in all_covered_paths:
                findings.append({
                    "layer": 2, "rule": "AUDIT-MECHANICAL",
                    "severity": "HIGH",
                    "file": rel_path, "line": 0,
                    "message": (
                        f"Source file '{rel_path}' is not in any charter's Covers: line. "
                        f"No charter governs this module."
                    ),
                })

    # Check cross-references (← / →) in charters
    # Skip common names that appear everywhere and aren't meaningful to verify
    XREF_SKIP = {"main", "init", "setup", "run", "start", "test"}
    for charter_name, charter_text in charters.items():
        for line in charter_text.splitlines():
            # Look for ← func_name() or → func_name() references
            for arrow_match in re.finditer(r'[←→]\s+(\w+)\(\)', line):
                ref_name = arrow_match.group(1)
                if ref_name in XREF_SKIP:
                    continue
                # Check if referenced function exists in any covered file
                found = False
                for content in covered_file_contents.values():
                    if ref_name in content:
                        found = True
                        break
                if not found and ref_name not in all_chartered_funcs:
                    findings.append({
                        "layer": 2, "rule": "AUDIT-MECHANICAL",
                        "severity": "MEDIUM",
                        "file": charter_name, "line": 0,
                        "message": (
                            f"Cross-reference to '{ref_name}()' but function not "
                            f"found in any covered file."
                        ),
                    })

    return findings, discrepancies, charters


def _run_phase2(discrepancies, charters, config):
    """Phase 2: Send only discrepancies to the model for semantic review.

    Instead of sending entire source files, sends:
    - Stale entries: charter entry text (what to verify)
    - Missing entries: function body + charter overview (should this be documented?)
    - Cross-cutting: summary of Phase 1 findings for TRIPWIRE check
    """
    l23 = config.get("layer2_3", {})
    provider = l23.get("provider", "anthropic")
    model = l23.get("model", "claude-sonnet-4-6")
    api_key_env = l23.get("api_key_env", "ANTHROPIC_API_KEY")
    findings = []

    if not discrepancies:
        return findings

    if provider == "none":
        return findings

    api_key = None
    if provider != "ollama":
        api_key = os.environ.get(api_key_env)
        if not api_key:
            return [{
                "layer": 2, "rule": "SKIP", "severity": "INFO",
                "file": "", "line": 0,
                "message": (
                    f"{api_key_env} not set — Phase 2 (model review of "
                    f"{len(discrepancies)} discrepancies) skipped."
                ),
            }]

    # Build focused prompt with only the discrepancies
    sections = []
    for d in discrepancies[:30]:  # Cap to prevent runaway token usage
        if d["type"] == "stale_entry":
            sections.append(
                f"STALE? Charter '{d['charter']}' documents '{d['function']}()' "
                f"but the name was not found in covered files.\n"
                f"Charter entry:\n{d['entry_text']}\n"
                f"Question: Is this function gone, renamed, or moved?"
            )
        elif d["type"] == "missing_entry":
            sections.append(
                f"UNDOCUMENTED? '{d['function']}()' in {d['file']} has no charter entry.\n"
                f"Function body:\n{d['body']}\n"
                f"Question: Is this a public function that should be chartered, "
                f"or an internal helper that's fine without one?"
            )

    if not sections:
        return findings

    # Build charter summary for context (not full text — just Owns/Does Not Own)
    charter_summary = ""
    for name, text in charters.items():
        summary_lines = []
        for line in text.splitlines()[:20]:  # First 20 lines captures Owns/Does Not Own
            summary_lines.append(line)
        charter_summary += f"\n--- {name} ---\n" + "\n".join(summary_lines) + "\n"

    user_message = (
        f"Phase 1 mechanical analysis found {len(discrepancies)} discrepancies.\n"
        f"Review each and assess whether it's a real problem or a false positive.\n\n"
        + "\n---\n".join(sections)
    )

    try:
        phase2_prompt = (
            "You are an enforcer reviewing charter-vs-code discrepancies found by "
            "mechanical analysis. For each item, determine if it's a real drift "
            "problem or a false positive (e.g., the function was intentionally "
            "removed, or the 'undocumented' function is genuinely internal).\n\n"
            "Output ONLY a JSON array of real problems (exclude false positives):\n"
            '[{"severity": "HIGH|MEDIUM", "file": "path", "finding": "description"}]\n\n'
            "If all discrepancies are false positives, output: []"
        )

        response_text, usage_info = call_model(
            provider, model, api_key, phase2_prompt, user_message,
            charter_text=charter_summary,
        )

        if usage_info:
            cache_read = usage_info.get("cache_read_input_tokens", 0)
            cache_created = usage_info.get("cache_creation_input_tokens", 0)
            input_tok = usage_info.get("input_tokens", 0)
            output_tok = usage_info.get("output_tokens", 0)
            usage_parts = [f"{input_tok} input, {output_tok} output"]
            if cache_read:
                usage_parts.append(f"{cache_read} cached (90% savings)")
            elif cache_created:
                usage_parts.append(f"{cache_created} cached for next run")
            findings.append({
                "layer": 2, "rule": "USAGE", "severity": "INFO",
                "file": "", "line": 0,
                "message": (
                    f"Phase 2 model review ({provider}/{model}): "
                    + ", ".join(usage_parts)
                ),
            })

        json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if json_match:
            model_findings = json.loads(json_match.group())
            for f in model_findings:
                findings.append({
                    "layer": 2,
                    "rule": "AUDIT-MODEL",
                    "severity": f.get("severity", "MEDIUM"),
                    "file": f.get("file", ""),
                    "line": 0,
                    "message": f.get("finding", ""),
                })

        return findings

    except ImportError as e:
        pkg = {"anthropic": "anthropic", "openai": "openai", "google": "google-generativeai"}.get(provider, provider)
        return [{
            "layer": 2, "rule": "SKIP", "severity": "INFO",
            "file": "", "line": 0,
            "message": f"Package not installed for {provider}: pip install {pkg}",
        }]
    except Exception as e:
        return [{
            "layer": 2, "rule": "ERROR", "severity": "INFO",
            "file": "", "line": 0,
            "message": f"Phase 2 model review failed ({provider}/{model}): {str(e)}",
        }]


def run_full_audit(config):
    """Run a comprehensive two-phase charter-vs-code audit.

    Phase 1 (mechanical, free): Parse charters, grep code for function names,
    scan for undocumented functions, check cross-references. Catches ~70% of
    drift without a model.

    Phase 2 (model, targeted): Send only the discrepancies from Phase 1 to the
    model with function-level snippets (not whole files). The model classifies
    each as real drift or false positive.
    """
    repo_root = os.getcwd()
    charter_dir = _resolve_primary_charter_dir(repo_root)

    if not os.path.isdir(charter_dir):
        return [{
            "layer": 2, "rule": "SKIP", "severity": "INFO",
            "file": "", "line": 0,
            "message": "No charters found — cannot run full audit.",
        }]

    # Phase 1: Mechanical
    phase1_findings, discrepancies, charters = _run_phase1(charter_dir, repo_root)

    all_findings = []
    all_findings.extend(phase1_findings)

    # Summary of Phase 1
    mechanical_issues = len([f for f in phase1_findings if f["severity"] != "INFO"])
    all_findings.append({
        "layer": 2, "rule": "AUDIT-SUMMARY", "severity": "INFO",
        "file": "", "line": 0,
        "message": (
            f"Phase 1 (mechanical): scanned {len(charters)} charters, "
            f"found {mechanical_issues} issue(s), "
            f"{len(discrepancies)} sent to model for verification."
        ),
    })

    # Phase 2: Model review of discrepancies only
    if discrepancies:
        phase2_findings = _run_phase2(discrepancies, charters, config)
        all_findings.extend(phase2_findings)

    return all_findings


# ─── Output Formatting ────────────────────────────────────────────────

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}


def format_findings(findings, fmt="text"):
    """Format findings for the primary agent to read."""
    if not findings:
        return "Enforcer review: clean. No findings."

    findings.sort(key=lambda f: SEVERITY_ORDER.get(f["severity"], 5))

    if fmt == "json":
        return json.dumps(findings, indent=2)

    # Separate real findings from informational messages
    real = [f for f in findings if f["severity"] not in ("INFO",)]
    info = [f for f in findings if f["severity"] == "INFO"]

    lines = []

    if real:
        lines.append(f"Enforcer Review — {len(real)} finding(s)")
        lines.append("=" * 50)
        for f in real:
            sev = f["severity"]
            loc = f["file"]
            if f.get("line", 0) > 0:
                loc += f":{f['line']}"
            lines.append(f"[{sev}] {f['rule']} — {loc}")
            lines.append(f"  {f['message']}")
            if f.get("match"):
                lines.append(f"  > {f['match']}")
            lines.append("")
    else:
        lines.append("Enforcer Review — clean")
        lines.append("=" * 50)
        lines.append("  No issues found.")
        lines.append("")

    # Append info messages (usage, skips) at the end, clearly labeled
    if info:
        for f in info:
            rule = f["rule"]
            if rule == "SKIP":
                lines.append(f"  Note: {f['message']}")
            elif rule == "USAGE":
                lines.append(f"  {f['message']}")
            else:
                lines.append(f"  [{rule}] {f['message']}")
            lines.append("")

    return "\n".join(lines)


def append_to_whiteboard(output, review_type="enforcer-review.py"):
    """Write findings to whiteboard.md — the authoritative Architect-visible record.

    The findings are also printed to stdout by the caller, so this does NOT hide
    them from the primary agent. The trust boundary is behavioral: the agent
    presents the whiteboard findings to the Architect and does not act on them
    unprompted. Fully agent-blind review requires the Architect running an
    enforcer independently in a separate terminal.
    """
    from datetime import datetime, timezone

    whiteboard_path = os.path.join(
        os.path.dirname(SCRIPT_DIR), "whiteboard.md"
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    header = f"\n## Review — {timestamp} — {review_type}\n\n"

    # Read existing content
    existing = ""
    if os.path.isfile(whiteboard_path):
        with open(whiteboard_path, encoding="utf-8") as f:
            existing = f.read()

    # Append new review
    with open(whiteboard_path, "w", encoding="utf-8") as f:
        f.write(existing.rstrip() + "\n" + header + output + "\n")

    # Check size and warn if rotation needed
    line_count = existing.count("\n") + header.count("\n") + output.count("\n")
    if line_count > 100:
        print(
            f"Note: whiteboard.md is now ~{line_count} lines. "
            f"Consider archiving older reviews to artifacts/review-log.md."
        )


# ─── Main ─────────────────────────────────────────────────────────────

def main():
    ensure_utf8_stdout()

    parser = argparse.ArgumentParser(description="Enforcer review — charter-grounded linter")
    parser.add_argument("--files", help="Comma-separated file paths to review")
    parser.add_argument("--staged", action="store_true", help="Review git staged changes")
    parser.add_argument("--full", action="store_true",
                        help="Comprehensive charter-vs-code audit (reads all charters and all covered code, no diff needed)")
    parser.add_argument("--layer", default="all", help="Which layers to run: 1, 2, 3, or all")
    parser.add_argument("--format", default="text", choices=["text", "json"], help="Output format")
    parser.add_argument(
        "--no-whiteboard", action="store_true",
        help="Skip writing to .gator/whiteboard.md (stdout only)"
    )
    args = parser.parse_args()

    config = load_config()

    # Full audit mode — reads all charters and covered code, no diff
    if args.full:
        all_findings = run_full_audit(config)
        output = format_findings(all_findings, fmt=args.format)
        print(output)
        if not args.no_whiteboard:
            append_to_whiteboard(output, review_type="enforcer-review.py (full audit)")
            print(f"\n\u2192 Findings written to .gator/whiteboard.md")
        if any(f["severity"] in ("HIGH", "CRITICAL") for f in all_findings):
            sys.exit(1)
        return

    # Determine files to review
    if args.files:
        files = [f.strip() for f in args.files.split(",")]
    elif args.staged:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"Error: git diff --cached failed: {result.stderr.strip()}")
            sys.exit(1)
        files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    else:
        # Default: all modified files (tracked changes + untracked files)
        files = []

        # Modified tracked files
        result = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"Error: git diff failed: {result.stderr.strip()}")
            sys.exit(1)
        files.extend(f.strip() for f in result.stdout.strip().split("\n") if f.strip())

        # Staged files
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            files.extend(f.strip() for f in result.stdout.strip().split("\n") if f.strip())

        # Untracked files (not ignored)
        result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            capture_output=True, text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            files.extend(f.strip() for f in result.stdout.strip().split("\n") if f.strip())

        # Deduplicate while preserving order
        seen = set()
        unique_files = []
        for f in files:
            if f not in seen:
                seen.add(f)
                unique_files.append(f)
        files = unique_files

    if not files:
        print("No files to review. No modified, staged, or untracked files found.")
        return

    all_findings = []
    layer = args.layer

    # Layer 1: Mechanical lint (always fast, no model)
    if layer in ("1", "all"):
        all_findings.extend(run_layer1(files))

    # Layer 2-3: Charter-grounded review (needs model)
    if layer in ("2", "3", "all"):
        diff = get_diff_for_files(files)
        if diff:
            all_findings.extend(run_layer2_3(files, diff, config))

    output = format_findings(all_findings, fmt=args.format)
    print(output)

    # Write to whiteboard by default — the authoritative Architect-visible record
    if not args.no_whiteboard:
        review_type = f"enforcer-review.py (Layer {args.layer})"
        append_to_whiteboard(output, review_type=review_type)
        print(f"\n→ Findings written to .gator/whiteboard.md")

    # Exit code: non-zero if any HIGH or CRITICAL findings
    if any(f["severity"] in ("HIGH", "CRITICAL") for f in all_findings):
        sys.exit(1)


if __name__ == "__main__":
    main()
