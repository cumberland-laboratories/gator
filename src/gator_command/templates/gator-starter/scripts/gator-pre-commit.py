#!/usr/bin/env python3
"""
gator-pre-commit.py — Deterministic governance gate for gator-managed repos.

Called from three git hooks:
  pre-commit:  --phase validate
  commit-msg:  --phase trailers <msg-file>
  post-commit: --phase cleanup

Phase 1 (validate): Checks structural rules, writes status.json and
whiteboard.md, stages both. Blocks the commit if hard rules fail.

Phase 2 (trailers): Reads commit_draft.md frontmatter and .gator/ state,
assembles Gator-* trailers, appends them to the commit message.

Phase 3 (cleanup): Resets .gator/commit_draft.md to the blank stub after a
successful commit so stale content does not leak into the next session.

No LLM. No interpretation. Same result every time regardless of which
model produced the session work or how deep into context it was.

@reads: .gator/, commit_draft.md, git diff --cached
@writes: .gator/status.json, .gator/whiteboard.md, commit message (trailers),
         .gator/commit_draft.md
@does-not-own: the code changes themselves (the LLM/PI did that)
"""

import argparse
import io
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Submodules live alongside this script — add script dir to path
_script_dir = str(Path(__file__).resolve().parent)
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from precommit_lint import (  # noqa: E402
    LINT_RULES,
    DANGEROUS_FILENAMES,
    DANGEROUS_PREFIXES,
    DANGEROUS_SAFE,
    parse_diff_added_lines,
    load_lint_allowlist,
    _effective_severity,
    run_layer1_lint,
)
from precommit_charter import (  # noqa: E402
    CHARTER_SCAFFOLD_FILES,
    _check_charter_function_refs,
    _detect_new_functions,
    _parse_charter_index,
    _required_charters_for_files,
    _resolve_charter_surface,
    _resolve_charter_dir,
    _iter_charter_files,
    count_charters,
    read_tripwire_patterns,
)
from precommit_session import (  # noqa: E402
    normalize_agent_name,
    _update_frontmatter,
    _extract_note_lines,
    _read_machine_id,
    _read_machine_label,
    _read_vendor_session,
    _derive_intent,
    parse_ledger,
    build_commit_entry,
    render_ledger_block,
    render_snippet_json,
    _infer_vendor_from_agent,
    _reassemble_ledger,
    write_commit_summary,
    record_commit_and_emit_snippet as _record_commit_and_emit_snippet,
)
import precommit_override as override_state  # noqa: E402  (#34, #35)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

def _git_version():
    """Version from git tags, resolved from this script's location."""
    import subprocess
    from pathlib import Path
    # Walk up from script location to find .git
    p = Path(__file__).resolve().parent
    for _ in range(10):
        if (p / ".git").is_dir():
            break
        p = p.parent
    try:
        r = subprocess.run(["git", "describe", "--tags", "--always"],
                           capture_output=True, text=True, cwd=p, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return "dev"

VERSION = _git_version()

# Extensions that don't require a charter update when changed
EXEMPT_EXTENSIONS = {
    ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini",
    ".gitignore", ".gitkeep", ".env.example", ".lock",
}

# Paths that never require a charter update
EXEMPT_PATHS = {
    "LICENSE", "README.md", "CLAUDE.md", "AGENTS.md",
    ".claude/", ".github/", ".vscode/", ".gitignore",
}

COMMIT_DRAFT_STUB = (
    "---\n"
    "message: \"\"\n"
    "change-type:\n"
    "significance:\n"
    "decision-tags: []\n"
    "agent:\n"
    "architect:\n"
    "---\n\n"
    "# Session Change Log\n"
)

# High file count threshold for soft warning
HIGH_FILE_COUNT = 20


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def git(*args, cwd=None):
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


def get_staged_files(repo_root):
    """Return list of staged file paths (relative to repo root)."""
    output = git("diff", "--cached", "--name-only", cwd=repo_root)
    if not output:
        return []
    return [line for line in output.splitlines() if line.strip()]


def get_current_branch(repo_root):
    """Return current branch name."""
    return git("branch", "--show-current", cwd=repo_root) or "unknown"


def stage_file(filepath, repo_root):
    """Stage a single file."""
    git("add", str(filepath), cwd=repo_root)


# ---------------------------------------------------------------------------
# .gator/ state readers (non-charter)
# ---------------------------------------------------------------------------

def find_gator_root(start_path=None):
    """Walk up from start_path looking for .gator/ directory."""
    path = Path(start_path) if start_path else Path.cwd()
    path = path.resolve()
    if (path / ".gator").is_dir():
        return path
    for parent in path.parents:
        if (parent / ".gator").is_dir():
            return parent
    return None


def count_threads(gator_dir):
    """Count threads across active-threads/ and threads/."""
    total = 0
    for subdir_name in ("active-threads", "threads"):
        subdir = gator_dir / subdir_name
        if subdir.is_dir():
            total += len([
                f for f in subdir.iterdir()
                if f.suffix == ".md" and f.name != ".gitkeep"
            ])
    return total


def read_generation(gator_dir):
    """Read generation from .gator-version."""
    version_file = gator_dir / ".gator-version"
    if not version_file.exists():
        return 0
    text = version_file.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if line.startswith("generation:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                return 0
    return 0


def read_policy_version(gator_dir):
    """Read policy version date from command-post.md."""
    cp_file = gator_dir / "command-post.md"
    if not cp_file.exists():
        return None
    text = cp_file.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if line.startswith("version:"):
            return line.split(":", 1)[1].strip()
    return None


def count_issues(gator_dir):
    """Count open/working issues."""
    issues_file = gator_dir / "issues.md"
    if not issues_file.exists():
        return 0
    text = issues_file.read_text(encoding="utf-8", errors="replace")
    count = 0
    for line in text.splitlines():
        if "**Status**: Open" in line or "**Status**: Working" in line:
            count += 1
    return count


# ---------------------------------------------------------------------------
# commit_draft.md parsing
# ---------------------------------------------------------------------------

def parse_commit_draft(gator_dir):
    """Parse commit_draft.md into frontmatter dict and body string.

    Returns (frontmatter, body, error).
    - frontmatter: dict of YAML fields, or {} if no frontmatter
    - body: string of everything after frontmatter
    - error: string if frontmatter is present but malformed, else None
    """
    draft_file = gator_dir / "commit_draft.md"
    if not draft_file.exists():
        return {}, "", None

    text = draft_file.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        return {}, "", None

    # Check for YAML frontmatter (--- delimited)
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            yaml_text = parts[1].strip()
            body = parts[2].strip()
            frontmatter = _parse_simple_yaml(yaml_text)
            if frontmatter is None:
                return {}, body, "Malformed YAML frontmatter in commit_draft.md"
            return frontmatter, body, None

    # No frontmatter — entire file is body
    # Strip the "# Session Change Log" header if present
    lines = text.splitlines()
    body_lines = [l for l in lines if not l.startswith("# ")]
    return {}, "\n".join(body_lines).strip(), None


def _parse_simple_yaml(text):
    """Minimal YAML parser for commit_draft frontmatter.

    Handles flat key: value pairs and simple lists [a, b, c].
    No external dependency needed. Returns None on parse failure.
    """
    result = {}
    try:
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                return None  # malformed
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()

            # Handle YAML list syntax: [a, b, c]
            if value.startswith("[") and value.endswith("]"):
                inner = value[1:-1]
                items = [item.strip().strip("'\"") for item in inner.split(",")]
                result[key] = [i for i in items if i]
            # Handle quoted strings
            elif (value.startswith('"') and value.endswith('"')) or \
                 (value.startswith("'") and value.endswith("'")):
                result[key] = value[1:-1]
            else:
                result[key] = value

        return result
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Fallback heuristics (body text inference)
# ---------------------------------------------------------------------------

def extract_tags_from_body(body):
    """Extract [#tag] patterns from commit_draft body."""
    if not body:
        return []
    tags = set()
    for match in re.finditer(r'\[#([a-zA-Z0-9_-]+)\]', body):
        tags.add(match.group(1))
    return sorted(tags)


def infer_change_type(body, has_code_staged):
    """Infer change type from body tags, gated on staged reality.

    Per Codex review: body-text inference must never produce a stronger
    signal than the staged files justify. If no code is staged, cap at
    docs/policy regardless of tags.
    """
    if not body:
        return None

    text = body.lower()

    if not has_code_staged:
        # No code files staged — this is docs/policy work at most
        if "[#policy]" in text or "[#governance]" in text:
            return "policy"
        return "docs"

    # Code is staged — full inference
    if "[#security]" in text:
        return "security"
    if "[#bugfix]" in text or "[#fix]" in text:
        return "fix"
    if "[#refactor]" in text:
        return "refactor"
    if "[#architecture]" in text or "[#decision]" in text or "[#feature]" in text:
        return "feature"
    if "[#policy]" in text or "[#governance]" in text:
        return "policy"
    if "[#docs]" in text or "[#charter]" in text:
        return "docs"
    return None


def infer_significance(body, charter_changed, has_code_staged):
    """Infer significance from body signals, gated on staged reality.

    Per Codex review: if no code files staged, cap at routine regardless
    of tags in the body.
    """
    if not body or not has_code_staged:
        return "routine"

    text = body.lower()
    if any(tag in text for tag in ["[#security]", "[#architecture]", "[#breaking]"]):
        return "high"
    if charter_changed or "[#decision]" in text or "[#feature]" in text:
        return "notable"
    return "routine"


def detect_agent_from_body(body):
    """Extract agent attribution from body text."""
    if not body:
        return None
    agents = set()
    for line in body.splitlines():
        stripped = line.rstrip()
        # Match org policy format: -claude, -codex, -gemini at end of line
        if stripped.endswith("-claude"):
            agents.add("claude")
        elif stripped.endswith("-codex"):
            agents.add("codex")
        elif stripped.endswith("-gemini"):
            agents.add("gemini")
        # Also match — claude, — codex style
        for model in ("claude", "codex", "gemini"):
            if f"— {model}" in stripped.lower():
                agents.add(model)
    if agents:
        return ",".join(sorted(agents))
    return None


def detect_architect_from_body(body):
    """Extract Architect attribution from body text.

    Per Codex review: must match the actual org policy format (— AG),
    not the old -pi suffix pattern. If no real value found, return None
    rather than 'architect'.
    """
    if not body:
        return None
    for line in body.splitlines():
        # Match "— AG" or "— JD" (em dash + space + 2-4 uppercase letters)
        match = re.search(r'—\s+([A-Z]{2,4})(?:\s|$)', line)
        if match:
            return match.group(1)
    return None


# ---------------------------------------------------------------------------
# File classification & override mechanism
# ---------------------------------------------------------------------------

def classify_staged_files(staged_files, _charter_patterns_cache=[None]):
    """Classify staged files into code and charter changes.

    Returns (has_code, has_charter, code_files, charter_files).
    Uses the resolved charter directory to identify charter files.
    """
    # Resolve charter path patterns once per process
    if _charter_patterns_cache[0] is None:
        try:
            repo_root = Path.cwd()
            for _ in range(10):
                if (repo_root / ".gator").is_dir():
                    break
                repo_root = repo_root.parent
            surface = _resolve_charter_surface(repo_root)
            charter_dir = surface[0]
            # Build both absolute and relative patterns for matching
            # Git staged paths are relative; resolved dir is absolute
            abs_str = str(charter_dir).replace("\\", "/")
            try:
                rel_str = str(charter_dir.relative_to(repo_root)).replace("\\", "/")
            except ValueError:
                rel_str = abs_str
            _charter_patterns_cache[0] = [
                rel_str + "/",   # relative: gator-command/charters/
                abs_str + "/",   # absolute: C:/.../gator-command/charters/
                ".gator/charters/",  # always recognize standard path
            ]
        except Exception:
            _charter_patterns_cache[0] = [".gator/charters/"]

    charter_patterns = _charter_patterns_cache[0]

    code_files = []
    charter_files = []

    for f in staged_files:
        # Normalize path separators
        f_normalized = f.replace("\\", "/")

        # Charter files — match against resolved charter directory patterns
        is_charter = any(p in f_normalized for p in charter_patterns)
        if is_charter:
            basename = f_normalized.split("/")[-1]
            if basename not in CHARTER_SCAFFOLD_FILES:
                charter_files.append(f)
            continue

        # Other .gator/ internal files — exempt
        if ".gator/" in f_normalized:
            continue

        # Check exempt paths
        is_exempt = False
        for exempt in EXEMPT_PATHS:
            if f_normalized.startswith(exempt) or f_normalized == exempt:
                is_exempt = True
                break
        if is_exempt:
            continue

        # Check exempt extensions
        _, ext = os.path.splitext(f_normalized)
        if ext.lower() in EXEMPT_EXTENSIONS:
            continue

        # Everything else is a code file
        code_files.append(f)

    return bool(code_files), bool(charter_files), code_files, charter_files


# The v1 override flow (check_override / _write_override_request / the
# legacy .gator/.override bypass) was replaced by the tree-bound
# block/approval envelope in precommit_override.py (#34, #35). See
# scripts-precommit.md and phase_validate() below.


# ---------------------------------------------------------------------------
# Validation rules
# ---------------------------------------------------------------------------

# Sync obligation: this enum MUST stay byte-consistent with the
# `change_type` enum in `contracts/schemas/gator-session-snippet-v2.json`
# (`properties.change_type.enum`). Both surfaces are read by the same
# schema-validation test (`contracts/compatibility/test_snippet_schema.py`),
# so drift here would let a bad value pass pre-commit only to be caught
# later by CI on the emitted session snippet — the exact failure mode
# this validation exists to prevent. If either enum changes, change
# both in the same commit.
VALID_CHANGE_TYPES = frozenset({
    "feature", "fix", "refactor", "docs", "test",
    "release", "maintenance", "review", "governance", "",
})

# Sync obligation: this enum MUST stay byte-consistent with the
# `significance` enum in `contracts/schemas/gator-session-snippet-v2.json`
# (`properties.significance.enum`). Added 2026-08-10 (v2.6.0) per the
# smoke-test finding that surfaced 5 pre-existing snippets with `"medium"`
# (not in enum) and 8 with `"architectural"` (which we then added to the
# enum since it's a legitimate value that had been in de facto use). Gate
# added to prevent future drift, mirroring v2.5.3's change-type gate. If
# either enum changes, change both in the same commit.
VALID_SIGNIFICANCE = frozenset({
    "low", "minor", "routine", "notable", "high", "critical",
    "architectural", "",
})


def validate_hard_rules(staged_files, frontmatter, body, parse_error, gator_dir, override=None):
    """Check hard rules. Returns list of (rule_name, message) for failures."""
    failures = []

    # 1. Frontmatter parse failure
    if parse_error:
        failures.append(("frontmatter-parse", parse_error))

    # 1a. change-type enum validation (must match schema)
    # Blocks values like "bugfix" that read plausibly but fail the
    # gator-session-snippet-v2 schema at CI validation. `None` is
    # allowed (agent may omit the field entirely; infer_change_type
    # fills a default at trailer-assembly time).
    change_type = frontmatter.get("change-type")
    if change_type is not None and change_type not in VALID_CHANGE_TYPES:
        valid_str = ", ".join(sorted(v for v in VALID_CHANGE_TYPES if v))
        failures.append((
            "invalid-change-type",
            f"change-type: {change_type!r} is not one of the schema-legal "
            f"values. Valid: {valid_str} (or empty). Common typos: "
            f"'bugfix' -> 'fix', 'chore' -> 'maintenance', 'style' -> "
            f"'refactor'. Update .gator/commit_draft.md and retry."
        ))

    # 1b. significance enum validation (must match schema) — added 2026-08-10
    # (v2.6.0) per smoke-test finding. Mirrors 1a's shape. `None` is
    # allowed (agent may omit; infer_significance fills at trailer time).
    significance = frontmatter.get("significance")
    if significance is not None and significance not in VALID_SIGNIFICANCE:
        valid_str = ", ".join(sorted(v for v in VALID_SIGNIFICANCE if v))
        failures.append((
            "invalid-significance",
            f"significance: {significance!r} is not one of the schema-legal "
            f"values. Valid: {valid_str} (or empty). Common typos: "
            f"'medium' -> 'notable', 'major' -> 'high', 'trivial' -> "
            f"'routine'. Update .gator/commit_draft.md and retry."
        ))

    # 2. Empty commit_draft
    if not frontmatter and not body:
        failures.append((
            "empty-commit-draft",
            "commit_draft.md is empty or missing. The agent must document "
            "what changed and why before committing."
        ))

    # 3. Charter-alongside-code
    has_code, has_charter, code_files, charter_files_staged = classify_staged_files(staged_files)

    if has_code and override != "charter-skip":
        files_str = ", ".join(code_files[:5])
        if len(code_files) > 5:
            files_str += f" (and {len(code_files) - 5} more)"

        if not has_charter:
            # No charter at all — block. Use INDEX to tell the agent
            # exactly which charters are needed.
            required = _required_charters_for_files(code_files, gator_dir.parent)
            if required:
                charters_str = ", ".join(sorted(required))
                failures.append((
                    "charter-alongside-code",
                    f"Code files changed ({files_str}) but no charters "
                    f"were updated. INDEX.md requires: {charters_str}. "
                    f"Update the affected charters and retry."
                ))
            else:
                failures.append((
                    "charter-alongside-code",
                    f"Code files changed ({files_str}) but no charters "
                    f"were updated. "
                    f"Update the affected charters and retry."
                ))
        else:
            # Charter(s) staged — check if all INDEX-required charters
            # are covered. This catches the case where the module charter
            # is staged but cross-cutting (or another required charter)
            # is not.
            required = _required_charters_for_files(code_files, gator_dir.parent)
            if required:
                staged_names = set()
                for f in charter_files_staged:
                    fn = f.replace("\\", "/").rsplit("/", 1)[-1]
                    staged_names.add(fn)
                missing = required - staged_names
                if missing:
                    missing_str = ", ".join(sorted(missing))
                    failures.append((
                        "charter-index-gap",
                        f"Code files changed ({files_str}). INDEX.md requires "
                        f"charters: {', '.join(sorted(required))}. "
                        f"Missing from staged files: {missing_str}. "
                        f"Update the missing charters and retry."
                    ))

    # 4. Missing commit message
    has_message = bool(frontmatter.get("message"))
    # The stub heading "# Session Change Log" alone should not count
    # as real body content. Only strip that exact stub line — preserve
    # all other #-prefixed lines (e.g. "#123 fix", markdown headings).
    _STUB_HEADING = "# Session Change Log"
    body_lines = [l for l in (body or "").splitlines()
                  if l.strip() and l.strip() != _STUB_HEADING]
    has_body_content = bool(body_lines)
    if not has_message and not has_body_content:
        failures.append((
            "missing-message",
            "No commit message found. Add a 'message' field to "
            "commit_draft.md frontmatter, or add content to the body."
        ))

    return failures


def validate_soft_rules(staged_files, frontmatter, body, gator_dir):
    """Check soft rules. Returns list of (rule_name, message) for warnings."""
    warnings = []

    has_code, has_charter, code_files, _ = classify_staged_files(staged_files)

    # 1. No significance assessment
    if has_code and not frontmatter.get("significance"):
        inferred = infer_significance(body, has_charter, has_code)
        if inferred == "routine":
            warnings.append((
                "no-significance",
                "commit_draft.md has no 'significance' field and no "
                "inferrable signals. Consider adding a significance "
                "assessment before committing."
            ))

    # 2. No decision tags
    if not frontmatter.get("decision-tags") and not extract_tags_from_body(body):
        warnings.append((
            "no-decision-tags",
            "No decision tags found in commit_draft.md frontmatter or body. "
            "Untagged commits are harder to query later."
        ))

    # 3. Tripwire files touched
    tripwires = read_tripwire_patterns(gator_dir)
    if tripwires:
        touched = []
        for f in staged_files:
            f_normalized = f.replace("\\", "/")
            for pattern in tripwires:
                if pattern in f_normalized or f_normalized.endswith(pattern):
                    touched.append(f)
                    break
        if touched:
            files_str = ", ".join(touched[:3])
            warnings.append((
                "tripwire-touched",
                f"Tripwire-tagged file(s) touched: {files_str}. "
                f"Verify the PI is aware of these changes."
            ))

    # 4. High file count
    if len(staged_files) > HIGH_FILE_COUNT:
        warnings.append((
            "high-file-count",
            f"{len(staged_files)} files staged (threshold: {HIGH_FILE_COUNT}). "
            f"Large commits may indicate skipped incremental steps."
        ))

    # 5. Charter function-name smoke test: check that ### func() entries in
    #    staged charters still reference functions that exist in the code.
    if has_charter:
        _, _, _, charter_files = classify_staged_files(staged_files)
        stale_refs = _check_charter_function_refs(
            charter_files, gator_dir.parent
        )
        if stale_refs:
            refs_str = ", ".join(stale_refs[:5])
            if len(stale_refs) > 5:
                refs_str += f" (+{len(stale_refs) - 5} more)"
            warnings.append((
                "stale-charter-refs",
                f"Charter references function(s) not found in covered files: "
                f"{refs_str}. Verify these weren't renamed or removed."
            ))

    # 6. New code functions without charter entries: if code added new def/func
    #    lines but charter didn't add corresponding ### entries, warn.
    #    Compares specific names, not just counts — adding an unrelated charter
    #    entry doesn't suppress the warning for undocumented functions.
    if has_code and has_charter:
        new_code_funcs, new_charter_entries = _detect_new_functions(
            staged_files, gator_dir.parent
        )
        charter_entry_names = set(new_charter_entries)
        undocumented = [f for f in new_code_funcs if f not in charter_entry_names]
        if undocumented:
            funcs_str = ", ".join(undocumented[:5])
            if len(undocumented) > 5:
                funcs_str += f" (+{len(undocumented) - 5} more)"
            warnings.append((
                "new-functions-undocumented",
                f"New function(s) in code ({funcs_str}) without matching ### "
                f"entries in charters. Consider documenting them."
            ))

    # 7. Cross-module imports — now enforced as a hard block in
    #    validate_hard_rules() when cross-cutting charter is not staged.
    #    No soft warning needed; the hard check covers it.

    return warnings


# ---------------------------------------------------------------------------
# Trailer assembly
# ---------------------------------------------------------------------------

def assemble_trailers(frontmatter, body, gator_dir, staged_files, override=None,
                      handoff=None):
    """Build Gator-* trailer lines from all available sources.

    ``handoff`` is the validate->commit-msg override handoff (read via
    ``override_state.read_handoff`` for the current tree). ``override`` is
    retained for signature compatibility and is ignored.
    """
    charter_count, func_count = count_charters(gator_dir)
    thread_count = count_threads(gator_dir)
    generation = read_generation(gator_dir)
    policy_version = read_policy_version(gator_dir)
    issue_count = count_issues(gator_dir)

    _, has_charter, _, _ = classify_staged_files(staged_files)
    has_code, _, _, _ = classify_staged_files(staged_files)

    trailers = []

    # Core metrics (always from file state — deterministic)
    trailers.append(f"Gator-Charters: {charter_count}")
    trailers.append(f"Gator-Functions: {func_count}")
    trailers.append(f"Gator-Threads: {thread_count}")
    trailers.append(f"Gator-Generation: {generation}")

    if policy_version:
        trailers.append(f"Gator-Policy-Version: {policy_version}")
    if issue_count > 0:
        trailers.append(f"Gator-Issues: {issue_count}")

    # Charter changed (from git diff --cached — deterministic), unless an
    # Architect approval for this exact tree overrode a charter rule.
    if handoff and handoff.get("charter_override"):
        trailers.append("Gator-Charter-Changed: override-skip")
    else:
        trailers.append(f"Gator-Charter-Changed: {'yes' if has_charter else 'no'}")
    # Durable, sanitized audit of any approval used (#34 Phase F). The
    # handoff is only read here — it is consumed in post-commit.
    trailers.extend(override_state.override_trailers(handoff))

    # Change type (frontmatter preferred, fallback to inference)
    change_type = frontmatter.get("change-type") or infer_change_type(body, has_code)
    if change_type:
        trailers.append(f"Gator-Change-Type: {change_type}")

    # Decision tags (frontmatter preferred, fallback to body extraction)
    tags = frontmatter.get("decision-tags")
    if isinstance(tags, list):
        tag_str = ",".join(tags)
    elif isinstance(tags, str):
        tag_str = tags
    else:
        extracted = extract_tags_from_body(body)
        tag_str = ",".join(extracted) if extracted else ""
    if tag_str:
        trailers.append(f"Gator-Decision-Tags: {tag_str}")

    # Significance (frontmatter preferred, fallback to inference)
    significance = (
        frontmatter.get("significance")
        or infer_significance(body, has_charter, has_code)
    )
    trailers.append(f"Gator-Significance: {significance}")

    # Agent attribution (frontmatter preferred, fallback to body)
    agent = frontmatter.get("agent") or detect_agent_from_body(body)
    if agent:
        trailers.append(f"Gator-Agent: {agent}")

    # Architect attribution (frontmatter preferred, fallback to body)
    # Accepts both "architect:" (current) and "pi:" (legacy) from frontmatter
    architect = frontmatter.get("architect") or frontmatter.get("pi") or detect_architect_from_body(body)
    if architect:
        trailers.append(f"Gator-Architect: {architect}")

    # Machine identity trailer (2026-08-08 transcripts-first MVP Phase 6).
    # Sourced from ~/.gator/machine-id, which is populated on first
    # `gator init` via `gator machine-id`. Silent no-op when the file is
    # absent — standalone base-gator use on a machine that never activated
    # Enterprise (or that predates the file) still commits without a
    # trailer rather than failing the hook. The Enterprise linkage
    # pipeline consumes this trailer to correlate commit → machine in the
    # `commits` row (see enterprise/app/routes/ingest.py::ingest_commits
    # for the consumer side and 2026-08-08-transcripts-first ADR D4 for
    # the trust-boundary reasoning behind this being a client-emitted
    # trailer, not a server-supplied evidence-id).
    machine_id = _read_machine_id()
    if machine_id:
        trailers.append(f"Gator-Machine-Id: {machine_id}")

    return trailers


# ---------------------------------------------------------------------------
# Status snapshot
# ---------------------------------------------------------------------------

def build_status(gator_dir, staged_files, frontmatter, body, handoff=None):
    """Build the status.json content.

    ``handoff`` is the override handoff for this attempt (None when no
    approval was used); a charter override records ``override-skip``.
    """
    charter_count, func_count = count_charters(gator_dir)
    thread_count = count_threads(gator_dir)
    generation = read_generation(gator_dir)
    policy_version = read_policy_version(gator_dir)
    issue_count = count_issues(gator_dir)

    has_code, has_charter, _, _ = classify_staged_files(staged_files)

    change_type = frontmatter.get("change-type") or infer_change_type(body, has_code)
    significance = (
        frontmatter.get("significance")
        or infer_significance(body, has_charter, has_code)
    )

    tags = frontmatter.get("decision-tags")
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]
    elif not isinstance(tags, list):
        tags = extract_tags_from_body(body)

    agent = frontmatter.get("agent") or detect_agent_from_body(body)
    architect = frontmatter.get("architect") or frontmatter.get("pi") or detect_architect_from_body(body)

    charter_changed = ("override-skip"
                       if handoff and handoff.get("charter_override")
                       else has_charter)

    return {
        "repo": gator_dir.parent.name,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "branch": get_current_branch(gator_dir.parent),
        "charters": charter_count,
        "functions": func_count,
        "threads": thread_count,
        "generation": generation,
        "policy_version": policy_version,
        "issues": issue_count,
        "charter_changed": charter_changed,
        "change_type": change_type,
        "significance": significance,
        "decision_tags": tags,
        "agent": agent,
        "architect": architect,
        "draft_body": body.strip(),
        "files_touched": [str(f) for f in staged_files],
    }


def write_status_json(gator_dir, status):
    """Write .gator/status.json."""
    status_file = gator_dir / "status.json"
    status_file.write_text(
        json.dumps(status, indent=2) + "\n",
        encoding="utf-8",
    )
    return status_file


# ---------------------------------------------------------------------------
# Whiteboard & output artifacts
# ---------------------------------------------------------------------------

def write_whiteboard(gator_dir, failures, warnings, handoff,
                     enforcement_level="strict"):
    """Write findings to .gator/whiteboard.md.

    ``handoff`` is the override handoff used by this attempt, or None.
    """
    whiteboard = gator_dir / "whiteboard.md"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines = [
        "# Enforcer Whiteboard",
        "",
        f"Last updated: {timestamp} (pre-commit hook)",
        "",
    ]

    if enforcement_level == "off":
        lines.append("**Enforcement level: off** — governance checks disabled.")
        lines.append("")
    elif enforcement_level == "warn":
        lines.append("**Enforcement level: warn** — findings are advisory, "
                      "commit was not blocked.")
        lines.append("")

    if failures:
        lines.append("## Blocked")
        lines.append("")
        for rule, msg in failures:
            lines.append(f"- **{rule}**: {msg}")
        lines.append("")

    if warnings:
        lines.append("## Warnings")
        lines.append("")
        for rule, msg in warnings:
            lines.append(f"- **{rule}**: {msg}")
        lines.append("")

    if handoff:
        lines.append("## Overrides")
        lines.append("")
        rules = ", ".join(handoff.get("overridden_rules", [])) or "?"
        lines.append(
            f"- **Gator-Override**: {rules} (committed at {timestamp})"
            f" — approved by {handoff.get('approved_by', '?')}"
            f" — reason: {handoff.get('reason', '')}"
            f" — block: {handoff.get('block_id', '?')}")
        lines.append("")

    if not failures and not warnings and not handoff:
        lines.append("No findings.")
        lines.append("")

    whiteboard.write_text("\n".join(lines), encoding="utf-8")
    return whiteboard


def write_commit_issues(gator_dir, findings):
    """Write lint findings to .gator/commit_issues.md for PI review."""
    ci_file = gator_dir / "commit_issues.md"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines = [
        "# Commit Issues",
        "",
        f"Lint findings from pre-commit hook — {timestamp}",
        "",
        "Review each finding. HIGH/CRITICAL findings block the commit: fix them,",
        "or the Architect approves this exact staged change with `gator hook approve`.",
        "The agent must not approve its own findings.",
        "",
    ]

    for f in findings:
        sev = f["severity"]
        lines.append(f"- **{sev}** `{f['rule']}` in `{f['file']}:{f['line']}`")
        lines.append(f"  {f['message']}")
        if f.get("match"):
            lines.append(f"  `> {f['match']}`")
        lines.append("")

    ci_file.write_text("\n".join(lines), encoding="utf-8")
    return ci_file


def clear_commit_issues(gator_dir):
    """Clear commit_issues.md after a clean pass."""
    ci_file = gator_dir / "commit_issues.md"
    if ci_file.exists():
        ci_file.write_text("# Commit Issues\n\nNo findings.\n", encoding="utf-8")


# clear_lint_allowlist() was retired (#34): lint-allow.json is a
# deprecated read-only input and is never rewritten or staged.


# ---------------------------------------------------------------------------
# Enforcement configuration
# ---------------------------------------------------------------------------

def _read_enforcement_level(gator_dir):
    """Read enforcement level from .gator/config.json. Default: strict."""
    config_path = gator_dir / "config.json"
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            level = config.get("enforcement_level", "strict")
            if level in ("strict", "warn", "off"):
                return level
        except (json.JSONDecodeError, OSError):
            pass
    return "strict"


# ---------------------------------------------------------------------------
# Phase 1: validate (called from pre-commit hook)
# ---------------------------------------------------------------------------

def phase_validate():
    """Pre-commit validation. Exit 0 to allow, exit 1 to block."""
    repo_root = find_gator_root()
    if not repo_root:
        # Hooks are installed (this script is running) but .gator/ is absent.
        # This means the repo is governed on another branch but the current
        # branch hasn't merged the governance layer yet. Warn and allow.
        print("\n  Gator: this repo has governance hooks installed, but the current")
        print("  branch does not contain .gator/. Proceeding in warning mode.")
        print("  If this branch should be governed, merge or restore the Gator layer.\n")
        sys.exit(0)

    gator_dir = repo_root / ".gator"
    staged_files = get_staged_files(repo_root)

    # Read enforcement level
    enforcement = _read_enforcement_level(gator_dir)

    # If enforcement is off, skip governance checks but clear stale artifacts
    # so the repo doesn't misrepresent its posture. Trailers and cleanup
    # still run in their own phases.
    if enforcement == "off":
        clear_commit_issues(gator_dir)  # transient; never staged (#34)
        wb = write_whiteboard(gator_dir, [], [], None, enforcement_level="off")
        stage_file(wb, repo_root)
        status = build_status(gator_dir, staged_files, {}, "", None)
        sf = write_status_json(gator_dir, status)
        stage_file(sf, repo_root)
        print()
        print("  gator pre-commit: enforcement OFF — governance checks skipped")
        print()
        sys.exit(0)

    # Parse commit_draft
    frontmatter, body, parse_error = parse_commit_draft(gator_dir)

    # Override state (#34, #35). Every rule is evaluated first with no
    # override consulted; an approval is applied afterwards only if it is
    # valid for this exact staged tree. Nothing is consumed here — a retry
    # that is blocked for another reason keeps the approval, and only
    # phase_cleanup() (post-commit) retires it. See scripts-precommit.md.
    tree = sdir = None
    state_problem = None
    try:
        tree = override_state.index_tree(repo_root)
        sdir = override_state.state_dir(repo_root)
    except override_state.OverrideStateError as exc:
        state_problem = str(exc)

    # Validate governance rules (no override: approvals apply below)
    failures = validate_hard_rules(staged_files, frontmatter, body, parse_error, gator_dir)
    warnings = validate_soft_rules(staged_files, frontmatter, body, gator_dir)

    if state_problem:
        failures.append(("unmerged-index", state_problem))

    # The v1 direct bypass file no longer authorizes anything.
    if (gator_dir / ".override").exists():
        failures.append((
            "legacy-override-file",
            ".gator/.override is a retired v1 bypass and no longer authorizes "
            "a commit. Delete it. Overrides are Architect-approved with "
            "`gator hook approve` for the exact staged change."
        ))

    # Run Layer 1 mechanical lint on staged files (dangerous code patterns)
    lint_findings = run_layer1_lint(staged_files, repo_root)
    lint_failures = []
    lint_warnings = []
    for finding in lint_findings:
        if finding["severity"] in ("CRITICAL", "HIGH"):
            lint_failures.append(finding)
            failures.append((
                finding["rule"],
                f"{finding['file']}:{finding['line']} — {finding['message']}"
                + (f"\n       > {finding['match']}" if finding.get("match") else ""),
            ))
        else:
            lint_warnings.append(finding)
            warnings.append((
                finding["rule"],
                f"{finding['file']}:{finding['line']} — {finding['message']}",
            ))
    lint_rules = {f["rule"] for f in lint_failures}

    # Deprecated lint-allow.json (#34): it no longer suppresses findings.
    if load_lint_allowlist(gator_dir):
        listed = sorted({f"{f['rule']} in {f['file']}" for f in lint_findings
                         if f.get("allowlisted")})
        warnings.append((
            "lint-allow-deprecated",
            ".gator/lint-allow.json no longer authorizes lint findings on its "
            "own. HIGH/CRITICAL findings block until fixed or the Architect "
            "approves this exact staged change with `gator hook approve`."
            + (f" Still blocking despite being listed: {', '.join(listed)}."
               if listed else "")
        ))

    # Write lint findings to commit_issues.md (Architect reviews these)
    # commit_issues.md is hook-transient and gitignored (#34): written for
    # the Architect to read, never staged or committed.
    if lint_failures or lint_warnings:
        write_commit_issues(gator_dir, lint_failures + lint_warnings)
    else:
        # Clear any stale commit_issues from a previous blocked attempt
        clear_commit_issues(gator_dir)

    # Apply an Architect approval — only for this exact tree, only for the
    # rules it names, and never for fix-required rules (shared with the
    # Enterprise evidence_only path via precommit_override).
    all_failures = list(failures)
    failures, handoff, approval_notes = override_state.apply_approval(
        sdir, tree, failures, lint_rules)

    # Warn mode: move failures to warnings (still report, but don't block)
    if enforcement == "warn" and failures:
        warnings.extend(failures)
        failures = []

    # Write status.json (even on failure — captures the state at attempt time)
    status = build_status(gator_dir, staged_files, frontmatter, body, handoff)
    status_file = write_status_json(gator_dir, status)
    stage_file(status_file, repo_root)

    # Write whiteboard (always — clears stale findings on clean pass)
    wb_file = write_whiteboard(gator_dir, failures, warnings, handoff,
                               enforcement_level=enforcement)
    stage_file(wb_file, repo_root)

    # Output
    if failures:
        # Record every blocked attempt — including ones with nothing
        # approvable — so `gator hook approve` / `override status` can
        # always diagnose it (#35). The block lists ALL current failures
        # (approval-covered ones included) so a re-approval covers them all.
        block = None
        if sdir is not None and tree is not None:
            try:
                block = override_state.write_block(
                    sdir, tree, all_failures, staged_files, lint_rules)
            except OSError as exc:
                approval_notes.append(f"Could not record the block: {exc}")

        info = ["  Lint findings written to .gator/commit_issues.md"] if lint_failures else []
        info.append("  Findings written to .gator/whiteboard.md")
        for line in override_state.render_block_report(
                "gator pre-commit: BLOCKED", failures, warnings, lint_rules,
                approval_notes, block, info):
            print(line)
        sys.exit(1)

    # lint-allow.json is a deprecated, read-only compatibility input (#34):
    # it no longer authorizes anything, so the hook never rewrites or
    # stages it.

    if warnings:
        print()
        if enforcement == "warn":
            print("  gator pre-commit: PASS (enforcement: warn — findings are advisory)")
        else:
            print("  gator pre-commit: PASS (with warnings)")
        print()
        for rule, msg in warnings:
            print(f"  ⚠ {rule}: {msg}")
        print()

    if handoff:
        print()
        print(f"  gator pre-commit: OVERRIDE ({', '.join(handoff['overridden_rules'])}) "
              f"approved by {handoff['approved_by']}")
        print(f"  Recorded in commit trailers and whiteboard.md "
              f"(block {handoff['block_id']})")
        print()

    sys.exit(0)


# ---------------------------------------------------------------------------
# Phase 2: trailers (called from commit-msg hook)
# ---------------------------------------------------------------------------

def phase_trailers(msg_file_path):
    """Append Gator-* trailers to the commit message file."""
    repo_root = find_gator_root()
    if not repo_root:
        # Not a gator repo — leave message alone
        sys.exit(0)

    gator_dir = repo_root / ".gator"
    staged_files = get_staged_files(repo_root)
    frontmatter, body, _ = parse_commit_draft(gator_dir)

    # Override handoff written by validate for THIS staged tree (#34, #35).
    # Read-only here: if this hook or git fails after it, an unchanged
    # retry still finds the approval and handoff. post-commit consumes them.
    handoff = None
    try:
        handoff = override_state.read_handoff(
            override_state.state_dir(repo_root),
            tree=override_state.index_tree(repo_root))
    except override_state.OverrideStateError:
        handoff = None

    # Build trailers
    trailers = assemble_trailers(frontmatter, body, gator_dir, staged_files,
                                 handoff=handoff)

    # Read current message (the -m message the agent provided, if any)
    msg_path = Path(msg_file_path)
    current_msg = msg_path.read_text(encoding="utf-8", errors="replace")

    # --- Assemble message from commit_draft.md when it has real content ---
    draft_message = (frontmatter.get("message") or "").strip()
    # Strip only the exact stub heading — preserve all other #-prefixed
    # lines (e.g. "#123 fix", "## Refactored auth", "#security follow-up").
    _STUB_HEADING = "# Session Change Log"
    draft_body_lines = []
    for l in (body or "").splitlines():
        if l.strip() == _STUB_HEADING:
            continue
        draft_body_lines.append(l)
    # Strip leading/trailing blank lines
    while draft_body_lines and not draft_body_lines[0].strip():
        draft_body_lines.pop(0)
    while draft_body_lines and not draft_body_lines[-1].strip():
        draft_body_lines.pop()
    draft_has_content = bool(draft_message or draft_body_lines)

    if draft_has_content:
        # commit_draft.md is the source of truth for the commit message
        assembled_lines = []
        if draft_message:
            assembled_lines.append(draft_message)
        elif draft_body_lines:
            # Use first non-heading body line as summary if no message field
            assembled_lines.append(draft_body_lines[0])
            draft_body_lines = draft_body_lines[1:]
        assembled_lines.append("")  # blank line after summary

        if draft_body_lines:
            assembled_lines.extend(draft_body_lines)
            assembled_lines.append("")  # blank line after body

        # Append trailers
        final_lines = assembled_lines + trailers + [""]
    else:
        # Fallback: use whatever -m the agent provided (backward compatible)
        # Strip any existing Gator-* trailers (in case of retry)
        clean_lines = []
        for line in current_msg.splitlines():
            if not line.startswith("Gator-"):
                clean_lines.append(line)
        # Remove trailing blank lines
        while clean_lines and not clean_lines[-1].strip():
            clean_lines.pop()

        # Assemble final message
        final_lines = clean_lines + [""] + trailers + [""]

    msg_path.write_text("\n".join(final_lines), encoding="utf-8")

    sys.exit(0)


def record_commit_and_emit_snippet(gator_dir, status):
    """Thin wrapper: inject this module's git() into the canonical implementation."""
    return _record_commit_and_emit_snippet(gator_dir, status, git_fn=git)


def phase_cleanup():
    """Post-commit cleanup: emit snippet, reset draft, clear whiteboard."""
    repo_root = find_gator_root()
    if not repo_root:
        sys.exit(0)

    gator_dir = repo_root / ".gator"

    # Read status.json (hook state — what just committed)
    status_file = gator_dir / "status.json"
    status = {}
    if status_file.exists():
        try:
            status = json.loads(status_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    # Emit session snippet (uses active session ledger). Guarded — snippet
    # emission failure must never block a successful commit.
    try:
        record_commit_and_emit_snippet(gator_dir, status)
    except Exception:
        pass

    # Reset commit_draft.md
    draft_file = gator_dir / "commit_draft.md"
    draft_file.write_text(COMMIT_DRAFT_STUB, encoding="utf-8")

    # Reset whiteboard (pre-commit findings are stale after successful commit)
    whiteboard = gator_dir / "whiteboard.md"
    if whiteboard.exists():
        whiteboard.write_text("# Whiteboard\n\nNo findings.\n", encoding="utf-8")

    # The commit exists — only now is any override state consumed (#34, #35).
    # Idempotent; also retires abandoned blocks/approvals and legacy v1 files.
    # Guarded: cleanup must never fail a commit that already landed.
    try:
        override_state.retire(override_state.state_dir(repo_root), gator_dir)
    except Exception:
        pass

    sys.exit(0)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    if sys.stdout.encoding != "utf-8":
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )

    parser = argparse.ArgumentParser(
        description="Gator pre-commit hook — deterministic governance gate."
    )
    parser.add_argument(
        "--phase",
        choices=["validate", "trailers", "cleanup"],
        required=True,
        help="Which hook phase to run",
    )
    parser.add_argument(
        "msg_file",
        nargs="?",
        help="Path to commit message file (required for trailers phase)",
    )
    args = parser.parse_args()

    # Runtime-split Phase 2 (roadmap item 19, Variant A): fail-closed
    # version negotiation, feature-flagged for safe dogfooding. Gates the
    # validate phase ONLY — refusing mid-commit (trailers/cleanup) would
    # strand a half-finished commit. Flag off (default) = pre-Phase-2
    # behavior exactly. The invocation retarget itself is Phase 3; this
    # gate only decides run-vs-refuse.
    if args.phase == "validate" and os.environ.get("GATOR_RUNTIME_RESOLVER") == "1":
        try:
            from gator_core import resolve_governed_runtime
            decision = resolve_governed_runtime(Path.cwd())
            if decision["mode"] == "refuse":
                print("\n  gator pre-commit: RUNTIME VERSION MISMATCH\n")
                print(f"  {decision['reason']}\n")
                sys.exit(1)
            if decision["mode"] in ("cli-newer", "pin-unreadable"):
                print(f"  gator runtime: {decision['reason']}")
        except ImportError:
            pass  # resolver unavailable (very old repo copy) — proceed
        except SystemExit:
            raise
        except Exception as e:  # noqa: BLE001 — gate must not add new failure modes
            print(f"  gator runtime: resolver check skipped ({type(e).__name__}: {e})")

    if args.phase == "validate":
        phase_validate()
    elif args.phase == "trailers":
        if not args.msg_file:
            print("Error: trailers phase requires a message file path", file=sys.stderr)
            sys.exit(1)
        phase_trailers(args.msg_file)
    elif args.phase == "cleanup":
        phase_cleanup()


if __name__ == "__main__":
    main()
