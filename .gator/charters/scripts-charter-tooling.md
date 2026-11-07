# Charter: Charter Tooling

**Covers**: `src/gator_command/scripts/gator-charter-lint.py`, `src/gator_command/scripts/gator-charter-draft.py`, `src/gator_command/scripts/gator-charter-verify.py`, `src/gator_command/scripts/charter_covers.py`, `src/gator_command/scripts/charter_significance.py`, `src/gator_command/scripts/charter_report.py`, `src/gator_command/scripts/gator-charters.py`

## Owns

- Charter Schema v1 parsing and shape validation.
- Source discovery and draft charter scaffolding.
- Heuristic coverage, function-gap, stale-structure, complexity, and cross-cutting reports.
- The shared `Covers` matcher grammar (`gator-covers-v1`).
- The shared function-significance policy (`gator-significance-v1`): which functions need a charter entry.
- The read-only charter health report (`gator charters report`, `gator-charters-report-v1`) and its input fingerprint.

## Does Not Own

- Governance enforcement at commit time; see [`scripts-cross-cutting.md`](scripts-cross-cutting.md).
- Human decisions about whether an informational finding warrants more charter detail.
- Charter content for any product domain.

---

### parse_charter() / validate_charter()
File: src/gator_command/scripts/gator-charter-lint.py
Parse one charter and validate required shape, function-entry fields, and index links. `_validate_internal()` adds the `**Internal**:` shape rules (#105): `internal-syntax` (malformed item, empty list, a second line, or a line after the first `## `), `internal-duplicate`, and `internal-conflict` (a name that a heading also documents; the documented entry wins). `bare-entry` (warn) flags a `###` entry with neither a `File:` line nor description prose, in addition to `file-line`, never instead of it.
<- lint `main()`
-> Charter Schema v1 rules, `charter_significance.parse_internal()` / `heading_names()`
! `INDEX.md` and the cross-cutting charter have intentional structural exceptions; keep exemptions narrow and explicit.
! A `---` separator ends the current entry and is never counted as its description, so an entry followed only by a separator is bare.
! Scope (is each Internal name defined in a covered file?) needs coverage resolution: it is the verifier's `stale-exclusion`, not a lint rule.

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

### parse_charters() / verify(repo_root, gator_dir, dirs=None, changed_only=False, function_policy="default")
File: src/gator_command/scripts/gator-charter-verify.py
Build coverage maps and emit structured findings over selected source directories. `parse_charters()` still returns its raw entry-keyed map, but `verify()` discards it and resolves coverage with `charter_covers.coverage_index(all_files, charters)` (#88): `{file: [charter names]}` over the discovered files, so every check (coverage-gap, function-gap, complexity, stale-structure) sees glob- and prefix-covered files. `_check_complexity_mismatch()` takes the longest covering charter's `line_count` from that index. `_parse_function_entries()` reads headings through `charter_significance.heading_names()` (a grouped `### a() / b()` documents every name, and each inherits the entry's `File:`) and `parse_file_line()` (`File:` with or without backticks).
<- verify `main()`
-> source analyzers and Git changed-file selection, `charter_covers.coverage_index()`, `charter_significance`
! Warnings identify likely coverage gaps; informational function/complexity findings are heuristics, not instructions to expand every charter.
! **Function gaps (#105).** `_collect_signals()` reads each analyzed `.py` / `.js`-family file once into `charter_significance` signals and builds the `(stem, name) → importer files` map over analyzed files only. `_check_function_gaps()` reports `function-gap` (with `reason`: `entry` | `cross-module`) only when `charter_significance.decide()` says `document`; importer and file owners come from the resolved coverage index. `function_policy="strict"` (`--functions strict`) also reports `function-candidate` for `internal` functions the broad `_is_charter_worthy()` heuristic flags; default findings are identical in both modes, and only strict mode keeps that heuristic.
! **Internal exclusions.** `parse_charters()` adds each charter's `internal` names (`charter_significance.parse_internal()`). A name clears a function gap or candidate only through a charter that `coverage_index()` assigns to the file, so a broad or unrelated charter never suppresses another file's gap. `_check_stale_exclusions()` emits `stale-exclusion` (info; `file` is the charter path) for a name defined in none of that charter's covered files: functions, classes, methods or `registered` names. "Out of scope" and "stale" are the same condition.
! **Stale checks.** `File:` remains the only association that enables `stale-structure`, and since #105 the README's plain `File: path` form counts. `_check_stale_structure()` counts the file's `registered` signal names (Python module-level bindings, JavaScript `window.<path>` registrations and object-literal methods) as existing code. A grouped entry whose names live in two files but whose `File:` names one is reported as stale for the others: that is real charter drift.

### charter_summaries(repo_root) / print_json_findings(findings, charters=None, function_policy=None)
File: src/gator_command/scripts/gator-charter-verify.py
`--json` output is `{version, finding_count, summary, findings, charters, function_policy}`. `charters` (additive, 2026-10-29) is `[{name, path, covers}]` for every parsed charter: `path` is repo-relative POSIX, and `covers` is the raw backtick list from the `**Covers**` line, globs included. `function_policy` (additive, #105) is `"default"` or `"strict"`; `function-gap` findings carry an additive `reason`, and `function-candidate` appears only in strict mode. Text output is unchanged.
<- verify `main()` (JSON mode only)
-> `find_charter_dirs()`, `parse_charters()`
! Consumers: the Dashboard `/check` route, enforcer-review structural priors and the Dashboard charter sync check (`scripts-dashboard.md` → `dashboard/charter_sync.py`). Only the last reads `charters`. Its absence (older wheel) must stay tolerated. Existing keys and finding shapes do not change meaning (cross-cutting additive rule).
! Coverage honours globs and directory prefixes through the shared grammar (#88 fixed, 2026-11-06), so the verifier and the charter sync check agree. `charters.covers` still exposes the raw entries; consumers match them with `charter_covers.covers_match()`, never their own rule. Fixing #88 changed findings, not keys: fewer `coverage-gap`, and possibly more function/stale/complexity findings for files that are now covered.

### coverage and stale checks
File: src/gator_command/scripts/gator-charter-verify.py
Compare `**Covers**` patterns and documented names with current source structure.
<- `verify()`
! Coverage globs must use repository-relative paths. A broad glob can hide poor routing even when the metric turns green.
! Discovery uses plain `git ls-files`, which quotes non-ASCII paths; such files never match a `Covers` entry and are reported as uncovered (known limit).

### normalize_path() / covers_match() / covering_charters() / coverage_index() — shared Covers matcher (`GRAMMAR = "gator-covers-v1"`)
File: src/gator_command/scripts/charter_covers.py
The one answer to "does this `Covers` entry name this file?". Paths and entries are normalized (`\` → `/`, no leading `./`); matching is case-sensitive everywhere. An entry with `*`, `?` or `[` is `fnmatchcase` over the full path (never the basename; `*` crosses `/`); a trailing `/` is a directory prefix; anything else is exact. `coverage_index(files, charters)` returns `{file: [names]}` for covered files only; `covering_charters()` keeps the caller's charter order.
<- `gator-charter-verify.verify()`, `dashboard/charter_sync.py` (`covers_match` is re-bound there, see `scripts-dashboard.md`)
! Closed grammar: an empty, absolute (`/…`, `X:`) or `..`-segment entry matches nothing. Adding a rule changes every consumer's numbers at once; extend it only with a grammar bump and the compatibility matrix in `tests/test_charter_covers.py`.
! Standard library only, imported by plain name: callers run with the scripts directory on `sys.path` (scripts run by filename, the Dashboard). It ships through `package-data`.
! Other producers (pre-commit `precommit_charter.py`, `gator-repo-status.py`, enforcer audit phase 1) still use their own matching; moving them needs a separate decision.

### decide() / heading_names() / parse_file_line() / parse_internal() / python_signals() / javascript_signals() — shared significance policy (`POLICY = "gator-significance-v1"`)
File: src/gator_command/scripts/charter_significance.py
The one answer to "does this function need a charter entry?". `decide(name, is_private, entries, importer_owners, file_owners)` → `(decision, reason)`: `document` for an entry point (`entry`) or a name imported by a file whose owning charters are disjoint from the defining file's (`cross-module`); `internal` (`local`) otherwise; `not-applicable` for private names and `CONVENTIONAL_NAMES`. Signals: `python_signals()` (AST: `ENTRY_DECORATORS` final attribute, `func=` keywords, literal `__all__`; imports as `(module_stem, name)` through `from … import`, `import M as a` + `a.x`, `import_sibling` / `import_module` aliases) and `javascript_signals()` (regex: exports, `module.exports`, named functions assigned to `window.<path>`; `import { … } from`). `heading_names()`, `parse_file_line()` and `parse_internal()` are the charter-side readers. `parse_internal(text)` → `(names, problems)`: at most one `**Internal**:` line before the first `## `, backticked identifiers only. Only the first well-placed line suppresses anything; problem codes are `malformed`, `duplicate`, `multiple-lines` and `misplaced`.
<- `gator-charter-verify.py` (`parse_charters()`, `_parse_function_entries()`, `_collect_signals()`, `_check_function_gaps()`, `_check_stale_structure()`), `gator-charter-lint.py` (`_validate_internal()`)
! No patterns on `**Internal**:`. A finite, stale-checked name list is auditable; a wildcard would be a blanket suppression.
! Closed policy: docstrings, argument counts, file size and verb prefixes never make a function a seam by default. An importer with no owning charter (tests, undiscovered files) is ignored. Widening the policy changes every consumer's numbers at once.
! Never imports or executes inspected source; unparseable Python gives empty signals. State access and tripwires are not inferred (strict mode is the investigation tool).
! Standard library only, imported by plain name like `charter_covers`; ships through `package-data`.

### build_report(repo_root) / input_fingerprint(repo_root) / render_text(report) / unavailable_report() / failed_report() — charter health report
File: src/gator_command/scripts/charter_report.py
Build `gator-charters-report-v1` from files and Git only: `{schema, status (complete|partial|unavailable|failed), generated_at, gator_version, inputs {fingerprint, head, revision}, charters {count, lines, documented_functions, charter_dir, items[≤200], items_truncated}, coverage {grammar, source_files, covered_files, uncovered_files, percent, uncovered[≤50], uncovered_truncated}, code {product_files, product_lines, charter_to_code_pct, target {3, 6, constitution}, band, modules[≤200] {charter, files, lines, paths[≤50], paths_truncated}, modules_truncated, uncovered_module, largest_files[≤10]}, sync, measurement, problems[≤20]}`; `unavailable` carries `reason`, `failed` carries `error` (≤300 chars) and nothing else.
<- `gator-charters.py main()`; `input_fingerprint()` also ← the Dashboard report relay (checkpoint 3)
-> `gator-charter-draft.discover_files()` (the source-file set), `gator-charter-verify.parse_charters()` (the charter set, lines, documented functions) through `import_sibling`, `charter_covers.coverage_index()`, `gator_core.resolve_charter_surface()` (charter directory), `dashboard.charter_sync.read_last()` (sync summary)
! Reuse, not copy: the report never runs the verifier's checks or the sync check and never writes a file. Because it uses the verifier's own file and charter sets, `coverage.uncovered_files` equals the verifier's `coverage-gap` count on the same tree (pinned).
! **Fingerprint.** SHA-256 over canonical JSON of the schema, `gator_version()`, HEAD (null when unborn), SHA-256 of `ls-files -s -z`, each `--no-optional-locks status --porcelain=v1 -z --untracked-files=no` entry's `(path, XY, size, mtime_ns)`, the charter directory's `*.md` `(name, size, mtime_ns)`, `.charterignore`'s stat, and the charter sync record's bytes. Any Git failure → None ("unknown" to consumers); it never raises. It is taken before any input is read, so an edit during a run leaves the report stale, never falsely current. Stat-based detection shares Git's same-size, same-tick limit.
! `modules[].paths` / `paths_truncated` (additive in v1, 2026-11-06) list the covered source files in discovery order, capped at `MODULE_PATHS_MAX` (50), so a consumer can say what each charter covers.
! **States.** No `.gator/` or not a work tree → `unavailable`; a Git read failure or a missing verifier → `failed`. An unreadable source file (counted as 0 lines) or an unavailable sync reader (`sync.state: unavailable`) → `partial` with `problems`. No sync record → `sync.state: none`, not a problem. No charters → `complete` with every source file uncovered.
! `gator_version()` resolves from this file's directory, never the caller's working directory, so a CLI run and the Dashboard of one install compute the same fingerprint; it never raises (`unknown`).
! The coverage percent uses the verifier's file set, not `gator-repo-status.py`'s `charter_coverage_pct`; the two can differ (`measurement.coverage` says which). Prose fragments in a charter's `**Covers**` line are read as entries: a directory fragment such as `src/gator_command/scripts/` claims that whole directory.

### main()
File: src/gator_command/scripts/gator-charters.py
`gator charters report [--json] [--path P]`: one positional `action` (`report`) and flat optionals, so `report --json` and the Dashboard's `--json report --path P` both parse. Prints `render_text()` or the JSON (`indent=2`). Exit 0 for `complete` / `partial`, 1 for `unavailable` / `failed`; the JSON body is printed either way. An unexpected exception becomes `failed` with a one-line message, never a traceback on stdout.
<- `cli.py` `COMMANDS["charters"]`, `helpers.run_json("gator-charters", "report", ...)` (checkpoint 3)
-> `find_gator_root()`, `charter_report`

## Before Changing This Module

- Test Windows and POSIX path normalization.
- Preserve text and JSON output schemas.
- Run `tests/test_charter_lint.py`, `tests/test_charter_covers.py`, `tests/test_charter_report.py`, `tests/test_charter_significance.py`, `tests/test_charter_verify_functions.py` and focused draft/verify tests.
- Keep `gator-charters-report-v1` additive; a removed or redefined field needs a schema bump and consumer migration.
- Validate the repository's own charters as a dogfood case.

## Connections

-> [Cross-Cutting](scripts-cross-cutting.md) - canonical charter-surface resolver
-> [Repo Lifecycle](scripts-repo-lifecycle.md) - boot-time charter counts
-> [Charter README](README.md) - authoring and size rules, the `**Internal**:` line and the function-gap repair rule (the starter `charters/README.md` and `docs/charter-schema-v1.html` carry the same schema text)
