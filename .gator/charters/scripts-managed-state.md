# Charter: Managed State

**Covers**: `src/gator_command/scripts/gator-state.py`

## Owns

The `gator state` CLI surface (schema `gator-state-v2`):

- `gator state status`: a host-vs-repo version diagnostic and detection-only constitution drift for fleet repos. It also gives an **informational** view of native agent files (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`): present or absent, whether an older Gator left a historical block, and whether a `*.local.md` companion exists.
- `gator state repair`: a **no-write compatibility stub**. It accepts the old arguments, explains that Gator no longer manages native agent files, and exits 0.

Since the gator-native entry point (2026-10-08), native agent files are repository-owned. Gator's entry document is `GATOR_INIT.md` (see [`scripts-repo-lifecycle.md`](scripts-repo-lifecycle.md)).

## Does Not Own

- Sentinel parsing: `gatorize/managed_block.py` (`GATOR_BEGIN`, `GATOR_END`, `detect_legacy_gator_content`).
- Baseline resolution: reuses `gator_core.resolve_template_source()`.
- Any write to a native agent file or `*.local.md`. Nothing in this module writes to the repository.
- Any mutation of the source-repo `constitution.md`. The source repo's root constitution IS the baseline, and `is_source_repo()` guards this.

---

## Schema
File: `src/gator_command/scripts/gator-state.py`
The module-level constant `"gator-state-v2"` appears at the top of every JSON payload (`status` and `repair`), per the JSON Schema Versioning TRIPWIRE in `scripts-cross-cutting.md`.
! v2 (2026-10-08) removed `entry_points` and `entry_point_baseline_kind` and added `native_files`. Removing fields is a meaning change, hence the bump from v1. New fields inside v2 are additive.

### is_source_repo(repo_root)
File: `src/gator_command/scripts/gator-state.py`
Returns True iff `repo_root/gator-command/mission.md` and root `constitution.md` both exist. Used to short-circuit the constitution drift check with the `"source-repo-exempt"` verdict.
Filesystem: `repo_root/gator-command/mission.md` (R), `repo_root/constitution.md` (R)
<- `check_constitution()`
! Both signals must be present. A repo with only one of them is NOT the source repo and receives normal drift checks. (The detector probes `gator-command/mission.md`; this charter previously said `.gator/mission.md`. That earlier wording was charter drift, not a code change.)

### read_repo_gator_version(repo_root)
File: `src/gator_command/scripts/gator-state.py`
Reads the `cli-version` field from `.gator/.gator-version`. Never raises; a missing file, unreadable content or absent key all return None.
Filesystem: `.gator/.gator-version` (R)
<- `collect_status()` for the version-diagnostic line
! Diagnostics only. It MUST NOT be treated as a baseline.

### local_companion_present(repo_root, filename)
File: `src/gator_command/scripts/gator-state.py`
Returns True if `<VENDOR>.local.md` exists at the repo root. It NEVER reads the file; it only calls `.exists()`.
<- `describe_native_file()`
! Ownership boundary (Invariant #7). Any code path here that opens a `*.local.md` file is a bug.

### describe_native_file(repo_root, filename)
File: `src/gator_command/scripts/gator-state.py`
Returns `{filename, present, managed: False, historical_gator_block, local_companion}` for one native agent file. Read-only.
Filesystem: `repo_root/<filename>` (R)
<- `collect_status()`
-> `GATOR_BEGIN` / `GATOR_END` / `detect_legacy_gator_content()`, `local_companion_present()`
! `historical_gator_block` is True for any sentinel bytes (well-formed or corrupted) or a legacy fingerprint. It is history, not drift: no caller may turn it into a repair proposal or a failure.

### check_constitution(repo_root, templates_dir) / check_constitution_drift(repo_root)
File: `src/gator_command/scripts/gator-state.py`
`check_constitution` returns `{"status": ...}`, one of `source-repo-exempt` / `no-baseline` / `no-repo-constitution` / `clean` / `modified`. `check_constitution_drift` resolves the template source itself and never raises (failure → `no-baseline`).
Filesystem: `templates_dir/constitution.md` (R), `get_gator_paths(repo_root).constitution` (R)
<- `collect_status()`; `gator-init._constitution_drift_suffix()` (via `import_sibling("gator-state")`)
! Constitution is detection-only, never repaired. `check_constitution_drift` takes only `repo_root` so `gator init` stays ignorant of template resolution.

### collect_status(repo_root)
File: `src/gator_command/scripts/gator-state.py`
Assembles `schema`, `repo_root`, `host_cli_version`, `repo_gator_version`, `constitution_baseline_source`, `native_files` and `constitution`.
<- `main_status()`
-> `resolve_template_source()`, `describe_native_file()`, `check_constitution()`, `get_version()`, `read_repo_gator_version()`

### render_status_text(report) / render_status_json(report)
File: `src/gator_command/scripts/gator-state.py`
Text: the version diagnostic, a `native agent files (not managed by Gator):` section (`absent` / `present` / `present · historical Gator block (not refreshed)`) and the constitution verdict. JSON: the report dict.
<- `main_status()`
! Text must not use drift, failure or repair vocabulary for native files.

### render_repair_text(dry_run) / render_repair_json(dry_run) / main_repair(args)
File: `src/gator_command/scripts/gator-state.py`
The compatibility stub. Text: "Nothing to repair…" plus the constitution-deferred and local-companions-preserved lines. JSON: `{schema, dry_run, actions: [], native_files: "not-managed", constitution: "repair-deferred-v1", local_companions: "preserved"}`. It accepts `filename`, `--dry-run` and `--json` for compatibility and returns 0 (1 only when no `.gator/` is found).
<- `main()`
! Writes nothing. Removing the stub is a separate, later Architect decision.

### main_status(args) / main()
File: `src/gator_command/scripts/gator-state.py`
`main()` calls `ensure_utf8_stdout()` first, builds the argparse tree and dispatches. `main_status` resolves the repo via `find_gator_root(args.path)` and prints text or JSON; it returns 1 if no `.gator/` is found.
<- `src/gator_command/cli.py` (via `_run_script`)

---

## TRIPWIRE: Native Agent Files Are Not Managed

`gator state` never creates, edits, backs up, or repairs `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, or `*.local.md`. Status reports them for information only. An absent or team-owned file is normal, and a historical Gator block is labeled "not refreshed", never "modified" or "drift". The retired six-state status/repair, the `<VENDOR>_ROLLBACK.md` backups and the entry-point renderer are gone. Pins: `tests/test_state.py` (`TestStatusV2`, `TestRepairStub`).

## TRIPWIRE: Source-Repo Constitution Exemption

The source repo IS the constitution baseline. `is_source_repo()` short-circuits to `"source-repo-exempt"`, and NO byte-compare runs. Do NOT weaken this guard; a false negative would report the authoritative constitution as "drifted".

## Before Changing This Module

- Bumping `SCHEMA` from `gator-state-v2` requires migrating downstream consumers (tests only today; the Dashboard does not read it).
- Any change that writes to the repository, or reads a `*.local.md` file, is a plan-level violation. Reject it and route it through the Architect.

## Connections

-> [scripts-installer](scripts-installer.md) — `managed_block.py` parsing API; native-file ownership TRIPWIRE
-> [scripts-repo-update](scripts-repo-update.md) — update never touches native files either
-> [scripts-repo-lifecycle](scripts-repo-lifecycle.md) — `GATOR_INIT.md` handoff; `_constitution_drift_suffix()` consumer
-> [scripts-cross-cutting](scripts-cross-cutting.md) — UTF-8 stdout, JSON schema versioning, `gator_core` import convention
-> [scripts-layout](scripts-layout.md) — `get_gator_paths()` for constitution path resolution across v1/v2 layouts
-> [Index](INDEX.md)
