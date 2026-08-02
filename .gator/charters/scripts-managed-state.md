# Charter: Managed State

**Covers**: `src/gator_command/scripts/gator-state.py`

## Owns

The `gator state` CLI surface — reporting and repairing the sentinel-delimited managed regions inside entry-point files (CLAUDE.md, AGENTS.md, GEMINI.md), plus detection-only reporting of constitution drift for fleet repos.

Two subcommands (v1):

- `gator state status` — reports per-file state using the canonical six-state vocabulary (`clean` / `modified` / `legacy` / `corrupted` / `absent` / `foreign`), companion-file presence (`*.local.md` — informational only, never read), constitution drift for fleet repos, and a version-diagnostic line showing host CLI version vs. the repo's recorded gatorized version.
- `gator state repair` — restores managed regions. Repair dispatches by state: `clean` → no-op; `modified` → sentinel-region byte-splice from `render_entry_content()`; `legacy` → delegate to `upgrade_legacy_entry_point()`; `corrupted` → backup to `<VENDOR>_ROLLBACK.md` then recreate; `absent` → create fresh; `foreign` → skip, refer to `gatorize`.

Constitution repair is NOT owned here — detection-only in v1 per plan Stage 5. Local companion files (`*.local.md`) are NEVER read, written, created, or deleted (ownership boundary — Invariant #7).

## Does Not Own

- Sentinel parsing and classification — that is `gatorize/managed_block.py`'s API (`find_managed_block`, `classify_managed_block`, `render_managed_region`, `detect_legacy_gator_content`, `BlockState`).
- Baseline resolution — reuses `gator_core.resolve_template_source()` (the same resolver `gator-update.py` uses).
- Legacy-upgrade byte format — delegated to `entry_points.upgrade_legacy_entry_point()`.
- Any mutation of `*.local.md` — those are strictly user-owned; only `gatorize.ensure_repo_gitignore()` even mentions the filenames.
- Any mutation of the source-repo `constitution.md` — the source repo's root constitution IS the baseline; there is nothing to drift from. `is_source_repo()` guards this.

---

### SCHEMA
File: `src/gator_command/scripts/gator-state.py`
Module-level string constant `"gator-state-v1"`. Appears at the top of every JSON payload (`status` and `repair`) per the JSON Schema Versioning TRIPWIRE in `scripts-cross-cutting.md`.
! Bumping the schema means downstream consumers (dashboard, tests, JSON-scraping tools) must migrate. New fields inside the v1 shape are additive and do not require a bump.

### is_source_repo(repo_root)
File: `src/gator_command/scripts/gator-state.py`
Returns True iff the repo is the source `gator-command` repo — detected by presence of `.gator/mission.md` alongside root `constitution.md`. Used to short-circuit the constitution drift check with the `"source-repo-exempt"` verdict.
Filesystem: `repo_root/.gator/mission.md` (R), `repo_root/constitution.md` (R)
<- `check_constitution()`, `collect_status()`
! This is the SAME two-file signature the constitution's Special Case section relies on. Both signals must be present — a repo with only one of them is NOT the source repo and receives normal drift checks.

### read_repo_gator_version(repo_root)
File: `src/gator_command/scripts/gator-state.py`
Reads the `cli-version` field from `.gator/.gator-version` (written by `gatorize.write_gator_version()`). Returns the version string or None. Never raises — missing file / unreadable content / absent key all return None.
Filesystem: `.gator/.gator-version` (R)
<- `collect_status()` for the version-diagnostic line
! Only used for diagnostics — MUST NOT be treated as a baseline. Baseline is host-scoped per Invariant #8.

### local_companion_present(repo_root, filename)
File: `src/gator_command/scripts/gator-state.py`
Returns True if `<VENDOR>.local.md` exists at repo root for the given entry-point filename. NEVER reads the file — only `.exists()`.
Filesystem: `repo_root/<VENDOR>.local.md` (existence check only)
<- `collect_status()`
! This is the ownership boundary — Invariant #7. Any code path here that opens a `*.local.md` file for read or write is a bug.

### classify_entry_point(repo_root, filename, agent_type)
File: `src/gator_command/scripts/gator-state.py`
Reads the entry-point file (if present), computes the baseline via `render_entry_content(has_command_post=False, agent_type=...)` (hardcoded False per Invariant #13), and delegates to `managed_block.classify_managed_block()`. Returns `(BlockState, text_or_None)`.
Filesystem: `repo_root/filename` (R)
<- `collect_status()`, `plan_repair()`
-> `render_entry_content()`, `classify_managed_block()`

### check_constitution(repo_root, templates_dir)
File: `src/gator_command/scripts/gator-state.py`
Returns a dict with a `"status"` key that is one of `"source-repo-exempt"` / `"no-baseline"` / `"no-repo-constitution"` / `"clean"` / `"modified"`. Source-repo exemption checked first; then absent baseline, absent repo constitution, then byte-compare.
Filesystem: templates_dir/constitution.md (R), `get_gator_paths(repo_root).constitution` (R)
<- `collect_status()`, `check_constitution_drift()`
-> `is_source_repo()`, `get_gator_paths()`
! Constitution is NEVER repaired in v1 (plan Stage 5 keeps it detection-only). Callers that display the `modified` status also print a "repair is deferred" line pointing to manual copy.

### check_constitution_drift(repo_root)
File: `src/gator_command/scripts/gator-state.py`
Stage 5 convenience wrapper — resolves the template source internally via `resolve_template_source()` and delegates to `check_constitution()`. Returns the same status dict. Never raises: any failure inside `resolve_template_source()` degrades to `{"status": "no-baseline"}` so `gator init`'s best-effort drift check stays fast and non-fatal.
Filesystem: `.gator/product-source.json` (R via resolver), plus what `check_constitution()` reads
<- `gator-init._constitution_drift_suffix()` (via `import_sibling("gator-state")`)
-> `resolve_template_source()`, `check_constitution()`
! Signature deliberately takes only `repo_root` so `gator init` doesn't need to know about template-source resolution. Adding parameters here means teaching every caller about the resolver — keep the surface flat.

### collect_status(repo_root)
File: `src/gator_command/scripts/gator-state.py`
Assembles the full status report as a dict: `schema`, `repo_root`, `host_cli_version`, `repo_gator_version`, `entry_point_baseline_kind` (fixed `"installed-package-code"`), `constitution_baseline_source` (path or None), `entry_points` (list of per-file records), `constitution` (dict from `check_constitution()`). Takes no source override — see the Baseline Sources TRIPWIRE below for why entry-point baseline is not file-based.
Filesystem: delegated (calls the read helpers above)
<- `main_status()`
-> `resolve_template_source()`, `classify_entry_point()`, `local_companion_present()`, `check_constitution()`, `get_version()`, `read_repo_gator_version()`

### render_status_text(report)
File: `src/gator_command/scripts/gator-state.py`
Concise text rendering of the status report: version diagnostic line, per-file state + companion presence, constitution verdict.
<- `main_status()`

### render_status_json(report)
File: `src/gator_command/scripts/gator-state.py`
Serializes the status report dict to indented JSON.
<- `main_status()`

### plan_repair(repo_root, only_filename=None)
File: `src/gator_command/scripts/gator-state.py`
Returns a list of planned repair actions (one per entry-point file, or one for the single file named via `only_filename`). Read-only — mirrors the plan/execute separation TRIPWIRE from `scripts-cross-cutting.md`. Each entry: `{filename, agent_type, state, action}`.
Filesystem: delegated (classify_entry_point reads files)
<- `main_repair()`
-> `classify_entry_point()`, `_plan_action_for_state()`

### _plan_action_for_state(state, meta)
File: `src/gator_command/scripts/gator-state.py`
Maps a `BlockState` to a machine-readable action string. Private.

### execute_repair(repo_root, plan)
File: `src/gator_command/scripts/gator-state.py`
Executes each planned action and annotates the plan with an `outcome` field. All mutation happens here.
Filesystem: entry-point files (RW), `<VENDOR>_ROLLBACK.md` backups (W) on `corrupted`
<- `main_repair()` (when not `--dry-run`)
-> `_execute_one()`
! Dispatch is by `entry["action"]` string, not `entry["state"]`. Keep `_plan_action_for_state()` and `_execute_one()` in lockstep — an action string emitted by the planner that the executor does not handle silently falls through to `skipped-unknown`.

### _execute_one(repo_root, entry)
File: `src/gator_command/scripts/gator-state.py`
Applies one planned action for one entry-point file. Returns an outcome string. Private.
Filesystem: entry-point file (RW), rollback file (W on corrupted)
! `restore-block` re-reads the file and re-parses via `find_managed_block()` — defensive against the file changing between plan and execute (returns `skipped-race` if the sentinel pair is no longer well-formed).
! `foreign` files are NEVER modified — the outcome is `skipped-foreign` and the user is referred to `gatorize` (Invariant #7-adjacent: no silent ownership claims).

### render_repair_text(plan, dry_run)
File: `src/gator_command/scripts/gator-state.py`
Concise text rendering of the repair plan (dry-run: "would ...") or outcomes. Always ends with a constitution-deferred line and a local-companions-preserved line.
<- `main_repair()`

### render_repair_json(plan, dry_run)
File: `src/gator_command/scripts/gator-state.py`
Serializes the repair plan/outcomes to indented JSON. Top-level fields: `schema`, `dry_run`, `actions`, `constitution` (fixed `"repair-deferred-v1"`), `local_companions` (fixed `"preserved"`).
<- `main_repair()`

### main_status(args)
File: `src/gator_command/scripts/gator-state.py`
Subcommand entry point. Resolves the repo via `find_gator_root(args.path)`, collects status, and prints text or JSON. Returns 0 on success, 1 if no `.gator/` was found.
<- `main()`
-> `find_gator_root()`, `collect_status()`, `render_status_text()`, `render_status_json()`

### main_repair(args)
File: `src/gator_command/scripts/gator-state.py`
Subcommand entry point. Resolves the repo, builds a plan (optionally scoped to a single filename), and either prints the dry-run preview or executes and prints outcomes. Returns 0 on success, 1 if no `.gator/` was found.
<- `main()`
-> `find_gator_root()`, `plan_repair()`, `execute_repair()`, `render_repair_text()`, `render_repair_json()`

### main()
File: `src/gator_command/scripts/gator-state.py`
CLI entry point. Calls `ensure_utf8_stdout()` first (cross-cutting TRIPWIRE), builds the argparse tree, dispatches to `main_status()` or `main_repair()`. Exits with the subcommand's return code.
<- `if __name__ == "__main__"`, `src/gator_command/cli.py` (via `_run_script`)
! `ensure_utf8_stdout()` must run BEFORE any `print()` — Windows default encoding breaks the ASCII prompts otherwise. Required by the UTF-8 stdout TRIPWIRE in `scripts-cross-cutting.md`.

---

## TRIPWIRE: Two Baseline Sources With Different Lifecycles

Managed state has **two independent baselines**, not one. Conflating them is the whiteboard-round-9 bug: an earlier draft of this TRIPWIRE claimed both flowed through `resolve_template_source()`, but `render_entry_content()` is a Python function in the `gator_command` package — there is no template file to resolve for it.

- **Entry-point baseline** is `render_entry_content(has_command_post=False, agent_type)` from the currently-imported `gator_command` package. Host-scoped: it moves when the host's `gator` install advances (`pipx upgrade`). Not a file, not overridable, not routed through `resolve_template_source()`. Consequences:
  - Entry-point files that were `clean` before a `pipx upgrade` may report `modified` after, even with no local edits — this is the intentional Git-analog behavior (see Invariant #8 of the Stage plan).
  - `gator state status` does NOT accept `--source` (Round 9 remediation) — a flag that appeared to influence the entry-point baseline but did not.
  - `gator state repair` writes bytes from the same in-process `render_entry_content()` — same baseline the future `gator update` block-refresh (Stage 4b) will use.
- **Constitution baseline** is the file at `resolve_template_source(gator_dir).constitution.md`. Moves when the template source moves (`product-source.json` rebind, upstream template update, or a re-`gatorize`). This is where `--source` semantics belong in the future if we add a comparison flag — a plan-level decision, not implicit.
- `has_command_post` is hardcoded `False` at every call site that computes an entry-point baseline (Invariant #13 in the Stage plan). Do NOT call `find_command_post()` at check time — that reintroduces a retired mode.

The `gator state status` JSON declares this explicitly:
```
"entry_point_baseline_kind": "installed-package-code",
"constitution_baseline_source": "<path>" | null
```
Any future refactor that reads code from the template source (Stage 6+ option) MUST bump the schema and rewrite this TRIPWIRE.

## TRIPWIRE: Repair Never Touches *.local.md Files

`gator state repair` explicitly enumerates the three tracked entry-point filenames. Adding a fourth filename (or any dynamic filename discovery) is a plan-level decision. `*.local.md` files are NEVER included — they are user-owned. Only `local_companion_present()` even references those filenames, and only via `.exists()`.

## TRIPWIRE: Source-Repo Constitution Exemption

The source `gator-command` repo IS the constitution baseline — there is no upstream to drift from. `is_source_repo()` returns True when both `.gator/mission.md` and root `constitution.md` are present; the check returns `"source-repo-exempt"` and NO byte-compare runs. Do NOT weaken this guard — a false-negative would report the authoritative constitution as "drifted" and prompt users to "restore" it against a template that was generated FROM it.

## Before Changing This Module

- Bumping `SCHEMA` from `gator-state-v1` requires migrating downstream consumers (tests, dashboard integration when it lands in Stage 6+).
- Adding a new `BlockState` value means adding a new dispatch branch in `_plan_action_for_state()` AND `_execute_one()` AND `render_status_text()` AND `render_repair_text()`.
- Adding a new subcommand: add a sibling `main_<name>()` function + a `sub.add_parser(...)` block in `_build_parser()` + a dispatch branch in `main()`. Keep JSON output schema-versioned.
- Any change that reads or writes a `*.local.md` file is a plan-level violation — reject and route through the Architect.

## Connections

-> [scripts-installer](scripts-installer.md) — `render_entry_content()`, `upgrade_legacy_entry_point()`, `managed_block.py` API
-> [scripts-repo-lifecycle](scripts-repo-lifecycle.md) — future Stage 4b extension of `plan_updates()` / `execute_updates()` to refresh managed blocks; reuses the same six-state classification
-> [scripts-cross-cutting](scripts-cross-cutting.md) — UTF-8 stdout, JSON schema versioning, plan/execute separation, `gator_core` import convention
-> [scripts-layout](scripts-layout.md) — `get_gator_paths()` for constitution path resolution across v1/v2 layouts
-> [Local Agent Overrides + Managed State plan](../artifacts/2026-07-28-local-agent-overrides-and-managed-state-plan.md) — Stage 4 (this module)
-> [Index](INDEX.md)
