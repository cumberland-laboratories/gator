---
generated: 2026-06-04
generator: field-guide-gen-v1
type: pi-tutorial
language: python
source-charters: [gator-core, boot-version, fleet-intelligence, commit-gate, session-archaeology, deploy]
patterns: python-patterns.md
---

# Python Tutorial

Companion to [python-patterns.md](python-patterns.md). Real code snippets from this repo, with rationale and charter connections. Read this to restore sharpness on the Python idioms used here.

### git() Tuple Return

**Charter connection**: Cross-Cutting — git() return pattern; Shared Infrastructure — git() function entry

From `gator_core.py`:
```python
def git(*args, cwd=None):
    try:
        result = subprocess.run(
            ["git"] + list(args),
            capture_output=True, text=True, cwd=cwd, timeout=10,
        )
        return result.stdout.strip(), result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return "", False
```

Callers unpack like this (from `gator-fleet-report.py`):
```python
log_line, ok = git("log", "-1", "--format=%h|%s|%ar|%ai", cwd=repo_path)
if not ok or not log_line:
    return None
```

**Why it matters**: The original git helper returned bare strings. Empty output from a failed command was indistinguishable from a successful command that returned nothing. Codex found this bug twice in fleet-report. The tuple makes the caller explicitly handle failure — you can't accidentally use a failed git result as if it succeeded.

**What to watch for**: Any new git() call where only the first element is captured (`output = git(...)` instead of `output, ok = git(...)`).

### ensure_utf8_stdout() at Entry

**Charter connection**: Shared Infrastructure — ensure_utf8_stdout() function entry

From `gator_core.py`:
```python
def ensure_utf8_stdout():
    if sys.stdout.encoding != "utf-8":
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
```

**Why it matters**: Windows terminals default to cp1252 or similar encodings. The boot sequence prints Unicode characters (checkmarks, bullet dots). Without this call, those characters crash the script on Windows. Every script that prints to stdout needs this as its first action in main().

**What to watch for**: A new script that prints formatted output but doesn't call ensure_utf8_stdout() in main().

### Path via pathlib Exclusively

**Charter connection**: Shared Infrastructure — normalize_path(), find_gator_root(), find_command_post()

From `gator_core.py`:
```python
def find_gator_root(start_path=None):
    path = Path(start_path) if start_path else Path.cwd()
    path = path.resolve()
    if (path / ".gator").is_dir():
        return path
    for parent in path.parents:
        if (parent / ".gator").is_dir():
            return parent
    return None
```

**Why it matters**: The codebase runs on Windows (Git Bash, PowerShell, native cmd) and Unix. pathlib handles path separators, resolution, and joining portably. Mixing os.path and pathlib creates subtle bugs when MSYS2 paths (/c/Users/...) interact with Windows paths (C:\Users\...). normalize_path() in gator_core handles the MSYS2 conversion explicitly.

**What to watch for**: Any use of `os.path.join`, `os.path.exists`, or string concatenation for paths.

### @reads/@writes Docstring Tags

**Charter connection**: All charters mirror this in their function entries

From `gator-drift.py` module docstring:
```python
"""
gator drift — Policy drift detection across the fleet.

@reads: gator-command/registry.md, gator-command/org-policy.md,
        .gator/ in each registered repo, git history
@writes: nothing (read-only, display only)
"""
```

From `gator-init.py` function docstring:
```python
def count_constitution_rules(gator_dir):
    """Count enforceable rules in the constitution.

    @reads: .gator/constitution.md
    """
```

**Why it matters**: These tags are the bridge between code and charters. When the charter says a function `@reads: .gator/.gator-version`, the code's docstring should say the same thing. When they diverge, either the charter is stale or the code changed its access patterns without updating the map. Note: this convention is established in the core fleet-facing scripts but not yet adopted in older scripts (memex.py, crawler.py, gator-sessions.py).

**What to watch for**: A function that reads a file not listed in its @reads tag, or a new function with no @reads/@writes declaration. When writing new scripts, follow this convention; when editing older scripts, adopt it for the functions you touch.

### Sentinel Returns on Failure

**Charter connection**: Shared Infrastructure — git() returns ("", False); Fleet Intelligence — scan functions return partial dicts

From `gator-fleet-report.py`:
```python
try:
    text = cf.read_text(encoding="utf-8", errors="replace")
except (OSError, UnicodeDecodeError):
    continue
```

From `gator_core.py`:
```python
try:
    return int(count)
except ValueError:
    return 0
```

**Why it matters**: These scripts scan fleet repos that may be in any state — missing files, corrupted encoding, network-mounted drives going stale. Raising exceptions would abort an entire fleet scan because one repo has a broken file. Sentinel returns let the scanner continue, reporting partial data for the broken repo and full data for everything else.

**What to watch for**: A new fleet-facing function that raises on I/O failure instead of returning a sentinel. The session archaeology scripts (gator-sessions.py, extract-*-sessions.py, gator-session-sink.py) legitimately use broader `except Exception` handlers because they parse undocumented vendor formats where failure modes are unpredictable — that's a different tradeoff than the fleet scripts.

### import_sibling() for Hyphenated Scripts

**Charter connection**: Shared Infrastructure — import_sibling() function entry; Session Archaeology — "Use import_sibling() for sibling imports"

From `gator_core.py`:
```python
def import_sibling(name):
    scripts_dir = Path(__file__).resolve().parent
    path = scripts_dir / f"{name}.py"
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), path
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
```

**Why it matters**: Python can't import modules with hyphens in their names (`import gator-fleet-report` is a syntax error). Before import_sibling() existed, each script hand-rolled its own importlib boilerplate. The shared helper provides consistent error handling (returns None if missing, raises ImportError with diagnostics if the file exists but fails). Note: `gator-sessions.py` still has a legacy hand-rolled import at line 55 that predates this helper — new code should use import_sibling() instead.

**What to watch for**: New sibling imports that don't use import_sibling(). Existing hand-rolled imports in older scripts are tech debt, not violations — migrate them when you're already editing those files.

### Pre-Commit Hook Self-Containment

**Charter connection**: Cross-Cutting — "Pre-Commit Hook Is Self-Contained" TRIPWIRE; Commit Gate charter

`gator-pre-commit.py` has its own implementations of git(), count_charters(), and other utilities that also exist in gator_core.py. This looks like code duplication. It is intentional.

**Why it matters**: The pre-commit hook runs on every commit in every fleet repo. If it imported gator_core and gator_core had a syntax error, import failure, or incompatible change, no repo in the fleet could commit. The hook's self-containment is a blast radius limiter. A broken gator_core breaks fleet-report and drift (annoying). A broken hook blocks all work (catastrophic).

**What to watch for**: Any PR that refactors the hook to import from gator_core. Also: the hook's git() returns a bare string (different contract than gator_core's tuple) — don't "fix" this to match.

### Template Sync Obligation

**Charter connection**: Cross-Cutting — "Template Sync Obligation" TRIPWIRE

Five Python files exist in two locations:

| File | Source of truth | Template copy |
|------|----------------|---------------|
| gator_core.py | src/gator_command/scripts/ | templates/gator-starter/scripts/ |
| gator-init.py | src/gator_command/scripts/ | templates/gator-starter/scripts/ |
| gator-update.py | src/gator_command/scripts/ | templates/gator-starter/scripts/ |
| gator-version.py | src/gator_command/scripts/ | templates/gator-starter/scripts/ |
| gator-pre-commit.py | .gator/scripts/ | templates/gator-starter/scripts/ |

**Why it matters**: `gator update` propagates the template copy to fleet repos. If the command-post copy is updated but the template isn't, fleet repos get stale behavior on their next update. The divergence is silent — no test catches it, no hook flags it, the drift detector checks generation numbers but not file content.

**What to watch for**: Editing any of these five files without copying the result to the other location. The charter says "command-post copy is the source of truth" — edit there first, then copy.

### CURRENT_GENERATION Cross-Language Format

**Charter connection**: Cross-Cutting — "CURRENT_GENERATION Cross-Language Constant" TRIPWIRE

From `gator_core.py`:
```python
CURRENT_GENERATION = 2
```

From `gatorize.sh`:
```bash
GATOR_GEN=$(sed -n 's/^CURRENT_GENERATION\s*=\s*\([0-9]*\)/\1/p' \
    "$COMMAND_POST/scripts/gator_core.py" | tr -d ' ')
```

**Why it matters**: This is the only value that crosses the Python/Bash language boundary at runtime. The Bash installer reads a Python source file with sed. The format must stay parseable: `CURRENT_GENERATION = N` with spaces around `=`, integer value, on its own line. Adding a type annotation (`CURRENT_GENERATION: int = 2`), using a different format (`CURRENT_GENERATION=2`), or wrapping it in a dict would silently break the installer.

**What to watch for**: Any refactoring of constants in gator_core.py that changes the line format of CURRENT_GENERATION.
