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
    _derive_intent,
    parse_ledger,
    build_commit_entry,
    render_ledger_block,
    _infer_vendor_from_agent,
    _reassemble_ledger,
    write_commit_summary,
)


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


def _generate_block_id():
    """Generate a short unique block ID for override tracking."""
    import hashlib
    import time
    raw = f"{time.time()}-{os.getpid()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:8]


def _write_override_request(gator_dir, failure_type, files, override_type="charter-skip"):
    """Write an override request for PI review."""
    import time
    request = {
        "block_id": _generate_block_id(),
        "failure_type": failure_type,
        "override_type": override_type,
        "files": files[:10],
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z"),
        "epoch": time.time(),
    }
    request_file = gator_dir / "override-request.json"
    request_file.write_text(
        json.dumps(request, indent=2) + "\n",
        encoding="utf-8",
    )
    return request


OVERRIDE_DELAY_SECONDS = 10


def check_override(gator_dir):
    """Check for a PI-approved two-phase override.

    Two-phase override flow:
      1. Hook blocks -> writes override-request.json (block ID, failure)
      2. PI reviews findings, runs gator-approve.py -> writes override-approved.json
      3. Agent retries git commit -> hook checks approval matches request

    Approval is valid only if:
      - Both request and approval files exist
      - Block IDs match
      - Approval timestamp is later than request
      - Minimum delay has passed (agent cannot instantly self-approve)

    Also supports legacy .override file for backward compatibility,
    but prints a deprecation notice.

    Returns the override value if approved, None otherwise.
    """
    import time

    # --- New two-phase flow ---
    request_file = gator_dir / "override-request.json"
    approved_file = gator_dir / "override-approved.json"

    two_phase_valid = False
    if request_file.exists() and approved_file.exists():
        try:
            request = json.loads(request_file.read_text(encoding="utf-8"))
            approval = json.loads(approved_file.read_text(encoding="utf-8"))

            ids_match = request.get("block_id") == approval.get("block_id")

            req_epoch = request.get("epoch", 0)
            try:
                appr_str = approval["approved_at"]
                # Parse with timezone offset (e.g. 2026-06-04T10:58:37-0400)
                # Python 3.7+ fromisoformat handles most ISO formats;
                # strptime with %z handles the +HHMM offset reliably.
                try:
                    appr_dt = datetime.fromisoformat(appr_str)
                except ValueError:
                    appr_dt = datetime.strptime(appr_str[:24], "%Y-%m-%dT%H:%M:%S%z")
                appr_epoch = appr_dt.timestamp()
            except (KeyError, ValueError):
                appr_epoch = 0

            timing_ok = appr_epoch >= req_epoch
            delay_ok = time.time() - req_epoch >= OVERRIDE_DELAY_SECONDS

            two_phase_valid = ids_match and timing_ok and delay_ok
        except (json.JSONDecodeError, OSError):
            two_phase_valid = False

    if two_phase_valid:
        # Valid two-phase approval — consume both files (one-shot)
        override_type = approval.get("override_type", "charter-skip")
        approved_by = approval.get("approved_by", "unknown")
        reason = approval.get("reason", "")

        for f in (request_file, approved_file):
            try:
                f.unlink()
            except OSError:
                pass
            git("rm", "--cached", "--quiet", "--force", "--",
                str(f.relative_to(gator_dir.parent)),
                cwd=gator_dir.parent)

        # Stash approval metadata for trailer assembly
        _override_meta = {
            "type": override_type,
            "approved_by": approved_by,
            "reason": reason,
            "block_id": request.get("block_id", ""),
        }
        meta_file = gator_dir / ".override-meta.json"
        meta_file.write_text(json.dumps(_override_meta), encoding="utf-8")

        return override_type

    # --- Legacy .override file (fallback when two-phase fails or is absent) ---
    override_file = gator_dir / ".override"
    if override_file.exists():
        value = override_file.read_text(encoding="utf-8").strip()
        try:
            override_file.unlink()
        except OSError:
            pass
        git("rm", "--cached", "--quiet", "--force", "--",
            str(override_file.relative_to(gator_dir.parent)),
            cwd=gator_dir.parent)

        if value:
            # Write minimal meta for trailers
            meta_file = gator_dir / ".override-meta.json"
            meta_file.write_text(json.dumps({
                "type": value,
                "approved_by": "legacy-override",
                "reason": "",
                "block_id": "",
            }), encoding="utf-8")
        return value or None

    return None


# ---------------------------------------------------------------------------
# Validation rules
# ---------------------------------------------------------------------------

def validate_hard_rules(staged_files, frontmatter, body, parse_error, gator_dir, override=None):
    """Check hard rules. Returns list of (rule_name, message) for failures."""
    failures = []

    # 1. Frontmatter parse failure
    if parse_error:
        failures.append(("frontmatter-parse", parse_error))

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

def assemble_trailers(frontmatter, body, gator_dir, staged_files, override=None):
    """Build Gator-* trailer lines from all available sources."""
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

    # Charter changed (from git diff --cached — deterministic)
    if override == "charter-skip":
        trailers.append("Gator-Charter-Changed: override-skip")
        # Include PI attribution from approval metadata
        meta_file = gator_dir / ".override-meta.json"
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                approved_by = meta.get("approved_by", "")
                block_id = meta.get("block_id", "")
                if approved_by and approved_by != "legacy-override":
                    trailers.append(f"Gator-Override-Approved-By: {approved_by}")
                if block_id:
                    trailers.append(f"Gator-Override-Block: {block_id}")
                # Consume the meta file
                meta_file.unlink(missing_ok=True)
            except (json.JSONDecodeError, OSError):
                pass
    else:
        trailers.append(f"Gator-Charter-Changed: {'yes' if has_charter else 'no'}")

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

def build_status(gator_dir, staged_files, frontmatter, body, override=None):
    """Build the status.json content."""
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

    charter_changed = "override-skip" if override == "charter-skip" else has_charter

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

def write_whiteboard(gator_dir, failures, warnings, override,
                     enforcement_level="strict"):
    """Write findings to .gator/whiteboard.md."""
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

    if override:
        lines.append("## Overrides")
        lines.append("")
        override_detail = f"{override} (committed at {timestamp})"
        meta_file = gator_dir / ".override-meta.json"
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                approved_by = meta.get("approved_by", "")
                reason = meta.get("reason", "")
                block_id = meta.get("block_id", "")
                if approved_by and approved_by != "legacy-override":
                    override_detail += f" — approved by {approved_by}"
                if reason:
                    override_detail += f" — reason: {reason}"
                if block_id:
                    override_detail += f" — block: {block_id}"
            except (json.JSONDecodeError, OSError):
                pass
        lines.append(f"- **Gator-Override**: {override_detail}")
        lines.append("")

    if not failures and not warnings and not override:
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
        "Review each finding. If intentional, tell the agent to approve it.",
        "The agent will add the approval to `.gator/lint-allow.json` and retry the commit.",
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


def clear_lint_allowlist(gator_dir, repo_root):
    """Clear lint-allow.json after a successful commit.

    The allowlist is a one-shot approval mechanism. Once the commit lands,
    the dangerous code is in the codebase and future diffs won't show it
    as new — so the allowlist entry is no longer needed. Clear it to
    prevent stale approvals from accumulating.
    """
    allowlist_file = gator_dir / "lint-allow.json"
    if not allowlist_file.exists():
        return
    try:
        entries = json.loads(allowlist_file.read_text(encoding="utf-8"))
        if entries:  # Only clear if non-empty (was actually used)
            allowlist_file.write_text("[]\n", encoding="utf-8")
            stage_file(allowlist_file, repo_root)
    except (json.JSONDecodeError, OSError):
        pass


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
        # Not a gator repo — allow the commit silently
        sys.exit(0)

    gator_dir = repo_root / ".gator"
    staged_files = get_staged_files(repo_root)

    # Read enforcement level — from GATOR_HOOK_MODE env var (set by Enterprise
    # hook wrapper) or from .gator/ config
    enforcement = os.environ.get("GATOR_HOOK_MODE") or _read_enforcement_level(gator_dir)

    # Normalize: Enterprise uses "warning", Individual uses "warn" — accept both
    if enforcement == "warning":
        enforcement = "warn"

    # Evidence-only mode: skip governance ceremony (charters, commit_draft),
    # but KEEP safety lint (dangerous patterns, secrets detection).
    # This is the default mode for Gator Enterprise repos.
    if enforcement == "evidence_only":
        # Write status.json (evidence)
        status = build_status(gator_dir, staged_files, {}, "", None)
        sf = write_status_json(gator_dir, status)
        stage_file(sf, repo_root)

        # Run Layer 1 lint — dangerous code patterns that the admin may want
        # enforced even without governance ceremony
        lint_findings = run_layer1_lint(staged_files, repo_root)
        lint_failures = [f for f in lint_findings if f["severity"] in ("CRITICAL", "HIGH")]
        lint_warnings = [f for f in lint_findings if f["severity"] not in ("CRITICAL", "HIGH")]

        if lint_failures:
            print()
            print("  gator pre-commit: BLOCKED (evidence_only — dangerous pattern detected)")
            print()
            for f in lint_failures:
                print(f"  ✗ {f['rule']}: {f['file']}:{f['line']} — {f['message']}")
            if lint_warnings:
                print()
                for f in lint_warnings:
                    print(f"  ⚠ {f['rule']}: {f['file']}:{f['line']} — {f['message']}")
            print()
            sys.exit(1)

        if lint_warnings:
            print()
            print("  gator pre-commit: PASS (evidence_only, with warnings)")
            print()
            for f in lint_warnings:
                print(f"  ⚠ {f['rule']}: {f['file']}:{f['line']} — {f['message']}")
            print()

        sys.exit(0)

    # If enforcement is off, skip governance checks but clear stale artifacts
    # so the repo doesn't misrepresent its posture. Trailers and cleanup
    # still run in their own phases.
    if enforcement == "off":
        clear_commit_issues(gator_dir)
        ci_file = gator_dir / "commit_issues.md"
        if ci_file.exists():
            stage_file(ci_file, repo_root)
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

    # Check override — read once, pass everywhere, file deleted atomically
    override = check_override(gator_dir)

    # Validate governance rules
    failures = validate_hard_rules(staged_files, frontmatter, body, parse_error, gator_dir, override)
    warnings = validate_soft_rules(staged_files, frontmatter, body, gator_dir)

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

    # Write lint findings to commit_issues.md (PI reviews these to approve)
    if lint_failures or lint_warnings:
        ci_file = write_commit_issues(gator_dir, lint_failures + lint_warnings)
        stage_file(ci_file, repo_root)
    else:
        # Clear any stale commit_issues from a previous blocked attempt
        clear_commit_issues(gator_dir)

    # Warn mode: move failures to warnings (still report, but don't block)
    if enforcement == "warn" and failures:
        warnings.extend(failures)
        failures = []

    # Write status.json (even on failure — captures the state at attempt time)
    status = build_status(gator_dir, staged_files, frontmatter, body, override)
    status_file = write_status_json(gator_dir, status)
    stage_file(status_file, repo_root)

    # Write whiteboard (always — clears stale findings on clean pass)
    wb_file = write_whiteboard(gator_dir, failures, warnings, override,
                               enforcement_level=enforcement)
    stage_file(wb_file, repo_root)

    # Output
    if failures:
        print()
        print("  gator pre-commit: BLOCKED")
        print()
        for rule, msg in failures:
            print(f"  ✗ {rule}: {msg}")
        if warnings:
            print()
            for rule, msg in warnings:
                print(f"  ⚠ {rule}: {msg}")
        print()
        if lint_failures:
            print("  Lint findings written to .gator/commit_issues.md")
            print("  PI: review findings, approve with lint-allow.json, retry commit")
        else:
            print("  Findings written to .gator/whiteboard.md")

        # Write override request for PI approval flow
        charter_failures = [
            r for r, _ in failures
            if r in ("charter-alongside-code", "cross-cutting-missing", "charter-index-gap")
        ]
        if charter_failures:
            _, has_charter, code_files, _ = classify_staged_files(staged_files)
            request = _write_override_request(
                gator_dir, charter_failures[0], code_files
            )
            block_id = request["block_id"]
            print()
            print("  ┌─────────────────────────────────────────────────────────┐")
            print("  │ STOP. Do not override this yourself.                   │")
            print("  │                                                        │")
            print("  │ Present these findings to the PI. The PI decides:      │")
            print("  │   1. Update the affected charters and retry the commit │")
            print("  │   2. Approve override:                                 │")
            print(f"  │      python .gator/scripts/gator-approve.py           │")
            print("  │                                                        │")
            print("  │ You may NOT create override files yourself.            │")
            print("  │ You may NOT run gator-approve.py yourself.             │")
            print("  │ Unauthorized self-approval is a governance violation.  │")
            print("  └─────────────────────────────────────────────────────────┘")
            print()
            print(f"  Block ID: {block_id}")

        print()
        sys.exit(1)

    # Commit is passing — consume and clear lint-allow.json (one-shot approvals)
    clear_lint_allowlist(gator_dir, repo_root)

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

    if override:
        print()
        print(f"  gator pre-commit: OVERRIDE ({override})")
        print(f"  Override recorded in trailers and whiteboard.md")
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

    # Read override from status.json (written by validate phase, which
    # already consumed and deleted the .override file)
    override = None
    status_file = gator_dir / "status.json"
    if status_file.exists():
        try:
            status_data = json.loads(status_file.read_text(encoding="utf-8"))
            charter_changed = status_data.get("charter_changed")
            if charter_changed == "override-skip":
                override = "charter-skip"
        except (json.JSONDecodeError, OSError):
            pass

    # Build trailers
    trailers = assemble_trailers(frontmatter, body, gator_dir, staged_files, override)

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


def _emit_session_snippet(gator_dir, repo_root):
    """Write a session snippet JSON for the just-completed commit.

    Delegates to record_commit_and_emit_snippet() in precommit_session —
    the canonical orchestrator for ledger append + snippet emission.
    Uses the real .gator/sessions/_active/ ledger surface.
    """
    try:
        from precommit_session import record_commit_and_emit_snippet
    except ImportError:
        return

    # Read status.json to pass as the status dict
    status = {}
    status_file = gator_dir / "status.json"
    if status_file.exists():
        try:
            status = json.loads(status_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    try:
        record_commit_and_emit_snippet(gator_dir, status)
    except Exception:
        pass  # Never block post-commit for snippet emission failure


def phase_cleanup():
    """Post-commit cleanup: emit snippet, reset draft, clear whiteboard.

    Snippet emission happens HERE (post-commit) because HEAD now points to
    the just-completed commit. Snippets are staggered by one commit —
    the snippet for commit N is generated post-commit and staged for commit N+1,
    just like session blocks.
    """
    repo_root = find_gator_root()
    if not repo_root:
        sys.exit(0)

    gator_dir = repo_root / ".gator"
    mode = os.environ.get("GATOR_HOOK_MODE", "")

    # Emit session snippet (runs in ALL modes except "off" — evidence capture)
    if mode != "off":
        _emit_session_snippet(gator_dir, repo_root)

    # Evidence-only mode: skip governance cleanup (no commit_draft or whiteboard to reset)
    if mode == "evidence_only":
        sys.exit(0)

    # Read status.json (hook state — what just committed)
    status_file = gator_dir / "status.json"
    if status_file.exists():
        try:
            status = json.loads(status_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    # Reset commit_draft.md (only if it exists — evidence_only repos may not have it)
    draft_file = gator_dir / "commit_draft.md"
    if draft_file.exists():
        draft_file.write_text(COMMIT_DRAFT_STUB, encoding="utf-8")

    # Reset whiteboard (pre-commit findings are stale after successful commit)
    whiteboard = gator_dir / "whiteboard.md"
    if whiteboard.exists():
        whiteboard.write_text("# Whiteboard\n\nNo findings.\n", encoding="utf-8")

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
