# Charter: Audit and Repository Intelligence

**Covers**: `src/gator_command/scripts/gator-audit.py`, `src/gator_command/scripts/gator-audit-renderers.py`, `src/gator_command/scripts/gator-repo-status.py`

## Owns

- Fleet audit assembly and text/HTML rendering.
- Per-repository governance status, charter coverage, hook health, trailer history, and recent session summaries.
- Decision filtering and session-evidence presentation.

## Does Not Own

- Low-level fleet scanning and drift comparison; see [`scripts-fleet-intelligence.md`](scripts-fleet-intelligence.md).
- Session parsing, grouping, and cache identity; see [`scripts-session-archaeology.md`](scripts-session-archaeology.md).
- Dashboard HTTP or browser rendering.

---

### assemble_audit_data(since_days=7)
File: src/gator_command/scripts/gator-audit.py
Join fleet status, drift, trailer intelligence, committed decisions, and optional session summaries into one audit schema.
<- audit CLI and dashboard audit data
-> fleet/drift modules, session reader/aggregator
! Optional sibling failure degrades the corresponding section only and remains visible in output.

### _committed_decisions_from_snippets()
File: src/gator_command/scripts/gator-audit.py
Read committed summary decisions through the canonical parser and attach source provenance.
<- `assemble_audit_data()`
-> `gator_session_reader.parse_committed_summary()`
! Do not duplicate summary parsing in audit code.

### _collect_trailer_intelligence()
File: src/gator_command/scripts/gator-audit.py
Aggregate change type, significance, agent, Architect/legacy PI, machine identity, and override events from recent commits.
<- `assemble_audit_data()`
-> Git trailer readers, `gator_core.override_event_fields()`
! Accept historical trailer vocabulary while emitting current field names.
! Override events come from `override_event_fields()` (v1 + v2 + legacy shapes); each event carries `override_type`, `approver`, `block_id`, `reason`, `rules`, plus `repo`/`hash`/`timestamp` (#34).

### _is_real_decision(text)
File: src/gator_command/scripts/gator-audit.py
Filter empty/template/no-op decision text without rewriting substantive content.
<- committed-decision collection
! Keep filtering conservative; uncertainty is evidence, not permission to discard.

### render_text(data) / render_html(data)
File: src/gator_command/scripts/gator-audit-renderers.py
Render one assembled audit payload into human-readable formats.
<- audit CLI
! Renderers do not recompute governance state or perform network access.

### _handle_sessions(args) / _render_sessions_text()
File: src/gator_command/scripts/gator-audit.py
Load cached or refreshed session summaries for one repo or the fleet.
<- audit `--sessions`
-> session aggregator
! Fleet/refresh session flags without `--sessions` are rejected rather than silently ignored.

### scan_repo_status(repo_path, repo_name)
File: src/gator_command/scripts/gator-repo-status.py
Assemble per-repository health from charters, trailers, hooks, sessions, and current Git state.
<- repo-status CLI and dashboard
-> coverage/trailer/hook/session helpers
! Every field is scoped to the resolved requested repository.

### get_charter_coverage(repo_path)
File: src/gator_command/scripts/gator-repo-status.py
Compute bounded charter count/coverage/staleness signals for the repository.
<- `scan_repo_status()`
! Coverage is a structural heuristic and is labeled accordingly.

### get_trailer_data(repo_path, lookback_days, limit)
File: src/gator_command/scripts/gator-repo-status.py
Read recent governed commit trailers with backward-compatible Architect attribution.
<- `scan_repo_status()`
-> Git, `gator_core.override_event_fields()`
! Bound history reads by both date and count.
! `entry["override"]` and `override_events` use `override_event_fields()`; events carry `override_type`, `approver`, `block_id`, `reason`, `rules`, `hash`, `timestamp` (#34).

### get_hook_status(repo_path)
File: src/gator_command/scripts/gator-repo-status.py
Report managed-hook presence/configuration without repairing it.
<- `scan_repo_status()`
-> updater hook probes
! Status collection is read-only and uses the same canonical hook directory as installation.

### resolve_repo(repo_name, repo_path_arg)
File: src/gator_command/scripts/gator-repo-status.py
Resolve one explicit path or registry identity.
<- repo-status CLI
! Missing or ambiguous repos fail explicitly; do not substitute another repo.

### get_session_summaries(repo_path, limit=20)
File: src/gator_command/scripts/gator-repo-status.py
Read recent committed summaries through the canonical reader and tag local provenance.
<- `scan_repo_status()`
-> session reader
! Missing optional reader yields an unavailable/empty session section, not total status failure.

## Before Changing This Module

- Keep assembly separate from rendering.
- Preserve per-repo scoping and source provenance.
- Exercise missing optional modules, legacy trailers, and no-session repositories.
- Run audit, repo-status, session-reader, and dashboard-data tests.

## Connections

-> [Fleet Status and Drift](scripts-fleet-intelligence.md) - base fleet/drift inputs
-> [Session Archaeology](scripts-session-archaeology.md) - canonical summaries and grouping
-> [Dashboard Server](scripts-dashboard.md) - API consumer
-> [Cross-Cutting](scripts-cross-cutting.md) - schemas and optional imports
