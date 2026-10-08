# Charter: Repository Update and Policy Sync

**Covers**: `src/gator_command/scripts/gator-update.py`, `src/gator_command/scripts/gator-policy-status.py`, `src/gator_command/templates/gator-starter/scripts/gator-update.py`

## Owns

- Read-only update planning followed by explicit template and hook execution.
- v1/v2 layout-aware routing and explicit migration.
- Managed Git-hook wrappers and `core.hooksPath` convergence.
- Optional organization-policy source, sync state, cache, and status output.

## Does Not Own

- Fresh repository installation; see [`scripts-installer.md`](scripts-installer.md).
- Session boot and hook dispatch; see [`scripts-repo-lifecycle.md`](scripts-repo-lifecycle.md).
- Layout classification constants; see [`scripts-layout.md`](scripts-layout.md).
- Enterprise control-plane policy APIs.

---

### plan_file_update() / plan_updates()
File: src/gator_command/scripts/gator-update.py
Compare shipped templates with the resolved repository destinations without writing.
Filesystem: template source and `.gator/` layout (R)
<- update `main()`
-> layout resolver, template routing tables
! Planning is side-effect free. Dry-run output must describe the same actions execution would take.
! User-visible scaffolding is routed from `gator_layout.USER_VISIBLE_SCAFFOLDING`; do not duplicate the filename set locally.
! `TEMPLATE_FILES` (both copies) includes `GATOR_INIT.md`, so an ordinary update adds the bootstrap document to a repo that predates it and refreshes it idempotently.

## TRIPWIRE: Native Agent Files Are Repository-Owned

`gator update` (both copies) never reads, creates, refreshes, backs up, or edits `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, or `*.local.md` (gator-native entry point, 2026-10-08). Historical `GATOR:BEGIN`/`GATOR:END` blocks keep their exact bytes, and no `.pre-gator-update` sibling is written. The Gator entry document is `GATOR_INIT.md`, delivered through `TEMPLATE_FILES`. The retired Stage 4b entry-point plan/execute pair and the template copy's inlined managed-block helpers are gone. Do not reintroduce native-file writes here; an opt-in adapter would be a separate, explicit command. Pins: `TestUpdateLeavesNativeFilesUntouched` in `tests/test_template_sync.py`.

### merge_hooks_into_settings() / install_vendor_hooks()
File: src/gator_command/scripts/gator-update.py
Merge managed vendor hook commands while preserving unrelated user commands.
Filesystem: vendor settings (RW)
<- update execution
! Recognize prior and current Gator hook shapes so migration is idempotent and never duplicates hooks.

### build_git_hook_wrappers() / install_git_hooks()
File: src/gator_command/scripts/gator-update.py
Build thin managed wrappers that invoke the installed `gator hook` dispatcher and configure the canonical hook path.
Filesystem: managed hook directory and Git config (RW)
<- init repair, update, installation
-> Python launcher preference resolver
! Refuse an unresolvable explicit launcher rather than writing wrappers that cannot execute.
! Wrapper generation, health probes, and display paths agree on the same canonical directory.

### execute_updates()
File: src/gator_command/scripts/gator-update.py
Apply a previously built overlay plan and create required destination directories.
Filesystem: shipped `.gator/` content (W)
<- update `main()`
! Execute only actions present in the plan; discovery during execution would invalidate dry-run guarantees.

### migrate_layout()
File: src/gator_command/scripts/gator-update.py
Move shipped content into the v2 included tree while preserving user content and reporting mixed-layout residue.
Filesystem: `.gator/` and `.gator/.includes/` (RW)
<- explicit `--migrate-layout`
-> layout classifier, residue enumerator
! Migration is explicit and refuses unresolved conflicts. A normal update never flips layout generation.
! Mixed-residue reporting mirrors every category recognized by the classifier.

### print_json_plan()
File: src/gator_command/scripts/gator-update.py
Emit the versioned machine-readable update plan.
<- update `--json`
! Preserve `gator-update-v1` compatibility; removing or renaming fields requires a schema bump.
! `entry_point_actions` and `summary.entry_point_actions` remain for v1 compatibility and are always `[]` / `0`.

### main()
File: src/gator_command/scripts/gator-update.py
Resolve templates, self-heal stale product-source metadata when safe, plan, preview or execute updates, and stamp version state.
<- `gator update`, dashboard update action
-> planning/execution helpers, policy sync
! `cli-version` records every successful verification, even when no files changed. The `updated` timestamp changes only when state changed.
! Product-source self-heal is best-effort and package/template-copy synchronized; direct fleet copies without templates retain the explicit source error.

### load_governance_source() / derive_governance_source() / get_governance_source()
File: src/gator_command/scripts/gator-policy-status.py
Resolve explicit or derived policy authority and distinguish standalone from inconsistent topology.
Filesystem: governance source metadata (R)
<- policy status and update
! Do not invent a remote or command-post source when no valid authority is configured.

### compute_sync_state() / sync_policy()
File: src/gator_command/scripts/gator-policy-status.py
Compare source and cached policy, then explicitly synchronize the local policy cache and link metadata.
Filesystem: policy cache/link (RW during sync)
<- status output and update policy channel
! Product templates and organization policy are separate channels. Template update remains valid for standalone repos.

### init_governance_source()
File: src/gator_command/scripts/gator-policy-status.py
Initialize or replace policy-source metadata under explicit force rules.
<- policy CLI
! Rebinding authority is a distinct, explicit action; routine status/update does not silently change it.

## Before Changing This Module

- Keep plan and execute phases behaviorally aligned.
- Test both layout generations, mixed-layout refusal, and user-visible scaffolding routing.
- Check package/template mirror parity for shipped update code.
- Run update, layout, hooks, policy, and packaging tests relevant to the change.

## Connections

-> [Session Boot](scripts-repo-lifecycle.md) - health checks and hook dispatch
-> [Installer](scripts-installer.md) - fresh-install helpers and shipped root files
-> [Layout Resolver](scripts-layout.md) - path classification and routing constants
-> [Managed State](scripts-managed-state.md) - native-file status reporting
-> [Cross-Cutting](scripts-cross-cutting.md) - copy sync and machine-local preferences
