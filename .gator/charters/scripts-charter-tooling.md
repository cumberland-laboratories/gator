# Charter: Charter Tooling

**Covers**: `src/gator_command/scripts/gator-charter-lint.py`, `src/gator_command/scripts/gator-charter-draft.py`, `src/gator_command/scripts/gator-charter-verify.py`

## Owns

- Charter Schema v1 parsing and shape validation.
- Source discovery and draft charter scaffolding.
- Heuristic coverage, function-gap, stale-structure, complexity, and cross-cutting reports.

## Does Not Own

- Governance enforcement at commit time; see [`scripts-cross-cutting.md`](scripts-cross-cutting.md).
- Human decisions about whether an informational finding warrants more charter detail.
- Charter content for any product domain.

---

### parse_charter() / validate_charter()
File: src/gator_command/scripts/gator-charter-lint.py
Parse one charter and validate required shape, function-entry fields, and index links.
<- lint `main()`
-> Charter Schema v1 rules
! `INDEX.md` and the cross-cutting charter have intentional structural exceptions; keep exemptions narrow and explicit.

### collect_files() / find_charter_dirs()
File: src/gator_command/scripts/gator-charter-lint.py
Resolve explicit or repository-discovered charter inputs deterministically.
<- lint `main()`
! Do not lint README/template prose as module charters unless the caller explicitly selects them.

### load_charterignore() / discover_files()
File: src/gator_command/scripts/gator-charter-draft.py
Discover charter-worthy source files after applying repository ignore rules.
<- draft `main()`
-> layout resolver, charterignore
! Ignore evaluation uses repo-relative normalized paths across platforms.

### analyze_python() / analyze_javascript() / analyze_shell() / analyze_minimal()
File: src/gator_command/scripts/gator-charter-draft.py
Extract structural ownership signals without executing source code.
<- draft generation
-> language-specific static parsing
! Parse failure degrades to minimal analysis and is reported; it never causes source execution.

### generate_scaffold() / write_scaffolds()
File: src/gator_command/scripts/gator-charter-draft.py
Render reviewable charter starting points and optionally write them to an explicit output directory.
<- draft `main()`
! Drafts are scaffolds, not authoritative documentation. Never overwrite a maintained charter implicitly.

### parse_charters() / verify()
File: src/gator_command/scripts/gator-charter-verify.py
Build coverage maps and emit structured findings over selected source directories.
<- verify `main()`
-> source analyzers and Git changed-file selection
! Warnings identify likely coverage gaps; informational function/complexity findings are heuristics, not instructions to expand every charter.

### coverage and stale checks
File: src/gator_command/scripts/gator-charter-verify.py
Compare `**Covers**` patterns and documented names with current source structure.
<- `verify()`
! Coverage globs must use repository-relative paths. A broad glob can hide poor routing even when the metric turns green.

## Before Changing This Module

- Test Windows and POSIX path normalization.
- Preserve text and JSON output schemas.
- Run `tests/test_charter_lint.py` and focused draft/verify tests.
- Validate the repository's own charters as a dogfood case.

## Connections

-> [Cross-Cutting](scripts-cross-cutting.md) - canonical charter-surface resolver
-> [Repo Lifecycle](scripts-repo-lifecycle.md) - boot-time charter counts
-> [Charter README](README.md) - authoring and size rules
