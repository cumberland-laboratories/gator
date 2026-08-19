# Charter: Repo Lifecycle

**Covers**: `src/gator_command/scripts/gator-init.py`, `src/gator_command/scripts/gator-update.py`, `src/gator_command/scripts/gator-charter-lint.py`, `src/gator_command/scripts/gator-charter-draft.py`, `src/gator_command/scripts/gator-charter-verify.py`, `src/gator_command/scripts/gator-policy-status.py`, `src/gator_command/scripts/gator-pulse.py`

## Owns

Per-repo governance lifecycle operations:

- `gator-init.py` owns the branded boot sequence for governed fleet repos. Detects `.gator/`, reads the knowledge layer via `gator_layout.get_gator_paths()` (all detection functions take a `GatorPaths` object, not raw `gator_dir`), self-heals missing/stale git hooks via `gator-update.py`, auto-registers the repo in the machine-local dashboard registry via `ensure_dashboard_registry_entry()`, and prints a formatted status display. Designed to run at session open in any AI CLI. Layout-aware: works on both v1 and v2 repos.
- `gator-update.py` owns the two-channel overlay-update process. Layout-aware: detects v1/v2 via `gator_layout` and routes shipped content to `.gator/.includes/` on v2 repos, `.gator/` root on v1 repos. User content always targets root. Channel 1 (all repos): resolves template source via `product-source.json` (or `--source` arg or thin-link fallback) and overlays template-derived files. `SHIPPED_TEMPLATE_DIRS` (scripts, procedures, reference-notes, blueprints) go to `.includes/` on v2. `USER_TEMPLATE_DIRS` (docs, artifacts, threads, etc.) always go to root. Channel 2 (policy-synced repos only): syncs org policy via thin link. Standalone repos get channel 1 only. `install_git_hooks()` resolves hook wrapper script path via layout resolver for v2 repos. Never touches user content. Never flips the layout — follows whichever layout it finds.
- `gator-charter-lint.py` owns structural validation of charter files against Charter Schema v1. Checks title format, Covers line, required sections (Owns, Does Not Own), function entry structure, and index dispatch tables.
- `gator-charter-draft.py` owns mechanical charter scaffold generation. Three analysis tiers: Python (full `ast`), JS/TS and shell (regex-based function/class extraction), and minimal (line count for coverage tracking). Emits charter drafts with clear machine/agent boundary markers. Machine extracts structure; agent writes meaning.
- `gator-charter-verify.py` owns structural charter quality checking. Compares existing charters against actual code structure and emits findings (coverage-gap, function-gap, complexity-mismatch, stale-structure, cross-cutting-suspect). Analyzes all supported languages (Python, JS/TS, shell) using the same analyzers as charter-draft. Function-gap uses heuristics to suppress conventional helpers and only flag charter-worthy functions. Parses both `###` and `####` entries from charters (methods use `####`). Findings are warnings, not verdicts — the enforcer judges materiality.
- `gator-pulse.py` owns generation of `.gator/pulse.md` — a read-only strategic operations brief assembled from the knowledge layer (roadmap, issues, inbox, mission, sessions, latest project-assessment artifact) and recent git history. It reads evidence and synthesizes orientation sections (Next Steps, Project Assessment, Roadmap Check, Priorities, Issues & Blockers, Recent Activity); it never mutates the knowledge layer.
- `gator-policy-status.py` owns policy sync state reporting and cache materialization. Four modes: status (report sync state), sync (materialize policy cache from source — local or remote), init (generate `governance-source.json` from thin link — explicit sources only, no implicit remote inference), reinit (rebuild `governance-source.json` from thin link, overwriting existing — repair path for repos with implicitly inherited remote URLs). Source resolution: tries `governance-source.json` first, falls back to `command-post.md` thin link. `governance-source.json` stores `remote_url` as portable primary source (only when explicitly configured) and `_local_path_hint` as machine-local fast path. Remote sync uses `git fetch --depth=1` + `git show FETCH_HEAD` — no named remote created.

## Does Not Own

- Initial gatorization (creating `.gator/` from scratch) — that belongs to `gatorize.py` (bash chain retired in v2.4.0).
- Template content — templates live in `src/gator_command/templates/gator-starter/` and are owned by the PI who maintains the command post.
- Charter content quality — the linter validates structure only, not semantic correctness or path resolution.

---

### count_charters(paths)
File: `src/gator_command/scripts/gator-init.py`
Counts charter files and estimates function coverage by scanning `### FunctionName()` lines across all charters and counting `def`/`func`/`function` declarations in source files.
Filesystem: `.gator/charters/` (R), repo source files (R)
<- `print_boot_sequence()`, `print_json()`
! Coverage estimation is a heuristic — it walks all source extensions but skips `.gator/` itself. The percentage is an approximation shown for orientation, not a precise audit figure.

### count_field_guides(paths)
File: `src/gator_command/scripts/gator-init.py`
Counts field guide languages from `*-patterns.md` files in `.gator/field-guides/`.
Filesystem: `.gator/field-guides/` (R)
<- `print_boot_sequence()`, `print_json()`
! Field guides are only displayed in the boot output when at least one exists. Absence is silent — not shown as a warning or gap.

### ensure_git_hooks(repo_root, paths)
File: `src/gator_command/scripts/gator-init.py`
Self-heals git hooks at session start by importing `gator-update.py`, checking whether the generated Python wrappers match the managed hook directory, and reinstalling them when missing or stale. On Windows this also repairs `core.hooksPath`. Returns a status dict used by both text and JSON boot output. Reports `degraded` when `gator-pre-commit.py` is missing — never false-green `ok`.
Filesystem: managed hook dir (RW), `.git/config` (RW on Windows), `.gator/scripts/gator-pre-commit.py` (R)
<- `main()`
-> `gator-update.plan_hook_updates()`, `gator-update.install_git_hooks()`
! This is intentionally side-effecting at session start. `.gator/` travels in Git; `.git/hooks/` does not. Cloned repos need a reliable self-heal point.
! Missing `gator-pre-commit.py` must return `degraded`, not `ok`. Without the target script, hooks can't work even if installed — silent false-green is the failure mode this feature exists to prevent.

### print_boot_sequence(repo_root, paths, hook_status, registry_status)
File: `src/gator_command/scripts/gator-init.py`
Renders the branded boot display: gator ASCII art (from `GATOR_MARK_LINES`), version, and status lines for constitution, charters, working set, field guides, enforcer, git hooks, and dashboard registry. The constitution line appends `" · modified from baseline"` when `_constitution_drift_suffix()` detects drift against the resolved template source (Stage 5 — warning-only, source-repo exempt, best-effort with graceful degradation).
Filesystem: reads all detection functions
@reads: `.gator/constitution.md`, `.gator/charters/`, `.gator/threads/`, `.gator/active-threads/`, `.gator/field-guides/`, `.gator/scripts/`, `.gator/.gator-version`, `.gator/product-source.json` (via drift check)
<- `main()`
-> `count_constitution_rules()`, `count_charters()`, `count_working_set()`, `count_field_guides()`, `detect_enforcer()`, `_constitution_drift_suffix()`, `GATOR_MARK_LINES` from `gator_core`
! `GATOR_MARK_LINES` is the single source of truth for the ASCII logo. Never copy it into this file.
! The drift suffix MUST stay best-effort. Any failure inside `_constitution_drift_suffix()` — sibling script missing, template source unresolvable, unreadable files — degrades silently to no suffix. `gator init` runs at every session open; a fatal drift check would break session-opening.

### _constitution_drift_suffix(repo_root)
File: `src/gator_command/scripts/gator-init.py`
Returns `" · modified from baseline"` when constitution drifts, else `""`. Loads `gator-state` via `import_sibling` and calls `check_constitution_drift()`. Any exception → empty string (never raises).
<- `print_boot_sequence()`
-> `import_sibling("gator-state")`, `gator-state.check_constitution_drift()`
! Source-repo exemption is handled inside `check_constitution_drift()` — returns `"source-repo-exempt"`, which this function renders as no suffix. Do not add a separate `is_source_repo()` check here; that would duplicate the guard and drift the two implementations.

### count_constitution_rules(paths)
File: `src/gator_command/scripts/gator-init.py`
Counts enforceable rules in the constitution by matching numbered bold items, bold-prefixed dash items, and standalone bold imperatives — a heuristic, not a parser.
Filesystem: `.gator/constitution.md` (R)
<- `print_boot_sequence()`, `print_json()`

### count_working_set(paths)
File: `src/gator_command/scripts/gator-init.py`
Counts thread files and their total line count across `active-threads/` and `threads/` subdirectories.
Filesystem: `.gator/active-threads/`, `.gator/threads/` (R)
<- `print_boot_sequence()`, `print_json()`

### detect_enforcer(paths)
File: `src/gator_command/scripts/gator-init.py`
Detects enforcer configuration by checking for `enforcer-prompt.md` and `enforcer-review.py`; returns `"ready"`, `"partial"`, or `"not configured"`.
Filesystem: `.gator/scripts/enforcer-prompt.md`, `.gator/scripts/enforcer-review.py` (R)
<- `print_boot_sequence()`, `print_json()`

### read_version(paths)
File: `src/gator_command/scripts/gator-init.py`
Reads `.gator/.gator-version` and returns its key-value pairs as a dict.
Filesystem: `.gator/.gator-version` (R)
<- `print_json()`

### format_check(label, value, width=16)
File: `src/gator_command/scripts/gator-init.py`
Formats a single status line with a checkmark prefix and fixed-width label for the boot display.
Filesystem: none (returns string)
<- `print_boot_sequence()`

### print_json(repo_root, paths, hook_status, registry_status)
File: `src/gator_command/scripts/gator-init.py`
Prints the full boot status as a JSON object for programmatic consumption, calling all detection functions.
Filesystem: reads all detection functions, stdout (W)
<- `main()`

### print_not_found()
File: `src/gator_command/scripts/gator-init.py`
Prints the branded header with a "no .gator/ found" message and gatorize instructions when no governed repo is detected.
Filesystem: stdout (W)
<- `main()`

### main()
File: `src/gator_command/scripts/gator-init.py`
Entry point: parses `--path`, `--json`, and `--hook` args, finds the gator root, self-heals hooks, registers with the dashboard, and dispatches to text, JSON, or vendor hook output. `--hook` captures boot display text and emits it as `hookSpecificOutput.additionalContext` JSON — available for manual use but not wired into the automatic SessionStart hook chain (models receive the context but don't act on it, so automatic injection was removed). Returns silently (no error, no exit 1) when `--hook` is set and no `.gator/` is found.
Filesystem: delegates to detection and output functions
<- CLI invocation (`gator init`)

---

### plan_updates(templates_dir, gator_dir, repo_root)
File: `src/gator_command/scripts/gator-update.py`
Builds the full update plan by comparing template files to installed versions. Layout-aware: detects v1/v2 via `gator_layout.resolve_gator_layout()` and routes shipped content to `.gator/.includes/` on v2 repos, `.gator/` root on v1 repos. User-content directories always target `.gator/` root regardless of layout. Read-only: does not create directories or write files.
Filesystem: templates (R), `.gator/` (R), `.gator/.includes/` (R on v2)
<- `main()`
-> `plan_file_update()`, `_plan_dir_overlay()`
! `plan_updates()` is deliberately read-only. Directory creation happens in `execute_updates()`. This separation enables accurate dry-run output — the plan reflects reality without side effects.
! On v2 repos, shipped content (scripts, procedures, reference-notes, blueprints, constitution, startup guide, charterignore) is routed to `.includes/`. Scaffolding files (`_template.md`, `README.md`) in shipped directories are routed to the user-visible root even on v2 — agents need them visible alongside user content. On v1 repos, everything goes to the flat root. The updater never flips the layout — it follows whichever layout it finds.
! Raises `RuntimeError` on mixed or invalid layouts — refuses to write. Forces the user to run `--migrate-layout` first. This prevents silently reinforcing a broken layout.
! `main()` self-heals a stale `product-source.json` before calling `plan_updates()`. When `resolve_template_source()` returns None (typically because the recorded `gator_root` points at a nonexistent pipx venv path — the fleet-wide bug exposed by v2.4.0's Dashboard-Update-endpoint swap and fixed in v2.4.1), main() falls back to `Path(__file__).resolve().parent.parent`, prints a "Self-healing" warning, and rewrites `product-source.json` (preserving `installed`, refreshing `updated`) so future runs don't need the fallback. Fleet-repo direct invocations of the template mirror at `.gator/scripts/gator-update.py` correctly fail through to the "run --source" error — the mirror's parent.parent has no templates alongside. Any change to the fallback logic must land in BOTH the package copy and the template mirror per the Stage 4b sync obligation. See `scripts-cross-cutting.md` "TRIPWIRE: product-source.json self-heal" for the full contract.
! `.gator-version` stamping has TWO different gate semantics (as of v2.4.2):
  - **`cli-version`** stamps on EVERY successful gator-update run — records the CLI that last verified the repo. Drives the Dashboard Fleet "Version" column and its Update-button enable/disable logic. Prior to v2.4.2 this was gated on `made_changes`, which caused a fleet-wide bug where already-current repos never re-stamped after a CLI upgrade, and their Update buttons stayed falsely enabled forever.
  - **`updated:`** timestamp still gates on `made_changes` (file overlay OR entry-point actions changed state) — preserves the "last modification" semantic.
  Sync obligation applies: the branching logic (`if line.startswith("updated:") and made_changes`) must match byte-for-byte between `src/gator_command/scripts/gator-update.py` and `src/gator_command/templates/gator-starter/scripts/gator-update.py`. Regression guard: `TestCliVersionAlwaysStamps` in `tests/test_update_entry_points.py` uses a subprocess invocation to pin the cli-version-always-stamps behavior.

### plan_entry_point_updates(repo_root)
File: `src/gator_command/scripts/gator-update.py`
Stage 4b. Plans managed-block refresh actions for `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`. Returns list of dicts `{filename, agent_type, state, action}`. Read-only.
Dispatch: `clean` → skip (no plan entry); `modified` → `refresh-block` (executor writes `<filename>.pre-gator-update` sibling backup first); `legacy` → `upgrade-legacy` (delegates to `upgrade_legacy_entry_point()`); `absent` → `create-fresh` (deterministic, non-destructive); `corrupted` / `foreign` → skip (ambiguity — `gator state repair` or `gatorize` respectively).
Filesystem: entry-point files at repo root (R)
<- `main()`
-> `classify_managed_block()`, `render_entry_content()` (both via the guarded import; empty list when `_ENTRY_POINT_REFRESH_AVAILABLE` is False)
! Empty list when the gatorize sub-package is not reachable (template copy on fleet repos run directly rather than via the pipx CLI). Graceful degradation, not an error.
! Same baseline invariant as `gator state status` / `gator state repair`: `render_entry_content(has_command_post=False, agent_type)` from the currently-imported `gator_command` package. Do NOT call `find_command_post()` at check time.

### execute_updates(plan)
File: `src/gator_command/scripts/gator-update.py`
Executes the update plan: copies "add" and "update" files, creates parent directories as needed. Before execution, `main()` calls `ensure_repo_gitignore(repo_root)` (imported from `gatorize` via `import_sibling`) to converge gitignore rules, ensuring existing repos pick up new entries like `.gator/session-blocks/` without re-gatorizing. Entry-point block refresh is executed separately via `execute_entry_point_updates()` — the two are decoupled so JSON/dry-run output can preview both without executing either.
Filesystem: `.gator/` template-derived files (W), `.gator/.includes/` on v2 repos (W)

### execute_entry_point_updates(repo_root, actions)
File: `src/gator_command/scripts/gator-update.py`
Stage 4b. Executes the planned entry-point actions. Annotates each action with an `outcome` field. `refresh-block` writes `<filename>.pre-gator-update` sibling backup before overwriting the sentinel region (content outside sentinels byte-preserved). `upgrade-legacy` delegates to `upgrade_legacy_entry_point()`. `create-fresh` writes a new sentinel-wrapped file, no backup written.
Filesystem: entry-point files (RW), `<filename>.pre-gator-update` backups (W on `refresh-block` only)
<- `main()` (after `execute_updates()`)
-> `find_managed_block()`, `render_managed_region()`, `render_entry_content()`, `upgrade_legacy_entry_point()`
! `refresh-block` re-parses via `find_managed_block()` — defensive against the file changing between plan and execute (returns `skipped-race` if the sentinel pair is no longer well-formed).
! Never touches `*.local.md` files — Invariant #7 of the Stage plan.
! `corrupted` and `foreign` states are never planned here (see `plan_entry_point_updates()`), so no executor branch handles them — those belong to `gator state repair` (corrupted) and `gatorize` (foreign) exclusively.

### print_plan(plan, dry_run=False, hooks=None, entry_point_actions=None)
File: `src/gator_command/scripts/gator-update.py`
Renders the human-readable plan. Stage 4b added the `entry_point_actions` parameter — when non-empty, an "Entry-point blocks" section prints per-file state + planned action alongside the file/hook sections.
<- `main()` (dry-run and execute paths)

### print_json_plan(plan, templates_dir, hooks=None, entry_point_actions=None)
File: `src/gator_command/scripts/gator-update.py`
Emits the plan as JSON with top-level `"schema": "gator-update-v1"` (added in Stage 4b — closes a pre-existing gap against the Schema Versioning TRIPWIRE). New field `entry_point_actions` runs parallel to the existing `hooks` list; `summary.entry_point_actions` is the count. Existing fields (`version`, `templates`, `plan`, `hooks`, `summary`) preserved unchanged — additive within `gator-update-v1`.
<- `main()` (`--json` path)
! Any change to the top-level shape MUST bump the schema. Adding fields inside `gator-update-v1` is additive; renaming or removing fields is a v1→v2 bump requiring downstream migration (dashboard, drift tooling, packaging tests).

### _enumerate_mixed_residue(gator_dir)
File: `src/gator_command/scripts/gator-update.py`, `src/gator_command/templates/gator-starter/scripts/gator-update.py`
Called only from `migrate_layout()`'s Step 11 when the post-migration classifier returns `mixed`. Returns a list of `(path_str, reason)` tuples so the migration report can point the operator at concrete files/directories instead of the historical "check conflicts" hand-wave. Enumerates the same three categories as `_has_legacy_shipped_content` (Category 1: shipped root files at root; Category 2: fully shipped directories at root holding real content — scaffolding-only dirs correctly skipped; Category 3: shipped default files at root of mixed directories). Distinguishes "duplicated in .includes/" vs "should have moved to .includes/" per category so the reason column tells the operator whether to delete-the-duplicate or investigate-the-move-failure.
<- `migrate_layout()` Step 11 (mixed-result branch)
-> `gator_layout.SHIPPED_ROOT_FILES`, `gator_layout.SHIPPED_DIRECTORIES`, `gator_layout.MIXED_DIRECTORY_SHIPPED_DEFAULTS`, `gator_layout.USER_VISIBLE_SCAFFOLDING`
! **Sync obligation with `_has_legacy_shipped_content` in `gator_layout.py`.** Any new mixed-detection category added to the classifier MUST be mirrored here or the report will silently under-report the residue — and the operator will hit a `mixed` result with no blocking-path list, triggering the "Classifier reported mixed but no residue enumerated" belt-and-suspenders branch. Regression pins: `tests/test_layout.py::TestMigration::test_enumerate_mixed_residue_finds_root_file`, `test_enumerate_mixed_residue_ignores_scaffolding_only_dir`, `test_enumerate_mixed_residue_reports_dir_with_real_content`.

### _merge_dir_files_only(src, dest, report, prefix)
File: `src/gator_command/scripts/gator-update.py`, `src/gator_command/templates/gator-starter/scripts/gator-update.py`
Recursive files-only merge helper. Used only by `migrate_layout()`'s Step 5 to handle both-directories-exist cases whose names aren't in the known-safe legacy allowlist (`__pycache__`, `hooks`). Moves files not in dest; on file collision, removes src (dest is canonical, matching Step 4's SHIPPED_ROOT_FILES rule). Recurses into subdirs. Non-file/non-dir entries (symlinks, sockets) and subdirs that still hold content after merge are logged into `report["conflicts"]` and left in place so the operator sees a concrete path in the final migration report.
Filesystem: src (RW — moves/removes), dest (W — creates)
<- `migrate_layout()` Step 5
! Recurses without a depth guard. Callers must only invoke on directories under `.gator/` (bounded by `SHIPPED_DIRECTORIES` in Step 5) — never on an unbounded ancestor.
! `mkdir(exist_ok=True)` on dest is safe because Step 5 only calls this when both src and dest already exist as directories.

### migrate_layout(repo_root, gator_dir, templates_dir)
File: `src/gator_command/scripts/gator-update.py`
The ONLY code path that moves files from v1 flat `.gator/` to `.gator/.includes/`. Invoked by `--migrate-layout` flag. Refuses unless layout is v1 or repairable mixed. Moves shipped root files, shipped directories, and shipped files from mixed directories. Regenerates Git hook wrappers for new `.includes/scripts/` path. Writes `layout-version.json`. Emits a deterministic migration report. Re-validates the result.
Filesystem: `.gator/` (RW — moves files), `.gator/.includes/` (W — creates), `.gator/layout-version.json` (W), managed git hooks (W)
<- `main()` when `--migrate-layout` is set
-> `gator_layout.resolve_gator_layout()`, `gator_layout.get_shipped_files_for_directory()`, `install_git_hooks()`
! This is the single migration surface. No other code path may move files between v1 and v2 locations. Idempotent: re-running on v2 is a no-op.
! Mixed directories (procedures, charters, blueprints) are split by template-derived classification: shipped files move, user files stay. Scaffolding (`_template.md`, `README.md`) is always preserved at root. Falls back to bootstrap defaults if template source unavailable.
! **Duplicate handling in Step 5 (SHIPPED_DIRECTORIES) must mirror Step 4 (SHIPPED_ROOT_FILES).** When a file exists at BOTH `.gator/<shipped-dir>/X.md` AND `.gator/.includes/<shipped-dir>/X.md`, the `.includes/` copy is canonical and the root copy is removed (not preserved). Without this, a repo where a shipped directory was bootstrapped to root AND populated in `.includes/` (e.g. re-gatorized on top of a v1-shape port — the exact state the monorepo cutover hit in `.gator/reference-notes/`) leaves the root duplicates in place, `--migrate-layout` reports "Result: mixed (migration incomplete — check conflicts)", and the tool never converges. Regression pin: `tests/test_layout.py::TestMigration::test_shipped_dir_duplicates_get_removed`. Fixed 2026-08-02.
! **Step 5 directory-conflict handling (Issue #6, fixed 2026-08-03).** Sibling defect to the file-conflict fix above. When a shipped directory exists at BOTH `.gator/<shipped-dir>/<subdir>/` AND `.gator/.includes/<shipped-dir>/<subdir>/`, Step 5 must NOT leave the src-side subdir in place. Known-safe legacy names — `__pycache__/` (Python bytecode) and `hooks/` (pre-monorepo git-hook install location; `install_git_hooks()` now writes to `.git/hooks/` or `.git/gator-hooks/`) — get `shutil.rmtree`'d unconditionally. Everything else goes through `_merge_dir_files_only()` (below), which recursively moves files (dest-wins on collision) and logs any unresolvable residue into `report["conflicts"]`. Without the fix, `src_dir.rmdir()` fails silently (except OSError: pass) whenever any subdir survives, layout re-detects as `mixed`, and migration never converges on any fleet repo that ever ran a Python script under `.gator/scripts/`. Regression pins: `test_shipped_dir_pycache_conflict_removed`, `test_shipped_dir_unknown_dir_conflict_merges`.
! Migration moves files but does not update their content. A post-migration `gator update` is required to refresh the scripts in `.includes/` with resolver-aware versions. The migration prints a reminder.
! **Non-convergence report enrichment (A2, 2026-08-03).** When `final_layout == "mixed"`, Step 11 now calls `_enumerate_mixed_residue(gator_dir)` and prints each blocking path with a per-path reason ("root-side file duplicated in .includes/", "root-side directory could not be merged", etc.) followed by a "Suggested next step" hint. The prior message ("Result: mixed (migration incomplete — check conflicts)") gave the operator no signal of what to look at. If the enumerator returns empty but `report["conflicts"]` has entries (from `_merge_dir_files_only`), those are printed instead. If both are empty, a "should be unreachable" belt-and-suspenders branch tells the operator to inspect manually and file a bug — that path firing indicates the enumerator has drifted from `_has_legacy_shipped_content` in `gator_layout.py`.
<- `main()`
! Never deletes files. The overlay contract ("add/update, never delete") means files that exist only in the target are left untouched. This is intentional — user-created files in template directories are preserved.

### get_managed_hooks_path_value() / get_managed_hook_dir(repo_root) / get_hook_probe_dirs(repo_root) / hooks_config_needs_update(repo_root) / _configure_managed_hooks_path(repo_root) / get_managed_hook_display_path()
File: `src/gator_command/scripts/gator-update.py`
Platform-specific hook-path helpers. They define the managed install location (`.git/gator-hooks` on Windows, `.git/hooks` elsewhere), expose backward-compatible probe order for readers, detect stale `core.hooksPath`, repair it, and provide the human-readable destination path used in dry-run/JSON output.
Filesystem: `.git/config` (R/W when checking or setting `core.hooksPath`)
<- `plan_hook_updates()`, `install_git_hooks()`, fleet/drift/repo-status hook probes, dry-run output
! These helpers are the compatibility bridge during the Windows hook migration. Readers must tolerate legacy `.git/hooks` while installers converge on the managed path.

### install_git_hooks(gator_dir, repo_root)
File: `src/gator_command/scripts/gator-update.py`
Writes hook wrappers from `build_git_hook_wrappers()` into the managed hook directory and makes them executable. On Windows, also sets `core.hooksPath` to the managed directory.
Filesystem: managed hook dir (W), `.git/config` (W on Windows)
<- `main()`
-> `build_git_hook_wrappers()`
! Windows installation is not complete until both wrapper files and `core.hooksPath` are current.

### build_git_hook_wrappers()
File: `src/gator_command/scripts/gator-update.py`
Generates the exact Python wrapper contents expected in the managed hook directory for `pre-commit`, `commit-msg`, and `post-commit`. Windows uses a direct `#!C:/Windows/py.exe -3` shebang; Unix uses `#!/usr/bin/env python3`. `subprocess.call` uses exact `sys.executable` path. Each wrapper includes a guard that checks if `.gator/scripts/gator-pre-commit.py` exists before calling it. On branches where `.gator/` hasn't been merged yet, the guard prints a warning ("Proceeding in warning mode") and exits 0 — allowing the commit without blocking.
<- `plan_hook_updates()`, `install_git_hooks()`
! The shebang and `subprocess.call` path solve different problems: the shebang must launch cleanly under Git, while `subprocess.call` keeps the exact current interpreter even when its path contains spaces.
! The file-existence guard is critical for repos where `.gator/` exists on main but not on feature branches. Without it, the commit is hard-blocked with a "file not found" error from subprocess.

! `chmod +x` is a no-op on Windows but required on Unix. Always call it — the function handles the OSError silently. Hook installation happens after the overlay so the latest hook sources are installed.

### Policy cache sync step
File: `src/gator_command/scripts/gator-update.py`
After template overlay and policy version bump, syncs the policy cache from source via `gator-policy-status`. Auto-inits `governance-source.json` from the thin link if not yet present. Gracefully skips if policy-status module is unavailable.
Filesystem: `.gator/governance-source.json` (W on init), `.gator/policy-link.json` (W), `.gator/policy-cache/org-policy.md` (W)
<- `main()`
-> `_get_governance_source()`, `_init_governance_source()`, `_sync_policy()` from `gator-policy-status`
! The auto-init uses only explicitly configured remote URLs (from registry or command-post.md). It does NOT infer a remote from the command post's git origin — that would silently promote an unrelated upstream into fleet governance state.
! `--reinit` rebuilds `governance-source.json` from the thin link (`command-post.md`), overwriting the existing file. This is the manual repair path for repos initialized before the implicit-remote bug was fixed. It re-derives from the thin link (not the existing corrupted file) and applies the same no-implicit-inference rule. Caution: if a repo's `remote_url` was intentionally written directly into `governance-source.json` (not via `--init`), `--reinit` will erase it since the thin link has no record of it. Use only when the remote was implicitly inherited.
! There is no automatic migration in `gator-update` — inference cannot distinguish an implicitly inherited remote from an intentionally configured one. Repair requires explicit `gator policy-status --reinit`.
! On any exception, prints a warning and continues — policy sync failure must not block the rest of the update.

### plan_file_update(src, dest)
File: `src/gator_command/scripts/gator-update.py`
Compares a single template file to the installed version and returns an `(action, src, dest)` tuple where action is `"add"`, `"update"`, or `"unchanged"`.
Filesystem: template file (R), installed file (R)
<- `plan_updates()`

### plan_hook_updates(gator_dir, repo_root)
File: `src/gator_command/scripts/gator-update.py`
Plans git hook installations by comparing the generated cross-platform Python wrappers to the current managed hook directory contents, returning a list of `(hook_name, action)` tuples. Layout-aware: resolves the pre-commit script path via `gator_layout.get_gator_paths()` so v2 repos check `.includes/scripts/gator-pre-commit.py`. Passes the resolved script path to `build_git_hook_wrappers()` so the planned content matches what `install_git_hooks()` would actually write.
Filesystem: managed hook dir (R), scripts/gator-pre-commit.py (R, layout-resolved)
<- `main()`, `ensure_git_hooks()` in `gator-init.py`
! Must resolve the same script path as `install_git_hooks()`. If these diverge, the plan reports "unchanged" but install writes different content.

### print_result(added, updated, unchanged, entry_point_counts=None)
File: `src/gator_command/scripts/gator-update.py`
Prints the one-line summary after executing updates (e.g., "Done: 2 added, 1 updated, 5 unchanged"). Stage 4b: `entry_point_counts` is the `(refreshed, upgraded, created, skipped)` tuple returned by `execute_entry_point_updates()` — when any of refreshed/upgraded/created is non-zero, prints an additional "Entry-point blocks:" line so users see that repo state changed even when file-overlay counts are all zero.
Filesystem: stdout (W)
<- `main()`
! Signatures for `print_plan()` and `print_json_plan()` are documented in their own entries above — do not duplicate them here.

### main()
File: `src/gator_command/scripts/gator-update.py`, `src/gator_command/templates/gator-starter/scripts/gator-update.py`
Entry point: parses CLI args (`--dry-run`, `--json`, `--path`, `--source`, `--no-policy`, `--migrate-layout`), resolves template source, builds and optionally executes the update plan, syncs policy for policy-synced repos, installs git hooks, installs vendor SessionStart hook configs, and stamps version metadata. Both the package-level and template-deployed copies install vendor hooks — the template copy includes its own `merge_hooks_into_settings()`, `install_vendor_hooks()`, and `_extract_hook_commands()` implementations so governed repos can propagate new vendor hooks without depending on a pip install.
Filesystem: delegates to plan/execute/hook/policy functions
<- CLI invocation
-> `install_vendor_hooks()` (merge-safe vendor hook config propagation — separates Gator hooks from user hooks, rebuilds with template Gator hooks + preserved user hooks; never crashes on malformed user configs), `migrate_layout()` (when `--migrate-layout` is set)
! **`--migrate-layout` refreshes vendor hooks after successful convergence.** When migration lands the repo at v2, `main()` calls `install_vendor_hooks(templates_dir, repo_root)` before exit — same call the normal update path makes. This closes the v1→v2 gap where session-hook command strings in `.claude/settings.json` / `.codex/hooks.json` / `.gemini/settings.json` would otherwise stay pointed at `.gator/scripts/...` (now gone) until a follow-up `gator update`. Vendor-hook refresh is wrapped in try/except so failure prints a warning to stderr but never masks or overrides the migration's own exit code (which is 0 iff `final_layout == "v2"`).

### load_governance_source(gator_dir)
File: `src/gator_command/scripts/gator-policy-status.py`
Loads `governance-source.json` if it exists. Normalizes `_local_path_hint` into `local_path` for internal use. Returns dict or None.
Filesystem: `.gator/governance-source.json` (R)
<- `get_governance_source()`

### derive_governance_source(gator_dir)
File: `src/gator_command/scripts/gator-policy-status.py`
Derives governance source from the existing thin link (`command-post.md`). Fallback for repos without `governance-source.json`. Parses `command-post-absolute:`, `command-post:`, and `remote:` fields.
Filesystem: `.gator/command-post.md` (R)
<- `get_governance_source()`, `--reinit` handler in `main()`
! Only uses explicitly configured `remote:` values. Does NOT infer remote from the command post's git origin.

### get_governance_source(gator_dir)
File: `src/gator_command/scripts/gator-policy-status.py`
Tries `load_governance_source()` first, falls back to `derive_governance_source()`. Returns `(source_dict, is_derived)` tuple.
Filesystem: indirectly `.gator/governance-source.json`, `.gator/command-post.md` (R)
<- `main()`, `gator-update.py` via `import_sibling`

### query_local_policy(source)
File: `src/gator_command/scripts/gator-policy-status.py`
Gets the current policy commit hash and content from a local command post. Returns `(commit_hash, content, error)` tuple.
Filesystem: local command post git log + file content (R)
<- `compute_sync_state()`, `sync_policy()`

### fetch_remote_policy(source, repo_root)
File: `src/gator_command/scripts/gator-policy-status.py`
Fetches the policy file from a remote command post via `git fetch --depth=1` + `git show FETCH_HEAD:<path>`. No named remote created — FETCH_HEAD is temporary. Returns `(content, error)` tuple.
Filesystem: remote Git URL via fetch + show
<- `compute_sync_state()`, `sync_policy()`
! Do NOT expose as a read-only path — it is state-changing (mutates `.git/` refs, hits network).

### load_policy_link(gator_dir) / write_policy_link(gator_dir, link_data)
File: `src/gator_command/scripts/gator-policy-status.py`
Read/write the `policy-link.json` manifest that records the last sync state (source commit, cache hash, timestamps).
Filesystem: `.gator/policy-link.json` (RW)
<- `compute_sync_state()` (read), `sync_policy()` (write)

### compute_sync_state(gator_dir, source)
File: `src/gator_command/scripts/gator-policy-status.py`
Determines the policy sync state for a repo by comparing the cached policy against the source. Returns a dict with `state` (synced, behind, diverged, cached, no-cache, local-only, etc.), `authority`, and provenance fields.
Filesystem: `.gator/policy-link.json`, `.gator/policy-cache/org-policy.md` (R), local/remote source (R)
<- `main()`, `gator-fleet-report.py` via `import_sibling`, `gator-drift.py` via `import_sibling`
! The state taxonomy (synced/behind/diverged/cached/no-cache/local-only/offline/unreachable/no-source/unknown) is the contract that dashboard and fleet-report consume. Adding states is safe; removing or renaming breaks downstream.

### sync_policy(gator_dir, source, repo_root)
File: `src/gator_command/scripts/gator-policy-status.py`
Materializes/refreshes the policy cache from source. Tries local path first, falls back to remote fetch. Writes `policy-link.json` and `policy-cache/org-policy.md`.
Filesystem: `.gator/policy-link.json` (W), `.gator/policy-cache/org-policy.md` (W), source (R)
<- `main() --sync`, `gator-update.py` via `import_sibling`

### init_governance_source(gator_dir, source, force=False)
File: `src/gator_command/scripts/gator-policy-status.py`
Writes `governance-source.json` from derived source info. Only uses explicitly configured remote URLs — does NOT infer from command post git origin. `force=True` overwrites existing file (repair path via `--reinit`).
Filesystem: `.gator/governance-source.json` (W)
<- `main() --init`, `main() --reinit`, `gator-update.py` via `import_sibling`
! Does NOT call `git remote get-url origin`. Implicit remote inference was a previous bug that caused fleet repos to inherit the command post's upstream URL.

### print_status(data) / print_json_status(data)
File: `src/gator_command/scripts/gator-policy-status.py`
Output formatters for human-readable and JSON policy status reports.
Filesystem: none (stdout)
<- `main()`

### TEMPLATE_FILES / SHIPPED_TEMPLATE_DIRS / USER_TEMPLATE_DIRS / CHARTER_TEMPLATE_FILES
File: `src/gator_command/scripts/gator-update.py`
Constants defining the update boundary. `SHIPPED_TEMPLATE_DIRS` (scripts, procedures, reference-notes, blueprints) target `.includes/` on v2 repos. `USER_TEMPLATE_DIRS` (docs, artifacts, threads, policies, field-guides, vault, sessions) always target `.gator/` root. `TEMPLATE_DIRS` is the combined set for backward compat.
<- `plan_updates()`, `_plan_dir_overlay()`
! This boundary is the ownership contract with the Architect. Files not in these lists are user content and must never be touched. If a new template file is added to `gator-starter`, add it to the appropriate constant (shipped or user) or it will be silently skipped by `gator update`. (Files inside an already-listed directory — e.g. a new `procedures/*.md` — propagate automatically with no constant change; `plan_updates()` walks the directory.)
! Adding a directory to `SHIPPED_TEMPLATE_DIRS` means it will be routed to `.includes/` on v2 repos. Adding to `USER_TEMPLATE_DIRS` means it stays at root always.
! **Runtime-split Phase 3a (2026-08-19) — machine-side hook dispatch.** New wheel script `gator-hook.py` (`### plan_dispatch` semantics below); `build_git_hook_wrappers()` generates PIN-AWARE stubs (new `_installed_dispatcher_path()` resolves the installed CLI's dispatcher at generation time; None when the package isn't importable → stubs byte-match the pre-Phase-3 shape). Stub contract: pin present AND dispatcher file exists → route `[interp, dispatcher, <hook-name>] + sys.argv[1:]`; otherwise fall through to the pre-Phase-3 repo-script invocation verbatim. `plan_hook_updates()` S5 forward-compat: script-absent-but-pinned repos still plan stub installs (post-Phase-4 shape); script-absent AND pin-absent → empty plan. `gator-init.py::ensure_git_hooks` degraded check likewise keys on script-missing AND pin-missing. Dispatcher entry:

### plan_dispatch(hook_name, repo_root, decision, wheel_dir=None) / main()  [gator-hook.py]
File: `src/gator_command/scripts/gator-hook.py`
Machine-side hook dispatcher (runtime-split Phase 3a). `HOOK_MAP`: pre-commit/commit-msg/post-commit → `gator-pre-commit.py` phases (commit-msg forwards passthrough argv for the msg file); session-open/session-start → the session scripts. `plan_dispatch` is PURE (no side effects): `current`/`cli-newer` → wheel templates runtime (`templates/gator-starter/scripts/`); wheel-incomplete → repo copy with reinstall advisory, or refusal escalation when neither exists; `repo-scripts`/`pin-unreadable` → repo copy (v2-first probe); `refuse` + repo copy present → **run the repo copy** (it IS the pinned runtime — true refusal only bites post-Phase-4) with upgrade advisory; `refuse` + no copy → pre-commit blocks (exit 1), all other hooks warn + exit 0 (`BLOCKING_HOOKS = {"pre-commit"}` — never strand a mid-flight commit or session open); `ungoverned` → warning-mode exit 0 matching the pre-split stub contract. `main()` executes the plan via subprocess with cwd=repo_root and inherited stdin (session-start reads its vendor payload from stdin — must pass through untouched).
Filesystem: `.gator/runtime-pin.json` (R via resolver), wheel + repo runtime dirs (R)
<- pin-aware git hook stubs (generated by `build_git_hook_wrappers`), `gator hook` CLI verb (cli.py)
-> `gator_core.resolve_governed_runtime`, subprocess to the chosen runtime script
! The dispatcher supersedes the Phase 2 flag-gated in-script check as the enforcement point on pinned repos — `GATOR_RUNTIME_RESOLVER` stays available for repos reached only via the fallback path.
! Regression pins: `tests/test_gator_hook.py` (18 — every mode × availability combination) + `tests/test_hooks.py::TestPinAwareWrappers` (6).

! **Runtime-split Phase 3b (2026-08-19) — vendor SessionStart retarget.** The three vendor-hook JSON templates (`vendor-hooks/{claude-settings,codex-hooks,gemini-settings}.json`) now command `gator hook session-open` / `gator hook session-start` (CLI route via the dispatcher) instead of `python .gator/.includes/scripts/...`. **Whiteboard 2026-08-19 hardening**: the repo-scoped commands are SHELL CHAINS — `gator hook session-open || python .gator/.includes/scripts/gator-session-open.py` — so source-checkout/public-clone machines without the CLI shim fall through to the pre-split repo-script behavior (`||` works in both cmd.exe and POSIX sh; both clauses live-verified). Post-Phase-4 the fallback file disappears and the CLI clause is the only live path — the chain is honest transitional scaffolding. The merge logic's Gator-managed predicate `_is_gator_hook_command(cmd)` matches THREE shapes: `.gator/` substring (old-style AND the chain's fallback clause), bare `gator hook ` prefix, and the quoted absolute-launcher form Enterprise emits machine-side; missing any shape would duplicate the Gator group on migration. Migration contract pinned: old-style entries replaced in place, user hooks in the same group preserved (`tests/test_session_hooks.py::TestVendorHookMigration`, enterprise `TestGatorCommandPredicate` + `TestAbsolutizeCommands`).

! Runtime-split Phase 1 (2026-08-18, roadmap item 19): both `gator-update.py::main()` (immediately before `print_result`, after the `.gator-version` stamp) and `gatorize.py`'s v2 install path (after `write_gator_version`) call `gator_core.write_runtime_pin()` inside try/except — emitting the committed `.gator/runtime-pin.json` record of the shipped runtime in force. Best-effort by contract: pin failure prints a skip line, never fails the operation. See `scripts-core-library.md` for the helper's semantics; contract at `contracts/schemas/gator-runtime-pin-v1.json`. Template gator-update.py mirrors the wiring (repo-resident standalone runs emit too, via the mirrored template gator_core).
! TRIPWIRE — a shipped procedure only propagates if it exists in `templates/gator-starter/procedures/`; a copy in THIS repo's `.gator/.includes/procedures/` alone is invisible to `gator update` on fleet repos. The v2.7.0 pair (`committing-gator-files.md`, `pre-gator-residue.md`) shipped `.includes`-only by mistake and was backfilled into the template 2026-08-17 alongside the new `gator-version-drift.md` (cross-branch version drift / `.gator/` merge-conflict resolution, per-file-class rules; constitution step-8 note cross-references all three). When adding a shipped procedure: write it in the template FIRST, copy to `.includes/` second, and add the constitution cross-reference in BOTH the template constitution and this repo's `.includes/constitution.md`.

---

### parse_charter(path)
File: `src/gator_command/scripts/gator-charter-lint.py`
Parses a charter markdown file into a `CharterDoc` structure: title, Covers line, sections, function entries, separators, and type flags (index, cross-cutting).
Filesystem: charter file (R)
<- `main()`
! `_template.md` and `README.md` are in `SKIP_FILES` and never linted. `INDEX.md` is parsed but validated by `_validate_index()` (different rules). Cross-cutting charters (those with TRIPWIRE sections) are exempt from the Covers requirement.

### validate_charter(doc)
File: `src/gator_command/scripts/gator-charter-lint.py`
Validates a parsed `CharterDoc` against Charter Schema v1. Returns a list of `Finding` objects with check name, severity (error/warn/info), line number, and message.
Filesystem: none
<- `main()`
! Required sections: `# Charter: [Name]` title, `**Covers**:` line, `## Owns`, `## Does Not Own`. Recommended sections (warn, not error): `## Before Changing This Module`, `## Connections`. Function entries require a `File:` line (warn if absent).

### find_charter_dirs()
File: `src/gator_command/scripts/gator-charter-lint.py`
Finds charter directories from the current working directory: checks `.gator/charters/` (per-repo) and `.gator/charters/` (command-post).
Filesystem: cwd (R)
<- `collect_files()`
! Both directories are linted when running from the repo root. This means the command-post's own charters (this directory) are linted alongside any fleet repo's charters.

---

### load_charterignore(gator_dir)
File: `src/gator_command/scripts/gator-charter-draft.py`
Loads `.gator/.charterignore` patterns. Falls back to `FALLBACK_EXCLUSIONS` if the file doesn't exist.
Filesystem: `.gator/.charterignore` (R)
<- `discover_files()`
! The fallback exclusions are intentionally conservative. Once a repo has a `.charterignore`, the fallbacks are completely replaced — not merged.

### discover_files(repo_root, gator_dir, dirs)
File: `src/gator_command/scripts/gator-charter-draft.py`
Uses `git ls-files` to find tracked files, then filters by `--dirs` scope, `.charterignore` patterns, and supported extensions. Returns sorted list of relative paths.
Filesystem: git index (R), `.gator/.charterignore` (R)
<- `main()`

### analyze_python(file_path, rel_path)
File: `src/gator_command/scripts/gator-charter-draft.py`
Extracts structural information from a Python file using `ast`: functions (with signatures, decorators, docstrings), classes and methods, imports, entrypoint markers, module docstring, complexity signals. Returns None if the file cannot be parsed.
Filesystem: single source file (R)
<- `main()`
! Returns None on SyntaxError — unparseable files are silently skipped, not errors. This is intentional for repos with mixed Python versions.

### generate_scaffold(analysis)
File: `src/gator_command/scripts/gator-charter-draft.py`
Generates a markdown charter scaffold from analysis results. Separates mechanical structure (function inventory, imports, complexity) from agent enrichment markers (Owns, Does Not Own, tripwires).
<- `main()`
! The scaffold contains `<!-- Agent enrichment needed -->` comments — these are the contract boundary between machine and agent.

### write_scaffolds(scaffolds, output_dir, dry_run)
File: `src/gator_command/scripts/gator-charter-draft.py`
Writes scaffold files to the specified directory. Never overwrites existing files.
Filesystem: charter directory (W)
<- `main()`
! `--output-dir` overrides the default `.gator/charters/` target. In the command post repo, the authoritative charter surface is `.gator/charters/`, not `.gator/charters/`.

---

### verify(repo_root, gator_dir, dirs, changed_only)
File: `src/gator_command/scripts/gator-charter-verify.py`
Main verification entry point. Discovers files, parses charters, runs all checks, returns a list of findings. Each finding has class, severity, file, and message.
Filesystem: charters (R), source files (R via ast), git (R)
<- `main()`
! Imports analysis functions from `gator-charter-draft.py` via `import_sibling`. If charter-draft is missing, the verifier refuses to start.

### parse_charters(charter_dirs)
File: `src/gator_command/scripts/gator-charter-verify.py`
Parses all charter files and extracts structural information: Covers paths, function entries, File: references. Returns coverage_map, charter_functions, charter_function_files, and charter list.
Filesystem: charter .md files (R)
<- `verify()`
! Skips `_template.md`, `README.md`, `INDEX.md`. Checks both `.gator/charters/` and `.gator/charters/` when both exist.
! Function entries are matched to files via their `File:` line. Entries without a `File:` line are excluded from stale-structure checks to avoid false positives in multi-file charters.

---

### build_pulse(repo_path, days=7)
File: `src/gator_command/scripts/gator-pulse.py`
Assembles the full `pulse.md` content string. Gathers evidence via layout-resolved paths (`get_gator_paths()`), classifies roadmap items (done/building/designed) and issues (open/resolved), then emits the ordered sections: header, Top 5 Next Steps, Project Assessment, Roadmap Check, Top 5 Priorities, Issues & Blockers, Recent Activity, footer.
Filesystem: `.gator/roadmap.md`, `.gator/issues.md`, `.gator/inbox.md`, `.gator/mission.md`, `.gator/sessions/` (R), git log (R)
<- `main()`
-> `read_file()`, `get_recent_commits()`, `parse_roadmap_items()`, `parse_issues()`, `parse_inbox_items()`, `get_session_decisions()`, `get_latest_assessment()`, `extract_roadmap_table()`
! Section order is the pulse contract the boot flow and Architect expect. The output is a synthesis of existing knowledge-layer content — do not have it write back into roadmap/issues/inbox.

### get_latest_assessment(artifacts_dir)
File: `src/gator_command/scripts/gator-pulse.py`
Finds the newest `*project-assessment*.md` artifact (filename-sorted, date-prefixed descending), parses its YAML frontmatter for `model` and `date`, and strips the heading to return the assessment body. Returns a dict (`content`, `model`, `date`, `file`) or None.
Filesystem: `.gator/artifacts/` (R)
<- `build_pulse()`
! Relies on the date-prefixed filename convention for recency ordering, not frontmatter dates. The `model`/`date` become the signature line under the assessment in the pulse. Keep in sync with the project-assessment artifact format described in CLAUDE.md.

### parse_roadmap_items(roadmap_text)
File: `src/gator_command/scripts/gator-pulse.py`
Scans markdown table rows for a status cell (Done/Building/Working/Designed/Considering/Deferred/Open) and pairs it with the preceding name cell (bold-stripped, truncated).
Filesystem: none (operates on strings)
<- `build_pulse()`
! Status vocabulary is hardcoded. Roadmaps that use different status words will not classify into next-steps/roadmap-check buckets — extend the keyword set here if the roadmap conventions change.

### extract_roadmap_table(roadmap_text)
File: `src/gator_command/scripts/gator-pulse.py`
Returns the raw first markdown table (header + separator + rows) from the roadmap for pass-through rendering into the Roadmap Check section. Returns an empty list if fewer than three table lines are found.
Filesystem: none (operates on strings)
<- `build_pulse()`
! Preserves the source roadmap's own columns verbatim. `build_pulse()` falls back to a two-column Item/Status table built from `parse_roadmap_items()` only when this returns empty.

### get_recent_commits(repo_path, days=7, limit=30) / parse_issues(issues_text) / parse_inbox_items(inbox_text)
File: `src/gator_command/scripts/gator-pulse.py`
Evidence gatherers for the pulse. `get_recent_commits()` runs `git log --since` and returns hash/message/date dicts. `parse_issues()` extracts `### `-heading issues with their `**Status**:` value. `parse_inbox_items()` collects inbox bullets (truncated).
Filesystem: git log (R); `parse_*` operate on strings read by `build_pulse()`
<- `build_pulse()`
! These are read-only extractors. Their output shapes feed the Next Steps / Priorities / Issues sections — keep the dict keys stable if you touch them.

### get_session_decisions(sessions_dir, days=7)
File: `src/gator_command/scripts/gator-pulse.py`
Scans committed session summaries newer than the cutoff (filename date check), extracts bullets under a `## Decisions` heading, strips leading timestamp prefixes, and returns up to 10.
Filesystem: `.gator/sessions/*.md` (R)
<- `build_pulse()`
! Skips underscore-prefixed files (e.g. `_active` ledgers) and does a filename-date prefilter — session files must keep the `YYYY-MM-DD` name prefix for the window filter to work.

### main()
File: `src/gator_command/scripts/gator-pulse.py`
Entry point: ensures UTF-8 stdout, parses `--path`, `--days`, `--dry-run`, finds the gator root, builds the pulse, and either prints it (dry-run) or writes `.gator/pulse.md`.
Filesystem: `.gator/pulse.md` (W)
<- CLI invocation (`gator pulse`)
-> `find_gator_root()`, `build_pulse()`, `get_gator_paths()`

---

## Before Changing This Module

- `gator-update.py`'s `TEMPLATE_FILES`, `SHIPPED_TEMPLATE_DIRS`, `USER_TEMPLATE_DIRS`, and `CHARTER_TEMPLATE_FILES` constants are the boundary between template-derived and user-owned content. `SHIPPED_TEMPLATE_DIRS` target `.includes/` on v2 repos. Any change requires deliberate review of the ownership contract and layout implications.
- The `plan_updates()` / `execute_updates()` separation must be preserved. The dry-run path depends on plan being read-only.
- `gator-charter-lint.py` is invoked by the enforcer-review pipeline. Its exit code (0 = clean, 1 = errors) is used as a gate. Changing severity levels for existing checks may affect CI behavior.
- Charter Schema v1 requirements are enforced by `validate_charter()`. If the charter format evolves (new required sections, changed notation), update the validator and update all existing charters to pass.

## Connections

-> [scripts-core-library](scripts-core-library.md) — gator_core (find_gator_root, resolve_thin_link, GATOR_MARK_LINES)
-> [charters/README](README.md) — Charter Schema v1 specification (the standard gator-charter-lint.py enforces)
-> [scripts-cross-cutting](scripts-cross-cutting.md) — SKIP_FILES pattern, plan/execute separation
-> [Index](INDEX.md)
