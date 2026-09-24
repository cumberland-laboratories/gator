# Charter: Fleet Status and Drift

**Covers**: `src/gator_command/scripts/gator-fleet-report.py`, `src/gator_command/scripts/gator-fleet-intel.py`, `src/gator_command/scripts/gator-drift.py`

## Owns

- Local and remote fleet repository status with a shared result shape.
- Governance drift comparison against configured authority.
- Lightweight repository profiles used for fleet-level intelligence.

## Does Not Own

- Dashboard transport or rendering; see the Dashboard charters.
- Per-repository deep status, audit reports, and session evidence; see [`scripts-audit-intelligence.md`](scripts-audit-intelligence.md).
- Registry persistence and Git cache primitives; see [`scripts-core-library.md`](scripts-core-library.md).
- Policy synchronization; see [`scripts-repo-update.md`](scripts-repo-update.md).

---

### read_gator_state(repo_path)
File: src/gator_command/scripts/gator-fleet-report.py
Read current local governance state into the fleet row schema.
Filesystem: repo `.gator/` and Git metadata (R)
<- `scan_repo()`
! Local state fields remain schema-compatible with `gator_remote.read_gator_state_remote()`.

### scan_repo(repo_entry, force_remote=False)
File: src/gator_command/scripts/gator-fleet-report.py
Prefer a healthy local checkout and fall back to the remote cache when requested or necessary.
<- `scan_fleet()`
-> local readers, `gator_remote`
! Fallback preserves provenance and error state; remote data is never labeled as a successful local scan.

### get_last_commit() / get_commit_count() / get_current_branch() / get_working_tree_status() / get_latest_trailers()
File: src/gator_command/scripts/gator-fleet-report.py
Collect bounded Git signals used in fleet health rows.
<- `scan_repo()`
-> Git
! Git failure affects only its field and does not erase otherwise useful repository state.

### scan_fleet(repos, force_remote=False)
File: src/gator_command/scripts/gator-fleet-report.py
Scan registry entries in stable order and return one result per repository.
<- CLI and dashboard data collection
-> `scan_repo()`
! Missing/deleted repositories remain represented with an explicit status so registry cleanup is possible.

### print_fleet_report() / print_json_report()
File: src/gator_command/scripts/gator-fleet-report.py
Render human and versioned machine output from the same result list.
<- fleet-report CLI
! JSON retains its top-level schema identifier; text-only labels do not leak into the wire contract.

### read_command_post_policy()
File: src/gator_command/scripts/gator-drift.py
Read legacy policy authority only when that topology is valid.
<- drift scan
! Absence of authority is a distinct standalone state, not automatic drift.

### check_repo_drift() / check_repo_drift_remote()
File: src/gator_command/scripts/gator-drift.py
Compare local or remote governance state with the same policy baseline and finding vocabulary.
<- drift CLI and audit
-> fleet readers, policy status
! Local and remote paths return equivalent fields and severity meaning.

### build_profile(name, repo_path)
File: src/gator_command/scripts/gator-fleet-intel.py
Collect bounded activity, mission, charter, thread, and issue signals for one repository.
Filesystem: repo Git and `.gator/` knowledge surfaces (R)
<- fleet-intel CLI
! Profiles summarize evidence; they do not infer governance compliance beyond available signals.

### render_thread(profile)
File: src/gator_command/scripts/gator-fleet-intel.py
Render a lightweight fleet-intelligence thread from a profile.
<- fleet-intel CLI
! Generated summaries remain source-attributed and bounded.

## TRIPWIRE: Local/Remote Parity

When a local reader has a remote counterpart, add or change fields on both paths and their consumers together. A remote scan may be less complete, but shared field names and meanings do not diverge.

## Before Changing This Module

- Exercise healthy local, missing local, stale cache, and forced-remote paths.
- Compare text and JSON output from the same fixture.
- Run fleet, drift, remote-cache, and dashboard-data tests.

## Connections

-> [Audit and Repo Intelligence](scripts-audit-intelligence.md) - deeper per-repo and session evidence
-> [Core Library](scripts-core-library.md) - Git and remote-cache helpers
-> [Dashboard Server](scripts-dashboard.md) - fleet consumer
-> [Repo Update](scripts-repo-update.md) - policy authority and sync state
-> [Cross-Cutting](scripts-cross-cutting.md) - schema and fallback contracts
