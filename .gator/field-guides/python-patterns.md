---
generated: 2026-06-04
generator: field-guide-gen-v1
type: agent-patterns
language: python
source-charters: [gator-core, boot-version, fleet-intelligence, commit-gate, session-archaeology, deploy]
source-file-count: 14
pattern-count: 15
tutorial: python-tutorial.md
---

# Python Patterns

### git() Tuple Return
Files: gator_core.py, gator-fleet-report.py, gator-drift.py
Every git() call returns (stdout, success_bool). Callers MUST unpack both. Never use the output without checking success.
! Ignoring the success flag reintroduces silent-failure bugs. Charter: cross-cutting git() pattern.

### ensure_utf8_stdout() at Entry
Files: gator-init.py, gator-fleet-report.py, gator-drift.py, gator-audit.py, gator-update.py, gator-deploy.py
Call once at the top of main() before any print(). Required for Windows terminal encoding.

### Path via pathlib Exclusively
Files: gator_core.py, gator-init.py, gator-fleet-report.py, gator-drift.py, gator-audit.py, gator-update.py, gator-deploy.py, gator-session-common.py, gator-session-sink.py
Use pathlib.Path for all file operations. Join with `/` operator, check with `.is_dir()`/`.exists()`, read with `.read_text(encoding="utf-8", errors="replace")`. Never os.path after initial argument parsing.

### @reads/@writes Docstring Tags
Files: gator_core.py, gator-init.py, gator-fleet-report.py, gator-drift.py, gator-audit.py, gator-update.py, gator-deploy.py, gator-session-common.py
Module and function docstrings declare what they access. Module-level tags in the triple-quote docstring. Function-level tags after the description line. Adopted consistently in the core 8 scripts; older scripts (memex.py, crawler.py) predate this convention.

### Sentinel Returns on Failure
Files: gator_core.py, gator-init.py, gator-fleet-report.py, gator-drift.py, gator-update.py
Return None, 0, empty dict, or empty list on failure. Never raise from I/O operations in the fleet-facing scripts. Callers check the sentinel, not try/except. Prefer specific exception types: (OSError, UnicodeDecodeError), (OSError, subprocess.TimeoutExpired). Note: session archaeology and sink scripts use broader `except Exception` handlers because they parse undocumented vendor formats where the failure modes are unpredictable.

### File Read Guard Pattern
Files: gator-init.py, gator-fleet-report.py, gator-drift.py, gator-update.py
Check .exists() before reading. Wrap read in try/except (OSError, UnicodeDecodeError) with continue or sentinel return.

### argparse with Short Flags
Files: gator-init.py, gator-fleet-report.py, gator-drift.py, gator-audit.py, gator-update.py, gator-deploy.py
Long flags always have short companions: --json/-j, --path/-p. Boolean flags use action="store_true".

### import_sibling() for Hyphenated Scripts
Files: gator_core.py (definition), gator-audit.py, gator-session-sink.py, extract-*-sessions.py
Use gator_core.import_sibling("script-name") to import sibling scripts with hyphens. Returns None if not found. Raises ImportError with diagnostics if file exists but fails to load. Preferred over hand-rolled spec_from_file_location (gator-sessions.py still has a legacy hand-rolled import that predates this helper).

### Dict-Based Data Structures
Files: gator-fleet-report.py, gator-drift.py, gator-audit.py, gator-session-sink.py
Initialize all expected keys upfront. Use .get(key, default) for optional fields. Always JSON-serializable. Return dicts, never custom objects.

### Section Headers for Organization
Files: gator_core.py, gator-init.py, gator-fleet-report.py, gator-drift.py, gator-audit.py, gator-update.py, gator-deploy.py
Group functions by semantic domain with `# ---...---` separator lines. Helper functions above callers. main() always last.

### Dual Output Modes
Files: gator-init.py, gator-fleet-report.py, gator-drift.py, gator-audit.py
Text output (default, human-readable) and JSON output (--json flag, complete data). The two must return equivalent information.

### Pre-Commit Hook Self-Containment
Files: gator-pre-commit.py
The hook does NOT import gator_core.py. It has its own git(), count_charters(), etc. This is a trust boundary — import breakage must never block commits fleet-wide.
! Never refactor the hook to use gator_core imports. Charter: cross-cutting self-containment tripwire.

### CURRENT_GENERATION Cross-Language Format
Files: gator_core.py
The format `CURRENT_GENERATION = N` (spaces around =, integer, own line) must stay parseable by sed. Bash installer reads this value at runtime.
! Changing the format breaks gatorize.sh generation detection. Charter: cross-cutting CURRENT_GENERATION tripwire.

### Overlay-Not-Replace Semantics
Files: gator-update.py, gatorize.sh (Bash counterpart)
Template files overwrite same-named files. Files that exist only in the target are never deleted. User charters, threads, and artifacts are sacred.
! Charter: cross-cutting overlay-not-replace pattern.

### Template Sync Obligation
Files: gator_core.py, gator-init.py, gator-update.py, gator-version.py, gator-pre-commit.py
Scripts that exist in both src/gator_command/scripts/ and templates/gator-starter/scripts/ must be kept synchronized. The command-post copy is the source of truth.
! After modifying any synced file, copy to the template directory. Charter: cross-cutting template sync tripwire.
